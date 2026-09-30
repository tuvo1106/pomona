import json

import pytest
from fastapi.testclient import TestClient

from pomona import db as db_module
from pomona.api.app import app
from pomona.api.dependencies import get_db
from tests.conftest import (
    CLINICAL_FIXTURES_DIR,
    ECG_FIXTURES_DIR,
    ROUTES_FIXTURES_DIR,
    SAMPLE_EXPORT_XML,
    ingest_into,
    writing,
)


def _client_for(db_path) -> TestClient:
    """A client whose requests read `db_path`, read-only, the way the app reads its database."""

    def override_get_db():
        conn = db_module.connect(db_path, readonly=True)
        try:
            yield conn
        finally:
            conn.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


@pytest.fixture
def seeded_db_path(tmp_path):
    db_path = tmp_path / "health.db"
    with writing(db_path) as conn:
        ingest_into(
            conn,
            export_xml=SAMPLE_EXPORT_XML,
            clinical_dir=CLINICAL_FIXTURES_DIR,
            routes_dir=ROUTES_FIXTURES_DIR,
            ecg_dir=ECG_FIXTURES_DIR,
        )
    return db_path


@pytest.fixture
def client(seeded_db_path):
    try:
        yield _client_for(seeded_db_path)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def clinical_client(tmp_path):
    """Builds a client over a database holding only the FHIR resources passed to it.

    For resource shapes that only one test cares about. They don't belong in the shared
    `tests/fixtures/clinical-records/`: tests there assert exact record counts and treat the
    single Observation as `body[0]`, so adding one there would break them.
    """
    builds = 0

    def build(*resources: dict) -> TestClient:
        # Each call gets its own directory and database, so a second one in the same test
        # can't be served leftover files from the first.
        nonlocal builds
        builds += 1
        records_dir = tmp_path / f"clinical-records-{builds}"
        records_dir.mkdir()
        for index, resource in enumerate(resources):
            path = records_dir / f"{resource.get('resourceType', 'Unknown')}-{index}.json"
            path.write_text(json.dumps(resource))

        db_path = tmp_path / f"clinical-{builds}.db"
        with writing(db_path) as conn:
            ingest_into(conn, clinical_dir=records_dir)
        return _client_for(db_path)

    try:
        yield build
    finally:
        app.dependency_overrides.clear()
