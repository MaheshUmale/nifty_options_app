import asyncio
from playwright.async_api import async_playwright
import time

async def capture():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto("http://127.0.0.1:8000")

        print("Replaying... waiting for trades...")
        # Replay should take 126 seconds total. Let's wait for most of it.
        for i in range(13):
            await asyncio.sleep(10)
            decision = await page.inner_text("#signal-decision")
            spot = await page.inner_text("#spot-price")
            print(f"Time {i*10}s: Spot {spot}, Decision {decision}")

            if "GO" in decision:
                 await page.screenshot(path=f"verification/screenshots/replay_trade_{i}.png", full_page=True)

        await page.screenshot(path="verification/screenshots/replay_final.png", full_page=True)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(capture())
