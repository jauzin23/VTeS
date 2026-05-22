import asyncio
import re
import json
import logging
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode, urljoin
from selectolax.parser import HTMLParser
from .browser import browser_manager, JS_COOKIE_ACCEPT, scroll_down_page
import httpx

logger = logging.getLogger("h_audit.discover")

DETAIL_PATH_IGNORES = re.compile(
    r"\/(sobre|contacto|contactos|login|registo|termos|privacidade|privacy|cookies|pesquisa|search|account|perfil|checkout|cart|carrinho)(\/|$)",
    re.I
)

PAGE_PARAM_CANDIDATES = ["page", "pagina", "pg", "p", "offset", "inicio"]
MAX_PAGES_TO_FOLLOW = 20

def normalize_url(url_str: str) -> str:
    try:
        p = urlparse(url_str)
        path = p.path
        if len(path) > 1 and path.endswith("/"):
            path = path[:-1]
        elif path == "/":
            path = ""
        query = f"?{p.query}" if p.query else ""
        return f"{p.scheme}://{p.netloc}{path}{query}"
    except Exception:
        return url_str

def build_page_url(base_url: str, page_number: int, param_name: str = "page") -> str:
    try:
        p = urlparse(base_url)
        params = dict(parse_qsl(p.query, keep_blank_values=True))
        params[param_name] = str(page_number)
        query = urlencode(params)
        return normalize_url(urlunparse((p.scheme, p.netloc, p.path, p.params, query, "")))
    except Exception:
        return base_url

def parse_page_param(url_str: str) -> tuple[str | None, int | None]:
    try:
        p = urlparse(url_str)
        query = dict(parse_qsl(p.query, keep_blank_values=True))
        for k in PAGE_PARAM_CANDIDATES:
            if k in query:
                val = query[k]
                try:
                    return k, int(val)
                except ValueError:
                    return k, None
    except Exception:
        pass
    return None, None

def is_pagination_label(label: str) -> bool:
    return bool(re.search(
        r"\b(page|pagina|página|anterior|prev|previous|next|seguinte|próxima|proxima)\b",
        label,
        re.I
    ))

def should_ignore_detail_link(href: str, start_url: str, label: str = "") -> bool:
    if not href or href.lower().startswith(("javascript:", "mailto:", "tel:", "#")):
        return True
    if is_pagination_label(label):
        return True
    try:
        url = urlparse(href)
        start = urlparse(start_url)
        if url.netloc and url.netloc != start.netloc:
            return True
            
        path = url.path.lower()
        # Same page check
        if url.path == start.path and url.query == start.query:
            return True
            
        if len(path) <= 1:
            return True
        if DETAIL_PATH_IGNORES.search(path):
            return True
        if re.search(r"\/page\/\d+", path, re.I) and not url.query:
            return True
        if re.match(r"^(?:\/?(page|pagina|p)\/?\d+)$", path.strip("/"), re.I):
            return True
        return False
    except Exception:
        return True

def extract_next_data(html: str) -> dict | None:
    if not html:
        return None
    try:
        tree = HTMLParser(html)
        script_node = tree.css_first("script#__NEXT_DATA__")
        if script_node:
            text = script_node.text(strip=False) or ""
            return json.loads(text)
    except Exception:
        pass
    return None

def traverse_pagination_keys(next_data: dict) -> dict:
    if not isinstance(next_data, dict):
        return {}
    props = next_data.get("props", {}).get("pageProps", next_data)
    
    total_keys = ("totalpages", "total_bytes", "pagecount", "page_count", "total_pages", "lastpage", "last_page")
    current_keys = ("currentpage", "current_page", "page", "pagina_atual")
    
    def _find_val(obj, targets):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k.lower().replace("_", "").replace("-", "") in targets:
                    return v
            for v in obj.values():
                res = _find_val(v, targets)
                if res is not None:
                    return res
        elif isinstance(obj, list):
            for item in obj:
                res = _find_val(item, targets)
                if res is not None:
                    return res
        return None

    total = _find_val(props, total_keys)
    current = _find_val(props, current_keys)
    
    res = {}
    try:
        if total is not None:
            res["total_paginas"] = int(total)
    except Exception:
        pass
    try:
        if current is not None:
            res["pagina_atual"] = int(current)
    except Exception:
        pass
    return res

