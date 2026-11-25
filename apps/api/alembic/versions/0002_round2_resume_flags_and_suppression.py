"""resume scan flags and language, and the erasure suppression list

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa
import sendora_core.db


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('cf_resume', schema=None) as batch_op:
        batch_op.add_column(sa.Column('injection_scan', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('language', sa.String(length=10), server_default='en', nullable=False))
    op.create_table('cf_suppression',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('digest', sa.String(length=64), nullable=False),
    sa.Column('kind', sa.String(length=10), nullable=False),
    sa.Column('created_at', sendora_core.db.UTCDateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('cf_suppression', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_cf_suppression_digest'), ['digest'], unique=True)


def downgrade() -> None:
    with op.batch_alter_table('cf_suppression', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_cf_suppression_digest'))
    op.drop_table('cf_suppression')
    with op.batch_alter_table('cf_resume', schema=None) as batch_op:
        batch_op.drop_column('language')
        batch_op.drop_column('injection_scan')
