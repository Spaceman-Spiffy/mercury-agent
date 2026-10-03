"""Tests for the update check mechanism in hermes_cli.banner.

MERCURY FORK: ported forward from the pre-pm-clean test_update_check.py.
Upstream deleted the whole file (commit ae2452c288, "drop the banner
update-check probes; source_check owns passive checks"). True for
check_for_updates (confirmed removed from hermes_cli.banner; the logic lives
in hermes_cli.source_check.check_for_updates now) but
prefetch_update_check (banner's own non-blocking background-thread wrapper,
itself MERCURY FORK-touched at efc2a91c3) is still live code with no
successor test in test_source_check.py or test_banner.py. Ported with one
fix: prefetch_update_check is a no-op under pytest by design
(_skip_background_prefetch(), see its docstring: "tests that exercise the
prefetch itself monkeypatch this predicate to False") — the original test
predates that guard and would silently no-op without the monkeypatch.
"""
import threading
import time
from unittest.mock import patch


def test_prefetch_non_blocking(monkeypatch):
    """prefetch_update_check() should return immediately without blocking."""
    import hermes_cli.banner as banner

    # The banner's background-prefetch-under-pytest guard would otherwise
    # make this call a no-op (see _skip_background_prefetch's docstring).
    monkeypatch.setattr(banner, "_skip_background_prefetch", lambda: False)

    # Reset module state
    banner._update_result = None
    banner._update_check_done = threading.Event()

    with patch.object(banner.source_check, "check_for_updates", return_value={"behind": 5}):
        start = time.monotonic()
        banner.prefetch_update_check()
        elapsed = time.monotonic() - start

        # Should return almost immediately (well under 1 second)
        assert elapsed < 1.0

        # Wait for the background thread to finish
        banner._update_check_done.wait(timeout=5)
        assert banner._update_result == 5
