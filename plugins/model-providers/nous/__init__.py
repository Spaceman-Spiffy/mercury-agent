"""Nous Portal provider profile."""

from typing import Any

from agent.portal_tags import nous_portal_tags
from providers import register_provider
from providers.base import ProviderProfile


class NousProfile(ProviderProfile):
    """Nous Portal — product tags, reasoning with Nous-specific omission.

    When the active model is a Kimi-family variant, injects
    ``extra_body["thinking"]["keep"] = "all"`` so historical
    ``reasoning_content`` is preserved across multi-turn conversations.
    """

    def build_extra_body(
        self, *, session_id: str | None = None, **context
    ) -> dict[str, Any]:
        return {"tags": nous_portal_tags()}

    @staticmethod
    def _is_kimi_model(model: str | None) -> bool:
        if not model:
            return False
        m = model.lower()
        return "kimi" in m or "moonshot" in m

    def build_api_kwargs_extras(
        self,
        *,
        reasoning_config: dict | None = None,
        supports_reasoning: bool = False,
        model: str | None = None,
        **context,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Nous: passes full reasoning_config, but OMITS when disabled.

        Kimi-family models also receive ``thinking.keep="all"`` so
        reasoning is preserved across turns.
        """
        extra_body = {}
        if supports_reasoning:
            if reasoning_config is not None:
                rc = dict(reasoning_config)
                if rc.get("enabled") is False:
                    pass  # Nous omits reasoning when disabled
                else:
                    extra_body["reasoning"] = rc
            else:
                extra_body["reasoning"] = {"enabled": True, "effort": "medium"}

        # Kimi via Nous portal: preserve reasoning across multi-turn conversations
        if self._is_kimi_model(model):
            _thinking = extra_body.get("thinking")
            if isinstance(_thinking, dict):
                _thinking["keep"] = "all"
            else:
                extra_body["thinking"] = {"keep": "all"}

        return extra_body, {}


nous = NousProfile(
    name="nous",
    aliases=("nous-portal", "nousresearch"),
    env_vars=("NOUS_API_KEY",),
    display_name="Nous Research",
    description="Nous Research — Hermes model family",
    signup_url="https://nousresearch.com/",
    fallback_models=(
        "hermes-3-405b",
        "hermes-3-70b",
    ),
    base_url="https://inference.nousresearch.com/v1",
    auth_type="oauth_device_code",
)

register_provider(nous)
