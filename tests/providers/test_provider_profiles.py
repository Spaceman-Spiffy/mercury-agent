"""Tests for the provider module registry and profiles."""

from providers import ProviderProfile, get_provider_profile


class TestOpenRouterProfile:

    def test_sticky_session_id_normalizes_cron_timestamp(self):
        """Cron re-fires of the same job keep the same sticky routing key."""
        p = get_provider_profile("openrouter")
        first = p.build_extra_body(session_id="cron_job42_20260801_090000")
        second = p.build_extra_body(session_id="cron_job42_20260802_090000")
        assert first["session_id"] == "cron_job42"
        assert first["session_id"] == second["session_id"]

    def test_pareto_min_coding_score_emitted_for_pareto_model(self):
        """min_coding_score → plugins block when model is openrouter/pareto-code."""
        p = get_provider_profile("openrouter")
        body = p.build_extra_body(
            model="openrouter/pareto-code",
            openrouter_min_coding_score=0.65,
        )
        assert body["plugins"] == [
            {"id": "pareto-router", "min_coding_score": 0.65}
        ]

    def test_grok_session_id_sets_cache_affinity_header(self):
        """OpenRouter + Grok model + session_id => x-grok-conv-id header."""
        p = get_provider_profile("openrouter")
        _, tl = p.build_api_kwargs_extras(
            model="x-ai/grok-4",
            session_id="sess-abc123",
        )
        assert tl["extra_headers"]["x-grok-conv-id"] == "sess-abc123"

    def test_grok_conv_id_normalizes_cron_timestamp(self):
        """Cron re-fires of the same job must pin to the same xAI backend,
        same as the body.session_id sticky key (#78941)."""
        p = get_provider_profile("openrouter")
        _, first = p.build_api_kwargs_extras(
            model="x-ai/grok-4", session_id="cron_job42_20260801_090000",
        )
        _, second = p.build_api_kwargs_extras(
            model="x-ai/grok-4", session_id="cron_job42_20260802_090000",
        )
        assert first["extra_headers"]["x-grok-conv-id"] == "cron_job42"
        assert (
            first["extra_headers"]["x-grok-conv-id"]
            == second["extra_headers"]["x-grok-conv-id"]
        )

    # --- reasoning-mandatory Anthropic effort → top-level verbosity (#43432) ---
    #
    # These models (Claude 4.6+ / fable / mythos-class) ignore
    # ``reasoning.effort`` and use adaptive thinking. OpenRouter honors the
    # requested effort on the top-level ``verbosity`` field instead (maps to
    # Anthropic ``output_config.effort``). The profile must route the existing
    # ``reasoning_config["effort"]`` there while still NEVER emitting a
    # ``reasoning`` field (which would 400 — see #42991).

    def test_mandatory_anthropic_verbosity_coexists_with_grok_header(self):
        """A reasoning-mandatory Anthropic model is never a Grok model, but the
        top-level dict must remain a single merged dict — verify the verbosity
        path doesn't clobber the extra_headers slot used by Grok affinity."""
        p = get_provider_profile("openrouter")
        # mandatory anthropic + effort → verbosity, no extra_headers
        _, tl = p.build_api_kwargs_extras(
            reasoning_config={"enabled": True, "effort": "high"},
            supports_reasoning=True,
            model="anthropic/claude-fable-5",
        )
        assert tl == {"verbosity": "high"}

    def test_speed_tier_slugs_pin_endpoints_and_rewrite_wire_model(self):
        """Nous-style ``-fast``/``-flex`` slugs are OpenRouter ENDPOINTS of the base model: the wire
        model must be the base slug and ``provider.only`` must select exactly that tier, while the
        user's other routing prefs survive. The base slug itself is pinned off the flex/fast tiers."""
        import inspect
        p = get_provider_profile("openrouter")
        pins = inspect.getmodule(type(p)).OPENROUTER_ENDPOINT_PINS
        for slug, (base, tags) in pins.items():
            _, tl = p.build_api_kwargs_extras(model=slug)
            body = p.build_extra_body(model=slug, provider_preferences={"ignore": ["deepinfra"]})
            assert tl.get("model", slug) == base
            assert body["provider"] == {"ignore": ["deepinfra"], "only": list(tags)}
            tiered = [t for t in tags if t.endswith(("/fast", "/flex"))]
            assert tiered == ([] if slug == base else list(tags))
        # Unpinned model: no rewrite, prefs pass through untouched.
        _, tl = p.build_api_kwargs_extras(model="openai/gpt-5.6-sol")
        assert "model" not in tl
        assert p.build_extra_body(model="openai/gpt-5.6-sol", provider_preferences={"ignore": ["x"]})["provider"] == {"ignore": ["x"]}


