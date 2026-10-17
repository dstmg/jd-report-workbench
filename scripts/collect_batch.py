"""Generate the requested dimensions first, then download and validate together."""
import asyncio,json,re,shutil,sys,unicodedata
from pathlib import Path
from datetime import datetime
from urllib.parse import urlsplit
from playwright.async_api import async_playwright,Error as BrowserError
from launch_browser import owned
from collection_state import Journal
from report_validation import validate
import report_filters
from report_download import files as native_files,wait_file,creation_matches
from report_ui import click as ui_click,active_tab,idle_table,Requests,until
ROOT=Path(__file__).resolve().parents[1]
START='';END=''
ACCOUNT='';ACCOUNT_ID=''
ACCOUNT_TABS=['账户','计划','单元','创意','关键词','商品定向','人群','流量包']
EFFECT_TABS=[('搜索词','搜索词'),('地域','地域'),('商品定向','商品定向'),('品类','品类'),('商品','商品'),('品牌追击','品牌拦截')]

def account_ids(text):
    normalized=unicodedata.normalize('NFKC',text)
    normalized=re.sub('[\u200b\u200c\u200d\ufeff]','',normalized)
    return set(re.findall(r'(?:账户|账号)\s*ID\s*:\s*([0-9]+)(?![0-9])',normalized,re.I))

async def verify_account(page):
    observed=set()
    for _ in range(20):
        observed=account_ids(await page.locator('body').inner_text())
        if observed=={ACCOUNT_ID}:return
        if observed:break
        await asyncio.sleep(.5)
    if not observed:raise RuntimeError('无法读取页面账户ID：请确认专用Chrome已登录，并进入快车账户报表页；若账户ID仅在账户菜单中显示，请保留诊断并反馈，未生成报表')
    if len(observed)>1:raise RuntimeError('页面显示多个账户ID，无法唯一核验当前账户，停止采集；请核对当前账户菜单')
    raise RuntimeError(f'账号不符：配置账户ID为{ACCOUNT_ID}，页面读到{next(iter(observed))}；请核对专用Chrome当前账户，未生成本份报表')
def identity(family,dimension,daily=True):
    result={'account':ACCOUNT,'account_id':ACCOUNT_ID,'family':family,'dimension':dimension,'start':START,'end':END,'window':30,'attribution':'下单','gifts':False,'order_state':'成交订单','daily':daily,'marketing_targets':'all'}
    if family=='账户报表' and dimension in ['创意','关键词','商品定向','人群','流量包']:result['collector_revision']=2
    if family=='账户报表' and dimension=='关键词':result['collector_revision']=3
    if family=='效果报表' and dimension=='品牌追击':result['marketing_targets']='品牌追击-关键词（平台固定）'
    return result
def name_for(family,dimension):return f'工作台{family}_{dimension}_30下单_{START.replace("-","")}_{END.replace("-","")}'+('_修正' if family=='账户报表' and dimension in ['创意','关键词','商品定向','人群','流量包'] else '')
async def inventory(page):
    tracker=Requests(page)
    try:
        url=(ROOT/'data/download-list-url.txt').read_text(encoding='utf-8')
        if page.url==url:await page.reload(wait_until='domcontentloaded',timeout=60000)
        else:await page.goto(url,wait_until='domcontentloaded',timeout=60000)
        await until(page.get_by_text('批量下载',exact=True).count,lambda n:n==1,label='下载管理页面加载')
        await tracker.idle()
        size=page.locator('button').filter(has_text=re.compile(r'\d+条/页'))
        if (await size.inner_text()).strip()!='100条/页':
            await ui_click(page,size,label='下载列表分页菜单')
            await ui_click(page,page.get_by_text('100 条',exact=True),label='每页100条')
        await until(size.inner_text,lambda text:text.strip()=='100条/页',label='分页数量读回',stable=3)
        await tracker.idle();table=await idle_table(page,downloads=True)
        text=await page.locator('body').inner_text()
        if not re.search(r'共\d+条',text) and table['rows']!=0:raise RuntimeError('无法读回任务数量')
        return text
    finally:tracker.close()
