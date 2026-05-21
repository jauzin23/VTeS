import os
import time
import logging
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from services.browser import browser_manager
from services.crawler import crawl_page
from services.discover import discover_urls, normalize_url
from services.multi_url_service import run_multi_url_audit
from services.sitemap_service import run_sitemap_audit
from services.crawler_service import run_crawler_audit
from services.html_processor import inject_iframe_script

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tes.server")


class SimpleCache:
    def __init__(self, max_size: int = 100, ttl_seconds: int = 300):
        self.max_size = max_size
        self.ttl = ttl_seconds
        self.store = {}
        self.lock = asyncio.Lock()

    async def get(self, key: str):
        async with self.lock:
            now = time.time()
            if key in self.store:
                val, expiry = self.store[key]
                if expiry > now:
                    return val
                else:
                    del self.store[key]
            return None

    async def set(self, key: str, value: any):
        async with self.lock:
            now = time.time()
            if len(self.store) >= self.max_size:
                first_key = next(iter(self.store))
                del self.store[first_key]
            self.store[key] = (value, now + self.ttl)


class AuditQueue:
    def __init__(self, concurrency: int = 3, max_queue: int = 20):
        self._sem = asyncio.Semaphore(concurrency)
        self._waiting = 0
        self._active = 0
        self._max_queue = max_queue
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        async with self._lock:
            if self._waiting >= self._max_queue:
                return False
            self._waiting += 1

        await self._sem.acquire()

        async with self._lock:
            self._waiting -= 1
            self._active += 1
        return True

    def release(self):
        self._sem.release()
        self._active = max(0, self._active - 1)

    @property
    def size(self):
        return self._waiting

    @property
    def pending(self):
        return self._active


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Browser Manager on startup...")
    await browser_manager.start()
    yield
    logger.info("Closing Browser Manager on shutdown...")
    await browser_manager.close()


app = FastAPI(title="VF-TeS API - Títulos e Subtítulos", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

cache = SimpleCache(max_size=200, ttl_seconds=600)
queue = AuditQueue(concurrency=3, max_queue=20)


class DiscoverRequest(BaseModel):
    url: str


class AuditRequest(BaseModel):
    url: str
    force: bool = False


class SitemapRequest(BaseModel):
    url: str  # domain like "example.com" or "https://example.com"


class MultiUrlAuditRequest(BaseModel):
    urls: list[str]


class CrawlerRequest(BaseModel):
    url: str
    maxPages: int = 100


@app.post("/api/discover")
async def api_discover(req: DiscoverRequest):
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL é obrigatório")
    try:
        urls = await discover_urls(url)
        return {"urls": urls}
    except Exception as e:
        logger.exception("Failed to discover URLs")
        raise HTTPException(status_code=500, detail="Falha ao descobrir URLs na paginação")


@app.post("/api/audit")
async def api_audit(req: AuditRequest):
    url_str = req.url.strip()
    if not url_str.startswith(("http://", "https://")):
        return JSONResponse(status_code=400, content={"erro": "URL inválido"})

    url = normalize_url(url_str)
    cache_key = f"audit:{url}"

    if not req.force:
        cached = await cache.get(cache_key)
        if cached:
            cached_copy = dict(cached)
            cached_copy["daCache"] = True
            return cached_copy

    acquired = await queue.acquire()
    if not acquired:
        return JSONResponse(
            status_code=429,
            content={
                "erro": "Servidor ocupado. Tente novamente em breve.",
                "retryAfter": 30,
            }
        )

    try:
        crawl_res = await crawl_page(url)

        processed_html = inject_iframe_script(
            crawl_res.get("renderedHtml", ""),
            crawl_res["finalUrl"]
        )

        result = {
            "url": url,
            "finalUrl": crawl_res["finalUrl"],
            "headings": crawl_res["headings"],
            "result": crawl_res["result"],
            "processedHtml": processed_html,
            "auditadoEm": datetime.utcnow().isoformat() + "Z",
        }

        await cache.set(cache_key, result)
        return result
    except Exception as e:
        logger.exception(f"Error auditing page {url}")
        status_code = 500
        err_msg = str(e)
        if "HTTP" in err_msg:
            try:
                status_code = int(err_msg.split("HTTP")[-1].strip())
            except ValueError:
                pass
        return JSONResponse(status_code=status_code, content={"erro": err_msg})
    finally:
        queue.release()


@app.post("/api/sitemap")
async def api_sitemap(req: SitemapRequest):
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL é obrigatório")

    cache_key = f"sitemap:{url}"
    cached = await cache.get(cache_key)
    if cached:
        return {**cached, "daCache": True}

    try:
        result = await run_sitemap_audit(url)
        await cache.set(cache_key, result)
        return result
    except Exception as e:
        logger.exception(f"Error running sitemap audit for {url}")
        raise HTTPException(status_code=500, detail=f"Erro no audit de sitemap: {str(e)}")


@app.post("/api/crawler")
async def api_crawler(req: CrawlerRequest):
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL é obrigatório")

    max_pages = min(max(req.maxPages, 1), 10000)
    cache_key = f"crawler:{url}:{max_pages}"
    cached = await cache.get(cache_key)
    if cached:
        return {**cached, "daCache": True}

    try:
        result = await run_crawler_audit(url, max_pages=max_pages)
        await cache.set(cache_key, result)
        return result
    except Exception as e:
        logger.exception(f"Error running crawler audit for {url}")
        raise HTTPException(status_code=500, detail=f"Erro no crawler: {str(e)}")


@app.post("/api/multi-url-audit")
async def api_multi_url_audit(req: MultiUrlAuditRequest):
    urls = [url.strip() for url in req.urls if url and url.strip()]
    if not urls:
        raise HTTPException(status_code=400, detail="Pelo menos um URL é obrigatório")

    cache_key = f"multi:{'|'.join(sorted(urls))}"
    cached = await cache.get(cache_key)
    if cached:
        return {**cached, "daCache": True}

    try:
        result = await run_multi_url_audit(urls)
        await cache.set(cache_key, result)
        return result
    except Exception as e:
        logger.exception("Error running multi-url audit")
        raise HTTPException(status_code=500, detail=f"Erro no audit multi-url: {str(e)}")


@app.get("/api/health")
async def api_health():
    return {
        "ok": True,
        "queue": queue.size,
        "pending": queue.pending,
    }


# SPA Fallback
DIST_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../client/dist"))


@app.get("/{path:path}")
async def spa_fallback(path: str):
    if path.startswith("api/"):
        return JSONResponse(status_code=404, content={"error": "Not Found"})

    file_path = os.path.join(DIST_PATH, path)
    if os.path.isfile(file_path):
        return FileResponse(file_path)

    index_file = os.path.join(DIST_PATH, "index.html")
    if os.path.isfile(index_file):
        return FileResponse(index_file)

    return JSONResponse(status_code=404, content={"error": "Frontend not built yet"})
