"""Add personal lending and borrowing records.

Revision ID: 003_personal_loans
Revises: 002_conversations
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "003_personal_loans"
down_revision: Union[str, None] = "002_conversations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    existing_tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "personal_loans" not in existing_tables:
        op.create_table(
            "personal_loans",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("person_name", sa.String(length=255), nullable=False),
            sa.Column("loan_type", sa.String(length=20), nullable=False),
            sa.Column("original_amount", sa.Numeric(precision=12, scale=2), nullable=False),
            sa.Column("outstanding_amount", sa.Numeric(precision=12, scale=2), nullable=False),
            sa.Column("transaction_date", sa.Date(), nullable=False),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("loan_type IN ('lent', 'borrowed')", name="ck_personal_loans_type"),
            sa.CheckConstraint("original_amount > 0", name="ck_personal_loans_original_amount"),
            sa.CheckConstraint(
                "outstanding_amount >= 0 AND outstanding_amount <= original_amount",
                name="ck_personal_loans_outstanding_amount",
            ),
            sa.CheckConstraint(
                "status IN ('active', 'partially_paid', 'settled')",
                name="ck_personal_loans_status",
            ),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_personal_loans_user_id", "personal_loans", ["user_id"])
        op.create_index("ix_personal_loans_user_person", "personal_loans", ["user_id", "person_name"])
        op.create_index("ix_personal_loans_user_status", "personal_loans", ["user_id", "status"])

    existing_tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "loan_repayments" not in existing_tables:
        op.create_table(
            "loan_repayments",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("loan_id", sa.Integer(), nullable=False),
            sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
            sa.Column("repayment_date", sa.Date(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("idempotency_key", sa.String(length=64), nullable=False),
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("amount > 0", name="ck_loan_repayments_amount"),
            sa.ForeignKeyConstraint(["loan_id"], ["personal_loans.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("idempotency_key", name="uq_loan_repayments_idempotency_key"),
        )
        op.create_index("ix_loan_repayments_loan_id", "loan_repayments", ["loan_id"])
        op.create_index("ix_loan_repayments_loan_date", "loan_repayments", ["loan_id", "repayment_date"])


def downgrade() -> None:
    op.drop_index("ix_loan_repayments_loan_date", table_name="loan_repayments")
    op.drop_index("ix_loan_repayments_loan_id", table_name="loan_repayments")
    op.drop_table("loan_repayments")
    op.drop_index("ix_personal_loans_user_status", table_name="personal_loans")
    op.drop_index("ix_personal_loans_user_person", table_name="personal_loans")
    op.drop_index("ix_personal_loans_user_id", table_name="personal_loans")
    op.drop_table("personal_loans")
