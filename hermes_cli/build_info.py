"""
Baked-in build metadata for Hermes Agent.

MERCURY FORK NOTE: ``get_code_identity()`` below is a thin compat SHIM —
upstream moved the real implementation (install-stamp-first resolution) to
``hermes_cli/version_info.py``; this module now only re-exports it so any
``from hermes_cli.build_info import get_code_identity`` call site that has
not yet migrated keeps working. The old Docker-build-arg sha mechanism
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
    """Compat shim: re-exports the real implementation in version_info.py.

    Upstream moved resolution (install-stamp first, live-git second, unknown
    third) to ``hermes_cli/version_info.get_code_identity()``. This module
    keeps re-exporting the name so call sites that still import it from
    ``build_info`` (fork and upstream alike) do not break.
    """
    from hermes_cli.version_info import get_code_identity as _real_get_code_identity

    return _real_get_code_identity(refresh=refresh)
