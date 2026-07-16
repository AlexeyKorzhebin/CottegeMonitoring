"""Add TimescaleDB retention + compression policies for events.

Revision ID: 006
Revises: 005
"""

from typing import Sequence, Union

from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Compress chunks older than 7 days (segment by house for efficient queries).
    op.execute(
        """
        ALTER TABLE events SET (
          timescaledb.compress,
          timescaledb.compress_segmentby = 'house_id'
        )
        """
    )
    op.execute(
        """
        SELECT add_compression_policy('events', INTERVAL '7 days', if_not_exists => TRUE)
        """
    )
    # Drop raw chunks older than 365 days.
    op.execute(
        """
        SELECT add_retention_policy('events', INTERVAL '365 days', if_not_exists => TRUE)
        """
    )


def downgrade() -> None:
    op.execute("SELECT remove_retention_policy('events', if_exists => TRUE)")
    op.execute("SELECT remove_compression_policy('events', if_exists => TRUE)")
    op.execute("ALTER TABLE events SET (timescaledb.compress = false)")
