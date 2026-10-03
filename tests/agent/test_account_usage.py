from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest

from agent import account_usage


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://chatgpt.com/backend-api/wham/usage")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("request failed", request=request, response=response)

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, calls, payload):
        self.calls = calls
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, headers):
        self.calls.append({"url": url, "headers": headers})
        return _FakeResponse(self.payload)


@pytest.fixture
def codex_usage_payload():
    return {
        "plan_type": "plus",
        "rate_limit": {
            "primary_window": {
                "used_percent": 21,
                "reset_at": 1779846359,
            },
            "secondary_window": {
                "used_percent": 4,
                "reset_at": 1780230796,
            },
        },
        "credits": {"has_credits": False},
    }


def test_codex_usage_prefers_explicit_live_agent_credentials(monkeypatch, codex_usage_payload):
    calls = []
    monkeypatch.setattr(
        account_usage.httpx,
        "Client",
        lambda timeout: _FakeClient(calls, codex_usage_payload),
    )
    monkeypatch.setattr(
        account_usage,
        "resolve_codex_runtime_credentials",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("legacy auth should not be used")),
    )

    snapshot = account_usage.fetch_account_usage(
        "openai-codex",
        base_url="https://chatgpt.com/backend-api/codex",
        api_key="live-agent-token",
    )

    assert snapshot is not None
    assert snapshot.provider == "openai-codex"
    assert snapshot.plan == "Plus"
    assert [w.label for w in snapshot.windows] == ["Session", "Weekly"]
    assert snapshot.windows[0].used_percent == 21
    assert calls[0]["url"] == "https://chatgpt.com/backend-api/wham/usage"
    assert calls[0]["headers"]["Authorization"] == "Bearer live-agent-token"


def test_codex_usage_falls_back_to_native_credential_pool(monkeypatch, codex_usage_payload):
    calls = []
    monkeypatch.setattr(
        account_usage.httpx,
        "Client",
        lambda timeout: _FakeClient(calls, codex_usage_payload),
    )
    # Pool fallback fires only on AuthError (the documented "no creds" mode of
    # the resolver), NOT on arbitrary exceptions — see the transient-error guard
    # test below.
    monkeypatch.setattr(
        account_usage,
        "resolve_codex_runtime_credentials",
        lambda **kwargs: (_ for _ in ()).throw(
            account_usage.AuthError("no singleton auth", provider="openai-codex", code="codex_auth_missing")
        ),
    )

    pool_entry = SimpleNamespace(
        runtime_api_key="pooled-token",
        runtime_base_url="https://chatgpt.com/backend-api/codex",
    )
    pool = SimpleNamespace(select=lambda: pool_entry)

    import agent.credential_pool as credential_pool

    monkeypatch.setattr(credential_pool, "load_pool", lambda provider: pool)

    snapshot = account_usage.fetch_account_usage("openai-codex")

    assert snapshot is not None
    assert snapshot.windows[0].label == "Session"
    assert snapshot.windows[1].label == "Weekly"
    assert calls[0]["url"] == "https://chatgpt.com/backend-api/wham/usage"
    assert calls[0]["headers"]["Authorization"] == "Bearer pooled-token"
    # Pool creds have no account_id concept — the ChatGPT-Account-ID header must
    # be omitted rather than sent stale/wrong.
    assert "ChatGPT-Account-ID" not in calls[0]["headers"]




def _explicit_creds_snapshot(monkeypatch, payload):
    calls = []
    monkeypatch.setattr(account_usage.httpx, "Client", lambda timeout: _FakeClient(calls, payload))
    snapshot = account_usage.fetch_account_usage(
        "openai-codex", base_url="https://chatgpt.com/backend-api/codex", api_key="live-agent-token",
    )
    return snapshot, calls


def test_codex_weekly_only_primary_window_is_labeled_weekly(monkeypatch):
    """#65387: a lone 604800s primary_window is the weekly limit, not the session one."""
    payload = {"plan_type": "pro", "rate_limit": {
        "primary_window": {"used_percent": 1, "limit_window_seconds": 604800},
        "secondary_window": None,
    }}
    snapshot, _ = _explicit_creds_snapshot(monkeypatch, payload)
    assert [(w.label, w.used_percent) for w in snapshot.windows] == [("Weekly", 1.0)]


