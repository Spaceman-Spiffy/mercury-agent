#!/usr/bin/env python3
"""Hermes Agent CLI — interactive terminal interface (``python cli.py --help`` for usage)."""

# Must be the very first import (UTF-8 stdio on Windows). Missing only mid-``hermes update``.
try:
    import hermes_bootstrap  # noqa: F401
except ModuleNotFoundError as exc:
    if exc.name != "hermes_bootstrap":
        raise  # the bootstrap exists but cannot load: skipping it would skip PM activation

import logging
import os
import functools
import shutil  # noqa: F401 — tests patch shutil/time through the cli facade
import sys
import re
import atexit
import errno
import time  # noqa: F401 — see shutil
from collections import deque
from dataclasses import dataclass
from contextlib import contextmanager, suppress
from pathlib import Path
from datetime import datetime  # noqa: F401 — siblings import it lazily through cli
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

os.environ["HERMES_QUIET"] = "1"  # suppress our modules' startup chatter


from hermes_cli.cli_agent_setup_mixin import CLIAgentSetupMixin
from hermes_cli.cli_commands_mixin import CLICommandsMixin
from hermes_cli.cli_billing_mixin import CLIBillingMixin
from hermes_cli.cli_loops_mixin import CLILoopsMixin
from hermes_cli.cli_info_mixin import CLIInfoMixin
from hermes_cli.cli_terminal_mixin import CLITerminalMixin
from hermes_cli.cli_modal_mixin import CLIModalMixin
from hermes_cli.cli_stream_mixin import CLIStreamMixin
from hermes_cli.cli_session_mixin import CLISessionMixin
from hermes_cli.cli_model_switch_mixin import CLIModelSwitchMixin
from hermes_cli.cli_voice_mixin import CLIVoiceMixin
from hermes_cli.cli_status_bar_mixin import CLIStatusBarMixin
from hermes_cli.cli_tui_mixin import CLITuiMixin
from hermes_cli.cli_process_notifications import CLIProcessNotificationsMixin
from hermes_cli.cli_init_mixin import CLIInitMixin
from hermes_cli.cli_tui_runtime_mixin import CLITuiRuntimeMixin
# Extracted clusters (mechanical split, #116911); re-exported here so `cli.<name>` stays the seam.
from hermes_cli.cli_shutdown import (  # noqa: F401,E402
    _CLEANUP_STEPS,
    _arm_exit_watchdog,
    _emit_interrupted_session_end,
    _exit_watchdog_timeout,
    _finalize_single_query,
    _float_env,
    _flush_logging_and_stdio,
    _flush_one_shot_session_store,
    _interrupt_async_delegations,
    _invoke_interrupted_session_end,
    _notify_session_finalize,
    _notify_single_query_session_finalize,
    _oneshot_agent_and_session,
    _should_emit_cleanup_session_finalize,
    _shutdown_agent_memory_provider,
    _shutdown_cached_aux_clients,
    _shutdown_mcp_servers,
    _stop_cli_wake_word,
    _sync_process_session_id,
    _wait_for_oneshot_background_completions,
)
from hermes_cli.cli_auto_maintenance import (  # noqa: F401,E402
    _run_checkpoint_auto_maintenance,
    _run_state_db_auto_maintenance,
)
from hermes_cli.cli_render import (  # noqa: F401,E402
    ChatConsole,
    _ACCENT,
    _ACCENT_ANSI_DEFAULT,
    _BOLD,
    _DA1_REPLY_RE,
    _DIM,
    _FALSE_RE,
    _LIGHT_DEFAULT_TERM_PROGRAMS,
    _LIGHT_MODE_REMAP,
    _LIGHT_MODE_REMAP_UPPER,
    _REASONING_TAGS,
    _RST,
    _STREAM_PAD,
    _STREAM_PARTIAL_PREVIEW_LEN,
    _SkinAwareAnsi,
    _TOOL_CALL_TAGS,
    _TRUE_RE,
    _WINDOWS_PATH_WITH_DOT_SEGMENT_RE,
    _accent_hex,
    _add_suspect_rows,
    _append_blank_panel_line,
    _append_panel_line,
    _assistant_content_as_text,
    _assistant_copy_text,
    _b,
    _build_compact_banner,
    _clear_output_history,
    _cli_visible_print,
    _coerce_output_history_limit,
    _cprint,
    _d,
    _detect_light_mode_uncached,
    _heal_cooked_mode_drift,
    _hex_to_ansi,
    _install_skin_light_mode_hook,
    _line_rows,
    _luminance_from_hex,
    _maybe_remap_for_light_mode,
    _output_history_lines,
    _output_history_recording,
    _output_history_rows,
    _output_tail_fitting,
    _painted_columns,
    _PaintedLine,
    _panel_box_width,
    _post_stream_transform_output,
    _prepend_note_to_message,
    _preserve_windows_dot_segments_for_markdown,
    _pt_app_is_running,
    _pt_print_ansi,
    _query_osc11_background,
    _record_output_history,
    _record_output_history_entry,
    _release_paints,
    _render_final_assistant_content,
    _rich_text_from_ansi,
    _set_chrome_floor,
    _strip_markdown_syntax,
    _strip_reasoning_tags,
    _terminal_columns,
    _terminal_reflows,
    _terminal_width_for_streaming,
    _tty_wrap,
    _wrap_panel_text,
    _wrap_panel_text_keep_ws,
)
from hermes_cli.cli_config_load import (  # noqa: F401,E402
    _AUXILIARY_TASK_ENV,
    _CWD_PLACEHOLDERS,
    _TERMINAL_ENV_MAPPINGS,
    _cli_config_defaults,
    _init_logging_and_display_from_config,
    _load_prefill_messages,
    _merge_file_config,
    _mirror_config_to_env,
    _parse_reasoning_config,
    _parse_service_tier_config,
    _resolve_prefill_messages_file,
    load_cli_config,
)
from hermes_cli.cli_terminal_input import (  # noqa: F401,E402
    _BACKSLASH_LINE_CONTINUATION_RE,
    _DSR_CPR_ESC_RE,
    _DSR_CPR_VISIBLE_RE,
    _EXTENDED_ENTER_KEYS_SEQ,
    _IMAGE_EXTENSIONS,
    _KITTY_KEYBOARD_PUSH_SEQ,
    _MODIFY_OTHER_KEYS_SEQ,
    _SGR_MOUSE_BARE_RE,
    _SGR_MOUSE_ESC_RE,
    _SGR_MOUSE_VISIBLE_RE,
    _TERMINAL_INPUT_MODE_RESET_SEQ,
    _apply_backslash_line_continuation,
    _apply_bracketed_paste_timeout_patch,
    _bind_prompt_submit_keys,
    _build_cpr_disabled_output,
    _cli_multiline_shortcuts_enabled,
    _collect_query_images,
    _detect_file_drop,
    _disable_prompt_toolkit_cpr_warning,
    _enable_extended_enter_keys,
    _estimate_tui_input_height,
    _file_drop_result,
    _format_image_attachment_badges,
    _hermes_call_output_screen_diff,
    _is_backslash_line_continuation,
    _is_ghostty_terminal,
    _preserve_ctrl_enter_newline,
    _resolve_attachment_path,
    _select_classic_cli_pt_output,
    _should_auto_attach_clipboard_image_on_paste,
    _split_path_input,
    _status_bar_visible_from_display_config,
    _strip_leaked_terminal_responses_with_meta,
    _terminal_may_leak_cpr,
    _terminal_supports_extended_enter_keys,
    _termux_example_image_path,
)
from hermes_cli.cli_single_query import (  # noqa: F401,E402
    _TERMINAL_PROVIDER_REASONS,
    _TRANSIENT_PROVIDER_REASONS,
    _collect_kanban_task_images,
    _configure_quiet_agent,
    _install_single_query_signal_handlers,
    _int_or,
    _interrupt_agent_for_signal,
    _route_single_query_images,
    _run_kanban_goal_loop_chat,
    _run_kanban_goal_loop_q,
    _run_quiet_single_query,
    _run_single_query_mode,
    _single_query_exit_code,
    _sync_cli_session_id_from_agent,
)

try:
    from prompt_toolkit.patch_stdout import patch_stdout
except ImportError:  # partial/broken prompt_toolkit (#96075); sole use is a `with patch_stdout():`
    from contextlib import nullcontext as patch_stdout
try:
    from prompt_toolkit.enums import EditingMode
except ImportError:  # partial prompt_toolkit stubs in tests
    EditingMode = None
from prompt_toolkit import print_formatted_text as _pt_print
from prompt_toolkit.formatted_text import ANSI as _PT_ANSI
try:
    from prompt_toolkit.cursor_shapes import CursorShape
    _STEADY_CURSOR = CursorShape.BLOCK
except (ImportError, AttributeError):
    _STEADY_CURSOR = None

try:
    from hermes_cli import pt_input_extras as _pt_extras

    _pt_extras.install_shift_enter_alias()
    _pt_extras.install_ctrl_enter_alias()
    _pt_extras.install_cmd_backspace_alias()
    _pt_extras.install_modify_other_keys_aliases()
    _pt_extras.install_keypress_data_normalization()
    _pt_extras.install_ignored_terminal_sequences()
    del _pt_extras
except Exception:
    pass
import threading
import queue


def _lazy_shim(module: str, name: str, alias: str | None = None):
    """Import ``module.name`` on first call; keeps heavy imports off startup while ``cli.<name>`` stays patchable."""
    import importlib

    def shim(*args, **kwargs):
        return getattr(importlib.import_module(module), name)(*args, **kwargs)

    shim.__name__ = shim.__qualname__ = alias or name
    return shim


def format_duration_compact(*args, **kwargs):
    seconds = float(args[0] if args else kwargs.get("seconds", 0.0))
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.0f}m"
    hours = minutes / 60
    if hours < 24:
        remaining_min = int(minutes % 60)
        return f"{int(hours)}h {remaining_min}m" if remaining_min else f"{int(hours)}h"
    days = hours / 24
    return f"{days:.1f}d"


# model id -> shortest configured alias (process-lifetime cache; config is read once).
_REVERSE_ALIAS_CACHE: dict[str, str] | None = None


def _reverse_alias_for_display(model_name: str) -> str:
    """Shortest alias for ``model_name`` from ``model_aliases:`` or ``model.aliases:``, else ``model_name``."""
    global _REVERSE_ALIAS_CACHE
    if not model_name:
        return model_name
    if _REVERSE_ALIAS_CACHE is None:
        rmap: dict[str, str] = {}

        def _put(m: str, alias: str) -> None:
            if m and (m not in rmap or len(alias) < len(rmap[m])):
                rmap[m] = alias

        try:
            from hermes_cli.config import load_config
            cfg = load_config() or {}
            ma = cfg.get("model_aliases")
            if isinstance(ma, dict):
                for alias, entry in ma.items():
                    if isinstance(entry, dict):
                        _put(str(entry.get("model", "") or "").strip(), alias)
            mdl = cfg.get("model", {}) or {}
            if isinstance(mdl, dict):
                simple = mdl.get("aliases")
                if isinstance(simple, dict):
                    for alias, val in simple.items():
                        if isinstance(val, str) and val.strip():
                            v = val.strip()
                            _put(v.split("/", 1)[1] if "/" in v else v, alias)
        except Exception:
            pass
        _REVERSE_ALIAS_CACHE = rmap
    return _REVERSE_ALIAS_CACHE.get(model_name, model_name)


def format_token_count_compact(*args, **kwargs):
    value = int(args[0] if args else kwargs.get("value", 0))
    abs_value = abs(value)
    if abs_value < 1_000:
        return str(value)

    sign = "-" if value < 0 else ""
    units = ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K"))
    for threshold, suffix in units:
        if abs_value >= threshold:
            scaled = abs_value / threshold
            text = f"{scaled:.{2 if scaled < 10 else 1 if scaled < 100 else 0}f}"
            if "." in text:
                text = text.rstrip("0").rstrip(".")
            return f"{sign}{text}{suffix}"

    return f"{value:,}"


realign_markdown_tables = _lazy_shim("agent.markdown_tables", "realign_markdown_tables")

_COMMAND_SPINNER_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")


# ~/.hermes/.env first, project .env as dev fallback; user env files override stale shell exports.
from hermes_constants import get_hermes_home
from hermes_cli.env_loader import load_hermes_dotenv
from agent.i18n import t as _t  # noqa: E402

_hermes_home = get_hermes_home()
_project_env = Path(__file__).parent / '.env'
load_hermes_dotenv(hermes_home=_hermes_home, project_env=_project_env)


CLI_CONFIG = load_cli_config()


_init_logging_and_display_from_config()

# Neuter AsyncHttpxClientWrapper.__del__ before any AsyncOpenAI client exists: it
# schedules aclose() on the running loop (prompt_toolkit's, during idle), closing
# transports bound to dead worker loops ("Event loop is closed" / "Press ENTER to
# continue..."). A meta_path finder patches ``openai._base_client`` at first import —
# eager import costs ~166ms/30MB cold, and the patch is guaranteed to land before
# instantiation. See ``agent.auxiliary_client.neuter_async_httpx_del``.
try:
    import sys as _httpx_neuter_sys
    import importlib.util as _httpx_neuter_imp_util

    class _AsyncHttpxDelNeuter:
        """Patch ``AsyncHttpxClientWrapper.__del__`` to a no-op when ``openai._base_client`` loads."""

        _armed = True

        def find_spec(self, fullname, path=None, target=None):
            if not self._armed or fullname != "openai._base_client":
                return None
            # Disarm before delegating so the recursive find_spec doesn't loop through us.
            self._armed = False
            try:
                _httpx_neuter_sys.meta_path.remove(self)
            except ValueError:
                pass
            spec = _httpx_neuter_imp_util.find_spec(fullname)
            if spec is None or spec.loader is None:
                return None
            _orig_exec = spec.loader.exec_module

            def _patched_exec(module):
                _orig_exec(module)
                try:
                    cls = getattr(module, "AsyncHttpxClientWrapper", None)
                    if cls is not None:
                        cls.__del__ = lambda self: None  # type: ignore[assignment]
                except Exception:
                    pass

            spec.loader.exec_module = _patched_exec  # type: ignore[method-assign]
            return spec

    _httpx_neuter_sys.meta_path.insert(0, _AsyncHttpxDelNeuter())
except Exception:
    pass


# Agent/tool systems load lazily: bare startup only needs the prompt.
def get_tool_definitions(*args, **kwargs):
    from hermes_cli.mcp_startup import wait_for_mcp_discovery
    from model_tools import get_tool_definitions as _get_tool_definitions

    wait_for_mcp_discovery()
    return _get_tool_definitions(*args, **kwargs)


validate_toolset = _lazy_shim("toolsets", "validate_toolset")


_cleanup_all_terminals = _lazy_shim("tools.terminal_tool", "cleanup_all_environments", "_cleanup_all_terminals")
set_sudo_password_callback = _lazy_shim("tools.terminal_tool", "set_sudo_password_callback")
set_approval_callback = _lazy_shim("tools.terminal_tool", "set_approval_callback")
set_secret_capture_callback = _lazy_shim("tools.skills_tool", "set_secret_capture_callback")
_cleanup_all_browsers = _lazy_shim("tools.browser_tool_lifecycle", "_emergency_cleanup_all_sessions", "_cleanup_all_browsers")

_cleanup_done = False  # _run_cleanup runs exactly once
_cleanup_in_progress = False
_cli_wake_owner = None
# One-shot finalization runs before process cleanup (plugins see the boundary while the
# agent is attached); atexit cleanup must not finalize those sessions again.
_single_query_finalize_attempted_session_ids: set[str | None] = set()
# /handoff sessions belong to the gateway: finalizing them here would stamp end_reason on
# a row the gateway just reopened, making the handoff leg vanish from history.
# Session IDs that were handed off to the gateway via /handoff. The CLI process exits after a successful
# handoff, but the gateway now owns the session lifecycle — _run_cleanup must NOT call finalize_session on
# these, because doing so sets end_reason on a row the gateway just reopened and is actively writing to
# (#88234). The race made the handoff leg vanish from session history and broke session_search recall for
# the handed-off session.
_handed_off_session_ids: set[str | None] = set()
_active_agent_ref = None  # active AIAgent, for memory-provider shutdown at exit
_deferred_agent_startup_done = False
# Set once the TUI app starts (focus reporting + mouse tracking on); gates the on-exit
# terminal reset so non-TUI one-shot runs never emit codes for modes they never enabled.
_tui_input_modes_active = False


# Set True once the TUI's prompt_toolkit app starts (which enables focus reporting + mouse tracking). Gates
# the on-exit terminal reset so non-TUI one-shot CLI runs — which also register _run_cleanup via atexit —
# don't emit escape codes for modes they never enabled (#36823).
def _mark_tui_input_modes_active() -> None:
    """Record that the TUI app started, so _run_cleanup resets input modes."""
    global _tui_input_modes_active
    _tui_input_modes_active = True


def _prepare_deferred_agent_startup() -> None:
    """Run Termux-deferred agent discovery before the first real agent turn."""
    global _deferred_agent_startup_done
    if _deferred_agent_startup_done:
        return
    if os.environ.get("HERMES_DEFER_AGENT_STARTUP") != "1":
        return
    _deferred_agent_startup_done = True
    _accept_hooks = os.environ.get("HERMES_ACCEPT_HOOKS", "").lower() in {"1", "true", "yes", "on"}
    try:
        from hermes_cli.plugins import discover_plugins

        discover_plugins()
    except Exception:
        logger.warning("plugin discovery failed at deferred CLI startup", exc_info=True)
    try:
        from hermes_cli.mcp_startup import start_background_mcp_discovery

        start_background_mcp_discovery(logger=logger, thread_name="termux-cli-mcp-discovery")
    except Exception:
        logger.debug("MCP tool discovery failed at deferred CLI startup", exc_info=True)
    try:
        from agent.shell_hooks import register_from_config
        from agent.outbound_webhooks import register_from_config as register_outbound_webhooks
        from hermes_cli.config import load_config

        _hooks_cfg = load_config()
        register_from_config(_hooks_cfg, accept_hooks=_accept_hooks)
        register_outbound_webhooks(_hooks_cfg)
    except Exception:
        logger.debug("shell-hook registration failed at deferred CLI startup", exc_info=True)


_signal_watchdog_armed = False


def _arm_exit_watchdog_on_shutdown_signal() -> None:
    """Arm the exit backstop the moment a termination signal arrives (idempotent; never raises).

    The graceful unwind has wedge points BEFORE ``_run_cleanup`` arms its own watchdog
    (main thread in a syscall, prompt_toolkit teardown never returning). Leash is 2x
    the cleanup timeout so a progressing cleanup is never cut short. Never arm at
    startup: the timer exits unconditionally.

    SIGTERM/SIGHUP establish unambiguous shutdown intent, but the graceful path from signal →
    ``agent.interrupt()`` → ``app.exit()`` / ``KeyboardInterrupt`` → ``finally`` → ``_run_cleanup`` has
    several wedge points BEFORE ``_run_cleanup`` arms the normal watchdog: a main thread parked in a syscall
    that never observes the unwind, a prompt_toolkit teardown that never returns, or an agent worker
    blocking the ``finally``. When that happens the process has NO backstop and a "dead" CLI lingers
    (observed: ``hermes --tui`` alive ~47 min at 4% CPU after terminal close — the #65998 class).
    """
    global _signal_watchdog_armed
    if _signal_watchdog_armed:
        return
    _signal_watchdog_armed = True
    base = _exit_watchdog_timeout()
    if base <= 0:
        return  # explicitly disabled
    with suppress(Exception):  # never let the backstop break signal handling
        _arm_exit_watchdog(timeout_s=base * 2, from_signal=True)


def _run_cleanup(*, notify_session_finalize: bool = True):
    """Run resource cleanup exactly once."""
    global _cleanup_done, _cleanup_in_progress
    if _cleanup_done:
        return
    _cleanup_done = True
    _cleanup_in_progress = True

    try:
        _arm_exit_watchdog()
        # Reset terminal input modes FIRST: teardown below can take seconds and a later
        # step raising must not skip the reset. No-op unless the TUI ran.
        # See #36823.
        _reset_terminal_input_modes_on_exit()

        for step, swallow in _CLEANUP_STEPS:
            with suppress(swallow):
                globals()[step]()
        if notify_session_finalize:
            cleanup_session_id = _active_agent_ref.session_id if _active_agent_ref else None
            if _should_emit_cleanup_session_finalize(cleanup_session_id):
                _notify_session_finalize(session_id=cleanup_session_id, platform="cli", reason="shutdown")
        try:
            _shutdown_agent_memory_provider(_active_agent_ref)
        except Exception as e:
            logger.warning("CLI cleanup memory shutdown failed: %s", e, exc_info=True)
    finally:
        _cleanup_in_progress = False


def _reset_terminal_input_modes_on_exit() -> None:
    """Disable focus reporting + mouse tracking on TUI exit (best-effort).

    Ctrl+C / SIGTERM / crashes bypass prompt_toolkit's unwind, leaving focus events and
    mouse reports as visible text in the next shell. Writes to stdout when it is the
    terminal, else /dev/tty (the TUI may have run with stdout redirected).

    Called from ``_run_cleanup`` (atexit-registered + invoked on the normal / EOF / interrupt exit paths)
    this covers normal quit, Ctrl+C and SIGTERM/SIGHUP. ``kill -9`` is uncatchable, and the kanban worker's
    ``os._exit(0)`` path bypasses ``atexit``; neither runs this — but both are non-TTY / non-TUI, so there
    is nothing to reset there. See #36823.
    """
    global _tui_input_modes_active
    if not _tui_input_modes_active:
        return
    # Clear first so a re-armed _run_cleanup doesn't re-emit.
    _tui_input_modes_active = False
    try:
        stream = sys.stdout
        if stream is not None and stream.isatty():
            stream.write(_TERMINAL_INPUT_MODE_RESET_SEQ)
            stream.flush()
            return
    except Exception:
        pass
    with suppress(Exception), open("/dev/tty", "w", encoding="ascii") as tty:
        tty.write(_TERMINAL_INPUT_MODE_RESET_SEQ)
        tty.flush()


from hermes_cli.worktree_ops import (
    _git_quiet,
    _git_repo_root,
    _maintain_pack_health,
    _prune_stale_worktrees,
    _repo_is_shallow,
    _setup_worktree,
    _worktree_has_unpushed_commits,
    _worktree_is_dirty,
    release_lsp_clients,
)

# ============================================================================= Git Worktree Isolation
# (#652) =============================================================================
_active_worktree: Optional[Dict[str, str]] = None


def _cleanup_worktree(info: Dict[str, str] = None) -> None:
    """Remove a clean worktree and its branch on exit; preserve recoverable work."""
    global _active_worktree
    info = info or _active_worktree
    if not info:
        return

    wt_path, branch, repo_root = info["path"], info["branch"], info["repo_root"]
    if not Path(wt_path).exists():
        return
    _active_worktree = None

    if _worktree_is_dirty(wt_path, repo_root, timeout=10):
        # Uncommitted work: say so, and don't hint at `remove --force`, which would destroy it.
        _cprint(f"\n\033[33m{_t('cli.worktree.uncommitted_keeping', path=wt_path)}\033[0m")
        return

    if _worktree_has_unpushed_commits(wt_path, timeout=10):
        if _repo_is_shallow(repo_root):
            # Shallow boundary makes the unpushed verdict unreliable; the startup pruner reaps later.
            _cprint(f"\n\033[33m{_t('cli.worktree.shallow_clone_keeping', path=wt_path)}\033[0m")
            print(f"  {_t('cli.worktree.next_session_deepens')}")
        else:
            _cprint(f"\n\033[33m{_t('cli.worktree.unpushed_keeping', path=wt_path)}\033[0m")
            print(f"  {_t('cli.worktree.clean_up_manually', path=wt_path)}")
        return

    # Release the tree's language servers while the path still exists, then unlock so `remove`
    # isn't blocked by the lock placed at creation. Fail-soft.
    release_lsp_clients(wt_path)
    _git_quiet(["worktree", "unlock", wt_path], repo_root, log="git worktree unlock failed (non-fatal)")
    _git_quiet(["worktree", "remove", wt_path, "--force"], repo_root, timeout=15, log="Failed to remove worktree")
    _git_quiet(["branch", "-D", branch], repo_root, log=f"Failed to delete branch {branch}")
    _cprint(f"\033[32m{_t('cli.worktree.cleaned_up', path=wt_path)}\033[0m")


# Light/dark terminal detection (mirrors ui-tui/src/theme.ts detectLightMode()). Priority:
# HERMES_LIGHT/HERMES_TUI_LIGHT env, HERMES_TUI_THEME, HERMES_TUI_BACKGROUND, COLORFGBG
# (bg slot 7/15 = light), OSC 11 query, default dark. Cached so the terminal is queried once.
_LIGHT_MODE_CACHE: bool | None = None


def _detect_light_mode() -> bool:
    global _LIGHT_MODE_CACHE
    if _LIGHT_MODE_CACHE is not None:
        return _LIGHT_MODE_CACHE
    try:
        result = _detect_light_mode_uncached()
    except Exception:
        result = False
    _LIGHT_MODE_CACHE = result
    return result


_install_skin_light_mode_hook()


# Prime the light-mode cache when interactive so OSC 11 happens before prompt_toolkit owns the tty.
with suppress(Exception):
    if sys.stdin.isatty() and sys.stdout.isatty():
        _detect_light_mode()


_OUTPUT_HISTORY_ENABLED = True
_OUTPUT_HISTORY_REPLAYING = False
_OUTPUT_HISTORY_SUPPRESSED = False
_OUTPUT_HISTORY_MAX_LINES = 200
_OUTPUT_HISTORY = deque(maxlen=_OUTPUT_HISTORY_MAX_LINES)


def _configure_output_history(enabled: bool, max_lines=200) -> None:
    """Configure recent CLI output replayed after terminal redraws."""
    global _OUTPUT_HISTORY_ENABLED, _OUTPUT_HISTORY_MAX_LINES, _OUTPUT_HISTORY
    _OUTPUT_HISTORY_ENABLED = bool(enabled)
    _OUTPUT_HISTORY_MAX_LINES = _coerce_output_history_limit(max_lines)
    _OUTPUT_HISTORY = deque(maxlen=_OUTPUT_HISTORY_MAX_LINES)


@contextmanager
def _suspend_output_history():
    global _OUTPUT_HISTORY_SUPPRESSED
    old_value = _OUTPUT_HISTORY_SUPPRESSED
    _OUTPUT_HISTORY_SUPPRESSED = True
    try:
        yield
    finally:
        _OUTPUT_HISTORY_SUPPRESSED = old_value


def _replay_output_history(fit=None, output=None) -> None:
    """Repaint recent output above the prompt after a full screen clear.

    ``fit=(rows, columns, painted, top)`` replays only the newest lines whose wrapped height
    fits ``rows`` (see ``_output_tail_fitting``) — the older ones are still in scrollback
    (#95375) — from screen row ``top`` when known (``_set_chrome_floor``). ``output``: paint
    now, straight to this prompt_toolkit output, where the caller just erased the viewport and
    reset the renderer — ``run_in_terminal`` would first erase below the top row, which
    scroll-on-clear terminals (tmux) take as a clear and copy the blank screen into scrollback.
    """
    global _OUTPUT_HISTORY_REPLAYING
    if not _OUTPUT_HISTORY_ENABLED or not _OUTPUT_HISTORY:
        return
    _OUTPUT_HISTORY_REPLAYING = True
    try:
        rendered_lines = _output_history_lines()
        top = None
        if fit is not None:
            rows, columns, painted, top = fit
            rendered_lines = _output_tail_fitting(rendered_lines, rows, columns, painted)
        if rendered_lines:
            # One payload: per-line pt prints each force a sync redraw (a waterfall of old output).
            if output is None:
                _pt_print(_PT_ANSI("\n".join(rendered_lines)))
            else:
                from prompt_toolkit.renderer import print_formatted_text as _paint_formatted_text
                from prompt_toolkit.styles import Style
                _paint_formatted_text(output, _PT_ANSI("\n".join(rendered_lines) + "\n"), Style([]))
                size = output.get_size()
                if top is not None:  # the chrome's top is now this many rows down
                    top += sum(_line_rows(line, columns) for line in rendered_lines)
                    _set_chrome_floor(max(0, size.rows - top))
                    if size.columns != columns:
                        _add_suspect_rows(top + 1 - size.rows)
            width = _painted_columns() if fit is None else columns
            for line in rendered_lines:  # repainted: they wrap at today's width from now on
                if isinstance(line, _PaintedLine):
                    line.width = width
    except Exception:
        pass
    finally:
        _OUTPUT_HISTORY_REPLAYING = False


