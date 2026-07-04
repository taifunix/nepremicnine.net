import httpx


class SiteFetcher:
    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    def fetch_text(self, url: str) -> str:
        response = httpx.get(url, timeout=self.timeout, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        return response.text
