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
    # Buat tabel sekali di level engine agar permanen selama test berjalan
    RollbackProbe.__table__.drop(database_engine, checkfirst=True)
    RollbackProbe.__table__.create(database_engine)
    
    try:
        # Tambahkan data di dalam session, lalu rollback session-nya
        db_session.add(RollbackProbe(id=1))
        db_session.flush()
        db_session.rollback()

        # Pastikan data ter-rollback (bernilai None), sementara tabelnya tetap ada
        assert db_session.get(RollbackProbe, 1) is None
    finally:
        RollbackProbe.__table__.drop(database_engine, checkfirst=True)
