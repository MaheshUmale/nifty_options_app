import asyncio
from playwright.async_api import async_playwright
import time

async def capture():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto("http://127.0.0.1:8000")

        print("Waiting for GO signal...")
        start_time = time.time()
        while time.time() - start_time < 300: # 5 min timeout
            decision = await page.inner_text("#signal-decision")
            if "GO" in decision:
                print(f"GO Signal Detected! Decision: {decision}")
                await page.screenshot(path="verification/screenshots/replay_go_signal.png", full_page=True)
                break
            await asyncio.sleep(1)
        else:
            print("Timed out waiting for GO signal.")
            await page.screenshot(path="verification/screenshots/replay_timeout.png", full_page=True)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(capture())
