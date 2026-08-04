"""Create the complete SawtAI section 4.3 schema.

Revision ID: 0001_core_schema
Revises: None
Create Date: 2026-08-04
"""

from pathlib import Path

from alembic import op

revision = "0001_core_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema_sql = Path(__file__).with_name("0001_core_schema.sql").read_text(encoding="utf-8")
    op.get_bind().exec_driver_sql(schema_sql)


def downgrade() -> None:
    # Prototype bootstrap migration: schemas contain only objects created here.
    op.execute("DROP SCHEMA IF EXISTS restricted CASCADE")
    op.execute("DROP SCHEMA IF EXISTS core CASCADE")