# XHR log interception helper
CHAVES_LISTA = ("items", "data", "results", "events", "eventos", "products", "produtos", "list", "rows")
CHAVES_TOTAL = ("totalpages", "total_pages", "pagecount", "page_count", "total", "totalitems", "total_items")

def inspect_xhr_response(json_data: any) -> dict | None:
    if not isinstance(json_data, dict):
        return None
    
    total_pages = 0
    list_key = None
    list_len = 0
    
    def norm(k: str) -> str:
        return k.lower().replace("-", "").replace("_", "")
        
    for k, v in json_data.items():
        if isinstance(v, (int, float)) and norm(k) in CHAVES_TOTAL:
            total_pages = max(total_pages, int(v))
            
    if total_pages == 0:
        for v in json_data.values():
            if isinstance(v, dict):
                for k2, v2 in v.items():
                    if isinstance(v2, (int, float)) and norm(k2) in CHAVES_TOTAL:
                        total_pages = max(total_pages, int(v2))
                        
    for k, v in json_data.items():
        if isinstance(v, list) and v and isinstance(v[0], dict):
            if norm(k) in CHAVES_LISTA or len(v) > list_len:
                list_key = k
                list_len = len(v)
                
    if total_pages > 1 or (list_len and total_pages):
        return {
            "totalPages": int(total_pages) if total_pages else None,
            "items_len": list_len,
            "list_key": list_key
        }
    return None


async def audit_and_cache_page(page, url: str, html: str, audit_cache: dict | None):
    if audit_cache is None or url in audit_cache:
        return
    try:
        from bs4 import BeautifulSoup
        from datetime import datetime
        from .crawler import HEADING_ANALYZER, JS_EXTRACT_HEADINGS

        headings = await page.evaluate(JS_EXTRACT_HEADINGS)
        final_url = page.url
        soup = BeautifulSoup(html, "html.parser")
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
        
        audit_cache[url] = {
            "headings": headings,
            "finalUrl": final_url,
            "renderedHtml": html,
            "result": aspect_result,
            "auditadoEm": datetime.utcnow().isoformat() + "Z",
        }
        logger.info(f"Audited and cached page during discovery: {url}")
    except Exception as e:
        logger.warning(f"Failed to audit and cache page {url} during discovery: {e}")