class TestNousProfile:

    def test_sticky_session_id_normalizes_cron_timestamp(self):
        """Cron re-fires of the same job keep the same sticky routing key."""
        p = get_provider_profile("nous")
        first = p.build_extra_body(session_id="cron_job42_20260801_090000")
        second = p.build_extra_body(session_id="cron_job42_20260802_090000")
        assert first["session_id"] == "cron_job42"
        assert first["session_id"] == second["session_id"]

    def test_extra_body_ignores_provider_preferences(self):
        """Nous Portal rejects caller-supplied provider routing prefs (HTTP 400)."""
        p = get_provider_profile("nous")
        body = p.build_extra_body(
            provider_preferences={"allow": ["anthropic"], "sort": "price"}
        )
        assert "provider" not in body
        assert "tags" in body

    def test_kimi_model_no_thinking_keep_via_portal(self):
        """Nous portal does NOT honor thinking.keep (proven inert 2026-06-06),
        so the nous profile must NOT inject it for Kimi models. Preserved
        Thinking lives on the Moonshot-direct kimi-coding provider instead."""
        p = get_provider_profile("nous")
        eb, _ = p.build_api_kwargs_extras(
            reasoning_config={"enabled": True, "effort": "medium"},
            supports_reasoning=True,
            model="moonshotai/kimi-k2.6",
        )
        assert "thinking" not in eb
        assert eb["reasoning"] == {"enabled": True, "effort": "medium"}

    def test_base_url_uses_inference_api_host(self):
        """Live endpoint is inference-api.nousresearch.com (not inference.…)."""
        p = get_provider_profile("nous")
        assert p.base_url == "https://inference-api.nousresearch.com/v1"

    def test_non_kimi_model_no_thinking(self):
        """Non-Kimi models should not receive the thinking key."""
        p = get_provider_profile("nous")
        eb, _ = p.build_api_kwargs_extras(
            reasoning_config={"enabled": True, "effort": "medium"},
            supports_reasoning=True,
            model="anthropic/claude-opus-4",
        )
        assert "thinking" not in eb

    def test_kimi_disabled_reasoning_no_thinking(self):
        """When reasoning is disabled, no thinking key should be added."""
        p = get_provider_profile("nous")
        eb, _ = p.build_api_kwargs_extras(
            reasoning_config={"enabled": False},
            supports_reasoning=True,
            model="moonshotai/kimi-k2.6",
        )
        assert "thinking" not in eb
        assert "reasoning" not in eb


class TestQwenProfile:

    def test_prepare_messages_protects_nested_image_url_retry_mutation(self):
        qwen = get_provider_profile("qwen-oauth")
        image_url = {"url": "data:image/png;base64,original"}
        msgs = [
            {"role": "system", "content": "Be helpful"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "see image"},
                    {"type": "image_url", "image_url": image_url},
                ],
            },
        ]

        qwen_result = qwen.prepare_messages(msgs)

        assert qwen_result[1] is not msgs[1]
        assert qwen_result[1]["content"] is not msgs[1]["content"]
        assert qwen_result[1]["content"][1] is not msgs[1]["content"][1]
        assert qwen_result[1]["content"][1]["image_url"] is not image_url

        qwen_result[1]["content"][1]["image_url"]["url"] = (
            "data:image/png;base64,shrunk"
        )
        assert msgs[1]["content"][1]["image_url"]["url"] == (
            "data:image/png;base64,original"
        )

    def test_metadata_top_level(self):
        p = get_provider_profile("qwen-oauth")
        meta = {"sessionId": "s123", "promptId": "p456"}
        eb, tl = p.build_api_kwargs_extras(qwen_session_metadata=meta)
        assert tl["metadata"] == meta
        assert "metadata" not in eb


