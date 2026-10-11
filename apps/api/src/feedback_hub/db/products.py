from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from feedback_hub.github.eligibility import EligibilityResult


@dataclass(frozen=True, slots=True)
class RegisteredProduct:
    id: UUID
    name: str
    created_at: datetime
    repository_id: UUID
    github_node_id: str
    full_name: str
    html_url: str
    default_branch: str
    license_spdx: str
    license_checked_at: datetime | None


_SELECT_PRODUCT = """
select
  p.id, p.name, p.created_at,
  r.id as repository_id, r.github_node_id, r.full_name, r.html_url, r.default_branch,
  r.license_spdx,
  (select max(c.checked_at) from public.repository_license_checks c
    where c.repository_id = r.id) as license_checked_at
from public.products p
join public.github_repositories r on r.product_id = p.id
"""


async def get_product(conn: AsyncConnection) -> RegisteredProduct | None:
    row = (await conn.execute(text(_SELECT_PRODUCT))).first()
    return RegisteredProduct(**row._mapping) if row else None


async def product_exists(conn: AsyncConnection) -> bool:
    result = await conn.execute(text("select exists (select 1 from public.products)"))
    return bool(result.scalar_one())


async def create_github_product(
    conn: AsyncConnection, *, tenant_id: UUID, actor_id: UUID, eligibility: EligibilityResult
) -> UUID:
    repo = eligibility.repository
    if repo.license_spdx is None:
        raise ValueError("Eligible repositories always carry a license.")

    product_id: UUID = (
        await conn.execute(
            text(
                "insert into public.products (tenant_id, name, created_by) "
                "values (:tenant_id, :name, :actor_id) returning id"
            ),
            {"tenant_id": tenant_id, "name": repo.name, "actor_id": actor_id},
        )
    ).scalar_one()

    repository_id: UUID = (
        await conn.execute(
            text(
                "insert into public.github_repositories (tenant_id, product_id, github_node_id, "
                "owner, name, full_name, html_url, default_branch, license_spdx) values "
                "(:tenant_id, :product_id, :node_id, :owner, :name, :full_name, :html_url, "
                ":default_branch, :license_spdx) returning id"
            ),
            {
                "tenant_id": tenant_id,
                "product_id": product_id,
                "node_id": repo.node_id,
                "owner": repo.owner,
                "name": repo.name,
                "full_name": repo.full_name,
                "html_url": repo.html_url,
                "default_branch": repo.default_branch,
                "license_spdx": repo.license_spdx,
            },
        )
    ).scalar_one()

    await conn.execute(
        text(
            "insert into public.repository_license_checks "
            "(tenant_id, repository_id, eligible, reasons, license_spdx) "
            "values (:tenant_id, :repository_id, :eligible, :reasons, :license_spdx)"
        ),
        {
            "tenant_id": tenant_id,
            "repository_id": repository_id,
            "eligible": eligibility.eligible,
            "reasons": [reason.value for reason in eligibility.reasons],
            "license_spdx": repo.license_spdx,
        },
    )
    return product_id
