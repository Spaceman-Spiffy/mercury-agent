"""
Baked-in build metadata for Hermes Agent.

Source installs report their git revision live via ``git rev-parse`` (see
``hermes_cli/dump.py`` and ``hermes_cli/banner.py``).  That doesn't work inside
the published Docker image because ``.dockerignore`` excludes ``.git``, so
those callsites fall back to ``"(unknown)"`` / drop the banner suffix entirely.

To make ``hermes dump`` and the startup banner identify the exact commit the
image was built from, the Docker build writes the build-time ``$HERMES_GIT_SHA``
arg into ``<project_root>/.hermes_build_sha``.  This module is the single
read-side helper consumed by both callsites — keeping the lookup in one place
so the file path and missing-file behaviour stay consistent.

Behaviour:

- Returns ``None`` when the file is absent.  Source installs and dev images
  built without the ``HERMES_GIT_SHA`` build-arg fall through to live-git
  resolution in the caller, so non-Docker installs are unaffected.
- Returns ``None`` on any IO / decoding error.  The build-sha is a nice-to-have
  for support triage; nothing in the CLI is allowed to crash because of it.
- Truncates to ``short`` characters (default 8) to match the format used by
  ``git rev-parse --short=8`` throughout the codebase.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

# Display brand name reported by the CLI ("<brand> v<version> ...").  This is a
# fork-local re-identification: the install presents as "Mercury" rather than
# the stock "Hermes Agent".  Overridable at runtime via HERMES_BRAND_NAME so a
# persona switch (e.g. back to Apollo) needs no code edit.
#
# SCOPE: this affects CLI stdout / banners ONLY.  It is deliberately NOT wired
# into agent/anthropic_adapter.py's OAuth identity-substitution table, which is
# load-bearing for Claude-subscription billing and must keep the literal
# "Hermes Agent" string.  Renaming here has zero billing/filter impact because
# these strings are never sent to Anthropic.
_DEFAULT_BRAND_NAME = "Mercury"


def get_brand_name() -> str:
    """Return the display brand name for CLI version/identity output.

    Reads ``HERMES_BRAND_NAME`` at call time (empty/whitespace falls back to the
    default) so the value can be flipped per-process without a restart of the
    importing module.
    """
    return (os.environ.get("HERMES_BRAND_NAME") or "").strip() or _DEFAULT_BRAND_NAME

# Path is resolved relative to this module so it works regardless of cwd —
# matches the pattern used by ``banner._resolve_repo_dir``.
_BUILD_SHA_FILE = Path(__file__).parent.parent / ".hermes_build_sha"


def get_build_sha(short: int = 8) -> Optional[str]:
    """Return the baked-in build SHA, truncated to ``short`` chars, or None.

    Reads ``<project_root>/.hermes_build_sha`` if present.  The file is
    written by the Dockerfile's ``HERMES_GIT_SHA`` build-arg and contains
    the full 40-character commit hash on a single line.
    """
    try:
        if not _BUILD_SHA_FILE.is_file():
            return None
        sha = _BUILD_SHA_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return None
    if not sha:
        return None
    return sha[:short] if short and short > 0 else sha
