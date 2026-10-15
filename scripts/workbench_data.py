"""Import only explicitly verified manifests; never scan unrelated Downloads."""
import csv, json, hashlib
from pathlib import Path
from report_validation import validate
ROOT = Path(__file__).resolve().parents[1]

def load_data(root=ROOT):
    periods=[]; seen=set()
    for manifest in sorted((root/'data/reports').glob('*/校验清单.json')):
        if (manifest.parent/'已被复核版本替代.md').exists():continue
        document=json.loads(manifest.read_text(encoding='utf-8-sig'))
        key=(document['start'],document['end'])
        if key in seen:raise ValueError('同一周期存在多份校验清单，请先确定唯一快照')
        seen.add(key)
        reports=[]; report_keys=set(); account_ids=set()
        for item in document['reports']:
            report_key=(item['family'],item['dimension'])
            if report_key in report_keys:raise ValueError('校验清单包含重复报表维度')
            report_keys.add(report_key)
            path=manifest.parent/Path(item['file']).name
            result=validate(path,document['start'],document['end'])
            if result['sha256']!=item['sha256']:raise ValueError(f'文件哈希不符：{path.name}')
            with path.open(encoding='utf-8-sig',newline='') as stream:
                reader=csv.DictReader(stream); rows=list(reader); fields=reader.fieldnames
            task=json.loads(Path(item['task']).read_text(encoding='utf-8-sig')) if item.get('task') and Path(item['task']).exists() else {}
            identity=item.get('identity') or task.get('identity',{})
            if identity:
                if any(identity.get(k)!=value for k,value in [('family',item['family']),('dimension',item['dimension']),('start',document['start']),('end',document['end'])]):raise ValueError('报表任务身份与清单不符')
                account_ids.add(identity.get('account_id'))
            reports.append({'key':item['family']+'/'+item['dimension'],'family':item['family'],'dimension':item['dimension'],'daily':item['daily'],'fields':fields,'rows':rows,'sha256':result['sha256'],'file':path.name,'checks':result['roi_checks'],'identity':identity})
        if len(account_ids)>1:raise ValueError('同周期报表混入多个账户，停止汇总')
        available=len(reports);known={r['key'] for r in reports};reference=reports[0]['identity'] if reports else {}
        for spec in json.loads((root/'report_catalog.json').read_text(encoding='utf-8')):
            if spec['family']+'/'+spec['dimension'] not in known:
                reports.append({'key':spec['family']+'/'+spec['dimension'],'family':spec['family'],'dimension':spec['dimension'],'fields':spec['fields'],'rows':[],'daily':spec['family']=='账户报表','available':False,'identity':reference,'checks':0,'sha256':'','file':'未导入'})
        periods.append({'key':document['start']+'_'+document['end'],'start':document['start'],'end':document['end'],'available_reports':available,'reports':reports})
    return {'periods':periods,'notice':'单文件日期、哈希和内部指标校验；不代表账户账单对账。'}
