from sqlalchemy.engine import make_url

from app import database
from app.config import Settings


def test_settings_do_not_include_database_credentials_in_repr() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://user:private-password@localhost/example",
    )
    assert "private-password" not in repr(settings)
    assert "database_url" not in repr(settings)


def test_engine_hides_sql_parameters_without_changing_connection(monkeypatch) -> None:
    url = "postgresql+psycopg://user:private-password@localhost/example"
    monkeypatch.setattr(
        database, "get_settings", lambda: Settings(_env_file=None, database_url=url)
    )
    database.get_engine.cache_clear()
    engine = database.get_engine()
    try:
        assert engine.hide_parameters is True
        assert engine.url == make_url(url)
    finally:
        engine.dispose()
        database.get_engine.cache_clear()
