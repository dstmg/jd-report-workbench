"""Set and read back JD report filters without toggling confirmed state."""
import re
from datetime import date
from report_ui import click,until,checked,UIStateError

async def policy(surface):
    button=surface.locator('button.jad-select-radios-btn,button.jad-pro-select-radios-btn')
    expected='30天/下单/不含赠品/成交订单'
    async def value():return (await button.inner_text()).strip()
    if await value()==expected:return {'label':expected,'changed':False}
    await click(surface,button,label='归因口径菜单')
    for text in ['30天','下单','不含赠品','成交订单']:
        label=surface.locator('label.jad-radio-wrapper:visible').filter(has_text=re.compile(r'^\s*'+text+r'\s*$'))
        await until(label.count,lambda n:n==1,label=text+'选项加载')
        control=label.locator('input[type="radio"]')
        if not await control.is_checked():await click(surface,label,label=text)
        await checked(control,label=text+'选中')
    await click(surface,button,label='关闭归因菜单')
    actual=await until(value,lambda v:v==expected,label='归因口径读回',stable=3)
    return {'label':actual,'changed':True}

async def date_values(surface,effect):
    if effect:
        value=await surface.get_by_placeholder('双日历选择日期',exact=True).input_value()
        return re.findall(r'\d{4}-\d{2}-\d{2}',value)
    return [await surface.get_by_placeholder(x,exact=True).input_value() for x in ['开始日期','结束日期']]

async def calendars(surface):
    results=[]
    for css in ['.jad-date-picker-content-left:visible','.jad-date-picker-content-right:visible']:
        pane=surface.locator(css).filter(has=surface.locator('.jad-date-picker-ctrl'))
        if await pane.count()==1:
            header=await pane.locator('.jad-date-picker-ctrl').inner_text()
            match=re.search(r'(\d{4})年\s*(\d{1,2})月',header)
            if match:results.append((pane,(int(match[1]),int(match[2]))))
    return results

async def pick_day(surface,target):
    month=(target.year,target.month)
    for _ in range(120):
        panes=await calendars(surface)
        if not panes:raise UIStateError('日历月份没有加载')
        matching=[pane for pane,ym in panes if ym==month]
        if matching:
            pane=matching[0]
            cell=pane.locator('.jad-date-picker-cell:not(.jad-date-picker-cell-prev-month):not(.jad-date-picker-cell-next-month)').filter(has=surface.locator('em',has_text=re.compile('^'+str(target.day)+'$')))
            if 'disabled' in (await cell.get_attribute('class') or ''):raise UIStateError('平台不允许选择日期 '+str(target))
            await click(surface,cell,label='日期 '+str(target));return
        before=[ym for _,ym in panes]
        direction='prev' if month<min(before) else 'next'
        arrow=surface.locator('.jad-date-picker-'+direction+'-btn-arrow:visible')
        await click(surface,arrow,label='日历翻月')
        async def months():return [ym for _,ym in await calendars(surface)]
        await until(months,lambda x:x and x!=before,label='月份切换',stable=3)
    raise UIStateError('日期超出本次允许的翻月范围')

async def dates(surface,start,end,*,effect=False):
    expected=[start,end]
    if date.fromisoformat(start)>date.fromisoformat(end):raise ValueError('开始日期不能晚于结束日期')
    if await date_values(surface,effect)==expected:return expected
    field=surface.get_by_placeholder('双日历选择日期' if effect else '开始日期',exact=True)
    if not await calendars(surface):await click(surface,field,label='打开日期范围')
    await until(lambda:calendar_months(surface),lambda v:bool(v),label='日期菜单月份加载',stable=3)
    await pick_day(surface,date.fromisoformat(start))
    # Wait for the calendar DOM to finish its first selection before the second click.
    async def selection():
        return await surface.locator('.jad-date-picker-cell-start:visible').evaluate_all('es=>es.map(e=>({text:e.innerText,class:e.className}))')
    await until(selection,lambda xs:any(x['text'].strip()==str(date.fromisoformat(start).day) for x in xs),label='起始日期选中',stable=3)
    await pick_day(surface,date.fromisoformat(end))
    actual=await until(lambda:date_values(surface,effect),lambda v:v==expected,label='日期范围读回',stable=3)
    await until(lambda:calendar_months(surface),lambda xs:not xs,label='日期菜单关闭')
    return actual

async def calendar_months(surface):return [ym for _,ym in await calendars(surface)]

async def account_goals(surface):
    root=surface.locator('.jad-cascader')
    if await root.count()!=1:raise UIStateError('营销目标控件不唯一')
    all_item=surface.locator('li.jad-cascader-menu-item').filter(has_text=re.compile(r'^\s*全部\s*$'))
    if not await surface.locator('.jad-cascader-menus:visible').count():
        await click(surface,root.locator('.relative-hover'),label='打开营销目标')
    all_box=all_item.locator('[class*="jad-cascader-checkbox"]')
    async def state():return await all_box.get_attribute('class')
    if await state()!='jad-cascader-checkbox-checked':await click(surface,all_box,label='全部营销目标')
    await until(state,lambda v:v=='jad-cascader-checkbox-checked',label='全选读回',stable=3)
    label=(await root.locator('.jad-cascader-label:visible').inner_text()).strip()
    # Close on a static label outside the menu, never on its selected-value label.
    await click(surface,surface.get_by_text('账号',exact=True),label='关闭营销目标菜单')
    await until(lambda:surface.locator('.jad-cascader-menus:visible').count(),lambda n:n==0,label='营销目标菜单关闭')
    await until(state,lambda v:v=='jad-cascader-checkbox-checked',label='关闭后全选保留',stable=3)
    return {'all_checked':True,'label':label,'closed_checked':True}

async def effect_goals(surface,*,brand=False):
    if brand:
        tab=(await surface.locator('.jad-tabs-nav-tab-active').inner_text()).strip()
        if tab!='品牌拦截' or '品牌追击-关键词' not in await surface.locator('body').inner_text():raise UIStateError('品牌固定场景不符')
        return {'scope':'平台固定品牌追击-关键词','all_available_targets':True}
    chip=surface.get_by_text(re.compile(r'^已选\d+个$|^请选择$')).filter(visible=True)
    await click(surface,chip,label='效果营销目标')
    for group in ['商品','店铺','活动','内容']:
        label=surface.locator('label.check-item:visible').filter(has=surface.locator('input[value="'+group+'"]'))
        control=label.locator('input[type="checkbox"]')
        if not await control.is_checked():await click(surface,label,label='全选'+group)
        await checked(control,label=group+'全选')
        if await label.locator('.jad-checkbox-indeterminate').count():raise UIStateError(group+'仍为部分选中')
    panel=surface.locator('.jad-popover-poper:visible').filter(has=surface.locator('input[value="商品"]'))
    await click(surface,panel.locator('button:visible').filter(has_text=re.compile(r'^\s*确定\s*$')),label='确认全部营销目标')
    await until(panel.count,lambda n:n==0,label='营销目标确认完成')
    return {'all_available_targets':True,'chip':(await chip.inner_text()).strip()}
