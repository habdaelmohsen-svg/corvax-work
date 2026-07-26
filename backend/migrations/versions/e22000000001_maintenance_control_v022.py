"""maintenance planning spare parts calibration v022

Revision ID: e22000000001
Revises: e20000000001
"""
from alembic import op
import sqlalchemy as sa
revision='e22000000001'; down_revision='e20000000001'; branch_labels=None; depends_on=None

def upgrade():
    op.create_table('maintenance_plans',
        sa.Column('id',sa.Integer(),primary_key=True),sa.Column('company_id',sa.Integer(),sa.ForeignKey('companies.id',ondelete='CASCADE'),nullable=False),sa.Column('asset_id',sa.Integer(),sa.ForeignKey('maintenance_assets.id',ondelete='CASCADE'),nullable=False),sa.Column('code',sa.String(50),nullable=False),sa.Column('description',sa.String(500),nullable=False),sa.Column('interval_days',sa.Integer()),sa.Column('meter_interval',sa.Numeric(18,2)),sa.Column('next_due_date',sa.Date()),sa.Column('next_due_meter',sa.Numeric(18,2)),sa.Column('priority',sa.String(20),nullable=False,server_default='MEDIUM'),sa.Column('active',sa.Boolean(),nullable=False,server_default=sa.true()),sa.Column('last_generated_at',sa.DateTime()),sa.Column('created_by',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False),sa.UniqueConstraint('company_id','code',name='uq_maintenance_plan_company_code'))
    op.create_index('ix_maintenance_plans_company_id','maintenance_plans',['company_id']); op.create_index('ix_maintenance_plans_asset_id','maintenance_plans',['asset_id'])
    op.create_table('maintenance_spare_parts',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('company_id',sa.Integer(),sa.ForeignKey('companies.id',ondelete='CASCADE'),nullable=False),sa.Column('code',sa.String(50),nullable=False),sa.Column('name_ar',sa.String(200),nullable=False),sa.Column('name_en',sa.String(200),nullable=False),sa.Column('unit',sa.String(30),nullable=False),sa.Column('quantity_on_hand',sa.Numeric(18,4),nullable=False),sa.Column('reorder_level',sa.Numeric(18,4),nullable=False),sa.Column('average_cost',sa.Numeric(18,4),nullable=False),sa.Column('active',sa.Boolean(),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False),sa.UniqueConstraint('company_id','code',name='uq_maintenance_spare_company_code'))
    op.create_index('ix_maintenance_spare_parts_company_id','maintenance_spare_parts',['company_id'])
    op.create_table('maintenance_work_order_parts',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('work_order_id',sa.Integer(),sa.ForeignKey('maintenance_work_orders.id',ondelete='CASCADE'),nullable=False),sa.Column('spare_part_id',sa.Integer(),sa.ForeignKey('maintenance_spare_parts.id'),nullable=False),sa.Column('quantity',sa.Numeric(18,4),nullable=False),sa.Column('unit_cost',sa.Numeric(18,4),nullable=False),sa.Column('total_cost',sa.Numeric(18,2),nullable=False),sa.Column('issued_by',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),sa.Column('issued_at',sa.DateTime(),nullable=False))
    op.create_index('ix_maintenance_work_order_parts_work_order_id','maintenance_work_order_parts',['work_order_id'])
    op.create_table('calibration_records',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('company_id',sa.Integer(),sa.ForeignKey('companies.id',ondelete='CASCADE'),nullable=False),sa.Column('asset_id',sa.Integer(),sa.ForeignKey('maintenance_assets.id',ondelete='CASCADE'),nullable=False),sa.Column('instrument_code',sa.String(80),nullable=False),sa.Column('calibration_date',sa.Date(),nullable=False),sa.Column('next_due_date',sa.Date(),nullable=False),sa.Column('result',sa.String(20),nullable=False),sa.Column('certificate_reference',sa.String(120)),sa.Column('notes',sa.String(500)),sa.Column('performed_by',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False))
    op.create_index('ix_calibration_records_company_id','calibration_records',['company_id']); op.create_index('ix_calibration_records_asset_id','calibration_records',['asset_id']); op.create_index('ix_calibration_records_next_due_date','calibration_records',['next_due_date'])

def downgrade():
    op.drop_table('calibration_records'); op.drop_table('maintenance_work_order_parts'); op.drop_table('maintenance_spare_parts'); op.drop_table('maintenance_plans')
