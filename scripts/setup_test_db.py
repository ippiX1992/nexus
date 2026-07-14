"""Create an isolated PostgreSQL cluster for Module 1 integration tests."""
import os
import shutil
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/".pgtest"; PORT=os.getenv("NEXUS_TEST_PG_PORT","55432")
def binary(name):
    configured=os.getenv("POSTGRES_BIN")
    choices=[Path(configured)] if configured else [Path(r"C:\Program Files\PostgreSQL\17\bin"),Path(r"C:\Program Files\PostgreSQL\16\bin")]
    for base in choices:
        path=base/f"{name}.exe" if os.name=="nt" else base/name
        if path.exists(): return str(path)
    found=shutil.which(name)
    if found: return found
    raise SystemExit(f"PostgreSQL binary '{name}' not found. Set POSTGRES_BIN.")
def run(args,env=None):
    try: subprocess.run(args,cwd=ROOT,check=True,env=env)
    except subprocess.CalledProcessError as exc: raise SystemExit(f"PostgreSQL setup failed at {args[0]} (exit {exc.returncode}); credentials were not printed.") from None
if not (DATA/"PG_VERSION").exists(): run([binary("initdb"),"-D",str(DATA),"-U","postgres","--auth=trust","--encoding=UTF8","--no-locale"])
running=False
try:
    import psycopg
    with psycopg.connect(f"host=127.0.0.1 port={PORT} dbname=postgres user=postgres connect_timeout=2"):
        running=True
except Exception:
    pass
if not running:
    run([binary("pg_ctl"),"-D",str(DATA),"-l",str(DATA/"postgres.log"),"-o",f"-p {PORT} -h 127.0.0.1","start"])
run([binary("psql"),"-h","127.0.0.1","-p",PORT,"-U","postgres","-d","postgres","-f",str(ROOT/"scripts/create_database_roles.sql")])
print(f"PostgreSQL test cluster ready on 127.0.0.1:{PORT}; use environment variables from .env.test.example")