def test_codex_window_labels_follow_duration_with_positional_fallback(monkeypatch):
    # Swapped positions: labels must follow limit_window_seconds.
    payload = {"rate_limit": {
        "primary_window": {"used_percent": 4, "limit_window_seconds": 604800},
        "secondary_window": {"used_percent": 21, "limit_window_seconds": 18000},
    }}
    snapshot, _ = _explicit_creds_snapshot(monkeypatch, payload)
    assert [w.label for w in snapshot.windows] == ["Weekly", "Session"]
    # Missing / unrecognized durations keep the legacy positional labels.
    payload = {"rate_limit": {
        "primary_window": {"used_percent": 4},
        "secondary_window": {"used_percent": 21, "limit_window_seconds": 12345},
    }}
    snapshot, _ = _explicit_creds_snapshot(monkeypatch, payload)
    assert [w.label for w in snapshot.windows] == ["Session", "Weekly"]


def test_codex_snapshot_exposes_exact_raw_payload_with_one_get(monkeypatch, codex_usage_payload):
    """#79695: the decoded body rides along untouched (unknown fields included), from the single GET."""
    codex_usage_payload["future_field"] = {"nested": [1, 2]}
    snapshot, calls = _explicit_creds_snapshot(monkeypatch, codex_usage_payload)
    assert snapshot.raw == codex_usage_payload
    assert snapshot.raw["future_field"] == {"nested": [1, 2]}
    assert len(calls) == 1
    assert [w.label for w in snapshot.windows] == ["Session", "Weekly"]  # normalized limits unchanged
    # Additive: existing constructor calls stay valid and default to no raw body.
    assert account_usage.AccountUsageSnapshot(provider="anthropic", source="x", fetched_at=snapshot.fetched_at).raw is None


def test_codex_invalid_payload_fails_closed(monkeypatch):
    snapshot, _ = _explicit_creds_snapshot(monkeypatch, ["not", "a", "dict"])
    assert snapshot is None


def test_codex_usage_account_id_read_failure_keeps_singleton_token(monkeypatch, codex_usage_payload):
    """When the resolver succeeds but the separate account_id read raises, the
    working singleton token must still be used (best-effort account_id), NOT
    abandoned in favor of a header-less pool credential."""
    calls = []
    monkeypatch.setattr(
        account_usage.httpx,
        "Client",
        lambda timeout: _FakeClient(calls, codex_usage_payload),
    )
    monkeypatch.setattr(
        account_usage,
        "resolve_codex_runtime_credentials",
        lambda **kwargs: {
            "api_key": "singleton-token",
            "base_url": "https://chatgpt.com/backend-api/codex",
        },
    )
    monkeypatch.setattr(
        account_usage,
        "_read_codex_tokens",
        lambda *a, **k: (_ for _ in ()).throw(
            account_usage.AuthError("partial store", provider="openai-codex", code="codex_auth_invalid_shape")
        ),
    )

    import agent.credential_pool as credential_pool

    monkeypatch.setattr(
        credential_pool,
        "load_pool",
        lambda provider: (_ for _ in ()).throw(AssertionError("pool must not be consulted")),
    )

    snapshot = account_usage.fetch_account_usage("openai-codex")

    assert snapshot is not None
    assert calls[0]["headers"]["Authorization"] == "Bearer singleton-token"
    # account_id read failed → header omitted, but the singleton token is kept.
    assert "ChatGPT-Account-ID" not in calls[0]["headers"]


def test_codex_usage_retries_401_with_forced_refresh(monkeypatch, codex_usage_payload):
    credential_calls = []
    request_calls = []
    responses = [_FakeResponse({}, status_code=401), _FakeResponse(codex_usage_payload)]

    def resolve(**kwargs):
        credential_calls.append(kwargs)
        token = "fresh-token" if kwargs.get("force_refresh") else "revoked-token"
        return {"api_key": token, "base_url": "https://chatgpt.com/backend-api/codex"}

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, url, headers):
            request_calls.append(headers["Authorization"])
            return responses.pop(0)

    monkeypatch.setattr(account_usage, "resolve_codex_runtime_credentials", resolve)
    monkeypatch.setattr(account_usage, "_read_codex_tokens", lambda: {"tokens": {}})
    monkeypatch.setattr(account_usage.httpx, "Client", lambda timeout: Client())

    snapshot = account_usage.fetch_account_usage("openai-codex")

    assert snapshot is not None
    assert snapshot.windows[0].label == "Session"
    assert credential_calls == [
        {"refresh_if_expiring": True},
        {"refresh_if_expiring": True, "force_refresh": True},
    ]
    assert request_calls == ["Bearer revoked-token", "Bearer fresh-token"]


# ── Banked rate-limit reset credits (`/usage reset`) ─────────────────────────


class _FakeResetClient:
    """GET returns the usage payload; POST returns the consume payload."""

    def __init__(self, calls, usage_payload, consume_payload=None):
        self.calls = calls
        self.usage_payload = usage_payload
        self.consume_payload = consume_payload or {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, headers):
        self.calls.append({"method": "GET", "url": url, "headers": headers})
        return _FakeResponse(self.usage_payload)

    def post(self, url, headers=None, json=None):
        self.calls.append({"method": "POST", "url": url, "headers": headers, "json": json})
        return _FakeResponse(self.consume_payload)


