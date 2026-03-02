"""Add devices table and device_id to all entity tables.

Revision ID: 003
Revises: 002
Create Date: 2026-03-02

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "devices",
        sa.Column("house_id", sa.String(64),
                  sa.ForeignKey("houses.house_id"), nullable=False),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("online_status", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("house_id", "device_id"),
    )

    op.add_column("objects", sa.Column("device_id", sa.String(64), nullable=True))
    op.add_column("current_state", sa.Column("device_id", sa.String(64), nullable=True))
    op.add_column("events", sa.Column("device_id", sa.String(64), nullable=True))
    op.add_column("commands", sa.Column("device_id", sa.String(64), nullable=True))

    # schema_versions: add device_id and recreate PK
    op.add_column("schema_versions", sa.Column("device_id", sa.String(64),
                                                nullable=False, server_default=""))
    conn = op.get_bind()
    r = conn.execute(sa.text(
        "SELECT conname FROM pg_constraint "
        "WHERE conrelid = 'schema_versions'::regclass AND contype = 'p'"
    ))
    row = r.fetchone()
    if row:
        op.drop_constraint(row[0], "schema_versions", type_="primary")
    op.create_primary_key(
        "schema_versions_pkey", "schema_versions",
        ["house_id", "device_id", "schema_hash"],
    )


def downgrade() -> None:
    conn = op.get_bind()
    r = conn.execute(sa.text(
        "SELECT conname FROM pg_constraint "
        "WHERE conrelid = 'schema_versions'::regclass AND contype = 'p'"
    ))
    row = r.fetchone()
    if row:
        op.drop_constraint(row[0], "schema_versions", type_="primary")
    op.create_primary_key(
        "schema_versions_pkey", "schema_versions",
        ["house_id", "schema_hash"],
    )
    op.drop_column("schema_versions", "device_id")

    op.drop_column("commands", "device_id")
    op.drop_column("events", "device_id")
    op.drop_column("current_state", "device_id")
    op.drop_column("objects", "device_id")

    op.drop_table("devices")
