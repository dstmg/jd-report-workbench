"""Synthetic native-browser checks; no merchant page, login or report submission."""
import asyncio,json,time,unittest
from pathlib import Path
from playwright.async_api import async_playwright
from report_ui import click,UIStateError,Requests
from collect_batch import submit
import collect_batch

class FakeJournal:
    def __init__(self):self.identity={'family':'账户报表','dimension':'计划'};self.data={'state':'pending'}
    def save(self,**changes):self.data.update(changes)

class NativeUI(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.previous_dates=(collect_batch.START,collect_batch.END)
        collect_batch.START='2026-10-07';collect_batch.END='2026-10-13'
        self.p=await async_playwright().start()
        self.browser=await self.p.chromium.launch(channel='chrome',headless=True)
        self.page=await self.browser.new_page(viewport={'width':900,'height':700})
    async def asyncTearDown(self):
        collect_batch.START,collect_batch.END=self.previous_dates
        await self.browser.close();await self.p.stop()
    async def test_occluded_raf_and_moving_control(self):
        await self.page.set_content('''<button id="target" style="position:absolute;left:40px;top:50px" onclick="this.dataset.clicks=Number(this.dataset.clicks||0)+1">目标</button>
        <script>window.requestAnimationFrame=()=>0;let n=0;const timer=setInterval(()=>{target.style.left=(40+(++n)*5)+'px';if(n===5)clearInterval(timer)},80)</script>''')
        await click(self.page,self.page.locator('#target'),label='运动后的目标')
        self.assertEqual(await self.page.locator('#target').get_attribute('data-clicks'),'1')
    async def test_blocked_control_is_never_clicked(self):
        await self.page.set_content('''<button id="target" style="position:absolute;left:40px;top:50px" onclick="this.dataset.clicked='yes'">目标</button><div style="position:absolute;inset:0;z-index:20;background:white">遮挡</div>''')
        with self.assertRaises(UIStateError):await click(self.page,self.page.locator('#target'),label='被挡住',timeout=0.6)
        self.assertIsNone(await self.page.locator('#target').get_attribute('data-clicked'))
    async def test_nested_frame_waits_for_parent_overlay(self):
        await self.page.set_content('''<iframe id="inner" style="position:absolute;left:130px;top:160px;width:400px;height:220px" srcdoc="<button id='target' style='margin:30px' onclick=&quot;this.dataset.clicked='yes'&quot;>目标</button>"></iframe><div id="cover" style="position:absolute;left:120px;top:150px;width:430px;height:250px;z-index:20;background:white">遮挡</div><script>setTimeout(()=>cover.remove(),500)</script>''')
        element=await self.page.locator('#inner').element_handle()
        frame=await element.content_frame()
        await click(frame,frame.locator('#target'),label='嵌套目标')
        self.assertEqual(await frame.locator('#target').get_attribute('data-clicked'),'yes')
    async def test_waits_for_fetch_completion_and_table_refresh(self):
        await self.page.set_content('<table><tbody><tr><td>汇总1条数据</td></tr></tbody></table>')
        tracker=Requests(self.page)
        async def respond(route):
            await asyncio.sleep(0.4)
            await route.fulfill(status=200,headers={'Access-Control-Allow-Origin':'*'},body='ok')
        await self.page.route('https://fixture.invalid/data',respond)
        started=time.monotonic()
        await self.page.evaluate('()=>{fetch("https://fixture.invalid/data").then(()=>document.querySelector("td").innerText="汇总2条数据")}')
        await tracker.idle()
        self.assertGreaterEqual(time.monotonic()-started,0.8)
        self.assertEqual(await self.page.locator('td').inner_text(),'汇总2条数据')
        tracker.close()
    async def submission_fixture(self,redirect=False):
        name='Demo_报表中心_计划_30天_下单_不含赠品_成交订单_20261007_20261013'
        body=f'''<button title="下载报表" onclick="popup.style.display='block'">导出</button>
        <div id="popup" style="display:none"><input placeholder="默认下载列表名称" value="{name}"><button onclick="generate()">开始生成</button></div>
        <div id="receipt" style="display:none;position:absolute;left:80px;top:180px;padding:25px;background:white;border:1px solid black"><p>{name}</p><p>正在生成, 3秒后跳转至 下载列表</p><button onclick="clearTimeout(window.timer);receipt.style.display='none';window.acknowledged=1">知道了</button></div>
        <script>window.generated=0;window.acknowledged=0;function generate(){{window.generated++;popup.style.display='none';
        {'window.timer=setTimeout(()=>location.hash="/download",200);' if redirect else 'receipt.style.display="block";window.timer=setTimeout(()=>location.hash="/download",3000);'}
        }}</script>'''
        await self.page.set_content(body)
        return name
    async def test_submit_confirms_name_and_cancels_countdown(self):
        name=await self.submission_fixture();journal=FakeJournal()
        redirected=await submit(self.page,journal,'pilot')
        self.assertFalse(redirected)
        self.assertEqual(journal.data['state'],'submitted')
        self.assertEqual(journal.data['backend_name_prefix'],name)
        self.assertTrue(journal.data['submit_started_at'])
        self.assertEqual(await self.page.evaluate('window.generated'),1)
        self.assertEqual(await self.page.evaluate('window.acknowledged'),1)
    async def test_auto_redirect_never_replays_the_submit(self):
        await self.submission_fixture(redirect=True);journal=FakeJournal()
        redirected=await submit(self.page,journal,'pilot')
        self.assertTrue(redirected)
        self.assertEqual(journal.data['state'],'submitting')
        self.assertTrue(journal.data['redirect_detected'])
        self.assertEqual(await self.page.evaluate('window.generated'),1)

if __name__=='__main__':unittest.main()
