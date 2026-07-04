import httpx


DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,sl;q=0.8",
}


class SiteFetcher:
    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    def fetch_text(self, url: str) -> str:
        response = httpx.get(url, timeout=self.timeout, headers=DEFAULT_HEADERS, follow_redirects=True)
        response.raise_for_status()
        return response.text


class BrowserSiteFetcher:
    def __init__(self, headless: bool = True, timeout_ms: int = 30000):
        self.headless = headless
        self.timeout_ms = timeout_ms

    def fetch_text(self, url: str) -> str:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is required for browser fetch mode. Install it with 'pip install playwright' "
                "and then run 'playwright install chromium'."
            ) from exc

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=self.headless)
            try:
                page = browser.new_page(user_agent=DEFAULT_HEADERS["User-Agent"])
                page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                return page.content()
            finally:
                browser.close()



def build_fetcher(mode: str):
    if mode == "http":
        return SiteFetcher()
    if mode == "browser":
        return BrowserSiteFetcher()
    raise ValueError(f"Unsupported fetch mode: {mode}")
