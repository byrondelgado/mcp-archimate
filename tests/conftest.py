"""Shared pytest configuration.

The file tools refuse paths outside the configured roots, which default
to the launching user's home directory. Pytest's `tmp_path` lives under
the system temp directory — outside home on macOS — so the suite would
otherwise fail everywhere a test writes a model or an SVG.

Widening the roots to the temp directory rather than disabling the check
is deliberate: every file test then exercises the real boundary code on
its way through, instead of a bypass that only the tests take.
`tests/test_filesystem_roots.py` overrides these per test, so the
boundary's own behaviour is still tested against explicit settings.
"""

import os
import tempfile

import pytest

from pyarchimate_mcp_server import filesystem


@pytest.fixture(autouse=True)
def _allow_temp_directory_paths(monkeypatch):
    roots = os.pathsep.join(
        [str(tempfile.gettempdir()), os.path.expanduser("~")],  # noqa: PTH111
    )
    monkeypatch.setenv(filesystem.ALLOWED_READ_ROOTS_ENV, roots)
    monkeypatch.setenv(filesystem.ALLOWED_WRITE_ROOTS_ENV, roots)
