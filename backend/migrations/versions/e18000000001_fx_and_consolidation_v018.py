"""foreign currency and consolidation v018

Revision ID: e18000000001
Revises: d95c5098650e
"""
from alembic import op
import sqlalchemy as sa

revision = 'e18000000001'
down_revision = 'd95c5098650e'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('currencies',
        sa.Column('code', sa.String(3), primary_key=True),
        sa.Column('name_ar', sa.String(100), nullable=False),
        sa.Column('name_en', sa.String(100), nullable=False),
        sa.Column('decimal_places', sa.Integer(), nullable=False, server_default='2'),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_table('exchange_rates',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('currency_code', sa.String(3), sa.ForeignKey('currencies.code'), nullable=False),
        sa.Column('rate_date', sa.Date(), nullable=False),
        sa.Column('rate', sa.Numeric(18,8), nullable=False),
        sa.Column('source', sa.String(100), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('company_id','currency_code','rate_date',name='uq_fx_rate_company_currency_date'))
    op.create_index('ix_exchange_rates_company_id','exchange_rates',['company_id'])
    op.create_index('ix_exchange_rates_currency_code','exchange_rates',['currency_code'])
    op.create_index('ix_exchange_rates_rate_date','exchange_rates',['rate_date'])
    op.create_table('foreign_currency_balances',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('accounts.id'), nullable=False),
        sa.Column('currency_code', sa.String(3), sa.ForeignKey('currencies.code'), nullable=False),
        sa.Column('foreign_amount', sa.Numeric(18,4), nullable=False),
        sa.Column('carrying_amount', sa.Numeric(18,2), nullable=False),
        sa.Column('last_rate', sa.Numeric(18,8), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('company_id','account_id','currency_code',name='uq_fx_balance_account_currency'))
    op.create_index('ix_foreign_currency_balances_company_id','foreign_currency_balances',['company_id'])
    op.create_index('ix_foreign_currency_balances_account_id','foreign_currency_balances',['account_id'])
    op.create_table('fx_revaluation_runs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('revaluation_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('total_gain', sa.Numeric(18,2), nullable=False),
        sa.Column('total_loss', sa.Numeric(18,2), nullable=False),
        sa.Column('journal_id', sa.Integer(), sa.ForeignKey('journal_entries.id')),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False))
    op.create_index('ix_fx_revaluation_runs_company_id','fx_revaluation_runs',['company_id'])
    op.create_index('ix_fx_revaluation_runs_revaluation_date','fx_revaluation_runs',['revaluation_date'])
    op.create_table('consolidation_groups',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('code', sa.String(30), nullable=False, unique=True),
        sa.Column('name_ar', sa.String(200), nullable=False),
        sa.Column('name_en', sa.String(200), nullable=False),
        sa.Column('reporting_currency', sa.String(3), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False))
    op.create_table('consolidation_members',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('group_id', sa.Integer(), sa.ForeignKey('consolidation_groups.id', ondelete='CASCADE'), nullable=False),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('ownership_percent', sa.Numeric(8,4), nullable=False),
        sa.Column('effective_date', sa.Date(), nullable=False),
        sa.UniqueConstraint('group_id','company_id',name='uq_consolidation_group_company'))
    op.create_index('ix_consolidation_members_group_id','consolidation_members',['group_id'])
    op.create_index('ix_consolidation_members_company_id','consolidation_members',['company_id'])
    op.create_table('consolidation_runs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('group_id', sa.Integer(), sa.ForeignKey('consolidation_groups.id', ondelete='CASCADE'), nullable=False),
        sa.Column('period_end', sa.Date(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('total_debit', sa.Numeric(18,2), nullable=False),
        sa.Column('total_credit', sa.Numeric(18,2), nullable=False),
        sa.Column('elimination_amount', sa.Numeric(18,2), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False))
    op.create_index('ix_consolidation_runs_group_id','consolidation_runs',['group_id'])
    op.create_index('ix_consolidation_runs_period_end','consolidation_runs',['period_end'])
    op.create_table('consolidation_lines',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('run_id', sa.Integer(), sa.ForeignKey('consolidation_runs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('account_code', sa.String(30), nullable=False),
        sa.Column('account_name_ar', sa.String(250), nullable=False),
        sa.Column('account_name_en', sa.String(250), nullable=False),
        sa.Column('debit', sa.Numeric(18,2), nullable=False),
        sa.Column('credit', sa.Numeric(18,2), nullable=False),
        sa.Column('is_elimination', sa.Boolean(), nullable=False))
    op.create_index('ix_consolidation_lines_run_id','consolidation_lines',['run_id'])
    op.create_index('ix_consolidation_lines_account_code','consolidation_lines',['account_code'])

def downgrade():
    for table in ['consolidation_lines','consolidation_runs','consolidation_members','consolidation_groups','fx_revaluation_runs','foreign_currency_balances','exchange_rates','currencies']:
        op.drop_table(table)
