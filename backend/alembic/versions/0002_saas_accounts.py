"""SaaS accounts: plans, workspaces, memberships, invites, email tokens, platform settings.

Existing users each get a personal workspace that takes ownership of their analyses
and cases. The former "admin" becomes the platform "owner".

Revision ID: 0002
Revises: 0001
"""
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

PLANS = [
    ("free", "Free", "Try DeepShield on a few files a month.", 10, 10, 1, 0, True, 0),
    ("pro", "Pro", "For journalists, creators and investigators.", 300, 100, 1, 1900, True, 1),
    ("business", "Business", "Team workspace with shared investigations.", 2000, 100, 10, 9900, True, 2),
    ("internal", "Internal (unlimited)", "Platform owner and staff.", -1, 100, 50, 0, False, 9),
]


def _ts():
    return sa.DateTime(timezone=True)


# 0001 created these FKs without explicit names. On SQLite they are reflected through a naming
# convention so batch mode can drop them; PostgreSQL auto-names them <table>_<column>_fkey.
_NAMING = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def _batch(table: str):
    return op.batch_alter_table(table, naming_convention=_NAMING) if _is_sqlite() else op.batch_alter_table(table)


def _user_fk_name(table: str) -> str:
    return f"fk_{table}_user_id_users" if _is_sqlite() else f"{table}_user_id_fkey"


