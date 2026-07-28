"""The filesystem boundary for the three file-touching tools.

`load_model_from_file`, `export_model_to_file` and
`render_view_to_svg_file` take paths from an agent, and the agent's
input can come from a model file the user did not author. This module
is the single place that decides whether a path is reachable.

Leaf module by design: stdlib plus `exceptions` only. It never imports
`model_manager`, so both the manager and the tools layer can call it.
"""

import os
from pathlib import Path

from pyarchimate_mcp_server.exceptions import (
    InvalidAllowedRootsError,
    PathOutsideAllowedRootsError,
)

ALLOWED_READ_ROOTS_ENV = "MCP_ARCHIMATE_ALLOWED_READ_ROOTS"
ALLOWED_WRITE_ROOTS_ENV = "MCP_ARCHIMATE_ALLOWED_WRITE_ROOTS"


def _parse_roots(env_var: str) -> list[Path]:
    """Resolve one environment variable into a list of allowed roots.

    Read at call time, never cached: a client may set the variables
    after import, and tests must be able to change them per case.

    Unset falls back to the launching user's home directory. That is
    the documented default — see `SECURITY.md`. Deny-by-default would
    break the quickstarts in the README, which write to `~/Desktop`,
    and unrestricted would leave the protection reachable only by
    someone who already knew the variables existed.
    """
    raw = os.environ.get(env_var)
    if raw is None:
        return [Path.home().resolve()]

    entries = [entry.strip() for entry in raw.split(os.pathsep)]
    candidates = [entry for entry in entries if entry]
    if not candidates:
        msg = (
            f"{env_var} is set but lists no paths. Unset it to fall back to "
            f"the home directory, or list one or more absolute paths "
            f"separated by {os.pathsep!r}."
        )
        raise InvalidAllowedRootsError(msg, {"environment_variable": env_var})

    roots = []
    for candidate in candidates:
        expanded = Path(candidate).expanduser()
        if not expanded.is_absolute():
            # Resolving a relative root against the CWD would make the
            # boundary depend on where the client happened to launch
            # the server, which is not something a user can reason about.
            msg = (
                f"{env_var} entry {candidate!r} is not an absolute path. "
                f"Allowed roots must be absolute."
            )
            raise InvalidAllowedRootsError(
                msg,
                {"environment_variable": env_var, "entry": candidate},
            )
        roots.append(expanded.resolve())
    return roots


def allowed_read_roots() -> list[Path]:
    """Return the roots the file tools may read from."""
    return _parse_roots(ALLOWED_READ_ROOTS_ENV)


def allowed_write_roots() -> list[Path]:
    """Return the roots the file tools may write to."""
    return _parse_roots(ALLOWED_WRITE_ROOTS_ENV)


def _resolve_within(path: str, roots: list[Path], env_var: str) -> Path:
    # `resolve()` is what makes this a real check rather than a string
    # comparison: it expands `..` and follows symlinks across the whole
    # path, including a tail that does not exist yet, so a link inside
    # an allowed root pointing out of it resolves to its true target
    # and fails containment. It also resolves a relative path against
    # the CWD, which is the pre-existing behaviour.
    resolved = Path(path).expanduser().resolve()
    if any(resolved == root or resolved.is_relative_to(root) for root in roots):
        return resolved
    msg = (
        f"Path {path!r} resolves to {str(resolved)!r}, which is outside the "
        f"allowed roots. Set {env_var} to permit it."
    )
    raise PathOutsideAllowedRootsError(
        msg,
        {
            "path": str(path),
            "resolved_path": str(resolved),
            "allowed_roots": [str(root) for root in roots],
            "environment_variable": env_var,
        },
    )


def resolve_read_path(path: str) -> Path:
    """Return the resolved path, or raise if it is not readable here."""
    return _resolve_within(path, allowed_read_roots(), ALLOWED_READ_ROOTS_ENV)


def resolve_write_path(path: str) -> Path:
    """Return the resolved path, or raise if it is not writable here."""
    return _resolve_within(path, allowed_write_roots(), ALLOWED_WRITE_ROOTS_ENV)
