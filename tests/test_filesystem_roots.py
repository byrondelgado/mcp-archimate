"""The filesystem boundary: where the file tools may read and write.

These tests own the security-relevant half of the contract. The rest of
the suite writes to `tmp_path`, which is outside the home directory on
macOS, so `conftest.py` widens the roots for it; everything here sets
the environment explicitly instead.
"""

import os
from pathlib import Path

import pytest

from pyarchimate_mcp_server import filesystem
from pyarchimate_mcp_server.exceptions import (
    InvalidAllowedRootsError,
    PathOutsideAllowedRootsError,
)


@pytest.fixture(autouse=True)
def _no_inherited_roots(monkeypatch):
    """Start every test from an unconfigured server."""
    monkeypatch.delenv(filesystem.ALLOWED_READ_ROOTS_ENV, raising=False)
    monkeypatch.delenv(filesystem.ALLOWED_WRITE_ROOTS_ENV, raising=False)


def _set_roots(monkeypatch, *roots):
    joined = os.pathsep.join(str(root) for root in roots)
    monkeypatch.setenv(filesystem.ALLOWED_READ_ROOTS_ENV, joined)
    monkeypatch.setenv(filesystem.ALLOWED_WRITE_ROOTS_ENV, joined)


def test_unset_roots_default_to_the_home_directory():
    assert filesystem.allowed_read_roots() == [Path.home().resolve()]
    assert filesystem.allowed_write_roots() == [Path.home().resolve()]


def test_unset_roots_allow_a_path_under_home():
    target = Path.home() / "Desktop" / "architecture.archimate"

    assert filesystem.resolve_write_path(str(target)) == target.resolve()


def test_unset_roots_reject_a_path_outside_home():
    with pytest.raises(PathOutsideAllowedRootsError) as exc_info:
        filesystem.resolve_read_path("/etc/passwd")

    assert exc_info.value.code == "PATH_OUTSIDE_ALLOWED_ROOTS"
    assert exc_info.value.details["allowed_roots"] == [str(Path.home().resolve())]
    assert exc_info.value.details["environment_variable"] == (
        filesystem.ALLOWED_READ_ROOTS_ENV
    )


def test_configured_root_allows_paths_inside_it(tmp_path, monkeypatch):
    _set_roots(monkeypatch, tmp_path)
    target = tmp_path / "nested" / "model.archimate"

    assert filesystem.resolve_write_path(str(target)) == target.resolve()


