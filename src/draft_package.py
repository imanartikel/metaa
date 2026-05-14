from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from textwrap import shorten
from typing import Any

from config import AppConfig


def run_draft_package(
    config: AppConfig,
    *,
    brief_path: Path,
    no_image: bool,
) -> int:
    resolved_brief_path = (
        brief_path if brief_path.is_absolute() else config.project_root / brief_path
    )
    brief = _load_brief(resolved_brief_path)
    draft = build_placeholder_draft(brief)

    draft_dir = config.output_dir / "drafts"
    image_dir = config.project_root / "assets" / "generated"
    draft_dir.mkdir(parents=True, exist_ok=True)
    image_dir.mkdir(parents=True, exist_ok=True)

    draft_id = draft["draft_id"]
    image_path = image_dir / f"{draft_id}.jpg"
    draft_path = draft_dir / f"{draft_id}.json"

    if no_image:
        draft["image"] = {
            "provider": "placeholder",
            "status": "not_generated",
            "path": None,
        }
    else:
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

    with draft_path.open("w", encoding="utf-8") as file:
        json.dump(draft, file, indent=2, sort_keys=True)
        file.write("\n")

    print("Meta Ads Drafter draft package")
    print("------------------------------")
    print(f"brief: {resolved_brief_path}")
    print(f"draft_id: {draft_id}")
    print(f"draft_json: {draft_path}")
    if not no_image:
        print(f"placeholder_image: {image_path}")
    print()
    print("Next review command:")
    print(f"python src/main.py create-creative-from-draft {draft_path}")
    return 0


def run_create_creative_from_draft(
    config: AppConfig,
    *,
    draft_path: Path,
    dry_run: bool,
) -> int:
    from create_creative import run_create_creative
    from meta_api import MetaAPI

    resolved_draft_path = (
        draft_path if draft_path.is_absolute() else config.project_root / draft_path
    )
    draft = _load_json(resolved_draft_path)
    creative = _expect_dict(draft.get("creative"), "creative")
    image = _expect_dict(draft.get("image"), "image")
    image_path_value = image.get("path")

    if not image_path_value:
        raise ValueError("Draft has no generated image path.")

    api = MetaAPI(config)
    return run_create_creative(
        api,
        config,
        name=str(creative["name"]),
        link_url=str(creative["link_url"]),
        message=str(creative["primary_text"]),
        headline=str(creative["headline"]),
        description=str(creative.get("description") or ""),
        call_to_action_type=str(creative.get("cta") or "LEARN_MORE"),
        image_hash=None,
        image_path=Path(str(image_path_value)),
        url_tags=str(creative["url_tags"]) if creative.get("url_tags") else None,
        dry_run=dry_run,
    )


def build_placeholder_draft(brief: dict[str, Any]) -> dict[str, Any]:
    product_name = str(brief.get("product_name") or "Produk")
    offer = str(brief.get("offer") or "Penawaran spesial tersedia")
    audience = str(brief.get("audience") or "calon pelanggan")
    landing_url = str(brief.get("landing_url") or "https://example.com")
    cta = str(brief.get("cta") or "LEARN_MORE").upper()

    pain_points = _string_list(brief.get("pain_points"))
    benefits = _string_list(brief.get("benefits"))

    primary_text = (
        f"{offer}. Cocok untuk {audience}. "
        f"{_join_sentence(benefits) if benefits else 'Dapatkan solusi yang jelas sebelum ambil keputusan.'}"
    )
    headline = shorten(f"{product_name}: {offer}", width=72, placeholder="...")
    description = (
        shorten(_join_sentence(pain_points), width=95, placeholder="...")
        if pain_points
        else "Cek detail penawaran dan konsultasi lebih lanjut."
    )
    image_prompt = (
        f"Create a clean Meta ad image for {product_name}. "
        f"Show the offer: {offer}. Audience: {audience}. "
        "Style: professional, trustworthy, direct-response ad, readable text area."
    )

    draft_id = f"draft_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{_slug(product_name)}"

    return {
        "draft_id": draft_id,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "source": {
            "type": "placeholder_generator",
            "ai_model": None,
            "notes": "Claude/Vertex belum dipanggil. Ini draft rule-based untuk validasi pipeline.",
        },
        "brief": brief,
        "strategy": {
            "angle": f"Lead with clear offer for {audience}",
            "customer_pain": pain_points,
            "benefits": benefits,
        },
        "creative": {
            "name": f"{product_name} - Placeholder Creative",
            "primary_text": primary_text,
            "headline": headline,
            "description": description,
            "cta": cta,
            "link_url": landing_url,
            "url_tags": "utm_source=meta&utm_medium=paid_social&utm_campaign=ai_draft",
            "image_prompt": image_prompt,
        },
        "safety": {
            "status": "DRAFT_ONLY",
            "creates_campaign": False,
            "creates_adset": False,
            "creates_ad": False,
            "publishes_active_ads": False,
            "requires_manual_review": True,
        },
    }


def generate_placeholder_image(
    *,
    image_path: Path,
    headline: str,
    subheadline: str,
    brand: str,
) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise RuntimeError(
            "Pillow belum terinstall. Jalankan: pip install -r requirements.txt"
        ) from exc

    width, height = 1200, 628
    image = Image.new("RGB", (width, height), (246, 248, 250))
    draw = ImageDraw.Draw(image)

    title_font = _font(ImageFont, size=58, bold=True)
    subtitle_font = _font(ImageFont, size=34, bold=False)
    brand_font = _font(ImageFont, size=26, bold=True)

    draw.rectangle((0, 0, width, 90), fill=(18, 96, 142))
    draw.text((70, 28), brand[:46], fill=(255, 255, 255), font=brand_font)

    draw.rectangle((70, 150, 1130, 520), outline=(18, 96, 142), width=6)
    draw.text((110, 205), _wrap_text(headline, 30), fill=(24, 36, 48), font=title_font)
    draw.text((110, 375), _wrap_text(subheadline, 52), fill=(75, 85, 99), font=subtitle_font)

    draw.rectangle((820, 470, 1085, 540), fill=(18, 96, 142))
    draw.text((865, 488), "LEARN MORE", fill=(255, 255, 255), font=brand_font)

    image_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(image_path, quality=92)


def _load_brief(path: Path) -> dict[str, Any]:
    data = _load_json(path)
    if not isinstance(data, dict):
        raise ValueError("Brief JSON must be an object.")
    if not data.get("product_name"):
        raise ValueError("Brief is missing product_name.")
    if not data.get("landing_url"):
        raise ValueError("Brief is missing landing_url.")
    return data


def _load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _expect_dict(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Draft field must be an object: {field_name}")
    return value


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _join_sentence(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + f", dan {items[-1]}"


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.lower()).strip("_")
    return slug[:40] or "creative"


def _wrap_text(value: str, max_chars: int) -> str:
    words = value.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word])
        if len(candidate) > max_chars and current:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines[:3])


def _font(image_font_module: Any, *, size: int, bold: bool) -> Any:
    candidates = (
        ["arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf"]
        if bold
        else ["arial.ttf", "Arial.ttf", "DejaVuSans.ttf"]
    )
    for candidate in candidates:
        try:
            return image_font_module.truetype(candidate, size)
        except OSError:
            continue
    return image_font_module.load_default()
