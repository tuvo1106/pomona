from fastapi import FastAPI
from fastapi.testclient import TestClient

from pomona.api import pages


def _build_app(dist_dir) -> TestClient:
    (dist_dir / "index.html").write_text("<html>spa shell</html>")
    (dist_dir / "assets").mkdir()
    (dist_dir / "assets" / "app.js").write_text("console.log('hi')")

    app = FastAPI()
    pages.mount_frontend(app, dist_dir=dist_dir)
    return TestClient(app)


class TestMountFrontend:
    def test_serves_a_real_static_asset(self, tmp_path):
        client = _build_app(tmp_path)
        response = client.get("/assets/app.js")
        assert response.status_code == 200
        assert "console.log" in response.text

    def test_client_side_route_falls_back_to_index_html(self, tmp_path):
        # /clinical has no corresponding file on disk -- only react-router (client-side
        # JS loaded from index.html) knows how to render it. A direct navigation or
        # refresh on that URL must still get the SPA shell, not a 404.
        client = _build_app(tmp_path)
        response = client.get("/clinical")
        assert response.status_code == 200
        assert "spa shell" in response.text

    def test_unknown_deep_path_also_falls_back_to_index_html(self, tmp_path):
        client = _build_app(tmp_path)
        response = client.get("/some/deep/unknown/path")
        assert response.status_code == 200
        assert "spa shell" in response.text

    def test_unknown_api_path_404s_instead_of_returning_the_spa_shell(self, tmp_path):
        # The mount is at "/", so an unmatched /api/... path would otherwise fall through
        # to the SPA fallback and hand the client index.html with a 200 -- turning a
        # renamed or mistyped endpoint into an opaque JSON parse error in the frontend.
        client = _build_app(tmp_path)
        response = client.get("/api/nonexistent-route")
        assert response.status_code == 404
        assert "spa shell" not in response.text

    def test_missing_hashed_asset_404s_instead_of_returning_the_spa_shell(self, tmp_path):
        # The frontend code-splits its pages, so a tab left open across a rebuild requests
        # a chunk whose content hash no longer exists. Answering index.html hands the
        # browser HTML where it expected a JS module: it then fails on the MIME type, and
        # React.lazy caches that rejection, so the page cannot recover without a reload.
        client = _build_app(tmp_path)
        response = client.get("/assets/RoutesPage-OLDHASH.js")
        assert response.status_code == 404
        assert "spa shell" not in response.text

    def test_missing_stylesheet_also_404s(self, tmp_path):
        client = _build_app(tmp_path)
        response = client.get("/assets/RoutesPage-OLDHASH.css")
        assert response.status_code == 404

    def test_client_side_route_containing_a_dot_still_falls_back(self, tmp_path):
        # Only the *last* segment is checked for an extension, so a route whose earlier
        # segments contain dots is still a route.
        client = _build_app(tmp_path)
        response = client.get("/clinical/some.vendor.id/detail")
        assert response.status_code == 200
        assert "spa shell" in response.text

    def test_does_nothing_when_dist_dir_is_missing(self, tmp_path):
        app = FastAPI()
        pages.mount_frontend(app, dist_dir=tmp_path / "does-not-exist")
        client = TestClient(app)
        response = client.get("/")
        assert response.status_code == 404
