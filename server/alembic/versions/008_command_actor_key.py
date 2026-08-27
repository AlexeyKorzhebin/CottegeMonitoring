"""Add nullable actor_key_id on commands (API-key actor).

Revision ID: 008
Revises: 007
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "commands",
        sa.Column(
            "actor_key_id",
            UUID(as_uuid=True),
            sa.ForeignKey("api_keys.id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("commands", "actor_key_id")
