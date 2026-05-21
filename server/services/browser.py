import asyncio
import logging
from contextlib import asynccontextmanager
from playwright.async_api import async_playwright

logger = logging.getLogger("h_audit.browser")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

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

class BrowserManager:
    def __init__(self, max_tabs: int = 5) -> None:
        self._playwright = None
        self._browser = None
        self._lock = asyncio.Lock()
        self._sem_tabs = asyncio.Semaphore(max_tabs)
        self._is_open = False
        self._context_page_pools = {}

    async def start(self) -> None:
        if self._is_open:
            return
        async with self._lock:
            if self._is_open:
                return
            logger.info("Starting Playwright Chromium instance...")
            self._playwright = await async_playwright().start()

            args = [
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-extensions",
                "--disable-background-networking",
                "--disable-sync",
                "--disable-translate",
                "--no-first-run",
            ]

            self._browser = await self._playwright.chromium.launch(
                headless=False,
                args=args
            )
            self._is_open = True
            logger.info("Playwright Chromium started.")

    async def close(self) -> None:
        async with self._lock:
            if not self._is_open:
                return
            logger.info("Closing Playwright Chromium...")
            try:
                if self._browser:
                    await self._browser.close()
            finally:
                if self._playwright:
                    await self._playwright.stop()
            self._is_open = False
            logger.info("Playwright Chromium closed.")

    async def _block_resources_custom(self, route):
        req = route.request
        resource_type = req.resource_type
        url = req.url.lower()

        # Block tracking/analytics domains to prevent navigation delays
        is_tracking = any(domain in url for domain in (
            "google-analytics.com", "googletagmanager.com", "connect.facebook.net",
            "facebook.com", "doubleclick.net", "hotjar.com", "clarity.ms",
            "analytics"
        ))

        if resource_type in ("image", "font", "other", "webmanifest", "media") or is_tracking:
            try:
                await route.abort()
            except:
                pass
        else:
            try:
                await route.continue_()
            except:
                pass

    @asynccontextmanager
    async def session_context(self, seed_url: str = None):
        await self.start()
        context = await self._browser.new_context(
            user_agent=USER_AGENT,
            locale="pt-PT",
            viewport={"width": 1280, "height": 720},
        )

        await context.route("**/*", self._block_resources_custom)

        try:
            yield context
        finally:
            for page in list(context.pages):
                try:
                    if not page.is_closed:
                        await page.close()
                except Exception:
                    pass
            try:
                await context.close()
            except Exception:
                pass

    @asynccontextmanager
    async def page_in_context(self, context):
        async with self._sem_tabs:
            page = await context.new_page()
            try:
                yield page
            finally:
                try:
                    if not page.is_closed:
                        await page.close()
                except Exception:
                    pass

    @asynccontextmanager
    async def page(self):
        await self.start()
        async with self._sem_tabs:
            context = await self._browser.new_context(
                user_agent=USER_AGENT,
                locale="pt-PT",
                viewport={"width": 1280, "height": 720},
            )

            await context.route("**/*", self._block_resources_custom)
            page = await context.new_page()
            try:
                yield page
            finally:
                try:
                    await page.close()
                except Exception:
                    pass
                try:
                    await context.close()
                except Exception:
                    pass

browser_manager = BrowserManager(max_tabs=5)


async def scroll_down_page(page) -> None:
    """Perform a full incremental scroll down to trigger lazy loading, then return to top."""
    try:
        await page.evaluate("""
            async () => {
                const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
                let lastHeight = document.body.scrollHeight;
                let steps = 0;
                while (steps < 4) {
                    window.scrollBy(0, window.innerHeight * 2);
                    await delay(100);
                    let newHeight = document.body.scrollHeight;
                    let currentScroll = window.scrollY + window.innerHeight;
                    if (currentScroll >= newHeight - 15) {
                        // Wait slightly more at the bottom to check for lazy-loaded content
                        await delay(100);
                        newHeight = document.body.scrollHeight;
                        currentScroll = window.scrollY + window.innerHeight;
                        if (currentScroll >= newHeight - 15) {
                            break;
                        }
                    }
                    lastHeight = newHeight;
                    steps++;
                }
                window.scrollTo(0, 0);
                await delay(100);
            }
        """)
    except Exception as e:
        logger.warning(f"Error scrolling down page: {e}")


