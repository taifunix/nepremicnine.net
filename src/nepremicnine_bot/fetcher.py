import json
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx


DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,sl;q=0.8",
}
DEFAULT_BROWSER_USER_DATA_DIR = "./data/browser-profile"
DEFAULT_BROWSER_COOKIES_PATH = "./data/session-cookies.json"
DEFAULT_BROWSER_STORAGE_STATE_PATH = "./data/storage-state.json"

VALID_SAMESITE = {"Strict", "Lax", "None"}
CHROME_SAMESITE_MAP = {
    "strict": "Strict",
    "lax": "Lax",
    "none": "None",
    "no_restriction": "None",
    "unspecified": None,
}
DROP_COOKIE_KEYS = {"hostOnly", "session", "storeId", "id"}
BLOCK_MARKERS = (
    "cloudflare",
    "attention required",
    "verify you are human",
    "just a moment",
)


def parse_proxy_config(proxy_value: str) -> dict[str, str]:
    candidate = proxy_value if "://" in proxy_value else f"http://{proxy_value}"
    parsed = urlsplit(candidate)
    if not parsed.hostname or not parsed.port or parsed.username is None or parsed.password is None:
        raise ValueError("Proxy must be in the format user:pass@host:port or scheme://user:pass@host:port")
    return {
        "server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}",
        "username": parsed.username,
        "password": parsed.password,
    }


def render_proxy_url(proxy_config: dict[str, str]) -> str:
    scheme, host_port = proxy_config["server"].split("://", 1)
    return f"{scheme}://{proxy_config['username']}:{proxy_config['password']}@{host_port}"


def _with_proxy_suffix(path: str) -> str:
    separator = "/" if "/" in path else "\\"
    if separator in path:
        head, tail = path.rsplit(separator, 1)
        prefix = f"{head}{separator}"
    else:
        prefix = ""
        tail = path
    if "." in tail:
        stem, suffix = tail.rsplit(".", 1)
        return f"{prefix}{stem}-proxy.{suffix}"
    return f"{prefix}{tail}-proxy"


def normalize_cookie(cookie: dict) -> dict:
    normalized = {key: value for key, value in cookie.items() if key not in DROP_COOKIE_KEYS}

    same_site = normalized.get("sameSite")
    if "sameSite" in normalized and same_site is None:
        normalized.pop("sameSite")
    elif isinstance(same_site, str):
        mapped = CHROME_SAMESITE_MAP.get(same_site.strip().lower(), same_site)
        if mapped is None:
            normalized.pop("sameSite", None)
        else:
            normalized["sameSite"] = mapped
    elif same_site is not None and same_site not in VALID_SAMESITE:
        normalized.pop("sameSite", None)

    if "expirationDate" in normalized and "expires" not in normalized:
        normalized["expires"] = normalized.pop("expirationDate")

    return normalized


