"""Smoke-test clean checkout and synthetic screenshots; never collect live data."""
import argparse,asyncio
from pathlib import Path
from playwright.async_api import async_playwright
async def main(url,screenshots):
    async with async_playwright() as p:
        b=await p.chromium.launch(channel='chrome',headless=True)
        page=await b.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto(url);await page.locator('#demoToggle').wait_for()
        await page.locator('#demoToggle').click();await page.locator('.card').first.wait_for()
        assert '虚拟数据' in await page.locator('#scope').inner_text()
        assert await page.locator('#period option').count()==1
        if screenshots:screenshots.mkdir(parents=True,exist_ok=True);await page.screenshot(path=str(screenshots/'overview.png'),full_page=True)
        await page.locator('[data-nav="7"]').click();await page.locator('[data-plan]').first.click()
        if screenshots:await page.screenshot(path=str(screenshots/'plan.png'),full_page=True)
        await page.locator('[data-jd-tab="region"]').click()
        if screenshots:await page.screenshot(path=str(screenshots/'region.png'),full_page=True)
        await page.locator('[data-nav="5"]').click();assert await page.locator('#collect').count()==0
        await page.locator('#demoToggle').click();await page.locator('#setupName').wait_for()
        assert await page.locator('#setupName').input_value()==''
        assert await page.locator('#collect').count()==1
        if screenshots:await page.screenshot(path=str(screenshots/'setup.png'),full_page=True)
        await page.set_viewport_size({'width':390,'height':844})
        assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert not errors,errors
        await b.close()
    print('PASS clean setup, demo14, plan tabs, collection isolation, mobile, screenshots')
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:5194');parser.add_argument('--screenshots',type=Path);a=parser.parse_args();asyncio.run(main(a.url,a.screenshots))
