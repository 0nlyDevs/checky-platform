from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(HTTPException):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(status_code=status_code, detail=message)
        self.code = code


def _body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def install_error_handlers(app: FastAPI) -> None:
    """Every error leaves the API as {"error": {"code", "message"}}."""

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
