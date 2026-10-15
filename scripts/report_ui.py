"""State-based report UI interaction, including occluded Chrome and nested frames.

Only inspect the selected report controls. Never replay an uncertain click.
"""
import asyncio
import json
import time

class Requests:
    """Count in-flight XHR/fetch only; do not read or store URLs, bodies or headers."""
    def __init__(self,page):
        self.page=page;self.pending=set();self.changed=time.monotonic()
        page.on('request',self.start)
        page.on('requestfinished',self.end)
        page.on('requestfailed',self.end)
    def start(self,request):
        if request.resource_type in ('xhr','fetch'):
            self.pending.add(request);self.changed=time.monotonic()
    def end(self,request):
        if request in self.pending:self.pending.discard(request);self.changed=time.monotonic()
    async def idle(self):
        async def read():return {'pending':len(self.pending),'quiet':time.monotonic()-self.changed>=0.8}
        await until(read,lambda s:s['pending']==0 and s['quiet'],label='报表请求完成',timeout=30,stable=3)
    def close(self):
        self.page.remove_listener('request',self.start)
        self.page.remove_listener('requestfinished',self.end)
        self.page.remove_listener('requestfailed',self.end)

class UIStateError(RuntimeError):
    pass

async def ensure_visible(page):
    """Restore the already-owned dedicated window; never create another window."""
    session=await page.context.new_cdp_session(page)
    try:
        info=await session.send('Browser.getWindowForTarget')
        restored=info['bounds']['windowState']=='minimized'
        if restored:
            await session.send('Browser.setWindowBounds',{'windowId':info['windowId'],'bounds':{'windowState':'normal'}})
        await session.send('Page.bringToFront')
    finally:await session.detach()
    if restored:await until(lambda:page.evaluate('document.visibilityState'),lambda v:v=='visible',label='专用 Chrome 恢复可见',timeout=10)

async def until(read, accept, *, label, timeout=15, interval=0.15, stable=1):
    deadline=time.monotonic()+timeout
    previous=None;count=0;last=None
    while time.monotonic()<deadline:
        last=await read()
        if accept(last):
            count=count+1 if last==previous else 1
            if count>=stable:return last
        else:count=0
        previous=last
        await asyncio.sleep(interval)
    raise UIStateError(f'{label}未达到目标状态：{json.dumps(last,ensure_ascii=False,default=lambda obj:type(obj).__name__)}')

async def reveal(surface, locator):
    # Scroll clipping ancestors only. scrollIntoView can move JD's portal first
    # row above its scroll viewport, so it must not run on an already-visible target.
    scroll=r'''e=>{for(let p=e.parentElement;p;p=p.parentElement){
        const s=getComputedStyle(p),r=e.getBoundingClientRect(),v=p.getBoundingClientRect();
        if(/auto|scroll|hidden/.test(s.overflowY) && p.scrollHeight>p.clientHeight){
            if(r.top<v.top+p.clientTop)p.scrollTop-=v.top+p.clientTop-r.top;
            else if(r.bottom>v.top+p.clientTop+p.clientHeight)p.scrollTop+=r.bottom-(v.top+p.clientTop+p.clientHeight);
        }
    }}'''
    await locator.evaluate(scroll)
    frame=surface.main_frame if hasattr(surface,'main_frame') else surface
    while frame.parent_frame:
        element=await frame.frame_element()
        await element.evaluate(scroll)
        frame=frame.parent_frame

