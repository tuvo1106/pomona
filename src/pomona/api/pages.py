from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.types import Scope

# repo_root/frontend/dist — see the Frontend section of docs/DESIGN.md.
_FRONTEND_DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"


class _SPAStaticFiles(StaticFiles):
    """Falls back to index.html for any path with no matching static file.

    The app uses client-side routing (react-router), so a direct navigation or
    refresh on e.g. /clinical has no corresponding file on disk — only client-side
    JS knows how to render that route. Without this fallback such requests 404
    (StaticFiles.get_response raises HTTPException(404) rather than returning one).

    API paths are deliberately excluded: this is mounted at "/", so an /api/... path
    the router didn't match would otherwise fall through to here and get index.html
    with a 200, turning a mistyped or renamed endpoint into an opaque JSON parse
    error in the client instead of the 404 it actually is.

    Built assets are excluded for the same reason. Since the frontend code-splits its
    pages, a tab left open across a rebuild asks for a chunk whose hash no longer exists;
    answering that with index.html hands the browser HTML where it expected a JS module,
    and it fails on the MIME type rather than on the missing file. A 404 is both true and
    the error the client can act on.
    """

    async def get_response(self, path: str, scope: Scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or not self._is_spa_route(path):
                raise
            return await super().get_response("index.html", scope)

    @staticmethod
    def _is_spa_route(path: str) -> bool:
        """Whether a missing path should render the app rather than 404.

        A client-side route is a bare path -- /clinical, /routes/42. Anything the browser
        fetches as a *file* has an extension, and a missing file is a missing file.
        """
        if path.startswith("api/"):
            return False
        return "." not in path.rsplit("/", 1)[-1]


def mount_frontend(app: FastAPI, *, dist_dir: Path = _FRONTEND_DIST) -> None:
    """Serves the built React app if it's been built (`npm run build` in frontend/).

    During active development, run `npm run dev` instead and hit the Vite dev
    server directly — this mount is only for the single-process "just run it" mode.
    `dist_dir` is overridable for tests; production callers should omit it.
    """
    if dist_dir.is_dir():
        app.mount("/", _SPAStaticFiles(directory=dist_dir, html=True), name="frontend")
