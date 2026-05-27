import asyncio
import logging
import httpx
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
from .discover import discover_paginated_pages, discover_urls, normalize_url
from .crawler import crawl_page
from .html_processor import inject_iframe_script
from .browser import browser_manager

logger = logging.getLogger("h_audit.sitemap")

MAX_SITEMAP_URLS = 200   # Maximum URLs to process from sitemap
CRAWL_CONCURRENCY = 5    # Concurrent page crawls


def strip_www(netloc: str) -> str:
    """Return netloc without a leading 'www.' for fuzzy domain matching."""
    n = netloc.lower()
    return n[4:] if n.startswith("www.") else n


def same_site(netloc_a: str, netloc_b: str) -> bool:
    """True if two netlocs refer to the same website (www-insensitive)."""
    return strip_www(netloc_a) == strip_www(netloc_b)


def normalize_base_url(raw: str) -> str:
    raw = raw.strip()
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    parsed = urlparse(raw)
    return f"{parsed.scheme}://{parsed.netloc}"


async def fetch_sitemap_urls(base_url: str) -> list[str]:
    """Fetch /sitemap.xml from the given base URL and return all <loc> page URLs.
    Handles sitemap index files recursively. Tries both www and non-www variants."""
    parsed = urlparse(base_url)
    base_netloc = parsed.netloc

    candidates = [base_url.rstrip("/") + "/sitemap.xml"]
    if base_netloc.startswith("www."):
        alt = f"{parsed.scheme}://{base_netloc[4:]}/sitemap.xml"
    else:
        alt = f"{parsed.scheme}://www.{base_netloc}/sitemap.xml"
    candidates.append(alt)

    urls = []
    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SitemapBot/1.0)"}
        ) as client:
            for sitemap_url in candidates:
                logger.info(f"Fetching sitemap: {sitemap_url}")
                urls = await _fetch_and_parse_sitemap(client, sitemap_url, base_url, depth=0)
                if urls:
                    break
                logger.info(f"No URLs found from {sitemap_url}, trying next candidate...")
    except Exception as e:
        logger.error(f"Failed to fetch sitemap: {e}")

    logger.info(f"Sitemap discovered {len(urls)} URLs total")
    return urls[:MAX_SITEMAP_URLS]


async def _fetch_and_parse_sitemap(client: httpx.AsyncClient, sitemap_url: str, base_url: str, depth: int = 0) -> list[str]:
    """Recursively parse sitemap or sitemap index XML."""
    if depth > 3:
        return []

    try:
        resp = await client.get(sitemap_url)
        if resp.status_code != 200:
            logger.warning(f"Sitemap HTTP {resp.status_code}: {sitemap_url}")
            return []
    except Exception as e:
        logger.warning(f"Error fetching {sitemap_url}: {e}")
        return []

    content = resp.text
    urls = []

    try:
        root = ET.fromstring(content)
        tag = root.tag.lower()

        if "sitemapindex" in tag:
            logger.info(f"Found sitemap index at {sitemap_url}")
            nested_urls = []
            for sitemap_elem in root.iter():
                if sitemap_elem.tag.endswith("}loc") or sitemap_elem.tag == "loc":
                    nested_sitemap_url = sitemap_elem.text.strip() if sitemap_elem.text else ""
                    if nested_sitemap_url:
                        nested_urls.append(nested_sitemap_url)

            tasks = [
                _fetch_and_parse_sitemap(client, url, base_url, depth + 1)
                for url in nested_urls[:10]
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, list):
                    urls.extend(r)

        elif "urlset" in tag:
            base_netloc = urlparse(base_url).netloc
            for elem in root.iter():
                if elem.tag.endswith("}loc") or elem.tag == "loc":
                    loc = elem.text.strip() if elem.text else ""
                    if loc and loc.startswith(("http://", "https://")):
                        loc_path = urlparse(loc).path.lower()
                        if loc_path.endswith((".pdf", ".jpg", ".jpeg", ".png", ".gif",
                                              ".svg", ".webp", ".zip", ".docx", ".xlsx",
                                              ".pptx", ".doc", ".xls", ".csv", ".mp4",
                                              ".mp3", ".avi", ".mov", ".wmv")):
                            continue
                        if same_site(urlparse(loc).netloc, base_netloc):
                            urls.append(loc)

    except ET.ParseError as e:
        logger.warning(f"XML parse error for {sitemap_url}: {e}")

    return urls