def _read_json_file(path: str | Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json_file(path: str | Path, payload: object) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_cookies_from_file(path: str | Path) -> list[dict]:
    raw = _read_json_file(path)
    if isinstance(raw, dict):
        cookies = raw.get("cookies", [])
    elif isinstance(raw, list):
        cookies = raw
    else:
        raise ValueError("Cookies file must contain a list or a storage-state object with a cookies key")
    if not isinstance(cookies, list):
        raise ValueError("Cookies payload must be a list")
    return [normalize_cookie(cookie) for cookie in cookies]


def load_storage_state_from_file(path: str | Path) -> dict[str, object]:
    raw = _read_json_file(path)
    if not isinstance(raw, dict):
        raise ValueError("Storage state file must contain an object")
    cookies = raw.get("cookies", [])
    origins = raw.get("origins", [])
    if not isinstance(cookies, list):
        raise ValueError("Storage state cookies must be a list")
    if not isinstance(origins, list):
        raise ValueError("Storage state origins must be a list")
    return {
        "cookies": [normalize_cookie(cookie) for cookie in cookies],
        "origins": origins,
    }


class SiteFetcher:
    def __init__(self, timeout: float = 10.0, proxy: str | None = None):
        self.timeout = timeout
        self.proxy = proxy

    def fetch_text(self, url: str) -> str:
        proxy_url = None
        if self.proxy:
            proxy_cfg = parse_proxy_config(self.proxy)
            proxy_url = render_proxy_url(proxy_cfg)
        response = httpx.get(
            url,
            timeout=self.timeout,
            headers=DEFAULT_HEADERS,
            follow_redirects=True,
            proxy=proxy_url,
        )
        response.raise_for_status()
        return response.text


class BrowserSiteFetcher:
    def __init__(
        self,
        user_data_dir: str = DEFAULT_BROWSER_USER_DATA_DIR,
        headless: bool = True,
        channel: str | None = "chrome",
        proxy: dict[str, str] | None = None,
        cookies_path: str = DEFAULT_BROWSER_COOKIES_PATH,
        storage_state_path: str = DEFAULT_BROWSER_STORAGE_STATE_PATH,
        timeout_ms: int = 30000,
    ):
        self.user_data_dir = user_data_dir
        self.headless = headless
        self.channel = channel
        self.proxy = proxy
        self.cookies_path = cookies_path
        self.storage_state_path = storage_state_path
        self.timeout_ms = timeout_ms

    def _open_context(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is required for browser fetch mode. Install it with 'pip install playwright' "
                "and then run 'playwright install chromium'."
            ) from exc
        return sync_playwright()

    def _launch_browser(self, playwright):
        Path(self.user_data_dir).mkdir(parents=True, exist_ok=True)
        launch_kwargs = {
            "headless": self.headless,
            "proxy": self.proxy,
            "user_agent": DEFAULT_HEADERS["User-Agent"],
        }
        if self.channel:
            launch_kwargs["channel"] = self.channel
        return playwright.chromium.launch_persistent_context(
            self.user_data_dir,
            **launch_kwargs,
        )

    def _load_cookies(self, context) -> int:
        if not self.cookies_path:
            return 0
        cookies_file = Path(self.cookies_path)
        if not cookies_file.exists():
            return 0
        cookies = load_cookies_from_file(cookies_file)
        if cookies:
            context.add_cookies(cookies)
        return len(cookies)

    def _apply_storage_origins(self, context, origins: list[dict]) -> int:
        restored = 0
        for origin_state in origins:
            origin = origin_state.get("origin")
            local_storage = origin_state.get("localStorage", [])
            if not origin or not local_storage:
                continue
            page = context.new_page()
            try:
                page.goto(origin, wait_until="domcontentloaded", timeout=self.timeout_ms)
                for item in local_storage:
                    name = item.get("name")
                    value = item.get("value")
                    if name is None or value is None:
                        continue
                    page.evaluate(
                        "([storage_key, storage_value]) => window.localStorage.setItem(storage_key, storage_value)",
                        [name, value],
                    )
                restored += 1
            except Exception:
                continue
            finally:
                if not page.is_closed():
                    page.close()
        return restored

    def _load_storage_state(self, context) -> tuple[int, int]:
        if not self.storage_state_path:
            return 0, 0
        storage_file = Path(self.storage_state_path)
        if not storage_file.exists():
            return 0, 0
        state = load_storage_state_from_file(storage_file)
        cookies = state["cookies"]
        if cookies:
            context.add_cookies(cookies)
        origins_loaded = self._apply_storage_origins(context, state["origins"])
        return len(cookies), origins_loaded

    def _restore_session(self, context) -> dict[str, int]:
        cookies_loaded = 0
        origins_loaded = 0
        storage_file = Path(self.storage_state_path) if self.storage_state_path else None
        if storage_file and storage_file.exists():
            cookies_loaded, origins_loaded = self._load_storage_state(context)
        elif self.cookies_path:
            cookies_loaded = self._load_cookies(context)
        return {
            "cookies_loaded": cookies_loaded,
            "origins_loaded": origins_loaded,
        }

    def _persist_cookies(self, context) -> int:
        if not self.cookies_path:
            return 0
        cookies = [normalize_cookie(cookie) for cookie in context.cookies()]
        _write_json_file(self.cookies_path, cookies)
        return len(cookies)

    def _persist_storage_state(self, context) -> int:
        if not self.storage_state_path:
            return 0
        state = context.storage_state()
        state["cookies"] = [normalize_cookie(cookie) for cookie in state.get("cookies", [])]
        _write_json_file(self.storage_state_path, state)
        return len(state.get("cookies", []))

    def _persist_session_artifacts(self, context) -> dict[str, int]:
        return {
            "cookies_saved": self._persist_cookies(context),
            "storage_cookies_saved": self._persist_storage_state(context),
        }

    def _build_session_report(self, page, session_state: dict[str, int], persisted_state: dict[str, int]) -> dict[str, object]:
        title = page.title()
        content = page.content().lower()
        blocked = any(marker in content or marker in title.lower() for marker in BLOCK_MARKERS)
        return {
            "ok": not blocked,
            "url": page.url,
            "title": title,
            "cookies_loaded": session_state["cookies_loaded"],
            "origins_loaded": session_state["origins_loaded"],
            "cookies_saved": persisted_state["cookies_saved"],
            "storage_cookies_saved": persisted_state["storage_cookies_saved"],
            "blocked": blocked,
        }

    def fetch_text(self, url: str) -> str:
        with self._open_context() as playwright:
            context = self._launch_browser(playwright)
            try:
                self._restore_session(context)
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                content = page.content()
                self._persist_session_artifacts(context)
                return content
            finally:
                context.close()

    def check_session(self, url: str) -> dict[str, object]:
        with self._open_context() as playwright:
            context = self._launch_browser(playwright)
            try:
                session_state = self._restore_session(context)
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                persisted_state = self._persist_session_artifacts(context)
                return self._build_session_report(page, session_state, persisted_state)
            finally:
                context.close()

    def export_session(self, url: str) -> dict[str, object]:
        with self._open_context() as playwright:
            context = self._launch_browser(playwright)
            try:
                session_state = self._restore_session(context)
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                persisted_state = self._persist_session_artifacts(context)
                return self._build_session_report(page, session_state, persisted_state)
            finally:
                context.close()

    def warm_session(self, url: str) -> dict[str, object]:
        with self._open_context() as playwright:
            context = self._launch_browser(playwright)
            try:
                session_state = self._restore_session(context)
                page = context.new_page()
                print(f"[warm] launched channel={self.channel} headless={self.headless} proxy={self.proxy}")
                print(f"[warm] cookies_path={self.cookies_path} storage_state_path={self.storage_state_path}")
                print(
                    f"[warm] restored cookies={session_state['cookies_loaded']} origins={session_state['origins_loaded']}"
                )
                page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                print(f"[warm] url={page.url}")
                print(f"[warm] title={page.title()}")
                print(f"[warm] pages={len(context.pages)}")
                if self.headless:
                    page.wait_for_timeout(1000)
                else:
                    print("Complete the browser interaction, then close the browser window manually.")
                    while True:
                        try:
                            pages = context.pages
                            if not pages:
                                print("[warm] no pages left, exiting loop")
                                break
                            if pages[0].is_closed():
                                print("[warm] primary page closed, exiting loop")
                                break
                            time.sleep(1)
                        except Exception as exc:
                            print(f"[warm] loop exception: {exc}")
                            break
                persisted_state = self._persist_session_artifacts(context)
                return {
                    **session_state,
                    **persisted_state,
                    "url": page.url,
                    "title": page.title(),
                }
            finally:
                try:
                    context.close()
                except Exception:
                    pass


def build_fetcher(
    mode: str,
    *,
    browser_user_data_dir: str = DEFAULT_BROWSER_USER_DATA_DIR,
    browser_headless: bool = True,
    browser_channel: str | None = "chrome",
    browser_proxy: str | None = None,
    browser_cookies_path: str = DEFAULT_BROWSER_COOKIES_PATH,
    browser_storage_state_path: str = DEFAULT_BROWSER_STORAGE_STATE_PATH,
):
    if mode == "http":
        return SiteFetcher(proxy=browser_proxy)
    if mode == "browser":
        proxy_config = parse_proxy_config(browser_proxy) if browser_proxy else None
        if (
            proxy_config
            and browser_user_data_dir == DEFAULT_BROWSER_USER_DATA_DIR
            and browser_cookies_path == DEFAULT_BROWSER_COOKIES_PATH
            and browser_storage_state_path == DEFAULT_BROWSER_STORAGE_STATE_PATH
        ):
            browser_user_data_dir = _with_proxy_suffix(browser_user_data_dir)
            browser_cookies_path = _with_proxy_suffix(browser_cookies_path)
            browser_storage_state_path = _with_proxy_suffix(browser_storage_state_path)
        return BrowserSiteFetcher(
            user_data_dir=browser_user_data_dir,
            headless=browser_headless,
            channel=browser_channel,
            proxy=proxy_config,
            cookies_path=browser_cookies_path,
            storage_state_path=browser_storage_state_path,
        )
    raise ValueError(f"Unsupported fetch mode: {mode}")
