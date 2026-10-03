# Mercury-agent sync cycle — 2026-10-01

upstream/main is 22,555 commits ahead of local main (154 ahead, local-only
fix commits). Largest cycle on record by a wide margin — prior record was
5,184 commits / 44 regions (2026-08-11). 57 conflicted files.

Probe worktree: /tmp/merge-probe (detached HEAD at main 5ce05bd4f8, merging
upstream/main 7817bf522a). Live checkout untouched.

Stage plan: 1) mechanical/cosmetic  2) credential-module split + identity
3) Matrix adapter (highest risk, done last)  4) lockfiles + full test batch
+ close-out (ff-only merge onto live main, push, dep reinstall).

## RESOLVED (57/57) — all conflict markers cleared, test-validated

**Real regressions found and fixed during full-suite validation (3 files,
none were conflicts — clean auto-merges that silently dropped fork
hardening):**

1. `plugins/memory/holographic/store.py` + `retrieval.py` — both had
   `from . import holographic as hrr` collapse from the fork's dual-mode
   `try: from . import holographic / except ImportError: import
   holographic` (needed because the test harness sys.path-inserts the
   plugin dir directly, so the package has no parent for a relative
   import). Restored the try/except in both files — confirmed via
   `git diff HEAD` that upstream's merge, not a real conflict, dropped it.
2. `plugins/memory/holographic/retrieval.py::_sanitize_fts_query` — the
   fork returned a sentinel (`__hermes_no_fts_match__`) when every token
   is stopword/too-short; upstream's merge changed the empty-case
   fallback to return the **raw unsanitized query** instead. Restored the
   sentinel: the raw query can still contain bare FTS5 operator chars and
   throw a MATCH syntax error instead of cleanly returning zero rows —
   the exact failure mode the function's own docstring says it exists to
   prevent. `test_sanitizer_empty_returns_no_match_sentinel` now passes.

**Confirmed upstream bug, NOT fixed here — resolved by the close-out's
own dep-reinstall step, not a code fix:**
`tools/tool_search_catalog.py` (new file, upstream addition, not a
conflict) does `import snowballstemmer` unconditionally at module level,
and `pyproject.toml` gates that dependency to
`snowballstemmer==3.1.1; python_version >= '3.14'`. Verified byte-identical
on `upstream/main` itself (not introduced by this merge). On a STALE 3.11
venv (both `~/.hermes/hermes-agent/.venv` and `venv` are 3.11.15 right
now) this is `ModuleNotFoundError` at import, breaking core tool dispatch
(`model_tools.py`, `agent/tool_dispatch_helpers.py`) entirely. BUT:
`.python-version` already pins `3.14`, and `setup-hermes.sh` resolves its
provisioning target FROM that pin (`py_version=$(pin version python |
...)`) — so the close-out's planned dep-reinstall onto a fresh 3.14 venv
resolves this automatically; no code fix needed. Do not run the merged
code against the CURRENT stale 3.11 venv in production — it will break
on this exact import until the 3.14 reinstall happens.

**Pre-existing fork bug found during validation (NOT merge-caused, NOT
fixed here — out of scope):**
`tests/gateway/test_matrix.py::TestMatrixPasswordLoginDeviceId::test_password_login_uses_device_id`
fails identically on pre-merge `main` (confirmed via direct run against
the live ~/.hermes/hermes-agent checkout before any merge work touched
it). Root cause: the test's `_make_fake_mautrix()` stub `PgCryptoStore`
has no `get_device_id()` method, and its fake `client.query_keys` is a
plain `MagicMock` instead of an `AsyncMock`, so `_verify_device_keys_on_server`
raises `TypeError: object MagicMock can't be used in 'await' expression`.
Flagging for a separate fix; not touched during this merge.

**Test-environment gotchas hit during validation (both pre-existing,
neither merge-caused):**
- `~/.hermes/hermes-agent/.venv` is Python 3.11.15 and missing aiohttp/
  mautrix/olm entirely; `~/.hermes/hermes-agent/venv` (no leading dot) is
  the fully-provisioned env with all three — use that one for Matrix
  adapter tests.
- The live venv's `sitecustomize.py` (hermes-claude-auth OAuth bypass)
  injects `~/.hermes/patches` onto `sys.path` at interpreter startup;
  `importlib.metadata.entry_points()` (used by `markdown`'s extension
  loader, hit via `_markdown_to_html`) scans all of `sys.path` and trips
  `tests/home_io_guard.py`'s real-home guard on that path. Set
  `HERMES_PATCHES_DIR=/nonexistent` for test runs in this venv to avoid
  it; harmless, doesn't disable the actual billing-bypass patch in
  production use (gateway runs are never launched this way).
- `pm/pyproject.toml`/`pm/uv.lock` (new, upstream-added, not a conflict)
  pin PM's isolated worker runtime to Python 3.14 — `/usr/bin/python3.14`
  is present and uv-registered on spacecom, but building `python-olm`/
  `evdev`/`pilk` (matrix/screen/silk extras) under 3.14 needs
  `python3-devel` (Solus eopkg; 2.32 MB, zero pending distro upgrades) —
  not yet installed, asked twice, no response both times. `tests/pm/`
  itself passes 667+ under 3.11 once past that gate; not blocking.