async def policy(page):return await report_filters.policy(page)
async def dates(page):return await report_filters.dates(page,START,END)
async def account_goals(page):return await report_filters.account_goals(page)
async def submit(page,journal,name):
    root=page if hasattr(page,'main_frame') else page.page
    realm=urlsplit(root.url)
    def redirected():
        current=urlsplit(root.url)
        return (current.scheme,current.netloc,current.path)==(realm.scheme,realm.netloc,realm.path) and current.fragment.split('?')[0]=='/download'
    acknowledgement=page.get_by_text('知道了',exact=True).filter(visible=True)
    await until(acknowledgement.count,lambda n:n==0,label='上次生成提示关闭')
    await ui_click(page,page.locator('button[title="下载报表"],button.download-report-icon'),label='打开生成报表')
    start=page.get_by_text('开始生成',exact=True).filter(visible=True)
    if await page.get_by_placeholder('默认下载列表名称',exact=True).count():field=page.get_by_placeholder('默认下载列表名称',exact=True)
    else:field=start.locator('..').locator('input')
    backend_name=await until(field.input_value,lambda value:journal.identity['dimension'] in value,label='报表名称加载',stable=3)
    # Preserve JD's canonical name: its blur handler restores the default.
    # Match the backend task by this readback plus date, creation time and schema.
    if journal.identity['dimension'] not in backend_name:raise RuntimeError('默认报表名维度不符')
    period=START.replace('-','')+'_'+END.replace('-','')
    if journal.identity['family']=='账户报表' and (period not in backend_name or '30天_下单_不含赠品_成交订单' not in backend_name):raise RuntimeError('默认报表名口径日期不符')
    journal.save(state='configured',name=name,backend_name_prefix=backend_name)
    def commit():journal.save(state='submitting',submit_started_at=datetime.now().isoformat(),submitted_at=datetime.now().isoformat())
    await ui_click(page,start,label='提交生成任务',before=commit)
    async def receipt():
        if redirected():return {'kind':'redirect'}
        if await acknowledgement.count()!=1:return {'kind':'waiting'}
        text=await acknowledgement.evaluate('e=>{for(let p=e;p;p=p.parentElement){if(p.innerText.includes("正在生成"))return p.innerText}return ""}')
        return {'kind':'confirmed' if backend_name in text and '正在生成' in text else 'waiting','text':text}
    outcome=await until(receipt,lambda r:r['kind'] in ('confirmed','redirect'),label='生成结果确认',timeout=10)
    if outcome['kind']=='redirect':
        journal.save(redirect_detected=True,submit_response_finished_at=datetime.now().isoformat())
        print('已跳转，等待下载列表核对任务',name,flush=True);return True
    journal.save(state='submitted',submitted_at=datetime.now().isoformat(),submit_dialog_visible=outcome['text'])
    try:await ui_click(page,acknowledgement,label='确认生成提示',timeout=3)
    except (BrowserError,RuntimeError):
        if not redirected():raise
        journal.save(redirect_detected=True)
    print('已生成任务',name,flush=True)
    return redirected()
