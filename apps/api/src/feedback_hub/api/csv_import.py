from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from feedback_hub.api.me import default_workspace_name
from feedback_hub.auth import CurrentUser
from feedback_hub.config import Settings, get_settings
from feedback_hub.db.csv_feedback import create_csv_import, upsert_csv_rows
from feedback_hub.db.engine import Database, get_database
from feedback_hub.db.products import get_product
from feedback_hub.db.workspaces import ensure_workspace, record_audit_event
from feedback_hub.feedback.csv_import import CsvEncodingError, CsvTooLargeError, decode_csv
from feedback_hub.feedback.csv_schema import RowError, parse_feedback_csv

router = APIRouter(prefix="/v1/product", tags=["product"])

_MAX_REASONS = 20


class CsvImportOut(BaseModel):
    import_id: UUID
    imported_count: int
    warnings: list[str]


def rejection(errors: list[RowError], warnings: list[str]) -> dict[str, object]:
    reasons = [f"Row {error.row}: {error.message}" for error in errors[:_MAX_REASONS]]
    remaining = len(errors) - len(reasons)
    if remaining > 0:
        reasons.append(f"{remaining} more row errors.")
    return {
        "message": "The CSV was rejected. No rows were saved.",
        "reasons": reasons,
        "warnings": warnings,
    }


@router.post("/csv", response_model=CsvImportOut, status_code=status.HTTP_201_CREATED)
async def upload_csv(
    user: CurrentUser,
    database: Annotated[Database, Depends(get_database)],
    settings: Annotated[Settings, Depends(get_settings)],
    file: Annotated[UploadFile, File()],
) -> CsvImportOut:
    try:
        text = decode_csv(await file.read(), max_bytes=settings.csv_max_bytes)
    except CsvTooLargeError as exc:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"CSV is larger than {settings.csv_max_bytes} bytes.",
        ) from exc
    except CsvEncodingError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {"message": "CSV must be UTF-8 text.", "reasons": []},
        ) from exc

    report = parse_feedback_csv(
        text,
        max_rows=settings.csv_max_rows,
        max_feedback_chars=settings.csv_max_feedback_chars,
    )
    if not report.ok:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, rejection(report.errors, report.warnings)
        )

    async with database.user_transaction(user) as conn:
        workspace = await ensure_workspace(conn, default_workspace_name(user.email))
        product = await get_product(conn)
        if product is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No product registered yet.")
        import_id = await create_csv_import(
            conn,
            tenant_id=workspace.tenant_id,
            actor_id=user.id,
            product_id=product.id,
            repository_id=product.repository_id,
            row_count=len(report.rows),
        )
        await upsert_csv_rows(
            conn,
            tenant_id=workspace.tenant_id,
            product_id=product.id,
            import_id=import_id,
            rows=report.rows,
        )
        await record_audit_event(
            conn,
            tenant_id=workspace.tenant_id,
            actor_id=user.id,
            action="csv.imported",
            target_type="import",
            target_id=str(import_id),
            metadata={"imported_count": len(report.rows)},
        )
    return CsvImportOut(
        import_id=import_id, imported_count=len(report.rows), warnings=report.warnings
    )