Full `tests/gateway/test_matrix.py` run (venv, HERMES_PATCHES_DIR unset
to /nonexistent): 107 passed, 1 failed (the pre-existing bug above).
Full `tests/plugins/test_holographic_hybrid_retrieval.py`: 20/20 passed
after the two import/sentinel fixes above.

- hermes_cli/curses_ui.py — keep-both: pop_kitty_keyboard() fork fix +
  theirs' NAV_BACK/NAV_INTERRUPT 4-tuple.
- hermes_cli/skin_engine.py region 1 — take theirs (pure refactor to
  _branding()/_HERMES_BRANDING; no "mercury" skin entry in either tree).
- hermes_cli/session_listing.py — docstring re-merge, same mechanism both
  sides, code below unconflicted.
- hermes_cli/plugins.py — keep-both: our 3 fork hooks
  (transform_gateway_notice/transform_interim_output/transform_stream_fragment)
  + theirs' new pre_auxiliary_call/post_auxiliary_call.
- hermes_cli/commands.py — took theirs' /bg+/btw un-aliasing (git log -S
  confirms our old aliasing traces to upstream 7fa70b6c87, which upstream
  itself superseded — pure upstream feature evolution) + kept our go/nogo
  aliases + theirs' desktop="messaging" kwarg.
- tools/registry.py — keep-both: doubly-wrapped-schema warning + normalize_scope.
- tui_gateway/server.py — took theirs wholesale (sess/git_probe.branch/
  _turn_started_at already used elsewhere in this exact merged file).
- tui_gateway/methods_session.py — keep-both: our Anthropic/Codex/OpenRouter
  account-limits block (84cbc27634) + theirs' Nous-credits block.
- agent/account_usage.py — REAL re-express. Fork fix 90c71d2ef3 (Sonnet-week
  scaling bug: OAuth usage API already returns percentage, old fraction
  heuristic inflated <=1% windows to 100%) ported onto upstream's refactored
  _usage_windows()/_snapshot()/_get_json() via fraction=False + Claude-Code
  labels. render_account_usage_block (rich bar renderer) is now upstream's
  own code, unconflicted.
- hermes_cli/status.py — god-file split (show_status monolith -> _render_header
  /_render_environment/... with _banner/_section/_kv helpers). Re-expressed
  the brand+glyph box title into upstream's new _render_header(), width 57
  preserved as a fork tunable comment.
