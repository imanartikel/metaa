from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from config import AppConfig, require_ad_account_id
from meta_api import DEFAULT_JAVA_BALI_REGION_KEYS, MetaAPI


def run_create_paused_draft(
    api: MetaAPI,
    config: AppConfig,
    *,
    creative_id: str,
    campaign_name: str,
    adset_name: str,
    ad_name: str,
    daily_budget: int,
    country: str,
    age_min: int,
    age_max: int,
    gender: str,
    dry_run: bool,
) -> int:
    ad_account_id = require_ad_account_id(config)
    if daily_budget <= 0:
        raise ValueError("daily_budget must be greater than 0.")
    if age_min < 13 or age_max > 65 or age_min > age_max:
        raise ValueError("age must be between 13-65 and age_min <= age_max.")
    gender_values = gender_to_meta_values(gender)

    print("Meta Ads Drafter PAUSED draft ad")
    print("--------------------------------")
    print(f"ad_account: {ad_account_id}")
    print(f"creative_id: {creative_id}")
    print(f"campaign_name: {campaign_name}")
    print(f"adset_name: {adset_name}")
    print(f"ad_name: {ad_name}")
    print(f"daily_budget: {daily_budget}")
    print(f"country: {country.upper()}")
    print(f"age: {age_min}-{age_max}")
    print(f"gender: {gender}")
    print("regions: Java + Bali default")
    print("status: PAUSED for campaign, ad set, and ad")

    plan = {
        "campaign": {
            "name": campaign_name,
            "objective": config.meta_campaign_objective,
            "status": "PAUSED",
            "special_ad_categories": [],
            "is_adset_budget_sharing_enabled": False,
        },
        "adset": {
            "name": adset_name,
            "daily_budget": daily_budget,
            "billing_event": "IMPRESSIONS",
            "optimization_goal": "LINK_CLICKS",
            "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
            "destination_type": "WEBSITE",
            "targeting": {
                "geo_locations": {
                    "regions": [{"key": key} for key in DEFAULT_JAVA_BALI_REGION_KEYS],
                    "location_types": ["home"],
                },
                "age_min": age_min,
                "age_max": age_max,
                "targeting_automation": {"advantage_audience": 0},
            },
            "status": "PAUSED",
        },
        "ad": {
            "name": ad_name,
            "creative": {"creative_id": creative_id},
            "status": "PAUSED",
        },
        "safety": {
            "creates_active_ads": False,
            "publishes_active_ads": False,
            "requires_manual_review": True,
        },
    }
    if gender_values:
        plan["adset"]["targeting"]["genders"] = gender_values  # type: ignore[index]

    if dry_run:
        print()
        print("[DRY RUN] No API write was sent.")
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0

    result, artifact_path = create_paused_draft_ad_from_creative(
        api,
        config,
        creative_id=creative_id,
        campaign_name=campaign_name,
        adset_name=adset_name,
        ad_name=ad_name,
        daily_budget=daily_budget,
        country=country,
        age_min=age_min,
        age_max=age_max,
        gender=gender,
        region_keys=list(DEFAULT_JAVA_BALI_REGION_KEYS),
        plan=plan,
    )

    print()
    print("[OK] PAUSED draft ad hierarchy created.")
    print(f"campaign_id: {result.campaign_id}")
    print(f"adset_id: {result.adset_id}")
    print(f"ad_id: {result.ad_id}")
    print(f"campaign_log: {result.response_log_paths['campaign']}")
    print(f"adset_log: {result.response_log_paths['adset']}")
    print(f"ad_log: {result.response_log_paths['ad']}")
    print(f"artifact: {artifact_path}")
    print()
    print("Open Meta Ads Manager and filter by the campaign name above.")
    return 0


def create_paused_draft_ad_from_creative(
    api: MetaAPI,
    config: AppConfig,
    *,
    creative_id: str,
    campaign_name: str,
    adset_name: str,
    ad_name: str,
    daily_budget: int,
    country: str,
    age_min: int = 25,
    age_max: int = 65,
    gender: str = "all",
    region_keys: list[str] | None = None,
    plan: dict[str, object] | None = None,
):
    ad_account_id = require_ad_account_id(config)
    genders = gender_to_meta_values(gender)
    result = api.create_paused_draft_ad(
        ad_account_id=ad_account_id,
        creative_id=creative_id,
        campaign_name=campaign_name,
        adset_name=adset_name,
        ad_name=ad_name,
        daily_budget=daily_budget,
        country=country,
        region_keys=region_keys,
        age_min=age_min,
        age_max=age_max,
        genders=genders,
    )

    if plan is None:
        plan = {
            "campaign": {
                "name": campaign_name,
                "objective": config.meta_campaign_objective,
                "status": "PAUSED",
            },
            "adset": {
                "name": adset_name,
                "daily_budget": daily_budget,
                "country": country.upper(),
                "region_keys": region_keys or [],
                "age_min": age_min,
                "age_max": age_max,
                "gender": gender,
                "status": "PAUSED",
            },
            "ad": {
                "name": ad_name,
                "creative": {"creative_id": creative_id},
                "status": "PAUSED",
            },
        }

    artifact_path = _save_paused_draft_artifact(
        config=config,
        plan=plan,
        campaign_id=result.campaign_id,
        adset_id=result.adset_id,
        ad_id=result.ad_id,
        raw_responses=result.raw_responses,
        response_log_paths=result.response_log_paths,
    )
    return result, artifact_path


def gender_to_meta_values(gender: str) -> list[int] | None:
    normalized = gender.strip().lower()
    if normalized in {"all", "semua", "any", "bebas", ""}:
        return None
    if normalized in {"male", "pria", "cowok", "laki", "laki-laki", "men"}:
        return [1]
    if normalized in {"female", "wanita", "cewek", "perempuan", "women"}:
        return [2]
    raise ValueError("gender harus salah satu: all, pria, wanita.")


def _save_paused_draft_artifact(
    *,
    config: AppConfig,
    plan: dict[str, object],
    campaign_id: str,
    adset_id: str,
    ad_id: str,
    raw_responses: dict[str, dict[str, object]],
    response_log_paths: dict[str, Path | None],
) -> Path:
    artifact_dir = config.output_dir / "draft_ads"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    artifact_path = artifact_dir / f"paused_draft_ad_{timestamp}_{ad_id}.json"

    artifact = {
        "created_at_utc": timestamp,
        "campaign_id": campaign_id,
        "adset_id": adset_id,
        "ad_id": ad_id,
        "plan": plan,
        "responses": raw_responses,
        "response_logs": {
            key: str(value) if value else None
            for key, value in response_log_paths.items()
        },
        "safety": {
            "campaign_status": "PAUSED",
            "adset_status": "PAUSED",
            "ad_status": "PAUSED",
            "spend_enabled": False,
            "manual_publish_required": True,
        },
    }

    with artifact_path.open("w", encoding="utf-8") as file:
        json.dump(artifact, file, indent=2, sort_keys=True)
        file.write("\n")

    return artifact_path
