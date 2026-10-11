from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from feedback_hub.api.me import default_workspace_name
from feedback_hub.api.repositories import RepositoryRequest, check_repository, get_github_client
from feedback_hub.auth import CurrentUser
from feedback_hub.config import Settings, get_settings
from feedback_hub.db.engine import Database, UserConnection, get_database
from feedback_hub.db.products import (
    RegisteredProduct,
    create_github_product,
    get_product,
    product_exists,
)
from feedback_hub.db.workspaces import ensure_workspace, record_audit_event
from feedback_hub.github.client import GitHubClient

router = APIRouter(prefix="/v1/product", tags=["product"])

ALREADY_REGISTERED = "This workspace already has a registered product."


class RepositoryOut(BaseModel):
    id: UUID
    github_node_id: str
    full_name: str
    html_url: str
    default_branch: str
    license_spdx: str
    license_checked_at: datetime | None


class ProductOut(BaseModel):
    id: UUID
    name: str
    created_at: datetime
    repository: RepositoryOut

    @classmethod
    def from_record(cls, product: RegisteredProduct) -> "ProductOut":
        return cls(
            id=product.id,
            name=product.name,
            created_at=product.created_at,
            repository=RepositoryOut(
                id=product.repository_id,
                github_node_id=product.github_node_id,
                full_name=product.full_name,
                html_url=product.html_url,
                default_branch=product.default_branch,
                license_spdx=product.license_spdx,
                license_checked_at=product.license_checked_at,
            ),
        )


@router.get("", response_model=ProductOut)
async def read_product(conn: UserConnection) -> ProductOut:
    product = await get_product(conn)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No product registered yet.")
    return ProductOut.from_record(product)


@router.post("/github", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def register_github_product(
    body: RepositoryRequest,
    user: CurrentUser,
    database: Annotated[Database, Depends(get_database)],
    github: Annotated[GitHubClient, Depends(get_github_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ProductOut:
    eligibility = await check_repository(body.repository, github, settings)
    repo = eligibility.repository

    if not eligibility.eligible:
        async with database.user_transaction(user) as conn:
            workspace = await ensure_workspace(conn, default_workspace_name(user.email))
            await record_audit_event(
                conn,
                tenant_id=workspace.tenant_id,
                actor_id=user.id,
                action="product.registration_rejected",
                target_type="github_repository",
                target_id=repo.node_id,
                metadata={
                    "full_name": repo.full_name,
                    "reasons": [r.value for r in eligibility.reasons],
                },
            )
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {
                "message": "Repository is not eligible.",
                "repository": repo.full_name,
                "reasons": [r.value for r in eligibility.reasons],
            },
        )

    try:
        async with database.user_transaction(user) as conn:
            workspace = await ensure_workspace(conn, default_workspace_name(user.email))
            if await product_exists(conn):
                raise HTTPException(status.HTTP_409_CONFLICT, ALREADY_REGISTERED)
            product_id = await create_github_product(
                conn, tenant_id=workspace.tenant_id, actor_id=user.id, eligibility=eligibility
            )
            await record_audit_event(
                conn,
                tenant_id=workspace.tenant_id,
                actor_id=user.id,
                action="product.registered",
                target_type="product",
                target_id=str(product_id),
                metadata={"full_name": repo.full_name, "license": repo.license_spdx},
            )
            product = await get_product(conn)
    except IntegrityError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, ALREADY_REGISTERED) from exc

    if product is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Product was not persisted.")
    return ProductOut.from_record(product)