async def discover_paginated_pages(start_url: str, context=None, audit_cache: dict = None) -> list[str]:
    normalized_start_url = normalize_url(start_url)
    discovered_pages = [normalized_start_url]
    discovered_set = {normalized_start_url}

    page_ctx = browser_manager.page_in_context(context) if context else browser_manager.page()

    async with page_ctx as page:
        api_captured = None

        async def on_response(response):
            nonlocal api_captured
            try:
                ct = (response.headers.get("content-type") or "").lower()
                if "json" not in ct:
                    return
                if response.request.method.upper() not in ("GET", "POST"):
                    return
                if response.status >= 400:
                    return
                data = await response.json()
                meta = inspect_xhr_response(data)
                if meta and meta.get("totalPages"):
                    api_captured = {
                        "url": response.request.url,
                        "method": response.request.method,
                        "totalPages": meta["totalPages"],
                    }
            except Exception:
                pass

        page.on("response", on_response)

        try:
            try:
                await page.goto(normalized_start_url, wait_until="domcontentloaded", timeout=20000)
            except Exception as e:
                logger.warning(f"Timeout on initial pagination discovery load: {e}")

            # Accept cookies
            try:
                await page.evaluate(JS_COOKIE_ACCEPT)
                await asyncio.sleep(0.3)
            except Exception:
                pass

            # Full scroll down to trigger dynamic loading of elements/images/links
            await scroll_down_page(page)

            try:
                await page.locator(
                    ".ant-pagination, .pagination--select, .events-card__link-wrapper, .events-card, .ant-list-item, .ant-card, .article, .content, [class*='card'], [class*='item'], img"
                ).first.wait_for(timeout=4000)
            except Exception:
                pass
            await asyncio.sleep(0.5)

            try:
                dom_pag = await page.evaluate(JS_DETETAR_PAGINACAO)
            except Exception as e:
                logger.warning(f"Failed to detect pagination: {e}")
                dom_pag = {}

            try:
                html = await page.content()
                next_data = extract_next_data(html)
            except Exception:
                next_data = None
                html = ""

            if html:
                await audit_and_cache_page(page, normalized_start_url, html, audit_cache)

            total_pages = 1
            param_name = "page"
            next_href = normalize_url(dom_pag.get("nextHref") or "") if dom_pag.get("nextHref") else ""

            url_param_name, _ = parse_page_param(normalized_start_url)
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

            if api_captured and api_captured.get("totalPages"):
                total_pages = max(total_pages, int(api_captured["totalPages"]))

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
                for page_num in range(2, total_pages + 1):
                    page_url = build_page_url(normalized_start_url, page_num, param_name)
                    if page_url not in discovered_set:
                        discovered_set.add(page_url)
                        discovered_pages.append(page_url)
            elif next_href:
                current_next = next_href
                hops = 0

                while current_next and hops < MAX_PAGES_TO_FOLLOW - 1:
                    normalized_next = normalize_url(current_next)
                    if normalized_next in discovered_set:
                        break

                    discovered_set.add(normalized_next)
                    discovered_pages.append(normalized_next)
                    hops += 1

                    try:
                        await page.goto(normalized_next, wait_until="domcontentloaded", timeout=15000)
                        # Accept cookies
                        try:
                            await page.evaluate(JS_COOKIE_ACCEPT)
                        except Exception:
                            pass
                        # Scroll down on subsequent listing page
                        await scroll_down_page(page)

                        try:
                            await page.locator(
                                ".ant-pagination, .pagination--select, .events-card__link-wrapper, .events-card, .ant-list-item, .ant-card, .article, .content, [class*='card'], [class*='item'], img"
                            ).first.wait_for(timeout=3000)
                        except Exception:
                            pass
                        try:
                            subsequent_html = await page.content()
                            await audit_and_cache_page(page, normalized_next, subsequent_html, audit_cache)
                        except Exception:
                            pass
                        next_dom = await page.evaluate(JS_DETETAR_PAGINACAO)
                        current_next = normalize_url(next_dom.get("nextHref") or "") if next_dom.get("nextHref") else ""
                    except Exception as e:
                        logger.warning(f"Failed following next pagination link {normalized_next}: {e}")
                        break
        finally:
            try:
                page.remove_listener("response", on_response)
            except Exception:
                pass

    return discovered_pages

