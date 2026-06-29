"""Tests for the ``transform_stream_fragment`` plugin hook.

Unlike ``transform_llm_output`` / ``transform_interim_output`` (which fire once
on a COMPLETE message), this hook fires repeatedly on the PARTIAL mid-stream
buffer the gateway stream consumer edits onto the platform message as tokens
arrive. It is the seam a cosmetic output filter uses to reach text the user
watches type in real time.

Two layers are covered:
  1. Dispatch semantics on the real PluginManager (kwargs contract, VALID_HOOKS
     membership, first-non-empty-string-wins) — mirrors the sibling hook tests.
  2. The consumer integration point
     ``GatewayStreamConsumer._apply_stream_fragment_transform`` — that it strips
     the streaming cursor before invoking the hook and re-appends it after, is a
     no-cost identity passthrough when no plugin registers, and passes the
     ``at_boundary`` flag through.

Mirrors ``test_transform_interim_output_hook.py``.
"""

from pathlib import Path

import yaml

from hermes_cli.plugins import PluginManager, VALID_HOOKS, get_plugin_manager


def _make_enabled_plugin(hermes_home: Path, name: str, register_body: str) -> Path:
    plugin_dir = hermes_home / "plugins" / name
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.yaml").write_text(
        yaml.safe_dump({"name": name, "version": "0.1.0"}), encoding="utf-8",
    )
    (plugin_dir / "__init__.py").write_text(
        "def register(ctx):\n"
        f"    {register_body}\n",
        encoding="utf-8",
    )
    cfg_path = hermes_home / "config.yaml"
    cfg = {}
    if cfg_path.exists():
        cfg = yaml.safe_load(cfg_path.read_text()) or {}
    cfg.setdefault("plugins", {}).setdefault("enabled", []).append(name)
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return plugin_dir


def test_transform_stream_fragment_in_valid_hooks():
    assert "transform_stream_fragment" in VALID_HOOKS


def test_stream_fragment_hook_receives_expected_kwargs(tmp_path, monkeypatch):
    """Hook sees response_text + at_boundary + session_id + model + platform."""
    hermes_home = tmp_path / "hermes_test"
    hermes_home.mkdir(exist_ok=True)
    _make_enabled_plugin(
        hermes_home, "capture_fragment",
        register_body=(
            'ctx.register_hook("transform_stream_fragment", '
            'lambda **kw: '
            '"|".join([kw["response_text"], str(kw["at_boundary"]), '
            'kw["session_id"], kw["model"], kw["platform"]]))'
        ),
    )
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    mgr = PluginManager()
    mgr.discover_and_load()

    results = mgr.invoke_hook(
        "transform_stream_fragment",
        response_text="the telemetry",
        at_boundary=False,
        session_id="sess-1",
        model="claude-opus",
        platform="matrix",
    )
    assert results == ["the telemetry|False|sess-1|claude-opus|matrix"]


def test_stream_fragment_first_non_empty_string_wins(tmp_path, monkeypatch):
    hermes_home = tmp_path / "hermes_test"
    hermes_home.mkdir(exist_ok=True)
    _make_enabled_plugin(
        hermes_home, "frag_decline",
        register_body='ctx.register_hook("transform_stream_fragment", lambda **kw: None)',
    )
    _make_enabled_plugin(
        hermes_home, "frag_rewrite",
        register_body='ctx.register_hook("transform_stream_fragment", lambda **kw: "REWRITTEN")',
    )
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    mgr = PluginManager()
    mgr.discover_and_load()

    results = mgr.invoke_hook(
        "transform_stream_fragment",
        response_text="original",
        at_boundary=False,
        session_id="s", model="m", platform="cli",
    )
    picked = next((r for r in results if isinstance(r, str) and r), "original")
    assert picked == "REWRITTEN"


# ── Consumer integration: _apply_stream_fragment_transform ──────────────────

def _make_consumer(cursor=" \u2589"):
    from gateway.stream_consumer import GatewayStreamConsumer, StreamConsumerConfig

    class _A:
        platform_name = "matrix"

    cfg = StreamConsumerConfig()
    cfg.cursor = cursor
    return GatewayStreamConsumer(adapter=_A(), chat_id="t", config=cfg)


def test_consumer_passthrough_when_no_plugin(monkeypatch):
    """No registered hook -> identity passthrough, zero mutation."""
    import hermes_cli.plugins as P
    monkeypatch.setattr(P, "_plugin_manager", P.PluginManager())  # empty
    c = _make_consumer()
    s = "the telemetry \u2014 let me \u2589"
    assert c._apply_stream_fragment_transform(s, at_boundary=False) == s


def test_consumer_strips_and_reappends_cursor(monkeypatch):
    """The hook must see the cursor-free body; the cursor is re-appended."""
    import hermes_cli.plugins as P
    mgr = P.PluginManager()
    monkeypatch.setattr(P, "_plugin_manager", mgr)
    # A plugin that uppercases the body it receives — proves the cursor was not
    # passed into the hook (it would otherwise be mangled / counted).
    seen = {}

    def _cb(**kw):
        seen["text"] = kw["response_text"]
        return kw["response_text"].upper()

    mgr._hooks["transform_stream_fragment"] = [_cb]
    c = _make_consumer(cursor=" \u2589")
    out = c._apply_stream_fragment_transform("hello \u2589", at_boundary=False)
    assert seen["text"] == "hello"          # cursor stripped before hook
    assert out == "HELLO \u2589"            # cursor re-appended verbatim
