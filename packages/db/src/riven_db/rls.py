"""Row-level security for tenant tables (S03.2.2, ADR 0013).

Request transactions run as the restricted role `riven_app` with `app.org_id` set; the RLS
policy on every tenant table only shows and accepts rows of that org. Without an org context
a query returns zero rows. System jobs (migrations, seed, relay, nightly checks) run as the
login role, which owns the tables and is not subject to RLS.

New tenant tables must call `enable_rls(op, "<table>")` in their migration;
`test_rls.py` fails otherwise.
"""

from typing import Any

from sqlalchemy import Connection, event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

APP_ROLE = "riven_app"
POLICY = "tenant_isolation"
ORG_SETTING = "app.org_id"


def create_app_role_sql() -> list[str]:
    return [
        f"""DO $$ BEGIN
              IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                CREATE ROLE {APP_ROLE} NOLOGIN;
              END IF;
            END $$""",
        f"GRANT {APP_ROLE} TO CURRENT_USER",
        f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}",
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}",
        f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}",
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}",
    ]


def enable_rls(op: Any, table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {POLICY} ON {table} "
        f"USING (org_id = current_setting('{ORG_SETTING}', true)) "
        f"WITH CHECK (org_id = current_setting('{ORG_SETTING}', true))"
    )


def disable_rls(op: Any, table: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS {POLICY} ON {table}")
    op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")


ORG_INFO_KEY = "riven_org_id"


@event.listens_for(Session, "after_begin")
def _apply_org_context(session: Session, _transaction: Any, connection: Connection) -> None:
    """Every transaction of an org-scoped session runs as `riven_app` with `app.org_id` set.
    SET LOCAL ends with the transaction, so a pooled connection never leaks the context."""
    org_id = session.info.get(ORG_INFO_KEY)
    if org_id:
        connection.exec_driver_sql(f"SET LOCAL ROLE {APP_ROLE}")
        connection.execute(
            text("SELECT set_config(:name, :org, true)"), {"name": ORG_SETTING, "org": org_id}
        )


def tenant_session(sessions: async_sessionmaker[AsyncSession], org_id: str) -> AsyncSession:
    """A session whose every query is confined to `org_id` by row-level security."""
    if not org_id:
        raise ValueError("tenant_session requires an org_id")
    return sessions(info={ORG_INFO_KEY: org_id})
