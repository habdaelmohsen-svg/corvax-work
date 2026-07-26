"""prepaid expenses engine v024

Revision ID: e24000000001
Revises: e22000000001
"""
from alembic import op
import sqlalchemy as sa

revision = 'e24000000001'
down_revision = 'e22000000001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'prepaid_expenses',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('number', sa.String(40), nullable=False),
        sa.Column('name_ar', sa.String(250), nullable=False),
        sa.Column('name_en', sa.String(250), nullable=False),
        sa.Column('supplier_name', sa.String(250)),
        sa.Column('payment_date', sa.Date(), nullable=False),
        sa.Column('service_start_date', sa.Date(), nullable=False),
        sa.Column('service_end_date', sa.Date(), nullable=False),
        sa.Column('allocation_method', sa.String(30), nullable=False),
        sa.Column('net_amount', sa.Numeric(18,2), nullable=False),
        sa.Column('vat_rate', sa.Numeric(8,4), nullable=False),
        sa.Column('vat_amount', sa.Numeric(18,2), nullable=False),
        sa.Column('gross_amount', sa.Numeric(18,2), nullable=False),
        sa.Column('amortized_amount', sa.Numeric(18,2), nullable=False),
        sa.Column('remaining_amount', sa.Numeric(18,2), nullable=False),
        sa.Column('prepaid_account_id', sa.Integer(), sa.ForeignKey('accounts.id'), nullable=False),
        sa.Column('expense_account_id', sa.Integer(), sa.ForeignKey('accounts.id'), nullable=False),
        sa.Column('bank_account_id', sa.Integer(), sa.ForeignKey('bank_accounts.id'), nullable=False),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id')),
        sa.Column('cost_center_id', sa.Integer(), sa.ForeignKey('cost_centers.id')),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('initial_journal_id', sa.Integer(), sa.ForeignKey('journal_entries.id'), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('company_id','number',name='uq_prepaid_company_number'),
    )
    op.create_index('ix_prepaid_expenses_company_id','prepaid_expenses',['company_id'])
    op.create_index('ix_prepaid_expenses_number','prepaid_expenses',['number'])
    op.create_index('ix_prepaid_expenses_status','prepaid_expenses',['status'])
    op.create_table(
        'prepaid_expense_schedules',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('prepaid_expense_id', sa.Integer(), sa.ForeignKey('prepaid_expenses.id', ondelete='CASCADE'), nullable=False),
        sa.Column('period_date', sa.Date(), nullable=False),
        sa.Column('amount', sa.Numeric(18,2), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('journal_id', sa.Integer(), sa.ForeignKey('journal_entries.id')),
        sa.Column('posted_by', sa.Integer(), sa.ForeignKey('users.id')),
        sa.Column('posted_at', sa.DateTime()),
        sa.UniqueConstraint('prepaid_expense_id','period_date',name='uq_prepaid_schedule_period'),
    )
    op.create_index('ix_prepaid_expense_schedules_prepaid_expense_id','prepaid_expense_schedules',['prepaid_expense_id'])
    op.create_index('ix_prepaid_expense_schedules_period_date','prepaid_expense_schedules',['period_date'])
    op.create_index('ix_prepaid_expense_schedules_status','prepaid_expense_schedules',['status'])

    # Add the default prepaid account to existing companies when upgrading an existing database.
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE asset_categories SET depreciation_convention='FULL_MONTH_BY_15TH' WHERE depreciation_convention='HALF_MONTH_15_DAY'"))
    companies = conn.execute(sa.text('SELECT id FROM companies')).fetchall()
    for (company_id,) in companies:
        exists = conn.execute(sa.text("SELECT 1 FROM accounts WHERE company_id=:c AND code='117010'"), {'c': company_id}).fetchone()
        if not exists:
            parent = conn.execute(sa.text("SELECT id FROM accounts WHERE company_id=:c AND code='110000'"), {'c': company_id}).fetchone()
            conn.execute(sa.text("""
                INSERT INTO accounts (company_id, code, name_ar, name_en, account_type, statement_group, parent_id, level, is_postable, is_cash, active)
                VALUES (:c, '117010', 'المصروفات المدفوعة مقدمًا', 'Prepaid Expenses', 'ASSET', 'PREPAID_EXPENSES', :p, 3, 1, 0, 1)
            """), {'c': company_id, 'p': parent[0] if parent else None})


def downgrade():
    op.drop_table('prepaid_expense_schedules')
    op.drop_table('prepaid_expenses')
