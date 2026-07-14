"""Reset the test database and apply Alembic migrations from zero."""
import os
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]; PORT=os.getenv("NEXUS_TEST_PG_PORT","55432")
env={**os.environ,"DATABASE_MIGRATION_URL":os.getenv("TEST_DATABASE_MIGRATION_URL",f"postgresql+psycopg://nexus_migrator:nexus_migrator@127.0.0.1:{PORT}/nexus_test")}
def run(*args): subprocess.run(args,cwd=ROOT,env=env,check=True)
run(sys.executable,"-m","alembic","downgrade","base"); run(sys.executable,"-m","alembic","upgrade","head")
print("Test database reset and migrated to head.")