_strip_leaked_bracketed_paste_wrappers = _lazy_shim(
    "hermes_cli.input_sanitize", "strip_leaked_bracketed_paste_wrappers", "_strip_leaked_bracketed_paste_wrappers"
)


# OSC sequences (e.g. OSC-8 links): pt's ANSI parser strips the ESC but leaks the payload as text.
_OSC_ESCAPE_RE = re.compile(r"\x1b\][\s\S]*?(?:\x07|\x1b\\)")


def _looks_like_slash_command(text: str) -> bool:
    """``/help`` yes, ``/Users/x/file.md`` no: a command's first word has no further ``/``."""
    if not text or not text.startswith("/"):
        return False
    return "/" not in text.split()[0][1:]


_skill_commands = None
_skill_bundles = None


def _slash_args(cmd: str) -> str:
    """Text after the slash-command word, stripped ("" when absent)."""
    parts = cmd.split(None, 1)
    return parts[1].strip() if len(parts) > 1 else ""


def _ensure_skill_commands() -> dict:
    global _skill_commands
    if _skill_commands is None:
        from agent.skill_commands import scan_skill_commands

        _skill_commands = scan_skill_commands()
    return _skill_commands


def get_skill_commands() -> dict:
    return _ensure_skill_commands()


build_skill_invocation_message = _lazy_shim("agent.skill_commands", "build_skill_invocation_message")
build_preloaded_skills_prompt = _lazy_shim("agent.skill_commands", "build_preloaded_skills_prompt")


def get_skill_bundles() -> dict:
    global _skill_bundles
    if _skill_bundles is None:
        from agent.skill_bundles import get_skill_bundles as _impl

        _skill_bundles = _impl()
    return _skill_bundles


build_bundle_invocation_message = _lazy_shim("agent.skill_bundles", "build_bundle_invocation_message")


def _get_plugin_cmd_handler_names() -> set:
    """Return plugin command names (without slash prefix) for dispatch matching."""
    try:
        from hermes_cli.plugins import get_plugin_commands
        return set(get_plugin_commands().keys())
    except Exception:
        return set()


def _parse_skills_argument(skills: str | list[str] | tuple[str, ...] | None) -> list[str]:
    """Normalize a CLI skills flag into a deduplicated list of skill identifiers."""
    if not skills:
        return []
    raw_values = [str(item) for item in skills if item is not None] if isinstance(skills, (list, tuple)) else [str(skills)]
    parts = (p.strip() for raw in raw_values for p in raw.split(","))
    return list(dict.fromkeys(p for p in parts if p))


def save_config_value(key_path: str, value: any) -> bool:
    """Persist dot-separated ``key_path`` = value into HERMES_HOME/config.yaml; True on success.

    Never the repo's cli-config.yaml: no config reader loads it, so the value would vanish.
    """
    config_path = get_hermes_home() / 'config.yaml'

    try:
        from hermes_constants import mkdir_under_hermes_home
        mkdir_under_hermes_home(config_path.parent)
        from utils import atomic_roundtrip_yaml_update
        atomic_roundtrip_yaml_update(config_path, key_path, value)
        try:  # owner-only: config files contain API keys
            os.chmod(config_path, 0o600)
        except (OSError, NotImplementedError):
            pass
        return True
    except Exception as e:
        logger.error("Failed to save config: %s", e)
        return False


