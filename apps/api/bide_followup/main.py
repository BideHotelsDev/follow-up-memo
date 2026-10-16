import logging
import secrets

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.sessions import SessionMiddleware

from bide_followup import auth
from bide_followup.config import settings
from bide_followup.db import SessionDep
from bide_followup.errors import DomainError, domain_error_handler
from bide_followup.routers import admin, connections
from bide_followup.schemas.api import HealthOut

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="Bide Meeting Follow-up", version="0.1.0")
app.add_exception_handler(DomainError, domain_error_handler)

if not settings.session_secret:
    log.warning("SESSION_SECRET not set; using a random key, so sessions end when the process restarts")
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret or secrets.token_urlsafe(32),
    session_cookie="bide_followup_session",
    max_age=settings.session_days * 24 * 3600,
    same_site="lax",
    https_only=settings.app_base_url.startswith("https://"),
)

health_router = APIRouter(prefix="/api")


@health_router.get("/health")
def health(session: SessionDep) -> HealthOut:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="database unavailable")
    return HealthOut(status="ok", database="ok")


app.include_router(health_router)
app.include_router(auth.router)
app.include_router(connections.router)
app.include_router(admin.router)

# In production the API serves the built web app on the same origin (no CORS, one cookie).
if settings.web_dist_dir and settings.web_dist_dir.is_dir():
    dist = settings.web_dist_dir.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(status_code=404)
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(dist):
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")
