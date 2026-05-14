from __future__ import annotations

import json
from pathlib import Path

from config import AppConfig, require_ad_account_id, require_page_id
from meta_api import MetaAPI, build_image_ad_creative_payload


def run_create_creative(
    api: MetaAPI,
    config: AppConfig,
    *,
    name: str,
    link_url: str,
    message: str,
    headline: str,
    description: str | None,
    call_to_action_type: str,
    image_hash: str | None,
    image_path: Path | None,
    url_tags: str | None,
    dry_run: bool,
) -> int:
    ad_account_id = require_ad_account_id(config)
    page_id = require_page_id(config)

    if bool(image_hash) == bool(image_path):
        raise ValueError("Use exactly one of --image-hash or --image-path.")

    final_image_hash = image_hash
    upload_log_path = None

    print("Meta Ads Drafter image creative")
    print("--------------------------------")
    print(f"ad_account: {ad_account_id}")
    print(f"page_id: {page_id}")
    print(f"name: {name}")

    if image_path:
        resolved_path = image_path if image_path.is_absolute() else config.project_root / image_path
        print(f"image: {resolved_path}")

        if dry_run:
            final_image_hash = "<uploaded_image_hash>"
        else:
            uploaded = api.upload_image(resolved_path, ad_account_id)
            final_image_hash = uploaded.image_hash
            upload_log_path = uploaded.response_log_path
            print(f"uploaded_image_hash: {final_image_hash}")

    if not final_image_hash:
        raise ValueError("Missing image hash.")

    payload = build_image_ad_creative_payload(
        page_id=page_id,
        name=name,
        image_hash=final_image_hash,
        link_url=link_url,
        message=message,
        headline=headline,
        description=description,
        call_to_action_type=call_to_action_type,
        url_tags=url_tags,
    )

    if dry_run:
        print()
        print("[DRY RUN] No API write was sent.")
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    result = api.create_image_ad_creative(
        ad_account_id=ad_account_id,
        page_id=page_id,
        name=name,
        image_hash=final_image_hash,
        link_url=link_url,
        message=message,
        headline=headline,
        description=description,
        call_to_action_type=call_to_action_type,
        url_tags=url_tags,
    )

    artifact_path = _save_creative_artifact(
        config=config,
        creative_id=result.creative_id,
        payload=payload,
        raw_response=result.raw_response,
    )

    print()
    print("[OK] Image ad creative created.")
    print(f"creative_id: {result.creative_id}")
    print(f"image_hash: {final_image_hash}")
    if upload_log_path:
        print(f"upload_log: {upload_log_path}")
    print(f"creative_response_log: {result.response_log_path}")
    print(f"creative_artifact: {artifact_path}")
    return 0


def _save_creative_artifact(
    *,
    config: AppConfig,
    creative_id: str,
    payload: dict[str, object],
    raw_response: dict[str, object],
) -> Path:
    artifact_path = config.output_dir / f"creative_{creative_id}.json"
    artifact = {
        "creative_id": creative_id,
        "payload": payload,
        "response": raw_response,
        "safety": {
            "creates_campaign": False,
            "creates_adset": False,
            "creates_ad": False,
            "spend_enabled": False,
        },
    }

    with artifact_path.open("w", encoding="utf-8") as file:
        json.dump(artifact, file, indent=2, sort_keys=True)
        file.write("\n")

    return artifact_path
