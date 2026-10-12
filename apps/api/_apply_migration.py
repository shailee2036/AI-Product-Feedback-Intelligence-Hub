import asyncio
from pathlib import Path

import asyncpg

from feedback_hub.config import get_settings

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "supabase"
    / "migrations"
    / "20261012040000_gemini_embedding_dimensions.sql"
)


async def main() -> None:
    settings = get_settings()
    if settings.database_url is None:
        raise SystemExit("database url is not configured")
    connection = await asyncpg.connect(settings.database_url.get_secret_value())
    try:
        await connection.execute(MIGRATION.read_text(encoding="utf-8"))
        kind = await connection.fetchval(
            "select format_type(a.atttypid, a.atttypmod) from pg_attribute a "
            "join pg_class c on c.oid = a.attrelid "
            "join pg_namespace n on n.oid = c.relnamespace "
            "where n.nspname = 'public' and c.relname = 'feedback_embeddings' "
            "and a.attname = 'embedding'"
        )
    finally:
        await connection.close()
    print("applied", kind)


asyncio.run(main())
