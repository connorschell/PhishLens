"""The package directory is named 03_Backend, which is not a valid Python
identifier, so it cannot be imported with a normal import statement. This shim
loads the app package by path and re-exports what the tests need."""

import importlib.util
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path,
                                                  submodule_search_locations=[str(path.parent)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Register "app" as a real package rooted at 03_Backend/app so the relative
# imports inside it resolve.
_pkg_spec = importlib.util.spec_from_file_location(
    "app", BACKEND / "app" / "__init__.py",
    submodule_search_locations=[str(BACKEND / "app")])
_pkg = importlib.util.module_from_spec(_pkg_spec)
sys.modules["app"] = _pkg
_pkg_spec.loader.exec_module(_pkg)

import app.main as _main            # noqa: E402
import app.services.scoring as scoring  # noqa: E402,F401

app = _main.app