async def run_sitemap_audit(raw_input: str) -> dict:
    from datetime import datetime
    import time
    
    start_time = time.time()
    iniciado_em = datetime.utcnow().isoformat() + "Z"

    base_url = normalize_base_url(raw_input)
    logger.info(f"Starting sitemap audit for: {base_url}")

    sitemap_urls = await fetch_sitemap_urls(base_url)

    if not sitemap_urls:
        finalized_at = datetime.utcnow().isoformat() + "Z"
        duracao = time.time() - start_time
        return {
            "baseUrl": base_url,
            "sitemapUrl": base_url + "/sitemap.xml",
            "status": "no_sitemap",
            "message": "Não foi possível obter URLs do sitemap.xml",
            "pages": [],
            "totalPages": 0,
            "iniciadoEm": iniciado_em,
            "finalizadoEm": finalized_at,
            "duracao": duracao,
            "duracaoFormatada": format_duration(duracao),
        }

    logger.info(f"Processing {len(sitemap_urls)} URLs from sitemap")

    groups_map: dict[str, dict] = {}
    all_pages_to_audit: set[str] = set()
    page_to_group: dict[str, str] = {}
    audit_cache = {}

    async with browser_manager.session_context(seed_url=base_url) as context:

        async def discover_for_url(input_url: str):
            """Discover paginated sub-pages for a given sitemap URL."""
            try:
                listing_pages = await discover_paginated_pages(input_url, context=context, audit_cache=audit_cache)
            except Exception as e:
                logger.warning(f"Discovery failed for {input_url}: {e}")
                listing_pages = [input_url]

            normalized_pages = []
            for page in listing_pages:
                normalized_page = normalize_url(page)
                if normalized_page not in normalized_pages:
                    normalized_pages.append(normalized_page)
                all_pages_to_audit.add(normalized_page)
                page_to_group[normalized_page] = input_url

            has_pagination = len(normalized_pages) > 1

            groups_map[input_url] = {
                "inputUrl": input_url,
                "pageCount": len(normalized_pages),
                "hasPagination": has_pagination,
                "pages": [],
                "_pageUrls": normalized_pages,
            }

        discovery_sem = asyncio.Semaphore(4)
        async def guarded_discover(url: str):
            async with discovery_sem:
                await discover_for_url(url)

        await asyncio.gather(
            *(guarded_discover(url) for url in sitemap_urls),
            return_exceptions=True
        )

        logger.info(f"Total pages to audit after discovery: {len(all_pages_to_audit)}")

        audit_results: dict[str, dict] = {}
        audit_sem = asyncio.Semaphore(CRAWL_CONCURRENCY)

        async def audit_page(url: str):
            async with audit_sem:
                try:
                    logger.info(f"Auditing: {url}")
                    crawl = await crawl_page(url, context=context, audit_cache=audit_cache)
                    processed_html = inject_iframe_script(
                        crawl.get("renderedHtml", ""),
                        crawl["finalUrl"]
                    )
                    audit_results[url] = {
                        "url": url,
                        "finalUrl": crawl["finalUrl"],
                        "headings": crawl["headings"],
                        "issues": crawl["result"]["issues"],
                        "status": crawl["result"]["status"],
                        "issueCount": len(crawl["result"]["issues"]),
                        "hasFailures": any(i["severity"] == "FAIL" for i in crawl["result"]["issues"]),
                        "processedHtml": processed_html,
                        "auditadoEm": crawl.get("auditadoEm") or datetime.utcnow().isoformat() + "Z",
                    }
                except Exception as e:
                    logger.warning(f"Audit failed for {url}: {e}")
                    audit_results[url] = {
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
                    }

        await asyncio.gather(
            *(audit_page(url) for url in sorted(list(all_pages_to_audit))),
            return_exceptions=True
        )

    groups = []
    total_issues = 0
    pages_with_failures = 0
    pages_with_warnings = 0

    for seed_url in sitemap_urls:
        group = groups_map.get(seed_url)
        if not group:
            continue

        page_results = []
        for page_url in group["_pageUrls"]:
            result = audit_results.get(page_url)
            if result:
                page_results.append(result)

        page_results.sort(key=lambda page: page["url"])
        group_issue_count = sum(page["issueCount"] for page in page_results)
        group_pages_with_failures = sum(1 for page in page_results if page.get("status") == "ERROR" or page.get("hasFailures"))
        group_pages_with_warnings = sum(1 for page in page_results if page.get("status") != "ERROR" and not page.get("hasFailures") and any(i["severity"] == "REVIEW" for i in page.get("issues", [])))

        total_issues += group_issue_count
        pages_with_failures += group_pages_with_failures
        pages_with_warnings += group_pages_with_warnings

        groups.append({
            "inputUrl": group["inputUrl"],
            "pageCount": len(page_results),
            "hasPagination": group["hasPagination"],
            "issueCount": group_issue_count,
            "pagesWithFailures": group_pages_with_failures,
            "pagesWithWarnings": group_pages_with_warnings,
            "pages": page_results,
        })

    finalized_at = datetime.utcnow().isoformat() + "Z"
    duracao = time.time() - start_time

    return {
        "baseUrl": base_url,
        "sitemapUrl": base_url + "/sitemap.xml",
        "status": "completed",
        "totalInputUrls": len(sitemap_urls),
        "totalPages": sum(group["pageCount"] for group in groups),
        "totalIssues": total_issues,
        "pagesWithFailures": pages_with_failures,
        "pagesWithWarnings": pages_with_warnings,
        "groups": groups,
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
