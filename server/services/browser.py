import os
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

class BrowserManager:
    def __init__(self, max_tabs: int = 5) -> None:
        self._playwright = None
        self._browser = None
        self._context = None
        self._lock = asyncio.Lock()
        self._sem_tabs = asyncio.Semaphore(max_tabs)
        self._is_open = False

    async def _close_internal(self) -> None:
        if not self._is_open:
            return
        logger.info("Closing Playwright Chromium (internal)...")
        try:
            if self._context:
                await self._context.close()
        except Exception:
            pass
        finally:
            self._context = None
            try:
                if self._browser:
                    await self._browser.close()
            except Exception:
                pass
            finally:
                self._browser = None
                try:
                    if self._playwright:
                        await self._playwright.stop()
                except Exception:
                    pass
                finally:
                    self._playwright = None
        self._is_open = False
        logger.info("Playwright Chromium closed.")

    async def _start_internal(self) -> None:
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
        import sys
        if os.getenv("BROWSER_SINGLE_PROCESS", "False").lower() == "true" and sys.platform != "win32":
            args.append("--single-process")
        
        max_old_space = os.getenv("PLAYWRIGHT_MAX_OLD_SPACE_SIZE", "512")
        args.append(f"--js-flags=--max-old-space-size={max_old_space}")

        headless_mode = os.getenv("PLAYWRIGHT_HEADLESS", "True").lower() == "true"
        self._browser = await self._playwright.chromium.launch(
            headless=headless_mode,
            args=args
        )
        self._context = await self._browser.new_context(
            user_agent=USER_AGENT,
            locale="pt-PT",
            viewport={"width": 1280, "height": 720},
        )
        await self._context.route("**/*", self._block_resources_custom)
        self._is_open = True
        logger.info("Playwright Chromium started.")

    async def start(self) -> None:
        if self._is_open and self._browser and not self._browser.is_connected():
            logger.warning("Browser disconnected. Resetting state...")
            async with self._lock:
                if self._is_open and self._browser and not self._browser.is_connected():
                    await self._close_internal()

        if self._is_open:
            return
        async with self._lock:
            await self._start_internal()

    async def close(self) -> None:
        async with self._lock:
            await self._close_internal()

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

    async def _safe_close_page(self, page):
        """Close a page with a timeout to prevent hanging."""
        try:
            if page.is_closed:
                return
            await asyncio.wait_for(page.close(), timeout=3.0)
        except asyncio.TimeoutError:
            logger.warning("Page close timed out, force-closing...")
            try:
                await page.close()
            except Exception:
                pass
        except Exception:
            pass

    @asynccontextmanager
    async def session_context(self, seed_url: str = None):
        await self.start()
        yield self._context

    @asynccontextmanager
    async def page_in_context(self, context=None):
        await self.start()
        async with self._sem_tabs:
            ctx = context if context is not None else self._context
            
            # Check if browser is disconnected before attempting new page
            if self._browser and not self._browser.is_connected():
                logger.warning("Browser disconnected before page creation in page_in_context. Restarting...")
                async with self._lock:
                    if self._browser and not self._browser.is_connected():
                        await self._close_internal()
                        await self._start_internal()
                ctx = self._context

            try:
                page = await ctx.new_page()
            except Exception as e:
                err_str = str(e).lower()
                if any(x in err_str for x in ("closed", "connection", "target", "handler")):
                    logger.warning(f"Failed to create new page in page_in_context: {e}")
                    async with self._lock:
                        if self._context == ctx:
                            logger.info("Restarting browser context...")
                            await self._close_internal()
                            await self._start_internal()
                        else:
                            logger.info("Browser context already restarted by another task.")
                    ctx = self._context
                    page = await ctx.new_page()
                else:
                    raise

            try:
                yield page
            finally:
                try:
                    await page.close()
                except Exception:
                    pass

    @asynccontextmanager
    async def page(self):
        await self.start()
        async with self._sem_tabs:
            if self._browser and not self._browser.is_connected():
                logger.warning("Browser disconnected before page creation in page. Restarting...")
                async with self._lock:
                    if self._browser and not self._browser.is_connected():
                        await self._close_internal()
                        await self._start_internal()

            ctx = self._context
            try:
                page = await ctx.new_page()
            except Exception as e:
                err_str = str(e).lower()
                if any(x in err_str for x in ("closed", "connection", "target", "handler")):
                    logger.warning(f"Failed to create new page in page: {e}")
                    async with self._lock:
                        if self._context == ctx:
                            logger.info("Restarting browser context...")
                            await self._close_internal()
                            await self._start_internal()
                        else:
                            logger.info("Browser context already restarted by another task.")
                    ctx = self._context
                    page = await ctx.new_page()
                else:
                    raise

            try:
                yield page
            finally:
                try:
                    await page.close()
                except Exception:
                    pass

PLAYWRIGHT_MAX_TABS = int(os.getenv("PLAYWRIGHT_MAX_TABS", "10"))
browser_manager = BrowserManager(max_tabs=PLAYWRIGHT_MAX_TABS)


async def scroll_down_page(page) -> None:
    """Perform a full incremental scroll down to trigger lazy loading, then return to top."""
    try:
        await page.evaluate("""
            async () => {
                const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
                let lastHeight = document.body.scrollHeight;
                let steps = 0;
                const maxSteps = 25;
                while (steps < maxSteps) {
                    window.scrollBy(0, window.innerHeight * 1.5);
                    await delay(200);
                    let newHeight = document.body.scrollHeight;
                    let currentScroll = window.scrollY + window.innerHeight;
                    if (currentScroll >= newHeight - 30) {
                        // Wait slightly more at the bottom to check for lazy-loaded content
                        await delay(300);
                        newHeight = document.body.scrollHeight;
                        currentScroll = window.scrollY + window.innerHeight;
                        if (currentScroll >= newHeight - 30) {
                            break;
                        }
                    }
                    lastHeight = newHeight;
                    steps++;
                }
                window.scrollTo(0, 0);
                await delay(150);
            }
        """)
    except Exception as e:
        logger.warning(f"Error scrolling down page: {e}")


