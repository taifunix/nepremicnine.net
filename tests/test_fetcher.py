from pathlib import Path

from nepremicnine_bot.fetcher import (
    BrowserSiteFetcher,
    SiteFetcher,
    build_fetcher,
    load_cookies_from_file,
    load_storage_state_from_file,
    parse_proxy_config,
)


def test_parse_proxy_config_splits_server_and_credentials():
    proxy = parse_proxy_config("user:pass@example.com:1234")

    assert proxy["server"] == "http://example.com:1234"
    assert proxy["username"] == "user"
    assert proxy["password"] == "pass"


def test_parse_proxy_config_supports_scheme_prefixed_proxy_urls():
    proxy = parse_proxy_config("http://user:pass@example.com:1234")

    assert proxy["server"] == "http://example.com:1234"
    assert proxy["username"] == "user"
    assert proxy["password"] == "pass"


def test_load_cookies_from_file_supports_wrapped_storage_state(tmp_path: Path):
    cookies_file = tmp_path / "cookies.json"
    cookies_file.write_text(
        '{"cookies": [{"name": "cf_clearance", "value": "token", "domain": ".nepremicnine.net", "path": "/"}]}',
        encoding="utf-8",
    )

    cookies = load_cookies_from_file(cookies_file)

    assert len(cookies) == 1
    assert cookies[0]["name"] == "cf_clearance"


def test_load_cookies_from_file_normalizes_chrome_samesite_values(tmp_path: Path):
    cookies_file = tmp_path / "cookies.json"
    cookies_file.write_text(
        '[{"name": "cf_clearance", "value": "token", "domain": ".nepremicnine.net", "path": "/", "sameSite": "no_restriction", "hostOnly": false, "session": false, "storeId": "0"}]',
        encoding="utf-8",
    )

    cookies = load_cookies_from_file(cookies_file)

    assert cookies[0]["sameSite"] == "None"
    assert "hostOnly" not in cookies[0]
    assert "session" not in cookies[0]
    assert "storeId" not in cookies[0]


def test_load_cookies_from_file_removes_null_samesite(tmp_path: Path):
    cookies_file = tmp_path / "cookies.json"
    cookies_file.write_text(
        '[{"name": "cf_clearance", "value": "token", "domain": ".nepremicnine.net", "path": "/", "sameSite": null}]',
        encoding="utf-8",
    )

    cookies = load_cookies_from_file(cookies_file)

    assert "sameSite" not in cookies[0]


def test_load_storage_state_from_file_normalizes_cookies_and_preserves_origins(tmp_path: Path):
    state_file = tmp_path / "storage-state.json"
    state_file.write_text(
        '{"cookies": [{"name": "cf_clearance", "value": "token", "domain": ".nepremicnine.net", "path": "/", "sameSite": null}], "origins": [{"origin": "https://www.nepremicnine.net", "localStorage": [{"name": "a", "value": "b"}]}]}',
        encoding="utf-8",
    )

    state = load_storage_state_from_file(state_file)

    assert "sameSite" not in state["cookies"][0]
    assert state["origins"][0]["origin"] == "https://www.nepremicnine.net"


def test_build_fetcher_returns_http_fetcher_for_http_mode():
    fetcher = build_fetcher("http")

    assert isinstance(fetcher, SiteFetcher)


def test_build_fetcher_returns_browser_fetcher_for_browser_mode():
    fetcher = build_fetcher(
        "browser",
        browser_user_data_dir="./data/browser",
        browser_headless=False,
        browser_channel="chrome",
        browser_proxy="user:pass@example.com:1234",
        browser_cookies_path="./data/session-cookies.json",
        browser_storage_state_path="./data/storage-state.json",
    )

    assert isinstance(fetcher, BrowserSiteFetcher)
    assert fetcher.user_data_dir == "./data/browser"
    assert fetcher.headless is False
    assert fetcher.channel == "chrome"
    assert fetcher.proxy["server"] == "http://example.com:1234"
    assert fetcher.cookies_path == "./data/session-cookies.json"
    assert fetcher.storage_state_path == "./data/storage-state.json"


def test_build_fetcher_uses_dedicated_proxy_runtime_artifacts_for_default_paths():
    fetcher = build_fetcher(
        "browser",
        browser_proxy="user:pass@example.com:1234",
    )

    assert fetcher.user_data_dir == "./data/browser-profile-proxy"
    assert fetcher.cookies_path == "./data/session-cookies-proxy.json"
    assert fetcher.storage_state_path == "./data/storage-state-proxy.json"


def test_build_fetcher_keeps_custom_runtime_artifacts_in_proxy_mode():
    fetcher = build_fetcher(
        "browser",
        browser_proxy="user:pass@example.com:1234",
        browser_user_data_dir="./data/custom-browser",
        browser_cookies_path="./data/custom-cookies.json",
        browser_storage_state_path="./data/custom-state.json",
    )

    assert fetcher.user_data_dir == "./data/custom-browser"
    assert fetcher.cookies_path == "./data/custom-cookies.json"
    assert fetcher.storage_state_path == "./data/custom-state.json"
