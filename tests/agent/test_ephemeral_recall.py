"""Ephemeral recall: memory prefetch is injected for the CURRENT turn only and never stored.

Default behavior (``memory.ephemeral_recall`` false) is the existing "persist what you send"
contract: prefetch rides the ``api_content`` sidecar and replays on every later turn.

With the flag on:
  * the persisted sidecar is composed WITHOUT the prefetch block (history does not grow by it);
  * the current turn's wire copy still carries the prefetch block on every API call of that turn;
  * the next turn replays the row without it.
"""

from __future__ import annotations

from types import SimpleNamespace

from agent.turn_context import _stamp_api_content_sidecar, build_api_messages, compose_user_api_content

RECALL = "RECALL-BLOCK-UNIQUE-7731"
PLUGIN = "PLUGIN-CTX-UNIQUE-2208"


class _SendAgent:
    api_mode = "chat_completions"
    ephemeral_system_prompt = None
    _compression_warning = None
    _current_turn_timestamp = 10_000.0
    _ephemeral_recall = False
    _persist_user_message_override = None
    _session_db = None
    session_id = "s-test"

    @staticmethod
    def _copy_reasoning_content_for_api(_source, _target):
        return None

    @staticmethod
    def _should_sanitize_tool_calls():
        return False


def _agent(ephemeral: bool):
    a = _SendAgent()
    a._ephemeral_recall = ephemeral
    return a


def _stamp(agent, content, recall, plugin):
    messages = [{"role": "user", "content": content}]
    _stamp_api_content_sidecar(agent, messages, 0, recall, plugin, preflight_compressed=False)
    return messages[0]


def _wire(agent, history, recall="", plugin=""):
    request, _ = build_api_messages(
        agent, history, current_turn_user_idx=len(history) - 1,
        ext_prefetch_cache=recall, plugin_user_context=plugin, moa_config=None, active_system_prompt="",
    )
    return request


# --------------------------------------------------------------------------- stamping

def test_flag_off_sidecar_carries_recall_regression():
    msg = _stamp(_agent(False), "hello", RECALL, "")
    assert RECALL in msg["api_content"]


def test_flag_on_sidecar_excludes_recall():
    msg = _stamp(_agent(True), "hello", RECALL, "")
    assert "api_content" not in msg  # nothing else injected -> no sidecar at all


def test_flag_on_sidecar_keeps_plugin_context_but_not_recall():
    msg = _stamp(_agent(True), "hello", RECALL, PLUGIN)
    assert PLUGIN in msg["api_content"]
    assert RECALL not in msg["api_content"]


# --------------------------------------------------------------------------- wire

def test_flag_on_current_turn_wire_has_recall_even_with_plugin_sidecar():
    agent = _agent(True)
    cur = _stamp(agent, "now", RECALL, PLUGIN)
    wire = _wire(agent, [cur], recall=RECALL, plugin=PLUGIN)
    sent = wire[-1]["content"]
    assert RECALL in sent and PLUGIN in sent and sent.startswith("now")


def test_flag_on_current_turn_wire_has_recall_without_sidecar():
    agent = _agent(True)
    cur = _stamp(agent, "now", RECALL, "")
    wire = _wire(agent, [cur], recall=RECALL)
    assert RECALL in wire[-1]["content"]


def test_flag_on_next_turn_replays_previous_turn_without_recall():
    agent = _agent(True)
    turn1 = _stamp(agent, "first", RECALL, "")
    history = [turn1, {"role": "assistant", "content": "ok"}, {"role": "user", "content": "second"}]
    wire = _wire(agent, history, recall="OTHER-RECALL-5519")
    assert RECALL not in wire[0]["content"]       # turn 1 replays clean
    assert "OTHER-RECALL-5519" in wire[-1]["content"]  # turn 2 carries its own recall


def test_flag_off_next_turn_still_replays_recall_regression():
    agent = _agent(False)
    turn1 = _stamp(agent, "first", RECALL, "")
    history = [turn1, {"role": "assistant", "content": "ok"}, {"role": "user", "content": "second"}]
    wire = _wire(agent, history, recall="")
    assert RECALL in wire[0]["content"]


def test_flag_on_every_api_call_of_the_turn_sends_identical_bytes():
    agent = _agent(True)
    cur = _stamp(agent, "now", RECALL, PLUGIN)
    a = _wire(agent, [cur], recall=RECALL, plugin=PLUGIN)[-1]["content"]
    history = [cur, {"role": "assistant", "content": "", "tool_calls": [
        {"id": "c1", "type": "function", "function": {"name": "x", "arguments": "{}"}}]},
        {"role": "tool", "content": "r", "tool_call_id": "c1"}]
    b = build_api_messages(agent, history, current_turn_user_idx=0, ext_prefetch_cache=RECALL,
                           plugin_user_context=PLUGIN, moa_config=None, active_system_prompt="")[0][0]["content"]
    assert a == b