JS_DETETAR_PAGINACAO = r"""
async () => {
    const saida = {
        paginacao_total: 0,
        paginacao_atual: 1,
        parametro_pagina: 'page',
        amostra_paginacao: [],
        deteccao: '',
        nextHref: '',
    };
    const esperar = ms => new Promise(r => setTimeout(r, ms));
    const numerosDe = (nos) => {
        const vals = [];
        for (const no of nos) {
            const bruto = (no?.getAttribute?.('title') || no?.textContent || '').trim();
            const n = parseInt(bruto);
            if (!isNaN(n)) vals.push(n);
        }
        return vals;
    };

    const itensAntd = Array.from(document.querySelectorAll('li.ant-pagination-item[title]'));
    if (itensAntd.length) {
        const numeros = itensAntd.map(li => parseInt(li.getAttribute('title'))).filter(n => !isNaN(n) && !(n >= 1900 && n <= 2100) && n <= 5000);
        if (numeros.length) saida.paginacao_total = Math.max(...numeros);
        const ativo = document.querySelector('li.ant-pagination-item-active[title]');
        if (ativo) {
            const v = parseInt(ativo.getAttribute('title'));
            if (!isNaN(v)) saida.paginacao_atual = v;
        }
        for (const li of itensAntd) {
            const a = li.querySelector('a[href]');
            if (a && a.href) saida.amostra_paginacao.push(a.href);
        }
        saida.deteccao = 'antd_pagination_item';
    }

    if (!saida.paginacao_total) {
        const sel =
            document.querySelector('.pagination--select .ant-select-selector') ||
            document.querySelector('[class*="pagination"] .ant-select-selector') ||
            document.querySelector('[class*="paginacao"] .ant-select-selector');
        if (sel) {
            const item = sel.querySelector('.ant-select-selection-item[title]');
            if (item) {
                const v = parseInt(item.getAttribute('title'));
                if (!isNaN(v)) saida.paginacao_atual = v;
            }
            try {
                sel.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true, view: window}));
                sel.click();
                await esperar(200);
                const options = Array.from(document.querySelectorAll('.ant-select-item-option[title], .ant-select-item-option'));
                const numeros = options.map(o => parseInt(o.getAttribute('title') || o.textContent)).filter(n => !isNaN(n) && !(n >= 1900 && n <= 2100) && n <= 5000);
                if (numeros.length) {
                    saida.paginacao_total = Math.max(...numeros);
                    saida.deteccao = 'antd_select_options';
                }
                document.body.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
            } catch (e) {}
        }
    }

    if (!saida.paginacao_total) {
        try {
            const containers = Array.from(document.querySelectorAll('[class*="pagination"], [class*="paginacao"], nav, footer'));
            for (const c of containers) {
                const txt = (c.innerText || '').trim();
                const m = txt.match(/(?:page|página)?\s*(\d+)\s*(?:de|of|from|\/)\s*(\d+)/i);
                if (m && m[2]) {
                    const v = parseInt(m[2]);
                    // Ignore years (1900-2100) to prevent interpreting "1 de 2025" as 2025 pages
                    if (v > 1 && v < 5000 && !(v >= 1900 && v <= 2100)) {
                        saida.paginacao_total = v;
                        saida.deteccao = 'label_de_n';
                        break;
                    }
                }
            }
        } catch (e) {}
    }

    let nextHref = '';
    const nextSels = [
        'link[rel="next"]', 'a[rel="next"]', '[aria-label*="Next" i]', '[aria-label*="Próxim" i]',
        '[aria-label*="Seguinte" i]', '.pagination .next a', '.pagination a.next',
        '.pager-next a', 'a.nextpostslink', '.nav-next a',
        '[data-testid*="pagination-next" i]', 'a[title*="Página seguinte" i]',
        'a[title*="Seguinte" i]', 'a[class*="next" i]:not([class*="newest" i])',
        '.pagination--select__next', '.ant-pagination-next a', '.ant-pagination-next'
    ];
    for (const sel of nextSels) {
        const el = document.querySelector(sel);
        const href = el?.href || el?.getAttribute?.('href');
        if (href && !href.startsWith('javascript:')) { nextHref = href; break; }
    }

    if (nextHref) {
        saida.nextHref = nextHref;
    }

    const candidatos = [
        '[role="navigation"][aria-label*="pagina" i] a',
        '[class*="pagination"] a',
        '[class*="paginacao"] a',
        'nav.pagination a',
    ];
    let maxN = 0;
    for (const s of candidatos) {
        document.querySelectorAll(s).forEach(el => {
            const txt = (el.textContent || '').trim();
            const n = parseInt(txt);
            if (!isNaN(n)) {
                // Prevent years from being parsed as page numbers
                if (!(n >= 1900 && n <= 2100) && n <= 5000) {
                    if (n > maxN) maxN = n;
                }
            }
            if (el.href) {
                try {
                    const u = new URL(el.href, window.location.href);
                    for (const k of ['page', 'pagina', 'pg', 'p', 'offset', 'inicio']) {
                        const v = u.searchParams.get(k);
                        if (v && /^\d+$/.test(v)) {
                            saida.parametro_pagina = k;
                            saida.amostra_paginacao.push(el.href);
                        }
                    }
                } catch (e) {}
            }
        });
    }

    if (maxN > saida.paginacao_total) {
        saida.paginacao_total = maxN;
        saida.deteccao = saida.deteccao || 'numeric_links';
    }

    return saida;
}
"""

