"""accruals recurring journals and close controls v026

Revision ID: e26000000001
Revises: e24000000001
"""
from alembic import op
import sqlalchemy as sa

revision = 'e26000000001'
down_revision = 'e24000000001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'accrual_entries',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('number', sa.String(40), nullable=False),
        sa.Column('accrual_type', sa.String(30), nullable=False),
        sa.Column('name_ar', sa.String(250), nullable=False),
        sa.Column('name_en', sa.String(250), nullable=False),
        sa.Column('reference', sa.String(120)),
        sa.Column('accrual_date', sa.Date(), nullable=False),
        sa.Column('amount', sa.Numeric(18,2), nullable=False),
        sa.Column('debit_account_id', sa.Integer(), sa.ForeignKey('accounts.id'), nullable=False),
        sa.Column('credit_account_id', sa.Integer(), sa.ForeignKey('accounts.id'), nullable=False),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id')),
        sa.Column('cost_center_id', sa.Integer(), sa.ForeignKey('cost_centers.id')),
        sa.Column('auto_reverse', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('reversal_date', sa.Date()),
        sa.Column('status', sa.String(25), nullable=False, server_default='DRAFT'),
        sa.Column('journal_id', sa.Integer(), sa.ForeignKey('journal_entries.id')),
        sa.Column('reversal_journal_id', sa.Integer(), sa.ForeignKey('journal_entries.id')),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('posted_by', sa.Integer(), sa.ForeignKey('users.id')),
        sa.Column('reversed_by', sa.Integer(), sa.ForeignKey('users.id')),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('posted_at', sa.DateTime()),
        sa.Column('reversed_at', sa.DateTime()),
        sa.UniqueConstraint('company_id','number',name='uq_accrual_company_number'),
    )
    op.create_index('ix_accrual_entries_company_id','accrual_entries',['company_id'])
    op.create_index('ix_accrual_entries_number','accrual_entries',['number'])
    op.create_index('ix_accrual_entries_accrual_type','accrual_entries',['accrual_type'])
    op.create_index('ix_accrual_entries_accrual_date','accrual_entries',['accrual_date'])
    op.create_index('ix_accrual_entries_reversal_date','accrual_entries',['reversal_date'])
    op.create_index('ix_accrual_entries_status','accrual_entries',['status'])

    op.create_table(
        'recurring_journal_templates',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('code', sa.String(50), nullable=False),
        sa.Column('name_ar', sa.String(250), nullable=False),
        sa.Column('name_en', sa.String(250), nullable=False),
        sa.Column('reference_prefix', sa.String(80), nullable=False, server_default='REC'),
        sa.Column('frequency', sa.String(20), nullable=False, server_default='MONTHLY'),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date()),
        sa.Column('next_run_date', sa.Date(), nullable=False),
        sa.Column('auto_post', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('company_id','code',name='uq_recurring_company_code'),
    )
    op.create_index('ix_recurring_journal_templates_company_id','recurring_journal_templates',['company_id'])
    op.create_index('ix_recurring_journal_templates_code','recurring_journal_templates',['code'])
    op.create_index('ix_recurring_journal_templates_next_run_date','recurring_journal_templates',['next_run_date'])
    op.create_index('ix_recurring_journal_templates_active','recurring_journal_templates',['active'])

    op.create_table(
        'recurring_journal_lines',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('template_id', sa.Integer(), sa.ForeignKey('recurring_journal_templates.id', ondelete='CASCADE'), nullable=False),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('accounts.id'), nullable=False),
        sa.Column('description', sa.String(500)),
        sa.Column('debit', sa.Numeric(18,2), nullable=False, server_default='0'),
        sa.Column('credit', sa.Numeric(18,2), nullable=False, server_default='0'),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id')),
        sa.Column('cost_center_id', sa.Integer(), sa.ForeignKey('cost_centers.id')),
    )
    op.create_index('ix_recurring_journal_lines_template_id','recurring_journal_lines',['template_id'])

    op.create_table(
        'recurring_journal_runs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('template_id', sa.Integer(), sa.ForeignKey('recurring_journal_templates.id', ondelete='CASCADE'), nullable=False),
        sa.Column('run_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='POSTED'),
        sa.Column('journal_id', sa.Integer(), sa.ForeignKey('journal_entries.id'), nullable=False),
        sa.Column('executed_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('executed_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('template_id','run_date',name='uq_recurring_template_run_date'),
    )
    op.create_index('ix_recurring_journal_runs_template_id','recurring_journal_runs',['template_id'])
    op.create_index('ix_recurring_journal_runs_run_date','recurring_journal_runs',['run_date'])

    conn=op.get_bind()
    permission_rows = [
        ("accruals.read", "عرض المصروفات والإيرادات المستحقة", "View accruals"),
        ("accruals.manage", "إدارة الاستحقاقات", "Manage accruals"),
        ("accruals.post", "ترحيل الاستحقاقات", "Post accruals"),
        ("accruals.reverse", "عكس الاستحقاقات", "Reverse accruals"),
        ("recurring.read", "عرض القيود المتكررة", "View recurring journals"),
        ("recurring.manage", "إدارة القيود المتكررة", "Manage recurring journals"),
        ("recurring.run", "تشغيل القيود المتكررة", "Run recurring journals"),
    ]
    for code, ar, en in permission_rows:
        if not conn.execute(sa.text("select id from permissions where code=:code"), {"code": code}).scalar():
            conn.execute(sa.text("insert into permissions(code,name_ar,name_en) values(:code,:ar,:en)"), {"code": code, "ar": ar, "en": en})
    role_map = {
        "CFO": [x[0] for x in permission_rows],
        "ACCOUNTANT": [x[0] for x in permission_rows],
        "AUDITOR": ["accruals.read", "recurring.read"],
    }
    for role_code, codes in role_map.items():
        role_id = conn.execute(sa.text("select id from roles where code=:code"), {"code": role_code}).scalar()
        if not role_id:
            continue
        for code in codes:
            permission_id = conn.execute(sa.text("select id from permissions where code=:code"), {"code": code}).scalar()
            exists = conn.execute(sa.text("select 1 from role_permissions where role_id=:r and permission_id=:p"), {"r": role_id, "p": permission_id}).scalar()
            if not exists:
                conn.execute(sa.text("insert into role_permissions(role_id,permission_id) values(:r,:p)"), {"r": role_id, "p": permission_id})

    companies=conn.execute(sa.text('select id from companies')).fetchall()
    for (company_id,) in companies:
        current_assets=conn.execute(sa.text("select id from accounts where company_id=:c and code='110000'"),{'c':company_id}).scalar()
        current_liab=conn.execute(sa.text("select id from accounts where company_id=:c and code='210000'"),{'c':company_id}).scalar()
        if current_assets and not conn.execute(sa.text("select id from accounts where company_id=:c and code='118010'"),{'c':company_id}).scalar():
            conn.execute(sa.text("""insert into accounts(company_id,code,name_ar,name_en,account_type,statement_group,parent_id,level,is_postable,is_cash,active)
                values(:c,'118010','إيرادات مستحقة','Accrued Revenue','ASSET','ACCRUED_REVENUE',:p,3,1,0,1)"""),{'c':company_id,'p':current_assets})
        if current_liab and not conn.execute(sa.text("select id from accounts where company_id=:c and code='217010'"),{'c':company_id}).scalar():
            conn.execute(sa.text("""insert into accounts(company_id,code,name_ar,name_en,account_type,statement_group,parent_id,level,is_postable,is_cash,active)
                values(:c,'217010','مصروفات مستحقة','Accrued Expenses','LIABILITY','ACCRUED_EXPENSES',:p,3,1,0,1)"""),{'c':company_id,'p':current_liab})


def downgrade():
    conn=op.get_bind()
    codes=('accruals.read','accruals.manage','accruals.post','accruals.reverse','recurring.read','recurring.manage','recurring.run')
    for code in codes:
        permission_id=conn.execute(sa.text('select id from permissions where code=:code'),{'code':code}).scalar()
        if permission_id:
            conn.execute(sa.text('delete from role_permissions where permission_id=:p'),{'p':permission_id})
            conn.execute(sa.text('delete from permissions where id=:p'),{'p':permission_id})
    op.drop_table('recurring_journal_runs')
    op.drop_table('recurring_journal_lines')
    op.drop_table('recurring_journal_templates')
    op.drop_table('accrual_entries')
