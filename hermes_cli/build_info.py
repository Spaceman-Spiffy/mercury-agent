"""
Baked-in build metadata for Hermes Agent.

MERCURY FORK NOTE: ``get_code_identity()`` below is upstream's old-updater
shim (always ``unknown``); the real resolver is ``hermes_cli/version_info.py``.
The old Docker-build-arg sha mechanism
(``.hermes_build_sha`` / ``get_build_sha()`` / ``_resolve_git_head_sha()``)
was removed upstream in favor of ``install-stamp.json``-based resolution;
confirmed zero remaining callers of ``get_build_sha`` anywhere in this tree
post-merge, so that machinery is dropped here rather than carried as dead
code. ``get_brand_name()`` has NO upstream equivalent — identity/version
resolution upstream carries no brand concept at all — so it stays
fork-exclusive here.
"""

from __future__ import annotations

import os

# Display brand name reported by the CLI ("<brand> v<version> ..."). This is a
# fork-local re-identification: the install presents as "Mercury" rather than
# the stock "Hermes Agent". Overridable at runtime via HERMES_BRAND_NAME so a
# persona switch (e.g. back to Apollo) needs no code edit.
#
# SCOPE: this affects CLI stdout / banners ONLY. It is deliberately NOT wired
# into agent/anthropic_adapter.py's OAuth identity-substitution table, which is
# load-bearing for Claude-subscription billing and must keep the literal
# "Hermes Agent" string. Renaming here has zero billing/filter impact because
# these strings are never sent to Anthropic.
_DEFAULT_BRAND_NAME = "Mercury"


def get_brand_name() -> str:
    """Return the display brand name for CLI version/identity output.

    Reads ``HERMES_BRAND_NAME`` at call time (empty/whitespace falls back to the
    default) so the value can be flipped per-process without a restart of the
    importing module.
    """
    return (os.environ.get("HERMES_BRAND_NAME") or "").strip() or _DEFAULT_BRAND_NAME


def get_code_identity(refresh: bool = False) -> dict:
    """Upstream's shim: suppress old-updater work until relaunch, not certify the new checkout.

    The live resolver (install-stamp first, live git second) is ``hermes_cli.version_info
    .get_code_identity``; an old parent process importing this name after an update must get
    ``unknown`` so it schedules nothing against the fresh checkout
    (tests/hermes_cli/test_old_updater_additional_shims.py).
    """
    return {"sha": None, "short_sha": None, "version": None, "source": "unknown"}
