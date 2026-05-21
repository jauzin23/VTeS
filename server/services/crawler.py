import asyncio
import logging
from .browser import browser_manager, scroll_down_page
from .analyzers.heading_analyzer import HeadingAnalyzer

logger = logging.getLogger("h_audit.crawler")

HEADING_ANALYZER = HeadingAnalyzer()

JS_EXTRACT_HEADINGS = r"""
() => {
    function getXPath(el) {
        const parts = [];
        while (el?.nodeType === 1) {
            let idx = 1;
            let sib = el.previousElementSibling;
            while (sib) {
                if (sib.tagName === el.tagName) idx++;
                sib = sib.previousElementSibling;
            }
            parts.unshift(`${el.tagName.toLowerCase()}[${idx}]`);
            el = el.parentElement;
        }
        return '/' + parts.join('/');
    }

    return Array.from(document.querySelectorAll('h1, h2, h3, h4, h5, h6'))
        .filter(el => {
            const s = window.getComputedStyle(el);
            return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
        })
        .map((el, index) => {
            return {
                index,
                tag: el.tagName.toLowerCase(),
                level: parseInt(el.tagName[1]),
                text: (el.innerText || el.textContent || '').trim().slice(0, 150),
                outerHTML: el.outerHTML.slice(0, 400),
                xpath: getXPath(el)
            };
        });
}
"""

JS_COOKIE_ACCEPT = r"""
() => {
    try {
        // Try known selectors first
        const selectors = [
            '.btn-acceptAll', '.btn-accept-all', '#accept-all', '#acceptAll',
            '[class*="acceptAll"]', '[class*="accept-all"]', '[id*="acceptAll"]', '[id*="accept-all"]',
            '.cookies-btn', '.cookie-btn', '[class*="cookie-btn"]', '[class*="cookies-btn"]',
            '[class*="consent-btn"]', '[class*="cookie"] [class*="accept"]', '[id*="cookie"] [class*="accept"]'
        ];
        for (const sel of selectors) {
            const el = document.querySelector(sel);
            if (el && typeof el.click === 'function') {
                el.click();
                return "Clicked via selector: " + sel;
            }
        }

        // Try text-based matching
        const keywords = ['aceitar', 'accept', 'concordo', 'concordar', 'entendi', 'ok', 'permitir'];
        const buttons = Array.from(document.querySelectorAll('button, a, [role="button"], [class*="btn"]'));
        for (const btn of buttons) {
            const text = (btn.innerText || btn.textContent || '').trim().toLowerCase();
            if (
                keywords.some(kw => text.includes(kw)) &&
                !text.includes('recusar') &&
                !text.includes('reject')
            ) {
                btn.click();
                return "Clicked via text: " + text;
            }
        }
    } catch (e) {}
    return "Not clicked";
}
"""

async def crawl_page(url: str, context=None) -> dict:
    """Crawl a single page and return heading audit results."""
    headings = []
    final_url = ""
    from bs4 import BeautifulSoup

    page_ctx = browser_manager.page_in_context(context) if context else browser_manager.page()

    async with page_ctx as page:
        logger.info(f"Navigating to {url}")

        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=10000)
        except Exception as e:
            logger.warning(f"Failed to load {url} with 'domcontentloaded' state: {e}. Trying 'commit' fallback...")
            try:
                response = await page.goto(url, wait_until="commit", timeout=5000)
            except Exception as e2:
                logger.warning(f"Failed fallback navigation to {url}: {e2}")
                response = None

        if not response or not response.ok:
            status = response.status if response else 500
            raise Exception(f"HTTP {status}")

        await asyncio.sleep(0.8)

        # Accept cookies
        try:
            await page.evaluate(JS_COOKIE_ACCEPT)
        except Exception:
            pass

        await asyncio.sleep(0.3)

        # Full scroll down to ensure dynamic content / lazy loaded headings are loaded
        await scroll_down_page(page)

        headings = await page.evaluate(JS_EXTRACT_HEADINGS)

        rendered_html = await page.content()
        final_url = page.url
        soup = BeautifulSoup(rendered_html, "html.parser")

        res = await HEADING_ANALYZER.analyze(page, soup, final_url)
        aspect_result = {
            "status": res.status,
            "issues": [
                {
                    "rule": iss.rule,
                    "severity": iss.severity,
                    "message": iss.message,
                    "element": iss.element,
                    "xpath": iss.xpath,
                    "details": iss.details,
                }
                for iss in res.issues
            ]
        }

    return {
        "headings": headings,
        "finalUrl": final_url,
        "renderedHtml": rendered_html,
        "result": aspect_result,
    }

