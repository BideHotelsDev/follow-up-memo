"""Domain errors with stable codes, returned as problem details (RFC 9457) so the web app can match on `code`."""

from fastapi import Request
from fastapi.responses import JSONResponse


class DomainError(Exception):
    def __init__(self, code: str, detail: str, status: int = 409):
        super().__init__(detail)
        self.code, self.detail, self.status = code, detail, status


def not_found(what: str) -> DomainError:
    return DomainError("not_found", f"{what} not found", 404)


def forbidden(detail: str = "You can't do that") -> DomainError:
    return DomainError("forbidden", detail, 403)


async def domain_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    return JSONResponse(
        {
            "type": f"about:blank#{exc.code}",
            "title": exc.code.replace("_", " "),
            "status": exc.status,
            "detail": exc.detail,
            "code": exc.code,
        },
        status_code=exc.status,
        media_type="application/problem+json",
    )
