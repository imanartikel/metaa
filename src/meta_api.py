from __future__ import annotations

import json
import logging
import mimetypes
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import urljoin

import requests

from config import AppConfig


logger = logging.getLogger(__name__)

GRAPH_BASE_URL = "https://graph.facebook.com/"
DEFAULT_CREATION_STATUS = "PAUSED"
DEFAULT_JAVA_BALI_REGION_KEYS = ("1664", "4143", "1685", "1666", "1669", "1667", "1662")
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
SENSITIVE_KEYS = {
    "access_token",
    "app_secret",
    "client_secret",
    "token",
    "input_token",
    "page_access_token",
}


class MetaAPIError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_code: int | None = None,
        error_subcode: int | None = None,
        error_user_title: str | None = None,
        error_user_msg: str | None = None,
        response_log_path: Path | None = None,
        raw_error: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.error_subcode = error_subcode
        self.error_user_title = error_user_title
        self.error_user_msg = error_user_msg
        self.response_log_path = response_log_path
        self.raw_error = raw_error


@dataclass(frozen=True)
class UploadedImage:
    image_hash: str
    raw_response: dict[str, Any]
    response_log_path: Path | None


@dataclass(frozen=True)
class AdCreative:
    creative_id: str
    raw_response: dict[str, Any]
    response_log_path: Path | None


@dataclass(frozen=True)
class PausedDraftAd:
    campaign_id: str
    adset_id: str
    ad_id: str
    raw_responses: dict[str, dict[str, Any]]
    response_log_paths: dict[str, Path | None]


def require_paused_status(status: str | None = None) -> str:
    """Future creation helper: all campaign/adset/ad creation must start PAUSED."""
    if status is None:
        return DEFAULT_CREATION_STATUS

    normalized = status.upper()
    if normalized != DEFAULT_CREATION_STATUS:
        raise ValueError("This app never creates ACTIVE ads. Use status=PAUSED.")
    return normalized


