from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import requests

from config import AppConfig, require_telegram_bot_token
from create_creative import _save_creative_artifact
from create_paused_draft import create_paused_draft_ad_from_creative
from draft_package import build_draft, generate_placeholder_image
from meta_api import MetaAPI


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
        try:
            updates = client.get_updates(offset=offset, timeout=20)
            for update in updates:
                update_id = update.get("update_id")
                if isinstance(update_id, int):
                    offset = update_id + 1
                _handle_update(client, config, update)
        except TelegramAPIError as exc:
            logger.warning("Telegram polling error: %s", exc)
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

    if text == "/list_drafts":
        return _list_drafts(config)

    if text.startswith("/preview"):
        draft_ref = text.removeprefix("/preview").strip()
        return _preview_draft(config, draft_ref)

    if text.startswith("/push_draft"):
        draft_ref = text.removeprefix("/push_draft").strip()
        return _push_draft_to_meta(config, draft_ref)

    if text.startswith("/attach_image"):
        body = text.removeprefix("/attach_image").strip()
        return _attach_manual_image(config, body)

    if text.startswith("/draft"):
        brief = _parse_draft_command(text, config)
        draft_path, image_path = _create_draft_from_telegram_brief(config, brief)
        draft = _load_json(draft_path)
        return (
            "Draft package dibuat.\n"
            f"draft_id: {draft.get('draft_id')}\n"
            f"alias: {_alias_for_draft_path(config, draft_path)}\n"
            f"source: {draft.get('source', {}).get('type')}\n"
            f"draft_json: {draft_path}\n"
            f"placeholder_image: {image_path}\n\n"
            f"Review: /preview {_alias_for_draft_path(config, draft_path)}\n"
            f"Push PAUSED ke Meta: /push_draft {_alias_for_draft_path(config, draft_path)}"
        )

    return "Command belum dikenal.\n\n" + _help_text(user_id)


def _help_text(user_id: int) -> str:
    return (
        "Meta Ad Drafter bot aktif.\n\n"
        f"user_id kamu: {user_id}\n\n"
        "Commands:\n"
        "/id - tampilkan user id\n"
        "/draft product | offer | audience | landing_url | budget | gender\n"
        "/list_drafts - lihat 5 draft terbaru\n"
        "/preview d1 - lihat copy draft\n"
        "/attach_image d1 | filename.jpg - pakai gambar manual dari assets/manual\n"
        "/push_draft d1 - upload + create creative + create PAUSED ad\n\n"
        "Contoh:\n"
        "/draft Bengkel Mobil WL | Gratis cek kaki-kaki | Pemilik mobil Jakarta | https://example.com | 75000 | all\n"
        "/list_drafts\n"
        "/preview d1\n"
        "/attach_image d1 | bengkel_wl_01.jpg\n"
        "/push_draft d1"
    )


def _parse_draft_command(text: str, config: AppConfig) -> dict[str, Any]:
    body = text.removeprefix("/draft").strip()
    parts = [part.strip() for part in body.split("|")]
    if len(parts) not in {6, 7} or not all(parts):
        raise ValueError(
            "Format /draft salah. Pakai: /draft product | offer | audience | landing_url | budget | gender"
        )

    ad_settings = {
        "daily_budget": 50000,
        "country": "ID",
        "geo_preset": "JAVA_BALI",
        "region_keys": ["1664", "4143", "1685", "1666", "1669", "1667", "1662"],
        "age_min": 25,
        "age_max": 65,
        "gender": "all",
        "objective": config.meta_campaign_objective,
        "optimization_goal": "LINK_CLICKS",
    }

    if len(parts) == 6:
        product_name, offer, audience, landing_url, budget, gender = parts
        ad_settings.update(
            {
                "daily_budget": _parse_positive_int(budget, "budget"),
                "gender": _normalize_gender(gender),
            }
        )
    elif len(parts) == 7:
        # Legacy support for previous format: budget | country | age.
        product_name, offer, audience, landing_url, budget, country, age_range = parts
        age_min, age_max = _parse_age_range(age_range)
        ad_settings.update(
            {
                "daily_budget": _parse_positive_int(budget, "budget"),
                "country": country.upper(),
                "age_min": age_min,
                "age_max": age_max,
                "gender": "all",
            }
        )
    brief = {
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
        "ad_settings": ad_settings,
    }
    return brief


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


def _list_drafts(config: AppConfig) -> str:
    draft_paths = _latest_draft_paths(config, limit=5)
    if not draft_paths:
        return "Belum ada draft. Buat dulu pakai /draft product | offer | audience | landing_url"

    lines = ["Draft terbaru:"]
    for path in draft_paths:
        try:
            draft = _load_json(path)
            alias = _alias_for_draft_path(config, path)
            source = draft.get("source", {}).get("type", "unknown")
            creative = draft.get("creative", {})
            headline = creative.get("headline", "no headline")
            lines.append(f"- {alias} | {draft.get('draft_id')} | {source} | {headline}")
        except Exception:
            lines.append(f"- {path.stem} | unreadable")
    return "\n".join(lines)


