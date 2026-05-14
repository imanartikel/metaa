from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    """Raised when required local configuration is missing or invalid."""


@dataclass(frozen=True)
class AppConfig:
    project_root: Path
    env_path: Path
    output_dir: Path
    logs_dir: Path
    access_token: str
    ad_account_id: str | None
    page_id: str | None
    app_id: str | None
    app_secret: str | None
    graph_api_version: str
    telegram_bot_token: str | None
    telegram_allowed_user_ids: set[int]
    telegram_verify_ssl: bool
    request_timeout_seconds: int = 30
    max_retries: int = 3
    retry_backoff_seconds: float = 1.0


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _env_value(name: str, *, required: bool = False) -> str | None:
    value = os.getenv(name, "").strip()
    if required and not value:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value or None


def load_config(env_path: str | Path | None = None) -> AppConfig:
    root = project_root()
    resolved_env_path = Path(env_path).resolve() if env_path else root / ".env"

    if resolved_env_path.exists():
        load_dotenv(resolved_env_path)
    else:
        raise ConfigError(
            f"Could not find .env file at {resolved_env_path}. "
            "Create one from .env.example and fill in your Meta credentials."
        )

    logs_dir = root / "output" / "logs"
    output_dir = root / "output"
    logs_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    version = _env_value("META_GRAPH_API_VERSION") or "v25.0"
    if not version.startswith("v"):
        version = f"v{version}"

    return AppConfig(
        project_root=root,
        env_path=resolved_env_path,
        output_dir=output_dir,
        logs_dir=logs_dir,
        access_token=_env_value("META_ACCESS_TOKEN", required=True) or "",
        ad_account_id=_env_value("META_AD_ACCOUNT_ID"),
        page_id=_env_value("META_PAGE_ID"),
        app_id=_env_value("META_APP_ID"),
        app_secret=_env_value("META_APP_SECRET"),
        graph_api_version=version,
        telegram_bot_token=_env_value("TELEGRAM_BOT_TOKEN"),
        telegram_allowed_user_ids=_parse_int_set(_env_value("TELEGRAM_ALLOWED_USER_IDS")),
        telegram_verify_ssl=_parse_bool(_env_value("TELEGRAM_VERIFY_SSL"), default=True),
    )


def require_ad_account_id(config: AppConfig) -> str:
    if not config.ad_account_id:
        raise ConfigError("Missing META_AD_ACCOUNT_ID. It is required for ad account actions.")
    return config.ad_account_id


def require_page_id(config: AppConfig) -> str:
    if not config.page_id:
        raise ConfigError("Missing META_PAGE_ID. It is required for ad creative creation.")
    return config.page_id


def require_telegram_bot_token(config: AppConfig) -> str:
    if not config.telegram_bot_token:
        raise ConfigError("Missing TELEGRAM_BOT_TOKEN. It is required for Telegram commands.")
    return config.telegram_bot_token


def _parse_int_set(value: str | None) -> set[int]:
    if not value:
        return set()

    user_ids: set[int] = set()
    for raw_item in value.split(","):
        item = raw_item.strip()
        if not item:
            continue
        try:
            user_ids.add(int(item))
        except ValueError as exc:
            raise ConfigError(f"Invalid TELEGRAM_ALLOWED_USER_IDS value: {item}") from exc
    return user_ids


def _parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ConfigError(f"Invalid boolean value: {value}")


def setup_logging(logs_dir: Path, *, verbose: bool = False) -> None:
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_level = logging.DEBUG if verbose else logging.INFO
    log_file = logs_dir / "app.log"

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(log_level)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