async def download_one(page,journal,name):
    if journal.data.get('file'):
        journal.recover_file();return
    effective_name=journal.data.get('backend_name_prefix',name)
    row=page.locator('tr').filter(has_text=effective_name)
    if await row.count()==0:await inventory(page)
    if await row.count()==0 and journal.identity['family']=='效果报表' and journal.identity['dimension'] in ['地域','品类']:
        prefix='京准通-报表中心-'+journal.identity['dimension']+'效果报表报表_'+START.replace('-','')+'_'+END.replace('-','')
        candidates=page.locator('tr').filter(has_text=prefix)
        if await candidates.count()!=1:raise RuntimeError('平台默认名恢复任务不唯一')
        candidate_text=await candidates.inner_text()
        match=re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}',candidate_text)
        if not match or abs((datetime.fromisoformat(match.group())-datetime.fromisoformat(journal.data['submitted_at'])).total_seconds())>5:raise RuntimeError('默认名任务创建时间不符')
        row=candidates;effective_name=prefix
        journal.save(backend_name_prefix=prefix,name_reconciliation='维度、日期、创建时间与已保存 UI 口径匹配')
    if await row.count()==0:await page.wait_for_function('(name)=>document.body.innerText.includes(name)',arg=effective_name,polling=200,timeout=30000)
    if await row.count()>1:
        matches=[]
        for candidate in await row.all():
            text=await candidate.inner_text()
            created=re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}',text)
            if created and creation_matches(text,journal.data.get('submit_started_at',journal.data['submitted_at']),journal.data.get('submit_response_finished_at',journal.data['submitted_at'])):matches.append(candidate)
        if len(matches)!=1:raise RuntimeError('同名任务无法按创建时间区分')
        row=matches[0]
    if await row.count()!=1:raise RuntimeError('任务不唯一 '+name)
    await row.get_by_text('报表已生成',exact=True).wait_for(state='attached',timeout=60000)
    text=await row.inner_text()
    if START not in text or END not in text:raise RuntimeError('下载行日期不符')
    if not creation_matches(text,journal.data.get('submit_started_at',journal.data['submitted_at']),journal.data.get('submit_response_finished_at',journal.data['submitted_at'])):raise RuntimeError('下载行创建时间不符')
    if journal.data['state']=='submitting':journal.save(state='submitted',reconciled_row=text)
    titles=[x.strip() for x in await row.locator('td').all_text_contents() if x.strip().startswith(effective_name)]
    if len(titles)!=1:raise RuntimeError('任务完整文件名不唯一')
    title=re.sub(r'\s+','',titles[0])
    if not title.startswith(effective_name) or '/' in title or '\\' in title:raise RuntimeError('文件名不合法')
    # Effect exports append their backend creation time to the user-entered name.
    directory=Path.home()/'Downloads'
    if journal.data['state']=='submitted':
        baseline=native_files(directory,title)
        def commit_download():
            journal.save(state='downloading',download_row=text,clicked_at=datetime.now().timestamp(),download_baseline=baseline,download_title=title)
        await ui_click(page,row.get_by_text('下载',exact=True),label='下载对应报表',before=commit_download)
    elif journal.data['state'] not in ['downloading','saving']:
        raise RuntimeError('提交尚未确认，不能下载或重新生成')
    if not journal.data.get('clicked_at'):raise RuntimeError('缺少原下载时间，停止人工核对')
    source=await wait_file(directory,title,journal.data.get('download_baseline',{}),journal.data['clicked_at'])
    result=validate(source,START,END)
    if journal.data.get('expected_rows') is not None and result['rows']!=journal.data['expected_rows']:raise RuntimeError('下载行数与生成前后台显示不符')
    catalog=json.loads((ROOT/'report_catalog.json').read_text(encoding='utf-8'))
    schema=next(x for x in catalog if x['family']==journal.identity['family'] and x['dimension']==journal.identity['dimension'])
    distinguishing=set(schema['fields'])-{'下单时间','日期'}
    missing=distinguishing-set(result['fields'])
    if missing:raise RuntimeError('样本字段缺失 '+str(missing))
    filename='report.csv'
    journal.save(state='saving',original_filename=source.name)
    temporary=journal.directory/(filename+'.part')
    shutil.copy2(source,temporary)
    copied=validate(temporary,START,END)
    if result['sha256']!=copied['sha256']:raise RuntimeError('归档哈希不符')
    temporary.replace(journal.directory/filename)
    journal.save(state='validated',file=filename,sha256=result['sha256'],validation=result)
    print('已下载校验',journal.identity['family'],journal.identity['dimension'],result['rows'],'行',len(result['fields']),'字段',flush=True)
