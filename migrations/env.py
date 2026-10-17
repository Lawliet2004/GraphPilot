from alembic import context
from sqlalchemy import create_engine

from api import models  # noqa: F401
from api.config import settings
from api.db import Base

config = context.config
engine = create_engine(settings().database_url)
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()
