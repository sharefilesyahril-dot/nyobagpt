import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url is None:
        pytest.skip("DATABASE_URL must point to a disposable PostgreSQL database")
    if not url.startswith("postgresql"):
        pytest.fail("DATABASE_URL must use PostgreSQL; SQLite is not supported")
    return url


@pytest.fixture(scope="session")
def database_engine(database_url: str) -> Engine:
    engine = create_engine(database_url, pool_pre_ping=True)
    if engine.dialect.name != "postgresql":
        pytest.fail("DATABASE_URL must use PostgreSQL; SQLite is not supported")
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(database_engine: Engine):
    connection = database_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
