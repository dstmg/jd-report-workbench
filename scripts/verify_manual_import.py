"""Isolated browser acceptance with synthetic CSV; never writes merchant data."""
import asyncio, json, shutil, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path
from playwright.async_api import async_playwright
from test_manual_import import ManualImport

async def main():
    root=Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as temporary:
        target=Path(temporary)
        for folder in ('scripts','web'):
            shutil.copytree(root/folder,target/folder,ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copy2(root/'report_catalog.json',target/'report_catalog.json')
        fixture=ManualImport();fixture.setUp()
        try:
            request=fixture.request();plan_request=fixture.request('计划')
        finally:fixture.tearDown()
        process=subprocess.Popen([sys.executable,str(target/'scripts/workbench_server.py'),'--port','5196'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            for _ in range(50):
                try:urllib.request.urlopen('http://127.0.0.1:5196/api/data');break
                except OSError:time.sleep(.1)
            async with async_playwright() as p:
                browser=await p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
                try:
                    page=await browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    await page.goto('http://127.0.0.1:5196/')
                    await page.locator('#importFiles').wait_for()
                    await page.locator('#collect').click()
                    await page.locator('#jobActionMessage').filter(has_text='请先人工核对登录').wait_for()
                    await page.wait_for_timeout(2800)
                    assert '请先人工核对登录' in await page.locator('#jobActionMessage').inner_text()
                    assert await page.locator('#collectScope option').count()==3
                    await page.locator('#collectScope').select_option('analysis')
                    assert await page.locator('#collectScope').input_value()=='analysis'
                    config=await page.evaluate("async()=>{let r=await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({account:'演示账户',account_id:'123'})});return {status:r.status,body:await r.json()}}")
                    assert config['status']==200,config
                    import base64
                    await page.locator('#importStart').fill(request['start']);await page.locator('#importEnd').fill(request['end'])
                    await page.locator('#importFiles').set_input_files({'name':request['files'][0]['name'],'mimeType':'text/csv','buffer':base64.b64decode(request['files'][0]['content'])})
                    await page.locator('#previewImport').click();await page.locator('[data-import-index]').wait_for()
                    await page.locator('#importConfirmed').check();await page.locator('#confirmImport').click()
                    await page.locator('#importMessage').filter(has_text='新增1份').wait_for()
                    await page.locator('[data-nav="0"]').click();assert '13 份缺失' in await page.locator('#content').inner_text()
                    await page.locator('[data-nav="6"]').click();assert '尚无已导入报表' in await page.locator('#content').inner_text()
                    await page.locator('[data-nav="7"]').click();assert '计划报表尚未采集或导入' in await page.locator('#content').inner_text()
                    await page.locator('[data-nav="5"]').click()
                    await page.locator('#importFiles').set_input_files({'name':plan_request['files'][0]['name'],'mimeType':'text/csv','buffer':base64.b64decode(plan_request['files'][0]['content'])})
                    await page.locator('#previewImport').click();await page.locator('[data-import-index]').wait_for()
                    await page.locator('#importConfirmed').check();await page.locator('#confirmImport').click()
                    await page.locator('#importMessage').filter(has_text='新增1份').wait_for()
                    await page.locator('[data-nav="7"]').click();await page.locator('[data-plan]').first.click()
                    await page.locator('[data-jd-tab="region"]').click();assert '效果报表/地域尚未采集或导入' in await page.locator('#content').inner_text()
                    await page.locator('[data-jd-tab="terms"]').click();assert '账户报表/关键词尚未采集或导入' in await page.locator('#content').inner_text()
                    await page.locator('[data-jd-tab="attention"]').click();assert '未导入' in await page.locator('#content').inner_text()
                    assert not errors,errors
                    print('Manual import UI passed: preview, confirm, partial coverage, missing effect report; no page errors')
                finally:await browser.close()
        finally:process.terminate();process.wait(timeout=10)
if __name__=='__main__':asyncio.run(main())
