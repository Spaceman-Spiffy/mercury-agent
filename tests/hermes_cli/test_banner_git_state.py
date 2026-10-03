"""Tests for hermes_cli.banner's git-ancestry banner state.

MERCURY FORK: ported forward from the pre-pm-clean test_banner_git_state.py.
Upstream deleted the whole file (commit 427d4936c2, "retarget merge-fallout
tests at pm-clean's seams") on the stated rationale that it was "covered by
test_source_check" — true for the legacy SSH fastpath tests
(_check_via_local_git / _upstream_main_sha / _github_compare_behind /
UPDATE_AVAILABLE_NO_COUNT: confirmed removed, that coverage genuinely moved),
but format_banner_version_label and get_git_banner_state are a different,
still-live seam with a fork-only branch (MERCURY FORK brand-name lookup) and
have no coverage in test_source_check.py, which tests an unrelated
branch/fork-tracking subsystem. Ported with two fixes for the pm-clean
refactor: banner.VERSION -> get_version_info().derived_version, and the git
read helper moved to hermes_cli.source_check._git_stdout.
"""
from unittest.mock import MagicMock, patch


def test_format_banner_version_label_without_git_state():
    from hermes_cli import banner
    from hermes_cli.build_info import get_brand_name

    with patch.object(banner, "get_git_banner_state", return_value=None):
        value = banner.format_banner_version_label()

    assert value == (
        f"{get_brand_name()} v{banner.get_version_info().derived_version} "
        f"({banner.RELEASE_DATE})"
    )


def test_format_banner_version_label_on_upstream_main():
    from hermes_cli import banner

    with patch.object(
        banner,
        "get_git_banner_state",
        return_value={"upstream": "b2f477a3", "local": "b2f477a3", "ahead": 0},
    ):
        value = banner.format_banner_version_label()

    assert value.endswith("· upstream b2f477a3")
    assert "local" not in value


def test_get_git_banner_state_reads_origin_and_head(tmp_path):
    from hermes_cli import banner

    repo_dir = tmp_path / "repo"
    (repo_dir / ".git").mkdir(parents=True)

    results = {
        ("git", "rev-parse", "--short=8", "origin/main"): MagicMock(returncode=0, stdout="b2f477a3\n"),
        ("git", "rev-parse", "--short=8", "HEAD"): MagicMock(returncode=0, stdout="af8aad31\n"),
        ("git", "rev-list", "--count", "origin/main..HEAD"): MagicMock(returncode=0, stdout="3\n"),
    }

    def fake_run(cmd, **kwargs):
        key = tuple(cmd)
        if key not in results:
            raise AssertionError(f"unexpected command: {cmd}")
        return results[key]

    # MERCURY FORK sibling fix: the git subprocess helper moved from
    # banner.subprocess.run to hermes_cli.source_check._git_run's
    # subprocess.run call during the pm-clean refactor.
    with patch("hermes_cli.source_check.subprocess.run", side_effect=fake_run):
        state = banner.get_git_banner_state(repo_dir)

    assert state == {"upstream": "b2f477a3", "local": "af8aad31", "ahead": 3}
