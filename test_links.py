import asyncio
from playwright.async_api import async_playwright
import sys
sys.path.append("C:/PROGRAMATION/VF-TeS")
from server.services.crawler_service import JS_EXTRACT_LINKS

async def run():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        c = await b.new_context()
        pg = await c.new_page()
        await pg.goto('https://www.alenquer.pt')
        await asyncio.sleep(2)
        links = await pg.evaluate(JS_EXTRACT_LINKS)
        print('Links found:', len(links))
        print(links[:5])
        await b.close()

if __name__ == "__main__":
    asyncio.run(run())