def _preview_draft(config: AppConfig, draft_ref: str) -> str:
    path = _resolve_draft_path(config, draft_ref)
    draft = _load_json(path)
    creative = draft.get("creative", {})
    strategy = draft.get("strategy", {})
    image = draft.get("image", {})
    source = draft.get("source", {})
    ad_settings = draft.get("brief", {}).get("ad_settings", {})

    return (
        "Draft preview\n"
        f"draft_id: {draft.get('draft_id')}\n"
        f"source: {source.get('type')} {source.get('ai_model') or ''}\n"
        f"angle: {strategy.get('angle', 'not returned')}\n\n"
        f"headline: {creative.get('headline')}\n"
        f"primary_text: {creative.get('primary_text')}\n"
        f"description: {creative.get('description')}\n"
        f"cta: {creative.get('cta')}\n"
        f"link: {creative.get('link_url')}\n"
        f"budget: {ad_settings.get('daily_budget', 50000)}\n"
        f"target: {ad_settings.get('geo_preset', 'JAVA_BALI')} age {ad_settings.get('age_min', 25)}-{ad_settings.get('age_max', 65)} gender {ad_settings.get('gender', 'all')}\n"
        f"image: {image.get('path')}\n\n"
        f"Attach manual image:\n/attach_image {draft.get('draft_id')} | filename.jpg\n\n"
        f"Push PAUSED ke Meta:\n/push_draft {draft.get('draft_id')}"
    )


def _attach_manual_image(config: AppConfig, body: str) -> str:
    parts = [part.strip() for part in body.split("|", 1)]
    if len(parts) != 2 or not all(parts):
        raise ValueError("Format: /attach_image draft_id | filename.jpg")

    draft_ref, filename = parts
    if any(char in filename for char in ["\\", "/", ":"]):
        raise ValueError("filename saja, tanpa path. Taruh file di assets/manual/.")

    manual_path = config.project_root / "assets" / "manual" / filename
    if not manual_path.exists() or not manual_path.is_file():
        raise FileNotFoundError(f"Gambar tidak ditemukan: {manual_path}")
    if manual_path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
        raise ValueError("Format gambar harus .jpg, .jpeg, atau .png")

    draft_path = _resolve_draft_path(config, draft_ref)
    draft = _load_json(draft_path)
    draft["image"] = {
        "provider": "manual",
        "status": "attached",
        "path": str(manual_path),
        "filename": filename,
    }

    with draft_path.open("w", encoding="utf-8") as file:
        json.dump(draft, file, indent=2, sort_keys=True)
        file.write("\n")

    return (
        "Manual image attached.\n"
        f"draft_id: {draft.get('draft_id')}\n"
        f"image: {manual_path}\n\n"
        f"Preview: /preview {draft.get('draft_id')}\n"
        f"Push: /push_draft {draft.get('draft_id')}"
    )


def _push_draft_to_meta(config: AppConfig, draft_ref: str) -> str:
    path = _resolve_draft_path(config, draft_ref)
    draft = _load_json(path)
    creative = _expect_dict(draft.get("creative"), "creative")
    image = _expect_dict(draft.get("image"), "image")
    image_path_value = image.get("path")
    if not image_path_value:
        raise ValueError("Draft belum punya image path.")

    draft_id = str(draft.get("draft_id") or path.stem)
    api = MetaAPI(config)
    ad_account_id = config.ad_account_id
    page_id = config.page_id
    if not ad_account_id:
        raise ValueError("META_AD_ACCOUNT_ID belum diisi.")
    if not page_id:
        raise ValueError("META_PAGE_ID belum diisi.")

    uploaded = api.upload_image(Path(str(image_path_value)), ad_account_id)
    creative_result = api.create_image_ad_creative(
        ad_account_id=ad_account_id,
        page_id=page_id,
        name=str(creative["name"]),
        image_hash=uploaded.image_hash,
        link_url=str(creative["link_url"]),
        message=str(creative["primary_text"]),
        headline=str(creative["headline"]),
        description=str(creative.get("description") or ""),
        call_to_action_type=str(creative.get("cta") or "LEARN_MORE"),
        url_tags=str(creative["url_tags"]) if creative.get("url_tags") else None,
    )
    creative_artifact = _save_creative_artifact(
        config=config,
        creative_id=creative_result.creative_id,
        payload={
            "draft_id": draft_id,
            "creative": creative,
            "image_hash": uploaded.image_hash,
        },
        raw_response=creative_result.raw_response,
    )

    ad_settings = _expect_dict(draft.get("brief", {}).get("ad_settings", {}), "brief.ad_settings")
    daily_budget = int(ad_settings.get("daily_budget") or 50000)
    country = str(ad_settings.get("country") or "ID")
    region_keys = [str(key) for key in ad_settings.get("region_keys", [])]
    age_min = int(ad_settings.get("age_min") or 25)
    age_max = int(ad_settings.get("age_max") or 65)
    gender = str(ad_settings.get("gender") or "all")

    safe_name = draft_id[:80]
    paused_result, paused_artifact = create_paused_draft_ad_from_creative(
        api,
        config,
        creative_id=creative_result.creative_id,
        campaign_name=f"AI Draft - {safe_name}",
        adset_name=f"AI Draft Ad Set - {safe_name}",
        ad_name=f"AI Draft Ad - {safe_name}",
        daily_budget=daily_budget,
        country=country,
        region_keys=region_keys,
        age_min=age_min,
        age_max=age_max,
        gender=gender,
    )

    return (
        "Draft pushed ke Meta sebagai PAUSED.\n"
        f"draft_id: {draft_id}\n"
        f"creative_id: {creative_result.creative_id}\n"
        f"image_hash: {uploaded.image_hash}\n"
        f"campaign_id: {paused_result.campaign_id}\n"
        f"adset_id: {paused_result.adset_id}\n"
        f"ad_id: {paused_result.ad_id}\n\n"
        f"budget: {daily_budget}\n"
        f"target: {ad_settings.get('geo_preset', 'JAVA_BALI')} age {age_min}-{age_max} gender {gender}\n"
        "Status: campaign/adset/ad PAUSED. Tidak ada publish ACTIVE.\n"
        f"creative_artifact: {creative_artifact}\n"
        f"paused_artifact: {paused_artifact}"
    )


