from __future__ import annotations

from typing import Any

from config import AppConfig, require_ad_account_id
from meta_api import MetaAPI


def run_connection_test(api: MetaAPI) -> int:
    print("Meta Ads Drafter connection test")
    print("--------------------------------")

    token_result = api.test_token()
    _print_token_result(token_result)

    me = api.get_me()
    _print_identity(me)

    ad_accounts = api.get_ad_accounts()
    _print_collection("Ad accounts", ad_accounts, label_fields=("name", "id", "account_status"))

    pages = api.get_pages()
    _print_collection("Pages", pages, label_fields=("name", "id", "category"))

    print()
    print("[OK] Connection test completed.")
    print(f"API responses saved in: {api.config.logs_dir}")
    return 0


def run_whoami(api: MetaAPI) -> int:
    print("Meta Ads Drafter token identity")
    print("-------------------------------")
    me = api.get_me()
    _print_identity(me)
    print(f"response_log: {api.last_response_log_path}")
    return 0


def run_account_check(api: MetaAPI, config: AppConfig) -> int:
    ad_account_id = require_ad_account_id(config)

    print("Meta Ads Drafter ad account check")
    print("----------------------------------")
    print(f"configured_ad_account: {ad_account_id}")

    account = api.get_ad_account(ad_account_id)

    print()
    print("[OK] Configured ad account is reachable.")
    print(f"name: {account.get('name', 'not returned')}")
    print(f"id: {account.get('id', 'not returned')}")
    print(f"account_id: {account.get('account_id', 'not returned')}")
    print(f"account_status: {account.get('account_status', 'not returned')}")
    print(f"currency: {account.get('currency', 'not returned')}")
    print(f"timezone: {account.get('timezone_name', 'not returned')}")
    print(f"response_log: {api.last_response_log_path}")
    return 0


def _print_identity(me: dict[str, Any]) -> None:
    print()
    print("Token identity")
    print(f"  name: {me.get('name', 'not returned')}")
    print(f"  id: {me.get('id', 'not returned')}")


def _print_token_result(token_result: dict[str, Any]) -> None:
    print()
    print("Token")
    data = token_result.get("data")

    if isinstance(data, dict):
        is_valid = data.get("is_valid")
        app_id = data.get("app_id")
        expires_at = data.get("expires_at")
        scopes = data.get("scopes") or []
        print(f"  status: {'valid' if is_valid else 'invalid/unknown'}")
        print(f"  app_id: {app_id or 'not returned'}")
        print(f"  expires_at: {expires_at or 'not returned'}")
        print(f"  scopes: {len(scopes)} scope(s)")
        if scopes:
            print(f"  scope_list: {', '.join(sorted(str(scope) for scope in scopes))}")
        return

    user_id = token_result.get("id")
    name = token_result.get("name")
    print("  status: reachable via /me")
    print(f"  user: {name or 'not returned'} ({user_id or 'no id'})")


def _print_collection(
    title: str,
    response: dict[str, Any],
    *,
    label_fields: tuple[str, ...],
) -> None:
    print()
    print(title)
    records = response.get("data", [])
    if not isinstance(records, list) or not records:
        print("  none returned")
        return

    print(f"  count: {len(records)}")
    for index, record in enumerate(records[:10], start=1):
        if not isinstance(record, dict):
            print(f"  {index}. {record}")
            continue

        values = [str(record.get(field, "n/a")) for field in label_fields]
        print(f"  {index}. " + " | ".join(values))

    if len(records) > 10:
        print(f"  ... {len(records) - 10} more not shown")