async def effect_dates(frame):return await report_filters.dates(frame,START,END,effect=True)
async def effect_goals(frame,brand=False):return await report_filters.effect_goals(frame,brand=brand)
async def generate_effects(page,listing,existing,pending,tracker,dimensions=None):
    tabs=[pair for pair in EFFECT_TABS if dimensions is None or pair[0] in dimensions]
    if not tabs:return
    await page.bring_to_front()
    if urlsplit(page.url).fragment.split('?')[0]=='/download':
        await page.goto('https://jzt.jd.com/report/index.html/#/rtb/basic/account?objective=rtb&activeTab=account',wait_until='domcontentloaded')
        await active_tab(page,'账户');await tracker.idle()
    await ui_click(page,page.locator('span.child-label:visible').filter(has_text=re.compile('^效果报表$')),label='进入效果报表')
    await tracker.idle()
    effects_url=page.url
    frame=None
    for _ in range(30):
        frames=[f for f in page.frames if urlsplit(f.url).path=='/custom-report/']
        if len(frames)==1 and await frames[0].locator('.jad-tabs-nav-tab-no-icon').count():frame=frames[0];break
        await asyncio.sleep(1)
    if frame is None:raise RuntimeError('效果报表框架未加载')
    for dimension,tab in tabs:
        ident=identity('效果报表',dimension,False);name=name_for('效果报表',dimension)
        with Journal(ROOT,ident) as journal:
            if journal.data.get('file'):journal.recover_file();continue
            if journal.data['state'] in ['submitted','downloading','saving'] or (journal.data['state']=='submitting' and journal.data.get('redirect_detected')):pending.append((ident,name));continue
            journal.recover_file()
            if name in existing:raise RuntimeError('同名效果任务无本地记录，停止核对')
            if frame.is_detached() or urlsplit(page.url).fragment.split('?')[0]=='/download':
                await page.goto(effects_url,wait_until='domcontentloaded');await tracker.idle()
                async def frames_ready():return [f for f in page.frames if urlsplit(f.url).path=='/custom-report/']
                frame=(await until(frames_ready,lambda fs:len(fs)==1,label='恢复效果页面'))[0]
            await frame.evaluate('()=>{document.scrollingElement.scrollTop=0;const t=document.querySelector(".jad-tabs-nav-tab-active");for(let e=t;e;e=e.parentElement){if(e.scrollTop)e.scrollTop=0;}}')
            ancestor=frame
            while ancestor.parent_frame:
                element=await ancestor.frame_element()
                await element.evaluate('e=>{for(let x=e;x;x=x.parentElement){if(x.scrollTop)x.scrollTop=0;}}')
                ancestor=ancestor.parent_frame
            await ui_click(frame,frame.locator('.jad-tabs-nav-tab').filter(has=frame.get_by_text(tab,exact=True)),label='效果页签'+tab)
            await active_tab(frame,tab);await tracker.idle()
            readback={'selected_tab':tab,'policy':await policy(frame),'dates':await effect_dates(frame),'goals':await effect_goals(frame,dimension=='品牌追击'),'daily':False,'daily_note':'效果页面未提供分日报告勾选；本次保留平台区间维度'}
            readback['filters']=await frame.locator('button:visible').all_text_contents()
            await tracker.idle();table=await idle_table(frame,effect=True)
            journal.save(state='configured',readback=readback,expected_rows=table['rows'])
            await submit(frame,journal,name)
            pending.append((ident,name))
