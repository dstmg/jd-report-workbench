"""Explicit UI collection request, isolated in its own process."""
import asyncio,json,sys,shutil
from datetime import date
from pathlib import Path
import collect_batch as batch
from collection_state import Journal
from workbench_data import load_data,ROOT
from local_config import require_config
from file_lock import ProcessLock

SCOPES={
    'plan':(['计划'],[]),
    'analysis':(['计划','关键词'],['搜索词','地域']),
    'all':(batch.ACCOUNT_TABS,[dim for dim,_ in batch.EFFECT_TABS]),
}

def selection(request):
    scope=request.get('scope','all')
    if not isinstance(scope,str) or scope not in SCOPES:raise ValueError('报表范围无效')
    accounts,effects=SCOPES[scope]
    return list(accounts),list(effects)

def run(request):
    account_tabs,effect_dimensions=selection(request)
    start=date.fromisoformat(request['start']);end=date.fromisoformat(request['end'])
    if start>end or (end-start).days>365:raise ValueError('日期倒置或跨度超过366天')
    if end>=date.today():raise ValueError('请选择昨天或更早日期，避免混入未完整的当日数据')
    config=require_config()
    if not config.get('account_name') or not str(config.get('account_id','')).isdigit():raise ValueError('请先填写本机账号配置')
    batch.START=start.isoformat();batch.END=end.isoformat()
    batch.ACCOUNT=config['account_name'];batch.ACCOUNT_ID=str(config['account_id'])
    existing=[p for p in load_data()['periods'] if p['start']==batch.START and p['end']==batch.END]
    for period in existing:
        if any(r['identity'].get('source')=='manual' for r in period['reports'] if r.get('available') is not False):raise ValueError('此周期含人工导入文件，请继续人工补齐；避免混合不同来源快照，未操作浏览器')
        accounts={str(r['identity'].get('account_id','')) for r in period['reports'] if r.get('available') is not False}
        if accounts!={batch.ACCOUNT_ID}:raise ValueError('该日期已有其他或未知账户快照，请先隔离账户数据；未操作浏览器')
    wanted={f'账户报表/{d}' for d in account_tabs}|{f'效果报表/{d}' for d in effect_dimensions}
    if existing:
        present={r['key'] for r in existing[0]['reports'] if r.get('available') is not False}
        if wanted<=present:
            print(f'所选{len(wanted)}份已有有效快照，校验通过，未操作浏览器',flush=True);return
    print(f'本次选择{len(wanted)}份报表：'+ '、'.join(sorted(wanted)),flush=True)
    asyncio.run(batch.main(account_tabs,effect_dimensions))
    manifests=[p for p in (ROOT/'data/reports').glob('*/校验清单.json') if not (p.parent/'已被复核版本替代.md').exists() and (lambda d:d['start']==batch.START and d['end']==batch.END)(json.loads(p.read_text(encoding='utf-8-sig')))]
    if len(manifests)>1:raise RuntimeError('同周期清单不唯一，停止发布')
    manifest=manifests[0] if manifests else ROOT/'data/reports'/f'{start:%Y%m%d}_{end:%Y%m%d}_已复核'/'校验清单.json'
    output=manifest.parent
    output.mkdir(parents=True,exist_ok=True);reports=[]
    previous=json.loads(manifest.read_text(encoding='utf-8-sig'))['reports'] if manifest.exists() else []
    specs=[batch.identity('账户报表',dim) for dim in account_tabs]+[batch.identity('效果报表',dim,False) for dim in effect_dimensions]
    for ident in specs:
        with Journal(ROOT,ident) as journal:
            result=journal.recover_file()
            if result is None:raise RuntimeError('采集未全部完成，不发布看板数据')
            source=journal.directory/journal.data['file'];target=output/f"{ident['family']}_{ident['dimension']}_{start:%Y%m%d}_{end:%Y%m%d}.csv"
            if target.exists() and target.read_bytes()!=source.read_bytes():raise RuntimeError('已有不同文件，停止避免覆盖')
            shutil.copy2(source,target)
            reports.append({'family':ident['family'],'dimension':ident['dimension'],'file':str(target),'task':str(journal.path),'daily':ident['daily'],'sha256':result['sha256']})
    reports=[r for r in previous if r['family']+'/'+r['dimension'] not in wanted]+reports
    temporary=manifest.with_suffix('.tmp')
    temporary.write_text(json.dumps({'start':batch.START,'end':batch.END,'reports':reports},ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(manifest)
    print(f'所选{len(specs)}份已完成校验，本周期共有{len(reports)}/14份接入工作台',flush=True)
if __name__=='__main__':
    with ProcessLock(ROOT/'data/collection.lock'):run(json.loads(sys.argv[1]))