def upgrade() -> None:
    now = datetime.now(timezone.utc)
    op.create_table(
        "plans",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("monthly_scans", sa.Integer, nullable=False),
        sa.Column("max_upload_mb", sa.Integer, nullable=False),
        sa.Column("max_members", sa.Integer, nullable=False),
        sa.Column("price_monthly_cents", sa.Integer, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("public", sa.Boolean, nullable=False),
        sa.Column("sort", sa.Integer, nullable=False),
        sa.Column("created_at", _ts(), nullable=False),
    )
    plans = sa.table("plans", *[sa.column(c) for c in (
        "id", "name", "description", "monthly_scans", "max_upload_mb", "max_members", "price_monthly_cents",
        "currency", "public", "sort")], sa.column("created_at", _ts()))
    op.bulk_insert(plans, [dict(id=p[0], name=p[1], description=p[2], monthly_scans=p[3], max_upload_mb=p[4],
                                max_members=p[5], price_monthly_cents=p[6], currency="usd", public=p[7], sort=p[8],
                                created_at=now) for p in PLANS])

    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("plan_id", sa.String(40), sa.ForeignKey("plans.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("credits", sa.Integer, nullable=False),
        sa.Column("scan_quota_override", sa.Integer, nullable=True),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", _ts(), nullable=False),
    )
    op.create_table(
        "memberships",
        sa.Column("org_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("created_at", _ts(), nullable=False),
    )
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])
    op.create_table(
        "invites",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("org_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("invited_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("expires_at", _ts(), nullable=False),
        sa.Column("accepted_at", _ts(), nullable=True),
        sa.Column("created_at", _ts(), nullable=False),
    )
    op.create_index("ix_invites_org_id", "invites", ["org_id"])
    op.create_index("ix_invites_email", "invites", ["email"])
    op.create_table(
        "email_tokens",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose", sa.String(20), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", _ts(), nullable=False),
        sa.Column("used_at", _ts(), nullable=True),
        sa.Column("created_at", _ts(), nullable=False),
    )
    op.create_index("ix_email_tokens_user_id", "email_tokens", ["user_id"])
    op.create_table(
        "platform_settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.JSON, nullable=True),
    )
    settings = sa.table("platform_settings", sa.column("key"), sa.column("value", sa.JSON))
    op.bulk_insert(settings, [{"key": "signups_open", "value": True},
                              {"key": "require_email_verification", "value": True}])

    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("status", sa.String(20), nullable=False, server_default="active"))
        b.add_column(sa.Column("email_verified_at", _ts(), nullable=True))
        b.add_column(sa.Column("token_version", sa.Integer, nullable=False, server_default="0"))
        b.add_column(sa.Column("active_org_id", sa.Integer, nullable=True))
        b.add_column(sa.Column("last_login_at", _ts(), nullable=True))
        b.create_foreign_key("fk_users_active_org", "organizations", ["active_org_id"], ["id"], ondelete="SET NULL")
    # Work products now belong to the workspace: deleting a user detaches authorship (SET NULL)
    # instead of deleting team data (was CASCADE in 0001).
    for table in ("analyses", "cases", "case_notes"):
        with _batch(table) as b:
            if table != "case_notes":
                b.add_column(sa.Column("org_id", sa.Integer, nullable=True))
            if table == "analyses":
                b.add_column(sa.Column("parent_id", sa.String(20), nullable=True))
            b.alter_column("user_id", existing_type=sa.Integer, nullable=True)
            b.drop_constraint(_user_fk_name(table), type_="foreignkey")
            b.create_foreign_key(f"fk_{table}_user_id_users", "users", ["user_id"], ["id"], ondelete="SET NULL")

    # Data: a personal workspace per existing user. Raw SQL binds: SQLite stores naive UTC text.
    conn = op.get_bind()
    if _is_sqlite():
        now = now.replace(tzinfo=None)
    users = conn.execute(sa.text("SELECT id, email, role, created_at FROM users ORDER BY id")).fetchall()
    for uid, email, role, created in users:
        owner = role == "admin"
        res = conn.execute(sa.text(
            "INSERT INTO organizations (name, kind, plan_id, status, credits, created_by, created_at) "
            "VALUES (:n, 'personal', :p, 'active', 0, :u, :c)"),
            {"n": f"{email.split('@')[0]}'s workspace", "p": "internal" if owner else "free", "u": uid, "c": now})
        org_id = res.lastrowid if res.lastrowid else conn.execute(
            sa.text("SELECT max(id) FROM organizations WHERE created_by = :u"), {"u": uid}).scalar()
        conn.execute(sa.text("INSERT INTO memberships (org_id, user_id, role, created_at) VALUES (:o, :u, 'owner', :c)"),
                     {"o": org_id, "u": uid, "c": now})
        conn.execute(sa.text("UPDATE users SET active_org_id = :o, role = :r, email_verified_at = :v WHERE id = :u"),
                     {"o": org_id, "r": "owner" if owner else "user", "v": created or now, "u": uid})
        conn.execute(sa.text("UPDATE analyses SET org_id = :o WHERE user_id = :u"), {"o": org_id, "u": uid})
        conn.execute(sa.text("UPDATE cases SET org_id = :o WHERE user_id = :u"), {"o": org_id, "u": uid})
    # Embedded-media children inherit their own row's org (already set via user); mark them as children.
    conn.execute(sa.text("DELETE FROM analyses WHERE org_id IS NULL"))
    conn.execute(sa.text("DELETE FROM cases WHERE org_id IS NULL"))

    with op.batch_alter_table("analyses") as b:
        b.alter_column("org_id", existing_type=sa.Integer, nullable=False)
        b.create_foreign_key("fk_analyses_org", "organizations", ["org_id"], ["id"], ondelete="CASCADE")
        b.create_index("ix_analyses_org_id", ["org_id"])
        b.create_index("ix_analyses_parent_id", ["parent_id"])
    with op.batch_alter_table("cases") as b:
        b.alter_column("org_id", existing_type=sa.Integer, nullable=False)
        b.create_foreign_key("fk_cases_org", "organizations", ["org_id"], ["id"], ondelete="CASCADE")
        b.create_index("ix_cases_org_id", ["org_id"])


def downgrade() -> None:
    with op.batch_alter_table("cases") as b:
        b.drop_index("ix_cases_org_id")
        b.drop_constraint("fk_cases_org", type_="foreignkey")
        b.drop_column("org_id")
    with op.batch_alter_table("analyses") as b:
        b.drop_index("ix_analyses_parent_id")
        b.drop_index("ix_analyses_org_id")
        b.drop_constraint("fk_analyses_org", type_="foreignkey")
        b.drop_column("parent_id")
        b.drop_column("org_id")
    with op.batch_alter_table("users") as b:
        b.drop_constraint("fk_users_active_org", type_="foreignkey")
        for c in ("last_login_at", "active_org_id", "token_version", "email_verified_at", "status"):
            b.drop_column(c)
    op.execute("UPDATE users SET role = 'admin' WHERE role = 'owner'")
    op.execute("UPDATE users SET role = 'analyst' WHERE role = 'user'")
    for t in ("platform_settings", "email_tokens", "invites", "memberships", "organizations", "plans"):
        op.drop_table(t)
