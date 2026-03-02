"""Fix events.id default for TimescaleDB chunks (SERIAL not inherited).

Revision ID: 002
Revises: 001
Create Date: 2026-03-02

"""
from typing import Sequence, Union

from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # TimescaleDB chunks may not inherit SERIAL default. Create sequence and set default.
    op.execute("CREATE SEQUENCE IF NOT EXISTS events_id_seq OWNED BY events.id")
    op.execute(
        "SELECT setval('events_id_seq', COALESCE((SELECT max(id) FROM events), 0) + 1)"
    )
    op.execute("ALTER TABLE events ALTER COLUMN id SET DEFAULT nextval('events_id_seq'::regclass)")


def downgrade() -> None:
    op.execute("ALTER TABLE events ALTER COLUMN id DROP DEFAULT")
