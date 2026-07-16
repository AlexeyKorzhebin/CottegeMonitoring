"""Unique index for QoS1 event dedup (house, device, seq, ts).

TimescaleDB requires unique indexes to include the partitioning column (ts).

Revision ID: 007
Revises: 006
"""

from typing import Sequence, Union

from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove exact QoS1 duplicates before unique index (keep lowest id).
    op.execute(
        """
        DELETE FROM events a
        USING events b
        WHERE a.ctid > b.ctid
          AND a.house_id = b.house_id
          AND a.device_id IS NOT DISTINCT FROM b.device_id
          AND a.seq = b.seq
          AND a.ts = b.ts
          AND a.seq IS NOT NULL
        """
    )
    # Partial unique: only when seq is present (client sequence).
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_events_dedup
          ON events (house_id, device_id, seq, ts)
          WHERE seq IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_events_dedup")