class TestKimiCodingProfile:
    """Moonshot-direct provider — Preserved Thinking lives here (portal drops it)."""

    def test_k26_injects_thinking_keep_all(self):
        p = get_provider_profile("kimi-coding")
        eb, tl = p.build_api_kwargs_extras(
            reasoning_config={"enabled": True},
            model="kimi-k2.6",
        )
        assert eb["thinking"] == {"type": "enabled", "keep": "all"}
        assert "reasoning_effort" not in tl

    def test_k26_no_config_still_keeps(self):
        p = get_provider_profile("kimi-coding")
        eb, tl = p.build_api_kwargs_extras(reasoning_config=None, model="kimi-k2.6")
        assert eb["thinking"] == {"type": "enabled", "keep": "all"}

    def test_thinking_disabled_no_keep(self):
        p = get_provider_profile("kimi-coding")
        eb, _ = p.build_api_kwargs_extras(
            reasoning_config={"enabled": False}, model="kimi-k2.6"
        )
        assert eb["thinking"] == {"type": "disabled"}
        assert "keep" not in eb["thinking"]

    def test_non_thinking_kimi_no_keep(self):
        """Non-thinking Kimi models (turbo, k2.5) must NOT get keep."""
        p = get_provider_profile("kimi-coding")
        for model in ("kimi-k2-turbo-preview", "kimi-k2.5"):
            eb, _ = p.build_api_kwargs_extras(
                reasoning_config={"enabled": True}, model=model
            )
            assert eb["thinking"] == {"type": "enabled"}
            assert "keep" not in eb["thinking"]


class TestBaseProfile:
    def test_prepare_messages_passthrough(self):
        p = ProviderProfile(name="test")
        msgs = [{"role": "user", "content": "hi"}]
        assert p.prepare_messages(msgs) is msgs


class TestAlibabaRegionalAndTokenPlanProfiles:
    """#73265: the models.dev catalog advertises alibaba-cn /
    alibaba-token-plan(-cn) / alibaba-coding-plan-cn, but none were registered
    at runtime — `model.provider: alibaba-coding-plan-cn` failed with
    "Unknown provider" and users were forced onto the `custom` escape hatch.
    Profile names intentionally match the catalog keys exactly so model
    metadata lines up."""

    def test_cn_variants_resolve_in_auth_registry(self, monkeypatch):
        """The reporter's exact failure site: ``auth.resolve_provider()`` only
        consults PROVIDER_REGISTRY (auto-extended from provider profiles,
        hermes_cli/auth.py:461-490) and raised
        "Unknown provider 'alibaba-coding-plan-cn'" (hermes_cli/auth.py:1937)
        even though the models.dev catalog advertised the id — the
        resolve_provider_full() catalog chain covers only the CLI --provider
        path, not the credential/runtime path."""
        from hermes_cli.auth import PROVIDER_REGISTRY, resolve_provider
        monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
        monkeypatch.setenv("ALIBABA_CODING_PLAN_API_KEY", "sk-test")
        monkeypatch.setenv("ALIBABA_TOKEN_PLAN_API_KEY", "sk-test")
        for pid in ("alibaba-cn", "alibaba-coding-plan-cn",
                    "alibaba-token-plan", "alibaba-token-plan-cn"):
            assert pid in PROVIDER_REGISTRY, f"{pid} missing from PROVIDER_REGISTRY"
            assert resolve_provider(pid) == pid
            assert (PROVIDER_REGISTRY[pid].inference_base_url
                    == get_provider_profile(pid).base_url)
