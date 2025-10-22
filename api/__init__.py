"""Compatibility package exposing backend.api for legacy imports."""

from importlib import import_module
import sys
from typing import TYPE_CHECKING

_BACKEND_NAMESPACE = "backend.api"
_BACKEND_MODULE = import_module(_BACKEND_NAMESPACE)


def __getattr__(name: str):
    """Allow `api.foo` attribute access to fall through to backend.api."""
    return getattr(_BACKEND_MODULE, name)


def __dir__() -> list[str]:
    return sorted(set(globals().keys()) | set(dir(_BACKEND_MODULE)))


_SUBMODULES = (
    "main",
    "browser",
    "cache",
    "extract",
    "heuristics",
    "models",
    "scorer",
    "utils",
)

for _name in _SUBMODULES:
    sys.modules[f"{__name__}.{_name}"] = import_module(f"{_BACKEND_NAMESPACE}.{_name}")

if TYPE_CHECKING:
    from backend.api.main import app  # noqa: F401

__all__ = list(_SUBMODULES)
