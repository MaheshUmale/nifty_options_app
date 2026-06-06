import asyncio
from playwright.async_api import async_playwright

async def verify():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto("http://127.0.0.1:8000")

        # Wait for some ticks to arrive
        await asyncio.sleep(10)

        # Take a screenshot of the dashboard in replay mode
        await page.screenshot(path="verification/screenshots/replay_dashboard.png", full_page=True)

        # Check for signal updates
        decision = await page.inner_text("#signal-decision")
        spot = await page.inner_text("#spot-price")
        print(f"Current Replay Spot: {spot}, Decision: {decision}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(verify())
