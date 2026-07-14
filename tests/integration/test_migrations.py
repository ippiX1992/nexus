import os
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest

pytestmark=pytest.mark.integration
ROOT=Path(__file__).resolve().parents[2]; URL=os.environ["DATABASE_MIGRATION_URL"]
def alembic(*args): subprocess.run([sys.executable,"-m","alembic",*args],cwd=ROOT,check=True,env=os.environ)
def test_downgrade_upgrade_and_schema_contract():
    alembic("downgrade","base"); alembic("upgrade","head")
    with psycopg.connect(URL.replace("postgresql+psycopg://","postgresql://")) as conn:
        tables={r[0] for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")}; assert {"users","tenants","memberships","roles","permissions","refresh_tokens","tenant_resources"}<=tables
        policy=conn.execute("SELECT polname FROM pg_policy WHERE polrelid='tenant_resources'::regclass").fetchone(); assert policy
        role=conn.execute("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname='nexus_app'").fetchone(); assert role==(False,False)
        privileges=conn.execute("SELECT has_table_privilege('nexus_app','audit_logs','INSERT'),has_table_privilege('nexus_app','audit_logs','UPDATE'),has_table_privilege('nexus_app','audit_logs','DELETE')").fetchone(); assert privileges==(True,False,False)
        constraints={r[0] for r in conn.execute("SELECT contype FROM pg_constraint WHERE conrelid='memberships'::regclass")}; assert {"p","f","u"}<=constraints
        indexes={r[0] for r in conn.execute("SELECT indexname FROM pg_indexes WHERE tablename='refresh_tokens'")}; assert "ix_refresh_family" in indexes
        column=conn.execute("SELECT data_type FROM information_schema.columns WHERE table_name='users' AND column_name='id'").fetchone(); assert column[0]=="uuid"
        default=conn.execute("SELECT column_default FROM information_schema.columns WHERE table_name='users' AND column_name='created_at'").fetchone(); assert "now()" in default[0]
        assert {"platform_stores","platform_sites","platform_channels","platform_environments","platform_markets","platform_outbox_events","platform_inbox_events","platform_idempotency_records","platform_operations","platform_jobs"}<=tables
        policies=conn.execute("SELECT count(*) FROM pg_policy WHERE polrelid='platform_stores'::regclass").fetchone(); assert policies[0]==4
        forced=conn.execute("SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid='platform_stores'::regclass").fetchone(); assert forced==(True,True)
        platform_permissions=conn.execute("SELECT count(*) FROM permissions WHERE code LIKE 'store.%' OR code LIKE 'site.%'").fetchone(); assert platform_permissions[0]==8
