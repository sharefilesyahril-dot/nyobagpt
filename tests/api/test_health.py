
from fastapi.testclient import TestClient
from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, Session, mapped_column

from autopilot.app import create_app
from autopilot.db import Base


def test_health_returns_ok() -> None:
    response = TestClient(create_app()).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


class RollbackProbe(Base):
    __tablename__ = "test_rollback_probe"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)


def test_database_transaction_rollback(database_engine) -> None:
    # Siapkan tabel sebelum transaksi pengujian.
    RollbackProbe.__table__.drop(database_engine, checkfirst=True)
    RollbackProbe.__table__.create(database_engine)

    try:
        # INSERT dilakukan di dalam transaksi yang akan dibatalkan.
        with database_engine.connect() as connection:
            transaction = connection.begin()
            session = Session(bind=connection)

            try:
                session.add(RollbackProbe(id=100))
                session.flush()
            finally:
                session.close()
                if transaction.is_active:
                    transaction.rollback()

        # Gunakan koneksi baru untuk memastikan INSERT tidak tersimpan.
        with Session(database_engine) as verification_session:
            assert verification_session.get(RollbackProbe, 100) is None

    finally:
        # Hapus tabel setelah seluruh koneksi pengujian ditutup.
        RollbackProbe.__table__.drop(database_engine, checkfirst=True)