async def main(account_tabs=None,effect_dimensions=None):
    if not START or not END or not ACCOUNT_ID:raise ValueError('请从数据管理配置账户与日期，再开始采集')
    account_tabs=ACCOUNT_TABS if account_tabs is None else account_tabs
    effect_dimensions=[dim for dim,_ in EFFECT_TABS] if effect_dimensions is None else effect_dimensions
    specs=[identity('账户报表',tab) for tab in account_tabs]+[identity('效果报表',dim,False) for dim in effect_dimensions]
    complete=True
    for spec in specs:
        with Journal(ROOT,spec) as journal:
            if journal.data.get('state')=='validated' and journal.data.get('file'):journal.recover_file()
            else:complete=False
    if complete:
        print(f'本次{len(specs)}个维度的文件全部重新校验通过，未连接浏览器、未重复生成或下载');return
    record=json.loads((ROOT/'data/browser-launch.json').read_text(encoding='utf-8'))
    if not owned(record):raise RuntimeError('专用浏览器归属不符')
    async with async_playwright() as p:
        b=await p.chromium.connect_over_cdp(f"http://127.0.0.1:{record['port']}",no_defaults=True)
        context=b.contexts[0]
        pages=[x for x in context.pages if '/rtb/' in x.url]
        if not pages and len(context.pages)==1 and '#/download' in context.pages[0].url:
            pages=[context.pages[0]]
            await pages[0].goto('https://jzt.jd.com/report/index.html/#/rtb/basic/account?objective=rtb&activeTab=account',wait_until='domcontentloaded')
        if len(pages)!=1:raise RuntimeError('采集页面不唯一')
        page=pages[0];await page.bring_to_front();await page.set_viewport_size({'width':1600,'height':1000})
        if '/rtb/custom' in page.url:
            await page.goto('https://jzt.jd.com/report/index.html/#/rtb/basic/account?objective=rtb&activeTab=account',wait_until='domcontentloaded')
            await page.locator('.jad-tabs-nav-tab-active').filter(has_text='账户').wait_for(state='attached')
        listing=await context.new_page();await listing.set_viewport_size({'width':1600,'height':1000})
        tracker=Requests(page)
        try:
            existing=await inventory(listing)
            pending=[]
            for tab in account_tabs:
                ident=identity('账户报表',tab);name=name_for('账户报表',tab)
                if ident.get('collector_revision'):
                    old_ident=ident.copy();old_ident.pop('collector_revision')
                    with Journal(ROOT,old_ident) as old:
                        if '/basic/keyword' in old.data.get('readback',{}).get('url',''):
                            old.save(state='invalid_dimension',reason='页面仍停在关键词，排除验收；保留后台任务及原始文件')
                        if tab in ['创意','关键词'] and old.data.get('validation',{}).get('empty'):
                            old.save(state='invalid_scope',reason='同条件后台显示有数据，原空表排除验收；保留原件')
                with Journal(ROOT,ident) as journal:
                    if journal.data.get('file'):
                        journal.recover_file();print('跳过完成',tab,flush=True);continue
                    if journal.data['state'] in ['submitted','downloading','saving']:
                        pending.append((ident,name));continue
                    if journal.data['state']=='submitting':
                        if journal.data.get('redirect_detected'):
                            pending.append((ident,name));continue
                        row=listing.locator('tr').filter(has_text=journal.data.get('backend_name_prefix',name))
                        if await row.count()>1:
                            matching=[candidate for candidate in await row.all() if creation_matches(await candidate.inner_text(),journal.data.get('submit_started_at',journal.data['submitted_at']),journal.data.get('submit_response_finished_at',journal.data['submitted_at']))]
                            if len(matching)!=1:raise RuntimeError('提交不确定且同名任务无法区分')
                            row=matching[0]
                        if await row.count()!=1:raise RuntimeError('提交不确定且后台任务未找到，不重新生成')
                        row_text=await row.inner_text()
                        if START not in row_text or END not in row_text:raise RuntimeError('恢复任务日期不符')
                        created=re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}',row_text)
                        if not created:raise RuntimeError('后台创建时间不可核验')
                        journal.save(state='submitted',submitted_at=created.group(),reconciled_row=row_text)
                        pending.append((ident,name));continue
                    journal.recover_file()
                    if name in existing:raise RuntimeError('同名后台任务无本地确认，停止核对')
                    await page.bring_to_front()
                    if urlsplit(page.url).fragment.split('?')[0]=='/download':
                        await page.goto('https://jzt.jd.com/report/index.html/#/rtb/basic/account?objective=rtb&activeTab=account',wait_until='domcontentloaded')
                        await active_tab(page,'账户');await tracker.idle()
                    old_tab=(await page.locator('.jad-tabs-nav-tab-active').inner_text()).strip();old_url=page.url
                    if old_tab!=tab:await ui_click(page,page.locator('.jad-tabs-nav-tab-no-icon').filter(has_text=re.compile('^'+tab+'$')),label='账户页签'+tab)
                    await active_tab(page,tab)
                    if old_tab!=tab:await page.wait_for_url(lambda url:str(url)!=old_url,timeout=10000)
                    await page.locator('button[title="下载报表"]').wait_for(state='attached')
                    await tracker.idle()
                    await verify_account(page)
                    readback={'policy':await policy(page),'dates':await dates(page),'goals':await account_goals(page),'url':page.url}
                    daily=page.locator('label').filter(has_text=re.compile(r'^\s*分日报告\s*$'))
                    if not await daily.locator('input').is_checked():await ui_click(page,daily,label='分日报告')
                    if not await daily.locator('input').is_checked():raise RuntimeError('分日未勾选')
                    readback['daily']=True
                    await tracker.idle();table=await idle_table(page)
                    expected_rows=table['rows']
                    journal.save(state='configured',readback=readback,expected_rows=expected_rows)
                    await submit(page,journal,name)
                    pending.append((ident,name))
            await generate_effects(page,listing,existing,pending,tracker,effect_dimensions)
            await listing.bring_to_front();await inventory(listing)
            for ident,name in pending:
                with Journal(ROOT,ident) as journal:await download_one(listing,journal,name)
        finally:tracker.close();await listing.close()
if __name__=='__main__':raise SystemExit('请运行 workbench_collect.py 或使用工作台数据管理，不使用固定验收参数')