def _latest_draft_paths(config: AppConfig, *, limit: int) -> list[Path]:
    draft_dir = config.output_dir / "drafts"
    if not draft_dir.exists():
        return []
    paths = [path for path in draft_dir.glob("*.json") if path.is_file()]
    paths.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return paths[:limit]


def _resolve_draft_path(config: AppConfig, draft_ref: str) -> Path:
    if not draft_ref:
        raise ValueError("Masukkan draft_id. Contoh: /preview draft_...")

    alias_path = _resolve_draft_alias(config, draft_ref)
    if alias_path:
        return alias_path

    candidate = Path(draft_ref)
    if candidate.exists():
        return candidate

    draft_dir = config.output_dir / "drafts"
    if not draft_ref.endswith(".json"):
        draft_ref = f"{draft_ref}.json"
    path = draft_dir / draft_ref
    if not path.exists():
        raise FileNotFoundError(f"Draft tidak ditemukan: {path}")
    return path


def _resolve_draft_alias(config: AppConfig, draft_ref: str) -> Path | None:
    normalized = draft_ref.strip().lower()
    if not normalized.startswith("d"):
        return None
    number_text = normalized[1:]
    if not number_text.isdigit():
        return None

    index = int(number_text)
    if index <= 0:
        return None

    draft_paths = _latest_draft_paths(config, limit=max(index, 20))
    if index > len(draft_paths):
        raise FileNotFoundError(f"Alias tidak ditemukan: {draft_ref}")
    return draft_paths[index - 1]


def _alias_for_draft_path(config: AppConfig, draft_path: Path) -> str:
    draft_paths = _latest_draft_paths(config, limit=20)
    resolved = draft_path.resolve()
    for index, path in enumerate(draft_paths, start=1):
        if path.resolve() == resolved:
            return f"d{index}"
    return draft_path.stem


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"JSON harus object: {path}")
    return data


def _expect_dict(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Draft field bukan object: {field_name}")
    return value


def _parse_positive_int(value: str, field_name: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} harus angka.") from exc
    if parsed <= 0:
        raise ValueError(f"{field_name} harus lebih dari 0.")
    return parsed


def _parse_age_range(value: str) -> tuple[int, int]:
    if "-" not in value:
        raise ValueError("age harus format min-max, contoh 25-55.")
    raw_min, raw_max = [part.strip() for part in value.split("-", 1)]
    age_min = _parse_positive_int(raw_min, "age_min")
    age_max = _parse_positive_int(raw_max, "age_max")
    if age_min < 13:
        raise ValueError("age_min minimal 13.")
    if age_max > 65:
        raise ValueError("age_max maksimal 65 untuk placeholder targeting.")
    if age_min > age_max:
        raise ValueError("age_min tidak boleh lebih besar dari age_max.")
    return age_min, age_max


def _normalize_gender(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"all", "semua", "any", "bebas"}:
        return "all"
    if normalized in {"male", "pria", "cowok", "laki", "laki-laki", "men"}:
        return "pria"
    if normalized in {"female", "wanita", "cewek", "perempuan", "women"}:
        return "wanita"
    raise ValueError("gender harus salah satu: all, pria, wanita.")