def test_flag_on_matches_compose_helper_bytes():
    agent = _agent(True)
    cur = _stamp(agent, "now", RECALL, PLUGIN)
    sent = _wire(agent, [cur], recall=RECALL, plugin=PLUGIN)[-1]["content"]
    assert sent == compose_user_api_content("now", RECALL, PLUGIN)


# --------------------------------------------------------------------------- spill cap

def test_prefetch_spill_cap_override(monkeypatch):
    from agent.memory_manager import MemoryManager

    mm = MemoryManager()
    mm._external_prefetch_spill_config = {"enabled": True, "max_chars": 10_000,
                                          "preview_head": 500, "preview_tail": 500, "directory": None}
    mm.set_prefetch_spill_cap(24_000)
    assert mm._external_prefetch_spill_config["max_chars"] == 24_000
    assert mm._external_prefetch_spill_config["preview_head"] == 500  # other keys untouched
    mm.set_prefetch_spill_cap(None)  # None/0 = leave as is
    assert mm._external_prefetch_spill_config["max_chars"] == 24_000


# --------------------------------------------------------------------------- end to end
# Real AIAgent + mock provider + shared SessionDB (turn N+1 reloads history from the store).

from unittest.mock import MagicMock  # noqa: E402

from tests.agent.test_api_content_sidecar import (  # noqa: E402,F401  (wire_env is a fixture)
    _chat_requests,
    _tc_resp,
    _text_resp,
    _user_messages,
    wire_env,
)

_Q1 = "what did we decide about the reset policy last week"
_Q2 = "and what about the idle timeout value we settled on"


def _with_recall(agent, text, ephemeral):
    mm = MagicMock()
    mm.prefetch_all.return_value = text
    mm.describe_recall.return_value = ""
    agent._memory_manager = mm
    agent._ephemeral_recall = ephemeral
    return agent


def test_e2e_flag_on_recall_sent_every_call_never_stored_never_replayed(wire_env):
    make_agent, handler, db, sid = wire_env

    a1 = _with_recall(make_agent(), "RECALL-ONE-4410", ephemeral=True)
    handler.response_queue.append(_tc_resp("read_file", '{"file_path": "/nonexistent-path"}'))
    handler.response_queue.append(_text_resp("done"))
    a1.run_conversation(_Q1, conversation_history=[], task_id="t1")

    reqs = _chat_requests(handler)
    assert len(reqs) == 2
    sent_1 = _user_messages(reqs[0])[0]["content"]
    sent_2 = _user_messages(reqs[1])[0]["content"]
    assert "RECALL-ONE-4410" in sent_1 and "PLUGIN-CTX" in sent_1   # sent on call 1
    assert sent_2 == sent_1                                          # ...and identical on call 2

    row = [r for r in db.get_messages(sid) if r["role"] == "user"][0]
    assert row["content"] == _Q1
    assert "PLUGIN-CTX" in row["api_content"]
    assert "RECALL-ONE-4410" not in row["api_content"]               # never stored

    handler.captured_requests = []
    history = db.get_messages_as_conversation(sid)
    a2 = _with_recall(make_agent(), "RECALL-TWO-9027", ephemeral=True)
    a2.run_conversation(_Q2, conversation_history=history, task_id="t2")

    users = _user_messages(_chat_requests(handler)[0])
    assert "RECALL-ONE-4410" not in users[0]["content"]              # turn 1 replays without recall
    assert "PLUGIN-CTX" in users[0]["content"]                       # ...but keeps plugin context
    assert "RECALL-TWO-9027" in users[-1]["content"]                 # turn 2 carries its own recall
    assert "RECALL-ONE-4410" not in users[-1]["content"]


def test_e2e_flag_off_recall_persists_and_replays_regression(wire_env):
    make_agent, handler, db, sid = wire_env

    a1 = _with_recall(make_agent(), "RECALL-ONE-4410", ephemeral=False)
    a1.run_conversation(_Q1, conversation_history=[], task_id="t1")
    row = [r for r in db.get_messages(sid) if r["role"] == "user"][0]
    assert "RECALL-ONE-4410" in row["api_content"]

    handler.captured_requests = []
    history = db.get_messages_as_conversation(sid)
    a2 = _with_recall(make_agent(), "RECALL-TWO-9027", ephemeral=False)
    a2.run_conversation(_Q2, conversation_history=history, task_id="t2")
    users = _user_messages(_chat_requests(handler)[0])
    assert "RECALL-ONE-4410" in users[0]["content"]                  # unchanged default behavior


def test_e2e_flag_on_history_growth_is_recall_free(wire_env):
    """The point of the feature: the persisted bytes do not grow by the recall block."""
    make_agent, handler, db, sid = wire_env
    big = "R" * 15_000
    a1 = _with_recall(make_agent(), big, ephemeral=True)
    a1.run_conversation(_Q1, conversation_history=[], task_id="t1")
    row = [r for r in db.get_messages(sid) if r["role"] == "user"][0]
    stored = len(row["content"]) + len(row["api_content"] or "")
    assert stored < 1_000, stored
    assert big in _user_messages(_chat_requests(handler)[0])[0]["content"]  # but it WAS sent
