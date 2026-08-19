"""Compliant anti-bot / JS-rendering strategy.

The pipeline does not attempt to defeat CAPTCHAs or access controls. It first prefers
official APIs/feeds, then normal HTTP, then an optional browser renderer for pages the
operator is allowed to access.
"""
import logging
logger=logging.getLogger(__name__)

def get_stealth_headers(referer=None):
    headers={
        "User-Agent":"AI-Signal-Research/1.0 (+https://github.com/)",
        "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language":"en-US,en;q=0.9",
    }
    if referer: headers["Referer"]=referer
    return headers

async def render_js_page(url:str):
    """Optional Playwright fallback for permitted JS-rendered pages.

    Returns page HTML or None. A CAPTCHA/403 is treated as a stop condition.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.info("Playwright not installed; JS fallback unavailable for %s",url)
        return None
    try:
        async with async_playwright() as p:
            browser=await p.chromium.launch(headless=True)
            page=await browser.new_page()
            response=await page.goto(url,wait_until="domcontentloaded",timeout=30000)
            if response and response.status in (403,429):
                await browser.close()
                return None
            html=await page.content()
            await browser.close()
            return html
    except Exception as exc:
        logger.warning("JS rendering failed for %s: %s",url,exc)
        return None
