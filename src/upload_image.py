from __future__ import annotations

from pathlib import Path

from config import AppConfig, require_ad_account_id
from meta_api import MetaAPI


def run_upload_image(api: MetaAPI, config: AppConfig, image_path: Path) -> int:
    ad_account_id = require_ad_account_id(config)
    resolved_path = image_path if image_path.is_absolute() else config.project_root / image_path

    print("Meta Ads Drafter image upload")
    print("-----------------------------")
    print(f"image: {resolved_path}")
    print(f"ad_account: {ad_account_id}")
    print("status: uploading")

    result = api.upload_image(resolved_path, ad_account_id)

    print()
    print("[OK] Image uploaded.")
    print(f"image_hash: {result.image_hash}")
    if result.response_log_path:
        print(f"response_log: {result.response_log_path}")
    return 0
