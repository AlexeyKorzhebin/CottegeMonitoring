"""Add operation_traces table for MCP/command latency diagnostics.

Revision ID: 005
Revises: 004
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "operation_traces",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("house_id", sa.String(64), nullable=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("ref", sa.String(128), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(32), nullable=True),
        sa.Column("details", JSONB, nullable=True),
    )
    op.create_index("idx_operation_traces_ts", "operation_traces", ["ts"])
    op.create_index("idx_operation_traces_kind_ts", "operation_traces", ["kind", "ts"])
    op.create_index("idx_operation_traces_house_ts", "operation_traces", ["house_id", "ts"])


def downgrade() -> None:
    op.drop_index("idx_operation_traces_house_ts", table_name="operation_traces")
    op.drop_index("idx_operation_traces_kind_ts", table_name="operation_traces")
    op.drop_index("idx_operation_traces_ts", table_name="operation_traces")
    op.drop_table("operation_traces")
