from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config,pool
from app.core.config import get_settings
from app.infrastructure.models import Base
config=context.config
if config.config_file_name: fileConfig(config.config_file_name)
config.set_main_option("sqlalchemy.url",get_settings().database_migration_url)
target_metadata=Base.metadata
def offline():
    context.configure(url=config.get_main_option("sqlalchemy.url"),target_metadata=target_metadata,literal_binds=True,compare_type=True)
    with context.begin_transaction(): context.run_migrations()
def online():
    engine=engine_from_config(config.get_section(config.config_ini_section),prefix="sqlalchemy.",poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection,target_metadata=target_metadata,compare_type=True)
        with context.begin_transaction(): context.run_migrations()
offline() if context.is_offline_mode() else online()
