import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware import Middleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

log = logging.getLogger("checky.errors")


class ApiError(HTTPException):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(status_code=status_code, detail=message)
        self.code = code


def _body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


class CatchAll:
    """An unexpected exception becomes a logged 500 in the error envelope.

    It sits innermost (inside CORS), so the browser can read the answer; Starlette's own
    last-resort handler sits outside CORS and answers plain text a page cannot read. A stream that
    already started cannot change its status: the error is logged and the stream ends.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def tracked(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracked)
        except Exception:
            log.exception("unhandled error on %s %s", scope.get("method"), scope.get("path"))
            if started:
                return
            response = JSONResponse(
                _body("internal_error", "Something went wrong on our side. Try again."),
                status_code=500,
            )
            await response(scope, receive, send)


def install_error_handlers(app: FastAPI) -> None:
    """Every error leaves the API as {"error": {"code", "message"}}."""
    # Innermost, so the CORS middleware still wraps its answer (add_middleware puts outside).
    app.user_middleware.append(Middleware(CatchAll))

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException):
        code = getattr(exc, "code", None) or {
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
        }.get(exc.status_code, "http_error")
        return JSONResponse(
            _body(code, str(exc.detail)), status_code=exc.status_code, headers=exc.headers
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        return JSONResponse(_body("validation_error", str(exc.errors())), status_code=422)
