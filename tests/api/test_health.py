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


def test_database_transaction_rollback(database_engine, db_session) -> None:
    # Buat tabel via engine, di luar session utama.
    Base.metadata.create_all(bind=database_engine, tables=[RollbackProbe.__table__])

    try:
        # Tambahkan data dan lakukan flush
        db_session.add(RollbackProbe(id=100))
        db_session.flush()

        # Rollback session
        db_session.rollback()

        # Verifikasi bahwa baris bernilai None setelah rollback
        assert db_session.get(RollbackProbe, 100) is None
    finally:
        # Bersihkan tabel menggunakan engine terpisah
        Base.metadata.drop_all(bind=database_engine, tables=[RollbackProbe.__table__])