def _usage_payload_with_resets(primary_used, secondary_used, banked):
    return {
        "plan_type": "plus",
        "rate_limit": {
            "primary_window": {"used_percent": primary_used, "reset_at": 1779846359},
            "secondary_window": {"used_percent": secondary_used, "reset_at": 1780230796},
        },
        "rate_limit_reset_credits": {"available_count": banked},
        "credits": {"has_credits": False},
    }
















def test_redeem_retries_401_with_forced_refresh(monkeypatch):
    credential_calls = []
    request_calls = []
    client_count = 0
    payload = _usage_payload_with_resets(100, 40, 1)

    def resolve(base_url, api_key, *, force_refresh=False):
        credential_calls.append(force_refresh)
        token = "fresh-token" if force_refresh else "revoked-token"
        return token, "https://chatgpt.com/backend-api/codex", None

    class Client(_FakeResetClient):
        def get(self, url, headers):
            request_calls.append(("GET", headers["Authorization"]))
            if headers["Authorization"] == "Bearer revoked-token":
                return _FakeResponse({}, status_code=401)
            return _FakeResponse(payload)

        def post(self, url, headers=None, json=None):
            request_calls.append(("POST", headers["Authorization"]))
            return _FakeResponse({"code": "reset", "windows_reset": 2})

    def client_factory(timeout):
        nonlocal client_count
        client_count += 1
        return Client([], payload)

    monkeypatch.setattr(account_usage, "_resolve_codex_usage_credentials", resolve)
    monkeypatch.setattr(account_usage.httpx, "Client", client_factory)

    result = account_usage.redeem_codex_reset_credit()

    assert result.status == "reset"
    assert credential_calls == [False, True]
    assert request_calls == [
        ("GET", "Bearer revoked-token"),
        ("GET", "Bearer fresh-token"),
        ("POST", "Bearer fresh-token"),
    ]
    assert client_count == 2


def test_redeem_missing_credentials_reports_unavailable(monkeypatch):
    monkeypatch.setattr(
        account_usage,
        "_resolve_codex_usage_credentials",
        lambda base_url, api_key, **kwargs: (_ for _ in ()).throw(RuntimeError("no creds")),
    )

    result = account_usage.redeem_codex_reset_credit()

    assert result.status == "unavailable"
    assert "hermes auth" in result.message


def test_codex_usage_401_retry_refreshes_the_explicit_credential_not_another_account(monkeypatch, codex_usage_payload):
    """A live agent on pool entry B hands its own api_key in; after a 401 the retry must refresh B,
    not re-resolve and render the singleton/pool account A's usage."""
    request_calls = []
    refresh_hints = []
    responses = [_FakeResponse({}, status_code=401), _FakeResponse(codex_usage_payload)]

    class Pool:
        def try_refresh_matching(self, api_key_hint=None, credential_id=None):
            refresh_hints.append(api_key_hint)
            return SimpleNamespace(runtime_api_key="pool-B-fresh", runtime_base_url=None)

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, url, headers):
            request_calls.append(headers["Authorization"])
            return responses.pop(0)

    monkeypatch.setattr(account_usage, "resolve_codex_runtime_credentials",
                        lambda **kwargs: pytest.fail("must not re-resolve another account's credential"))
    monkeypatch.setattr(account_usage, "_read_codex_tokens", lambda: {"tokens": {"access_token": "singleton-A"}})
    monkeypatch.setattr("agent.credential_pool.load_pool", lambda provider: Pool())
    monkeypatch.setattr(account_usage.httpx, "Client", lambda timeout: Client())

    snapshot = account_usage.fetch_account_usage(
        "openai-codex", base_url="https://chatgpt.com/backend-api/codex", api_key="pool-B-revoked")

    assert snapshot is not None


# MERCURY FORK: the 7 tests below cover render_account_usage_lines/_block and the
# non-Codex provider paths (OpenRouter, Anthropic) that the upstream split above
# does not exercise. Ported forward from the pre-rename tests/test_account_usage.py
# (fork commits 84cbc27634, 90c71d2ef3) when upstream's test-tree reorg (d10bb2ab6f)
# moved this file to tests/agent/test_account_usage.py.

class _MercuryResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _MercuryClient:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, headers=None):
        return _MercuryResponse(self._payload)


