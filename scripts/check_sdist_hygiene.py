#!/usr/bin/env python3
"""Fail if a source distribution contains files that must never be published.

The 0.6.0 sdist was 4.8 MB and shipped `.taskmaster/`, `.backlog/`, agent
configuration and a 5 MB third-party PDF that was not ours to redistribute.
`[tool.hatch.build.targets.sdist]` now uses an explicit allow-list, so that
cannot happen by accident — but an allow-list is one line away from being
widened, and nobody would notice until it was on PyPI.

This is the check that notices. It runs in CI on every pull request, and it is
runnable locally:

    uv run python scripts/check_sdist_hygiene.py dist/*.tar.gz

Exits non-zero with the offending paths listed.
"""

from __future__ import annotations

import argparse
import sys
import tarfile
from pathlib import Path

# Matched against each archive path with the leading "<name>-<version>/" removed.
# Substring match, so ".backlog" catches ".backlog/tasks/arc-001 - ....md".
FORBIDDEN_SUBSTRINGS = (
    ".taskmaster",
    ".backlog",
    ".claude",
    ".codex",
    ".agents",
    ".windsurf",
    ".roomodes",
    ".venv",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
)

# Matched against the path suffix.
FORBIDDEN_SUFFIXES = (
    ".pdf",
    ".archimate",
)

# Exact basenames that must never appear. `.env.example` is covered by the
# `.env` prefix rule below rather than listed separately.
FORBIDDEN_BASENAME_PREFIXES = (".env",)

# A ceiling, not a target. The sdist is ~200 KB; anything approaching this means
# something large slipped in, even if it is not on the lists above.
MAX_SDIST_BYTES = 2 * 1024 * 1024


def strip_root(name: str) -> str:
    """Drop the leading `<project>-<version>/` component from an archive path."""
    _, _, rest = name.partition("/")
    return rest


def offending_paths(archive: Path) -> list[str]:
    offenders: list[str] = []
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            path = strip_root(member.name)
            if not path:
                continue
            basename = path.rsplit("/", 1)[-1]
            if (
                any(token in path for token in FORBIDDEN_SUBSTRINGS)
                or path.endswith(FORBIDDEN_SUFFIXES)
                or basename.startswith(FORBIDDEN_BASENAME_PREFIXES)
            ):
                offenders.append(path)
    return sorted(set(offenders))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", nargs="+", type=Path)
    args = parser.parse_args()

    failed = False
    for archive in args.archives:
        if not archive.exists():
            sys.stderr.write(f"error: no such archive: {archive}\n")
            return 2

        size = archive.stat().st_size
        offenders = offending_paths(archive)

        if offenders:
            failed = True
            sys.stderr.write(f"\n{archive.name}: FORBIDDEN PATHS PRESENT\n")
            for path in offenders:
                sys.stderr.write(f"  - {path}\n")
            sys.stderr.write(
                "\nThese must not be published. Check the `include` allow-list "
                "under [tool.hatch.build.targets.sdist] in pyproject.toml.\n",
            )

        if size > MAX_SDIST_BYTES:
            failed = True
            sys.stderr.write(
                f"\n{archive.name}: TOO LARGE — {size / 1024:.0f} KB exceeds the "
                f"{MAX_SDIST_BYTES / 1024:.0f} KB ceiling.\n"
                "Something large slipped into the sdist. Inspect it with "
                f"`tar -tzf {archive}`.\n",
            )

        if not offenders and size <= MAX_SDIST_BYTES:
            sys.stderr.write(f"{archive.name}: clean ({size / 1024:.0f} KB)\n")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
