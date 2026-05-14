from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from config import ConfigError, load_config, setup_logging
from create_creative import run_create_creative
from create_paused_draft import run_create_paused_draft
from draft_package import run_create_creative_from_draft, run_draft_package
from meta_api import MetaAPI, MetaAPIError
from telegram_bot import run_telegram_bot, run_telegram_updates, run_telegram_whoami
from test_connection import run_account_check, run_connection_test, run_whoami
from upload_image import run_upload_image


logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="meta-ad-drafter",
        description="Local CLI foundation for safe Meta Ads drafting.",
    )
    parser.add_argument(
        "--env",
        default=None,
        help="Path to .env file. Defaults to the project .env.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print debug logs to the terminal.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "test",
        help="Validate token and list ad accounts/pages visible to the token.",
    )

    subparsers.add_parser(
        "check-account",
        help="Read the configured META_AD_ACCOUNT_ID directly.",
    )

    subparsers.add_parser(
        "whoami",
        help="Show the Meta user/system-user identity behind the access token.",
    )

    upload_parser = subparsers.add_parser(
        "upload-image",
        help="Upload a local image to the configured Meta ad account.",
    )
    upload_parser.add_argument("image_path", help="Path to a JPG/PNG image file.")

    creative_parser = subparsers.add_parser(
        "create-creative",
        help="Create a Page link image ad creative. This does not create an ad.",
    )
    image_source = creative_parser.add_mutually_exclusive_group(required=True)
    image_source.add_argument(
        "--image-hash",
        help="Existing image_hash from Meta ad image upload.",
    )
    image_source.add_argument(
        "--image-path",
        help="Local image path. The app uploads it first, then creates the creative.",
    )
    creative_parser.add_argument("--name", required=True, help="Internal creative name.")
    creative_parser.add_argument("--link-url", required=True, help="Destination URL.")
    creative_parser.add_argument("--message", required=True, help="Primary text.")
    creative_parser.add_argument("--headline", required=True, help="Creative headline.")
    creative_parser.add_argument("--description", default=None, help="Optional description.")
    creative_parser.add_argument(
        "--cta",
        default="LEARN_MORE",
        help="CTA type, for example LEARN_MORE, SIGN_UP, SHOP_NOW, CONTACT_US.",
    )
    creative_parser.add_argument(
        "--url-tags",
        default=None,
        help="Optional URL tags / UTM string.",
    )
    creative_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print payload only. Does not upload image or create creative.",
    )

    draft_parser = subparsers.add_parser(
        "draft-package",
        help="Generate draft JSON and placeholder image from a brief JSON.",
    )
    draft_parser.add_argument("--brief", required=True, help="Path to brief JSON.")
    draft_parser.add_argument(
        "--no-image",
        action="store_true",
        help="Generate draft JSON only.",
    )
    draft_parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Force placeholder rule-based draft even if Anthropic API key is configured.",
    )

    draft_creative_parser = subparsers.add_parser(
        "create-creative-from-draft",
        help="Upload the draft image and create a Meta ad creative from draft JSON.",
    )
    draft_creative_parser.add_argument("draft_path", help="Path to draft JSON.")
    draft_creative_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print Meta creative payload only. Does not upload or create creative.",
    )

    paused_draft_parser = subparsers.add_parser(
        "create-paused-draft-ad",
        help="Create a PAUSED campaign, ad set, and ad from an existing creative.",
    )
    paused_draft_parser.add_argument("--creative-id", required=True, help="Existing Meta ad creative ID.")
    paused_draft_parser.add_argument(
        "--campaign-name",
        default="AI Draft - Placeholder Campaign",
        help="Campaign name visible in Meta Ads Manager.",
    )
    paused_draft_parser.add_argument(
        "--adset-name",
        default="AI Draft - Placeholder Ad Set",
        help="Ad set name visible in Meta Ads Manager.",
    )
    paused_draft_parser.add_argument(
        "--ad-name",
        default="AI Draft - Placeholder Ad",
        help="Ad name visible in Meta Ads Manager.",
    )
    paused_draft_parser.add_argument(
        "--daily-budget",
        type=int,
        default=50000,
        help="Ad set daily budget in account currency minor/basic units. Default: 50000.",
    )
    paused_draft_parser.add_argument(
        "--country",
        default="ID",
        help="Two-letter country code for placeholder targeting. Default: ID.",
    )
    paused_draft_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned payload only. Does not create anything.",
    )

    subparsers.add_parser(
        "telegram-whoami",
        help="Validate Telegram bot token and show bot identity.",
    )

    subparsers.add_parser(
        "telegram-updates",
        help="Show recent Telegram messages so you can find your user id.",
    )

    subparsers.add_parser(
        "telegram-bot",
        help="Run local Telegram polling bot for draft package creation.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        config = load_config(args.env)
        setup_logging(config.logs_dir, verbose=args.verbose)
        api = MetaAPI(config)

        logger.info("Starting command=%s project_root=%s", args.command, config.project_root)

        if args.command == "test":
            return run_connection_test(api)

        if args.command == "check-account":
            return run_account_check(api, config)

        if args.command == "whoami":
            return run_whoami(api)

        if args.command == "upload-image":
            return run_upload_image(api, config, Path(args.image_path))

        if args.command == "create-creative":
            return run_create_creative(
                api,
                config,
                name=args.name,
                link_url=args.link_url,
                message=args.message,
                headline=args.headline,
                description=args.description,
                call_to_action_type=args.cta,
                image_hash=args.image_hash,
                image_path=Path(args.image_path) if args.image_path else None,
                url_tags=args.url_tags,
                dry_run=args.dry_run,
            )

        if args.command == "draft-package":
            return run_draft_package(
                config,
                brief_path=Path(args.brief),
                no_image=args.no_image,
                use_ai=not args.no_ai,
            )

        if args.command == "create-creative-from-draft":
            return run_create_creative_from_draft(
                config,
                draft_path=Path(args.draft_path),
                dry_run=args.dry_run,
            )

        if args.command == "create-paused-draft-ad":
            return run_create_paused_draft(
                api,
                config,
                creative_id=args.creative_id,
                campaign_name=args.campaign_name,
                adset_name=args.adset_name,
                ad_name=args.ad_name,
                daily_budget=args.daily_budget,
                country=args.country,
                dry_run=args.dry_run,
            )

        if args.command == "telegram-whoami":
            return run_telegram_whoami(config)

        if args.command == "telegram-updates":
            return run_telegram_updates(config)

        if args.command == "telegram-bot":
            return run_telegram_bot(config)

        parser.error(f"Unknown command: {args.command}")
        return 2

    except ConfigError as exc:
        print(f"[CONFIG ERROR] {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"[FILE ERROR] {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"[INPUT ERROR] {exc}", file=sys.stderr)
        return 2
    except MetaAPIError as exc:
        print(f"[META API ERROR] {exc}", file=sys.stderr)
        if exc.status_code:
            print(f"status_code: {exc.status_code}", file=sys.stderr)
        if exc.error_code:
            print(f"error_code: {exc.error_code}", file=sys.stderr)
        if exc.error_subcode:
            print(f"error_subcode: {exc.error_subcode}", file=sys.stderr)
        if exc.error_user_title:
            print(f"error_user_title: {exc.error_user_title}", file=sys.stderr)
        if exc.error_user_msg:
            print(f"error_user_msg: {exc.error_user_msg}", file=sys.stderr)
        if exc.response_log_path:
            print(f"response_log: {exc.response_log_path}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"[RUNTIME ERROR] {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
