from nepremicnine_bot.fetcher import BrowserSiteFetcher, SiteFetcher, build_fetcher



def test_build_fetcher_returns_http_fetcher_for_http_mode():
    fetcher = build_fetcher("http")

    assert isinstance(fetcher, SiteFetcher)



def test_build_fetcher_returns_browser_fetcher_for_browser_mode():
    fetcher = build_fetcher("browser")

    assert isinstance(fetcher, BrowserSiteFetcher)
