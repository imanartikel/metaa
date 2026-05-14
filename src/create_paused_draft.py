from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from config import AppConfig, require_ad_account_id
from meta_api import MetaAPI


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
    dry_run: bool,
) -> int:
    ad_account_id = require_ad_account_id(config)
    if daily_budget <= 0:
        raise ValueError("daily_budget must be greater than 0.")

    print("Meta Ads Drafter PAUSED draft ad")
    print("--------------------------------")
    print(f"ad_account: {ad_account_id}")
    print(f"creative_id: {creative_id}")
    print(f"campaign_name: {campaign_name}")
    print(f"adset_name: {adset_name}")
    print(f"ad_name: {ad_name}")
    print(f"daily_budget: {daily_budget}")
    print(f"country: {country.upper()}")
    print("status: PAUSED for campaign, ad set, and ad")

    plan = {
        "campaign": {
            "name": campaign_name,
            "objective": "OUTCOME_TRAFFIC",
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
                "geo_locations": {"countries": [country.upper()]},
                "age_min": 18,
                "age_max": 65,
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
    plan: dict[str, object] | None = None,
):
    ad_account_id = require_ad_account_id(config)
    result = api.create_paused_draft_ad(
        ad_account_id=ad_account_id,
        creative_id=creative_id,
        campaign_name=campaign_name,
        adset_name=adset_name,
        ad_name=ad_name,
        daily_budget=daily_budget,
        country=country,
    )

    if plan is None:
        plan = {
            "campaign": {
                "name": campaign_name,
                "objective": "OUTCOME_TRAFFIC",
                "status": "PAUSED",
            },
            "adset": {
                "name": adset_name,
                "daily_budget": daily_budget,
                "country": country.upper(),
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
