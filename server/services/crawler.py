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
        .map((el, index) => {
            return {
                element: el,
                index: index,
                tag: el.tagName.toLowerCase(),
                level: parseInt(el.tagName[1]),
                text: (el.innerText || el.textContent || '').trim().slice(0, 150),
                outerHTML: el.outerHTML.slice(0, 400),
                xpath: getXPath(el)
            };
        })
        .filter(item => {
            const el = item.element;
            const s = window.getComputedStyle(el);
            const isVisible = s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
            delete item.element;
            return isVisible;
        });
}
"""

JS_COOKIE_ACCEPT = r"""
() => {
    try {
        const palavras_chave = /aceitar|accept|agree|allow all|got it|ok, i agree|concordo|i agree/i;
        const botao = Array.from(document.querySelectorAll("button, a, [role='button'], [class*='btn']"))
            .find(el => palavras_chave.test(el.innerText || '') || palavras_chave.test(el.getAttribute('aria-label') || ''));
        if (botao) {
            botao.click();
            return "Clicked";
        }
    } catch (e) {}
    return "Not clicked";
}
"""

async def crawl_page(url: str, context=None, audit_cache: dict = None) -> dict:
    """Crawl a single page and return heading audit results."""
    if audit_cache and url in audit_cache:
        logger.info(f"Returning cached audit for: {url}")
        return audit_cache[url]

    headings = []
    final_url = ""
    from bs4 import BeautifulSoup

    page_ctx = browser_manager.page_in_context(context) if context else browser_manager.page()

    async with page_ctx as page:
        logger.info(f"Navigating to {url}")

        try:
            response = await page.goto(url, wait_until="load", timeout=15000)
        except Exception as e:
            logger.warning(f"Failed to load URL '{url}' with 'load' state: {e}. Trying 'domcontentloaded' fallback...")
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=8000)
            except Exception as e2:
                logger.warning(f"Failed fallback navigation to URL '{url}' : {e2}")
                response = None

        if response and not response.ok:
            raise Exception(f"HTTP {response.status}")

        await asyncio.sleep(2.0)

        for _ in range(3):
            try:
                await page.evaluate(JS_COOKIE_ACCEPT)
            except Exception:
                pass
            await asyncio.sleep(0.8)

        try:
            await page.wait_for_selector('a[href], article, main, h1, h2, img', timeout=5000)
        except Exception:
            pass

        await scroll_down_page(page)

        headings = await page.evaluate(JS_EXTRACT_HEADINGS)

        rendered_html = await page.content()
        final_url = page.url

        def _process_soup(html_content, target_url):
            from bs4 import BeautifulSoup
            s = BeautifulSoup(html_content, "html.parser")
            import asyncio
            return s
            
        soup = await asyncio.to_thread(_process_soup, rendered_html, final_url)

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

    from datetime import datetime
    res_dict = {
        "headings": headings,
        "finalUrl": final_url,
        "renderedHtml": rendered_html,
        "result": aspect_result,
        "auditadoEm": datetime.utcnow().isoformat() + "Z",
    }
    if audit_cache is not None:
        audit_cache[url] = res_dict
    return res_dict

