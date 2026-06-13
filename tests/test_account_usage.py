from datetime import datetime, timezone

from agent.account_usage import (
    AccountUsageSnapshot,
    AccountUsageWindow,
    fetch_account_usage,
    render_account_usage_lines,
)


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _Client:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, headers=None):
        return _Response(self._payload)


class _RoutingClient:
    def __init__(self, payloads):
        self._payloads = payloads

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, headers=None):
        return _Response(self._payloads[url])


def test_fetch_account_usage_codex(monkeypatch):
    monkeypatch.setattr(
        "agent.account_usage.resolve_codex_runtime_credentials",
        lambda refresh_if_expiring=True: {
            "provider": "openai-codex",
            "base_url": "https://chatgpt.com/backend-api/codex",
            "api_key": "access-token",
        },
    )
    monkeypatch.setattr(
        "agent.account_usage._read_codex_tokens",
        lambda: {"tokens": {"account_id": "acct_123"}},
    )
    monkeypatch.setattr(
        "agent.account_usage.httpx.Client",
        lambda timeout=15.0: _Client(
            {
                "plan_type": "pro",
                "rate_limit": {
                    "primary_window": {
                        "used_percent": 15,
                        "reset_at": 1_900_000_000,
                        "limit_window_seconds": 18000,
                    },
                    "secondary_window": {
                        "used_percent": 40,
                        "reset_at": 1_900_500_000,
                        "limit_window_seconds": 604800,
                    },
                },
                "credits": {"has_credits": True, "balance": 12.5},
            }
        ),
    )

    snapshot = fetch_account_usage("openai-codex")

    assert snapshot is not None
    assert snapshot.plan == "Pro"
    assert len(snapshot.windows) == 2
    assert snapshot.windows[0].label == "Session"
    assert snapshot.windows[0].used_percent == 15.0
    assert snapshot.windows[0].reset_at == datetime.fromtimestamp(1_900_000_000, tz=timezone.utc)
    assert "Credits balance: $12.50" in snapshot.details


def test_render_account_usage_lines_includes_reset_and_provider():
    snapshot = AccountUsageSnapshot(
        provider="openai-codex",
        source="usage_api",
        fetched_at=datetime.now(timezone.utc),
        plan="Pro",
        windows=(
            AccountUsageWindow(
                label="Session",
                used_percent=25,
                reset_at=datetime.now(timezone.utc),
            ),
        ),
        details=("Credits balance: $9.99",),
    )
    lines = render_account_usage_lines(snapshot)

    assert lines[0] == "📈 Account limits"
    assert "openai-codex (Pro)" in lines[1]
    assert "Session: 75% remaining (25% used)" in lines[2]
    assert "Credits balance: $9.99" in lines[3]


def test_fetch_account_usage_openrouter_uses_limit_remaining_and_ignores_deprecated_rate_limit(monkeypatch):
    monkeypatch.setattr(
        "agent.account_usage.resolve_runtime_provider",
        lambda requested, explicit_base_url=None, explicit_api_key=None: {
            "provider": "openrouter",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "sk-test",
        },
    )
    monkeypatch.setattr(
        "agent.account_usage.httpx.Client",
        lambda timeout=10.0: _RoutingClient(
            {
                "https://openrouter.ai/api/v1/credits": {
                    "data": {"total_credits": 300.0, "total_usage": 10.92}
                },
                "https://openrouter.ai/api/v1/key": {
                    "data": {
                        "limit": 100.0,
                        "limit_remaining": 70.0,
                        "limit_reset": "monthly",
                        "usage": 12.5,
                        "usage_daily": 0.5,
                        "usage_weekly": 2.0,
                        "usage_monthly": 8.0,
                        "rate_limit": {"requests": -1, "interval": "10s"},
                    }
                },
            }
        ),
    )

    snapshot = fetch_account_usage("openrouter")

    assert snapshot is not None
    assert snapshot.windows == (
        AccountUsageWindow(
            label="API key quota",
            used_percent=30.0,
            detail="$70.00 of $100.00 remaining • resets monthly",
        ),
    )
    assert "Credits balance: $289.08" in snapshot.details
    assert "API key usage: $12.50 total • $0.50 today • $2.00 this week • $8.00 this month" in snapshot.details
    assert all("-1 requests / 10s" not in line for line in render_account_usage_lines(snapshot))