JS_EXTRACT_DETAIL_LINKS = r"""
(args) => {
    const startUrl = args[0];
    const detailPathIgnoresSource = args[1];
    const detailPathIgnores = new RegExp(detailPathIgnoresSource, 'i');
    
    const isPaginationLabel = (label) => {
        return /\b(page|pagina|página|anterior|prev|previous|next|seguinte|próxima|proxima)\b/i.test(label);
    };

    const shouldIgnore = (href, label = "") => {
        if (!href || /^javascript:/i.test(href) || href.startsWith('#') || href.startsWith('mailto:') || href.startsWith('tel:')) return true;
        if (isPaginationLabel(label)) return true;
        try {
            const url = new URL(href, window.location.href);
            const start = new URL(startUrl);
            if (url.origin !== start.origin) return true;
            if (url.pathname === start.pathname && url.search === start.search) return true;
            if (url.pathname.length <= 1) return true;
            if (detailPathIgnores.test(url.pathname)) return true;
            if (/\/page\/\d+/i.test(url.pathname) && !url.search) return true;
            if (/^(?:\/?(page|pagina|p)\/?\d+)$/.test(url.pathname.replace(/\/+$/, ""))) return true;
            return false;
        } catch {
            return true;
        }
    };

    const extractFromSelectors = (selectors) => {
        const links = [];
        const seen = new Set();
        selectors.forEach(sel => {
            document.querySelectorAll(sel).forEach(el => {
                if (el.closest("nav") || el.closest("footer") || el.closest("header")) return;
                const anchors = el.tagName.toLowerCase() === 'a' ? [el] : Array.from(el.querySelectorAll('a[href]'));
                anchors.forEach(a => {
                    const href = a.href;
                    const label = ((a.innerText || a.textContent || "") + " " + (a.getAttribute("aria-label") || "")).trim();
                    if (!shouldIgnore(href, label)) {
                        try {
                            const normUrl = href.replace(/\/$/, "");
                            if (!seen.has(normUrl)) {
                                seen.add(normUrl);
                                links.push(href);
                            }
                        } catch(e){}
                    }
                });
            });
        });
        return links;
    };

    // Layer 1: Specific card link wrappers and common patterns
    const specificSelectors = [
        ".events-card__link-wrapper",
        ".events-card a[href]",
        ".event-card a[href]",
        ".agenda-card a[href]",
        "a[class*='link-wrapper']",
        "a[class*='card-link']",
        "a[class*='item-link']",
        "[class*='card__link-wrapper']",
        "[class*='card__link']",
        "[class*='events-card'] a[href]",
        "[class*='event-card'] a[href]",
        "[class*='agenda-card'] a[href]",
        "[class*='noticia-card'] a[href]",
        "[class*='noticias-card'] a[href]",
        "[class*='post-card'] a[href]"
    ];
    let results = extractFromSelectors(specificSelectors);
    if (results.length > 0) return results;

    // Layer 2: Generic cards/list items
    const genericSelectors = [
        "[class*='card'] a[href]",
        "[class*='item'] a[href]",
        "[class*='grid'] a[href]",
        "[class*='list__item'] a[href]",
        "[class*='list-item'] a[href]",
        "[class*='post'] a[href]",
        "article a[href]"
    ];
    results = extractFromSelectors(genericSelectors);
    if (results.length > 0) return results;

    // Layer 3: Fallback - original main content container search
    const containers = [
        "main", '[role="main"]', "article", "section", ".content", '[class*="content"]',
        ".card", '[class*="card"]', '[class*="list"]', '[class*="grid"]', '[class*="item"]', "body"
    ].flatMap(sel => Array.from(document.querySelectorAll(sel)))
     .filter((c, idx, self) => self.indexOf(c) === idx)
     .filter(c => !c.closest("nav") && !c.closest("footer") && !c.closest("header"));

    const targets = containers.length ? containers : [document.body];
    const seen = new Set();
    const fallbackLinks = [];
    targets.forEach(c => {
        c.querySelectorAll('a[href]').forEach(a => {
            const href = a.href;
            const label = ((a.innerText || a.textContent || "") + " " + (a.getAttribute("aria-label") || "")).trim();
            if (!shouldIgnore(href, label)) {
                try {
                    const normUrl = href.replace(/\/$/, "");
                    if (!seen.has(normUrl)) {
                        seen.add(normUrl);
                        fallbackLinks.push(href);
                    }
                } catch(e){}
            }
        });
    });

    return fallbackLinks;
}
"""

