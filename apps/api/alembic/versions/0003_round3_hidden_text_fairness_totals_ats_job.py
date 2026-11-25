"""resume file notes and the kept original, fairness totals that survive erasure, keyed suppression hashes, the ATS job of a role

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('cf_resume', schema=None) as batch_op:
        batch_op.add_column(sa.Column('notes', sa.JSON(), server_default='[]', nullable=False))
    with op.batch_alter_table('cf_application', schema=None) as batch_op:
        batch_op.add_column(sa.Column('fairness_folded', sa.Boolean(), server_default='0', nullable=False))
    with op.batch_alter_table('cf_role', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ats_job_id', sa.String(length=120), server_default='', nullable=False))
    with op.batch_alter_table('cf_suppression', schema=None) as batch_op:
        batch_op.add_column(sa.Column('scheme', sa.String(length=8), server_default='salt', nullable=False))
        batch_op.add_column(sa.Column('group_id', sa.String(length=32), server_default='', nullable=False))
    op.create_table('cf_resume_file',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('application_id', sa.Integer(), nullable=False),
    sa.Column('media_type', sa.String(length=40), nullable=False),
    sa.Column('content', sa.LargeBinary(), nullable=False),
    sa.ForeignKeyConstraint(['application_id'], ['cf_application.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('application_id')
    )
    op.create_table('cf_fairness_aggregate',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('role_id', sa.Integer(), nullable=False),
    sa.Column('step', sa.String(length=20), nullable=False),
    sa.Column('group_label', sa.String(length=60), nullable=False),
    sa.Column('month', sa.String(length=7), nullable=False),
    sa.Column('entered', sa.Integer(), nullable=False),
    sa.Column('passed', sa.Integer(), nullable=False),
    sa.Column('people', sa.Integer(), server_default='0', nullable=False),
    sa.ForeignKeyConstraint(['role_id'], ['cf_role.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('role_id', 'step', 'group_label', 'month', name='uq_cf_fairness_aggregate')
    )
    with op.batch_alter_table('cf_fairness_aggregate', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_cf_fairness_aggregate_role_id'), ['role_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('cf_fairness_aggregate', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_cf_fairness_aggregate_role_id'))
    op.drop_table('cf_fairness_aggregate')
    op.drop_table('cf_resume_file')
    with op.batch_alter_table('cf_suppression', schema=None) as batch_op:
        batch_op.drop_column('group_id')
        batch_op.drop_column('scheme')
    with op.batch_alter_table('cf_role', schema=None) as batch_op:
        batch_op.drop_column('ats_job_id')
    with op.batch_alter_table('cf_application', schema=None) as batch_op:
        batch_op.drop_column('fairness_folded')
    with op.batch_alter_table('cf_resume', schema=None) as batch_op:
        batch_op.drop_column('notes')
