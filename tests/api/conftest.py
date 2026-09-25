import json

import pytest
from fastapi.testclient import TestClient

from pomona import db as db_module
from pomona.api.app import app
from pomona.api.dependencies import get_db
from pomona.ingest.clinical_loader import load_clinical_records
from pomona.ingest.ecg_loader import load_ecg_recordings
from pomona.ingest.gpx_loader import load_workout_routes
from pomona.ingest.loader import load_export_xml
from tests.conftest import (
    CLINICAL_FIXTURES_DIR,
    ECG_FIXTURES_DIR,
    ROUTES_FIXTURES_DIR,
    SAMPLE_EXPORT_XML,
    checkpoint_and_close,
)


@pytest.fixture
def seeded_db_path(tmp_path):
    db_path = tmp_path / "health.db"
    conn = db_module.connect(db_path, isolation_level=None)
    db_module.init_schema(conn)
    load_export_xml(conn, SAMPLE_EXPORT_XML, show_progress=False)
    load_clinical_records(conn, CLINICAL_FIXTURES_DIR)
    load_workout_routes(conn, ROUTES_FIXTURES_DIR)
    load_ecg_recordings(conn, ECG_FIXTURES_DIR)
    db_module.create_indexes(conn)
    db_module.create_views(conn)
    checkpoint_and_close(conn)
    return db_path


@pytest.fixture
def client(seeded_db_path):
    def override_get_db():
        conn = db_module.connect(seeded_db_path, readonly=True)
        try:
            yield conn
        finally:
            conn.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
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
        conn = db_module.connect(db_path, isolation_level=None)
        db_module.init_schema(conn)
        load_clinical_records(conn, records_dir)
        checkpoint_and_close(conn)

        def override_get_db():
            conn = db_module.connect(db_path, readonly=True)
            try:
                yield conn
            finally:
                conn.close()

        app.dependency_overrides[get_db] = override_get_db
        return TestClient(app)

    try:
        yield build
    finally:
        app.dependency_overrides.clear()
