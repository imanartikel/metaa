from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import requests

from config import AppConfig, require_telegram_bot_token
from draft_package import build_draft, generate_placeholder_image


logger = logging.getLogger(__name__)


class TelegramAPIError(RuntimeError):
    pass


class TelegramClient:
    def __init__(self, token: str, *, verify_ssl: bool = True) -> None:
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.session = requests.Session()
        self.verify_ssl = verify_ssl

        if not verify_ssl:
            requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]

    def get_me(self) -> dict[str, Any]:
        return self._request("getMe")

    def get_updates(self, *, offset: int | None = None, timeout: int = 25) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "timeout": timeout,
            "allowed_updates": json.dumps(["message"]),
        }
        if offset is not None:
            payload["offset"] = offset

        data = self._request("getUpdates", payload)
        result = data.get("result", [])
        if not isinstance(result, list):
            raise TelegramAPIError("Telegram getUpdates returned an invalid result.")
        return result

    def send_message(self, *, chat_id: int, text: str) -> None:
        self._request(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": True,
            },
        )

    def _request(self, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            response = self.session.post(
                f"{self.base_url}/{method}",
                data=payload or {},
                timeout=35,
                verify=self.verify_ssl,
            )
        except requests.RequestException as exc:
            raise TelegramAPIError(f"Telegram request failed for {method}: {exc.__class__.__name__}") from exc
        try:
            data = response.json()
        except ValueError as exc:
            raise TelegramAPIError(f"Telegram returned non-JSON response: {response.text}") from exc

        if not response.ok or not data.get("ok"):
            description = data.get("description") or response.reason
            raise TelegramAPIError(f"Telegram API error: {description}")
        return data


def run_telegram_whoami(config: AppConfig) -> int:
    token = require_telegram_bot_token(config)
    client = TelegramClient(token, verify_ssl=config.telegram_verify_ssl)
    bot = client.get_me().get("result", {})

    print("Telegram bot")
    print("------------")
    print(f"id: {bot.get('id', 'not returned')}")
    print(f"username: @{bot.get('username', 'not returned')}")
    print(f"name: {bot.get('first_name', 'not returned')}")
    return 0


def run_telegram_updates(config: AppConfig) -> int:
    token = require_telegram_bot_token(config)
    client = TelegramClient(token, verify_ssl=config.telegram_verify_ssl)

    print("Telegram updates")
    print("----------------")
    print("Kirim /start ke bot Telegram kamu, lalu command ini akan nampilin user id.")

    updates = client.get_updates(timeout=5)
    if not updates:
        print("Belum ada update. Kirim chat ke bot dulu, lalu ulangi command ini.")
        return 0

    for update in updates[-10:]:
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        from_user = message.get("from") or {}
        text = message.get("text") or ""
        print()
        print(f"update_id: {update.get('update_id')}")
        print(f"chat_id: {chat.get('id')}")
        print(f"user_id: {from_user.get('id')}")
        print(f"name: {from_user.get('first_name', '')} {from_user.get('last_name', '')}".strip())
        print(f"username: @{from_user.get('username')}" if from_user.get("username") else "username: not returned")
        print(f"text: {text}")
    return 0


def run_telegram_bot(config: AppConfig) -> int:
    token = require_telegram_bot_token(config)
    client = TelegramClient(token, verify_ssl=config.telegram_verify_ssl)
    bot = client.get_me().get("result", {})
    allowed = config.telegram_allowed_user_ids

    print("Meta Ads Drafter Telegram bot")
    print("-----------------------------")
    print(f"bot: @{bot.get('username', 'not returned')}")
    if allowed:
        print(f"allowed_user_ids: {', '.join(str(item) for item in sorted(allowed))}")
    else:
        print("allowed_user_ids: not set")
        print("WARNING: set TELEGRAM_ALLOWED_USER_IDS before using this outside local testing.")
    print("status: polling. Press Ctrl+C to stop.")

    offset: int | None = None
    while True:
        updates = client.get_updates(offset=offset, timeout=25)
        for update in updates:
            update_id = update.get("update_id")
            if isinstance(update_id, int):
                offset = update_id + 1
            _handle_update(client, config, update)
        time.sleep(0.5)


def _handle_update(client: TelegramClient, config: AppConfig, update: dict[str, Any]) -> None:
    message = update.get("message")
    if not isinstance(message, dict):
        return

    chat = message.get("chat") or {}
    from_user = message.get("from") or {}
    chat_id = chat.get("id")
    user_id = from_user.get("id")
    text = str(message.get("text") or "").strip()

    if not isinstance(chat_id, int) or not isinstance(user_id, int):
        return

    if config.telegram_allowed_user_ids and user_id not in config.telegram_allowed_user_ids:
        client.send_message(chat_id=chat_id, text=f"Unauthorized user_id: {user_id}")
        return

    try:
        reply = _handle_text_command(config, user_id=user_id, text=text)
    except Exception as exc:
        logger.exception("Telegram command failed")
        reply = f"Error: {exc}"

    client.send_message(chat_id=chat_id, text=reply)


def _handle_text_command(config: AppConfig, *, user_id: int, text: str) -> str:
    if not text or text in {"/start", "/help"}:
        return _help_text(user_id)

    if text == "/id":
        return f"user_id: {user_id}"

    if text.startswith("/draft"):
        brief = _parse_draft_command(text)
        draft_path, image_path = _create_draft_from_telegram_brief(config, brief)
        return (
            "Draft package dibuat.\n"
            f"draft_json: {draft_path}\n"
            f"placeholder_image: {image_path}\n\n"
            "Review dulu. Untuk push creative ke Meta, jalankan lokal:\n"
            f"python src/main.py create-creative-from-draft {draft_path}"
        )

    return "Command belum dikenal.\n\n" + _help_text(user_id)


def _help_text(user_id: int) -> str:
    return (
        "Meta Ad Drafter bot aktif.\n\n"
        f"user_id kamu: {user_id}\n\n"
        "Commands:\n"
        "/id - tampilkan user id\n"
        "/draft product | offer | audience | landing_url\n\n"
        "Contoh:\n"
        "/draft Bengkel Mobil WL | Gratis cek kaki-kaki | Pemilik mobil Jakarta | https://example.com"
    )


def _parse_draft_command(text: str) -> dict[str, Any]:
    body = text.removeprefix("/draft").strip()
    parts = [part.strip() for part in body.split("|")]
    if len(parts) != 4 or not all(parts):
        raise ValueError(
            "Format /draft salah. Pakai: /draft product | offer | audience | landing_url"
        )

    product_name, offer, audience, landing_url = parts
    return {
        "product_name": product_name,
        "offer": offer,
        "audience": audience,
        "pain_points": [
            "butuh solusi yang jelas",
            "ingin proses yang mudah",
            "ingin keputusan yang lebih aman",
        ],
        "benefits": [
            "penjelasan ringkas",
            "proses cepat",
            "bisa review sebelum lanjut",
        ],
        "landing_url": landing_url,
        "tone": "jelas, meyakinkan, tidak berlebihan",
        "cta": "LEARN_MORE",
    }


def _create_draft_from_telegram_brief(
    config: AppConfig,
    brief: dict[str, Any],
) -> tuple[Path, Path]:
    draft = build_draft(brief, config=config, use_ai=True)
    draft_dir = config.output_dir / "drafts"
    image_dir = config.project_root / "assets" / "generated"
    brief_dir = config.project_root / "input" / "telegram"
    draft_dir.mkdir(parents=True, exist_ok=True)
    image_dir.mkdir(parents=True, exist_ok=True)
    brief_dir.mkdir(parents=True, exist_ok=True)

    draft_id = str(draft["draft_id"])
    draft_path = draft_dir / f"{draft_id}.json"
    image_path = image_dir / f"{draft_id}.jpg"
    brief_path = brief_dir / f"{draft_id}_brief.json"

    generate_placeholder_image(
        image_path=image_path,
        headline=str(draft["creative"]["headline"]),
        subheadline=str(draft["creative"]["description"]),
        brand=str(brief.get("product_name", "Meta Ad Drafter")),
    )

    draft["image"] = {
        "provider": "placeholder",
        "status": "generated",
        "path": str(image_path),
    }

    with brief_path.open("w", encoding="utf-8") as file:
        json.dump(brief, file, indent=2, sort_keys=True)
        file.write("\n")

    with draft_path.open("w", encoding="utf-8") as file:
        json.dump(draft, file, indent=2, sort_keys=True)
        file.write("\n")

    return draft_path, image_path
