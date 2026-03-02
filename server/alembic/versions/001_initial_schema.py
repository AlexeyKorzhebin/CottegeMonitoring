"""Initial schema: houses, objects, current_state, events, schema_versions, commands

Revision ID: 001
Revises:
Create Date: 2026-03-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;")

    op.create_table(
        "houses",
        sa.Column("house_id", sa.String(64), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("online_status", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
    )

    op.create_table(
        "objects",
        sa.Column("house_id", sa.String(64),
                  sa.ForeignKey("houses.house_id"), nullable=False),
        sa.Column("ga", sa.String(16), nullable=False),
        sa.Column("object_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(256), nullable=True),
        sa.Column("datatype", sa.Integer(), nullable=False),
        sa.Column("units", sa.String(32), server_default=""),
        sa.Column("tags", sa.Text(), server_default=""),
        sa.Column("comment", sa.Text(), server_default=""),
        sa.Column("schema_hash", sa.String(128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_timeseries", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("house_id", "ga"),
    )
    op.create_index("idx_objects_house_active", "objects", ["house_id", "is_active"])

    op.create_table(
        "current_state",
        sa.Column("house_id", sa.String(64),
                  sa.ForeignKey("houses.house_id"), nullable=False),
        sa.Column("ga", sa.String(16), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", JSONB(), nullable=False),
        sa.Column("datatype", sa.Integer(), nullable=False),
        sa.Column("server_received_ts", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("house_id", "ga"),
    )

    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("house_id", sa.String(64), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("seq", sa.BigInteger(), nullable=True),
        sa.Column("type", sa.String(32), nullable=True),
        sa.Column("ga", sa.String(16), nullable=True),
        sa.Column("object_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(256), nullable=True),
        sa.Column("datatype", sa.Integer(), nullable=True),
        sa.Column("value", JSONB(), nullable=True),
        sa.Column("raw_json", JSONB(), nullable=False),
        sa.Column("server_received_ts", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.execute("SELECT create_hypertable('events', 'ts', migrate_data => true);")
    op.create_index("idx_events_house_ts", "events", ["house_id", sa.text("ts DESC")])
    op.create_index("idx_events_house_ga_ts", "events", ["house_id", "ga", sa.text("ts DESC")])

    op.create_table(
        "schema_versions",
        sa.Column("house_id", sa.String(64),
                  sa.ForeignKey("houses.house_id"), nullable=False),
        sa.Column("schema_hash", sa.String(128), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("raw_meta_json", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("house_id", "schema_hash"),
    )

    op.create_table(
        "commands",
        sa.Column("request_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("house_id", sa.String(64),
                  sa.ForeignKey("houses.house_id"), nullable=False),
        sa.Column("ts_sent", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("ts_ack", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="sent"),
        sa.Column("results", JSONB(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("idx_commands_house_ts", "commands", ["house_id", sa.text("ts_sent DESC")])
    op.create_index(
        "idx_commands_status", "commands", ["status"],
        postgresql_where=sa.text("status = 'sent'"),
    )


def downgrade() -> None:
    op.drop_table("commands")
    op.drop_table("schema_versions")
    op.drop_table("events")
    op.drop_table("current_state")
    op.drop_table("objects")
    op.drop_table("houses")
