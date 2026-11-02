from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from app.core.errors import ApiError, install_error_handlers


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware, allow_origins=["http://web.test"], allow_methods=["*"], allow_headers=["*"]
    )
    install_error_handlers(app)

    @app.get("/boom")
    async def boom():
        raise RuntimeError("database exploded with secret=hunter2")

    @app.get("/known")
    async def known():
        raise ApiError(409, "conflict", "Already there")

    @app.get("/stream")
    async def stream():
        async def gen():
            yield b"data: one\n\n"
            raise RuntimeError("mid-stream")

        return StreamingResponse(gen(), media_type="text/event-stream")

    return app


def test_an_unexpected_error_leaves_as_the_envelope_with_cors(caplog):
    c = TestClient(_app(), raise_server_exceptions=False)
    r = c.get("/boom", headers={"Origin": "http://web.test"})
    assert r.status_code == 500
    assert r.json() == {
        "error": {
            "code": "internal_error",
            "message": "Something went wrong on our side. Try again.",
        }
    }
    # The page can read it, and nothing of the exception leaks.
    assert r.headers["access-control-allow-origin"] == "http://web.test"
    assert "hunter2" not in r.text
    assert any("unhandled error on GET /boom" in m for m in caplog.messages)


def test_known_errors_keep_their_code():
    c = TestClient(_app(), raise_server_exceptions=False)
    r = c.get("/known")
    assert (r.status_code, r.json()["error"]["code"]) == (409, "conflict")


def test_a_stream_that_fails_midway_ends_without_a_second_answer():
    c = TestClient(_app(), raise_server_exceptions=False)
    r = c.get("/stream")
    assert r.status_code == 200
    assert r.text.startswith("data: one")
