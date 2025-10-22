"""Expose FastAPI app for `uvicorn api.main:app`."""

from backend.api.main import app

__all__ = ["app"]