def test_fetch_account_usage_openrouter_omits_quota_window_when_key_has_no_limit(monkeypatch):
    monkeypatch.setattr(
        "agent.account_usage.resolve_runtime_provider",
        lambda requested, explicit_base_url=None, explicit_api_key=None: {
            "provider": "openrouter",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "sk-test",
        },
    )
    monkeypatch.setattr(
        "agent.account_usage.httpx.Client",
        lambda timeout=10.0: _RoutingClient(
            {
                "https://openrouter.ai/api/v1/credits": {
                    "data": {"total_credits": 100.0, "total_usage": 25.5}
                },
                "https://openrouter.ai/api/v1/key": {
                    "data": {
                        "limit": None,
                        "limit_remaining": None,
                        "usage": 25.5,
                        "usage_daily": 1.25,
                        "usage_weekly": 4.5,
                        "usage_monthly": 18.0,
                    }
                },
            }
        ),
    )

    snapshot = fetch_account_usage("openrouter")

    assert snapshot is not None
    assert snapshot.windows == ()
    assert "Credits balance: $74.50" in snapshot.details
    assert "API key usage: $25.50 total • $1.25 today • $4.50 this week • $18.00 this month" in snapshot.details


def _anthropic_oauth_env(monkeypatch, payload):
    """Wire the Anthropic OAuth usage fetch to a canned payload."""
    monkeypatch.setattr(
        "agent.account_usage.resolve_anthropic_token",
        lambda: "oauth-token",
    )
    monkeypatch.setattr("agent.account_usage._is_oauth_token", lambda token: True)
    monkeypatch.setattr(
        "agent.account_usage.httpx.Client",
        lambda timeout=15.0: _Client(payload),
    )


def test_fetch_anthropic_utilization_is_percent_not_fraction(monkeypatch):
    """`utilization` is already a percentage (0–100); a 1.0 means 1%, not 100%.

    Regression: the old parser did `util*100 if util <= 1 else util`, which
    inflated any window sitting at <=1% (e.g. seven_day_sonnet=1.0) to 100%.
    The Sonnet-only week showed 100% used while Claude Code showed 1%.
    """
    from agent.account_usage import fetch_account_usage

    _anthropic_oauth_env(
        monkeypatch,
        {
            "five_hour": {"utilization": 7.0, "resets_at": "2026-06-13T15:39:59+00:00"},
            "seven_day": {"utilization": 5.0, "resets_at": "2026-06-15T10:59:59+00:00"},
            "seven_day_opus": None,
            "seven_day_sonnet": {"utilization": 1.0, "resets_at": "2026-06-15T10:59:59+00:00"},
        },
    )

    snapshot = fetch_account_usage("anthropic")

    assert snapshot is not None
    by_label = {w.label: w.used_percent for w in snapshot.windows}
    # The decisive assertion: 1.0 → 1%, NOT 100%.
    assert by_label["Current week (Sonnet only)"] == 1.0
    assert by_label["Current session"] == 7.0
    assert by_label["Current week (all models)"] == 5.0
    # Opus window is null in the payload and must be omitted, not zero-filled.
    assert "Current week (Opus only)" not in by_label


def test_render_account_usage_block_matches_claude_code_shape(monkeypatch):
    """The rich block renders heading + bar + 'N% used' + reset, per window."""
    from agent.account_usage import (
        AccountUsageSnapshot,
        AccountUsageWindow,
        render_account_usage_block,
    )

    snapshot = AccountUsageSnapshot(
        provider="anthropic",
        source="oauth_usage_api",
        fetched_at=datetime.now(timezone.utc),
        windows=(
            AccountUsageWindow(
                label="Current week (Sonnet only)",
                used_percent=1.0,
                reset_at=datetime.now(timezone.utc),
            ),
        ),
    )
    block = render_account_usage_block(snapshot)

    assert block[0] == "Current week (Sonnet only)"
    # The gauge line carries the percentage and a bar made of block glyphs.
    assert "1% used" in block[1]
    assert ("█" in block[1]) or ("░" in block[1])
    # A 1%-used 30-wide bar must be almost entirely empty (not full).
    assert block[1].count("█") <= 1
    assert any(line.startswith("Resets ") for line in block)


def test_render_account_usage_block_empty_when_unavailable():
    from agent.account_usage import AccountUsageSnapshot, render_account_usage_block

    empty = AccountUsageSnapshot(
        provider="anthropic",
        source="oauth_usage_api",
        fetched_at=datetime.now(timezone.utc),
    )
    assert render_account_usage_block(empty) == []
    assert render_account_usage_block(None) == []
