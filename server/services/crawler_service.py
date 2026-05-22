import asyncio
import json
import logging
import httpx
from urllib.parse import urlparse, urljoin, urlunparse, parse_qsl, urlencode
from selectolax.parser import HTMLParser
from .discover import (
    normalize_url,
    build_page_url,
    JS_DETETAR_PAGINACAO,
    parse_page_param,
    extract_next_data,
    traverse_pagination_keys,
    audit_and_cache_page
)
from .crawler import crawl_page
from .browser import browser_manager, scroll_down_page
from .html_processor import inject_iframe_script

logger = logging.getLogger("tes.crawler_service")

# Extensions to ignore during link discovery
EXTENSOES_IGNORAR = (
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".rar", ".gz", ".tar", ".7z", ".exe",
    ".mp4", ".mp3", ".avi", ".mov", ".wmv", ".flv", ".ogg", ".wav",
    ".xml", ".json", ".csv", ".txt", ".svg", ".ico", ".css", ".js",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".bmp", ".tiff"
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

JS_EXTRACT_LINKS = r"""
() => {
    const links = new Set();
    
    // 1. Standard anchors
    document.querySelectorAll('a[href]').forEach(a => {
        const h = a.getAttribute('href');
        if (h && !h.startsWith('#') && !h.startsWith('javascript:') && !h.startsWith('mailto:') && !h.startsWith('tel:')) {
            try {
                links.add(new URL(h, window.location.href).href);
            } catch(e){}
        }
    });
    
    // 2. Clickable elements with data-href or onclick location changes
    document.querySelectorAll('[data-href], [onclick]').forEach(el => {
        const h = el.getAttribute('data-href') || 
                  (el.getAttribute('onclick') || '').match(/window\.location\.href\s*=\s*['"]([^'"]+)['"]/)?.[1];
        if (h) {
            try {
                links.add(new URL(h, window.location.href).href);
            } catch(e){}
        }
    });

    // 3. __NEXT_DATA__ routes
    if (window.__NEXT_DATA__) {
        const routesFound = new Set();
        const recursiveFind = (obj, depth = 0) => {
            if (!obj || typeof obj !== 'object' || depth > 10) return;
            for (let k in obj) {
                try {
                    const v = obj[k];
                    if (typeof v === 'string' && v.length > 1) {
                        if (v.startsWith('/') && !v.startsWith('//')) {
                             if (!v.includes('.') || v.includes('.html')) {
                                  routesFound.add(v);
                             }
                        }
                    } else if (typeof v === 'object') {
                        recursiveFind(v, depth + 1);
                    }
                } catch(e){}
            }
        };
        recursiveFind(window.__NEXT_DATA__);
        routesFound.forEach(v => {
            try {
                links.add(new URL(v, window.location.href).href);
            } catch(e){}
        });
    }

    return Array.from(links);
}
"""

def strip_www(netloc: str) -> str:
    n = netloc.lower()
    return n[4:] if n.startswith("www.") else n

def same_site(netloc_a: str, netloc_b: str) -> bool:
    return strip_www(netloc_a) == strip_www(netloc_b)

def is_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False

def normalize_crawler_url(url_str: str) -> str:
    try:
        normalized = normalize_url(url_str)
        p = urlparse(normalized)
        if p.query:
            partes = parse_qsl(p.query, keep_blank_values=True)
            # Remove tracking and analytical query params
            filtradas = [
                (k, v) for k, v in partes
                if not k.lower().startswith(("utm_", "fbclid", "gclid", "_ga", "_gl", "msclkid"))
            ]
            if filtradas:
                filtradas.sort()
                query = urlencode(filtradas)
            else:
                query = ""
            return urlunparse((p.scheme, p.netloc, p.path, p.params, query, ""))
        return normalized
    except Exception:
        return url_str

def filter_and_normalize_links(links: list[str], target_host: str) -> list[str]:
    filtered = []
    for link in links:
        normalized = normalize_crawler_url(link)
        if not is_valid_url(normalized):
            continue
        path = urlparse(normalized).path.lower()
        if path.endswith(EXTENSOES_IGNORAR):
            continue
        if not same_site(urlparse(normalized).netloc, target_host):
            continue
        filtered.append(normalized)
    return filtered

def extract_static_links_and_markers(html: str, current_url: str):
    static_links = []
    has_spa_markers = False
    
    if not html:
        return static_links, has_spa_markers

    try:
        parser = HTMLParser(html)
        
        # Check base tag
        base_node = parser.css_first("base[href]")
        base_href = base_node.attributes.get("href") if base_node else None

        for node in parser.css("a[href]"):
            href = node.attributes.get("href")
            if not href:
                continue
            resolved_url = urljoin(base_href or current_url, href.strip())
            static_links.append(resolved_url)
            
        # Check next/spa markers in script tags
        for script in parser.css("script"):
            src = script.attributes.get("src") or ""
            if "_next/static" in src or "webpack-" in src or "chunk-" in src:
                has_spa_markers = True
                break
        
        # Check next data
        if parser.css_first("script#__NEXT_DATA__"):
            has_spa_markers = True
            
        if "_next/static" in html or "window.__NEXT_DATA__" in html or "id=\"__next\"" in html or "id=\"root\"" in html:
            has_spa_markers = True
            
    except Exception as e:
        logger.warning(f"Error extracting static links/markers: {e}")
        
    return static_links, has_spa_markers

def extract_next_data_routes(html: str, current_url: str) -> list[str]:
    routes = []
    try:
        parser = HTMLParser(html)
        script_node = parser.css_first("script#__NEXT_DATA__")
        if script_node:
            text = script_node.text(strip=False) or ""
            if text.strip():
                data = json.loads(text)
                
                def _recurse(obj, depth=0):
                    if depth > 10:
                        return
                    if isinstance(obj, str):
                        if len(obj) > 1 and obj.startswith('/') and not obj.startswith('//'):
                            path = urlparse(obj).path.lower()
                            if not path.endswith(EXTENSOES_IGNORAR):
                                routes.append(urljoin(current_url, obj))
                    elif isinstance(obj, list):
                        for item in obj:
                            _recurse(item, depth + 1)
                    elif isinstance(obj, dict):
                        for val in obj.values():
                            _recurse(val, depth + 1)
                
                _recurse(data)
    except Exception as e:
        logger.warning(f"Error extracting next data routes: {e}")
    return routes

async def extract_links_with_playwright(
    url: str,
    active_pages: list,
    pages_lock: asyncio.Lock,
    stop_event: asyncio.Event,
    context=None,
    audit_cache: dict = None
) -> list[str]:
    links = []
    if stop_event.is_set():
        return links
    try:
        page_ctx = browser_manager.page_in_context(context) if context else browser_manager.page()
        async with page_ctx as page:
            async with pages_lock:
                active_pages.append(page)
            try:
                try:
                    await page.goto(url, wait_until="load", timeout=15000)
                    await asyncio.sleep(2.0)  # Wait for SPA hydration
                except Exception as e:
                    if stop_event.is_set():
                        return links
                    logger.warning(f"Playwright navigation timed out or failed on load for {url}: {e}. Retrying with domcontentloaded...")
                    try:
                        await page.goto(url, wait_until="domcontentloaded", timeout=8000)
                        await asyncio.sleep(2.0)
                    except Exception as e2:
                        if stop_event.is_set():
                            return links
                        logger.warning(f"Playwright retry failed for {url}: {e2}")

                if stop_event.is_set():
                    return links

                # Accept cookies (try multiple times to catch delayed banners)
                for _ in range(3):
                    try:
                        await page.evaluate(JS_COOKIE_ACCEPT)
                    except Exception:
                        pass
                    await asyncio.sleep(0.8)

                if stop_event.is_set():
                    return links

                # Wait for generic content elements to verify the loader is gone
                try:
                    await page.wait_for_selector('a[href], article, main, h1, h2', timeout=5000)
                except Exception:
                    pass

                # Full scroll down to ensure dynamic content / lazy loaded links are rendered
                await scroll_down_page(page)

                if stop_event.is_set():
                    return links

                # Extract links using JS
                extracted = await page.evaluate(JS_EXTRACT_LINKS)
                if extracted:
                    links = [str(l) for l in extracted]

                # Detect pagination
                try:
                    dom_pag = await page.evaluate(JS_DETETAR_PAGINACAO)
                except Exception as e:
                    logger.warning(f"Failed to detect pagination on {url}: {e}")
                    dom_pag = {}

                try:
                    html = await page.content()
                    next_data = extract_next_data(html)
                    if html and audit_cache is not None:
                        await audit_and_cache_page(page, url, html, audit_cache)
                except Exception:
                    next_data = None

                total_pages = 1
                param_name = "page"
                next_href = normalize_url(dom_pag.get("nextHref") or "") if dom_pag.get("nextHref") else ""

                url_param_name, _ = parse_page_param(url)
                if url_param_name:
                    param_name = url_param_name

                if next_data:
                    next_info = traverse_pagination_keys(next_data)
                    if next_info.get("total_paginas"):
                        total_pages = next_info["total_paginas"]

                dom_total = dom_pag.get("paginacao_total") or 0
                if dom_total > 1:
                    total_pages = max(total_pages, int(dom_total))

                if dom_pag.get("parametro_pagina"):
                    param_name = dom_pag["parametro_pagina"]

                sample_pagination_urls = [
                    normalize_url(href)
                    for href in (dom_pag.get("amostra_paginacao") or [])
                    if href
                ]
                if total_pages <= 1 and sample_pagination_urls:
                    for sample_url in sample_pagination_urls:
                        sample_param_name, sample_page_num = parse_page_param(sample_url)
                        if sample_param_name:
                            param_name = sample_param_name
                        if sample_page_num and sample_page_num > total_pages:
                            total_pages = sample_page_num

                if total_pages > 1:
                    logger.info(f"Pagination detected on {url}: total_pages={total_pages}, param={param_name}")
                    for page_num in range(2, total_pages + 1):
                        page_url = build_page_url(url, page_num, param_name)
                        links.append(page_url)
                elif next_href:
                    logger.info(f"Next page link detected on {url}: {next_href}")
                    links.append(next_href)

            finally:
                async with pages_lock:
                    if page in active_pages:
                        active_pages.remove(page)
    except Exception as e:
        if not stop_event.is_set():
            logger.warning(f"Error using Playwright to extract links from {url}: {e}")
    return links

async def crawl_worker(
    client: httpx.AsyncClient,
    queue: asyncio.Queue,
    discovered_set: set,
    discovered_list: list,
    visited_set: set,
    target_host: str,
    max_pages: int,
    lock: asyncio.Lock,
    seed_url: str,
    stop_event: asyncio.Event,
    active_pages: list,
    active_pages_lock: asyncio.Lock,
    context=None,
    audit_cache: dict = None
):
    while not stop_event.is_set():
        try:
            current_url = await asyncio.wait_for(queue.get(), timeout=0.5)
        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            break

        async with lock:
            if current_url in visited_set or len(visited_set) >= max_pages or stop_event.is_set():
                queue.task_done()
                continue
            visited_set.add(current_url)

        logger.info(f"Crawler fetching: {current_url}")
        
        raw_links = []
        
        try:
            logger.info(f"Crawling {current_url} via Playwright")
            raw_links = await extract_links_with_playwright(
                current_url,
                active_pages,
                active_pages_lock,
                stop_event,
                context=context,
                audit_cache=audit_cache
            )

            # Filter and normalize links
            filtered_links = filter_and_normalize_links(raw_links, target_host)

            # Enqueue newly discovered links
            for normalized in filtered_links:
                async with lock:
                    if normalized not in discovered_set and len(discovered_set) < max_pages and not stop_event.is_set():
                        discovered_set.add(normalized)
                        discovered_list.append(normalized)
                        await queue.put(normalized)
        except Exception as e:
            logger.error(f"Error in crawl_worker processing {current_url}: {e}")
        finally:
            queue.task_done()

async def discover_all_links_concurrent(seed_url: str, max_pages: int = 100, concurrency: int = 5, context=None, audit_cache: dict = None) -> list[str]:
    seed_url = normalize_crawler_url(seed_url)
    if not is_valid_url(seed_url):
        return []

    parsed_seed = urlparse(seed_url)
    target_host = strip_www(parsed_seed.netloc)

    discovered_set = {seed_url}
    discovered_list = [seed_url]
    visited_set = set()

    queue = asyncio.Queue()
    await queue.put(seed_url)

    lock = asyncio.Lock()
    stop_event = asyncio.Event()
    active_pages = []
    active_pages_lock = asyncio.Lock()

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    async with httpx.AsyncClient(
        timeout=3.0,
        follow_redirects=True,
        headers=headers
    ) as client:
        workers = []
        for _ in range(concurrency):
            worker = asyncio.create_task(
                crawl_worker(
                    client,
                    queue,
                    discovered_set,
                    discovered_list,
                    visited_set,
                    target_host,
                    max_pages,
                    lock,
                    seed_url,
                    stop_event,
                    active_pages,
                    active_pages_lock,
                    context=context,
                    audit_cache=audit_cache
                )
            )
            workers.append(worker)

        # Wait until the queue is fully processed or we reach our limit
        queue_join_task = asyncio.create_task(queue.join())
        try:
            while not queue_join_task.done():
                async with lock:
                    if len(visited_set) >= max_pages:
                        stop_event.set()
                        break
                await asyncio.sleep(0.2)
        finally:
            stop_event.set()
            queue_join_task.cancel()
            
            # Close all active pages to abort their network operations immediately
            async with active_pages_lock:
                for page in list(active_pages):
                    try:
                        await page.close()
                    except Exception:
                        pass
            
            # Wait for workers to exit cleanly
            try:
                await asyncio.wait_for(asyncio.gather(*workers, return_exceptions=True), timeout=3.0)
            except asyncio.TimeoutError:
                logger.warning("Force-cancelling remaining crawler workers after timeout.")
                for w in workers:
                    if not w.done():
                        w.cancel()
                await asyncio.gather(*workers, return_exceptions=True)

    return discovered_list[:max_pages]

async def run_crawler_audit(raw_input: str, max_pages: int = 100) -> dict:
    """
    Crawls website links recursively and audits headings on each discovered page.
    """
    from datetime import datetime
    import time
    
    start_time = time.time()
    iniciado_em = datetime.utcnow().isoformat() + "Z"

    base_url = normalize_crawler_url(raw_input)
    if not is_valid_url(base_url):
        finalized_at = datetime.utcnow().isoformat() + "Z"
        duracao = time.time() - start_time
        return {
            "baseUrl": raw_input,
            "status": "error",
            "message": "URL inválido",
            "pages": [],
            "totalPages": 0,
            "iniciadoEm": iniciado_em,
            "finalizadoEm": finalized_at,
            "duracao": duracao,
            "duracaoFormatada": format_duration(duracao),
        }

    logger.info(f"Starting crawler link discovery for: {base_url} (limit: {max_pages})")

    audit_cache = {}

    async with browser_manager.session_context(seed_url=base_url) as context:
        try:
            discovered_urls = await discover_all_links_concurrent(base_url, max_pages=max_pages, context=context, audit_cache=audit_cache)
        except Exception as e:
            logger.exception("Failed link discovery in crawler")
            finalized_at = datetime.utcnow().isoformat() + "Z"
            duracao = time.time() - start_time
            return {
                "baseUrl": base_url,
                "status": "error",
                "message": f"Erro na descoberta de links: {str(e)}",
                "pages": [],
                "totalPages": 0,
                "iniciadoEm": iniciado_em,
                "finalizadoEm": finalized_at,
                "duracao": duracao,
                "duracaoFormatada": format_duration(duracao),
            }

        if not discovered_urls:
            finalized_at = datetime.utcnow().isoformat() + "Z"
            duracao = time.time() - start_time
            return {
                "baseUrl": base_url,
                "status": "error",
                "message": "Nenhum link encontrado para rastrear.",
                "pages": [],
                "totalPages": 0,
                "iniciadoEm": iniciado_em,
                "finalizadoEm": finalized_at,
                "duracao": duracao,
                "duracaoFormatada": format_duration(duracao),
            }

        logger.info(f"Crawler found {len(discovered_urls)} URLs. Running browser audits...")

        results = []
        # Using Playwright concurrency (e.g. 5)
        audit_sem = asyncio.Semaphore(5)
        results_lock = asyncio.Lock()

        async def audit_page(url: str):
            async with audit_sem:
                try:
                    logger.info(f"Auditing page: {url}")
                    crawl = await crawl_page(url, context=context, audit_cache=audit_cache)
                    processed_html = inject_iframe_script(
                        crawl.get("renderedHtml", ""),
                        crawl["finalUrl"]
                    )
                    async with results_lock:
                        results.append({
                            "url": url,
                            "finalUrl": crawl["finalUrl"],
                            "headings": crawl["headings"],
                            "issues": crawl["result"]["issues"],
                            "status": crawl["result"]["status"],
                            "issueCount": len(crawl["result"]["issues"]),
                            "hasFailures": any(i["severity"] == "FAIL" for i in crawl["result"]["issues"]),
                            "processedHtml": processed_html,
                            "auditadoEm": crawl.get("auditadoEm") or datetime.utcnow().isoformat() + "Z",
                        })
                except Exception as e:
                    logger.warning(f"Audit failed for {url}: {e}")
                    async with results_lock:
                        results.append({
                            "url": url,
                            "finalUrl": url,
                            "headings": [],
                            "issues": [],
                            "status": "ERROR",
                            "issueCount": 0,
                            "hasFailures": False,
                            "processedHtml": None,
                            "error": str(e),
                            "auditadoEm": datetime.utcnow().isoformat() + "Z",
                        })

        await asyncio.gather(
            *(audit_page(url) for url in discovered_urls),
            return_exceptions=True
        )

    # Sort results by URL
    results.sort(key=lambda r: r["url"])

    total_issues = sum(r["issueCount"] for r in results)
    pages_with_failures = sum(1 for r in results if r.get("status") == "ERROR" or r.get("hasFailures"))
    pages_with_warnings = sum(1 for r in results if r.get("status") != "ERROR" and not r.get("hasFailures") and any(i["severity"] == "REVIEW" for i in r.get("issues", [])))

    finalized_at = datetime.utcnow().isoformat() + "Z"
    duracao = time.time() - start_time

    return {
        "baseUrl": base_url,
        "status": "completed",
        "totalPages": len(results),
        "totalIssues": total_issues,
        "pagesWithFailures": pages_with_failures,
        "pagesWithWarnings": pages_with_warnings,
        "pages": results,
        "iniciadoEm": iniciado_em,
        "finalizadoEm": finalized_at,
        "duracao": duracao,
        "duracaoFormatada": format_duration(duracao),
    }


def format_duration(seconds: float) -> str:
    total_seconds = int(round(seconds))
    if total_seconds < 60:
        return f"{total_seconds}s"
    minutes = total_seconds // 60
    secs = total_seconds % 60
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}h {mins}m {secs}s"