class MetaAPI:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.session = requests.Session()
        self.last_response_log_path: Path | None = None

    def test_token(self) -> dict[str, Any]:
        if self.config.app_id and self.config.app_secret:
            logger.info("Validating access token with /debug_token")
            app_access_token = f"{self.config.app_id}|{self.config.app_secret}"
            return self._request(
                "GET",
                "debug_token",
                params={
                    "input_token": self.config.access_token,
                    "access_token": app_access_token,
                },
                include_default_access_token=False,
            )

        logger.warning(
            "META_APP_ID or META_APP_SECRET is missing; falling back to /me validation"
        )
        return self._request("GET", "me", params={"fields": "id,name"})

    def get_me(self) -> dict[str, Any]:
        logger.info("Reading token identity with /me")
        return self._request("GET", "me", params={"fields": "id,name"})

    def get_ad_accounts(self) -> dict[str, Any]:
        logger.info("Reading ad accounts visible to the token")
        return self._request(
            "GET",
            "me/adaccounts",
            params={
                "fields": "id,account_id,name,account_status,currency,timezone_name,business",
                "limit": "100",
            },
        )

    def get_ad_account(self, ad_account_id: str) -> dict[str, Any]:
        account_path = self._ad_account_path(ad_account_id)
        logger.info("Reading configured ad account %s", account_path)
        return self._request(
            "GET",
            account_path,
            params={
                "fields": (
                    "id,account_id,name,account_status,currency,timezone_name,"
                    "business,disable_reason,amount_spent,balance"
                ),
            },
        )

    def get_pages(self) -> dict[str, Any]:
        logger.info("Reading pages visible to the token")
        return self._request(
            "GET",
            "me/accounts",
            params={
                "fields": "id,name,category,tasks",
                "limit": "100",
            },
        )

    def upload_image(self, image_path: Path, ad_account_id: str) -> UploadedImage:
        resolved_path = image_path.resolve()
        if not resolved_path.exists() or not resolved_path.is_file():
            raise FileNotFoundError(f"Image file not found: {resolved_path}")

        mime_type = mimetypes.guess_type(resolved_path.name)[0] or "application/octet-stream"
        account_path = self._ad_account_path(ad_account_id)
        logger.info("Uploading image %s to %s/adimages", resolved_path.name, account_path)

        with resolved_path.open("rb") as image_file:
            files = {
                "filename": (
                    resolved_path.name,
                    image_file,
                    mime_type,
                )
            }
            response = self._request(
                "POST",
                f"{account_path}/adimages",
                data={"access_token": self.config.access_token},
                files=files,
                include_default_access_token=False,
            )

        image_hash = self._extract_image_hash(response)
        return UploadedImage(
            image_hash=image_hash,
            raw_response=response,
            response_log_path=self.last_response_log_path,
        )

    def create_image_ad_creative(
        self,
        *,
        ad_account_id: str,
        page_id: str,
        name: str,
        image_hash: str,
        link_url: str,
        message: str,
        headline: str,
        description: str | None = None,
        call_to_action_type: str = "LEARN_MORE",
        url_tags: str | None = None,
    ) -> AdCreative:
        account_path = self._ad_account_path(ad_account_id)
        payload = build_image_ad_creative_payload(
            page_id=page_id,
            name=name,
            image_hash=image_hash,
            link_url=link_url,
            message=message,
            headline=headline,
            description=description,
            call_to_action_type=call_to_action_type,
            url_tags=url_tags,
        )

        logger.info("Creating image ad creative name=%s account=%s", name, account_path)
        response = self._request(
            "POST",
            f"{account_path}/adcreatives",
            data={
                "access_token": self.config.access_token,
                "name": payload["name"],
                "object_story_spec": json.dumps(payload["object_story_spec"]),
                **({"url_tags": payload["url_tags"]} if payload.get("url_tags") else {}),
            },
            include_default_access_token=False,
        )

        creative_id = response.get("id")
        if not creative_id:
            raise MetaAPIError(
                "Ad creative creation succeeded but no creative id was found in the response.",
                response_log_path=self.last_response_log_path,
            )

        return AdCreative(
            creative_id=str(creative_id),
            raw_response=response,
            response_log_path=self.last_response_log_path,
        )

    def create_paused_campaign(
        self,
        *,
        ad_account_id: str,
        name: str,
        objective: str | None = None,
    ) -> tuple[str, dict[str, Any], Path | None]:
        account_path = self._ad_account_path(ad_account_id)
        status = require_paused_status()
        resolved_objective = objective or self.config.meta_campaign_objective
        logger.info("Creating PAUSED campaign name=%s account=%s", name, account_path)
        response = self._request(
            "POST",
            f"{account_path}/campaigns",
            data={
                "access_token": self.config.access_token,
                "name": name,
                "objective": resolved_objective,
                "status": status,
                "special_ad_categories": json.dumps([]),
                "is_adset_budget_sharing_enabled": "false",
            },
            include_default_access_token=False,
        )
        campaign_id = _required_response_id(response, "campaign")
        return campaign_id, response, self.last_response_log_path

    def create_paused_adset(
        self,
        *,
        ad_account_id: str,
        campaign_id: str,
        name: str,
        daily_budget: int,
        country: str = "ID",
        region_keys: list[str] | None = None,
        age_min: int = 18,
        age_max: int = 65,
        genders: list[int] | None = None,
        optimization_goal: str = "LINK_CLICKS",
        billing_event: str = "IMPRESSIONS",
        bid_strategy: str = "LOWEST_COST_WITHOUT_CAP",
        promoted_object: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any], Path | None]:
        account_path = self._ad_account_path(ad_account_id)
        status = require_paused_status()
        geo_locations: dict[str, Any]
        if region_keys:
            geo_locations = {
                "regions": [{"key": str(key)} for key in region_keys],
                "location_types": ["home"],
            }
        else:
            geo_locations = {"countries": [country.upper()]}

        targeting = {
            "geo_locations": geo_locations,
            "age_min": age_min,
            "age_max": age_max,
            "targeting_automation": {"advantage_audience": 0},
        }
        if genders:
            targeting["genders"] = genders

        logger.info("Creating PAUSED ad set name=%s campaign=%s", name, campaign_id)
        
        request_data = {
            "access_token": self.config.access_token,
            "name": name,
            "campaign_id": campaign_id,
            "daily_budget": str(daily_budget),
            "optimization_goal": optimization_goal,
            "targeting": json.dumps(targeting),
            "status": status,
        }
        
        if promoted_object:
            request_data["promoted_object"] = json.dumps(promoted_object)
        else:
            request_data["destination_type"] = "WEBSITE"

        response = self._request(
            "POST",
            f"{account_path}/adsets",
            data=request_data,
            include_default_access_token=False,
        )
        adset_id = _required_response_id(response, "ad set")
        return adset_id, response, self.last_response_log_path

    def create_paused_ad(
        self,
        *,
        ad_account_id: str,
        adset_id: str,
        creative_id: str,
        name: str,
    ) -> tuple[str, dict[str, Any], Path | None]:
        account_path = self._ad_account_path(ad_account_id)
        status = require_paused_status()
        logger.info("Creating PAUSED ad name=%s adset=%s creative=%s", name, adset_id, creative_id)
        response = self._request(
            "POST",
            f"{account_path}/ads",
            data={
                "access_token": self.config.access_token,
                "name": name,
                "adset_id": adset_id,
                "creative": json.dumps({"creative_id": creative_id}),
                "status": status,
            },
            include_default_access_token=False,
        )
        ad_id = _required_response_id(response, "ad")
        return ad_id, response, self.last_response_log_path

    def create_paused_draft_ad(
        self,
        *,
        ad_account_id: str,
        creative_id: str,
        campaign_name: str,
        adset_name: str,
        ad_name: str,
        daily_budget: int,
        country: str = "ID",
        region_keys: list[str] | None = None,
        age_min: int = 18,
        age_max: int = 65,
        genders: list[int] | None = None,
        optimization_goal: str = "LINK_CLICKS",
        promoted_object: dict[str, Any] | None = None,
    ) -> PausedDraftAd:
        campaign_id, campaign_response, campaign_log = self.create_paused_campaign(
            ad_account_id=ad_account_id,
            name=campaign_name,
        )
        adset_id, adset_response, adset_log = self.create_paused_adset(
            ad_account_id=ad_account_id,
            campaign_id=campaign_id,
            name=adset_name,
            daily_budget=daily_budget,
            country=country,
            region_keys=region_keys,
            age_min=age_min,
            age_max=age_max,
            genders=genders,
            optimization_goal=optimization_goal,
            promoted_object=promoted_object,
        )
        ad_id, ad_response, ad_log = self.create_paused_ad(
            ad_account_id=ad_account_id,
            adset_id=adset_id,
            creative_id=creative_id,
            name=ad_name,
        )

        return PausedDraftAd(
            campaign_id=campaign_id,
            adset_id=adset_id,
            ad_id=ad_id,
            raw_responses={
                "campaign": campaign_response,
                "adset": adset_response,
                "ad": ad_response,
            },
            response_log_paths={
                "campaign": campaign_log,
                "adset": adset_log,
                "ad": ad_log,
            },
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, tuple[str, BinaryIO, str]] | None = None,
        include_default_access_token: bool = True,
    ) -> dict[str, Any]:
        method = method.upper()
        request_params = dict(params or {})
        request_data = dict(data or {})

        if include_default_access_token:
            request_params.setdefault("access_token", self.config.access_token)

        url = self._url(path)
        last_exception: Exception | None = None

        for attempt in range(1, self.config.max_retries + 1):
            try:
                self._rewind_files(files)
                logger.debug(
                    "Meta API request attempt=%s method=%s url=%s params=%s data=%s",
                    attempt,
                    method,
                    url,
                    redact(request_params),
                    redact(request_data),
                )
                response = self.session.request(
                    method,
                    url,
                    params=request_params if request_params else None,
                    data=request_data if request_data else None,
                    files=files,
                    timeout=self.config.request_timeout_seconds,
                )

                response_body = self._parse_response_body(response)
                self.last_response_log_path = self._save_response_log(
                    method=method,
                    path=path,
                    status_code=response.status_code,
                    request_params=request_params,
                    request_data=request_data,
                    response_body=response_body,
                )

                if response.ok:
                    logger.info(
                        "Meta API request succeeded method=%s path=%s status=%s log=%s",
                        method,
                        path,
                        response.status_code,
                        self.last_response_log_path,
                    )
                    return response_body

                if response.status_code in RETRYABLE_STATUS_CODES and attempt < self.config.max_retries:
                    self._sleep_before_retry(attempt, response.status_code)
                    continue

                raise self._error_from_response(response, response_body)

            except (requests.ConnectionError, requests.Timeout) as exc:
                last_exception = exc
                logger.warning(
                    "Meta API network error attempt=%s/%s: %s",
                    attempt,
                    self.config.max_retries,
                    exc,
                )
                if attempt < self.config.max_retries:
                    self._sleep_before_retry(attempt, None)
                    continue
                break

        raise MetaAPIError(f"Meta API request failed after retries: {last_exception}")

    def _url(self, path: str) -> str:
        clean_path = path.lstrip("/")
        versioned_path = f"{self.config.graph_api_version}/{clean_path}"
        return urljoin(GRAPH_BASE_URL, versioned_path)

    def _ad_account_path(self, ad_account_id: str) -> str:
        normalized = ad_account_id.strip()
        if normalized.startswith("act_"):
            return normalized
        return f"act_{normalized}"

    def _extract_image_hash(self, response: dict[str, Any]) -> str:
        images = response.get("images")
        if isinstance(images, dict):
            for image_data in images.values():
                if isinstance(image_data, dict) and image_data.get("hash"):
                    return str(image_data["hash"])

        raise MetaAPIError(
            "Image upload succeeded but no image hash was found in the response.",
            response_log_path=self.last_response_log_path,
        )

    def _parse_response_body(self, response: requests.Response) -> dict[str, Any]:
        try:
            parsed = response.json()
        except ValueError:
            parsed = {"raw_text": response.text}

        if isinstance(parsed, dict):
            return parsed
        return {"data": parsed}

    def _save_response_log(
        self,
        *,
        method: str,
        path: str,
        status_code: int,
        request_params: dict[str, Any],
        request_data: dict[str, Any],
        response_body: dict[str, Any],
    ) -> Path:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        safe_path = re.sub(r"[^a-zA-Z0-9_.-]+", "_", path.strip("/"))[:80]
        filename = f"{timestamp}_{method}_{status_code}_{safe_path}.json"
        log_path = self.config.logs_dir / filename

        payload = {
            "timestamp_utc": timestamp,
            "request": {
                "method": method,
                "path": path,
                "api_version": self.config.graph_api_version,
                "params": redact(request_params),
                "data": redact(request_data),
            },
            "response": {
                "status_code": status_code,
                "body": redact(response_body),
            },
        }

        with log_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2, sort_keys=True)
            file.write("\n")

        return log_path

    def _error_from_response(
        self,
        response: requests.Response,
        response_body: dict[str, Any],
    ) -> MetaAPIError:
        error = response_body.get("error", {})
        if not isinstance(error, dict):
            error = {}

        message = error.get("message") or response.reason or "Meta API request failed"
        error_code = _safe_int(error.get("code"))
        error_subcode = _safe_int(error.get("error_subcode"))
        error_user_title = _safe_str(error.get("error_user_title"))
        error_user_msg = _safe_str(error.get("error_user_msg"))

        logger.error(
            "Meta API error status=%s code=%s subcode=%s message=%s user_title=%s log=%s",
            response.status_code,
            error_code,
            error_subcode,
            message,
            error_user_title,
            self.last_response_log_path,
        )
        return MetaAPIError(
            str(message),
            status_code=response.status_code,
            error_code=error_code,
            error_subcode=error_subcode,
            error_user_title=error_user_title,
            error_user_msg=error_user_msg,
            response_log_path=self.last_response_log_path,
            raw_error=error,
        )

    def _sleep_before_retry(self, attempt: int, status_code: int | None) -> None:
        delay = self.config.retry_backoff_seconds * (2 ** (attempt - 1))
        logger.warning(
            "Retrying Meta API request after %.1fs due to %s",
            delay,
            f"HTTP {status_code}" if status_code else "network error",
        )
        time.sleep(delay)

    def _rewind_files(
        self,
        files: dict[str, tuple[str, BinaryIO, str]] | None,
    ) -> None:
        if not files:
            return

        for file_tuple in files.values():
            file_tuple[1].seek(0)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if key.lower() in SENSITIVE_KEYS:
                redacted[key] = "***REDACTED***"
            else:
                redacted[key] = redact(item)
        return redacted

    if isinstance(value, list):
        return [redact(item) for item in value]

    return value


def build_image_ad_creative_payload(
    *,
    page_id: str,
    name: str,
    image_hash: str,
    link_url: str,
    message: str,
    headline: str,
    description: str | None = None,
    call_to_action_type: str = "LEARN_MORE",
    url_tags: str | None = None,
) -> dict[str, Any]:
    link_data: dict[str, Any] = {
        "image_hash": image_hash,
        "link": link_url,
        "message": message,
        "name": headline,
        "call_to_action": {
            "type": call_to_action_type.upper(),
            "value": {"link": link_url},
        },
    }

    if description:
        link_data["description"] = description

    payload: dict[str, Any] = {
        "name": name,
        "object_story_spec": {
            "page_id": page_id,
            "link_data": link_data,
        },
    }

    if url_tags:
        payload["url_tags"] = url_tags

    return payload


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _required_response_id(response: dict[str, Any], object_name: str) -> str:
    object_id = response.get("id")
    if not object_id:
        raise MetaAPIError(
            f"{object_name.title()} creation succeeded but no id was found in the response."
        )
    return str(object_id)
