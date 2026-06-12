"""Regression tests — hidden-thinking-only responses must not enter the
prefill loop.

Anthropic adaptive thinking with ``display="omitted"`` (the API default;
observed on claude-fable-5, which thinks by default even when the request
sends no thinking parameter) returns thinking blocks whose ``thinking`` text
is empty with only a ``signature`` payload.  The thinking-only prefill
recovery in conversation_loop replays the assistant message so the model can
"see its own reasoning and continue" — with no readable text that is futile:
the model re-emits hidden thinking, the prefill loop burns 2 calls, then the
empty-retry loop burns 3 more, all at full conversation context cost
(observed: 6 API calls × 79k input tokens for one dead turn).

The fix routes textless structured reasoning to the synthetic-user nudge
(the post-tool-empty recovery mechanism) instead of the prefill.
"""
import inspect
from types import SimpleNamespace

from agent import conversation_loop
from agent.conversation_loop import _reasoning_has_visible_text


def _msg(**kwargs):
    base = {"reasoning": None, "reasoning_content": None, "reasoning_details": None}
    base.update(kwargs)
    return SimpleNamespace(**base)


# ── _reasoning_has_visible_text ──────────────────────────────────────


def test_signature_only_thinking_block_is_not_visible():
    """The claude-fable-5 / display=omitted shape: empty text, signature only."""
    msg = _msg(reasoning_details=[
        {"type": "thinking", "thinking": "", "signature": "EqQBCkgIBRABGAI..."},
    ])
    assert _reasoning_has_visible_text(msg) is False


def test_multiple_signature_only_blocks_are_not_visible():
    msg = _msg(reasoning_details=[
        {"type": "thinking", "thinking": "", "signature": "sig1"},
        {"type": "thinking", "thinking": "", "signature": "sig2"},
    ])
    assert _reasoning_has_visible_text(msg) is False


def test_thinking_block_with_text_is_visible():
    """The display=summarized shape: readable thinking text present."""
    msg = _msg(reasoning_details=[
        {"type": "thinking", "thinking": "Let me work through this.",
         "signature": "EqQBCkgIBRABGAI..."},
    ])
    assert _reasoning_has_visible_text(msg) is True


def test_mixed_blocks_with_any_text_are_visible():
    msg = _msg(reasoning_details=[
        {"type": "thinking", "thinking": "", "signature": "sig1"},
        {"type": "thinking", "thinking": "step 2 reasoning", "signature": "sig2"},
    ])
    assert _reasoning_has_visible_text(msg) is True


def test_reasoning_string_field_is_visible():
    assert _reasoning_has_visible_text(_msg(reasoning="thought about it")) is True


def test_reasoning_content_field_is_visible():
    assert _reasoning_has_visible_text(_msg(reasoning_content="thinking...")) is True


def test_whitespace_only_reasoning_is_not_visible():
    msg = _msg(
        reasoning="  \n ",
        reasoning_details=[{"type": "thinking", "thinking": " ", "signature": "s"}],
    )
    assert _reasoning_has_visible_text(msg) is False


def test_no_reasoning_at_all_is_not_visible():
    assert _reasoning_has_visible_text(_msg()) is False


def test_redacted_thinking_block_is_not_visible():
    msg = _msg(reasoning_details=[{"type": "redacted_thinking", "data": "opaque"}])
    assert _reasoning_has_visible_text(msg) is False


def test_non_dict_details_are_tolerated():
    msg = _msg(reasoning_details=["garbage", None, 42])
    assert _reasoning_has_visible_text(msg) is False


# ── loop wiring invariants ───────────────────────────────────────────
# run_conversation is a 3,900-line closure-heavy loop; full harness tests
# live elsewhere.  These source-level invariants pin the recovery routing
# the same way test_gemini_fast_fallback.py pins the pool-helper call site.

_SOURCE = inspect.getsource(conversation_loop.run_conversation)


def test_prefill_branch_requires_visible_reasoning():
    """The prefill continuation must be gated on visible reasoning text,
    not merely the presence of structured reasoning fields."""
    assert "_has_visible_reasoning" in _SOURCE
    assert "_reasoning_has_visible_text(assistant_message)" in _SOURCE
    # The bare pre-fix gate must be gone.
    assert ("if _has_structured and agent._thinking_prefill_retries < 2:"
            not in _SOURCE)


def test_hidden_thinking_routes_to_synthetic_nudge():
    """Textless structured reasoning gets one synthetic-user nudge, marked
    synthetic so _persist_session strips it from failed turns."""
    assert "_hidden_thinking_nudged" in _SOURCE
    idx = _SOURCE.index("Hidden-thinking-only response")
    window = _SOURCE[idx:idx + 2200]
    assert "_empty_recovery_synthetic" in window
    assert '"role": "user"' in window


def test_hidden_thinking_nudge_fires_once_then_falls_through_to_retries():
    """After the nudge is spent, a repeat hidden-thinking response must
    qualify as prefill-exhausted so the empty-retry/fallback path runs
    instead of looping forever."""
    idx = _SOURCE.index("_prefill_exhausted = (")
    window = _SOURCE[idx:idx + 500]
    assert "_hidden_thinking_nudged" in window
    assert "not _has_visible_reasoning" in window


def test_turn_context_resets_hidden_thinking_flag():
    from agent import turn_context
    src = inspect.getsource(turn_context)
    assert "agent._hidden_thinking_nudged = False" in src
