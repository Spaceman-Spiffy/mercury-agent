"""Tests for the ``transform_gateway_notice`` plugin hook.

The hook fires inside ``GatewayRunner._transform_gateway_notice`` just
before a gateway-originated lifecycle notice (restart / online / long-run)
is sent to the chat. These notices never pass through the per-turn
``transform_llm_output`` path, so this is the seam a cosmetic output filter
uses to reach the gateway's own system messages.

Driving the full gateway from a unit test is prohibitively heavy, so these
tests exercise the invoke_hook dispatch semantics the wiring depends on:

    for r in results:
        if isinstance(r, str) and r:
            return r   # First non-empty string wins
    return text        # fail-safe: unchanged

Mirrors ``test_transform_llm_output_hook.py``.
"""

from pathlib import Path

import yaml

from hermes_cli.plugins import PluginManager, VALID_HOOKS


def _make_enabled_plugin(hermes_home: Path, name: str, register_body: str) -> Path:
    """Create a plugin under <hermes_home>/plugins/<name> and opt it in."""
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


def test_transform_gateway_notice_in_valid_hooks():
    assert "transform_gateway_notice" in VALID_HOOKS


def test_notice_hook_receives_expected_kwargs(tmp_path, monkeypatch):
    """Hook callback should see text + kind + platform."""
    hermes_home = tmp_path / "hermes_test"
    hermes_home.mkdir(exist_ok=True)
    _make_enabled_plugin(
        hermes_home, "capture_notice",
        register_body=(
            'ctx.register_hook("transform_gateway_notice", '
            'lambda **kw: f"{kw[\'text\']}|{kw[\'kind\']}|{kw[\'platform\']}")'
        ),
    )
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    mgr = PluginManager()
    mgr.discover_and_load()

    results = mgr.invoke_hook(
        "transform_gateway_notice",
        text="Gateway online",
        kind="online",
        platform="matrix",
    )
    assert results == ["Gateway online|online|matrix"]


def test_first_non_empty_string_wins(tmp_path, monkeypatch):
    """A plugin returning None must not suppress a later plugin's string."""
    hermes_home = tmp_path / "hermes_test"
    hermes_home.mkdir(exist_ok=True)
    # Plugin A returns None (declines); plugin B returns a replacement.
    _make_enabled_plugin(
        hermes_home, "notice_decline",
        register_body='ctx.register_hook("transform_gateway_notice", lambda **kw: None)',
    )
    _make_enabled_plugin(
        hermes_home, "notice_rewrite",
        register_body='ctx.register_hook("transform_gateway_notice", lambda **kw: "REWRITTEN")',
    )
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    mgr = PluginManager()
    mgr.discover_and_load()

    results = mgr.invoke_hook(
        "transform_gateway_notice",
        text="original",
        kind="restart",
        platform="cli",
    )
    # Dispatch returns every plugin's result; the consumer picks the first
    # non-empty string. Assert that selection rule holds over the results.
    picked = next((r for r in results if isinstance(r, str) and r), "original")
    assert picked == "REWRITTEN"
