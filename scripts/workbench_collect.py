"""Explicit UI collection request, isolated in its own process."""
import asyncio,json,sys,shutil
from datetime import date
from pathlib import Path
import collect_batch as batch
from collection_state import Journal
from workbench_data import load_data,ROOT
from local_config import require_config
from file_lock import ProcessLock

def run(request):
    start=date.fromisoformat(request['start']);end=date.fromisoformat(request['end'])
    if start>end or (end-start).days>365:raise ValueError('日期倒置或跨度超过366天')
    if end>=date.today():raise ValueError('请选择昨天或更早日期，避免混入未完整的当日数据')
    config=require_config()
    if not config.get('account_name') or not str(config.get('account_id','')).isdigit():raise ValueError('请先填写本机账号配置')
    batch.START=start.isoformat();batch.END=end.isoformat()
    batch.ACCOUNT=config['account_name'];batch.ACCOUNT_ID=str(config['account_id'])
    existing=[p for p in load_data()['periods'] if p['start']==batch.START and p['end']==batch.END]
    for period in existing:
        accounts={str(r['identity'].get('account_id','')) for r in period['reports']}
        if accounts!={batch.ACCOUNT_ID}:raise ValueError('该日期已有其他或未知账户快照，请先隔离账户数据；未操作浏览器')
    asyncio.run(batch.main())
    if existing:
        print('该周期已有唯一有效快照，复核完成，保留原文件',flush=True);return
    output=ROOT/'data/reports'/f'{start:%Y%m%d}_{end:%Y%m%d}_已复核'
    output.mkdir(parents=True,exist_ok=True);reports=[]
    specs=[batch.identity('账户报表',dim) for dim in batch.ACCOUNT_TABS]+[batch.identity('效果报表',dim,False) for dim,_ in batch.EFFECT_TABS]
    for ident in specs:
        with Journal(ROOT,ident) as journal:
            result=journal.recover_file()
            if result is None:raise RuntimeError('采集未全部完成，不发布看板数据')
            source=journal.directory/journal.data['file'];target=output/f"{ident['family']}_{ident['dimension']}_{start:%Y%m%d}_{end:%Y%m%d}.csv"
            if target.exists() and target.read_bytes()!=source.read_bytes():raise RuntimeError('已有不同文件，停止避免覆盖')
            shutil.copy2(source,target)
            reports.append({'family':ident['family'],'dimension':ident['dimension'],'file':str(target),'task':str(journal.path),'daily':ident['daily'],'sha256':result['sha256']})
    manifest=output/'校验清单.json';temporary=manifest.with_suffix('.tmp')
    temporary.write_text(json.dumps({'start':batch.START,'end':batch.END,'reports':reports},ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(manifest)
    print('全部14份文件已完成校验并接入工作台',flush=True)
if __name__=='__main__':
    with ProcessLock(ROOT/'data/collection.lock'):run(json.loads(sys.argv[1]))
