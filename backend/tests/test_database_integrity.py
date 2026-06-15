from app.core.database import engine


def test_application_sqlite_connections_enforce_foreign_keys():
    engine.dispose()
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
