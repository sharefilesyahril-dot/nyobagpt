from fastapi.testclient import TestClient
from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column

from autopilot.app import create_app
from autopilot.db import Base


def test_health_returns_ok() -> None:
    response = TestClient(create_app()).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


class RollbackProbe(Base):
    __tablename__ = "test_rollback_probe"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)


def test_database_transaction_rollback(db_session, database_engine) -> None:
    # Pastikan tabel bersih dari uji sebelumnya
    RollbackProbe.__table__.drop(database_engine, checkfirst=True)
    RollbackProbe.__table__.create(database_engine)

    try:
        # Gunakan savepoint eksplisit untuk menguji rollback session
        with db_session.begin_nested():
            db_session.add(RollbackProbe(id=99))
            db_session.flush()
            # Verifikasi data ada di dalam nested transaction
            assert db_session.get(RollbackProbe, 99) is not None

        # Setelah keluar dari context manager begin_nested
        # (atau rollback manual), data harusnya hilang
        db_session.rollback()
        assert db_session.get(RollbackProbe, 99) is None
    finally:
        RollbackProbe.__table__.drop(database_engine, checkfirst=True)