async def discover_urls(start_url: str, context=None, audit_cache: dict = None) -> list[str]:
    discovered_detail_urls = set()
    visited_listing_pages = set()
    api_captured = None

    normalized_start_url = normalize_url(start_url)
    visited_listing_pages.add(normalized_start_url)
    
    # 1. Open the browser and visit the start URL
    page_ctx = browser_manager.page_in_context(context) if context else browser_manager.page()
    async with page_ctx as page:
        # Attach response handler to intercept XHR/JSON APIs
        async def on_response(response):
            nonlocal api_captured
            try:
                ct = (response.headers.get("content-type") or "").lower()
                if "json" not in ct:
                    return
                if response.request.method.upper() not in ("GET", "POST"):
                    return
                if response.status >= 400:
                    return
                data = await response.json()
                meta = inspect_xhr_response(data)
                if meta and meta.get("totalPages"):
                    api_captured = {
                        "url": response.request.url,
                        "method": response.request.method,
                        "totalPages": meta["totalPages"],
                        "list_key": meta.get("list_key")
                    }
                    logger.info(f"Captured XHR API: {api_captured['url']} with totalPages={api_captured['totalPages']}")
            except Exception:
                pass
                
        page.on("response", on_response)

        try:
            try:
                await page.goto(normalized_start_url, wait_until="domcontentloaded", timeout=20000)
            except Exception as e:
                logger.warning(f"Timeout on initial load: {e}")

            # Accept cookies
            try:
                await page.evaluate(JS_COOKIE_ACCEPT)
                await asyncio.sleep(0.3)
            except Exception:
                pass

            # Full scroll down to trigger lazy load before extracting listing elements
            await scroll_down_page(page)

            # Wait for listings
            try:
                await page.locator(".ant-pagination, .ant-list-item, .ant-card, .article, .content, .events-card__link-wrapper, [class*='card'], [class*='item'], img").first.wait_for(timeout=4000)
            except Exception:
                pass
            await asyncio.sleep(0.5)

            # Detect pagination DOM
            try:
                dom_pag = await page.evaluate(JS_DETETAR_PAGINACAO)
            except Exception as e:
                logger.warning(f"Failed to detect pagination: {e}")
                dom_pag = {}

            # Extract next data
            try:
                html = await page.content()
                next_data = extract_next_data(html)
            except Exception:
                next_data = None
                html = ""

            if html and audit_cache is not None:
                await audit_and_cache_page(page, normalized_start_url, html, audit_cache)

            # Compute pagination details
            total_pages = 1
            param_name = "page"
            next_href = dom_pag.get("nextHref") or ""
            detection_source = dom_pag.get("deteccao") or ""

            # Query param checks
            url_param_name, url_param_val = parse_page_param(normalized_start_url)
            if url_param_name:
                param_name = url_param_name

            if next_data:
                next_info = traverse_pagination_keys(next_data)
                if next_info.get("total_paginas"):
                    total_pages = next_info["total_paginas"]
                    detection_source = "next_data"

            dom_total = dom_pag.get("paginacao_total") or 0
            if dom_total > 1:
                total_pages = max(total_pages, int(dom_total))
                detection_source = dom_pag.get("deteccao") or "dom_pagination"
                
            if dom_pag.get("parametro_pagina"):
                param_name = dom_pag["parametro_pagina"]

            if api_captured:
                total_pages = max(total_pages, api_captured["totalPages"])
                detection_source = "xhr_log"

            logger.info(f"Pagination Detection Source: {detection_source}, total={total_pages}, param={param_name}")

            # Extract initial detail links
            try:
                initial_links = await page.evaluate(JS_EXTRACT_DETAIL_LINKS, [normalized_start_url, DETAIL_PATH_IGNORES.pattern])
                for link in initial_links:
                    discovered_detail_urls.add(normalize_url(link))
            except Exception as e:
                logger.warning(f"Error extracting detail links from start URL: {e}")

            # If pagination total is found, build page URLs
            pages_to_crawl = []
            if total_pages > 1:
                limit = min(total_pages, MAX_PAGES_TO_FOLLOW)
                for page_num in range(2, limit + 1):
                    pages_to_crawl.append(build_page_url(normalized_start_url, page_num, param_name))
            elif next_href:
                # Let's start following sequentially up to max pages if no total count
                curr_next = next_href
                visited_listing_pages.add(normalize_url(curr_next))
                pages_to_crawl.append(curr_next)
        finally:
            try:
                page.remove_listener("response", on_response)
            except Exception:
                pass


    # 2. Visit other pagination pages
    # We can do this in parallel to save a lot of time!
    # We limit active concurrent listing page crawls to 4
    sem = asyncio.Semaphore(4)

    async def crawl_listing_page(list_url: str):
        async with sem:
            resolved = normalize_url(list_url)
            if resolved in visited_listing_pages:
                return
            visited_listing_pages.add(resolved)
            
            logger.info(f"Crawling pagination page: {resolved}")
            try:
                page_ctx_sub = browser_manager.page_in_context(context) if context else browser_manager.page()
                async with page_ctx_sub as page:
                    await page.goto(resolved, wait_until="domcontentloaded", timeout=15000)
                    
                    # Accept cookies
                    try:
                        await page.evaluate(JS_COOKIE_ACCEPT)
                    except Exception:
                        pass
                    
                    # Dynamic full scroll down
                    await scroll_down_page(page)

                    await asyncio.sleep(0.5)
                    try:
                        html = await page.content()
                    except Exception:
                        html = ""
                    if html and audit_cache is not None:
                        await audit_and_cache_page(page, resolved, html, audit_cache)

                    links = await page.evaluate(JS_EXTRACT_DETAIL_LINKS, [resolved, DETAIL_PATH_IGNORES.pattern])
                    for l in links:
                        discovered_detail_urls.add(normalize_url(l))
            except Exception as e:
                logger.warning(f"Failed crawling listing page {resolved}: {e}")

    if pages_to_crawl:
        await asyncio.gather(*(crawl_listing_page(u) for u in pages_to_crawl), return_exceptions=True)

    # Filter by origin
    start_origin = urlparse(normalized_start_url).netloc
    filtered_urls = []
    for href in discovered_detail_urls:
        try:
            if urlparse(href).netloc == start_origin:
                filtered_urls.append(href)
        except Exception:
            pass

    logger.info(f"Discovered {len(filtered_urls)} detail URLs.")
    return filtered_urls[:20]
