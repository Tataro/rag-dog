"""multi-user: users, ownership columns, and RLS

Revision ID: 0002_multi_user_rls
Revises: 0001_init
Create Date: 2026-06-02
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_multi_user_rls"
down_revision: str | None = "0001_init"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OWNED = ["documents", "chunks", "conversations", "messages"]


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("picture", sa.Text(), nullable=True),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "allowed_emails",
        sa.Column("email", sa.Text(), primary_key=True),
        sa.Column("added_by", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ⚠️ Disposable POC data has no owner; wipe before adding NOT NULL user_id.
    op.execute("DELETE FROM messages")
    op.execute("DELETE FROM conversations")
    op.execute("DELETE FROM chunks")
    op.execute("DELETE FROM documents")

    for tbl in _OWNED:
        op.add_column(
            tbl,
            sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        )
        op.create_index(f"{tbl}_user_id_idx", tbl, ["user_id"])

    # Conversations are no longer keyed by (channel, external_id).
    op.drop_constraint("uq_conversations_channel_external", "conversations", type_="unique")
    op.alter_column("conversations", "external_id", nullable=True)
    op.create_index("conversations_user_time", "conversations", ["user_id", "created_at"])

    # RLS: force it even for the table owner, default-deny when app.user_id is unset.
    # NULLIF(..., '') is required: a custom GUC reverts to an EMPTY STRING (not NULL)
    # after a transaction-local set_config, so on a pooled connection that previously
    # served a request `current_setting('app.user_id', true)` returns '' — and ''::uuid
    # raises. NULLIF maps '' -> NULL so an unset GUC safely matches no rows.
    for tbl in _OWNED:
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {tbl}_isolation ON {tbl}
            USING (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid)
            WITH CHECK (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid)
            """
        )

    # Least-privilege runtime role. The owner/superuser role bypasses RLS entirely
    # (FORCE only binds the table owner, never a superuser), so the application MUST
    # connect as a NON-superuser, NON-BYPASSRLS role for the policies above to take
    # effect (ADR 0005). Roles are cluster-global, so create idempotently; the local
    # password is for dev/test convenience — production should provision the role and
    # set its password out-of-band (the IF NOT EXISTS guard leaves a pre-made role
    # untouched). We deliberately do NOT drop the role on downgrade, because another
    # database in the same cluster may still depend on it.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ragdog_app') THEN
                CREATE ROLE ragdog_app LOGIN PASSWORD 'ragdog_app' NOSUPERUSER NOBYPASSRLS;
            END IF;
        END
        $$
        """
    )
    op.execute("GRANT USAGE ON SCHEMA public TO ragdog_app")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ragdog_app")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ragdog_app"
    )


def downgrade() -> None:
    # Release ragdog_app's privileges (so the role could be dropped later if desired),
    # but do NOT drop the role — another database in the cluster may still use it.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ragdog_app') THEN
                ALTER DEFAULT PRIVILEGES IN SCHEMA public
                    REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM ragdog_app;
                REVOKE SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public FROM ragdog_app;
                REVOKE USAGE ON SCHEMA public FROM ragdog_app;
            END IF;
        END
        $$
        """
    )
    for tbl in _OWNED:
        op.execute(f"DROP POLICY IF EXISTS {tbl}_isolation ON {tbl}")
        op.execute(f"ALTER TABLE {tbl} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY")
    op.drop_index("conversations_user_time", table_name="conversations")
    op.alter_column("conversations", "external_id", nullable=False)
    op.create_unique_constraint(
        "uq_conversations_channel_external", "conversations", ["channel", "external_id"]
    )
    for tbl in _OWNED:
        op.drop_index(f"{tbl}_user_id_idx", table_name=tbl)
        op.drop_column(tbl, "user_id")
    op.drop_table("allowed_emails")
    op.drop_table("users")