def _normalize_moa_model(model: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """``moa:<preset>`` -> ``("moa", preset)`` (same routing as ``/moa``); anything else -> ``(None, model)``.

    Returns ``("moa", "<preset>")`` when *model* selects the MoA virtual provider, otherwise ``(None,
    model)`` unchanged. This gives non-interactive ``hermes chat -Q -m moa:<preset>`` the same routing the
    interactive ``/moa`` command and the model picker already use: ``resolve_runtime_provider`` handles
    ``requested_provider == "moa"`` and ``agent_init`` builds the MoAClient off ``provider == "moa"``.
    Without this the raw ``moa:<preset>`` string is sent to the real provider and rejected with a 401/400
    "model not supported" (#56828).
    """
    if isinstance(model, str) and model.strip().lower().startswith("moa:"):
        preset = model.strip().split(":", 1)[1].strip()
        if preset:
            return "moa", preset
    return None, model

_split_model_config_default = _lazy_shim("hermes_cli.config", "split_model_config_default", "_split_model_config_default")


class _VoiceInputMessage:
    """Sentinel for voice-transcribed input so the concise voice prefix never applies to typed text.

    Distinguishes STT output from manually typed text while voice mode is active, so the
    concise-voice-response prefix is applied only to messages that actually came from the microphone
    (#65827).
    """

    __slots__ = ("text",)

    def __init__(self, text: str):
        self.text = text

    def __str__(self) -> str:
        return self.text


class _SeededQueryMessage:
    """Sentinel for a ``-q`` prompt seeded into an interactive session; treated LITERALLY (no slash/!/file-drop)."""

    __slots__ = ("text", "images")

    def __init__(self, text: str, images=None):
        self.text = text or ""
        self.images = list(images or [])

    def __str__(self) -> str:
        return self.text


def _should_seed_interactive(query, image, quiet: bool, oneshot: bool) -> bool:
    """``-q`` seeds an interactive session only on a real TTY without ``--oneshot``/``-Q`` (automation answers and exits)."""
    if not (query or image) or oneshot or quiet:
        return False
    try:
        return bool(sys.stdin.isatty() and sys.stdout.isatty())
    except Exception:
        return False


@dataclass
class _ChatTurn:
    """Per-turn state shared by the ``chat()`` phases and the agent worker thread.

    ``result`` is written by the worker and read after the join; ``tts_normal_exit`` is
    set only when the TTS worker drained on its own so the last sentence is never cut.
    """

    result: Optional[dict] = None
    mute_notification_reply: bool = False
    use_streaming_tts: bool = False
    box_opened: bool = False
    thinking_started: bool = False
    text_queue: Optional[queue.Queue] = None
    tts_thread: Optional[threading.Thread] = None
    stream_callback: Optional[Any] = None
    stop_event: Optional[threading.Event] = None
    tts_normal_exit: bool = False
    voice_prefix: str = ""
from hermes_cli.cli_chat_turn_mixin import CLIChatTurnMixin


_PASTE_REF_RE = re.compile(r'\[Pasted text #\d+: \d+ lines \u2192 (.+?)\]')


class HermesCLI(CLIInitMixin, CLITuiRuntimeMixin, CLIProcessNotificationsMixin, CLIAgentSetupMixin, CLICommandsMixin, CLIBillingMixin, CLITuiMixin, CLIStatusBarMixin, CLIVoiceMixin, CLIModelSwitchMixin, CLISessionMixin, CLIStreamMixin, CLIModalMixin, CLITerminalMixin, CLIInfoMixin, CLILoopsMixin, CLIChatTurnMixin):
    """Interactive REPL for the Hermes Agent."""

    # Seeded -q first message (see _should_seed_interactive); run() re-creates
    # _pending_input, so it is enqueued only after the fresh queue exists.
    _seeded_first_message: Optional["_SeededQueryMessage"] = None
    # Inspection surfaces (banner, /tools, status line) read this on partially built instances too.
    disabled_toolsets: Optional[List[str]] = None

    def __init__(
        self,
        model: str = None,
        toolsets: List[str] = None,
        provider: str = None,
        reasoning: str = None,
        api_key: str = None,
        base_url: str = None,
        max_turns: int = None,
        run_budget: float = None,
        verbose: Optional[bool] = None,
        compact: bool = False,
        resume: str = None,
        checkpoints: bool = False,
        pass_session_id: bool = False,
        ignore_rules: bool = False,
    ):
        """CLI args win over config; ``reasoning`` is per-run only; ``resume`` restores history from SQLite."""
        self._init_display_options(verbose, compact)
        self._init_model_routing(model, toolsets, provider, reasoning, api_key, base_url, max_turns, run_budget,
                                 checkpoints, pass_session_id, ignore_rules)
        self._init_runtime_state(resume)


    def _claim_active_session(self, surface: str = "cli", *, stderr: bool = False) -> bool:
        """Claim a global active-session slot for this CLI process."""
        if self._active_session_lease is not None:
            return True
        try:
            from hermes_cli.active_sessions import format_refusal_stderr, try_acquire_active_session

            lease, message = try_acquire_active_session(
                session_id=self.session_id,
                surface=surface,
                config=self.config,
                # Writer identity: a re-claim by this process replaces its own entry.
                # See #94595.
                metadata={"live_session_id": str(self.session_id)},
            )
        except Exception as exc:
            logger.warning("Failed to claim active session slot: %s", exc)
            return True
        if message:
            print(format_refusal_stderr(message), file=sys.stderr) if stderr else self._console_print(f"[bold red]{message}[/]")
            return False
        self._active_session_lease = lease
        with suppress(Exception):
            atexit.register(self._release_active_session)
        return True

    def _release_active_session(self) -> None:
        lease = getattr(self, "_active_session_lease", None)
        if lease is None:
            return
        try:
            lease.release()
        except Exception:
            logger.debug("Failed to release active session slot", exc_info=True)
        finally:
            self._active_session_lease = None

    _PET_FRAME_INTERVAL = 0.16
    _PET_CFG_INTERVAL = 2.5

    def _install_tool_callbacks(self) -> None:
        """Install tool callbacks that need the live prompt UI."""
        if self._tool_callbacks_installed:
            return
        set_sudo_password_callback(self._sudo_password_callback)
        set_approval_callback(self._approval_callback)
        set_secret_capture_callback(self._secret_capture_callback)
        from agent.vault_backends.unlock import set_code_prompt_callback, set_save_login_prompt_callback, set_unlock_prompt_callback
        set_unlock_prompt_callback(self._vault_unlock_callback)
        set_save_login_prompt_callback(self._vault_save_login_callback)
        set_code_prompt_callback(self._vault_code_callback)
        self._tool_callbacks_installed = True

    def _ensure_tirith_security(self) -> None:
        """Check tirith availability once before tools can run terminal commands."""
        if self._tirith_security_checked:
            return
        self._tirith_security_checked = True
        try:
            from tools.tirith_security import ensure_installed, is_platform_supported, missing_is_expected

            if (
                ensure_installed(log_failures=False) is None and is_platform_supported()
                and (self.config.get("security", {}) or {}).get("tirith_enabled", True)
            ):
                # First launch after install downloads tirith in the background;
                # warning then would report a fault that resolves itself.
                if missing_is_expected():
                    logger.info("tirith not ready (downloading or lazy installs off); pattern matching only")
                else:
                    _cprint(f"  {_DIM}{_t('cli.startup.tirith_unavailable')}{_RST}")
        except Exception as exc:
            logger.debug("tirith availability check failed: %s", exc)

    def _show_security_advisories(self):
        """Startup banner for unacked security advisories, on stderr (piped stdout stays clean); 24h rate-limited."""
        try:
            from hermes_cli.security_advisories import detect_compromised, startup_banner

            banner = startup_banner(detect_compromised())
            if banner:
                print(banner, file=sys.stderr, flush=True)
        except Exception:
            pass  # never block startup

    def _show_browser_backend_notice(self):
        """Once-per-24h hint when the default Browser Use backend silently fell back to built-in tools."""
        try:
            from tools.browser_use_cli import default_downgrade_notice

            notice = default_downgrade_notice()
            if notice:
                from gateway.warning_notifications import render_notification
                render_notification(lambda: self._console_print(f"[yellow]⚠ {notice}[/yellow]"), platform="cli")
        except Exception:
            logger.debug("browser backend notice failed", exc_info=True)

    def finalize_preloaded_skills(self) -> None:
        """Join the background --skills preload and fold it into the prompt (idempotent).

        Raises ``ValueError`` only when EVERY requested skill was unknown.
        """
        if getattr(self, "_preload_skills_finalized", False):
            return
        thread = getattr(self, "_preload_skills_thread", None)
        if thread is None:
            self._preload_skills_finalized = True
            return
        thread.join(timeout=120)
        self._preload_skills_finalized = True
        err = getattr(self, "_preload_skills_error", None)
        if err is not None:
            raise err
        auto_result = getattr(self, "_auto_load_skills_result", None)
        if auto_result and auto_result[2]:
            logger.warning("skills.auto_load: skill(s) not found or disabled, skipped: %s", ", ".join(auto_result[2]))
        # auto_load names first, then explicit -s names that were not already pinned.
        self.preloaded_skills = list(auto_result[1]) if auto_result else []
        result = getattr(self, "_preload_skills_result", None)
        if not result:
            return
        skills_prompt, loaded_skills, missing_skills = result
        if missing_skills:
            missing_display = ", ".join(missing_skills)
            # A typo'd name must not crash a kanban worker; only a fully-missing set fails loudly.
            if loaded_skills:
                logger.warning(
                    "Unknown skill(s) requested, skipping: %s. "
                    "Continuing with: %s. "
                    "List available skills with `hermes skills list`.",
                    missing_display,
                    ", ".join(loaded_skills),
                )
            else:
                raise ValueError(f"Unknown skill(s): {missing_display}")
        if skills_prompt:
            self.system_prompt = "\n\n".join(p for p in (self.system_prompt, skills_prompt) if p).strip()
        self.preloaded_skills += [name for name in loaded_skills if name not in self.preloaded_skills]

    def _show_tool_availability_warnings(self):
        """Warn about toolsets switched off at startup (missing API keys, unusable terminal backend)."""
        try:
            # Runs on a daemon thread on the snapshot fast path: keep the imports to modules the
            # registry walk already loaded plus the pure notices module (a heavy import here races
            # importlib's module locks against the main thread).
            from model_tools import check_tool_availability
            from hermes_cli.tool_availability_notices import (
                current_terminal_backend, filter_to_enabled_toolsets, tool_availability_warning_lines,
            )
            from tools.terminal_tool import terminal_backend_unavailable_reason
            from toolsets import resolve_toolset

            _, unavailable = check_tool_availability()
            # Only toolsets this CLI session actually has. The selection is usually a composite bundle
            # (``hermes-cli``), so expand it to tool names before matching — a raw name comparison
            # matched nothing on a default install and silently dropped the terminal notice.
            unavailable = filter_to_enabled_toolsets(unavailable, self.enabled_toolsets or [], resolve_toolset)
            lines = tool_availability_warning_lines(
                unavailable, terminal_reason=terminal_backend_unavailable_reason(),
                terminal_backend=current_terminal_backend())
            if lines:
                self._console_print()
                for line in lines:
                    self._console_print(line)
        except Exception:
            pass

    def show_config(self):
        """Display current configuration with kawaii ASCII art."""
        terminal_env = os.getenv("TERMINAL_ENV", "local")
        terminal_cwd = os.getenv("TERMINAL_CWD", os.getcwd())
        terminal_timeout = os.getenv("TERMINAL_TIMEOUT", "60")

        config_path = _hermes_home / 'config.yaml'
        if not config_path.exists():
            config_path = Path(__file__).parent / 'cli-config.yaml'
        config_status = _t("cli.config.loaded") if config_path.exists() else _t("cli.config.not_found")

        # ``api_key`` may be a callable (Entra ID bearer provider): never invoke it. Prefer the
        # LIVE agent's key: the constructor seeds self.api_key from env before provider
        # resolution, so on non-OpenAI providers it can be another vendor's key.
        from agent.azure_identity_adapter import is_token_provider

        display_key = self.api_key
        if self.agent is not None and getattr(self.agent, "api_key", None):
            display_key = self.agent.api_key
        if is_token_provider(display_key):
            api_key_display = _t("cli.config.microsoft_entra_id")
        elif isinstance(display_key, str) and len(display_key) > 12:
            api_key_display = f"{display_key[:8]}...{display_key[-4:]}"
        else:
            api_key_display = _t("cli.config.api_key_not_set")

        title = _t("cli.config.title")
        width = 50
        pad = width - len(title)
        _unset = _t("cli.config.value_not_set")
        ssh_target = (
            f"{os.getenv('TERMINAL_SSH_USER', _unset)}@{os.getenv('TERMINAL_SSH_HOST', _unset)}"
            f":{os.getenv('TERMINAL_SSH_PORT', '22')}"
        ) if terminal_env == "ssh" else None
        # (section key, ((label key, value), ...)); labels are re-padded at print time so
        # translated widths still line up instead of carrying alignment spaces in the catalog.
        sections = (
            ("cli.config.section_model", (
                ("cli.config.label_model", self.model),
                ("cli.config.label_base_url", self.base_url),
                ("cli.config.label_api_key", api_key_display))),
            ("cli.config.section_terminal", (
                ("cli.config.label_environment", terminal_env),
                *((("cli.config.label_ssh_target", ssh_target),) if ssh_target else ()),
                ("cli.config.label_working_dir", terminal_cwd),
                ("cli.config.label_timeout", f"{terminal_timeout}s"),
            )),
            ("cli.config.section_agent", (
                ("cli.config.label_max_turns", self.max_turns),
                ("cli.config.label_toolsets", ", ".join(self.enabled_toolsets) if self.enabled_toolsets else "all"),
                ("cli.config.label_verbose", self.verbose),
            )),
            ("cli.config.section_session", (
                ("cli.config.label_started", self.session_start.strftime("%Y-%m-%d %H:%M:%S")),
                ("cli.config.label_config_file", f"{config_path} {config_status}"),
            )),
        )
        print()
        print("+" + "-" * width + "+")
        print("|" + " " * (pad // 2) + title + " " * (pad - pad // 2) + "|")
        print("+" + "-" * width + "+")
        for section_key, rows in sections:
            print()
            print(f"  -- {_t(section_key)} --")
            label_width = max(len(_t(label_key)) for label_key, _ in rows)
            for label_key, value in rows:
                print(f"  {_t(label_key):<{label_width}} {value}")
        print()

    # canonical command -> (method name, pass cmd_original?). Absent commands resolve to
    # ``_handle_<name>_command(cmd)``. Looked up via getattr at dispatch time so
    # monkeypatching works. A handler returning False exits the REPL.
    _SLASH_DISPATCH: dict[str, tuple[str, bool]] = {
        "exit": ("_cmd_exit", True), "quit": ("_cmd_exit", True), "help": ("_cmd_help", True),
        "palette": ("_open_command_palette", False), "whoami": ("_handle_whoami_command", False),
        "profile": ("_handle_profile_command", False), "toolsets": ("show_toolsets", False),
        "config": ("show_config", False), "redraw": ("_cmd_redraw", True), "clear": ("_cmd_clear", True),
        "history": ("show_history", False), "title": ("_cmd_title", True), "new": ("_cmd_new", True),
        "model": ("_handle_model_switch", True), "codex-runtime": ("_handle_codex_runtime", True),
        "retry": ("_cmd_retry", True), "prompt": ("_handle_prompt_compose_command", True),
        "undo": ("_cmd_undo", True), "save": ("save_conversation", True), "skills": ("_cmd_skills", True),
        "platforms": ("_show_gateway_status", False), "status": ("_show_session_status", False),
        "context": ("_show_context_breakdown", True), "egress": ("_cmd_egress", True),
        "statusbar": ("_cmd_statusbar", True), "verbose": ("_toggle_verbose", False), "yolo": ("_toggle_yolo", False),
        "compress": ("_manual_compress", True), "subscription": ("_show_subscription", False),
        "topup": ("_show_billing", True), "insights": ("_show_insights", True), "update": ("_cmd_update", True),
        "version": ("_cmd_version", True), "paste": ("_handle_paste_command", False), "reload": ("_cmd_reload", True),
        "reload-mcp": ("_confirm_and_reload_mcp", True), "reload-skills": ("_cmd_reload_skills", True),
        "plugins": ("_cmd_plugins", True), "stop": ("_handle_stop_command", False),
        "agents": ("_handle_agents_command", False), "bg": ("_handle_background_command", True),
        "queue": ("_cmd_queue", True), "steer": ("_cmd_steer", True), "moa": ("_cmd_moa", True),
    }

    @classmethod
    def _slash_handler(cls, canonical: str) -> tuple[str, bool] | None:
        """(method name, pass cmd_original?) for a registered command, else None."""
        entry = cls._SLASH_DISPATCH.get(canonical)
        if entry is None:
            name = f"_handle_{canonical.replace('-', '_')}_command"
            if callable(getattr(cls, name, None)):
                entry = (name, True)
        return entry

    # Shared-metrics surface for user-typed commands; None where another process owns the count
    # (the TUI slash worker: tui_gateway records the command it forwards).
    _slash_metrics_surface: str | None = "cli"

    def process_command(self, command: str, *, redispatch: bool = False) -> bool:
        """Dispatch a slash command; returns False to exit the REPL. ``redispatch`` marks an internal
        re-entry (quick-command alias, prefix expansion) so the user's command is counted once."""
        cmd_lower = command.lower().strip()  # lowercase only for matching; args keep their case
        cmd_original = command.strip()

        # Aliases resolve via the central registry (hermes_cli/commands.py).
        from hermes_cli.commands import resolve_command as _resolve_cmd
        _base_word = cmd_lower.split()[0].lstrip("/")
        _cmd_def = _resolve_cmd(_base_word)
        canonical = _cmd_def.name if _cmd_def else _base_word
        if not redispatch and self._slash_metrics_surface:
            from hermes_cli.observability.shared_metrics_events import record_slash_command
            record_slash_command(command=canonical, surface=self._slash_metrics_surface)

        # Observer-only pre_command plugin hook (return values ignored; never raises).
        if _cmd_def is not None:
            from hermes_cli.plugins import fire_pre_command_hook
            fire_pre_command_hook(
                surface="cli", command=canonical, alias_used=_base_word, args_raw=_slash_args(cmd_original),
                session_key=getattr(self, "session_id", None), platform="cli",
            )

        # A bare `/resume` prompt is one-shot: any other command disarms it so a later
        # number isn't swallowed as a stale selection.
        # See #34584.
        if canonical not in {"resume", "sessions"}:
            # Armed when a bare `/resume` prints the recent-sessions list so the very next bare numeric
            # input (e.g. `3`) resolves to that session. Holds the exact list used for index resolution;
            # one-shot (cleared on the next submitted input, whether it's the selection or anything else).
            # See #34584.
            self._pending_resume_sessions = None

        entry = self._slash_handler(canonical)
        if entry is None:
            return self._process_unregistered_slash(cmd_original, cmd_lower)
        method_name, pass_arg = entry
        handler = getattr(self, method_name)
        result = handler(cmd_original) if pass_arg else handler()
        return result is not False

    def _process_unregistered_slash(self, cmd_original: str, cmd_lower: str) -> bool:
        """Slash input with no built-in handler; precedence: quick_commands -> plugins -> bundles -> skills -> prefix expansion."""
        base_cmd = cmd_lower.split()[0]
        bare = base_cmd.lstrip("/")
        skill_commands = _ensure_skill_commands()
        skill_bundles = get_skill_bundles()
        quick_commands = self.config.get("quick_commands", {})
        user_args = cmd_original[len(base_cmd):].strip()
        if bare in quick_commands:
            return self._run_quick_command(base_cmd, quick_commands[bare], user_args)
        if bare in _get_plugin_cmd_handler_names():
            self._run_plugin_slash_command(base_cmd, user_args)
        elif base_cmd in skill_bundles:
            self._run_skill_bundle_command(base_cmd, skill_bundles[base_cmd], user_args)
        elif base_cmd in skill_commands:
            self._run_skill_slash_command(base_cmd, skill_commands[base_cmd], user_args)
        else:
            return self._expand_slash_prefix(cmd_original, cmd_lower, skill_commands, skill_bundles)
        return True

    def _run_quick_command(self, base_cmd: str, qcmd: dict, user_args: str) -> bool:
        """User-defined quick command (config.yaml): ``exec`` runs a shell snippet, ``alias`` re-dispatches."""
        qtype = qcmd.get("type")
        if qtype == "alias":
            target = qcmd.get("target", "").strip()
            if target:
                target = target if target.startswith("/") else f"/{target}"
                return self.process_command(f"{target} {user_args}".strip(), redispatch=True)
            self._console_print(f"[bold red]{_t('cli.quick.no_target', command=base_cmd)}[/]")
            return True
        if qtype != "exec":
            self._console_print(f"[bold red]{_t('cli.quick.unsupported_type', command=base_cmd)}[/]")
            return True
        import subprocess
        exec_cmd = qcmd.get("command", "")
        if not exec_cmd:
            self._console_print(f"[bold red]{_t('cli.quick.no_command', command=base_cmd)}[/]")
            return True
        try:
            # shell=True is intentional (user-authored config snippets, never LLM controlled);
            # the env is sanitized because this process holds every API key.
            from tools.environments.local import build_subprocess_env
            from hermes_cli._subprocess_compat import windows_hide_flags
            result = subprocess.run(
                exec_cmd, shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=30, env=build_subprocess_env(),
                creationflags=windows_hide_flags(),  # no console flash on Windows (#56747)
            )
            # See #56747.
            output = result.stdout.strip() or result.stderr.strip()
            if output:
                from agent.redact import redact_sensitive_text
                self._console_print(_rich_text_from_ansi(redact_sensitive_text(output)))
            else:
                self._console_print(f"[dim]{_t('cli.quick.no_output')}[/]")
        except subprocess.TimeoutExpired:
            self._console_print(f"[bold red]{_t('cli.quick.timed_out')}[/]")
        except Exception as e:
            self._console_print(f"[bold red]{_t('cli.quick.error', error=str(e))}[/]")
        return True

    def _run_plugin_slash_command(self, base_cmd: str, user_args: str) -> None:
        from hermes_cli.plugins import get_plugin_command_handler, resolve_plugin_command_result

        plugin_handler = get_plugin_command_handler(base_cmd.lstrip("/"))
        if not plugin_handler:
            return
        try:
            result = resolve_plugin_command_result(plugin_handler(user_args))
            if result:
                _cprint(str(result))
        except Exception as e:
            _cprint(f"\033[1;31m{_t('cli.plugin.command_error', error=str(e))}{_RST}")

    def _queue_skill_message(self, msg) -> None:
        if hasattr(self, '_pending_input'):
            self._pending_input.put(msg)

    def _run_skill_bundle_command(self, base_cmd: str, bundle_info: dict, user_instruction: str) -> None:
        """``/<bundle>`` loads several skills at once (bundles win over same-named skills)."""
        bundle_result = build_bundle_invocation_message(base_cmd, user_instruction, task_id=self.session_id)
        if not bundle_result:
            ChatConsole().print(f"[bold red]{_t('cli.skills.bundle_load_failed', command=base_cmd)}[/]")
            return
        msg, loaded_names, missing = bundle_result
        self._queue_loaded_skills(
            msg, _t("cli.skills.loading_bundle", name=bundle_info['name'], count=str(len(loaded_names))), missing)

    def _queue_loaded_skills(self, msg, label: str, missing) -> None:
        print(f"\n⚡ {label}")
        if missing:
            ChatConsole().print(f"[yellow]{_t('cli.skills.skipped_missing', names=', '.join(missing))}[/]")
        self._queue_skill_message(msg)

    def _run_skill_slash_command(self, base_cmd: str, skill_info: dict, rest: str) -> None:
        """``/<skill> ...``; stacked ``/skill-a /skill-b do XYZ`` loads every leading skill (up to 5)."""
        from agent.skill_commands import build_stacked_skill_invocation_message, split_stacked_skill_commands

        extra_keys, user_instruction = split_stacked_skill_commands(rest)
        if extra_keys:
            stacked_result = build_stacked_skill_invocation_message(
                [base_cmd, *extra_keys], user_instruction, task_id=self.session_id,
            )
            if not stacked_result:
                ChatConsole().print(f"[bold red]{_t('cli.skills.stacked_load_failed', command=base_cmd)}[/]")
                return
            msg, loaded_names, missing = stacked_result
            self._queue_loaded_skills(
                msg, _t("cli.skills.loading_stacked", count=str(len(loaded_names)), names=', '.join(loaded_names)),
                missing,
            )
            return
        msg = build_skill_invocation_message(base_cmd, rest, task_id=self.session_id)
        if msg:
            self._queue_loaded_skills(msg, _t("cli.skills.loading_skill", name=skill_info['name']), None)
        else:
            ChatConsole().print(f"[bold red]{_t('cli.skills.skill_load_failed', command=base_cmd)}[/]")

    def _expand_slash_prefix(self, cmd_original: str, cmd_lower: str, skill_commands, skill_bundles) -> bool:
        """Unique-prefix expansion against built-in COMMANDS + skill commands/bundles (agrees with tab-completion)."""
        from hermes_cli.commands import COMMANDS
        typed_base = cmd_lower.split()[0]
        all_known = set(COMMANDS) | set(skill_commands) | set(skill_bundles)
        matches = [c for c in all_known if c.startswith(typed_base)]
        if len(matches) > 1:
            if typed_base in matches:
                matches = [typed_base]
            else:
                # Unique shortest match wins: /qui -> /quit (5) over /quint-pipeline (15)
                min_len = min(len(c) for c in matches)
                shortest = [c for c in matches if len(c) == min_len]
                if len(shortest) == 1:
                    matches = shortest
        if len(matches) == 1 and matches[0] != typed_base:
            # Expand to the full name, preserving arguments.
            return self.process_command(matches[0] + cmd_original.strip()[len(typed_base):], redispatch=True)
        if len(matches) > 1:
            _cprint(f"{_ACCENT}{_t('cli.command.ambiguous', command=cmd_lower)}{_RST}")
            _cprint(f"{_DIM}{_t('cli.command.did_you_mean_many', candidates=', '.join(sorted(matches)))}{_RST}")
        else:
            # Exact token with no handler (never re-dispatch the same token: recursion), or no match.
            from hermes_cli.cli_unknown_command import unknown_command_lines
            lead, pointer = unknown_command_lines(cmd_lower, all_known)
            _cprint(f"\033[1;31m{lead}{_RST}")
            _cprint(f"{_DIM}{_ACCENT}{pointer}{_RST}")
        return True

    def _drain_interrupt_queue_to_pending_input(self) -> None:
        """Move stray ``_interrupt_queue`` messages into ``_pending_input`` after every turn.

        Busy-time input lands in ``_interrupt_queue`` and is only drained by the explicit
        interrupt path; a turn that finishes naturally would otherwise strand it and the
        CLI appears to hang. Never raises.

        Called once at the end of every turn from ``process_loop``'s ``finally`` block. Catches and swallows
        ``Exception`` because the drain must never break the main loop. (#20271)
        """
        try:
            while not self._interrupt_queue.empty():
                stray = self._interrupt_queue.get_nowait()
                if stray:
                    self._pending_input.put(stray)
        except Exception:
            pass

    def _on_reasoning(self, reasoning_text: str):
        """Callback for intermediate reasoning display during tool-call loops."""
        if not reasoning_text:
            return
        self._reasoning_preview_buf = getattr(self, "_reasoning_preview_buf", "") + reasoning_text
        self._flush_reasoning_preview(force=False)

    def _manual_compress(self, cmd_original: str = ""):
        """Manually trigger context compression on the current conversation.

        Two modes:

        * ``/compress [<focus>]`` — compress the *whole* history. An
          optional focus topic guides the summariser to preserve
          information related to *focus* while being more aggressive
          about discarding everything else.  Inspired by Claude Code's
          ``/compact <focus>`` feature.
        * ``/compress here [N]`` — boundary-aware compression. Summarize
          everything *except* the most recent ``N`` exchanges (default
          2), which are preserved verbatim. Inspired by Claude Code's
          Rewind "Summarize up to here" action (v2.1.139, May 2026,
          https://code.claude.com/docs/en/whats-new/2026-w20). Lets the
          user pick the compression boundary instead of leaving it to
          the automatic token-budget heuristic.
        """
        if not self.conversation_history or len(self.conversation_history) < 4:
            print("(._.) Not enough conversation to compress (need at least 4 messages).")
            return

        if not self.agent:
            print("(._.) No active agent -- send a message first.")
            return

        # No compression_enabled gate here: the config flag disables
        # *automatic* compaction only. Manual /compress is an explicit user
        # action — the context-overflow error path (conversation_loop.py)
        # directs users here when auto-compaction is off, and the gateway's
        # /compress handler has never gated on the flag.

        from hermes_cli.partial_compress import (
            extract_compress_flags,
            parse_partial_compress_args,
            rejoin_compressed_head_and_tail,
            split_history_for_partial_compress,
            summarize_compress_preview,
        )
        from agent.conversation_compression import (
            finalize_context_engine_compression_notification,
        )

        # Args after the command word (e.g. "/compress here 3" -> "here 3").
        raw_args = ""
        if cmd_original:
            _parts = cmd_original.strip().split(None, 1)
            if len(_parts) > 1:
                raw_args = _parts[1].strip()

        # Strip --preview/--dry-run/--aggressive before positional parsing
        # so the flags coexist with 'here [N]' / focus-topic forms.
        raw_args, preview, aggressive = extract_compress_flags(raw_args)
        partial, keep_last, focus_topic = parse_partial_compress_args(raw_args)
        focus_topic = focus_topic or ""

        if aggressive:
            # LLM-free hard truncation is not supported: it would need its
            # own transcript-persistence path outside the guarded
            # _compress_context rotation machinery. Surface that instead of
            # silently mis-parsing the flag as a focus topic.
            print("(._.) --aggressive is not supported; use '/compress here [N]' "
                  "to keep only recent exchanges, or /undo to drop turns.")
            if not preview:
                return

        if preview:
            from agent.model_metadata import estimate_request_tokens_rough
            _sys_prompt = getattr(self.agent, "_cached_system_prompt", "") or ""
            _tools = getattr(self.agent, "tools", None) or None
            approx_tokens = estimate_request_tokens_rough(
                self.conversation_history,
                system_prompt=_sys_prompt,
                tools=_tools,
            )
            report = summarize_compress_preview(
                self.conversation_history,
                partial,
                keep_last,
                focus_topic or None,
                approx_tokens,
            )
            for line in report["lines"]:
                print(f"🗜️  {line}")
            return

        original_count = len(self.conversation_history)
        with self._busy_command("Compressing context...", blocks_input=False):
            try:
                from agent.model_metadata import estimate_request_tokens_rough
                from agent.manual_compression_feedback import summarize_manual_compression
                original_history = list(self.conversation_history)

                # Boundary-aware split: only the head is summarized; the
                # most recent `keep_last` exchanges ride along verbatim.
                tail: list = []
                head = original_history
                if partial:
                    head, tail = split_history_for_partial_compress(
                        original_history, keep_last
                    )
                    if not tail:
                        # Split degenerated (everything would be kept, or
                        # no head left to compress). Fall back to full
                        # compression so the user still gets an action.
                        partial = False
                        head = original_history

                # Include system prompt + tool schemas in the estimate —
                # a transcript-only number understates real request pressure
                # and can even appear to grow after compression because a
                # dense handoff summary replaces many short turns (#6217).
                _sys_prompt = getattr(self.agent, "_cached_system_prompt", "") or ""
                _tools = getattr(self.agent, "tools", None) or None
                approx_tokens = estimate_request_tokens_rough(
                    original_history,
                    system_prompt=_sys_prompt,
                    tools=_tools,
                )
                if partial:
                    print(f"🗜️  Summarizing up to here: compressing {len(head)} of "
                          f"{original_count} messages (~{approx_tokens:,} tokens), "
                          f"keeping last {keep_last} exchange(s) verbatim...")
                elif focus_topic:
                    print(f"🗜️  Compressing {original_count} messages (~{approx_tokens:,} tokens), "
                          f"focus: \"{focus_topic}\"...")
                else:
                    print(f"🗜️  Compressing {original_count} messages (~{approx_tokens:,} tokens)...")

                # Pass None as system_message so _compress_context rebuilds
                # the system prompt from scratch via _build_system_prompt(None).
                # Passing _cached_system_prompt caused duplication because
                # _build_system_prompt appends system_message to prompt_parts
                # which already contain the agent identity — resulting in the
                # identity block appearing twice (issue #15281).
                compressed, _ = self.agent._compress_context(
                    head,
                    None,
                    approx_tokens=approx_tokens,
                    focus_topic=focus_topic or None,
                    force=True,
                    defer_context_engine_notification=True,
                )

                # If _compress_context returned unchanged because a
                # concurrent compression lock is held, tell the user
                # clearly instead of showing the misleading
                # "No changes from compression" no-op text. The wording
                # distinguishes a confirmed holder from an unconfirmed
                # acquisition failure (describe_compression_lock_skip).
                # Type-pinned check (is True / str): the flag's only real
                # values are None/True/holder-string, and a bare getattr
                # truthiness test is fooled by MagicMock auto-attributes on
                # test-double agents (skill pitfall: MagicMock vs hasattr).
                _lock_skip_signal = getattr(
                    self.agent, "_compression_skipped_due_to_lock", None
                )
                if _lock_skip_signal is True or isinstance(_lock_skip_signal, str):
                    from agent.manual_compression_feedback import (
                        describe_compression_lock_skip,
                    )
                    print(
                        "  "
                        + describe_compression_lock_skip(
                            self.agent._compression_skipped_due_to_lock
                        )
                    )
                    self.agent._compression_skipped_due_to_lock = None
                    # No boundary was committed on a lock-skip; discard the
                    # deferred context-engine notification (exactly-once).
                    finalize_context_engine_compression_notification(
                        self.agent,
                        committed=False,
                    )
                    return

                if partial and tail:
                    compressed = rejoin_compressed_head_and_tail(compressed, tail)
                self.conversation_history = compressed
                # _compress_context ends the old session and creates a new child
                # session on the agent (run_agent.py::_compress_context). Sync the
                # CLI's session_id so /status, /resume, exit summary, and title
                # generation all point at the live continuation session, not the
                # ended parent. Without this, subsequent end_session() calls target
                # the already-closed parent and the child is orphaned.
                if (
                    getattr(self.agent, "session_id", None)
                    and self.agent.session_id != self.session_id
                ):
                    self.session_id = self.agent.session_id
                    getattr(self, "_write_terminal_breadcrumb", lambda: None)()
                    self._pending_title = None
                    # Manual /compress replaces conversation_history with a new
                    # compressed handoff for the child session. Persist it from
                    # offset 0 so resume can recover the continuation after exit.
                    self.agent._flush_messages_to_session_db(self.conversation_history, None)
                finalize_context_engine_compression_notification(
                    self.agent,
                    committed=True,
                )
                new_tokens = estimate_request_tokens_rough(
                    self.conversation_history,
                    system_prompt=_sys_prompt,
                    tools=_tools,
                )
                summary = summarize_manual_compression(
                    original_history,
                    self.conversation_history,
                    approx_tokens,
                    new_tokens,
                    compression_state=getattr(
                        self.agent, "context_compressor", None
                    ),
                )
                if (
                    summary.get("aborted")
                    or summary.get("fallback_used")
                    or summary.get("refused_would_grow")
                ):
                    icon = "⚠️"
                else:
                    icon = "🗜️" if summary["noop"] else "✅"
                print(f"  {icon} {summary['headline']}")
                print(f"     {summary['token_line']}")
                if summary["note"]:
                    print(f"     {summary['note']}")

            except Exception as e:
                finalize_context_engine_compression_notification(
                    self.agent,
                    committed=False,
                )
                print(f"  ❌ Compression failed: {e}")



    # Inline-skip tokens that bypass the destructive-slash confirmation modal.
    # A general escape hatch for non-interactive use (scripting/automation) and
    # for the degraded path where the modal can't be marshaled onto the app loop
    # — lets users self-serve without flipping approvals.destructive_slash_confirm
    # in config. (Native Windows now drives the modal normally — see #33961.)
    _DESTRUCTIVE_SKIP_TOKENS = frozenset({"now", "--yes", "-y"})

    @classmethod
    def _split_destructive_skip(cls, cmd_text: Optional[str]) -> tuple[str, bool]:
        """Split inline-skip tokens out of a destructive slash command.

        Returns ``(remainder, skip)`` where ``remainder`` is the original
        text with the command word and any recognized skip tokens removed,
        and ``skip`` is True iff at least one skip token was found.

        Examples:
            "/reset now"            -> ("", True)
            "/reset --yes My title" -> ("My title", True)
            "/new My title"         -> ("My title", False)
            "/clear"                -> ("", False)
        """
        if not cmd_text:
            return "", False
        tokens = cmd_text.strip().split()
        if not tokens:
            return "", False
        # Drop leading "/cmd" word — callers pass the full command text.
        if tokens[0].startswith("/"):
            tokens = tokens[1:]
        skip = False
        kept: list[str] = []
        for tok in tokens:
            if tok.lower() in cls._DESTRUCTIVE_SKIP_TOKENS:
                skip = True
                continue
            kept.append(tok)
        return " ".join(kept), skip

    def _confirm_destructive_slash(
        self,
        command: str,
        detail: str,
        cmd_original: Optional[str] = None,
    ) -> Optional[str]:
        """Prompt the user to confirm a destructive session slash command.

        Used by ``/clear``, ``/new``/``/reset``, and ``/undo`` before they
        discard conversation state.  Three-option prompt:

          1. Approve Once — proceed this time only
          2. Always Approve — proceed and persist
             ``approvals.destructive_slash_confirm: false`` so future
             destructive commands run without confirmation
          3. Cancel — abort

        Gated by ``approvals.destructive_slash_confirm`` (default on).  If the
        gate is off the function returns ``"once"`` immediately without
        prompting.

        Inline-skip: if ``cmd_original`` contains ``now``, ``--yes``, or
        ``-y`` as an argument (e.g. ``/reset now``, ``/new --yes My title``),
        the modal is bypassed and ``"once"`` is returned immediately. This is
        an escape hatch for non-interactive use and for the degraded path where
        the modal can't be marshaled onto the app loop (native Windows itself now
        drives the modal normally — see #33961). Callers are responsible
        for stripping the skip tokens from any remaining argument parsing
        (see :meth:`_split_destructive_skip`).

        Returns ``"once"``, ``"always"``, or ``None`` (cancelled).  Callers
        proceed with the destructive action when the result is non-None.
        """
        # Inline-skip escape hatch — works regardless of platform/modal state.
        # See class-level _DESTRUCTIVE_SKIP_TOKENS for the accepted tokens.
        if cmd_original:
            _, _skip = self._split_destructive_skip(cmd_original)
            if _skip:
                return "once"

        # Gate check — respects prior "Always Approve" clicks.
        try:
            cfg = load_cli_config()
            approvals = cfg.get("approvals") if isinstance(cfg, dict) else None
            confirm_required = True
            if isinstance(approvals, dict):
                confirm_required = bool(approvals.get("destructive_slash_confirm", True))
        except Exception:
            confirm_required = True

        if not confirm_required:
            return "once"

        # Render a prompt_toolkit-native confirmation panel.  This keeps option
        # labels visible above the composer and avoids raw input()/EOF races with
        # the running TUI.
        choices = [
            ("once", "Approve Once", "proceed this time only"),
            ("always", "Always Approve", "proceed and silence this prompt permanently"),
            ("cancel", "Cancel", "keep current conversation"),
        ]
        raw = self._prompt_text_input_modal(
            title=f"⚠️  /{command} — destroys conversation state",
            detail=detail,
            choices=choices,
        )
        if raw is None:
            print(f"🟡 /{command} cancelled (no input).")
            return None
        choice = self._normalize_slash_confirm_choice(raw, choices)
        if choice is None:
            print(f"🟡 Unrecognized choice '{raw}'. /{command} cancelled.")
            return None

        if choice == "cancel":
            print(f"🟡 /{command} cancelled. Conversation unchanged.")
            return None

        if choice == "always":
            if save_config_value("approvals.destructive_slash_confirm", False):
                print("🔒 Future /clear, /new, /reset, and /undo will run without confirmation.")
                print("   Re-enable via `approvals.destructive_slash_confirm: true` in config.yaml.")
            else:
                print("⚠️  Couldn't persist opt-out — proceeding once.")

        return choice

    def _confirm_and_reload_mcp(self, cmd_original: str = "") -> None:
        """Interactive /reload-mcp — confirm with the user, then reload.

        Reloading MCP tools invalidates the provider prompt cache for the
        active session (tool schemas are baked into the system prompt).
        The next message re-sends full input tokens — can be expensive on
        long-context or high-reasoning models.

        Three options: Approve Once, Always Approve (persists
        ``approvals.mcp_reload_confirm: false`` so future reloads run
        without this prompt), Cancel.  Gated by
        ``approvals.mcp_reload_confirm`` — default on.
        """
        # Gate check — respects prior "Always Approve" clicks.
        try:
            cfg = load_cli_config()
            approvals = cfg.get("approvals") if isinstance(cfg, dict) else None
            confirm_required = True
            if isinstance(approvals, dict):
                confirm_required = bool(approvals.get("mcp_reload_confirm", True))
        except Exception:
            confirm_required = True

        if not confirm_required:
            with self._busy_command(self._slow_command_status(cmd_original)):
                self._reload_mcp()
            return

        # Render warning + prompt.  Use the same prompt_toolkit-native composer
        # modal as destructive slash confirmations so choices stay visible.
        choices = [
            ("once", "Approve Once", "reload now"),
            ("always", "Always Approve", "reload now and silence this prompt permanently"),
            ("cancel", "Cancel", "leave MCP tools unchanged"),
        ]
        raw = self._prompt_text_input_modal(
            title="⚠️  /reload-mcp — Prompt cache invalidation warning",
            detail=(
                "Reloading MCP servers rebuilds the tool set for this session and\n"
                "invalidates the provider prompt cache. The next message will\n"
                "re-send full input tokens (can be expensive on long-context or\n"
                "high-reasoning models)."
            ),
            choices=choices,
        )
        if raw is None:
            print("🟡 /reload-mcp cancelled (no input).")
            return
        choice = self._normalize_slash_confirm_choice(raw, choices)
        if choice is None:
            print(f"🟡 Unrecognized choice '{raw}'. /reload-mcp cancelled.")
            return

        if choice == "cancel":
            print("🟡 /reload-mcp cancelled. MCP tools unchanged.")
            return

        if choice == "always":
            if save_config_value("approvals.mcp_reload_confirm", False):
                print("🔒 Future /reload-mcp calls will run without confirmation.")
                print("   Re-enable via `approvals.mcp_reload_confirm: true` in config.yaml.")
            else:
                print("⚠️  Couldn't persist opt-out — reloading once.")

        with self._busy_command(self._slow_command_status(cmd_original)):
            self._reload_mcp()

    def _reload_mcp(self):
        """Reload MCP servers: disconnect all, re-read config.yaml, reconnect.

        After reconnecting, refreshes the agent's tool list so the model
        sees the updated tools on the next turn.
        """
        try:
            from tools.mcp_tool import shutdown_mcp_servers, discover_mcp_tools, _servers, _lock

            # Capture old server names
            with _lock:
                old_servers = set(_servers.keys())

            if not self._command_running:
                print("🔄 Reloading MCP servers...")

            # Shutdown existing connections
            shutdown_mcp_servers()

            # Reconnect (reads config.yaml fresh)
            new_tools = discover_mcp_tools()

            # Compute what changed
            with _lock:
                connected_servers = set(_servers.keys())

            added = connected_servers - old_servers
            removed = old_servers - connected_servers
            reconnected = connected_servers & old_servers

            if reconnected:
                print(f"  ♻️  Reconnected: {', '.join(sorted(reconnected))}")
            if added:
                print(f"  ➕ Added: {', '.join(sorted(added))}")
            if removed:
                print(f"  ➖ Removed: {', '.join(sorted(removed))}")
            if not connected_servers:
                print("  No MCP servers connected.")
            else:
                print(f"  🔧 {len(new_tools)} tool(s) available from {len(connected_servers)} server(s)")

            # Refresh the agent's tool list so the model can call new tools.
            # Route through the shared helper so this CLI /reload-mcp path stays
            # in lockstep with the TUI RPC / gateway reload / late-binding paths
            # (name-diff, thread-safe, and — critically — additive-preserving so
            # memory-provider and context-engine tools survive the rebuild).
            if self.agent is not None:
                from tools.mcp_tool import refresh_agent_mcp_tools
                # Explicit reload: pick up MCP servers the user ENABLED in config
                # this session. self.enabled_toolsets was resolved once at
                # startup; merge in any now-connected server names (unless the
                # user pinned `all`/`*`, which already includes everything) so a
                # freshly-added server isn't filtered out. Mirrors startup, where
                # MCP server names are part of enabled_toolsets (see __init__).
                enabled_override = None
                et = self.enabled_toolsets
                if et and "all" not in et and "*" not in et:
                    merged = list(et)
                    for _name in sorted(connected_servers):
                        if _name not in merged:
                            merged.append(_name)
                    enabled_override = merged
                refresh_agent_mcp_tools(
                    self.agent,
                    enabled_override=enabled_override,
                    quiet_mode=True,
                )
                # Keep the CLI's own list in sync with what the agent now uses.
                if enabled_override is not None:
                    self.enabled_toolsets = enabled_override

            # Inject a message at the END of conversation history so the
            # model knows tools changed.  Appended after all existing
            # messages to preserve prompt-cache for the prefix.
            change_parts = []
            if added:
                change_parts.append(f"Added servers: {', '.join(sorted(added))}")
            if removed:
                change_parts.append(f"Removed servers: {', '.join(sorted(removed))}")
            if reconnected:
                change_parts.append(f"Reconnected servers: {', '.join(sorted(reconnected))}")
            tool_summary = f"{len(new_tools)} MCP tool(s) now available" if new_tools else "No MCP tools available"
            change_detail = ". ".join(change_parts) + ". " if change_parts else ""
            self.conversation_history.append({
                "role": "user",
                "content": f"[IMPORTANT: MCP servers have been reloaded. {change_detail}{tool_summary}. The tool list for this conversation has been updated accordingly.]",
            })

            # Persist session immediately so the session log reflects the
            # updated tools list (self.agent.tools was refreshed above).
            if self.agent is not None:
                try:
                    self.agent._persist_session(
                        self.conversation_history,
                        self.conversation_history,
                    )
                except Exception:
                    pass  # Best-effort

            print(f"  ✅ Agent updated — {len(self.agent.tools if self.agent else [])} tool(s) available")

        except Exception as e:
            print(f"  ❌ MCP reload failed: {e}")

    def _reload_skills(self) -> None:
        """Reload skills: rescan ~/.hermes/skills/ and queue a note for the
        next user turn.

        Skills don't need to live in the system prompt for the model to use
        them (they're invoked via ``/skill-name``, ``skills_list``, or
        ``skill_view`` at runtime), so this does NOT clear the prompt cache.
        It rescans the slash-command map, prints the diff for the user, and
        — if any skills were added or removed — queues a one-shot note that
        gets prepended to the next user message. This preserves message
        alternation (no phantom user turn injected out of band) and keeps
        prompt caching intact.
        """
        try:
            from agent.skill_commands import reload_skills, get_skill_commands

            if not self._command_running:
                print("🔄 Reloading skills...")

            result = reload_skills()

            # Sync cli.py's module-level _skill_commands so all consumers
            # (help display, command dispatch, Tab-completion lambda) see the
            # updated dict without needing to restart the session.
            global _skill_commands
            _skill_commands = get_skill_commands()
            added = result.get("added", [])      # [{"name", "description"}, ...]
            removed = result.get("removed", [])  # [{"name", "description"}, ...]
            total = result.get("total", 0)

            if not added and not removed:
                print("  No new skills detected.")
                print(f"  📚 {total} skill(s) available")
                return

            def _fmt_line(item: dict) -> str:
                nm = item.get("name", "")
                desc = item.get("description", "")
                return f"    - {nm}: {desc}" if desc else f"    - {nm}"

            if added:
                print("  ➕ Added Skills:")
                for item in added:
                    print(f"  {_fmt_line(item)}")
            if removed:
                print("  ➖ Removed Skills:")
                for item in removed:
                    print(f"  {_fmt_line(item)}")
            print(f"  📚 {total} skill(s) available")

            # Queue a one-shot note for the NEXT user turn. The CLI's agent
            # loop prepends ``_pending_skills_reload_note`` (if set) to the
            # API-call-local message at ~L8770, then clears it — same
            # pattern as ``_pending_model_switch_note``. Nothing is written
            # to conversation_history here, so message alternation stays
            # intact and no out-of-band user turn is persisted.
            #
            # Format matches how the system prompt renders pre-existing
            # skills (``    - name: description``) so the model reads the
            # diff in the same shape as its original skill catalog.
            sections = ["[USER INITIATED SKILLS RELOAD:"]
            if added:
                sections.append("")
                sections.append("Added Skills:")
                for item in added:
                    sections.append(_fmt_line(item))
            if removed:
                sections.append("")
                sections.append("Removed Skills:")
                for item in removed:
                    sections.append(_fmt_line(item))
            sections.append("")
            sections.append("Use skills_list to see the updated catalog.]")
            self._pending_skills_reload_note = "\n".join(sections)

        except Exception as e:
            print(f"  ❌ Skills reload failed: {e}")

    # ====================================================================
    # Tool-call generation indicator (shown during streaming)
    # ====================================================================

    def _on_tool_gen_start(self, tool_name: str) -> None:
        """Called when the model begins generating tool-call arguments.

        Closes any open streaming boxes (reasoning / response) exactly once,
        then prints a short status line so the user sees activity instead of
        a frozen screen while a large payload (e.g. 45 KB write_file) streams.
        """
        if getattr(self, "_stream_box_opened", False):
            self._flush_stream()
            self._stream_box_opened = False
        self._close_reasoning_box()

        from agent.display import get_tool_emoji
        emoji = get_tool_emoji(tool_name, default="⚡")
        _cprint(f"  ┊ {emoji} preparing {tool_name}…")

    # ====================================================================
    # Tool progress callback (audio cues for voice mode)
    # ====================================================================

    def _on_tool_progress(self, event_type: str, function_name: str = None, preview: str = None, function_args: dict = None, **kwargs):
        """Called on tool lifecycle events (tool.started, tool.completed, reasoning.available, etc.).

        Updates the TUI spinner widget so the user can see what the agent
        is doing during tool execution (fills the gap between thinking
        spinner and next response).

        On tool.started, records a monotonic timestamp so get_spinner_text()
        can show a live elapsed timer (the TUI poll loop already invalidates
        every ~0.15s, so the counter updates automatically).

        When tool_progress_mode is "all" or "new", also prints a persistent
        stacked line to scrollback on tool.completed so users can see the
        full history of tool calls (not just the current one in the spinner).
        """
        # MoA reference-model outputs: render each reference's answer as a
        # labelled thinking-style block BEFORE the aggregator acts, so the user
        # sees the mixture-of-agents process instead of a silent pause. These
        # are display-only events emitted by the MoA facade (agent_init relay);
        # they never enter message history.
        if event_type == "moa.reference":
            label = function_name or "reference"
            text = preview or ""
            idx = kwargs.get("moa_index")
            count = kwargs.get("moa_count")
            header = f"Reference {idx}/{count} — {label}" if idx and count else f"Reference — {label}"
            try:
                self._flush_reasoning_preview(force=True)
            except Exception:
                pass
            _cprint(f"  {_DIM}┊ ◇ {header}{_RST}")
            try:
                self._emit_reasoning_preview(text)
            except Exception:
                # Fallback: print the raw text dimmed if the preview helper fails.
                if text.strip():
                    _cprint(f"  {_DIM}{text.strip()}{_RST}")
            self._invalidate()
            return
        if event_type == "moa.aggregating":
            agg = function_name or ""
            self._spinner_text = f"◆ aggregating ({agg})" if agg else "◆ aggregating"
            self._invalidate()
            return

        # Feed the pet: tools mean "running" (not reasoning); a failed tool
        # latches the turn so it ends on a sulk.
        if event_type == "tool.started":
            self._pet_reasoning = False
        elif event_type == "tool.completed" and kwargs.get("is_error"):
            self._pet_turn_error = True
        elif event_type and event_type.startswith("reasoning"):
            self._pet_reasoning = True

        if event_type == "tool.completed":
            self._tool_start_time = 0.0
            # Per-turn accounting: this feed already sees every tool call with
            # its result, so the summary line needs no agent-loop state.
            self._turn_summary_record(
                function_name, kwargs.get("result"), kwargs.get("is_error", False)
            )
            # Focus view: count the scrollback line we are NOT printing, so the
            # post-turn recovery line can report how much was hidden. Counted
            # against the pre-focus tool-progress mode, so a user who already
            # had /verbose off is never told focus hid something it didn't.
            if getattr(self, "_focus_view_enabled", False):
                try:
                    self._note_focus_hidden_line(function_name or "")
                except Exception:
                    pass
            # Print stacked scrollback line for "new" / "all" / "verbose" modes.
            # "verbose" was previously omitted here, so non-streaming model
            # calls (MoA aggregator, copilot-acp) rendered each tool only into
            # the transient spinner line — which overwrites itself, so no
            # scrollable tool history accumulated. Streaming models hid the bug
            # because _on_tool_gen_start commits a "preparing" line per tool;
            # non-streaming calls never emit that, leaving verbose mode with no
            # committed line at all. "verbose" is strictly more than "all", so
            # it must commit at least the same line.
            if function_name and self.tool_progress_mode in {"new", "all", "verbose"}:
                duration = kwargs.get("duration", 0.0)
                # Pop stored args from tool.started for this function
                stored = self._pending_tool_info.get(function_name)
                stored_args = stored.pop(0) if stored else {}
                if stored is not None and not stored:
                    del self._pending_tool_info[function_name]
                # "new" mode: skip consecutive repeats of the same tool
                if self.tool_progress_mode == "new" and function_name == self._last_scrollback_tool:
                    self._invalidate()
                    return
                self._last_scrollback_tool = function_name
                try:
                    from agent.display import get_cute_tool_message
                    line = get_cute_tool_message(function_name, stored_args, duration, result=kwargs.get("result"))
                    _cprint(f"  {line}")
                except Exception:
                    pass
                # First-touch onboarding: on the first tool in this process
                # that takes longer than the threshold while we're in the
                # noisiest progress mode, print a one-time hint about
                # /verbose.  Latched on self so it fires at most once per
                # process; persisted to config.yaml so it never fires again
                # across processes either.
                try:
                    if (
                        not getattr(self, "_long_tool_hint_fired", False)
                        and self.tool_progress_mode == "all"
                        and duration >= 30.0
                    ):
                        from agent.onboarding import (
                            TOOL_PROGRESS_FLAG,
                            is_seen,
                            mark_seen,
                            tool_progress_hint_cli,
                        )
                        if not is_seen(CLI_CONFIG, TOOL_PROGRESS_FLAG):
                            self._long_tool_hint_fired = True
                            _cprint(f"  {_DIM}{tool_progress_hint_cli()}{_RST}")
                            mark_seen(_hermes_home / "config.yaml", TOOL_PROGRESS_FLAG)
                            CLI_CONFIG.setdefault("onboarding", {}).setdefault("seen", {})[TOOL_PROGRESS_FLAG] = True
                except Exception:
                    pass
            self._invalidate()
            return
        if event_type != "tool.started":
            return
        if function_name and not function_name.startswith("_"):
            from agent.display import get_tool_emoji
            emoji = get_tool_emoji(function_name)
            label = preview or function_name
            from agent.display import get_tool_preview_max_len
            _pl = get_tool_preview_max_len()
            if _pl > 0 and len(label) > _pl:
                label = label[:_pl - 3] + "..."
            self._spinner_text = f"{emoji} {label}"
            self._tool_start_time = time.monotonic()
            # Store args for stacked scrollback line on completion
            self._pending_tool_info.setdefault(function_name, []).append(
                function_args if function_args is not None else {}
            )
            self._invalidate()

    def _on_tool_start(self, tool_call_id: str, function_name: str, function_args: dict):
        """Capture local before-state for write-capable tools."""
        try:
            from agent.display import capture_local_edit_snapshot

            snapshot = capture_local_edit_snapshot(function_name, function_args)
            if snapshot is not None:
                self._pending_edit_snapshots[tool_call_id] = snapshot
        except Exception:
            logger.debug("Edit snapshot capture failed for %s", function_name, exc_info=True)

    def _on_tool_complete(self, tool_call_id: str, function_name: str, function_args: dict, function_result: str):
        """Render file edits with inline diff after write-capable tools complete."""
        # A top-level delegate_task dispatches in the background and re-enters as
        # a fresh turn when done. Say so once — no spinner, nothing to poll — so
        # the idle prompt doesn't read as "nothing happened" (⛓ tracks the work).
        if function_name == "delegate_task":
            try:
                parsed = json.loads(function_result) if isinstance(function_result, str) else (function_result or {})
            except Exception:
                parsed = {}
            if isinstance(parsed, dict) and parsed.get("status") == "dispatched" and parsed.get("mode") == "background":
                n = parsed.get("count") or 1
                noun, tail = ("task", "it finishes") if n == 1 else (f"{n} tasks", "they finish")
                try:
                    _cprint(f"\033[2m\u21a9 Background {noun} running — I'll resume when {tail}. Keep chatting.\033[0m")
                except Exception:
                    pass
        snapshot = self._pending_edit_snapshots.pop(tool_call_id, None)
        try:
            from agent.display import render_edit_diff_with_delta

            render_edit_diff_with_delta(
                function_name,
                function_result,
                function_args=function_args,
                snapshot=snapshot,
                print_fn=_cprint,
            )
        except Exception:
            logger.debug("Edit diff preview failed for %s", function_name, exc_info=True)

    # ====================================================================
    # Voice mode methods
    # ====================================================================

    def _voice_start_recording(self):
        """Start capturing audio from the microphone."""
        if getattr(self, '_should_exit', False):
            return
        from tools.voice_mode import create_audio_recorder, check_voice_requirements

        reqs = check_voice_requirements()
        if not reqs["audio_available"]:
            if _is_termux_environment():
                details = reqs.get("details", "")
                if "Termux:API Android app is not installed" in details:
                    raise RuntimeError(
                        "Termux:API command package detected, but the Android app is missing.\n"
                        "Install/update the Termux:API Android app, then retry /voice on.\n"
                        "Fallback: pkg install python-numpy portaudio && python -m pip install sounddevice"
                    )
                raise RuntimeError(
                    "Voice mode requires either Termux:API microphone access or Python audio libraries.\n"
                    "Option 1: pkg install termux-api and install the Termux:API Android app\n"
                    "Option 2: pkg install python-numpy portaudio && python -m pip install sounddevice"
                )
            raise RuntimeError(
                "Voice mode requires sounddevice and numpy.\n"
                f"Install with: {sys.executable} -m pip install sounddevice numpy"
            )
        if not reqs.get("stt_available", reqs.get("stt_key_set")):
            raise RuntimeError(
                "Voice mode requires an STT provider for transcription.\n"
                "Option 1: uv pip install faster-whisper  "
                "(free, local; `pip install faster-whisper` also works if pip is on PATH)\n"
                "Option 2: Set GROQ_API_KEY (free tier)\n"
                "Option 3: Set VOICE_TOOLS_OPENAI_KEY (paid)"
            )

        # Prevent double-start from concurrent threads (atomic check-and-set)
        with self._voice_lock:
            if self._voice_recording:
                return
            self._voice_recording = True

        # Load silence detection params from config. Shape-safe: a
        # hand-edited ``voice: true`` / ``voice: cmd+b`` leaves
        # ``load_config()['voice']`` as a non-dict; coerce to {} so
        # continuous recording falls back to the documented defaults
        # instead of crashing on ``.get()``.
        voice_cfg: dict = {}
        try:
            from hermes_cli.config import load_config
            _cfg = load_config().get("voice")
            voice_cfg = _cfg if isinstance(_cfg, dict) else {}
        except Exception:
            pass

        # Recorder creation can fail (no input device, PortAudio init error).
        # Reset the flag on failure or _voice_recording stays True forever and
        # every future voice start is silently skipped by the guard above.
        if self._voice_recorder is None:
            try:
                self._voice_recorder = create_audio_recorder()
            except Exception:
                with self._voice_lock:
                    self._voice_recording = False
                raise

        # Apply config-driven silence params (numeric-guarded so YAML
        # scalar corruption doesn't break recording start-up).
        #
        # ``bool`` is explicitly excluded from the numeric check — in
        # Python bool is a subclass of int, so a hand-edited
        # ``silence_threshold: true`` would otherwise be forwarded as
        # ``1`` instead of falling back to the 200 default (Copilot
        # round-12 on #19835).
        _threshold = voice_cfg.get("silence_threshold")
        _duration = voice_cfg.get("silence_duration")
        self._voice_recorder._silence_threshold = (
            _threshold if isinstance(_threshold, (int, float)) and not isinstance(_threshold, bool) else 200
        )
        self._voice_recorder._silence_duration = (
            _duration if isinstance(_duration, (int, float)) and not isinstance(_duration, bool) else 3.0
        )
        # voice.max_recording_seconds — hard cap on a single recording's length.
        # Same numeric guard as the silence params (bool excluded: a hand-edited
        # ``max_recording_seconds: true`` must not become ``1`` — it falls back
        # to the documented 120 default, mirroring the silence-param handling).
        # An explicit numeric value <= 0 disables the cap. Previously this
        # documented key was never read (dead config); wiring it here makes it
        # take effect.
        _max_rec = voice_cfg.get("max_recording_seconds")
        self._voice_recorder._max_recording_seconds = (
            (_max_rec if _max_rec > 0 else 0.0)
            if isinstance(_max_rec, (int, float)) and not isinstance(_max_rec, bool)
            else 120.0
        )

        def _on_silence():
            """Called by AudioRecorder when silence is detected after speech."""
            with self._voice_lock:
                if not self._voice_recording:
                    return
            _cprint(f"\n{_DIM}Silence detected, auto-stopping...{_RST}")
            if hasattr(self, '_app') and self._app:
                self._app.invalidate()
            self._voice_stop_and_transcribe()

        # Audio cue: single beep BEFORE starting stream (avoid CoreAudio conflict)
        if self._voice_beeps_enabled():
            try:
                from tools.voice_mode import play_beep
                play_beep(frequency=880, count=1)
            except Exception:
                pass

        try:
            self._voice_recorder.start(on_silence_stop=_on_silence)
        except Exception:
            with self._voice_lock:
                self._voice_recording = False
            raise
        _label = self._voice_record_key_label()
        if getattr(self._voice_recorder, "supports_silence_autostop", True):
            _recording_hint = f"auto-stops on silence | {_label} to stop & exit continuous"
        elif _is_termux_environment():
            _recording_hint = f"Termux:API capture | {_label} to stop"
        else:
            _recording_hint = f"{_label} to stop"
        _cprint(f"\n{_ACCENT}● Recording...{_RST} {_DIM}({_recording_hint}){_RST}")

        # Periodically refresh prompt to update audio level indicator
        def _refresh_level():
            while True:
                with self._voice_lock:
                    still_recording = self._voice_recording
                if not still_recording:
                    break
                if hasattr(self, '_app') and self._app:
                    self._app.invalidate()
                time.sleep(0.15)
        threading.Thread(target=_refresh_level, daemon=True).start()

    def _voice_stt_model(self) -> Optional[str]:
        """STT model override from config, or None for the provider default.

        For the local provider, prefer stt.local.model (default ``base``) so the
        CLI passes a real model name into the local STT backend.
        """
        try:
            from hermes_cli.config import load_config
            stt_config = load_config().get("stt", {})
            if not isinstance(stt_config, dict):
                return None
            provider = str(stt_config.get("provider") or "").strip().lower()
            if provider == "local":
                local_config = stt_config.get("local") or {}
                if not isinstance(local_config, dict):
                    local_config = {}
                return local_config.get("model") or "base"
            return stt_config.get("model")
        except Exception:
            return None

    def _voice_stt_provider(self) -> str:
        """Configured STT provider name (lowercased), or empty string."""
        try:
            from hermes_cli.config import load_config
            stt_config = load_config().get("stt", {})
            if not isinstance(stt_config, dict):
                return ""
            return str(stt_config.get("provider") or "").strip().lower()
        except Exception:
            return ""

    def _voice_restart_recording_async(self) -> None:
        """Restart continuous-mode recording off-thread (start() can block)."""
        def _restart_recording():
            try:
                self._voice_start_recording()
                if hasattr(self, '_app') and self._app:
                    self._app.invalidate()
            except Exception as e:
                _cprint(f"{_DIM}Voice auto-restart failed: {e}{_RST}")
        threading.Thread(target=_restart_recording, daemon=True).start()

    def _voice_stop_and_transcribe(self):
        """Stop recording, transcribe via STT, and queue the transcript as input."""
        # Atomic guard: only one thread can enter stop-and-transcribe.
        # Set _voice_processing immediately so concurrent Ctrl+B presses
        # don't race into the START path while recorder.stop() holds its lock.
        with self._voice_lock:
            if not self._voice_recording:
                return
            self._voice_recording = False
            self._voice_processing = True

        submitted = False
        transcription_failed = False
        wav_path = None
        try:
            if self._voice_recorder is None:
                return

            wav_path = self._voice_recorder.stop()

            # Audio cue: double beep after stream stopped (no CoreAudio conflict)
            if self._voice_beeps_enabled():
                try:
                    from tools.voice_mode import play_beep
                    play_beep(frequency=660, count=2)
                except Exception:
                    pass

            if wav_path is None:
                _cprint(f"{_DIM}No speech detected.{_RST}")
                return

            # _voice_processing is already True (set atomically above)
            if hasattr(self, '_app') and self._app:
                self._app.invalidate()

            stt_model = self._voice_stt_model()
            if self._voice_stt_provider() == "local":
                _cprint(
                    f"{_DIM}Preparing local STT model '{stt_model}' "
                    f"(first use may download it from Hugging Face)...{_RST}"
                )
            else:
                _cprint(f"{_DIM}Transcribing...{_RST}")

            from tools.voice_mode import transcribe_recording
            result = transcribe_recording(wav_path, model=stt_model)

            if result.get("success") and result.get("transcript", "").strip():
                transcript = result["transcript"].strip()
                from tools.voice_mode import is_voice_stop_phrase
                if is_voice_stop_phrase(transcript):
                    # Bare "stop" (or configured phrase) ends the voice chat
                    # instead of being sent to the agent.
                    _cprint(f"{_DIM}Stop phrase detected — ending voice chat.{_RST}")
                    self._disable_voice_mode()
                    return
                self._attached_images.clear()
                if hasattr(self, '_app') and self._app:
                    self._app.invalidate()
                self._pending_input.put(_VoiceInputMessage(transcript))
                submitted = True
            elif result.get("success"):
                _cprint(f"{_DIM}No speech detected.{_RST}")
            else:
                error = result.get("error", "Unknown error")
                _cprint(f"\n{_DIM}Transcription failed: {error}{_RST}")
                transcription_failed = True

        except Exception as e:
            _cprint(f"\n{_DIM}Voice processing error: {e}{_RST}")
            transcription_failed = wav_path is not None
        finally:
            with self._voice_lock:
                self._voice_processing = False
            if hasattr(self, '_app') and self._app:
                self._app.invalidate()
            # Clean up temp file unless transcription failed. On failure, keep
            # the source recording so long dictation is not lost.
            try:
                if wav_path and os.path.isfile(wav_path):
                    if transcription_failed:
                        _cprint(f"{_DIM}Recording preserved at: {wav_path}{_RST}")
                    else:
                        os.unlink(wav_path)
            except Exception:
                pass

            # Track consecutive no-speech cycles to avoid infinite restart loops.
            # While the agent is mid-turn or TTS is speaking, the user is
            # CORRECTLY silent (waiting/listening) — those cycles must not
            # count, or a multi-minute tool run ends the voice chat under
            # the user. The stop phrase and barge-in still work during the
            # hold (they run on their own paths above).
            stop_continuous_restart = False
            _tts_done = getattr(self, "_voice_tts_done", None)
            _activity_hold = bool(
                getattr(self, "_agent_running", False)
                or (_tts_done is not None and not _tts_done.is_set())
            )
            if not submitted:
                if _activity_hold:
                    pass  # held: keep listening without counting the cycle
                else:
                    self._no_speech_count = getattr(self, '_no_speech_count', 0) + 1
                    if self._no_speech_count >= 3:
                        self._voice_continuous = False
                        self._no_speech_count = 0
                        _cprint(f"{_DIM}No speech detected 3 times, continuous mode stopped.{_RST}")
                        stop_continuous_restart = True
            else:
                self._no_speech_count = 0

            # If no transcript was submitted but continuous mode is active,
            # restart recording so the user can keep talking.
            # (When transcript IS submitted, process_loop handles restart
            # after chat() completes.)
            if (
                self._voice_continuous
                and not submitted
                and not self._voice_recording
                and not stop_continuous_restart
            ):
                self._voice_restart_recording_async()

    def _voice_speak_response_async(self, text: str) -> None:
        """Schedule TTS and mark it pending before continuous recording can restart."""
        if not self._voice_tts or not text:
            return
        self._voice_tts_done.clear()
        threading.Thread(
            target=self._voice_speak_response,
            args=(text,),
            daemon=True,
        ).start()
        # Spoken barge-in must work on the whole-file fallback path too. The
        # full-duplex agent-turn listener normally already covers playback
        # (armed at turn start in chat()); this arm is an idempotent safety
        # net for speak calls outside a chat turn — the listener refuses to
        # double-arm via _voice_fd_active.
        if self._voice_continuous:
            threading.Thread(
                target=self._voice_full_duplex_listener,
                daemon=True,
            ).start()

    def _voice_speak_response(self, text: str):
        """Speak the agent's response aloud using TTS (runs in background thread)."""
        if not self._voice_tts:
            return
        self._voice_tts_done.clear()
        try:
            from tools.tts_tool import text_to_speech_tool
            from tools.voice_mode import play_audio_file

            # Strip markdown and non-speech content for cleaner TTS via the
            # shared cleaner (tools/tts_text_normalize): markdown, emoji,
            # ⋗ blocks, verifier footer, units, newline flattening.
            # The TTS tool owns provider request limits and long-form chunking.
            try:
                from tools.tts_text_normalize import prepare_spoken_text
                tts_text = prepare_spoken_text(text, max_chars=None)
            except Exception:
                # Legacy fallback pipeline — keep voice replies best-effort.
                tts_text = re.sub(r'```[\s\S]*?```', ' ', text)   # fenced code blocks
                tts_text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', tts_text)  # [text](url) -> text
                tts_text = re.sub(r'https?://\S+', '', tts_text)      # URLs
                tts_text = re.sub(r'\*\*(.+?)\*\*', r'\1', tts_text)  # bold
                tts_text = re.sub(r'\*(.+?)\*', r'\1', tts_text)      # italic
                tts_text = re.sub(r'`(.+?)`', r'\1', tts_text)        # inline code
                tts_text = re.sub(r'^#+\s*', '', tts_text, flags=re.MULTILINE)  # headers
                tts_text = re.sub(r'^\s*[-*]\s+', '', tts_text, flags=re.MULTILINE)  # list items
                tts_text = re.sub(r'---+', '', tts_text)              # horizontal rules
                tts_text = re.sub(r'\n{3,}', '\n\n', tts_text)        # excessive newlines
                tts_text = tts_text.strip()
            if not tts_text:
                return
            self._voice_last_tts_text = tts_text

            # Use MP3 output for CLI playback (afplay doesn't handle OGG well).
            # The TTS tool may auto-convert MP3->OGG, but the original MP3 remains.
            os.makedirs(os.path.join(tempfile.gettempdir(), "hermes_voice"), exist_ok=True)
            mp3_path = os.path.join(
                tempfile.gettempdir(), "hermes_voice",
                f"tts_{time.strftime('%Y%m%d_%H%M%S')}.mp3",
            )

            raw_result = text_to_speech_tool(text=tts_text, output_path=mp3_path)
            try:
                tts_result = json.loads(raw_result) if isinstance(raw_result, str) else {}
            except Exception:
                tts_result = {}

            # The tool result is authoritative — it may return multiple files
            # for long-form chunked output. Play each in order.
            play_paths = tts_result.get("file_paths") or [
                tts_result.get("file_path") or mp3_path
            ]
            for play_path in play_paths if tts_result.get("success") else []:
                if os.path.isfile(play_path) and os.path.getsize(play_path) > 0:
                    play_audio_file(play_path)
            # Clean up all generated files (play_paths + mp3_path + ogg variants)
            cleanup_paths = set(play_paths + [mp3_path, mp3_path.rsplit(".", 1)[0] + ".ogg"])
            for path in cleanup_paths:
                if os.path.isfile(path):
                    try:
                        os.unlink(path)
                    except OSError:
                        pass
        except Exception as e:
            logger.warning("Voice TTS playback failed: %s", e)
            _cprint(f"{_DIM}TTS playback failed: {e}{_RST}")
        finally:
            self._voice_tts_done.set()


    def _voice_full_duplex_listener(self) -> None:
        """Full-duplex agent-turn listener: mic live for the WHOLE turn.

        Armed at utterance-submit (chat() start in continuous voice mode) and
        disarmed when the turn is fully done (agent finished + TTS played).
        Replaces the old per-playback ``_voice_barge_in_monitor``, which only
        listened while TTS audio was playing — during LLM generation the mic
        was dead, so the user could not interject by voice at all (and the
        playback monitor calibrated against its own speaker bleed, making
        the trigger unreachable; see tools.voice_mode.full_duplex_listen).

        Phase behaviour:

        * generation (no TTS audio yet): speech interrupts the in-flight
          agent turn via ``self.agent.interrupt()`` — the same seam the
          typed/Ctrl+C interrupt uses — and the captured utterance is
          submitted as the next message.
        * playback: speech cuts TTS (pipeline stop event + stop_playback)
          and the interruption is captured with pre-roll and submitted.

        The stop phrase ends the voice chat in BOTH phases (a stop during
        generation means "stop everything": the turn is already interrupted
        at trip time, then ``_voice_submit_barge_utterance`` disables voice
        mode).
        """
        fd_active = getattr(self, "_voice_fd_active", None)
        if fd_active is None:
            fd_active = threading.Event()
            self._voice_fd_active = fd_active
        if fd_active.is_set():
            return  # one listener owns the mic for this turn
        fd_active.set()
        try:
            from hermes_cli.config import load_config
            voice_cfg = load_config().get("voice") or {}
            if not (isinstance(voice_cfg, dict) and voice_cfg.get("barge_in", True)):
                return
            from tools.voice_mode import (
                full_duplex_listen,
                is_audio_output_active,
                stop_playback,
            )

            try:
                _mult = float(voice_cfg.get("barge_in_threshold_multiplier", 0) or 0)
            except (TypeError, ValueError):
                _mult = 0.0
            try:
                _grace_ms = int(float(voice_cfg.get("barge_in_grace_seconds", 0.5)) * 1000)
            except (TypeError, ValueError):
                _grace_ms = 500

            tts_done = getattr(self, "_voice_tts_done", None)

            def _should_stop() -> bool:
                if not (getattr(self, "_voice_mode", False) and getattr(self, "_voice_continuous", False)):
                    return True
                if getattr(self, "_agent_running", False):
                    return False
                # Agent finished — keep listening until TTS fully played.
                if tts_done is not None and not tts_done.is_set():
                    return False
                return not is_audio_output_active()

            def _on_trigger(phase: str) -> None:
                # Latch BEFORE cutting anything: suppresses process_loop's
                # auto-restart until the capture is submitted.
                self._voice_barge_capture.set()
                self._voice_barge_phase = phase
                if phase == "playback":
                    logger.debug(
                        "TTS CUT: full-duplex listener tripped during playback"
                    )
                    from tools.tts_streaming import mark_speech_interrupted
                    mark_speech_interrupted()
                    _pipe_stop = getattr(self, "_voice_tts_stop", None)
                    if _pipe_stop is not None:
                        _pipe_stop.set()
                    stop_playback()
                else:
                    # Generation phase: no audio to cut — interrupt the
                    # in-flight agent turn (same seam as typed interrupt).
                    logger.debug(
                        "full-duplex listener tripped during generation — "
                        "interrupting agent turn"
                    )
                    _pipe_stop = getattr(self, "_voice_tts_stop", None)
                    if _pipe_stop is not None:
                        _pipe_stop.set()  # never let the stale reply speak
                    try:
                        if self.agent is not None and getattr(self, "_agent_running", False):
                            _cprint(f"\n{_DIM}🎤 Voice interjection — interrupting…{_RST}")
                            self.agent.interrupt()
                    except Exception as e:
                        logger.debug("voice interjection interrupt failed: %s", e)

            wav_path = full_duplex_listen(
                _should_stop,
                is_playing=is_audio_output_active,
                on_trigger=_on_trigger,
                multiplier=_mult or None,
                grace_ms=max(0, _grace_ms),
            )
            if wav_path and self._voice_barge_capture.is_set():
                self._voice_submit_barge_utterance(wav_path)
            else:
                self._voice_barge_capture.clear()
        except Exception as e:
            self._voice_barge_capture.clear()
            logger.debug("Voice full-duplex listener failed: %s", e)
        finally:
            fd_active.clear()

    def _voice_submit_barge_utterance(self, wav_path: str) -> None:
        """Transcribe a barge-captured interruption and queue it as the next turn."""
        submitted = False
        try:
            from tools.voice_mode import transcribe_recording
            result = transcribe_recording(wav_path, model=self._voice_stt_model())
            transcript = (result.get("transcript") or "").strip() if result.get("success") else ""
            if transcript:
                from tools.voice_mode import is_voice_stop_phrase
                if is_voice_stop_phrase(transcript):
                    _cprint(f"\n{_DIM}Stop phrase detected — ending voice chat.{_RST}")
                    self._disable_voice_mode()
                    return
                # Fail-closed echo guard (#75780): a playback-phase capture
                # has no acoustic echo cancellation, so speaker bleed alone
                # can trip the barge trigger. If the transcript is a close
                # match for what Hermes just spoke, treat it as self-capture
                # instead of queuing it as a user turn.
                if getattr(self, "_voice_barge_phase", None) == "playback":
                    from tools.voice_mode import is_tts_echo
                    if is_tts_echo(transcript, getattr(self, "_voice_last_tts_text", "")):
                        logger.debug(
                            "Dropping playback-phase barge transcript as TTS echo: %r",
                            transcript,
                        )
                        _cprint(f"\n{_DIM}Ignored likely TTS echo (not queued).{_RST}")
                        return
                self._pending_input.put(_VoiceInputMessage(transcript))
                submitted = True
            elif not result.get("success"):
                _cprint(f"\n{_DIM}Transcription failed: {result.get('error', 'Unknown error')}{_RST}")
        except Exception as e:
            _cprint(f"\n{_DIM}Voice processing error: {e}{_RST}")
        finally:
            try:
                if os.path.isfile(wav_path):
                    os.unlink(wav_path)
            except OSError:
                pass
            self._voice_barge_capture.clear()
            self._voice_barge_phase = None
            # No usable transcript: hand the mic back to the normal loop.
            if not submitted and self._voice_mode and self._voice_continuous and not self._voice_recording:
                self._voice_restart_recording_async()

    def _voice_beeps_enabled(self) -> bool:
        """Return whether CLI voice mode should play record start/stop beeps."""
        try:
            from hermes_cli.config import load_config
            from utils import is_truthy_value
            voice_cfg = load_config().get("voice", {})
            if isinstance(voice_cfg, dict):
                # is_truthy_value handles quoted YAML strings like "false"
                # which bool() would misread as True (#49883).
                return is_truthy_value(voice_cfg.get("beep_enabled", True), default=True)
        except Exception:
            pass
        return True

    def _enable_voice_mode(self):
        """Enable voice mode after checking requirements."""
        if self._voice_mode:
            _cprint(f"{_DIM}Voice mode is already enabled.{_RST}")
            return

        from tools.voice_mode import check_voice_requirements, detect_audio_environment

        # Environment detection -- warn and block in incompatible environments
        env_check = detect_audio_environment()
        if not env_check["available"]:
            _cprint(f"\n{_ACCENT}Voice mode unavailable in this environment:{_RST}")
            for warning in env_check["warnings"]:
                _cprint(f"  {_DIM}{warning}{_RST}")
            return

        reqs = check_voice_requirements()
        if not reqs["available"]:
            _cprint(f"\n{_ACCENT}Voice mode requirements not met:{_RST}")
            for line in reqs["details"].split("\n"):
                _cprint(f"  {_DIM}{line}{_RST}")
            if reqs["missing_packages"]:
                if _is_termux_environment():
                    _cprint(f"\n  {_BOLD}Option 1: pkg install termux-api{_RST}")
                    _cprint(f"  {_DIM}Then install/update the Termux:API Android app for microphone capture{_RST}")
                    _cprint(f"  {_BOLD}Option 2: pkg install python-numpy portaudio && python -m pip install sounddevice{_RST}")
                else:
                    _cprint(f"\n  {_BOLD}Install: {sys.executable} -m pip install {' '.join(reqs['missing_packages'])}{_RST}")
            return

        with self._voice_lock:
            self._voice_mode = True

        # Check config for auto_tts (shape-safe — malformed ``voice:`` YAML
        # leaves ``voice_config`` as a non-dict, so guard before .get()).
        try:
            from hermes_cli.config import load_config
            _raw_voice = load_config().get("voice")
            voice_config = _raw_voice if isinstance(_raw_voice, dict) else {}
            if voice_config.get("auto_tts", False):
                with self._voice_lock:
                    self._voice_tts = True
        except Exception:
            pass

        # Voice mode instruction is injected as a user message prefix (not a
        # system prompt change) to avoid invalidating the prompt cache.  See
        # _voice_message_prefix property and its usage in _process_message().

        tts_status = " (TTS enabled)" if self._voice_tts else ""
        # Use the startup-pinned cache so the advertised shortcut always
        # matches the live prompt_toolkit binding — reading live config
        # here would drift after a mid-session config edit (Copilot
        # round-14 on #19835, same class as round-13).
        _ptt_display = self._voice_record_key_label()
        _cprint(f"\n{_ACCENT}Voice mode enabled{tts_status}{_RST}")
        _cprint(f"  {_DIM}{_ptt_display} to start/stop recording{_RST}")
        # Spoken-stop hint sourced from voice.stop_phrases (first entry); the
        # helper returns "" when stop phrases are disabled — show no hint then.
        try:
            from tools.voice_mode import voice_stop_hint
            _stop_hint = voice_stop_hint()
        except Exception:
            _stop_hint = ""
        if _stop_hint:
            _cprint(f"  {_DIM}{_stop_hint}{_RST}")
        _cprint(f"  {_DIM}/voice tts  to toggle speech output{_RST}")
        _cprint(f"  {_DIM}/voice off  to disable voice mode{_RST}")

    def _typed_voice_stop(self, user_input) -> bool:
        """Typed bare stop phrase during an active voice chat ends the chat.

        Saying "stop" ends the voice chat (PR #73106); TYPING the same bare
        stop phrase while voice mode is on must behave identically instead of
        sending "stop" to the agent as a turn. Guarded on voice mode being ON
        — typed "stop" outside voice chat passes through to the agent exactly
        as before. Reuses ``is_voice_stop_phrase`` (same config
        ``voice.stop_phrases``, same exact-match semantics), so longer typed
        messages containing "stop" are never swallowed.
        """
        if not isinstance(user_input, str):
            return False
        with self._voice_lock:
            voice_on = self._voice_mode or self._voice_continuous
        if not voice_on:
            return False
        try:
            from tools.voice_mode import is_voice_stop_phrase
            if not is_voice_stop_phrase(user_input):
                return False
        except Exception:
            return False
        _cprint(f"\n{_DIM}Stop phrase typed — ending voice chat.{_RST}")
        self._disable_voice_mode()
        return True

    def _disable_voice_mode(self):
        """Disable voice mode, cancel any active recording, and stop TTS."""
        recorder = None
        with self._voice_lock:
            if self._voice_recording and self._voice_recorder:
                self._voice_recorder.cancel()
                self._voice_recording = False
            recorder = self._voice_recorder
            self._voice_mode = False
            self._voice_tts = False
            self._voice_continuous = False

        # Shut down the persistent audio stream in background
        if recorder is not None:
            def _bg_shutdown(rec=recorder):
                try:
                    rec.shutdown()
                except Exception:
                    pass
            threading.Thread(target=_bg_shutdown, daemon=True).start()
            self._voice_recorder = None

        # Stop any active TTS playback (file player + streaming pipeline)
        try:
            if self._voice_tts_stop is not None:
                logger.info("TTS CUT: _disable_voice_mode setting stop event")
                self._voice_tts_stop.set()
            from tools.voice_mode import stop_playback
            stop_playback()
        except Exception:
            pass
        self._voice_tts_done.set()

        _cprint(f"\n{_DIM}Voice mode disabled.{_RST}")

    # ── Wake word ("Hey Hermes") ─────────────────────────────────────────
    #
    # An always-on hotword listener (tools/wake_word.py) that, on detecting
    # the wake phrase, starts a fresh session and captures one utterance via
    # the existing voice pipeline — the "Hey Siri" pattern, fully on-device.
    #
    # The detector holds the microphone, so it must be paused while a voice
    # turn records (two input streams on one device is unreliable). On wake we
    # pause it and mark the system suspended; a lightweight watchdog resumes it
    # once the turn finishes and the CLI is idle again — covering every exit
    # path (transcript submitted, no speech, or transcription error) without
    # threading resume logic through the voice machinery.

    def _maybe_start_wake_word(self):
        """Start the wake-word listener at CLI startup if this surface is eligible."""
        try:
            from tools.wake_word import wake_surface_enabled
            if not wake_surface_enabled("cli"):
                return
        except Exception:
            return
        self._start_wake_word_listener(announce=True)

    def _start_wake_word_listener(self, announce: bool = False) -> bool:
        """Build + start the hotword detector. Returns True on success."""
        try:
            from tools.wake_word import (
                check_wake_word_requirements,
                load_wake_word_config,
                owns_listener,
                start_listening,
            )
        except Exception as e:
            if announce:
                _cprint(f"{_DIM}Wake word unavailable: {e}{_RST}")
            return False

        if getattr(self, "_wake_word_active", False) and owns_listener(self):
            if announce:
                _cprint(f"{_DIM}Wake word is already listening.{_RST}")
            return True
        self._wake_word_active = False

        cfg = load_wake_word_config()
        reqs = check_wake_word_requirements(cfg)
        if not reqs["available"]:
            if announce:
                _cprint(f"\n{_ACCENT}Wake word requirements not met:{_RST}")
                if reqs.get("hint"):
                    _cprint(f"  {_DIM}{reqs['hint']}{_RST}")
            return False

        if announce and not reqs.get("deps_available", True):
            # Fresh install: the engine constructor lazy-installs its deps
            # (onnxruntime is a large wheel) — tell the user why this is slow.
            _cprint(f"{_DIM}Installing wake word engine (first use — this may take a minute)...{_RST}")

        self._wake_start_new_session = bool(cfg.get("start_new_session", True))
        try:
            start_listening(self._on_wake_word, owner=self, config=cfg)
        except Exception as e:
            if announce:
                _cprint(f"\n{_DIM}Failed to start wake word: {e}{_RST}")
            return False

        self._wake_word_active = True
        self._wake_suspended = False
        global _cli_wake_owner
        _cli_wake_owner = self
        self._start_wake_watchdog()
        if announce:
            _cprint(f"\n{_ACCENT}Wake word listening{_RST} "
                    f"{_DIM}(say \"{reqs['phrase']}\" — /wake off to stop){_RST}")
        return True

    def _stop_wake_word_listener(self, announce: bool = False):
        """Stop and tear down the hotword detector."""
        global _cli_wake_owner
        was_active = getattr(self, "_wake_word_active", False)
        self._wake_word_active = False
        self._wake_suspended = False
        try:
            from tools.wake_word import stop_listening
            stop_listening(owner=self)
        except Exception:
            pass
        if _cli_wake_owner is self:
            _cli_wake_owner = None
        if announce:
            if was_active:
                _cprint(f"{_DIM}Wake word stopped.{_RST}")
            else:
                _cprint(f"{_DIM}Wake word is not running.{_RST}")

    def _on_wake_word(self):
        """Fired after the detector hears the wake phrase."""
        if getattr(self, "_should_exit", False):
            return
        # Ignore wake while a turn is in flight or the mic is already in use.
        if self._agent_running or self._voice_recording or getattr(self, "_voice_processing", False):
            return

        # Release the mic so STT can capture the command utterance.
        try:
            from tools.wake_word import pause_listening
            if not pause_listening(owner=self):
                self._wake_word_active = False
                return
        except Exception as e:
            logger.debug("wake word pause failed: %s", e)
            return
        self._wake_suspended = True

        # Multi-profile routing: the CLI is a single-profile process, so a
        # phrase enrolled by ANOTHER profile can't be routed here — print the
        # switch command and re-arm rather than answering as the wrong profile.
        try:
            from tools.wake_word import get_last_match
            _match = get_last_match()
        except Exception:
            _match = None
        if _match and _match[1]:
            from tools.wake_word import _active_profile_name
            if _match[1] != _active_profile_name():
                _cprint(f"\n{_DIM}Wake phrase for profile '{_match[1]}' — "
                        f"run: hermes -p {_match[1]}{_RST}")
                self._wake_suspended = True  # watchdog resumes the listener
                return

        _cprint(f"\n{_ACCENT}✦ Wake word detected — listening...{_RST}")
        if getattr(self, "_app", None):
            try:
                self._app.invalidate()
            except Exception:
                pass

        if getattr(self, "_wake_start_new_session", True):
            try:
                self.new_session(silent=True)
            except Exception as e:
                logger.debug("wake word new_session failed: %s", e)

        # Single-utterance capture (not continuous) via the voice pipeline;
        # VAD auto-stop transcribes and queues the transcript for process_loop.
        with self._voice_lock:
            self._voice_mode = True
        self._voice_continuous = False
        try:
            self._voice_start_recording()
        except Exception as e:
            _cprint(f"{_DIM}Wake capture failed: {e}{_RST}")
            # Leave _wake_suspended set; the watchdog resumes once idle.

    def _start_wake_watchdog(self):
        """Resume the paused detector when the CLI returns to a stable idle."""
        if getattr(self, "_wake_watchdog_started", False):
            return
        self._wake_watchdog_started = True

        def _loop():
            idle_polls = 0
            try:
                while getattr(self, "_wake_word_active", False) and not getattr(self, "_should_exit", False):
                    time.sleep(0.25)
                    if not getattr(self, "_wake_suspended", False):
                        idle_polls = 0
                        continue
                    busy = (
                        self._agent_running
                        or self._voice_recording
                        or getattr(self, "_voice_processing", False)
                        or not self._pending_input.empty()
                    )
                    if busy:
                        idle_polls = 0
                        continue
                    # Require a few consecutive idle polls (~0.75s) so we don't
                    # resume in the gap between VAD stop and the agent starting.
                    idle_polls += 1
                    if idle_polls >= 3:
                        idle_polls = 0
                        try:
                            from tools.wake_word import resume_listening
                            if resume_listening(owner=self):
                                self._wake_suspended = False
                            else:
                                self._wake_word_active = False
                        except Exception as e:
                            logger.debug("wake word resume failed: %s", e)
            finally:
                self._wake_watchdog_started = False

        threading.Thread(target=_loop, daemon=True, name="wake-watchdog").start()

    def _show_wake_word_status(self):
        """Show current wake-word listener status."""
        from tools.wake_word import (
            audio_is_silent,
            check_wake_word_requirements,
            is_listening,
            load_wake_word_config,
            owns_listener,
        )

        cfg = load_wake_word_config()
        reqs = check_wake_word_requirements(cfg)
        owned = owns_listener(self)
        state = "LISTENING" if owned and is_listening() else "PAUSED" if owned else "OFF"

        _cprint(f"\n{_BOLD}Wake Word Status{_RST}")
        _cprint(f"  State:       {state}")
        _cprint(f"  Phrase:      \"{reqs['phrase']}\"")
        _cprint(f"  Provider:    {reqs['provider']}")
        _cprint(f"  Surface:     {cfg.get('surface', 'auto')}")
        _cprint(f"  New session: {'yes' if cfg.get('start_new_session', True) else 'no'}")
        if state == "LISTENING" and audio_is_silent():
            _cprint(f"  {_ACCENT}⚠ Microphone delivers only silence — the listener can't hear anything.{_RST}")
            _cprint(f"  {_DIM}On macOS: System Settings > Privacy & Security > Microphone — allow your"
                    f" terminal/Hermes, then /wake off + /wake on.{_RST}")
        if not reqs["available"] and reqs.get("hint"):
            _cprint(f"  {_DIM}{reqs['hint']}{_RST}")
        if not owned:
            _cprint(f"  {_DIM}Enable with /wake on{_RST}")

    def _toggle_voice_tts(self):
        """Toggle TTS output for voice mode."""
        if not self._voice_mode:
            _cprint(f"{_DIM}Enable voice mode first: /voice on{_RST}")
            return

        with self._voice_lock:
            self._voice_tts = not self._voice_tts
        status = "enabled" if self._voice_tts else "disabled"

        if self._voice_tts:
            from tools.tts_tool import check_tts_requirements
            if not check_tts_requirements():
                _cprint(f"{_DIM}Warning: No TTS provider available. Install edge-tts or set API keys.{_RST}")

        _cprint(f"{_ACCENT}Voice TTS {status}.{_RST}")

    def _show_voice_status(self):
        """Show current voice mode status."""
        from tools.voice_mode import check_voice_requirements

        reqs = check_voice_requirements()

        _cprint(f"\n{_BOLD}Voice Mode Status{_RST}")
        _cprint(f"  Mode:      {'ON' if self._voice_mode else 'OFF'}")
        _cprint(f"  TTS:       {'ON' if self._voice_tts else 'OFF'}")
        _cprint(f"  Recording: {'YES' if self._voice_recording else 'no'}")
        # Display the startup-pinned label so /voice status always
        # matches the live prompt_toolkit binding (Copilot round-14 on
        # #19835, same class as round-13). Reading live config here
        # would drift after a mid-session config edit.
        _cprint(f"  Record key: {self._voice_record_key_label()}")
        _cprint(f"\n  {_BOLD}Requirements:{_RST}")
        for line in reqs["details"].split("\n"):
            _cprint(f"    {line}")

    def _persist_prompt_summary(self, icon: str, label: str, detail: str, outcome: str) -> None:
        """Print a one-line scrollback summary of a resolved modal prompt.

        Modal panels (approval / clarify) live in the prompt_toolkit layout and
        vanish on the next repaint, so the question and the decision leave no
        trace in the terminal scrollback. When display.persist_prompts is on
        (default), emit a dim single line after the prompt resolves so the
        decision survives in chat history.
        """
        if not CLI_CONFIG.get("display", {}).get("persist_prompts", True):
            return
        detail = " ".join(detail.split())
        if len(detail) > 120:
            detail = detail[:119] + "…"
        outcome = " ".join(outcome.split())
        if len(outcome) > 120:
            outcome = outcome[:119] + "…"
        _cprint(f"\n{_DIM}{icon} {label}: {detail} → {outcome}{_RST}")

    def _clarify_callback(self, question, choices, multi_select=False, questions=None):
        """
        Platform callback for the clarify tool. Called from the agent thread.

        Sets up the interactive selection UI (or freetext prompt for open-ended
        questions), then blocks until the user responds via the prompt_toolkit
        key bindings.  If no response arrives within the configured timeout the
        question is dismissed and the agent is told to decide on its own.

        When ``multi_select`` is True, shows checkboxes and the user can
        select multiple options with Space, confirming with Enter.

        When ``questions`` is a non-empty list (batch clarify, issue #18450),
        the panel switches to the A-compact multi-question layout and the
        return value is a dict ``{"answers": {qid: raw_answer}}`` (plus
        ``"timed_out": True`` when the deadline expired with only partial
        answers). The single-question path below is unchanged.
        """
        import time as _time

        from tools.clarify_gateway import resolve_clarify_timeout

        if questions:
            return self._clarify_callback_batch(questions)

        # Canonical clarify timeout, shared with the gateway/TUI path. `<= 0`
        # means unlimited (never auto-skip mid-think) → a null deadline.
        timeout = resolve_clarify_timeout(CLI_CONFIG)
        response_queue = queue.Queue()
        is_open_ended = not choices
        # multi-select support: only active when multi_select is True and choices exist
        effective_multi = multi_select and not is_open_ended

        self._clarify_state = {
            "question": question,
            "choices": choices if not is_open_ended else [],
            "selected": 0,
            # multi-select support
            "multi_select": effective_multi,
            "selected_indices": set() if effective_multi else None,
            "response_queue": response_queue,
        }
        self._clarify_deadline = None if timeout <= 0 else _time.monotonic() + timeout
        # Open-ended questions skip straight to freetext input
        self._clarify_freetext = is_open_ended
        self._clarify_multi_base = None

        # Trigger an immediate prompt_toolkit repaint from this (non-main)
        # thread. Modal prompts must paint at once and must not be gated by the
        # _invalidate throttle / resize guard — see _paint_now / _invalidate (#41098).
        self._paint_now()

        # Poll for the user's response. The countdown in the hint line updates
        # on each repaint; refresh it once a second so the timer stays visible
        # while we wait. Selection changes (↑/↓) trigger instant repaints via
        # the key bindings.
        _last_countdown_refresh = _time.monotonic()
        while True:
            try:
                result = response_queue.get(timeout=1)
                self._clarify_deadline = None
                self._persist_prompt_summary("?", "Clarify", question, str(result))
                return result
            except queue.Empty:
                # None deadline = unlimited: never auto-skip, just keep polling.
                if self._clarify_deadline is not None:
                    remaining = self._clarify_deadline - _time.monotonic()
                    if remaining <= 0:
                        break
                now = _time.monotonic()
                if now - _last_countdown_refresh >= 1.0:
                    _last_countdown_refresh = now
                    self._paint_now()

        # Timed out — tear down the UI and let the agent decide
        self._clarify_state = None
        self._clarify_freetext = False
        self._clarify_deadline = None
        self._clarify_multi_base = None
        self._paint_now()
        _cprint(f"\n{_DIM}(clarify timed out after {timeout}s — agent will decide){_RST}")
        return (
            "The user did not provide a response within the time limit. "
            "Use your best judgement to make the choice and proceed."
        )

    # --- Batch clarify (multi-question, issue #18450) -----------------------

    def _clarify_batch_set_active(self, state, index) -> None:
        """Point the batch clarify panel at question ``index``.

        Mirrors the active question's data into the flat keys the existing
        single-question keybindings and renderer read (``question``,
        ``choices``, ``selected``, ``multi_select``, ``selected_indices``),
        so ↑/↓/Space/number keys operate on the active question unchanged.
        Open-ended questions drop straight into freetext, matching the
        single-question path. Re-visiting an answered question restores the
        cursor to the earlier selection (choice answers highlight their row,
        an "Other" answer highlights the Other row) so the user can see and
        edit what they picked.
        """
        questions_list = state["questions"]
        index = max(0, min(index, len(questions_list) - 1))
        entry = questions_list[index]
        state["active"] = index
        state["question"] = entry["question"]
        state["choices"] = entry["choices"] or []
        state["selected"] = 0
        state["multi_select"] = bool(entry["multi_select"])
        state["selected_indices"] = set() if entry["multi_select"] else None
        self._clarify_freetext = not entry["choices"]
        self._clarify_multi_base = None
        # Restore the earlier answer's cursor/checkbox position on re-visit.
        meta = (state.get("answer_meta") or {}).get(entry["qid"])
        choices = entry["choices"] or []
        if meta is None:
            return
        if meta.get("kind") == "choice":
            answer = state["answers"].get(entry["qid"])
            if answer in choices:
                state["selected"] = choices.index(answer)
        elif meta.get("kind") == "other":
            state["selected"] = len(choices)
        elif meta.get("kind") == "multi":
            checked = set()
            for label in meta.get("choices") or []:
                if label in choices:
                    checked.add(choices.index(label))
            if meta.get("other_text"):
                checked.add(len(choices))
            state["selected_indices"] = checked

    def _clarify_batch_lock(self, state, answer, meta=None) -> None:
        """Lock ``answer`` for the active batch question and advance.

        Overwrites any earlier answer for the same question (locked answers
        stay editable until the batch completes). ``meta`` records how the
        answer was produced ({"kind": "choice"|"other"|"multi", ...}) so a
        re-visit can restore the cursor and prefill an "Other" edit. Advances
        ``active`` to the next unanswered question; when every question has
        an answer, puts the answers dict on the response queue and tears down
        the panel.
        """
        entry = state["questions"][state["active"]]
        state["answers"][entry["qid"]] = answer
        state.setdefault("answer_meta", {})[entry["qid"]] = meta or {"kind": "choice"}
        self._persist_prompt_summary("?", "Clarify", entry["question"], str(answer))
        total = len(state["questions"])
        for offset in range(1, total + 1):
            candidate = (state["active"] + offset) % total
            if state["questions"][candidate]["qid"] not in state["answers"]:
                self._clarify_batch_set_active(state, candidate)
                return
        # Every question answered — resolve the batch.
        try:
            state["response_queue"].put(dict(state["answers"]))
        except Exception:
            pass
        self._clarify_state = None
        self._clarify_freetext = False
        self._clarify_multi_base = None

    def _clarify_batch_enter(self, state) -> None:
        """Enter in batch choice mode: lock the active question's selection.

        Multi-select questions lock a JSON array string of the checked
        labels (the tool core parses it via ``_parse_multi_select_response``).
        Selecting "Other" switches to freetext; the freetext submit path
        locks the typed answer. Entering "Other" on a question whose earlier
        answer was typed prefills the composer with that text for editing.
        """
        choices = state.get("choices") or []
        selected = state.get("selected", 0)
        entry = state["questions"][state["active"]]
        meta = (state.get("answer_meta") or {}).get(entry["qid"]) or {}
        if state.get("multi_select"):
            indices = state.get("selected_indices") or set()
            sorted_idx = sorted(indices)
            selected_choices = [choices[i] for i in sorted_idx if i < len(choices)]
            other_checked = len(choices) in sorted_idx
            if other_checked:
                # Stash the checked real choices (possibly none) so the
                # freetext submit appends the typed answer to the array.
                self._clarify_multi_base = selected_choices
                self._clarify_freetext = True
                self._clarify_prefill = meta.get("other_text") or ""
                return
            self._clarify_batch_lock(
                state,
                json.dumps(selected_choices, ensure_ascii=False),
                meta={"kind": "multi", "choices": selected_choices, "other_text": ""},
            )
            return
        if selected < len(choices):
            self._clarify_batch_lock(
                state, choices[selected], meta={"kind": "choice"}
            )
            return
        # "Other" highlighted → switch to freetext; prefill an earlier typed
        # answer so Enter on an answered Other edits instead of retyping.
        self._clarify_freetext = True
        self._clarify_prefill = (
            meta.get("other_text") or "" if meta.get("kind") == "other" else ""
        )

    def _clarify_callback_batch(self, questions):
        """Batch clarify panel (A-compact): all questions, one active.

        Blocks on the response queue like the single-question path. Returns
        ``{"answers": {qid: raw_answer}}`` when every question is locked, the
        same dict plus ``"timed_out": True`` when the deadline expires with
        partial (or zero) answers, and passes a cancel string through
        unchanged so the tool core resolves the batch empty.
        """
        import time as _time

        from tools.clarify_gateway import resolve_clarify_timeout

        timeout = resolve_clarify_timeout(CLI_CONFIG)
        response_queue = queue.Queue()

        state = {
            "questions": list(questions),
            "answers": {},
            "answer_meta": {},
            "active": 0,
            "response_queue": response_queue,
            # Flat keys mirroring the active question — filled by
            # _clarify_batch_set_active below.
            "question": "",
            "choices": [],
            "selected": 0,
            "multi_select": False,
            "selected_indices": None,
        }
        self._clarify_state = state
        self._clarify_batch_set_active(state, 0)
        self._clarify_deadline = None if timeout <= 0 else _time.monotonic() + timeout
        self._paint_now()

        _last_countdown_refresh = _time.monotonic()
        while True:
            try:
                result = response_queue.get(timeout=1)
                self._clarify_deadline = None
                if isinstance(result, dict):
                    return {"answers": result}
                # Cancel path (Ctrl+C teardown) posts a plain string — pass
                # it through so the tool core resolves the batch empty.
                return result
            except queue.Empty:
                if self._clarify_deadline is not None:
                    remaining = self._clarify_deadline - _time.monotonic()
                    if remaining <= 0:
                        break
                now = _time.monotonic()
                if now - _last_countdown_refresh >= 1.0:
                    _last_countdown_refresh = now
                    self._paint_now()

        # Timed out — keep the answers locked so far and flag the timeout.
        partial = dict(state["answers"])
        self._clarify_state = None
        self._clarify_freetext = False
        self._clarify_deadline = None
        self._clarify_multi_base = None
        self._paint_now()
        _cprint(f"\n{_DIM}(clarify timed out after {timeout}s — locked answers returned){_RST}")
        return {"answers": partial, "timed_out": True}

    def _sudo_password_callback(self) -> str:
        """
        Prompt for sudo password through the prompt_toolkit UI.
        
        Called from the agent thread when a sudo command is encountered.
        Uses the same clarify-style mechanism: sets UI state, waits on a
        queue for the user's response via the Enter key binding.
        """
        import time as _time

        timeout = 45
        response_queue = queue.Queue()

        self._capture_modal_input_snapshot()
        self._sudo_state = {
            "response_queue": response_queue,
        }
        self._sudo_deadline = _time.monotonic() + timeout

        # Modal prompt — paint immediately, bypassing the throttle/resize guard
        # so the prompt can't be dropped and time out unseen (#41098).
        self._paint_now()

        while True:
            try:
                result = response_queue.get(timeout=1)
                self._sudo_state = None
                self._sudo_deadline = 0
                self._restore_modal_input_snapshot()
                self._paint_now()
                if result:
                    _cprint(f"\n{_DIM}  ✓ Password received (cached for session){_RST}")
                else:
                    _cprint(f"\n{_DIM}  ⏭ Skipped{_RST}")
                return result
            except queue.Empty:
                remaining = self._sudo_deadline - _time.monotonic()
                if remaining <= 0:
                    break
                self._paint_now()

        self._sudo_state = None
        self._sudo_deadline = 0
        self._restore_modal_input_snapshot()
        self._paint_now()
        _cprint(f"\n{_DIM}  ⏱ Timeout — continuing without sudo{_RST}")
        return ""

    def _approval_callback(self, command: str, description: str,
                           *, allow_permanent: bool = True,
                           smart_denied: bool = False) -> str:
        """
        Prompt for dangerous command approval through the prompt_toolkit UI.

        Called from the agent thread. Shows a selection UI similar to clarify
        with choices: once / session / always / deny. Smart DENY owner
        overrides show only once / deny. When allow_permanent is False for
        another reason (for example tirith), only 'always' is hidden.
        Long commands also get a 'view' option so the full command can be
        expanded before deciding.

        Uses _approval_lock to serialize concurrent requests (e.g. from
        parallel delegation subtasks) so each prompt gets its own turn
        and the shared _approval_state / _approval_deadline aren't clobbered.
        """
        import time as _time

        with self._approval_lock:
            timeout = int(CLI_CONFIG.get("approvals", {}).get("timeout", 300))
            response_queue = queue.Queue()

            self._approval_state = {
                "command": command,
                "description": description,
                "choices": self._approval_choices(
                    command,
                    allow_permanent=allow_permanent,
                    smart_denied=smart_denied,
                ),
                "selected": 0,
                "response_queue": response_queue,
            }
            self._approval_deadline = _time.monotonic() + timeout

            # Modal prompt — paint immediately, bypassing the throttle/resize
            # guard. A throttled paint here can be silently dropped (250ms
            # window collision or in-flight resize), leaving the panel unseen so
            # the command is denied on timeout without the user ever seeing it
            # (#41098). The countdown refreshes below paint the same way.
            self._paint_now()

            _last_countdown_refresh = _time.monotonic()
            while True:
                try:
                    result = response_queue.get(timeout=1)
                    self._approval_state = None
                    self._approval_deadline = 0
                    self._paint_now()
                    _outcome_labels = {
                        "once": "allowed once",
                        "session": "allowed for session",
                        "always": "added to allowlist",
                        "deny": "denied",
                    }
                    self._persist_prompt_summary(
                        "⚠", "Approval", command,
                        _outcome_labels.get(result, str(result)),
                    )
                    return result
                except queue.Empty:
                    remaining = self._approval_deadline - _time.monotonic()
                    if remaining <= 0:
                        break
                    now = _time.monotonic()
                    if now - _last_countdown_refresh >= 1.0:
                        _last_countdown_refresh = now
                        self._paint_now()

            self._approval_state = None
            self._approval_deadline = 0
            self._paint_now()
            _cprint(f"\n{_DIM}  ⏱ Timeout — denying command{_RST}")
            self._persist_prompt_summary(
                "⚠", "Approval", command, "timed out (no response)",
            )
            return "timeout"

    def _approval_choices(self, command: str, *, allow_permanent: bool = True,
                          smart_denied: bool = False) -> list[str]:
        """Return approval choices for a dangerous command prompt."""
        if smart_denied:
            choices = ["once", "deny"]
        else:
            choices = ["once", "session", "always", "deny"] if allow_permanent else ["once", "session", "deny"]
        if len(command) > 70:
            choices.append("view")
        return choices

    def _computer_use_approval_callback(self, action: str, args: dict, summary: str) -> str:
        """Adapt the generic approval UI for the computer_use tool.

        The computer_use handler expects verdicts of the form
        `approve_once` | `approve_session` | `always_approve` | `deny`.
        The CLI's built-in approval UI returns `once` | `session` | `always`
        | `deny`. Translate between the two.
        """
        # Build a command-ish string so the existing UI renders something
        # meaningful. `summary` is already a one-line human description.
        verdict = self._approval_callback(
            command=f"computer_use: {summary}",
            description=f"Allow computer_use to perform `{action}`?",
        )
        return {
            "once": "approve_once",
            "session": "approve_session",
            "always": "always_approve",
            "deny": "deny",
            "timeout": "timeout",
        }.get(verdict, "deny")

    def _handle_approval_selection(self) -> None:
        """Process the currently selected dangerous-command approval choice."""
        state = self._approval_state
        if not state:
            return

        selected = state.get("selected", 0)
        choices = state.get("choices")
        if not isinstance(choices, list):
            choices = []
        if not (0 <= selected < len(choices)):
            return

        chosen = choices[selected]
        if chosen == "view":
            state["show_full"] = True
            state["choices"] = [choice for choice in choices if choice != "view"]
            if state["selected"] >= len(state["choices"]):
                state["selected"] = max(0, len(state["choices"]) - 1)
            self._invalidate()
            return

        state["response_queue"].put(chosen)
        self._approval_state = None
        self._invalidate()

    def _get_approval_display_fragments(self):
        """Render the dangerous-command approval panel for the prompt_toolkit UI.

        Layout priority: title + command + choices must always render, even if
        the terminal is short or the description is long. Description is placed
        at the bottom of the panel and gets truncated to fit the remaining row
        budget. This prevents HSplit from clipping approve/deny off-screen when
        tirith findings produce multi-paragraph descriptions or when the user
        runs in a compact terminal pane.
        """
        state = self._approval_state
        if not state:
            return []

        def _panel_box_width(title_text: str, content_lines: list[str], min_width: int = 46, max_width: int = 76) -> int:
            term_cols = shutil.get_terminal_size((100, 20)).columns
            longest = max([len(title_text)] + [len(line) for line in content_lines] + [min_width - 4])
            inner = min(max(longest + 4, min_width - 2), max_width - 2, max(24, term_cols - 6))
            return inner + 2

        def _wrap_panel_text(text: str, width: int, subsequent_indent: str = "") -> list[str]:
            wrapped = textwrap.wrap(
                text,
                width=max(8, width),
                replace_whitespace=False,
                drop_whitespace=False,
                subsequent_indent=subsequent_indent,
            )
            return wrapped or [""]

        def _append_panel_line(lines, border_style: str, content_style: str, text: str, box_width: int) -> None:
            inner_width = max(0, box_width - 2)
            lines.append((border_style, "│ "))
            lines.append((content_style, text.ljust(inner_width)))
            lines.append((border_style, " │\n"))

        def _append_blank_panel_line(lines, border_style: str, box_width: int) -> None:
            lines.append((border_style, "│" + (" " * box_width) + "│\n"))

        command = state["command"]
        description = state["description"]
        choices = state["choices"]
        selected = state.get("selected", 0)
        show_full = state.get("show_full", False)

        title = "⚠️  Dangerous Command"
        cmd_display = command
        choice_labels = {
            "once": "Allow once",
            "session": "Allow for this session",
            "always": "Add to permanent allowlist",
            "deny": "Deny",
            "view": "Show full command",
        }

        preview_lines = _wrap_panel_text(description, 60)
        preview_lines.extend(_wrap_panel_text(cmd_display, 60))
        for i, choice in enumerate(choices):
            prefix = '❯ ' if i == selected else '  '
            preview_lines.extend(_wrap_panel_text(
                f"{prefix}{choice_labels.get(choice, choice)}",
                60,
                subsequent_indent="  ",
            ))

        box_width = _panel_box_width(title, preview_lines)
        inner_text_width = max(8, box_width - 2)

        # Pre-wrap the mandatory content — command + choices must always render.
        cmd_wrapped = _wrap_panel_text(cmd_display, inner_text_width)
        if not show_full and "view" in choices and len(cmd_wrapped) > 4:
            cmd_wrapped = cmd_wrapped[:3] + _wrap_panel_text(
                "… (choose Show full command)",
                inner_text_width,
            )

        # (choice_index, wrapped_line) so we can re-apply selected styling below
        choice_wrapped: list[tuple[int, str]] = []
        for i, choice in enumerate(choices):
            label = choice_labels.get(choice, choice)
            # Show number prefix for quick selection (1-9 for items 1-9, 0 for 10th item)
            if i < 9:
                num_prefix = str(i + 1)
            elif i == 9:
                num_prefix = '0'
            else:
                num_prefix = ' '  # No number for items beyond 10th
            if i == selected:
                prefix = f'❯ {num_prefix}. '
            else:
                prefix = f'  {num_prefix}. '
            for wrapped in _wrap_panel_text(f"{prefix}{label}", inner_text_width, subsequent_indent="    "):
                choice_wrapped.append((i, wrapped))

        # Budget vertical space so HSplit never clips the command or choices.
        # Panel chrome (full layout with separators):
        #   top border + title + blank_after_title
        #   + blank_between_cmd_choices + bottom border = 5 rows.
        # In tight terminals we collapse to:
        #   top border + title + bottom border = 3 rows (no blanks).
        #
        # reserved_below: rows consumed below the approval panel by the
        # spinner/tool-progress line, status bar, input area, separators, and
        # prompt symbol. Measured at ~6 rows during live PTY approval prompts;
        # budget 6 so we don't overestimate the panel's room.
        term_rows = shutil.get_terminal_size((100, 24)).lines
        chrome_full = 5
        chrome_tight = 3
        reserved_below = 6

        available = max(0, term_rows - reserved_below)
        mandatory_full = chrome_full + len(cmd_wrapped) + len(choice_wrapped)

        # If the full-chrome panel doesn't fit, drop the separator blanks.
        # This keeps the command and every choice on-screen in compact terminals.
        use_compact_chrome = mandatory_full > available
        chrome_rows = chrome_tight if use_compact_chrome else chrome_full

        # If the command itself is too long to leave room for choices (e.g. user
        # hit "view" on a multi-hundred-character command), truncate it so the
        # approve/deny buttons still render. Keep at least 1 row of command.
        max_cmd_rows = max(1, available - chrome_rows - len(choice_wrapped))
        if len(cmd_wrapped) > max_cmd_rows:
            keep = max(1, max_cmd_rows - 1) if max_cmd_rows > 1 else 1
            cmd_wrapped = cmd_wrapped[:keep] + _wrap_panel_text(
                "… (command truncated — use /logs or /debug for full text)",
                inner_text_width,
            )

        # Allocate any remaining rows to description. The extra -1 in full mode
        # accounts for the blank separator between choices and description.
        mandatory_no_desc = chrome_rows + len(cmd_wrapped) + len(choice_wrapped)
        desc_sep_cost = 0 if use_compact_chrome else 1
        available_for_desc = available - mandatory_no_desc - desc_sep_cost
        # Even on huge terminals, cap description height so the panel stays compact.
        available_for_desc = max(0, min(available_for_desc, 10))

        desc_wrapped = _wrap_panel_text(description, inner_text_width) if description else []
        if available_for_desc < 1 or not desc_wrapped:
            desc_wrapped = []
        elif len(desc_wrapped) > available_for_desc:
            keep = max(1, available_for_desc - 1)
            desc_wrapped = desc_wrapped[:keep] + ["… (description truncated)"]

        # Render: title → command → choices → description (description last so
        # any remaining overflow clips from the bottom of the least-critical
        # content, never from the command or choices). Use compact chrome (no
        # blank separators) when the terminal is tight.
        lines = []
        lines.append(('class:approval-border', '╭' + ('─' * box_width) + '╮\n'))
        _append_panel_line(lines, 'class:approval-border', 'class:approval-title', title, box_width)
        if not use_compact_chrome:
            _append_blank_panel_line(lines, 'class:approval-border', box_width)

        for wrapped in cmd_wrapped:
            _append_panel_line(lines, 'class:approval-border', 'class:approval-cmd', wrapped, box_width)
        if not use_compact_chrome:
            _append_blank_panel_line(lines, 'class:approval-border', box_width)

        for i, wrapped in choice_wrapped:
            style = 'class:approval-selected' if i == selected else 'class:approval-choice'
            _append_panel_line(lines, 'class:approval-border', style, wrapped, box_width)

        if desc_wrapped:
            if not use_compact_chrome:
                _append_blank_panel_line(lines, 'class:approval-border', box_width)
            for wrapped in desc_wrapped:
                _append_panel_line(lines, 'class:approval-border', 'class:approval-desc', wrapped, box_width)

        lines.append(('class:approval-border', '╰' + ('─' * box_width) + '╯\n'))
        return lines

    def _secret_capture_callback(self, var_name: str, prompt: str, metadata=None) -> dict:
        return prompt_for_secret(self, var_name, prompt, metadata)

    def _capture_modal_input_snapshot(self) -> None:
        """Temporarily clear the input buffer and save the user's in-progress draft."""
        if self._modal_input_snapshot is not None or not getattr(self, "_app", None):
            return
        try:
            buf = self._app.current_buffer
            self._modal_input_snapshot = {
                "text": buf.text,
                "cursor_position": buf.cursor_position,
            }
            buf.reset()
        except Exception:
            self._modal_input_snapshot = None

    def _restore_modal_input_snapshot(self) -> None:
        """Restore any draft text that was present before a modal prompt opened."""
        snapshot = self._modal_input_snapshot
        self._modal_input_snapshot = None
        if not snapshot or not getattr(self, "_app", None):
            return
        try:
            buf = self._app.current_buffer
            buf.text = snapshot.get("text", "")
            buf.cursor_position = min(snapshot.get("cursor_position", 0), len(buf.text))
        except Exception:
            pass

    def _clear_active_overlays_for_interrupt(self) -> None:
        """Drain and clear every input-blocking overlay left by an interrupted agent.

        approval/clarify/sudo/secret prompts each block a worker thread on a
        ``response_queue.get()``.  When the agent is interrupted the worker
        thread is torn down, but the overlay's state dict stays set — leaving
        the CLI input gated (``read_only`` condition + keypress filter) with no
        thread servicing the prompt.  The result is a frozen terminal until the
        prompt's own timeout expires.  Push a terminal value onto each queue so
        any still-blocked thread unblocks cleanly, then nil the state out and
        restore the user's pre-modal draft (#14026).

        Safe default per prompt: approval -> "deny", clarify/sudo/secret ->
        cancel (None / empty).  Each step is wrapped so a dead queue can't
        prevent clearing the others.
        """
        if self._approval_state:
            try:
                self._approval_state["response_queue"].put("deny")
            except Exception:
                pass
            self._approval_state = None
        if self._clarify_state:
            try:
                self._clarify_state["response_queue"].put(
                    "The user cancelled. Use your best judgement to proceed."
                )
            except Exception:
                pass
            self._clarify_state = None
            self._clarify_freetext = False
            self._clarify_multi_base = None
        if self._sudo_state:
            try:
                self._sudo_state["response_queue"].put("")
            except Exception:
                pass
            self._sudo_state = None
            self._sudo_deadline = 0
            self._restore_modal_input_snapshot()
        if self._secret_state:
            try:
                self._cancel_secret_capture()
            except Exception:
                self._secret_state = None

    def _submit_secret_response(self, value: str) -> None:
        if not self._secret_state:
            return
        self._secret_state["response_queue"].put(value)
        self._secret_state = None
        self._secret_deadline = 0
        # Modal teardown — paint directly so the secret panel clears at once and
        # isn't held by the _invalidate throttle/resize guard (#41098).
        self._paint_now()

    def _cancel_secret_capture(self) -> None:
        self._submit_secret_response("")

    def _clear_secret_input_buffer(self) -> None:
        if getattr(self, "_app", None):
            try:
                self._app.current_buffer.reset()
            except Exception:
                pass

    def chat(self, message, images: list = None, voice_input: bool = False) -> Optional[str]:
        """
        Send a message to the agent and get a response.
        
        Handles streaming output, interrupt detection (user typing while agent
        is working), and re-queueing of interrupted messages.
        
        Uses a dedicated _interrupt_queue (separate from _pending_input) to avoid
        race conditions between the process_loop and interrupt monitoring. Messages
        typed while the agent is running go to _interrupt_queue; messages typed while
        idle go to _pending_input.
        
        Args:
            message: The user's message (str or multimodal content list)
            images: Optional list of Path objects for attached images
            voice_input: True when the message came from voice transcription
                (gates the concise voice-response prefix, #65827)
            
        Returns:
            The agent's response, or None on error
        """
        # Single-query and direct chat callers do not go through run(), so
        # register secure secret capture here as well.
        set_secret_capture_callback(self._secret_capture_callback)

        # Reset the per-turn interrupt flag. Any subsequent path that
        # discovers an interrupt (below, after run_conversation) will flip
        # this to True. Early returns (credential refresh failure, etc.)
        # leave it False, which is correct — those aren't user interrupts.
        self._last_turn_interrupted = False

        # Refresh provider credentials if needed (handles key rotation transparently)
        if not self._ensure_runtime_credentials():
            return None

        turn_route = self._resolve_turn_agent_config(message)
        if turn_route["signature"] != self._active_agent_route_signature:
            self.agent = None

        # Initialize agent if needed
        if self.agent is None:
            _cprint(f"{_DIM}Initializing agent...{_RST}")
        if not self._init_agent(
            model_override=turn_route["model"],
            runtime_override=turn_route["runtime"],
            request_overrides=turn_route.get("request_overrides"),
        ):
            return None
        agent = self.agent
        if agent is None:
            return None

        # Route image attachments based on the active model's vision capability.
        # "native" → pass pixels as OpenAI-style content parts (adapters
        #            translate for Anthropic/Gemini/Bedrock).
        # "text"   → pre-analyze each image with vision_analyze and prepend the
        #            description as text — works with non-vision models.
        # See agent/image_routing.py for the decision table.
        if images:
            try:
                from agent.image_routing import (
                    build_native_content_parts,
                    decide_image_input_mode,
                )
                from hermes_cli.config import load_config

                _img_model, _img_provider = "", ""
                if isinstance(self.model, dict):
                    _img_model, _ = _split_model_config_default(self.model)
                else:
                    _img_model = str(self.model or "")
                if isinstance(self.provider, dict):
                    _, _img_provider = _split_model_config_default(self.provider)
                else:
                    _img_provider = str(self.provider or "")
                _img_mode = decide_image_input_mode(
                    _img_provider.strip(),
                    _img_model.strip(),
                    load_config(),
                    requested_provider=(self.requested_provider or "").strip(),
                )
            except Exception as _img_exc:
                logging.debug("image_routing decision failed, defaulting to text: %s", _img_exc)
                _img_mode = "text"

            if _img_mode == "native":
                try:
                    _text_for_parts = message if isinstance(message, str) else ""
                    _img_str_paths = [str(p) for p in images]
                    _parts, _skipped = build_native_content_parts(
                        _text_for_parts,
                        _img_str_paths,
                    )
                    if _skipped:
                        _cprint(
                            f"  {_DIM}⚠ skipped {len(_skipped)} unreadable image path(s){_RST}"
                        )
                    if any(p.get("type") == "image_url" for p in _parts):
                        _img_names = ", ".join(Path(p).name for p in _img_str_paths)
                        _cprint(
                            f"  {_DIM}📎 attaching {len(images)} image(s) natively "
                            f"(model supports vision): {_img_names}{_RST}"
                        )
                        message = _parts
                    else:
                        # All images unreadable — fall back to text enrichment.
                        message = self._preprocess_images_with_vision(
                            message if isinstance(message, str) else "", images
                        )
                except Exception as _img_exc:
                    logging.warning("native image attach failed, falling back to text: %s", _img_exc)
                    message = self._preprocess_images_with_vision(
                        message if isinstance(message, str) else "", images
                    )
            else:
                message = self._preprocess_images_with_vision(
                    message if isinstance(message, str) else "", images
                )

        # Expand @ context references (e.g. @file:main.py, @diff, @folder:src/)
        if isinstance(message, str) and "@" in message:
            try:
                from agent.context_references import preprocess_context_references
                from agent.model_metadata import get_model_context_length
                _ctx_len = get_model_context_length(
                    self.model, base_url=self.base_url or "", api_key=self.api_key or "",
                    provider=self.provider or "",
                    config_context_length=getattr(self.agent, "_config_context_length", None) if self.agent else None)
                _ctx_result = preprocess_context_references(
                    message, cwd=os.getcwd(), context_length=_ctx_len)
                if _ctx_result.expanded or _ctx_result.blocked:
                    if _ctx_result.references:
                        _cprint(
                            f"  {_DIM}[@ context: {len(_ctx_result.references)} ref(s), "
                            f"{_ctx_result.injected_tokens} tokens]{_RST}")
                    for w in _ctx_result.warnings:
                        _cprint(f"  {_DIM}⚠ {w}{_RST}")
                    if _ctx_result.blocked:
                        return "\n".join(_ctx_result.warnings) or "Context injection refused."
                    message = _ctx_result.message
            except Exception as e:
                logging.debug("@ context reference expansion failed: %s", e)

        # Sanitize surrogate characters that can arrive via clipboard paste from
        # rich-text editors (Google Docs, Word, etc.).  Lone surrogates are invalid
        # UTF-8 and crash JSON serialization in the OpenAI SDK.
        if isinstance(message, str):
            from run_agent import _sanitize_surrogates
            message = _sanitize_surrogates(message)

        # Keep the exact CLI input dict available until turn-start persistence.
        # Copy the completed agent transcript before appending: otherwise this
        # UI-only staging step mutates ``agent._session_messages`` and exposes a
        # duplicate-prone intermediate snapshot to terminal-close persistence.
        if self.conversation_history is getattr(agent, "_session_messages", None):
            self.conversation_history = list(self.conversation_history)
        # The prior turn's override applies only to its own user dict. Clear it
        # before exposing the next staged input to close persistence; otherwise
        # a shutdown before the worker prologue can write old API-local text as
        # this new user message (#63766).
        persist_lock = getattr(agent, "_session_persist_lock", None)

        def _stage_user_message() -> None:
            agent._persist_user_message_idx = None
            agent._persist_user_message_override = None
            agent._persist_user_message_timestamp = None
            from agent.message_metadata import stamp_message_timestamp

            staged_user_message = stamp_message_timestamp(
                {"role": "user", "content": message}
            )
            agent._pending_cli_user_message = staged_user_message
            self.conversation_history.append(staged_user_message)

        if persist_lock is None:
            _stage_user_message()
        else:
            with persist_lock:
                _stage_user_message()

        ChatConsole().print(f"[{_accent_hex()}]{'─' * 40}[/]")
        print(flush=True)
        
        try:
            # Run the conversation with interrupt monitoring
            result = None

            # Reset streaming display state for this turn
            self._reset_stream_state()
            # Separate from _reset_stream_state because this must persist
            # across intermediate turn boundaries (tool-calling loops) — only
            # reset at the start of each user turn.
            self._reasoning_shown_this_turn = False

            # Full-duplex agent-turn listener (continuous voice mode): arm
            # the mic NOW — at utterance-submit — not when TTS playback
            # starts. It spans generation (speech interrupts the turn) and
            # playback (speech cuts TTS), and disarms itself when the turn
            # is fully done. See _voice_full_duplex_listener.
            if self._voice_mode and self._voice_continuous:
                self._voice_last_tts_text = ""
                threading.Thread(
                    target=self._voice_full_duplex_listener, daemon=True
                ).start()

            # --- Streaming TTS setup ---
            # Any working TTS provider streams sentence-by-sentence as the agent
            # generates tokens: PCM-streaming providers (ElevenLabs, OpenAI) play
            # chunks as they arrive, everything else synthesizes per sentence.
            use_streaming_tts = False
            _streaming_box_opened = False
            _thinking_started = False
            text_queue = None
            tts_thread = None
            stream_callback = None
            stop_event = None
            _tts_normal_exit = False

            if self._voice_tts:
                try:
                    from tools.tts_tool import (
                        _import_sounddevice,
                        check_tts_requirements,
                        stream_tts_to_speaker,
                    )
                    _import_sounddevice()
                    use_streaming_tts = check_tts_requirements()
                except Exception:
                    pass

            if use_streaming_tts:
                text_queue = queue.Queue()
                stop_event = threading.Event()

                # When token streaming is enabled (the common case), the
                # CLI's _stream_delta already renders text token-by-token as
                # the model generates it. Passing a display_callback here too
                # would render every sentence a second time. Only attach the
                # callback when streaming is disabled, so the TTS consumer
                # becomes the sole display path.
                _tts_display_cb = None
                if not self.streaming_enabled:
                    def display_callback(sentence: str):
                        """Called by TTS consumer when a sentence is ready to display + speak."""
                        nonlocal _streaming_box_opened
                        if not _streaming_box_opened:
                            _streaming_box_opened = True
                            w = self._scrollback_box_width(getattr(self.console, "width", 80))
                            # MERCURY FORK: response label from the skin engine.
                            try:
                                from hermes_cli.skin_engine import get_active_skin
                                label = get_active_skin().get_branding("response_label", " ⚕ Hermes ")
                            except Exception:
                                label = " ⚕ Hermes "
                            if self.show_timestamps:
                                label = f"{label}{datetime.now().strftime(getattr(self, 'timestamp_format', '%H:%M'))} "
                            fill = w - 2 - HermesCLI._status_bar_display_width(label)
                            _cprint(f"\n{_ACCENT}╭─{label}{'─' * max(fill - 1, 0)}╮{_RST}")
                        _cprint(f"{_STREAM_PAD}{sentence.rstrip()}")
                    _tts_display_cb = display_callback

                tts_thread = threading.Thread(
                    target=stream_tts_to_speaker,
                    args=(text_queue, stop_event, self._voice_tts_done),
                    kwargs={"display_callback": _tts_display_cb},
                    daemon=True,
                )
                tts_thread.start()
                # Expose the pipeline's stop event so barge-in paths (voice
                # key, full-duplex listener) can cut playback from outside
                # this turn. The full-duplex listener itself was armed at
                # turn start (see above) — it spans generation AND playback.
                self._voice_tts_stop = stop_event

                def stream_callback(delta: str):
                    if text_queue is not None:
                        text_queue.put(delta)
                    # Track what's actually being spoken so a playback-phase
                    # barge capture can be checked against it (echo guard,
                    # #75780).
                    self._voice_last_tts_text = (self._voice_last_tts_text or "") + delta

            # When voice mode is active, prepend a brief instruction so the
            # model responds concisely. The prefix is API-call-local only —
            # run_conversation persists the original clean user message.
            _voice_prefix = ""
            if voice_input and isinstance(message, str):
                _voice_prefix = (
                    "[Voice input — respond concisely and conversationally, "
                    "2-3 sentences max. No code blocks or markdown.] "
                )

            def run_agent():
                nonlocal result
                # Set callbacks inside the agent thread so thread-local storage
                # in terminal_tool is populated for this thread.  The main thread
                # registration (run() line ~9046) is invisible here because
                # _callback_tls is threading.local().  Matches the pattern used
                # by acp_adapter/server.py for ACP sessions.
                set_sudo_password_callback(self._sudo_password_callback)
                set_approval_callback(self._approval_callback)
                try:
                    set_secret_capture_callback(self._secret_capture_callback)
                except Exception:
                    pass
                # Bind this turn's approval session key into the contextvar so
                # ``tools.approval.is_current_session_yolo_enabled()`` resolves
                # against the same key that ``/yolo`` toggles under (see
                # ``_toggle_yolo`` → ``enable_session_yolo(self.session_id)``).
                # Mirrors ``tui_gateway/server.py`` and ``gateway/run.py`` which
                # bind the same contextvar before invoking the agent.
                try:
                    from tools.approval import (
                        reset_current_session_key,
                        set_current_session_key,
                    )
                    _approval_session_token = set_current_session_key(
                        self.session_id or "default"
                    )
                except Exception:
                    reset_current_session_key = None  # type: ignore[assignment]
                    _approval_session_token = None
                agent_message = _voice_prefix + message if _voice_prefix else message
                # Prepend pending notes via _prepend_note_to_message, which
                # handles both plain-string and multimodal content-parts list
                # messages. Naive ``note + "\n\n" + agent_message`` crashed with
                # TypeError when an image was attached (agent_message is a list)
                # and a /model or /reload-skills note was queued for the turn.
                _msn = getattr(self, '_pending_model_switch_note', None)
                if _msn:
                    agent_message = _prepend_note_to_message(agent_message, _msn)
                    self._pending_model_switch_note = None
                # Prepend pending /reload-skills note so the model sees which
                # skills were added/removed before handling this turn. Same
                # one-shot queue pattern as the model-switch note above.
                _srn = getattr(self, '_pending_skills_reload_note', None)
                if _srn:
                    agent_message = _prepend_note_to_message(agent_message, _srn)
                    self._pending_skills_reload_note = None
                # Barged mid-speech (VAD or record key)? Tell the model it was
                # cut off — same one-shot, API-local note channel as above.
                from tools.tts_streaming import SPEECH_INTERRUPTED_NOTE, take_speech_interrupted
                if take_speech_interrupted():
                    agent_message = _prepend_note_to_message(agent_message, SPEECH_INTERRUPTED_NOTE)
                _moa_cfg = getattr(self, "_pending_moa_config", None)
                self._pending_moa_config = None
                if _moa_cfg is None:
                    _moa_cfg = None
                # Model/skill notes and voice instructions are API-local. Keep
                # the original staged input as the durable transcript value so a
                # close-path marker follows the same dict into turn setup rather
                # than producing a second noted user row (#63766).
                _persist_clean_user_message = (
                    message if (_voice_prefix or agent_message != message) else None
                )
                _one_turn_model_restore = getattr(
                    self, "_pending_one_turn_model_restore", None
                )
                self._pending_one_turn_model_restore = None
                try:
                    result = self.agent.run_conversation(
                        user_message=agent_message,
                        conversation_history=self.conversation_history[:-1],  # Exclude the message we just added
                        stream_callback=stream_callback,
                        task_id=self.session_id,
                        persist_user_message=_persist_clean_user_message,
                        moa_config=_moa_cfg,
                    )
                    if getattr(self, "_pending_moa_disable_after_turn", False):
                        _restore = getattr(self, "_pending_moa_restore_model", None) or {}
                        for _key, _value in _restore.items():
                            if _value is not None:
                                setattr(self, _key, _value)
                        self.agent = None
                        self._pending_moa_restore_model = None
                        self._pending_moa_disable_after_turn = False
                except Exception as exc:
                    logging.error("run_conversation raised: %s", exc, exc_info=True)
                    _summary = getattr(self.agent, '_summarize_api_error', lambda e: str(e)[:300])(exc)
                    result = {
                        "final_response": f"Error: {_summary}",
                        "messages": [],
                        "api_calls": 0,
                        "completed": False,
                        "failed": True,
                        "error": _summary,
                    }
                finally:
                    if _one_turn_model_restore:
                        self._restore_model_runtime_snapshot(_one_turn_model_restore)
                    # Surface any credit notices queued during the turn (cold-start
                    # seed / per-turn capture) now that the response is done — printing
                    # at this boundary paints cleanly above the prompt instead of being
                    # buried behind the streaming output.
                    self._flush_credit_notices()
                    # Clear thread-local callbacks so a reused thread doesn't
                    # hold stale references to a disposed CLI instance.
                    try:
                        set_sudo_password_callback(None)
                        set_approval_callback(None)
                        set_secret_capture_callback(None)
                    except Exception:
                        pass
                    # Release the per-turn approval session key. ``_session_yolo``
                    # state itself is preserved across turns (so /yolo persists
                    # for the whole CLI run); we just unbind the contextvar so a
                    # reused thread doesn't see stale identity on its next run.
                    if _approval_session_token is not None and reset_current_session_key is not None:
                        try:
                            reset_current_session_key(_approval_session_token)
                        except Exception:
                            pass

            # Start agent in background thread (daemon so it cannot keep the
            # process alive when the user closes the terminal tab — SIGHUP
            # exits the main thread and daemon threads are reaped automatically).
            # Start per-prompt elapsed timer — frozen after the agent thread
            # finishes; reset on the next turn.
            self._prompt_start_time = time.time()
            self._prompt_duration = 0.0
            agent_thread = threading.Thread(target=run_agent, daemon=True)
            agent_thread.start()

            # Ambient "thinking" sound: calm bubble blips while the agent
            # works in voice mode with no audio flowing, so the user knows
            # it's alive during long thinking/tool stretches. Skipped per-blip
            # while TTS speaks, the mic records, or a barge capture is live;
            # stopped outright as soon as the turn ends. voice.thinking_sound
            # gates it (default on); macOS is handled inside (TCC-safe skip).
            _thinking_started = False
            if self._voice_mode:
                try:
                    from tools.voice_mode import start_thinking_sound

                    _thinking_started = start_thinking_sound(
                        should_play=lambda: (
                            self._voice_tts_done.is_set()
                            and not self._voice_recording
                            and not self._voice_barge_capture.is_set()
                        )
                    )
                except Exception:
                    _thinking_started = False

            # Monitor the dedicated interrupt queue while the agent runs.
            # _interrupt_queue is separate from _pending_input, so process_loop
            # and chat() never compete for the same queue.
            # When a clarify question is active, user input is handled entirely
            # by the Enter key binding (routed to the clarify response queue),
            # so we skip interrupt processing to avoid stealing that input.
            interrupt_msg = None
            while agent_thread.is_alive():
                if hasattr(self, '_interrupt_queue'):
                    try:
                        interrupt_msg = self._interrupt_queue.get(timeout=0.1)
                        if interrupt_msg:
                            # If clarify is active, the Enter handler routes
                            # input directly; this queue shouldn't have anything.
                            # But if it does (race condition), don't interrupt —
                            # and don't drop the message either: park it in
                            # _pending_input so it runs as the next turn.
                            if self._clarify_state or self._clarify_freetext:
                                try:
                                    self._pending_input.put(interrupt_msg)
                                except Exception:
                                    pass
                                interrupt_msg = None
                                continue
                            print("\n⚡ New message detected, interrupting...")
                            # Signal TTS to stop on interrupt
                            if stop_event is not None:
                                stop_event.set()
                            self.agent.interrupt(interrupt_msg)
                            # Clear any active overlay states the interrupted agent
                            # left behind.  approval/clarify/sudo/secret prompts gate
                            # input (read_only condition + keypress filter) until
                            # explicitly reset — without this the CLI freezes after
                            # an interrupt until the prompt's own timeout expires (#14026).
                            self._clear_active_overlays_for_interrupt()
                            # Debug: log to file (stdout may be devnull from redirect_stdout)
                            try:
                                _dbg = _hermes_home / "interrupt_debug.log"
                                with open(_dbg, "a", encoding="utf-8") as _f:
                                    _f.write(f"{time.strftime('%H:%M:%S')} interrupt fired: msg={str(interrupt_msg)[:60]!r}, "
                                             f"children={len(self.agent._active_children)}, "
                                             f"parent._interrupt={self.agent._interrupt_requested}\n")
                                    for _ci, _ch in enumerate(self.agent._active_children):
                                        _f.write(f"  child[{_ci}]._interrupt={_ch._interrupt_requested}\n")
                            except Exception:
                                pass
                            break
                    except queue.Empty:
                        # Force prompt_toolkit to flush any pending stdout
                        # output from the agent thread.  Without this, the
                        # StdoutProxy buffer only flushes on renderer passes
                        # triggered by input events — on macOS this causes
                        # the CLI to appear frozen until the user types. (#1624)
                        self._invalidate(min_interval=0.15)
                else:
                    # Fallback for non-interactive mode (e.g., single-query)
                    agent_thread.join(0.1)

            # Wait for the agent thread to finish.  After an interrupt the
            # agent may take a few seconds to clean up (kill subprocess, persist
            # session).  Poll instead of a blocking join so the process_loop
            # stays responsive — if the user sent another interrupt or the
            # agent gets stuck, we can break out instead of freezing forever.
            if interrupt_msg is not None:
                # Interrupt path: poll briefly, then move on.  The agent
                # thread is daemon — it dies on process exit regardless.
                for _wait_tick in range(50):  # 50 * 0.2s = 10s max
                    agent_thread.join(timeout=0.2)
                    if not agent_thread.is_alive():
                        break
                    # Check if user fired ANOTHER interrupt (Ctrl+C sets
                    # _should_exit which process_loop checks on next pass).
                    if getattr(self, '_should_exit', False):
                        break
                if agent_thread.is_alive():
                    logger.warning(
                        "Agent thread still alive after interrupt "
                        "(thread %s). Daemon thread will be cleaned up "
                        "on exit.",
                        agent_thread.ident,
                    )
            else:
                # Normal completion: agent thread should be done already,
                # but guard against edge cases.
                agent_thread.join(timeout=30)

            # Freeze per-prompt elapsed timer once the agent thread has
            # exited (or been abandoned as a daemon after interrupt).
            if self._prompt_start_time is not None:
                self._prompt_duration = max(0.0, time.time() - self._prompt_start_time)
                self._prompt_start_time = None
            # Record when this agent loop finished so the status bar can show
            # idle time since the last final response.
            self._last_turn_finished_at = time.time()

            # Proactively clean up async clients whose event loop is dead.
            # The agent thread may have created AsyncOpenAI clients bound
            # to a per-thread event loop; if that loop is now closed, those
            # clients' __del__ would crash prompt_toolkit's loop on GC.
            try:
                from agent.auxiliary_client import cleanup_stale_async_clients
                cleanup_stale_async_clients()
            except Exception:
                pass

            # Flush any remaining streamed text and close the box
            self._flush_stream()

            # Signal end-of-text to TTS consumer and wait for it to finish
            if use_streaming_tts and text_queue is not None:
                text_queue.put(None)  # sentinel
                if tts_thread is not None:
                    tts_thread.join(timeout=120)
                # Mark normal completion only if the thread actually
                # finished.  If join() timed out and the thread is still
                # alive, leave _tts_normal_exit False so the finally block
                # sets stop_event to kill the runaway worker.
                if tts_thread is not None and not tts_thread.is_alive():
                    _tts_normal_exit = True

            # Drain any remaining agent output still in the StdoutProxy
            # buffer so tool/status lines render ABOVE our response box.
            # The flush pushes data into the renderer queue; the short
            # sleep lets the renderer actually paint it before we draw.
            sys.stdout.flush()
            time.sleep(0.15)

            # Update history with full conversation
            self.conversation_history = result.get("messages", self.conversation_history) if result else self.conversation_history

            # If auto-compression fired mid-turn, the agent created a new
            # continuation session and mutated self.agent.session_id. Sync
            # the CLI's session_id so /status, /resume, title generation,
            # and the exit summary all target the live child session rather
            # than the ended parent. Mirrors the gateway's post-run sync
            # (gateway/run.py around line 9983).
            if (
                self.agent
                and getattr(self.agent, "session_id", None)
                and self.agent.session_id != self.session_id
            ):
                self._transfer_session_yolo(self.session_id, self.agent.session_id)
                self.session_id = self.agent.session_id
                getattr(self, "_write_terminal_breadcrumb", lambda: None)()
                self._pending_title = None

            # Get the final response
            response = result.get("final_response", "") if result else ""

            # Session titling now runs at TURN START (agent/turn_context.py)
            # from the user's message alone, so it is already done — or in
            # flight — by the time we get here, instead of waiting on a final
            # response that a failed or interrupted turn never produces.

            # Handle failed or partial results (e.g., non-retryable errors, rate limits,
            # truncated output, invalid tool calls). Both "failed" and "partial" with
            # an empty final_response mean the agent couldn't produce a usable answer.
            if result and (result.get("failed") or result.get("partial")) and not response:
                error_detail = result.get("error", "Unknown error")
                response = f"Error: {error_detail}"
                # Stop continuous voice mode on persistent errors (e.g. 429 rate limit)
                # to avoid an infinite error → record → error loop
                if self._voice_continuous:
                    self._voice_continuous = False
                    _cprint(f"\n{_DIM}Continuous voice mode stopped due to error.{_RST}")

            # Handle interrupt - check if we were interrupted
            pending_message = None
            _show_interrupt_marker = False
            _interrupted_this_turn = bool(result and result.get("interrupted"))
            # Expose the flag for post-turn hooks (e.g. goal continuation)
            # so they can skip themselves when the turn was user-cancelled.
            self._last_turn_interrupted = _interrupted_this_turn
            if _interrupted_this_turn:
                pending_message = result.get("interrupt_message") or interrupt_msg
                # #60920: Don't append the interruption marker to response so it
                # is never recorded in _OUTPUT_HISTORY by the Panel rendering
                # below. The marker is printed separately with _suspend_output_history
                # after the response Panel to preserve the visual while avoiding
                # duplicates on terminal redraw (_recover_terminal_after_interrupt).
                _show_interrupt_marker = bool(response and pending_message)
            elif interrupt_msg:
                # We fired agent.interrupt(interrupt_msg) but the turn result
                # doesn't acknowledge it. Two ways this happens, both racy:
                #   1. The agent thread had already passed its last interrupt
                #      check (or finished) when the interrupt landed — the turn
                #      completed normally and finalize_turn() never saw the flag.
                #   2. The 10s post-interrupt wait above expired and we
                #      abandoned the daemon thread; `result` is still None.
                # In both cases the user's message must NOT be dropped —
                # re-queue it as the next turn (#interrupt-vacuumed-into-void).
                pending_message = interrupt_msg
                # If the interrupt landed after finalize_turn()'s
                # clear_interrupt(), the stale flag would instantly abort the
                # NEXT turn at its first loop check. Clear it now that we've
                # claimed the message — but ONLY if the agent thread actually
                # exited. If it's still alive (abandoned after the 10s wait),
                # the flag is what makes the wedged tool eventually unwind;
                # clearing it would un-signal that thread.
                try:
                    if (
                        not agent_thread.is_alive()
                        and self.agent
                        and getattr(self.agent, "_interrupt_requested", False)
                    ):
                        self.agent.clear_interrupt()
                except Exception:
                    pass

            response_previewed = result.get("response_previewed", False) if result else False

            # Display reasoning (thinking) box if enabled and available.
            # Skip when streaming already showed reasoning live.  Use the
            # turn-persistent flag (_reasoning_shown_this_turn) instead of
            # _reasoning_stream_started — the latter gets reset during
            # intermediate turn boundaries (tool-calling loops), which caused
            # the reasoning box to re-render after the final response.
            _reasoning_already_shown = getattr(self, '_reasoning_shown_this_turn', False)
            if self.show_reasoning and result and not _reasoning_already_shown:
                reasoning = result.get("last_reasoning")
                if reasoning:
                    w = self._scrollback_box_width()
                    r_label = " Reasoning "
                    r_fill = w - 2 - len(r_label)
                    r_top = f"{_DIM}┌─{r_label}{'─' * max(r_fill - 1, 0)}┐{_RST}"
                    r_bot = f"{_DIM}└{'─' * (w - 2)}┘{_RST}"
                    # Collapse long reasoning to the first 10 lines unless the
                    # user opted into full display via /reasoning full.
                    lines = reasoning.strip().splitlines()
                    if len(lines) > 10 and not getattr(self, "reasoning_full", False):
                        display_reasoning = "\n".join(lines[:10])
                        display_reasoning += f"\n{_DIM}  ... ({len(lines) - 10} more lines — /reasoning full to show){_RST}"
                    else:
                        display_reasoning = reasoning.strip()
                    _cprint(f"\n{r_top}\n{_DIM}{display_reasoning}{_RST}\n{r_bot}")

            if response and not response_previewed:
                # Use skin engine for label/color with fallback
                try:
                    from hermes_cli.skin_engine import get_active_skin
                    _skin = get_active_skin()
                    label = _skin.get_branding("response_label", "⚕ Hermes")
                    _resp_color = _maybe_remap_for_light_mode(_skin.get_color("response_border", "#CD7F32"))
                    _resp_text = _maybe_remap_for_light_mode(_skin.get_color("banner_text", "#FFF8DC"))
                except Exception:
                    label = "⚕ Hermes"
                    _resp_color = _maybe_remap_for_light_mode("#CD7F32")
                    _resp_text = _maybe_remap_for_light_mode("#FFF8DC")

                is_error_response = result and (result.get("failed") or result.get("partial"))
                already_streamed = self._stream_started and self._stream_box_opened and not is_error_response
                if use_streaming_tts and _streaming_box_opened and not is_error_response:
                    # Text was already printed sentence-by-sentence; just close the box
                    w = self._scrollback_box_width()
                    _cprint(f"\n{_ACCENT}╰{'─' * (w - 2)}╯{_RST}")
                elif already_streamed:
                    # Response was already streamed token-by-token with box framing;
                    # _flush_stream() already closed the box. Skip Rich Panel.
                    # A transform hook runs after streaming. Show a suffix for
                    # append-only changes, or the complete replacement otherwise.
                    _post_stream_text = _post_stream_transform_output(response, result)
                    if _post_stream_text.strip():
                        _cprint(_post_stream_text)
                else:
                    _chat_console = ChatConsole()
                    _chat_console.print(Panel(
                        _render_final_assistant_content(response, mode=self.final_response_markdown),
                        title=f"[{_resp_color} bold]{label}[/]",
                        title_align="left",
                        border_style=_resp_color,
                        style=_resp_text,
                        box=rich_box.HORIZONTALS,
                        padding=(1, 0),
                        width=self._scrollback_box_width(),
                    ))

                # Durable, provider-agnostic billing CTA below the response. The
                # response panel carries the full guidance; this pins the single
                # action to take (Nous → /topup, other providers → their billing
                # page) so it stays visible instead of scrolling away as prose.
                if result and result.get("failure_reason") == "billing":
                    _bb = result.get("billing_block") or {}
                    _prov_label = _bb.get("provider_label") or "your provider"
                    if _bb.get("is_nous"):
                        _cta_lines = [
                            "Run [bold]/topup[/] to add credits, or "
                            "[bold]/subscription[/] to change plan.",
                        ]
                    else:
                        _url = _bb.get("billing_url")
                        _cta_lines = [
                            f"Add credits with {_prov_label}"
                            + (f": [bold]{_url}[/]" if _url else ".")
                        ]
                    _cta_lines.append(
                        "Or switch providers with "
                        "[bold]/model <model> --provider <provider>[/]."
                    )
                    try:
                        ChatConsole().print(Panel(
                            "\n".join(_cta_lines),
                            title="[#CD7F32 bold]⚡ Out of credits[/]",
                            title_align="left",
                            border_style="#CD7F32",
                            box=rich_box.HORIZONTALS,
                            padding=(1, 4),
                            width=self._scrollback_box_width(),
                        ))
                    except Exception:
                        pass

            # #60920: Print interruption marker with history suppressed so it
            # is never recorded in _OUTPUT_HISTORY. The marker was previously
            # appended to `response` which caused a duplicate on terminal redraw
            # when _replay_output_history replayed it. Printing it here with
            # _suspend_output_history preserves the user-visible indicator while
            # keeping _OUTPUT_HISTORY clean for replay.
            if _show_interrupt_marker:
                with _suspend_output_history():
                    _cprint(f"\n{_DIM}── [Interrupted — processing new message] ──{_RST}")


            # Focus view: dim recovery line reporting what was hidden this turn
            # (and how to reveal it). Printed after the response so the turn
            # reads prompt → answer → "⋯ N tool lines hidden". Display-only;
            # resets the counter for the next turn.
            try:
                self._emit_focus_recovery_line()
            except Exception:
                pass

            # Play terminal bell when agent finishes (if enabled).
            # Works over SSH — the bell propagates to the user's terminal.
            if self.bell_on_complete:
                sys.stdout.write("\a")
                sys.stdout.flush()

            # Notify when iteration budget was hit
            if result and not result.get("completed") and not result.get("interrupted"):
                _api_calls = result.get("api_calls", 0)
                if _api_calls >= getattr(self.agent, "max_iterations", 500):
                    _max_iter = getattr(self.agent, "max_iterations", 500)
                    _cprint(
                        f"\n{_DIM}⚠ Iteration budget reached "
                        f"({_api_calls}/{_max_iter}) — "
                        f"response may be incomplete{_RST}"
                    )

            # Speak response aloud if voice TTS is enabled
            # Skip batch TTS when streaming TTS already handled it
            if self._voice_tts and response and not use_streaming_tts:
                self._voice_speak_response_async(response)


            # Re-queue the interrupt message (and any that arrived while we were
            # processing the first) as the next prompt for process_loop.
            # Only reached when busy_input_mode == "interrupt" (the default).
            # In "queue" mode Enter routes directly to _pending_input so this
            # block is never hit.
            if pending_message and hasattr(self, '_pending_input'):
                all_parts = [pending_message]
                while not self._interrupt_queue.empty():
                    try:
                        extra = self._interrupt_queue.get_nowait()
                        if extra:
                            all_parts.append(extra)
                    except queue.Empty:
                        break
                combined = "\n".join(all_parts)
                n = len(all_parts)
                preview = combined[:50] + ("..." if len(combined) > 50 else "")
                if n > 1:
                    print(f"\n⚡ Sending {n} messages after interrupt: '{preview}'")
                else:
                    print(f"\n⚡ Sending after interrupt: '{preview}'")
                self._pending_input.put(combined)

            # If a /steer was left over (agent finished before another tool
            # batch could absorb it), deliver it as the next user turn.
            _leftover_steer = result.get("pending_steer") if result else None
            if _leftover_steer and hasattr(self, '_pending_input'):
                preview = _leftover_steer[:60] + ("..." if len(_leftover_steer) > 60 else "")
                print(f"\n⏩ Delivering leftover /steer as next turn: '{preview}'")
                self._pending_input.put(_leftover_steer)

            return response
            
        except Exception as e:
            print(f"Error: {e}")
            return None
        finally:
            # Stop the ambient thinking sound the moment the turn ends —
            # every exit path (normal, error, interrupt) lands here.
            if _thinking_started:
                try:
                    from tools.voice_mode import stop_thinking_sound
                    stop_thinking_sound()
                except Exception:
                    pass
            # Ensure streaming TTS resources are cleaned up even on error.
            # Normal path sends the sentinel at line ~3568; this is a safety
            # net for exception paths that skip it.  Duplicate sentinels are
            # harmless — stream_tts_to_speaker exits on the first None.
            #
            # Only set stop_event on the exception path.  On normal exit
            # (_tts_normal_exit is True) the pipeline has already drained —
            # setting stop_event here would race the playback worker and
            # could cut the final sentence mid-audio.
            if text_queue is not None:
                try:
                    text_queue.put_nowait(None)
                except Exception:
                    pass
            if stop_event is not None and not _tts_normal_exit:
                logger.info("TTS CUT: exception finally block setting stop_event")
                stop_event.set()
            if tts_thread is not None and tts_thread.is_alive():
                tts_thread.join(timeout=5)
    
    def _clear_terminal_on_exit(self):
        """Clear screen + scrollback so nothing is stranded above the exit summary.

        Called from ``_print_exit_summary`` after ``app.run()`` has returned and
        prompt_toolkit has torn down its renderer + restored terminal modes —
        so a direct write to the real stdout fd is safe (the StdoutProxy /
        patch_stdout layer is gone by now).

        Sequence: ``ESC[3J`` (erase scrollback) + ``ESC[2J`` (erase visible
        screen) + ``ESC[H`` (cursor home). Modern terminals on Linux, macOS and
        Windows (Terminal / conhost with VT processing, which prompt_toolkit
        already enables) all honor these. Best-effort: skip silently when
        stdout isn't a real console, and fall back to the platform ``clear`` /
        ``cls`` command if the escape write fails.
        """
        try:
            stream = sys.stdout
            if stream is None or not stream.isatty():
                return
        except Exception:
            return
        try:
            stream.write("\033[3J\033[2J\033[H")
            stream.flush()
            return
        except Exception:
            pass
        # Fallback: shell clear command (rarely needed — escapes work on every
        # VT-capable terminal, but this covers exotic stdout wrappers).
        try:
            os.system("cls" if os.name == "nt" else "clear")
        except Exception:
            pass

    def _persist_active_session_before_close(self):
        """Best-effort SQLite/JSON flush before the CLI marks a session closed.

        ``run_conversation()`` normally persists at turn boundaries, but a
        terminal close/SIGHUP/SIGTERM can unwind the prompt_toolkit app while
        the agent thread still holds the current turn only in memory.  Flush the
        agent's live ``_session_messages`` before ``end_session()`` so resume,
        session_search, and state.db do not lose the interrupted turn.
        """
        agent = getattr(self, "agent", None)
        if not agent or not hasattr(agent, "_persist_session"):
            return

        persist_lock = getattr(agent, "_session_persist_lock", None)

        def _snapshot_and_persist() -> None:
            # This snapshot must share the staging lock with ``chat()``. Without
            # it, close can retain a mutable history baseline just before chat
            # appends its pending dict; the later flush then mistakes that dict
            # for durable history and stamps it without writing a row (#63766).
            messages = getattr(agent, "_session_messages", None)
            pending_cli_message = getattr(agent, "_pending_cli_user_message", None)
            if not isinstance(messages, list):
                messages = getattr(self, "conversation_history", None)
            if not isinstance(messages, list):
                return
            if isinstance(pending_cli_message, dict) and not any(
                message is pending_cli_message for message in messages
            ):
                # The UI has accepted a new input but the worker still exposes its
                # prior snapshot. Include only that staged dict; the baseline below
                # keeps any durable resumed prefix from being re-appended.
                messages = [*messages, pending_cli_message]
            if not messages:
                return

            # A normal turn builds a new list that reuses the resumed-history dicts.
            # Keep that CLI history as the baseline so a signal between assigning
            # ``_session_messages`` and the turn's DB flush cannot append its durable
            # prefix a second time. Once the CLI takes the turn result, however, both
            # names can point at the same live list; passing that alias would mark an
            # unflushed tail durable without writing it. Marker-only persistence is
            # correct only in that alias case.
            conversation_history = getattr(self, "conversation_history", None)
            pending_cli_message = getattr(agent, "_pending_cli_user_message", None)
            if (
                isinstance(conversation_history, list)
                and conversation_history
                and conversation_history[-1] is pending_cli_message
            ):
                # The UI accepted this user message before the agent finished its
                # early persistence. Its dict can already be in ``messages`` but is
                # not durable yet, so exclude it from the resumed-history baseline.
                conversation_history = conversation_history[:-1]
            elif not isinstance(conversation_history, list) or conversation_history is messages:
                conversation_history = None

            # A first-turn close can arrive before the worker builds its cached
            # prompt. Build or restore it before the DB row is created so the
            # durable transcript never leaves a NULL system_prompt cache entry.
            if getattr(agent, "_cached_system_prompt", None) is None:
                try:
                    from agent.conversation_loop import _restore_or_build_system_prompt

                    _restore_or_build_system_prompt(agent, None, conversation_history)
                except Exception:
                    logger.debug("Could not build system prompt during CLI close", exc_info=True)
                    return
            if getattr(agent, "_cached_system_prompt", None) is None:
                return

            agent._ensure_db_session()
            agent._persist_session(messages, conversation_history)
            if getattr(agent, "session_id", None):
                self.session_id = agent.session_id
                getattr(self, "_write_terminal_breadcrumb", lambda: None)()

        try:
            if persist_lock is None:
                _snapshot_and_persist()
            else:
                with persist_lock:
                    _snapshot_and_persist()
        except (Exception, KeyboardInterrupt) as e:
            logger.debug("Could not persist active CLI session before close: %s", e)

    def _print_exit_summary(self, clear_screen: bool = True):
        """Print session resume info on exit, similar to Claude Code.

        Args:
            clear_screen: When True (default), clear the terminal screen and
                scrollback before printing the summary. This is appropriate for
                interactive TUI teardown (#38252). Single-query (-q) mode should
                pass False to preserve the printed answer (#53009).
        """
        if clear_screen:
            # Clear the screen + scrollback before printing the summary so the
            # live bottom chrome (status bar, input box, separator rules) and the
            # rest of the session transcript don't get stranded above the exit
            # summary (#38252). By this point app.run() has returned and
            # prompt_toolkit has restored terminal modes, so writing raw escapes
            # to stdout is safe. ESC[3J clears scrollback, ESC[2J clears the
            # visible screen, ESC[H homes the cursor — so the summary prints at a
            # clean top-left. Falls back to the platform clear command if stdout
            # isn't a TTY-capable stream. Honors NO_COLOR/dumb terminals by
            # skipping silently when there's no real console.
            self._clear_terminal_on_exit()
        print()
        msg_count = len(self.conversation_history)
        if msg_count > 0:
            user_msgs = len([m for m in self.conversation_history if m.get("role") == "user"])
            tool_calls = len([m for m in self.conversation_history if m.get("role") == "tool" or m.get("tool_calls")])
            elapsed = datetime.now() - self.session_start
            hours, remainder = divmod(int(elapsed.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            if hours > 0:
                duration_str = f"{hours}h {minutes}m {seconds}s"
            elif minutes > 0:
                duration_str = f"{minutes}m {seconds}s"
            else:
                duration_str = f"{seconds}s"
            
            # Look up session title for resume-by-name hint
            session_title = None
            if self._session_db:
                try:
                    session_title = self._session_db.get_session_title(self.session_id)
                except Exception:
                    pass

            print("Resume this session with:")
            # Session IDs are profile-constrained, so the resume hint must
            # include `-p <profile>` for non-default profiles. Without this,
            # copying the hint from a non-default profile fails to find the
            # session on the next invocation. The "default" and "custom"
            # profile names use the standard HERMES_HOME, so no -p needed.
            try:
                from hermes_cli.profiles import get_active_profile_name
                _active_profile = get_active_profile_name()
            except Exception:
                _active_profile = "default"
            profile_flag = (
                "" if _active_profile in ("default", "custom") else f" -p {_active_profile}"
            )
            print(f"  hermes --resume {self.session_id}{profile_flag}")
            if session_title:
                print(f"  hermes -c \"{session_title}\"{profile_flag}")
            print()
            print(f"Session:        {self.session_id}")
            if session_title:
                print(f"Title:          {session_title}")
            print(f"Duration:       {duration_str}")
            print(f"Messages:       {msg_count} ({user_msgs} user, {tool_calls} tool calls)")
        else:
            try:
                from hermes_cli.skin_engine import get_active_goodbye
                goodbye = get_active_goodbye("Goodbye! ⚕")
            except Exception:
                goodbye = "Goodbye! ⚕"
            print(goodbye)

    def _get_tui_prompt_symbols(self) -> tuple[str, str]:
        """Return ``(normal_prompt, state_suffix)`` for the active skin.

        ``normal_prompt`` is the full ``branding.prompt_symbol``.
        ``state_suffix`` is what special states (sudo/secret/approval/agent)
        should render after their leading icon.

        When a profile is active (not "default"), the profile name is
        prepended to the prompt symbol: ``coder ❯`` instead of ``❯``.
        """
        try:
            from hermes_cli.skin_engine import get_active_prompt_symbol
            symbol = get_active_prompt_symbol("❯ ")
        except Exception:
            symbol = "❯ "

        symbol = (symbol or "❯ ").rstrip() + " "

        # Prepend profile name when not default
        try:
            from hermes_cli.profiles import get_active_profile_name
            profile = get_active_profile_name()
            if profile not in {"default", "custom"}:
                symbol = f"{profile} {symbol}"
        except Exception:
            pass
        stripped = symbol.rstrip()
        if not stripped:
            return "❯ ", "❯ "

        parts = stripped.split()
        candidate = parts[-1] if parts else ""
        arrow_chars = ("❯", ">", "$", "#", "›", "»", "→")
        if any(ch in candidate for ch in arrow_chars):
            return symbol, candidate.rstrip() + " "

        # Icon-only custom prompts should still remain visible in special states.
        return symbol, symbol

    def _audio_level_bar(self) -> str:
        """Return a visual audio level indicator based on current RMS."""
        _LEVEL_BARS = " ▁▂▃▄▅▆▇"
        rec = getattr(self, "_voice_recorder", None)
        if rec is None:
            return ""
        rms = rec.current_rms
        # Normalize RMS (0-32767) to 0-7 index, with log-ish scaling
        # Typical speech RMS is 500-5000, we cap display at ~8000
        level = min(rms, 8000) * 7 // 8000
        return _LEVEL_BARS[level]

    def _get_tui_prompt_fragments(self):
        """Return the prompt_toolkit fragments for the current interactive state."""
        symbol, state_suffix = self._get_tui_prompt_symbols()
        compact = self._use_minimal_tui_chrome(width=self._get_tui_terminal_width())

        def _state_fragment(style: str, icon: str, extra: str = ""):
            if compact:
                text = icon
                if extra:
                    text = f"{text} {extra.strip()}".rstrip()
                return [(style, text + " ")]
            if extra:
                return [(style, f"{icon} {extra} {state_suffix}")]
            return [(style, f"{icon} {state_suffix}")]

        if self._voice_recording:
            bar = self._audio_level_bar()
            return _state_fragment("class:voice-recording", "●", bar)
        if self._voice_processing:
            return _state_fragment("class:voice-processing", "◉")
        if self._sudo_state:
            return _state_fragment("class:sudo-prompt", "🔐")
        if self._secret_state:
            return _state_fragment("class:sudo-prompt", "🔑")
        if self._approval_state:
            return _state_fragment("class:prompt-working", "⚠")
        if getattr(self, "_slash_confirm_state", None):
            return _state_fragment("class:prompt-working", "⚠")
        if self._clarify_freetext:
            return _state_fragment("class:clarify-selected", "✎")
        if self._clarify_state:
            return _state_fragment("class:prompt-working", "?")
        if self._command_running:
            return _state_fragment("class:prompt-working", self._command_spinner_frame())
        if self._agent_running:
            return _state_fragment("class:prompt-working", self._brand_icon())
        if self._voice_mode:
            return _state_fragment("class:voice-prompt", "🎤")
        return [("class:prompt", symbol)]

    def _get_tui_prompt_text(self) -> str:
        """Return the visible prompt text for width calculations."""
        return "".join(text for _, text in self._get_tui_prompt_fragments())

    def _build_tui_style_dict(self) -> dict[str, str]:
        """Layer the active skin's prompt_toolkit colors over the base TUI style.

        Also rewrites any hex-color tokens in the resulting style strings
        to their light-mode equivalents (via _LIGHT_MODE_REMAP) when the
        terminal is detected as light.  This makes the chrome readable
        on cream Terminal.app backgrounds without per-skin overrides.
        """
        style_dict = dict(getattr(self, "_tui_style_base", {}) or {})
        try:
            from hermes_cli.skin_engine import get_prompt_toolkit_style_overrides
            style_dict.update(get_prompt_toolkit_style_overrides())
        except Exception:
            pass
        # Light-mode remap on the style strings.  Each value is a pt
        # style string like "bg:#1a1a2e #C0C0C0 bold" — split on space,
        # rewrite any "#XXX" tokens (including "bg:#XXX") through the
        # light-mode remap, rejoin.
        #
        # CRITICAL: skip the remap entirely when a style string already
        # specifies its own bg (e.g. status-bar / completion-menu styles
        # with `bg:#1a1a2e ...`).  Those colors were tuned for that
        # specific dark bg and remapping the FG to a dark equivalent
        # would produce dark-on-dark (invisible).  The terminal's BG
        # mode is irrelevant — what matters is the bg the style itself
        # paints.
        try:
            if _detect_light_mode():
                def _remap_value(v: str) -> str:
                    if not v:
                        return v
                    tokens = v.split()
                    has_explicit_bg = any(t.startswith("bg:") for t in tokens)
                    if has_explicit_bg:
                        # The style paints its own bg — leave its fg alone.
                        return v
                    return " ".join(
                        _maybe_remap_for_light_mode(t) if t.startswith("#") else t
                        for t in tokens
                    )
                style_dict = {k: _remap_value(v or "") for k, v in style_dict.items()}
        except Exception:
            pass
        return style_dict

    def _apply_tui_skin_style(self) -> bool:
        """Refresh prompt_toolkit styling for a running interactive TUI."""
        if not getattr(self, "_app", None) or not getattr(self, "_tui_style_base", None):
            return False
        self._app.style = PTStyle.from_dict(self._build_tui_style_dict())
        self._invalidate(min_interval=0.0)
        return True

    # --- Protected TUI extension hooks for wrapper CLIs ---

    def _get_extra_tui_widgets(self) -> list:
        """Return extra prompt_toolkit widgets to insert into the TUI layout.

        Wrapper CLIs can override this to inject widgets (e.g. a mini-player,
        overlay menu) into the layout without overriding ``run()``.  Widgets
        are inserted between the spacer and the status bar.
        """
        return []

    def _register_extra_tui_keybindings(self, kb, *, input_area) -> None:
        """Register extra keybindings on the TUI ``KeyBindings`` object.

        Wrapper CLIs can override this to add keybindings (e.g. transport
        controls, modal shortcuts) without overriding ``run()``.

        Parameters
        ----------
        kb : KeyBindings
            The active keybinding registry for the prompt_toolkit application.
        input_area : TextArea
            The main input widget, for wrappers that need to inspect or
            manipulate user input from a keybinding handler.
        """

    def _build_tui_layout_children(
        self,
        *,
        sudo_widget,
        secret_widget,
        approval_widget,
        slash_confirm_widget=None,
        clarify_widget,
        model_picker_widget=None,
        command_palette_widget=None,
        spinner_widget=None,
        spacer,
        status_bar,
        input_rule_top,
        image_bar,
        input_area,
        input_rule_bot,
        voice_status_bar,
        completions_menu,
    ) -> list:
        """Assemble the ordered list of children for the root ``HSplit``.

        Wrapper CLIs typically override ``_get_extra_tui_widgets`` instead of
        this method.  Override this only when you need full control over widget
        ordering.
        """
        return [
            item for item in [
                Window(height=0),
                sudo_widget,
                secret_widget,
                approval_widget,
                slash_confirm_widget,
                clarify_widget,
                model_picker_widget,
                command_palette_widget,
                spinner_widget,
                spacer,
                *self._get_extra_tui_widgets(),
                getattr(self, "_pet_widget", None),
                getattr(self, "_stash_panel_widget", None),
                status_bar,
                input_rule_top,
                image_bar,
                input_area,
                input_rule_bot,
                voice_status_bar,
                completions_menu,
            ] if item is not None
        ]

    def run(self):
        """Run the interactive CLI loop with persistent input at bottom."""
        if not self._claim_active_session("cli"):
            return

        self._tui_print_startup()
        self._tui_init_run_state()
        kb = self._tui_build_key_bindings()
        layout, style = self._tui_build_layout(kb)

        app = self._tui_build_application(layout, kb, style)
        _disable_prompt_toolkit_cpr_warning(app)
        app.after_render += self._pet_flush_kitty_frame
        from hermes_cli.observability.shared_metrics_startup import cli_prompt_ready_handler
        app.after_render += cli_prompt_ready_handler()
        self._app = app

        # Ghost status-bar lines on resize: pt's renderer scrolls the terminal after each
        # paint, pushing chrome into scrollback where a column-shrink reflows it into
        # duplicates. Wrapping _output_screen_diff keeps its reserve-space branch from firing.
        try:
            # Background: prompt_toolkit's renderer (renderer.py L232-242) explicitly moves the cursor to
            # the bottom of the canvas after painting "to make sure the terminal scrolls up, even when the
            # lower lines of the canvas just contain whitespace". In non-fullscreen mode this scrolls chrome
            # content (status bar, input rules) into terminal scrollback on every render. When the terminal
            # column-shrinks, the emulator reflows the previously rendered full-width rows into multiple
            # narrower rows that get pushed up — leaving ghost duplicates AND polluting scrollback. Same
            # issue as pt #29 (open since 2014), #1675, #1933. Surgical fix: wrap _output_screen_diff so
            # that when its internal `if current_height > previous_screen.height` branch fires (the one that
            # does the bottom-cursor-move), we make it fall through by inflating previous_screen.height
            # first.
            import prompt_toolkit.renderer as _pt_renderer
            from prompt_toolkit.renderer import _output_screen_diff as _orig_osd

            if not getattr(_pt_renderer, "_hermes_osd_patched", False):
                _pt_renderer._output_screen_diff = functools.partial(
                    _hermes_call_output_screen_diff, _orig_osd
                )
                _pt_renderer._hermes_osd_patched = True
        except Exception:
            pass

        _apply_bracketed_paste_timeout_patch()

        self._install_resize_recovery(app)

        threading.Thread(target=self._tui_spinner_loop, daemon=True).start()
        threading.Thread(target=self._tui_process_loop, daemon=True).start()
        # Wake word listener off-thread so a first-run engine install never blocks the prompt.
        threading.Thread(target=self._tui_wake_startup, daemon=True, name="wake-startup").start()

        atexit.register(_run_cleanup)
        self._tui_install_signal_handlers()

        if not self._tui_stdin_usable():
            _run_cleanup()
            self._print_exit_summary()
            return

        try:
            with patch_stdout():
                try:
                    # run_in_terminal() may return either: • a coroutine / Future (prompt_toolkit ≥ 3.0) —
                    # must be scheduled via ensure_future so the coroutine is actually awaited; calling it
                    # bare would leave it unawaited and silently drop the output (fixes #23185 Bug A). •
                    # None (some mocks / older PT builds) — just call the inner function directly since PT
                    # already executed it synchronously. Do NOT fall back to a bare _pt_print when
                    # ensure_future raises, because run_in_terminal already invoked the lambda in that case
                    # (the mock path), which would double-print the line.
                    import asyncio as _aio
                    _aio.get_running_loop().set_exception_handler(self._tui_suppress_closed_loop_errors)
                except Exception:
                    pass  # no running loop -- nothing to patch
                # Record that the app enables focus reporting + mouse tracking so _run_cleanup
                # resets them; extended key modes are popped by the same reset.
                # When multiline shortcuts are on, also ask supported terminals (e.g. iTerm2) to report
                # modified keys distinctly (kitty protocol + modifyOtherKeys); the cleanup reset pops both
                # modes. See #36823.
                _mark_tui_input_modes_active()
                if self._tui_multiline_shortcuts:
                    _enable_extended_enter_keys(app.output)
                self._pet_start_anim()
                app.run()
        except (EOFError, KeyboardInterrupt, BrokenPipeError):
            pass
        except (KeyError, OSError) as _stdin_err:
            # Selector registration failures from broken stdin and I/O errors from a
            # broken stdout during interrupt (EIO is suppressed).
            _errno = getattr(_stdin_err, "errno", None) if isinstance(_stdin_err, OSError) else None
            _msg = str(_stdin_err)
            if _errno == errno.EIO:
                pass
            elif _errno in {errno.EINVAL, errno.EBADF} or any(
                s in _msg for s in ("is not registered", "Bad file descriptor", "Invalid argument")
            ):
                print(_t("cli.startup.stdin_unusable", error=str(_stdin_err)))
            else:
                raise
        finally:
            # A resize right before exit leaves its recovery (and the paints it held) unrun.
            _release_paints()
            self._tui_shutdown()

        # /update relaunch happens here, after prompt_toolkit restored terminal modes, on the
        # main thread (the process_loop thread would skip cleanup / only exit itself on Windows).
        if self._pending_relaunch:
            from hermes_cli.relaunch import relaunch
            relaunch(self._pending_relaunch, preserve_inherited=False)


def _build_cli_from_args(model, toolsets, provider, reasoning, api_key, base_url, max_turns, run_budget, verbose, compact, resume, checkpoints, pass_session_id, ignore_rules, skills):
    """Resolve the toolset list (explicit / coding posture / platform default), construct HermesCLI, and start the background skills preload."""
    toolsets_list = None
    if isinstance(toolsets, str) and toolsets:
        toolsets_list = [t.strip() for t in toolsets.split(",")]
    elif isinstance(toolsets, (list, tuple)) and toolsets:
        # Fire may pass multiple --toolsets as a tuple
        toolsets_list = []
        for t in toolsets:
            toolsets_list.extend([x.strip() for x in t.split(",")] if isinstance(t, str) else [str(t)])
    elif not toolsets:
        # Coding posture inside a code workspace, else the shared platform resolver.
        try:
            from agent.coding_context import coding_selection
            toolsets_list = coding_selection(platform="cli", config=CLI_CONFIG)
        except Exception:
            toolsets_list = None
        if toolsets_list is None:
            from hermes_cli.tools_config import _get_platform_tools
            toolsets_list = sorted(_get_platform_tools(CLI_CONFIG, "cli"))

    parsed_skills = _parse_skills_argument(skills)

    try:
        cli = HermesCLI(
            model=model,
            toolsets=toolsets_list,
            provider=provider,
            reasoning=reasoning,
            api_key=api_key,
            base_url=base_url,
            max_turns=max_turns,
            run_budget=run_budget,
            verbose=verbose,
            compact=compact,
            resume=resume,
            checkpoints=checkpoints,
            pass_session_id=pass_session_id,
            ignore_rules=ignore_rules,
        )
    except ImportError as e:
        # Direct `python cli.py` bypasses cmd_chat's partial-update ImportError handler.
        from hermes_constants import emit_partial_update_hint

        if emit_partial_update_hint(e):
            sys.exit(1)
        raise

    # skills.auto_load rides the same background preload as -s; --ignore-rules skips it with
    # the rest of the auto-injected context. Resolved here (not lazily in the agent) so the
    # session id is real for ${HERMES_SESSION_ID} and -s can dedupe against it.
    from agent.skill_commands import build_auto_load_prompt, resolve_auto_load_skills
    auto_load_names = [] if getattr(cli, "ignore_rules", ignore_rules) else resolve_auto_load_skills(CLI_CONFIG)
    if not auto_load_names:
        cli._auto_load_skills_result = ("", [], [])
    if parsed_skills or auto_load_names:
        # Load the skill payloads in the background: skill_view walks the full skills
        # tree per skill (~0.5s for a large library) and the result is only consumed
        # at agent init, not by the banner. finalize_preloaded_skills() joins the
        # thread before any consumer reads cli.system_prompt.
        def _load_preloaded_skills() -> None:
            try:
                if auto_load_names:
                    cli._auto_load_skills_result = build_auto_load_prompt(task_id=cli.session_id, user_config=CLI_CONFIG)
                if parsed_skills:
                    cli._preload_skills_result = build_preloaded_skills_prompt(
                        parsed_skills, task_id=cli.session_id, excluded_loaded_names=set(cli._auto_load_skills_result[1]))
            except Exception as exc:  # surfaced by finalize
                cli._preload_skills_error = exc

        cli._preload_skills_requested = [*auto_load_names, *(s for s in parsed_skills if s not in auto_load_names)]
        cli._preload_skills_thread = threading.Thread(target=_load_preloaded_skills, name="skills-preload", daemon=True)
        cli._preload_skills_thread.start()
    return cli


def _run_legacy_gateway():
    """Legacy `cli.py --gateway` entry: arm the startup watchdog (before importing the gateway graph), then run it."""
    import asyncio
    with suppress(Exception):
        from hermes_startup_watchdog import arm_startup_watchdog
        arm_startup_watchdog()
    from gateway.run import start_gateway
    print(_t("cli.gateway.starting"))
    asyncio.run(start_gateway())


def _start_worktree_setup(list_tools, list_toolsets, worktree, w):
    """Start isolated-worktree creation (+ tool prewarm) in the background.

    Returns a join callable that publishes ``_active_worktree``/TERMINAL_CWD and
    schedules stale-worktree GC, or None when no worktree is wanted.
    """
    if list_tools or list_toolsets or not (worktree or w or CLI_CONFIG.get("worktree", False)):
        return None
    # Overlap tool discovery with the I/O-bound worktree setup so show_banner() hits a warm
    # cache (~0.4s). Only on the -w path: plain `hermes` has no I/O wait to hide.
    def _prewarm_tools() -> None:
        try:
            import model_tools as _mt
            _mt.get_tool_definitions(quiet_mode=True)
        except Exception:
            logger.debug("tool prewarm failed", exc_info=True)

    threading.Thread(target=_prewarm_tools, name="tool-prewarm", daemon=True).start()
    _sync_base = CLI_CONFIG.get("worktree_sync", True)
    _wt_result: dict = {}

    def _create_worktree() -> None:
        try:
            _wt_result["info"] = _setup_worktree(sync_base=_sync_base)
        except Exception:
            logger.debug("worktree setup failed", exc_info=True)
            _wt_result["info"] = None

    _wt_thread = threading.Thread(target=_create_worktree, name="worktree-setup", daemon=True)
    _wt_thread.start()

    def _worktree_maintenance(repo: str) -> None:
        _prune_stale_worktrees(repo)
        _maintain_pack_health(repo)

    def _join_worktree() -> Optional[Dict[str, str]]:
        _wt_thread.join(timeout=120)
        info = _wt_result.get("info")
        if not info:
            return info
        global _active_worktree
        _active_worktree = info
        os.environ["TERMINAL_CWD"] = info["path"]
        atexit.register(_cleanup_worktree, info)
        # GC stale worktrees AFTER _setup_worktree so they never race on git's worktree
        # metadata (the new tree is immune: <24h age gate + live pid lock); then repack
        # once refs are final so lookups stay fast on multi-agent boxes.
        _repo = _git_repo_root()
        if _repo:
            threading.Thread(target=_worktree_maintenance, args=(_repo,), name="worktree-prune", daemon=True).start()
        return info

    return _join_worktree


def main(
    query: str = None,
    q: str = None,
    oneshot: bool = False,
    image: str = None,
    toolsets: str = None,
    skills: str | list[str] | tuple[str, ...] = None,
    model: str = None,
    provider: str = None,
    reasoning: str = None,
    api_key: str = None,
    base_url: str = None,
    max_turns: int = None,
    run_budget: float = None,
    verbose: Optional[bool] = None,
    quiet: bool = False,
    compact: bool = False,
    list_tools: bool = False,
    list_toolsets: bool = False,
    gateway: bool = False,
    resume: str = None,
    worktree: bool = False,
    w: bool = False,
    checkpoints: bool = False,
    pass_session_id: bool = False,
    output_format: str = "text",
    ignore_user_config: bool = False,
    ignore_rules: bool = False,
):
    """
    Hermes Agent CLI - Interactive AI Assistant
    
    Args:
        query: Query to run. On a real TTY this seeds an interactive session
            (submitted literally as the first turn); with --oneshot/-Q or a
            non-TTY it answers and exits. Alias: -q
        q: Shorthand for --query
        oneshot: With -q: force the legacy answer-and-exit single-query mode
            even on a TTY.
        image: Optional local image path to attach to a single query
        toolsets: Comma-separated list of toolsets to enable (e.g., "web,terminal")
        skills: Comma-separated or repeated list of skills to preload for the session
        model: Model to use (default: anthropic/claude-opus-4-20250514)
        provider: Inference provider ("auto", "openrouter", "nous", "openai-codex", "zai", "kimi-coding", "minimax", "minimax-cn")
        reasoning: Reasoning effort for this run (none|minimal|low|medium|high|xhigh|max|ultra). Overrides agent.reasoning_effort.
        api_key: API key for authentication
        base_url: Base URL for the API
        max_turns: Maximum tool-calling iterations (default: 60)
        verbose: Enable verbose logging
        compact: Use compact display mode
        list_tools: List available tools and exit
        list_toolsets: List available toolsets and exit
        resume: Resume a previous session by its ID (e.g., 20260225_143052_a1b2c3)
        worktree: Run in an isolated git worktree (for parallel agents). Alias: -w
        w: Shorthand for --worktree
    
    Examples:
        python cli.py                            # Start interactive mode
        python cli.py --toolsets web,terminal    # Use specific toolsets
        python cli.py --skills hermes-agent-dev,github-auth
        python cli.py -q "What is Python?"       # Single query mode
        python cli.py -q "Describe this" --image ~/storage/shared/Pictures/cat.png
        python cli.py --list-tools               # List tools and exit
        python cli.py --resume 20260225_143052_a1b2c3  # Resume session
        python cli.py -w                         # Start in isolated git worktree
        python cli.py -w -q "Fix issue #123"     # Single query in worktree
    """
    # UTF-8 stdio on Windows before any print (Rich box-drawing would UnicodeEncodeError on cp1252).
    with suppress(Exception):
        from hermes_cli.stdio import configure_windows_stdio
        configure_windows_stdio()

    os.environ["HERMES_INTERACTIVE"] = "1"  # terminal_tool: interactive sudo prompts with timeout

    if gateway:
        _run_legacy_gateway()
        return

    if not (list_tools or list_toolsets):
        from hermes_cli.process_identity import register_self
        from hermes_cli.shared_profile_warning import shared_profile_warning

        register_self("cli")
        warning = shared_profile_warning()
        if warning:
            print(_t("cli.startup.warning", warning=warning), file=sys.stderr)

    _join_worktree = _start_worktree_setup(list_tools, list_toolsets, worktree, w)
    query = query or q
    # ``hermes chat`` already validated this; the direct Fire entry point gets the same contract.
    if output_format == "stream-json":
        if not query:
            raise ValueError("--format stream-json requires -q/--query")
        quiet = True
    cli = _build_cli_from_args(model, toolsets, provider, reasoning, api_key, base_url, max_turns, run_budget,
                               verbose, compact, resume, checkpoints, pass_session_id, ignore_rules, skills)

    # Join the background worktree creation before anything consumes TERMINAL_CWD.
    # A requested worktree whose setup failed aborts: never silently run without isolation.
    wt_info = _join_worktree() if _join_worktree is not None else None
    if _join_worktree is not None and not wt_info:
        return

    # Inject worktree context into agent's system prompt
    if wt_info:
        wt_note = (
            f"\n\n[System note: You are working in an isolated git worktree at "
            f"{wt_info['path']}. Your branch is `{wt_info['branch']}`. "
            f"Changes here do not affect the main working tree or other agents. "
            f"Remember to commit and push your changes, and create a PR if appropriate. "
            f"The original repo is at {wt_info['repo_root']}.]"
        )
        cli.system_prompt = (cli.system_prompt or "") + wt_note

    if list_tools or list_toolsets:
        cli.show_banner()
        (cli.show_tools if list_tools else cli.show_toolsets)()
        sys.exit(0)

    atexit.register(_run_cleanup)  # interactive mode registers again in run() (idempotent)
    _install_single_query_signal_handlers(cli)

    if query or image:
        _run_single_query_mode(cli, query, image, quiet, oneshot, stream_json=output_format == "stream-json")
        return
    cli.run()


if __name__ == "__main__":
    import fire

    fire.Fire(main)