class _MercuryRoutingClient:
    def __init__(self, payloads):
        self._payloads = payloads

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, headers=None):
        return _MercuryResponse(self._payloads[url])


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
        lambda timeout=15.0: _MercuryClient(
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

    snapshot = account_usage.fetch_account_usage("openai-codex")

    assert snapshot is not None
    assert snapshot.plan == "Pro"
    assert len(snapshot.windows) == 2
    assert snapshot.windows[0].label == "Session"
    assert snapshot.windows[0].used_percent == 15.0
    assert snapshot.windows[0].reset_at == datetime.fromtimestamp(1_900_000_000, tz=timezone.utc)
    assert "Credits balance: $12.50" in snapshot.details


def test_render_account_usage_lines_includes_reset_and_provider():
    snapshot = account_usage.AccountUsageSnapshot(
        provider="openai-codex",
        source="usage_api",
        fetched_at=datetime.now(timezone.utc),
        plan="Pro",
        windows=(
            account_usage.AccountUsageWindow(
                label="Session",
                used_percent=25,
                reset_at=datetime.now(timezone.utc),
            ),
        ),
        details=("Credits balance: $9.99",),
    )
    lines = account_usage.render_account_usage_lines(snapshot)

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
        lambda timeout=10.0: _MercuryRoutingClient(
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

    snapshot = account_usage.fetch_account_usage("openrouter")

    assert snapshot is not None
    assert snapshot.windows == (
        account_usage.AccountUsageWindow(
            label="API key quota",
            used_percent=30.0,
            detail="$70.00 of $100.00 remaining • resets monthly",
        ),
    )
    assert "Credits balance: $289.08" in snapshot.details
    assert "API key usage: $12.50 total • $0.50 today • $2.00 this week • $8.00 this month" in snapshot.details
    assert all("-1 requests / 10s" not in line for line in account_usage.render_account_usage_lines(snapshot))


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
        lambda timeout=10.0: _MercuryRoutingClient(
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

    snapshot = account_usage.fetch_account_usage("openrouter")

    assert snapshot is not None
    assert snapshot.windows == ()
    assert "Credits balance: $74.50" in snapshot.details
    assert "API key usage: $25.50 total • $1.25 today • $4.50 this week • $18.00 this month" in snapshot.details


def _mercury_anthropic_oauth_env(monkeypatch, payload):
    """Wire the Anthropic OAuth usage fetch to a canned payload."""
    monkeypatch.setattr(
        "agent.account_usage.resolve_anthropic_token",
        lambda: "oauth-token",
    )
    monkeypatch.setattr("agent.account_usage._is_oauth_token", lambda token: True)
    monkeypatch.setattr(
        "agent.account_usage.httpx.Client",
        lambda timeout=15.0: _MercuryClient(payload),
    )


def test_fetch_anthropic_utilization_is_percent_not_fraction(monkeypatch):
    """`utilization` is already a percentage (0–100); a 1.0 means 1%, not 100%.

    Regression: the old parser did `util*100 if util <= 1 else util`, which
    inflated any window sitting at <=1% (e.g. seven_day_sonnet=1.0) to 100%.
    The Sonnet-only week showed 100% used while Claude Code showed 1%.
    """
    _mercury_anthropic_oauth_env(
        monkeypatch,
        {
            "five_hour": {"utilization": 7.0, "resets_at": "2026-06-13T15:39:59+00:00"},
            "seven_day": {"utilization": 5.0, "resets_at": "2026-06-15T10:59:59+00:00"},
            "seven_day_opus": None,
            "seven_day_sonnet": {"utilization": 1.0, "resets_at": "2026-06-15T10:59:59+00:00"},
        },
    )

    snapshot = account_usage.fetch_account_usage("anthropic")

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
    snapshot = account_usage.AccountUsageSnapshot(
        provider="anthropic",
        source="oauth_usage_api",
        fetched_at=datetime.now(timezone.utc),
        windows=(
            account_usage.AccountUsageWindow(
                label="Current week (Sonnet only)",
                used_percent=1.0,
                reset_at=datetime.now(timezone.utc),
            ),
        ),
    )
    block = account_usage.render_account_usage_block(snapshot)

    assert block[0] == "Current week (Sonnet only)"
    # The gauge line carries the percentage and a bar made of block glyphs.
    assert "1% used" in block[1]
    assert ("█" in block[1]) or ("░" in block[1])
    # A 1%-used 30-wide bar must be almost entirely empty (not full).
    assert block[1].count("█") <= 1
    assert any(line.startswith("Resets ") for line in block)


def test_render_account_usage_block_empty_when_unavailable():
    empty = account_usage.AccountUsageSnapshot(
        provider="anthropic",
        source="oauth_usage_api",
        fetched_at=datetime.now(timezone.utc),
    )
    assert account_usage.render_account_usage_block(empty) == []
    assert account_usage.render_account_usage_block(None) == []