def test_configured_root_rejects_a_sibling_directory(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    denied = tmp_path / "denied"
    denied.mkdir()
    _set_roots(monkeypatch, allowed)

    with pytest.raises(PathOutsideAllowedRootsError):
        filesystem.resolve_write_path(str(denied / "model.archimate"))


def test_read_and_write_roots_are_configured_independently(tmp_path, monkeypatch):
    readable = tmp_path / "readable"
    readable.mkdir()
    writable = tmp_path / "writable"
    writable.mkdir()
    monkeypatch.setenv(filesystem.ALLOWED_READ_ROOTS_ENV, str(readable))
    monkeypatch.setenv(filesystem.ALLOWED_WRITE_ROOTS_ENV, str(writable))

    assert filesystem.resolve_read_path(str(readable / "in.archimate"))
    assert filesystem.resolve_write_path(str(writable / "out.archimate"))
    with pytest.raises(PathOutsideAllowedRootsError):
        filesystem.resolve_read_path(str(writable / "in.archimate"))
    with pytest.raises(PathOutsideAllowedRootsError):
        filesystem.resolve_write_path(str(readable / "out.archimate"))


def test_traversal_out_of_an_allowed_root_is_rejected(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    _set_roots(monkeypatch, allowed)

    with pytest.raises(PathOutsideAllowedRootsError):
        filesystem.resolve_read_path(str(allowed / ".." / "escaped.archimate"))


def test_traversal_that_returns_inside_the_root_is_allowed(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    (allowed / "sub").mkdir(parents=True)
    _set_roots(monkeypatch, allowed)

    resolved = filesystem.resolve_read_path(
        str(allowed / "sub" / ".." / "model.archimate"),
    )

    assert resolved == (allowed / "model.archimate").resolve()


def test_symlink_escaping_an_allowed_root_is_rejected(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.archimate").write_text("<model/>", encoding="utf-8")
    (allowed / "escape").symlink_to(outside, target_is_directory=True)
    _set_roots(monkeypatch, allowed)

    # The path is textually inside the root; only resolution reveals it is not.
    with pytest.raises(PathOutsideAllowedRootsError):
        filesystem.resolve_read_path(str(allowed / "escape" / "secret.archimate"))


def test_symlinked_root_still_matches_its_own_contents(tmp_path, monkeypatch):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    _set_roots(monkeypatch, link)

    assert (
        filesystem.resolve_write_path(str(real / "model.archimate"))
        == (real / "model.archimate").resolve()
    )


def test_tilde_is_expanded_before_the_root_check(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    _set_roots(monkeypatch, tmp_path)

    assert (
        filesystem.resolve_write_path("~/model.archimate")
        == (tmp_path / "model.archimate").resolve()
    )


def test_tilde_in_the_root_configuration_is_expanded(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv(filesystem.ALLOWED_WRITE_ROOTS_ENV, "~/exports")

    assert filesystem.allowed_write_roots() == [(tmp_path / "exports").resolve()]


def test_a_relative_path_resolves_against_the_cwd(tmp_path, monkeypatch):
    workdir = tmp_path / "work"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    _set_roots(monkeypatch, workdir)

    assert (
        filesystem.resolve_write_path("model.archimate")
        == (workdir / "model.archimate").resolve()
    )


def test_a_relative_path_outside_the_roots_is_rejected(tmp_path, monkeypatch):
    workdir = tmp_path / "work"
    workdir.mkdir()
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    monkeypatch.chdir(workdir)
    _set_roots(monkeypatch, allowed)

    with pytest.raises(PathOutsideAllowedRootsError):
        filesystem.resolve_write_path("model.archimate")


def test_multiple_roots_are_accepted(tmp_path, monkeypatch):
    first = tmp_path / "first"
    first.mkdir()
    second = tmp_path / "second"
    second.mkdir()
    _set_roots(monkeypatch, first, second)

    assert filesystem.resolve_write_path(str(first / "a.archimate"))
    assert filesystem.resolve_write_path(str(second / "b.archimate"))
    with pytest.raises(PathOutsideAllowedRootsError):
        filesystem.resolve_write_path(str(tmp_path / "c.archimate"))


def test_an_empty_root_setting_is_a_configuration_error(monkeypatch):
    monkeypatch.setenv(filesystem.ALLOWED_READ_ROOTS_ENV, "   ")

    with pytest.raises(InvalidAllowedRootsError) as exc_info:
        filesystem.allowed_read_roots()

    assert exc_info.value.code == "INVALID_ALLOWED_ROOTS"


def test_a_relative_root_setting_is_a_configuration_error(monkeypatch):
    monkeypatch.setenv(filesystem.ALLOWED_WRITE_ROOTS_ENV, "exports")

    with pytest.raises(InvalidAllowedRootsError) as exc_info:
        filesystem.allowed_write_roots()

    assert "exports" in str(exc_info.value)


def test_roots_are_read_at_call_time_not_import_time(tmp_path, monkeypatch):
    """A client that sets the variables late must still be honoured."""
    first = tmp_path / "first"
    first.mkdir()
    second = tmp_path / "second"
    second.mkdir()

    monkeypatch.setenv(filesystem.ALLOWED_WRITE_ROOTS_ENV, str(first))
    assert filesystem.allowed_write_roots() == [first.resolve()]

    monkeypatch.setenv(filesystem.ALLOWED_WRITE_ROOTS_ENV, str(second))
    assert filesystem.allowed_write_roots() == [second.resolve()]


def test_export_to_file_refuses_a_path_outside_the_allowed_roots(
    tmp_path,
    monkeypatch,
):
    import asyncio

    from pyarchimate_mcp_server.model_manager import ArchimateModelManager
    from pyarchimate_mcp_server.tools import model_tools

    manager = ArchimateModelManager()
    manager.create_new_model("Boundary Test")
    monkeypatch.setattr(model_tools, "_model_manager", lambda: manager)
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    denied = tmp_path / "denied"
    denied.mkdir()
    _set_roots(monkeypatch, allowed)

    target = denied / "model.archimate"
    response = asyncio.run(model_tools.export_model_to_file(str(target)))

    assert response["status"] == "error"
    assert response["error"]["code"] == "PATH_OUTSIDE_ALLOWED_ROOTS"
    # Refused before anything is written, not cleaned up afterwards.
    assert not target.exists()
    assert list(denied.iterdir()) == []


def test_render_svg_refuses_a_path_outside_the_allowed_roots(tmp_path, monkeypatch):
    import asyncio

    from pyarchimate_mcp_server.tools import view_tools
    from tests.test_model_manager import _build_rich_fixture_model

    manager = _build_rich_fixture_model()
    manager.auto_layout_all_views()
    monkeypatch.setattr(view_tools, "_model_manager", lambda: manager)
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    denied = tmp_path / "denied"
    denied.mkdir()
    _set_roots(monkeypatch, allowed)

    target = denied / "overview.svg"
    response = asyncio.run(
        view_tools.render_view_to_svg_file(manager.list_views()[0].uuid, str(target)),
    )

    assert response["status"] == "error"
    assert response["error"]["code"] == "PATH_OUTSIDE_ALLOWED_ROOTS"
    assert not target.exists()
    # The parent directory is never created for a refused path either.
    assert list(denied.iterdir()) == []
