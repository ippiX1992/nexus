"""Run reproducible PostgreSQL integration tests."""
import os
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]; PORT=os.getenv("NEXUS_TEST_PG_PORT","55432")
env={**os.environ,"TEST_DATABASE_URL":os.getenv("TEST_DATABASE_URL",f"postgresql+asyncpg://nexus_app:nexus_app@127.0.0.1:{PORT}/nexus_test"),"TEST_DATABASE_MIGRATION_URL":os.getenv("TEST_DATABASE_MIGRATION_URL",f"postgresql+psycopg://nexus_migrator:nexus_migrator@127.0.0.1:{PORT}/nexus_test")}
subprocess.run([sys.executable,str(ROOT/"scripts/reset_test_database.py")],cwd=ROOT,env=env,check=True)
subprocess.run([sys.executable,"-m","pytest","-m","integration","-q"],cwd=ROOT,env=env,check=True)
