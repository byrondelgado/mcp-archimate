#!/usr/bin/env python3
"""Refuse to publish when the tag, the package version and the CHANGELOG disagree.

Publishing to PyPI is irreversible: a version number can be yanked but never
reused. The cheap failure is tagging `v0.7.1` while `__version__` still says
`0.7.0` — the build succeeds, the upload succeeds, and the artefact is wrong
forever.

This runs before anything is built.

    uv run python scripts/check_release_version.py v0.7.0
    uv run python scripts/check_release_version.py --no-changelog v0.7.0
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INIT_PATH = REPO_ROOT / "pyarchimate_mcp_server" / "__init__.py"
CHANGELOG_PATH = REPO_ROOT / "CHANGELOG.md"

VERSION_RE = re.compile(r'^__version__\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)
TAG_RE = re.compile(r"^v(\d+\.\d+\.\d+(?:[-.]?[A-Za-z0-9]+)*)$")


def package_version() -> str:
    """Read __version__ directly rather than importing, so this needs no install."""
    match = VERSION_RE.search(INIT_PATH.read_text(encoding="utf-8"))
    if not match:
        sys.exit(f"could not find __version__ in {INIT_PATH}")
    return match.group(1)


def changelog_has_section(version: str) -> bool:
    if not CHANGELOG_PATH.exists():
        return False
    pattern = re.compile(rf"^##\s*\[?{re.escape(version)}\]?", re.MULTILINE)
    return bool(pattern.search(CHANGELOG_PATH.read_text(encoding="utf-8")))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="the release tag, e.g. v0.7.0")
    parser.add_argument(
        "--no-changelog",
        action="store_true",
        help="skip the CHANGELOG section check (for TestPyPI dry runs)",
    )
    args = parser.parse_args()

    tag_match = TAG_RE.match(args.tag)
    if not tag_match:
        sys.exit(
            f"tag {args.tag!r} is not of the form vX.Y.Z — refusing to guess "
            "what version it means",
        )
    tag_version = tag_match.group(1)
    version = package_version()

    if tag_version != version:
        sys.exit(
            f"VERSION MISMATCH\n"
            f"  tag says:              {tag_version}\n"
            f"  __version__ says:      {version}\n\n"
            f"pyarchimate_mcp_server/__init__.py is the single source of truth "
            f"(pyproject.toml reads it via [tool.hatch.version]). Either the bump "
            f"was forgotten or the wrong tag was pushed. Delete the tag, fix, "
            f"and re-tag — do not publish.",
        )

    if not args.no_changelog and not changelog_has_section(version):
        sys.exit(
            f"CHANGELOG.md has no section for {version}.\n"
            f"Add a '## [{version}] - YYYY-MM-DD' entry describing what changed. "
            f"A release with no notes is not a release.",
        )

    print(f"release checks passed: {args.tag} matches __version__ {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
