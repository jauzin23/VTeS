import asyncio
import logging

from .crawler import crawl_page
from .discover import discover_paginated_pages, discover_urls, normalize_url
from .html_processor import inject_iframe_script
from .browser import browser_manager

logger = logging.getLogger("h_audit.multi_url")

import os

CRAWL_CONCURRENCY = max(2, min(5, (os.cpu_count() or 4) // 2))
DISCOVERY_CONCURRENCY = 1


async def run_multi_url_audit(raw_urls: list[str]) -> dict:
    from datetime import datetime
    import time

    start_time = time.time()
    iniciado_em = datetime.utcnow().isoformat() + "Z"

    normalized_inputs = []
    seen_inputs = set()

    for raw in raw_urls:
        clean = raw.strip()
        if not clean:
            continue
        normalized = normalize_url(clean)
        if normalized in seen_inputs:
            continue
        seen_inputs.add(normalized)
        normalized_inputs.append(normalized)

    if not normalized_inputs:
        finalized_at = datetime.utcnow().isoformat() + "Z"
        duracao = time.time() - start_time
        return {
            "status": "completed",
            "totalInputUrls": 0,
            "totalPages": 0,
            "totalIssues": 0,
            "pagesWithFailures": 0,
            "pagesWithWarnings": 0,
            "groups": [],
            "iniciadoEm": iniciado_em,
            "finalizadoEm": finalized_at,
            "duracao": duracao,
            "duracaoFormatada": format_duration(duracao),
        }

    groups_map: dict[str, dict] = {}
    all_pages_to_audit: set[str] = set()
    page_to_group: dict[str, str] = {}
    audit_cache = {}

    seed_url = normalized_inputs[0] if normalized_inputs else None

    async with browser_manager.session_context(seed_url=seed_url) as context:
        async def discover_for_url(input_url: str):
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

            try:
                detail_pages = await discover_urls(input_url, context=context, audit_cache=audit_cache)
            except Exception as e:
                logger.warning(f"Detail discovery failed for {input_url}: {e}")
                detail_pages = []

            for page in detail_pages:
                normalized_page = normalize_url(page)
                if normalized_page not in normalized_pages:
                    normalized_pages.append(normalized_page)
                all_pages_to_audit.add(normalized_page)
                page_to_group[normalized_page] = input_url

            groups_map[input_url] = {
                "inputUrl": input_url,
                "pageCount": len(normalized_pages),
                "hasPagination": has_pagination,
                "pages": [],
                "_pageUrls": normalized_pages,
            }

        discovery_sem = asyncio.Semaphore(DISCOVERY_CONCURRENCY)

        async def guarded_discover(url: str):
            async with discovery_sem:
                await discover_for_url(url)

        await asyncio.gather(
            *(guarded_discover(url) for url in normalized_inputs),
            return_exceptions=True,
        )

        audit_results: dict[str, dict] = {}
        audit_sem = asyncio.Semaphore(CRAWL_CONCURRENCY)

        async def audit_page(url: str):
            async with audit_sem:
                try:
                    crawl = await crawl_page(url, context=context, audit_cache=audit_cache)
                    processed_html = await asyncio.to_thread(
                        inject_iframe_script,
                        crawl.get("renderedHtml", ""),
                        crawl["finalUrl"],
                    )
                    audit_results[url] = {
                        "url": url,
                        "finalUrl": crawl["finalUrl"],
                        "headings": crawl["headings"],
                        "issues": crawl["result"]["issues"],
                        "status": crawl["result"]["status"],
                        "issueCount": len(crawl["result"]["issues"]),
                        "hasFailures": any(
                            i["severity"] == "FAIL" for i in crawl["result"]["issues"]
                        ),
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
            *(audit_page(url) for url in sorted(all_pages_to_audit)),
            return_exceptions=True,
        )

    groups = []
    total_issues = 0
    pages_with_failures = 0
    pages_with_warnings = 0

    for seed_url in normalized_inputs:
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
        "status": "completed",
        "totalInputUrls": len(normalized_inputs),
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
