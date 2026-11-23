"""add guardrail columns to requests

Records what services/guardrails.py decided for each request: the
prompt-injection score, how many PII values were redacted (and of which
types), which model tier the router picked and its P(hard), and — for
requests routed to the small model — what the large model would have
cost, so /v1/metrics can report savings from routing.

status gains a new value, "blocked", for requests stopped by the
injection classifier; it's a plain String column, so no schema change is
needed for that.

Revision ID: 0004_guardrail_columns
Revises: 0003_tz_aware_timestamps
Create Date: 2026-11-23

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0004_guardrail_columns"
down_revision: Union[str, None] = "0003_tz_aware_timestamps"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("requests", sa.Column("injection_score", sa.Float(), nullable=True))
    op.add_column("requests", sa.Column("redaction_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("requests", sa.Column("redaction_types", sa.String(), nullable=True))
    op.add_column("requests", sa.Column("route", sa.String(), nullable=True))
    op.add_column("requests", sa.Column("router_score", sa.Float(), nullable=True))
    op.add_column("requests", sa.Column("cost_if_large_usd", sa.Float(), nullable=True))


def downgrade() -> None:
    for col in ("cost_if_large_usd", "router_score", "route", "redaction_types", "redaction_count", "injection_score"):
        op.drop_column("requests", col)
