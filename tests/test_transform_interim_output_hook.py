"""Tests for the ``transform_interim_output`` plugin hook.

The hook fires inside ``run_agent._emit_interim_assistant_message`` just
before a discrete interim (mid-turn, pre-tool) assistant commentary message
is surfaced to the UI/chat. These interim messages are delivered BEFORE the
tool-calling loop completes, so they never pass through the per-turn
``transform_llm_output`` path (which fires only on the final response in
``turn_finalizer.py``). This hook is the seam a cosmetic output filter uses
to reach that interim delivery surface.

Driving the full agent loop from a unit test is heavy, so these tests
exercise the invoke_hook dispatch semantics the wiring depends on:

    for r in results:
        if isinstance(r, str) and r:
            visible = r   # First non-empty string wins
            break
    # fail-safe: any error leaves the interim text unchanged

Mirrors ``test_transform_gateway_notice_hook.py`` and
``test_transform_llm_output_hook.py``.
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


def test_transform_interim_output_in_valid_hooks():
    assert "transform_interim_output" in VALID_HOOKS


def test_interim_hook_receives_expected_kwargs(tmp_path, monkeypatch):
    """Hook callback should see response_text + session_id + model + platform.

    These are the exact kwargs run_agent._emit_interim_assistant_message
    dispatches, matching the transform_llm_output contract so one plugin
    callback can serve both surfaces.
    """
    hermes_home = tmp_path / "hermes_test"
    hermes_home.mkdir(exist_ok=True)
    _make_enabled_plugin(
        hermes_home, "capture_interim",
        register_body=(
            'ctx.register_hook("transform_interim_output", '
            'lambda **kw: '
            '"|".join([kw["response_text"], kw["session_id"], '
            'kw["model"], kw["platform"]]))'
        ),
    )
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    mgr = PluginManager()
    mgr.discover_and_load()

    results = mgr.invoke_hook(
        "transform_interim_output",
        response_text="Stand by — running a board check.",
        session_id="sess-1",
        model="claude-opus",
        platform="matrix",
    )
    assert results == [
        "Stand by — running a board check.|sess-1|claude-opus|matrix"
    ]


def test_interim_first_non_empty_string_wins(tmp_path, monkeypatch):
    """A plugin returning None must not suppress a later plugin's string."""
    hermes_home = tmp_path / "hermes_test"
    hermes_home.mkdir(exist_ok=True)
    # Plugin A returns None (declines); plugin B returns a replacement.
    _make_enabled_plugin(
        hermes_home, "interim_decline",
        register_body='ctx.register_hook("transform_interim_output", lambda **kw: None)',
    )
    _make_enabled_plugin(
        hermes_home, "interim_rewrite",
        register_body='ctx.register_hook("transform_interim_output", lambda **kw: "REWRITTEN")',
    )
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    mgr = PluginManager()
    mgr.discover_and_load()

    results = mgr.invoke_hook(
        "transform_interim_output",
        response_text="original",
        session_id="s",
        model="m",
        platform="cli",
    )
    # Dispatch returns every plugin's result; the consumer (run_agent) picks
    # the first non-empty string. Assert that selection rule holds.
    picked = next((r for r in results if isinstance(r, str) and r), "original")
    assert picked == "REWRITTEN"
