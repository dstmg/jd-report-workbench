"""Entirely synthetic, generated from public column names. No merchant input."""
import json
from datetime import datetime,timedelta
from pathlib import Path
def build_demo():
    root=Path(__file__).resolve().parents[1]
    catalog=json.loads((root/'report_catalog.json').read_text(encoding='utf-8'))
    # UTC+8 arithmetic avoids an optional tzdata dependency on Windows.
    from datetime import timezone
    end=(datetime.now(timezone(timedelta(hours=8)))-timedelta(days=1)).date();start=end-timedelta(days=6)
    reports=[]
    for entry in catalog:
        fields=entry['fields'];daily=entry['family']=='账户报表';rows=[]
        for index in range(21 if daily else 9):
            plan=index%3;day=start+timedelta(days=index//3 if daily else 0)
            spend=round(45+plan*25+(index//3)*3.2,2);roi=[1.8,3.6,2.7][plan];revenue=round(spend*roi,2)
            direct=round(revenue*.75,2);clicks=40+index;orders=3+plan;impressions=clicks*35
            values={'下单时间':day.strftime('%Y%m%d'),'日期':f'{start:%Y%m%d}~{end:%Y%m%d}','计划ID':str(900001+plan),'推广计划':['演示计划·日用推广','演示计划·新品测试','演示计划·品牌词'][plan],'单元ID':str(910001+plan),'推广单元':'演示单元'+str(plan+1),'推广创意':'演示创意'+str(plan+1),'花费':spend,'总订单金额':revenue,'直接订单金额':direct,'间接订单金额':round(revenue-direct,2),'直接订单行':orders-1,'间接订单行':1,'总订单行':orders,'投产比':roi,'展现数':impressions,'点击数':clicks,'点击率(%)':round(100/35,2),'转化率(%)':round(orders/clicks*100,2),'平均点击成本':round(spend/clicks,2),'平均订单成本':round(spend/orders,2),'千次展现成本':round(spend/impressions*1000,2),'总加购数':12+plan,'直接加购数':8+plan,'间接加购数':4,'加购成本':round(spend/(12+plan),2),'加购率(%)':round((12+plan)/clicks*100,2),'关键词':['日用品','新品推荐','品牌词'][plan],'搜索词':['便携日用品','新品家居用品','品牌日用品'][plan],'关键词类型':'演示类型','购买类型':'演示匹配','省/直辖市':['广东省','江苏省','浙江省'][index%3],'跟单SKU ID':str(920001+plan),'跟单SKU名称':'演示成交商品'+str(plan+1),'人群名称':'演示人群'+str(plan+1),'流量包/资源位':'演示流量包'+str(plan+1)}
            row={key:str(values.get(key,('演示'+key+str(plan+1)) if any(t in key for t in ['名称','推广','关键词','类型','品牌','品类','匹配']) else (str(930001+plan) if 'id' in key.lower() else '0'))) for key in fields}
            rows.append(row)
        reports.append({'key':entry['family']+'/'+entry['dimension'],'family':entry['family'],'dimension':entry['dimension'],'daily':daily,'fields':fields,'rows':rows,'file':'演示生成·非真实报表','sha256':'synthetic','checks':0,'identity':{'account':'演示账户（全部为虚拟数据）','account_id':'DEMO'}})
    return {'demo':True,'periods':[{'key':f'{start}_{end}','start':str(start),'end':str(end),'reports':reports}],'notice':'全部为程序生成的演示数据，不代表任何真实商家，不参与采集或通知。'}
