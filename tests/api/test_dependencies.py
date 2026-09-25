import pytest
from fastapi import HTTPException

from pomona.api.dependencies import get_db
from pomona.config import settings


class TestGetDb:
    def test_missing_database_raises_503_naming_the_ingest_command(self, tmp_path, monkeypatch):
        # Running `serve` before ever running `ingest` is an easy first-run mistake. A
        # read-only connect to a nonexistent file raises OperationalError, which would
        # surface as an unhelpful 500 on every route.
        monkeypatch.setattr(settings, "db_path", tmp_path / "never-ingested.db")
        with pytest.raises(HTTPException) as excinfo:
            next(get_db())
        assert excinfo.value.status_code == 503
        assert "pomona ingest" in excinfo.value.detail

    def test_existing_database_yields_a_usable_connection(self, seeded_db_path, monkeypatch):
        monkeypatch.setattr(settings, "db_path", seeded_db_path)
        gen = get_db()
        conn = next(gen)
        try:
            assert conn.execute("SELECT COUNT(*) FROM records").fetchone()[0] > 0
        finally:
            gen.close()


def test_missing_database_detail_leads_with_the_path(tmp_path, monkeypatch):
    """The frontend splits this detail on ". Run " to show the path on its own (see
    components/NoDatabase.tsx), because the command after it is already rendered there.
    Changing the wording is fine; leading with "No health database at {path}." is not.
    """
    from fastapi import HTTPException

    from pomona.api import dependencies
    from pomona.config import settings

    monkeypatch.setattr(settings, "db_path", tmp_path / "absent.db")
    try:
        next(dependencies.get_db())
    except HTTPException as exc:
        detail = str(exc.detail)
    else:  # pragma: no cover - the fixture guarantees a missing file
        raise AssertionError("expected a 503 for a missing database")

    assert detail.startswith("No health database at ")
    assert detail.split(". Run ")[0].endswith("absent.db")
