"""ASGI entrypoint.

`uvicorn app.main:app` (or `make run`) imports this module and serves the
`app` object it defines. Building the FastAPI instance is `create_app()`'s
job (`app/application.py`) — this module stays a single line of actual
logic so nothing about app construction is duplicated between here and
tests, which call `create_app()` directly to get a fresh instance per test.
"""

from app.application import create_app

app = create_app()
