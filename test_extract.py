import asyncio
import sys
import logging
logging.basicConfig(level=logging.DEBUG)
sys.path.append("C:/PROGRAMATION/VF-TeS/server")

from services.browser import browser_manager
from services.crawler_service import extract_links_with_playwright

async def run():
    await browser_manager.start()
    
    active_pages = []
    pages_lock = asyncio.Lock()
    stop_event = asyncio.Event()
    
    links = await extract_links_with_playwright(
        "https://www.alenquer.pt",
        active_pages,
        pages_lock,
        stop_event
    )
    
    print("EXTRACTED LINKS:", len(links))
    print(links[:5])
    await browser_manager.close()

if __name__ == "__main__":
    asyncio.run(run())
