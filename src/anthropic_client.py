from __future__ import annotations

import json
import logging
from typing import Any

import requests

from config import AppConfig


logger = logging.getLogger(__name__)

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


class AnthropicAPIError(RuntimeError):
    pass


class AnthropicClient:
    def __init__(self, *, api_key: str, model: str, verify_ssl: bool = True) -> None:
        self.api_key = api_key
        self.model = model
        self.verify_ssl = verify_ssl
        self.session = requests.Session()

        if not verify_ssl:
            requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]

    def generate_ad_draft(self, brief: dict[str, Any]) -> dict[str, Any]:
        response = self._messages(
            system=_system_prompt(),
            user=_user_prompt(brief),
            max_tokens=1400,
            temperature=0.7,
        )
        text = _extract_text(response)
        parsed = _parse_json_text(text)
        return _normalize_ai_draft(parsed, brief=brief, model=self.model)

    def _messages(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float,
    ) -> dict[str, Any]:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }

        try:
            response = self.session.post(
                ANTHROPIC_MESSAGES_URL,
                headers=headers,
                json=payload,
                timeout=60,
                verify=self.verify_ssl,
            )
        except requests.RequestException as exc:
            raise AnthropicAPIError(
                f"Anthropic request failed: {exc.__class__.__name__}"
            ) from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise AnthropicAPIError("Anthropic returned non-JSON response.") from exc

        if not response.ok:
            error = data.get("error") if isinstance(data, dict) else None
            message = error.get("message") if isinstance(error, dict) else response.reason
            raise AnthropicAPIError(f"Anthropic API error: {message}")

        return data


def build_ai_draft_if_available(config: AppConfig, brief: dict[str, Any]) -> dict[str, Any] | None:
    if not config.anthropic_api_key:
        return None

    client = AnthropicClient(
        api_key=config.anthropic_api_key,
        model=config.anthropic_model,
        verify_ssl=config.anthropic_verify_ssl,
    )
    return client.generate_ad_draft(brief)


def _system_prompt() -> str:
    return (
        "You are a senior Meta ads strategist and direct-response copywriter. "
        "Create safe draft ad copy for manual review. Never suggest publishing active ads. "
        "Avoid exaggerated guarantees, medical/legal/financial claims, and discriminatory targeting. "
        "Return only valid JSON. No markdown."
    )


def _user_prompt(brief: dict[str, Any]) -> str:
    return (
        "Create a Meta image ad draft from this brief.\n"
        f"Brief JSON:\n{json.dumps(brief, ensure_ascii=True, indent=2)}\n\n"
        "Return JSON with exactly these top-level keys:\n"
        "strategy, creative, safety.\n\n"
        "creative must include: name, primary_text, headline, description, cta, "
        "link_url, url_tags, image_prompt.\n"
        "strategy must include: angle, customer_pain, benefits, targeting_notes.\n"
        "safety must include: status, creates_campaign, creates_adset, creates_ad, "
        "publishes_active_ads, requires_manual_review.\n\n"
        "Use Indonesian language for ad copy. Keep headline short. CTA must be one of "
        "LEARN_MORE, SIGN_UP, SHOP_NOW, CONTACT_US, BOOK_NOW, GET_QUOTE. "
        "Set safety.status to DRAFT_ONLY and all creation/publish booleans to false "
        "except requires_manual_review true."
    )


def _extract_text(response: dict[str, Any]) -> str:
    content = response.get("content", [])
    if not isinstance(content, list):
        raise AnthropicAPIError("Anthropic response missing content list.")

    parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))

    text = "\n".join(parts).strip()
    if not text:
        raise AnthropicAPIError("Anthropic response contained no text.")
    return text


def _parse_json_text(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise AnthropicAPIError("Anthropic did not return valid JSON.") from exc

    if not isinstance(parsed, dict):
        raise AnthropicAPIError("Anthropic JSON response must be an object.")
    return parsed


def _normalize_ai_draft(
    ai_payload: dict[str, Any],
    *,
    brief: dict[str, Any],
    model: str,
) -> dict[str, Any]:
    from draft_package import make_draft_shell

    draft = make_draft_shell(
        brief=brief,
        source_type="anthropic",
        ai_model=model,
        notes="Generated by Claude Haiku via Anthropic Messages API.",
    )

    strategy = ai_payload.get("strategy")
    creative = ai_payload.get("creative")
    safety = ai_payload.get("safety")

    if not isinstance(strategy, dict) or not isinstance(creative, dict):
        raise AnthropicAPIError("Anthropic JSON missing strategy or creative object.")

    required_creative_fields = {
        "name",
        "primary_text",
        "headline",
        "description",
        "cta",
        "link_url",
        "url_tags",
        "image_prompt",
    }
    missing = [field for field in required_creative_fields if not creative.get(field)]
    if missing:
        raise AnthropicAPIError(f"Anthropic JSON missing creative fields: {', '.join(missing)}")

    draft["strategy"] = strategy
    draft["creative"] = {
        "name": str(creative["name"]),
        "primary_text": str(creative["primary_text"]),
        "headline": str(creative["headline"]),
        "description": str(creative["description"]),
        "cta": str(creative["cta"]).upper(),
        "link_url": str(creative["link_url"]),
        "url_tags": str(creative["url_tags"]),
        "image_prompt": str(creative["image_prompt"]),
    }

    if isinstance(safety, dict):
        draft["safety"].update(safety)

    draft["safety"].update(
        {
            "status": "DRAFT_ONLY",
            "creates_campaign": False,
            "creates_adset": False,
            "creates_ad": False,
            "publishes_active_ads": False,
            "requires_manual_review": True,
        }
    )
    return draft