async def geometry(surface, locator):
    if await locator.count()!=1:return {'ready':False,'reason':'控件不唯一或未加载'}
    result=await locator.evaluate('''e=>{
        const r=e.getBoundingClientRect(),s=getComputedStyle(e);
        const x=r.x+r.width/2,y=r.y+r.height/2,hit=document.elementFromPoint(x,y);
        let transparent=false;for(let p=e;p;p=p.parentElement){if(Number(getComputedStyle(p).opacity)===0)transparent=true}
        const disabled=e.closest(':disabled,[aria-disabled="true"]') || (e.tagName==='LABEL' && e.querySelector('input:disabled'));
        return {ready:e.isConnected && r.width>0 && r.height>0 && s.display!=="none" && s.visibility==="visible" && !transparent && !disabled && (hit===e || e.contains(hit)),
            rect:[r.x,r.y,r.width,r.height].map(v=>Math.round(v*10)/10),point:[x,y],
            hit:hit?.tagName+":"+hit?.className,transform:s.transform};
    }''')
    if not result['ready']:return result
    frame=surface.main_frame if hasattr(surface,'main_frame') else surface
    point=result['point']
    while frame.parent_frame:
        element=await frame.frame_element()
        mapped=await element.evaluate('''(e,p)=>{
            const r=e.getBoundingClientRect(),sx=r.width/e.offsetWidth,sy=r.height/e.offsetHeight;
            if(!e.offsetWidth || !e.offsetHeight || !r.width || !r.height)return {point:[],clear:false,hit:'FRAME_HIDDEN'};
            const x=r.x+(e.clientLeft+p[0])*sx,y=r.y+(e.clientTop+p[1])*sy;
            const hit=e.ownerDocument.elementFromPoint(x,y);
            return {point:[x,y],clear:hit===e,hit:hit?.tagName+":"+hit?.className};
        }''',point)
        if not mapped['clear']:
            result.update(ready=False,reason='外层页面遮挡',outer_hit=mapped['hit']);return result
        point=mapped['point'];frame=frame.parent_frame
    result['global_point']=[round(x,1) for x in point]
    return result

async def click(surface, locator, *, label, timeout=12, before=None):
    page=surface if hasattr(surface,'main_frame') else surface.page
    await ensure_visible(page)
    await until(locator.count,lambda n:n==1,label=label+'加载',timeout=timeout)
    if not (await geometry(surface,locator))['ready']:await reveal(surface,locator)
    state=await until(lambda:geometry(surface,locator),lambda state:state['ready'],
                label=label+'位置与遮挡',timeout=timeout,stable=3)
    # Native mouse events retain trusted user-event semantics, without Playwright's
    # RAF wait or implicit scroll that can move a portal AFTER our hit test.
    for _ in range(3):
        point=state['global_point'];await page.mouse.move(*point)
        state=await until(lambda:geometry(surface,locator),lambda s:s['ready'],label=label+'悬停后稳定',timeout=timeout,stable=3)
        if state['global_point']==point:
            if before is not None:before()
            await page.mouse.down();await page.mouse.up();return
    raise UIStateError(label+'悬停后仍在移动，未点击')

async def checked(locator, *, label):
    return await until(locator.is_checked,lambda value:value,label=label)

async def active_tab(surface, expected):
    locator=surface.locator('.jad-tabs-nav-tab-active')
    async def read():
        if await locator.count()!=1:return None
        return (await locator.inner_text()).strip()
    return await until(read,lambda value:value==expected,label='当前页签',stable=3)

async def idle_table(surface, *, effect=False, downloads=False, timeout=20):
    # Rows, spinner and visible table summaries must agree and stop changing.
    async def read():
        return await surface.evaluate(r'''downloads=>{
            const visible=e=>{const s=getComputedStyle(e);return e.getClientRects().length && s.display!=="none" && s.visibility!=="hidden"};
            const tables=[...document.querySelectorAll('table')].filter(visible);
            if(!tables.length)return {ready:false};
            const wrappers=tables.map(t=>t.closest('.jad-table') || t.parentElement);
            const busy=[...document.querySelectorAll('.jad-loading,.jad-loading-mask,.jad-table-loading,.jad-spin,.jad-spin-wrapper')].some(e=>visible(e) && wrappers.some(w=>w.contains(e)||e.contains(w)));
            const text=tables.map(t=>t.innerText).join('\n');
            const counts=[...new Set([...(downloads?document.body.innerText:text).matchAll(downloads?/共\s*(\d+)条/g:/汇总(?:共)?\s*(\d+)条(?:数据)?/g)].map(m=>Number(m[1])))];
            const empty=wrappers.some(w=>w.innerText.includes('暂无数据'));
            const rows=tables.flatMap(t=>[...t.querySelectorAll('tbody tr')].map(e=>e.innerText));
            let fingerprint=2166136261;for(const c of rows.join('\n'))fingerprint=Math.imul(fingerprint^c.charCodeAt(0),16777619)>>>0;
            return {ready:!busy && (counts.length===1 || (counts.length===0 && empty)),rows:counts.length===1?counts[0]:(empty?0:null),fingerprint,busy};
        }''',downloads)
    state=await until(read,lambda x:x.get('ready',False),label='报表数据刷新',timeout=timeout,interval=0.3,stable=5)
    return {'rows':state['rows']}
