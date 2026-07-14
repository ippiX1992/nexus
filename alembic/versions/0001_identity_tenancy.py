"""Complete identity and tenancy schema.
Revision ID: 0001
"""
from alembic import op
from app.infrastructure.models import Base
revision="0001"; down_revision=None; branch_labels=None; depends_on=None
RLS_TABLES=("tenant_resources",)
def upgrade():
    bind=op.get_bind(); Base.metadata.create_all(bind=bind)
    op.execute("GRANT USAGE ON SCHEMA public TO nexus_app")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO nexus_app")
    for table in RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_tenant_isolation ON {table} USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid) WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)")
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO nexus_app")
    op.execute("REVOKE UPDATE, DELETE ON audit_logs FROM nexus_app")
def downgrade(): Base.metadata.drop_all(bind=op.get_bind())