- hermes_cli/build_info.py — RE-EXPRESSED, high attention. Upstream reduced
  this file to a get_code_identity() shim delegating to the new
  hermes_cli/version_info.py (install-stamp-first resolution). Confirmed via
  grep: get_build_sha() has ZERO remaining callers anywhere in the merged
  tree (its only callers, banner.py/dump.py, already auto-merged onto
  upstream's install-stamp approach) — dropped as genuinely dead code, not
  a silent loss. get_brand_name() has NO upstream equivalent and was kept
  verbatim; get_code_identity() now re-exports version_info's real impl.
- hermes_cli/_startup_fast.py — re-expressed the brand fast-path onto
  theirs' new version_info.get_version_info() import.
- hermes_cli/banner.py — TWO regions, both real re-express (not mechanical).
  Region 1: the ENTIRE update-check subsystem (GitHub comparison, local
  cache file, head-hash cache key) was relocated upstream to
  hermes_cli/source_check.py (confirmed already imported at top of this
  file). Confirmed the fork fix efc2a91c3 (head-hash cache-key invalidation
  after hermes sync) is SUPERSEDED, not lost — upstream's new
  check_for_updates() already keys its cache identity on `co.head` (the
  checkout's live HEAD sha), which is exactly the invalidation our fix
  added. Took theirs wholesale (the _compute()/_memo() skills-cache closure
  survived inside this same region). Region 2: re-expressed get_brand_name()
  into every "Hermes Agent" literal in format_banner_version_label()
  (desktop-app label, commit-build/canary/installer suffixes, base
  fallback) — 4 call sites, not 1, since upstream's version is richer than
  what we had.
- plugins/model-providers/kimi-coding/__init__.py — kept fork's Preserved
  Thinking (keep="all") logic layered atop upstream's shared
  thinking_toggle_extras import (not calling it directly — no param for the
  keep addition); fixed a dropped clamp_effort import mid-resolution.
- plugins/model-providers/nous/__init__.py — functionally identical both
  sides (early-return restyle only); took theirs.
- ui-tui/src/app/slash/commands/session.ts — kept fork's accountLines-aware
  suppression guard, adopted upstream's t() i18n call.
- ui-tui/src/__tests__/theme.test.ts, ui-tui/src/theme.ts — pure identity,
  kept ours (Mercury brand/glyph/colors), zero upstream equivalent content.
- ui-tui/src/types.ts + ui-tui/src/components/branding.tsx — IMPORTANT FIND.
  Upstream replaced the hand-written SessionInfo/ProjectInfo interfaces with
  a generated contract type (SessionLiveInfo, from
  apps/shared/src/gateway-contract.generated.ts) that has NO `session_key`
  field — it was renamed to `stored_session_id` server-side
  (tui_gateway/server.py::_session_info() emits "stored_session_id", not
  "session_key", confirmed by direct read). The fork's 397bbe7ca fix
  (persistent DB session_key over ephemeral RPC handle) would have silently
  regressed — info.session_key resolves to undefined through the
  interface's `[key: string]: unknown` catch-all, falling through to `sid`
  every time, i.e. exactly the bug 397bbe7ca fixed, with no type error to
  catch it. Repointed to info.stored_session_id at both branding.tsx JSX
  sites (wide + narrow layout) and adopted upstream's T.sessionLabel i18n
  token in place of the hardcoded "Session: " string.
- tools/lazy_deps.py — upstream completed a multi-commit architectural
  retirement (confirmed via `6a5a6a05d2`: real lazy-install logic moved to
  pm.extras/pm.install; lazy_deps.py is now a 26-line stub enforced by a
  dedicated CI guard, scripts/ci/check_lazy_deps_imports.py). Took theirs
  wholesale. FOLLOW-ON FIX (not a merge region, found by grepping remaining
  callers): tools/mercury_eyes/act.py still called the retired
  tools.lazy_deps.ensure("screen.uinput") — repointed to
  pm.extras.ensure_import("screen") and added a "screen": "evdev" anchor
  entry to pm/extras.py's ANCHORS table (that module is new upstream
  infrastructure our fork never had, so this is a genuine gap-fill, not a
  fork fix being carried forward).
- acp_adapter/server.py — TWO regions, the second one a SERIOUS near-miss.
  Region 1 (brand-name import + _named_custom_provider_catalogs, 150 lines):
  initially resolved as a straight keep-ours, but a closer read found
  upstream had ALREADY ABSORBED this exact fork feature (originally added
  by fork commits 4be38125af/cbd2011900) into a new acp_adapter/model_catalog.py
  with a modernized implementation (newer import paths, a _discover_flag
  helper) already wired in and called from server.py's _build_model_state.
  Keeping "ours" here would have left a dead, shadowing duplicate definition
  silently never called — removed entirely rather than ship dead code.
  Region 2 (_cmd_compress tail + _cmd_steer/_cmd_queue/_cmd_version, ~50
  lines): same pattern — upstream extracted the WHOLE SlashCommandsMixin
  class to a new acp_adapter/commands.py with a RICHER /compress
  implementation (compress_now/parse_compress_args, preview+aggressive
  args) already mixed into HermesACPAgent. My first pass re-created the old
  methods directly on the subclass, which would have SHADOWED the mixin's
  upgraded implementation and silently reverted the /compress feature
  upgrade — caught by checking class MRO before finalizing, reverted, and
  instead just fixed commands.py's _cmd_version (which hardcoded "Hermes
  Agent") to call get_brand_name(). General lesson for the rest of this
  cycle: when ours-side content looks fully absent from theirs-side of a
  conflict region, check whether it was RELOCATED to a new sibling file
  before assuming it needs restoring verbatim — god-file splits move code,
  they don't always delete it.
- plugins/memory/holographic/{__init__,retrieval,store}.py — SPLICE, not a
  pick. Confirmed via upstream tree check: plugins/memory/holographic/
  embedding.py does not exist upstream at all — the dense-embedding
  Hybrid-Full search (fork commit 23a20e59ba) is entirely fork-exclusive
  and never went upstream. Meanwhile upstream ran 6+ refactor() commits
  (Teknium) compacting probe/related/reason/contradict through new shared
  _vector_query/_rank_by_vector helpers — pure DRY, same algorithms,
  confirmed by direct comparison. Resolution: kept our __init__ (4-weight
  embed-aware constructor) and search()/_embedding_candidates() verbatim
  (the embedding feature, unique to us), grafted on theirs' probe/
  related/reason/contradict/_vector_rows/_rank_by_vector/_fts_candidates/
  _tokenize/_sanitize_fts_query/_jaccard_similarity/_temporal_decay tail
  wholesale (the refactor, unique to them) by finding the exact byte
  offsets between the two unconflicted anchors and splicing in Python
  rather than line-by-line patch (the span was too large and intermixed
  with 3 separate conflict regions for manual patching to be safe).
  store.py: adopted upstream's add_column_if_missing migration helper
  (race-safe on concurrent migrators, #21708) for BOTH hrr_vector and our
  embedding column — the bare ALTER TABLE ours used was not race-safe.
  __init__.py: caught and fixed a LATENT BUG surfaced by the merge — our
  side referenced a bare `default_trust` name with no definition in that
  function scope (dead/stale from an earlier refactor); replaced with
  theirs' inline self._config.get() form.
- agent/anthropic_adapter.py + agent/anthropic_credentials.py — THE big
  re-expression of this cycle. Merge conflict itself was simple (our
  1,929-line ours-side credential block vs 2 lines theirs-side — the whole
  module already extracted to agent/anthropic_credentials.py upstream,
  confirmed via upstream tree ls). Took theirs for the conflict region
  itself. Then re-planted FOUR real fork fixes onto the new module, each
  independently verified not already covered by upstream's own
  improvements to the same code:
    1. 429/5xx retry with Retry-After/exponential backoff in
       _post_oauth_token (122b567aba) — upstream had no retry; a transient
       429 during an Anthropic incident was previously indistinguishable
       from a dead grant. Ported onto upstream's cleaner AnthropicOAuthError
       .relogin_required check (better than our old ad-hoc _is_transient).
       Fixed a related bug while porting: the original used `break` on a
       terminal error, which only exited the inner endpoint loop, letting
       the outer retry loop spin again; changed to `raise` so it actually
       stops.
    2. Refresh-failure cooldown, 600s per-token (254b7d18b8) — added new
       module state (_REFRESH_FAILURE_COOLDOWN_S, _refresh_failure_cooldown
       dict) since upstream's _refresh_oauth_token had no equivalent; only
       applies to the NON-terminal failure path (terminal already gets
       upstream's permanent _DEAD_REFRESH_TOKEN_FINGERPRINTS treatment, which
       is actually tighter-scoped than our old version — kept that).
    3. debug→warning logging on refresh exhaustion — upstream's terminal
       branch was already WARNING (better than ours); only the non-terminal
       "retries exhausted" branch was still debug-level, invisible through
       the gateway's log filter. Raised that one branch specifically.
    4. Setup-token-wins precedence (254b7d18b8, part 2) — upstream had
       collapsed ANTHROPIC_TOKEN/CLAUDE_CODE_OAUTH_TOKEN into one
       _first_env() call, which silently lost the distinction our fix
       needs (only the long-lived setup-token var should skip a refresh
       attempt against a merely-EXPIRED file and fall through immediately).
       Split them back into two separate checks in resolve_anthropic_token;
       added refresh_expired=False param to _prefer_refreshable_claude_code_
       token, wired only to the CLAUDE_CODE_OAUTH_TOKEN branch.
  All four fixes independently confirmed via `git show <hash> -s` +
  `git show <hash> -- <file>` against the original fork commits before
  porting — none were guessed from memory of what the fix "probably" did.
- agent/conversation_loop.py (both regions) + agent/turn_context.py +
  agent/turn_empty_response.py + agent/turn_tool_round.py +
  agent/turn_final_response.py + tests/agent/test_hidden_thinking_nudge.py
  — the hidden-thinking-nudge fix (46e762b87e). Region 1 (small, docstring)
  was mechanical. Region 2 was the LARGEST single region in the whole
  cycle: 5,896 "ours" lines vs 20 "theirs" lines, because upstream
  decomposed conversation_loop.py from 8,511 lines down to 1,835 across
  ~117 new agent/*.py modules. Before taking theirs wholesale, traced
  where the fix's actual logic landed: _has_structured/prefill-gate ->
  agent/turn_empty_response.py (recover_empty_response), the two extra
  resets (_hidden_thinking_nudged on tool-success / successful-content) ->
  agent/turn_tool_round.py + agent/turn_final_response.py, the per-turn
  reset -> agent/turn_context.py's new _PER_TURN_RESET_STATE tuple
  (already handled). Ported _reasoning_has_visible_text() and the full
  nudge-vs-prefill branch into turn_empty_response.py, added the two
  missing resets, THEN took theirs for the conversation_loop.py region
  (now safe — the real logic lives in its new home).
  Updated tests/agent/test_hidden_thinking_nudge.py's module-source
  invariants to point at the new split locations (was asserting against
  conversation_loop.run_conversation's 3,900-line body; now asserts
  against turn_empty_response.recover_empty_response). ACTUALLY RAN this
  test file (not just syntax-checked) in an isolated scratch copy against
  the live venv — caught and fixed TWO real bugs the static read missed:
  (1) a stale `_SOURCE.index("_prefill_exhausted = (")` lookup — upstream
  renamed that variable to `_empty_candidate`, so the assertion would have
  raised ValueError at collection; (2) the turn_context.py reset-flag
  assertion looked for a literal `agent._hidden_thinking_nudged = False`
  line, which no longer exists under the tuple-based reset pattern — fixed
  to check for the tuple entry instead. All 14 tests pass for real.
- hermes_cli/update_cmd.py — zero fork-local commits (confirmed via git log
  main --not upstream/main, only merge noise). The entire fork-tracking git
  sync subsystem (_is_fork, _add_upstream_remote, _sync_fork_with_upstream,
  stash handling) already migrated to hermes_cli/update_cmd_git.py with real
  upstream improvements on top (fork-bomb probe, trampoline-git detection,
  lockfile-churn handling, parked-branch logic our version never had). Clean
  take-theirs; verified _update_via_zip and every moved function present in
  their new homes (update_cmd_git.py, update_cmd_zip.py) before committing.
- hermes_state.py + hermes_state_messages.py — SessionDB's message-storage
  mixin, same god-file-split pattern as conversation_loop.py (3,105 "ours"
  lines vs upstream's full SessionMessagesMixin extraction). Found the
  anthropic_content_blocks fork fix (0fab928d9c, interleaved-thinking
  signature-order fix) had its schema column already present in
  hermes_state_common.py but COMPLETELY UNWIRED in the new split module — no
  write, no read. Wired into _INSERT_MESSAGE_SQL, _message_row_params (both
  insert paths), both read-decode sites, and append_message's signature.
  ACTUALLY RAN test_anthropic_thinking_block_order.py against the live venv
  in an isolated scratch copy — first run FAILED with
  `IndexError: No item with that key`, surfacing a second real gap: a
  separate explicit column list (_CONVERSATION_ROW_COLUMNS, used by
  get_messages_as_conversation / conversation replay) was also missing the
  column. Fixed; all 4 tests pass for real on rerun. Confirmed
  restore_rewound (a method with no callers anywhere in the tree, including
  its own docstring: "not wired to a slash command in v1") was correctly
  dropped by upstream's d15c61b5dc refactor — not a loss.
- run_agent.py + agent/session_persistence.py + agent/stream_delivery.py —
  run_agent.py's own god-file decomposition (9,248 -> 1,586 lines). Region 1
  (926 lines) was dead weight (upstream's #46053 fix already live via the
  already-wired SessionPersistenceMixin). Region 2 (2,089 lines): the SAME
  anthropic_content_blocks fix had a SECOND unwired call site — the
  batch-row constructor moved to agent/session_persistence.py's
  _db_flush_row via a shared _ROW_REASONING_KEYS tuple; added the key there
  (cleaner than ours' per-key enumeration — one tuple feeds every row
  builder). Confirmed role-gating (assistant-only) flows through
  automatically via _message_row_params's existing keep_reasoning parameter.
  SEPARATELY, and more serious: traced the fork's transform_interim_output
  plugin hook (795f5a9b45 feature + 65fccf9b7d perf/correctness follow-up,
  gates the hook on `if not already_streamed`) and found _emit_interim_
  assistant_message had relocated to agent/stream_delivery.py — but the hook
  dispatch itself was NOT ported during the split. This was a genuine
  FEATURE LOSS, not a relocation: _deliver_interim called the callback
  directly with zero hook dispatch. Ported the full fixed-state logic
  (hook call gated behind `if not already_streamed`, first-non-empty-wins,
  fail-safe try/except) into _deliver_interim. Verified against the live
  venv: test_interim_transform_skipped_when_already_streamed (the specific
  regression test for the perf fix) now PASSES, along with
  test_transform_interim_output_hook.py (3/3) and the surrounding
  test_run_agent_codex_responses.py interim suite (5/7 — 2 unrelated
  failures traced to MY test harness: stubbing tests/conftest.py to work
  around its own unresolved conflict markers also disabled the autouse
  fixture that resets hermes_cli.plugins._plugin_manager between tests, so
  Peter's real installed diction-filter plugin leaked in and capitalized
  "short" -> "Short" in the observed text — confirmed by reading
  conftest.py's fixture comment directly, not guessed).
- hermes_cli/update_cmd.py -- already logged above (31/57 checkpoint).
- gateway/run.py + gateway/run_turn.py + gateway/run_notifications.py --
  3 regions, 2 pure relocation (59 methods -> run_turn.py; notification
  methods -> run_notifications.py's GatewayNotificationsMixin), 1 confirmed
  genuine-false-alarm (suspected 3ba6c4e9bf Matrix buffer_only/slash-confirm
  conflict in region 3 turned out to be ANOTHER pure relocation -- verified
  via git log that commit's only non-merge touch to gateway/run.py had
  already landed cleanly elsewhere in the tree before this region was even
  opened). THREE forked features actively re-planted: (1) "plain"
  reasoning_style delivery mode ported into run_turn.py's
  _hmwa_prepend_reasoning, converted sync->async, single call site updated
  to await; (2) display_config.py's choices tuple -- found ALREADY present,
  no action needed (a stale gap report); (3) transform_gateway_notice hook
  -- confirmed completely missing from run_notifications.py's
  GatewayNotificationsMixin (hermes_cli/plugins.py VALID_HOOKS already had
  the entry, only the dispatch-site wiring was gone) -- ported the method +
  both call sites (_send_restart_notification, _send_home_channel_startup_
  notifications). Verified: tests/test_transform_gateway_notice_hook.py 3/3
  pass for real in an isolated venv run.
- gateway/slash_commands.py -- 2 regions, both clean take-theirs. Verified
  independently (prior lead about kanban auto-subscribe was a red herring):
  fork commit 48b9d62886 (remove Matrix room isolation from /sessions,
  /resume) is fully superseded -- the HEAD-side duplicate of
  _gateway_session_origin_for_id/_same_matrix_room was found carrying its
  own code comment reading "MERCURY FORK -- DORMANT CODE NOTICE", i.e. the
  fork itself had already marked this code dead before the merge. Upstream's
  refactor moved the real resume/session room-scoping machinery to
  gateway/slash_commands_session.py with correct (room-isolation-free)
  behavior already in place.
- gateway/stream_consumer.py + gateway/stream_consumer_transport.py -- 2
  regions, both relocation (dropped HEAD-side duplicates of
  _send_new_chunk/_clean_for_display/_MEDIA_RE/_send_failure_may_have_
  delivered/_resolve_draft_streaming/_send_or_edit, all confirmed living in
  stream_consumer_transport.py / stream_consumer_fallback.py mixins) BUT
  caught the THIRD silent-hook-drop of this cycle: _apply_stream_fragment_
  transform (fork commit 941717eb4e, transform_stream_fragment hook for
  live-streamed text) was preserved as a method definition in
  stream_consumer.py but its actual DISPATCH call site -- inside
  _send_or_edit, right after _clean_for_display and before the
  _last_sent_text dedup, per the original commit's own diff -- never
  survived the split into stream_consumer_transport.py's _send_or_edit.
  agent/stream_delivery.py's ALREADY-RESOLVED docstring for _deliver_interim
  explicitly assumes this hook fires here ("filtered in-flight by
  transform_stream_fragment in gateway/stream_consumer.py") -- a false
  assumption until this fix. Re-planted the single-line dispatch call with
  matching at_boundary=finalize semantics. Verified: tests/test_transform_
  stream_fragment_hook.py 5/5 pass for real in an isolated venv run,
  including the two consumer-integration tests that specifically exercise
  the call site added (passthrough-when-no-plugin, cursor strip/re-append).
- cli.py (god-file, final close-out) -- Region 3: _DESTRUCTIVE_SKIP_TOKENS /
  _clarify_batch_* / _computer_use_approval_callback all confirmed already
  present on both "ours" class body AND cli_modal_mixin.py -- pure dead-
  weight duplicate, stripped. Region 4 (2,683 lines): pre-refactor duplicate
  of run()'s entire TUI startup sequence (banner, first-run offer, welcome
  text, prewarm threads, key bindings, Application() construction) --
  every distinctive symbol confirmed already present in cli_tui_mixin.py /
  cli_tui_runtime_mixin.py / cli_agent_setup_mixin.py, invoked by the 4
  lines immediately preceding the conflict. Took theirs
  (_tui_build_application(...)). i18n: propagated the agent_name-branded
  "{agent_name} CLI Status" status-title fix (from the b1694e5d18 skin-
  branding fork commit) to all 16 non-English locale files, mirroring the
  existing clarify_title bilingual precedent. render_account_usage_block
  fix (90c71d2ef3) correctly wired into cli_info_mixin.py's
  _print_account_limits().
  CAUGHT A SEPARATE, NOT-IN-ANY-CONFLICT-REGION BUG while verifying: cli.py's
  own HermesCLI class body had a *second*, un-flagged pre-refactor duplicate
  of 6 methods (_handle_usage_command, _usage_reset, _show_context_breakdown,
  _show_usage, _show_insights, _check_config_mcp_changes) sitting OUTSIDE any
  <<<<<<< marker -- leftover from an earlier "confirmed done" pass that
  missed this second cluster. Python's class __dict__ always wins over
  inherited mixin methods regardless of base-list/MRO order, so this
  shadow made the correctly-fixed cli_info_mixin.py version DEAD CODE for
  every real /usage call, AND the shadow's own inlined account-limits fetch
  crashed with NameError (used concurrent.futures without importing
  concurrent at cli.py's top level -- cli_info_mixin.py has the import,
  cli.py never did). Deleted the 354-line duplicate block (lines
  1647-2000, verified no super() calls or qualified cross-references
  first). Verified end-to-end: tests/cli/test_cli_status_bar.py 24/24 +
  tests/test_account_usage.py 7/7 pass for real in an isolated venv run,
  including the specific test that had been failing with the NameError
  before this fix (test_show_usage_omits_cost_reporting).
  cli.py: 0 markers, compiles clean, git-added along with cli_info_mixin.py
  and all 16 locale files.
  NOTE while staging: discovered tests/cli/test_cli_status_bar.py and
  tests/test_account_usage.py are listed in git's conflict set as UD
  (unmerged/deleted-by-them), NOT because of textual markers (they have
  none) but because upstream's test-tree reorg (d10bb2ab6f, "make tests/
  mirror the source tree") deleted these exact paths and split their
  content into tests/agent/test_account_usage.py +
  tests/hermes_cli/test_cli_status_bar.py. Diffed the test function names
  on both sides: this is GENUINE DUAL-SIDED DIVERGENCE, not a pure rename --
  upstream's new-path files add ~20 tests we don't have (codex credential-
  retry/account-id tests, status-bar field-config/cache-hit-rate/latency
  tests) and our old-path files have ~13 fork-local tests upstream's new
  files don't have (test_render_account_usage_block_matches_claude_code_
  shape, test_fetch_anthropic_utilization_is_percent_not_fraction,
  test_show_usage_omits_cost_reporting, test_context_style_thresholds,
  test_voice_status_bar_compacts_on_narrow_terminals, and others -- full
  list obtainable by re-running `git show :2:<old path>` and diffing
  `grep '^def test_\|    def test_'` output against the new path). This
  needs a real content merge (port our ~13 fork-only tests into the new-
  path files, keep upstream's ~20 new tests, then `git rm` the old paths)
  as part of the test-fallout tier below -- flagging now with exact test
  names so that pass doesn't have to re-diff from scratch.

## CLOSE-OUT GATE — PASSED

- git status: 0 files in UU/AA/DD/UD/DU state (all 57 resolved + staged).
- grep for real conflict markers tree-wide: 0 (the only 2 string hits are
  literal test fixtures in test_audit_old_updater_imports.py /
  test_mcp_oauth_metadata.py — tests ABOUT conflict-marker detection, not
  actual unresolved conflicts — confirmed by reading both).
- Full-tree `python3 -m py_compile` on every .py file: exit 0, zero
  SyntaxError. Only pre-existing SyntaxWarnings (docstring escape
  sequences in unrelated files, none touched by this merge).
- Heavy-risk files individually test-validated with real pytest runs
  (not just syntax checks) during resolution: conversation_loop/
  turn_empty_response (14/14), hermes_state/hermes_state_messages
  (4/4), run_agent/session_persistence/stream_delivery (interim-output
  suite), stream_consumer/stream_consumer_transport (5/5), cli.py +
  cli_info_mixin (24/24 + 7/7), gateway/run.py+run_turn+run_notifications
  (3/3), Matrix adapter (107/108, 1 pre-existing unrelated failure),
  holographic memory (20/20 after 2 genuine regressions fixed).
- Ready for the ff-only merge onto live main.

### Tier A — small/mechanical, do next
- hermes_cli/status.py — ours: box-drawing status print w/ get_brand_name().
  Theirs: _TERMINAL_ENV_ROWS data-driven refactor. Check brand-name call
  site survives theirs' refactor; likely re-express.
- gateway/display_config.py — ours: YAML bare-off normaliser w/ extra
  branches. Theirs: generic _NORMALISERS dispatch dict. Port any fork-added
  setting into theirs' dispatch table.
- locales/en.yaml — ours: emoji-prefixed literal strings. Theirs: plain
  text same keys. Check git blame: did fork add the emoji, or did upstream
  strip it? Decide accordingly.
- plugins/model-providers/{kimi-coding,nous}/__init__.py — likely
  near-identical logic, different formatting. HIGH ATTENTION: verify the
  06107ff348 finding (Kimi Preserved Thinking moved to Moonshot-direct,
  Nous-portal injection removed as inert — empirically proven via token
  accounting per maintained-fork-workflow) survives.
- ui-tui/src/app/slash/commands/session.ts,
  ui-tui/src/__tests__/theme.test.ts — small diffs, check.

### Tier B — identity/branding re-expression (doctrine §2 pattern)
- hermes_cli/build_info.py — HIGH ATTENTION. Ours: full get_brand_name()
  impl (fork's brand indirection used across cli.py/status.py/banner.py/
  tests). Theirs: reduces file to a one-line shim — brand resolution likely
  moved to new hermes_cli/version_info.py or hermes_cli/steward.py. MUST
  TRACE before deciding; this is load-bearing for Mercury identity.
- hermes_cli/_startup_fast.py — re-express our MERCURY FORK fast-path brand
  name onto theirs' new version_info.get_version_info() import.
- hermes_cli/banner.py region 1 (skills-by-category cache) — likely take
  theirs (pure _compute() closure refactor); region 2 (~line 555, version
  string) — re-express get_brand_name() onto theirs' richer canary-tag/
  install-stamp aware banner.
- ui-tui/src/theme.ts, ui-tui/src/components/branding.tsx — Mercury name/
  icon/welcome re-expression, established DARK_SEEDS-style pattern from
  doctrine §2 (fork-sync-conflict-doctrine.md).

### Tier C — god-file decomposition, re-express into new modules
- hermes_cli/update_cmd.py — ENTIRE file gutted upstream (0 theirs lines,
  1149 ours), logic scattered across ~60 new update_cmd_*.py/update_*.py
  modules. Biggest single re-express task in stage 1. Check for any
  fork-local fix here (e.g. update-check cache invalidation efc2a91c3 is
  already elsewhere per doctrine — verify it's not ALSO duplicated here).
- cli.py — 5 regions, largest up to ~6700 lines ours vs 0-8 theirs
  (ChatConsole, _pet_resolve_config, _manual_compress, _show_status,
  _tui_build_application). Re-trace each into the new cli_*_mixin.py set.
- gateway/run.py — 3 regions (_handle_message_with_agent ~4879 lines,
  update-notification-watch ~672 lines, _commit_memory_before_soft_evict
  ~900 lines) vs theirs' _HygieneSettings/_profile_name_for_source. Re-trace
  into run_turn.py/run_inbound.py/run_turn_runner.py/run_profile_reconcile.py.
- hermes_state.py — ours: _encode_content (3105 lines of context). Theirs:
  REACTIONS_METADATA_KEY + display-column contract. Check hermes_state_common.py
  (schema may already live there per doctrine §4) and new hermes_state_gateway.py.
- gateway/stream_consumer.py — 2 regions, MEDIA_TAG_CLEANUP_RE handling
  (known fork concern) vs theirs' tick/_DONE sentinel + _send_failure_may_have_delivered.
- gateway/slash_commands.py — 2 regions, large ours vs small theirs
  (_field/_handle_compress_command). Likely re-express.
- agent/conversation_loop.py — 2 regions (_reasoning_has_visible_text ~34
  lines vs theirs' Codex/Responses retry comment; huge 5896-line region vs
  theirs' 20-line result/messages/db snippet — re-trace).
- agent/turn_context.py — ours: 13-line inline per-turn reset. Theirs:
  _PER_TURN_RESET_STATE tuple-driven refactor. Port any fork-added reset
  field into theirs' tuple.
- run_agent.py — 2 regions (925 lines retry-row-creation vs theirs' 2-line
  cancel_requested check; 2089-line _uniquify_tool_call_ids vs theirs'
  staticmethod delegation to _sanitize_uniquify_tool_call_ids). Re-trace.
- acp_adapter/server.py — 2 regions, _named_custom_provider_catalogs (148
  lines) + AIAgent-off-loop block (51 lines) vs small theirs snippets.
- tools/lazy_deps.py — ours: full venv-scoped install docstring/impl (1086
  lines) vs theirs' 12-line install_specs() compat shim calling new updater.
  Check pyproject.toml extras coupling (doctrine's lazy-dep handling).
- gateway/display_config.py already in tier A above (smaller than others).

### Tier D — Memory plugin refactor (moderate complexity)
- plugins/memory/holographic/__init__.py, retrieval.py (3 regions), store.py
  (2 regions) — fork's Hybrid-Full dense-embedding addition (23a20e59ba)
  must be re-expressed onto theirs' refactored retrieval scoring (_shift(),
  candidates split, add_column_if_missing helper, _rebuild_bank/_one).

### Tier E — credential split (stage 2, do after Tier A-D)
- agent/anthropic_adapter.py — ~1924 lines of OAuth/credential code (incl.
  setup-token-wins fix 254b7d18b8, 429/5xx retry 122b567aba, warning-level
  logging 15417cb2eb) must be re-planted into NEW agent/anthropic_credentials.py
  (confirmed exists, ~42 lines read so far — read in FULL before porting).
  Small region 1 (3 lines ours vs 2 theirs imports) is trivial keep-both.

### Tier F — Matrix adapter (stage 3, DO LAST, highest risk)
- plugins/platforms/matrix/adapter.py — 11 regions. Fork-only content to
  preserve through upstream's _absorb_sync refactor: 502/503/504-before-
  auth-check (THE canonical maintained-fork-workflow case study),
  machine-provenance m.notice typing (glyph_flags/REQ header from THIS
  session's own prior work — 3f6f0a0c1d/9f1c0e9679/97949f1c67/2c3479dfbc),
  MercuryTerm sessions-panel side channel (4ee1f0bb74), cross-room
  /sessions+/resume (48b9d62886 — dormant-retention per
  fork-sync-conflict-doctrine §1; CHECK if upstream re-added the IDOR guard
  suite again this cycle, same pattern as the 2026-07-28 cycle).

### Tier G — test fallout (mechanical once source decisions land)
- Modify/delete (upstream deleted file outright, confirm coverage moved):
  tests/cli/test_cli_status_bar.py, tests/hermes_cli/test_banner_git_state.py,
  tests/hermes_cli/test_update_check.py,
  tests/skills/test_xurl_article_ingestion_docs.py, tests/test_account_usage.py.
- Content conflicts needing the standing PRUNE/ADOPT list
  (fork-sync-conflict-doctrine §4) + path updates for anthropic_credentials.py:
  tests/agent/test_anthropic_adapter.py (monkeypatch path:
  agent.anthropic_adapter.Path.home -> agent.anthropic_credentials.Path.home,
  TAKE THEIRS, 2 occurrences — mechanical, the module moved),
  tests/gateway/test_resume_command.py (2 regions, lane-scoping — apply
  PRUNE list), tests/gateway/test_update_command.py,
  tests/gateway/test_ws_auth_retry.py, tests/hermes_cli/test_banner.py,
  tests/hermes_cli/test_cli_status_command.py, tests/hermes_cli/test_kanban_db.py,
  tests/hermes_cli/test_startup_fast_guards.py,
  tests/hermes_cli/test_tui_resume_flow.py, tests/providers/test_provider_profiles.py,
  tests/conftest.py, tests/tui_gateway/test_tui_gateway_server.py.

### Tier H — lockfiles (stage 4, after everything else)
- pyproject.toml — our memory-embeddings-removal note vs upstream's large
  extras-taxonomy reorg. Resolve source first, then regenerate.
- uv.lock — resolve LAST, after pyproject.toml settles; do not hand-edit.

## Close-out sequence (after all tiers green)
1. Full test batch, background + notify_on_complete
   (tests/gateway tests/agent tests/hermes_cli tests/hermes_state
   tests/acp_adapter tests/tui_gateway — note the tree now also has
   tests/e2e/, decide whether to include).
2. py_compile every resolved .py file; tsc --noEmit on ui-tui; vitest run.
3. Mass-failure triage via lastfailed JSON set-diff against pristine
   upstream/main worktree (doctrine recipe) if failures are numerous.
4. `git add -A && git commit` the merge in the probe worktree.
5. On live main: `git merge --ff-only <probe-commit-sha>`.
6. `VIRTUAL_ENV=~/.hermes/hermes-agent/venv uv pip install -e '.[all,dev]'`
   + `uv pip install -e '.[messaging]'` (NEVER `uv sync`).
7. Import-check runtime module set; `rm ~/.hermes/.update_check`.
8. Push via hermes-git-push with HERMES_REPO pinned; verify HEAD == origin/main.
9. Tell Peter: live gateway/TUI still runs pre-merge code until restarted —
   he restarts from outside this session (gateway can't restart itself).
