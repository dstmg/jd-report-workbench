"""Explicit local CSV imports; never guess account or attribution from numeric data."""
import base64,csv,hashlib,io,json,re,tempfile,uuid
from datetime import date,datetime
from pathlib import Path
from file_lock import ProcessLock
from local_config import read_config
from report_validation import validate
ROOT=Path(__file__).resolve().parents[1]
def catalog(root=ROOT):return json.loads((root/'report_catalog.json').read_text(encoding='utf-8'))
def parse_file(item,start,end,root=ROOT):
    name=str(item.get('name',''))
    if not name.lower().endswith('.csv') or len(name)>240:raise ValueError('目前仅支持京东原始CSV，不支持Excel或ZIP')
    try:raw=base64.b64decode(item['content'],validate=True)
    except (KeyError,ValueError):raise ValueError('文件内容无效')
    if not raw or len(raw)>12*1024*1024:raise ValueError('单文件应为1字节至12MB')
    for encoding in ['utf-8-sig','gb18030']:
        try:text=raw.decode(encoding);break
        except UnicodeDecodeError:continue
    else:raise ValueError('CSV编码不支持，请使用UTF-8或GB18030')
    rows=list(csv.reader(io.StringIO(text,newline='')))
    if not rows:raise ValueError('CSV缺少表头')
    rows=[r for r in rows if any(c.strip() for c in r)]
    if not rows:raise ValueError('CSV缺少表头')
    rows[0]=[c.strip() for c in rows[0]];fields=rows[0]
    output=io.StringIO(newline='');writer=csv.writer(output);writer.writerows(rows);normalized=output.getvalue().encode('utf-8-sig')
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'report.csv';path.write_bytes(normalized);result=validate(path,start,end)
    matches=[]
    for spec in catalog(root):
        prefix=spec['fields'][:spec['fields'].index('展现数')]
        if not set(prefix).issubset(fields):continue
        # Exclude a broader schema presented as account-only data.
        known_identity={k for s in catalog(root) for k in s['fields'][:s['fields'].index('展现数')]}
        extra=(set(fields)&known_identity)-set(spec['fields'])
        if extra:continue
        if fields[0]!=spec['fields'][0]:continue
        matches.append(spec['family']+'/'+spec['dimension'])
    if not matches:raise ValueError('无法匹配14种京东快车报表，可能缺少身份字段或选错报表')
    date_values=[row[0] for row in rows[1:]]
    daily=all(re.fullmatch(r'\d{8}',value) for value in date_values)
    ranges={value for value in date_values if '~' in value}
    expected=start.replace('-','')+'~'+end.replace('-','')
    if ranges and ranges!={expected}:raise ValueError('周期汇总行与确认的起止日期不一致，不能混合周期')
    if fields[0]=='下单时间' and not daily:raise ValueError('账户报表必须导出分日数据，不能把汇总冒充分日')
    return {'name':name,'raw':raw,'normalized':normalized,'result':result,'matches':matches,'raw_sha256':hashlib.sha256(raw).hexdigest()}
def prepare(payload,root=ROOT):
    start=date.fromisoformat(payload['start']);end=date.fromisoformat(payload['end'])
    if start>end or (end-start).days>365:raise ValueError('日期倒置或跨度超过366天')
    files=payload.get('files',[])
    if not isinstance(files,list) or not 1<=len(files)<=14:raise ValueError('请选择1至14份CSV')
    return [parse_file(item,str(start),str(end),root) for item in files]
def preview(payload,root=ROOT):
    parsed=prepare(payload,root)
    return {'files':[{'name':p['name'],'rows':p['result']['rows'],'fields':len(p['result']['fields']),'empty':p['result']['empty'],'matches':p['matches']} for p in parsed]}
def import_files(payload,root=ROOT):
    if payload.get('confirmed') is not True:raise ValueError('请确认账户、日期及30天下单口径，CSV无法证明归因设置')
    config=read_config(root)
    if not config.get('account_name') or not str(config.get('account_id','')).isdigit():raise ValueError('请先保存目标账户名称和ID')
    parsed=prepare(payload,root);keys=[f.get('key') for f in payload['files']]
    if len(set(keys))!=len(keys):raise ValueError('同一次不能导入重复维度')
    for p,key in zip(parsed,keys):
        if key not in p['matches']:raise ValueError('所选维度与CSV身份字段不符：'+p['name'])
        if key.startswith('效果报表/') and any(day!=payload['start'].replace('-','')+'~'+payload['end'].replace('-','') and not (payload['start']==payload['end'] and day==payload['start'].replace('-','')) for day in p['result']['dates']):raise ValueError('效果报表必须与确认周期一致，不把分日或子区间冒充完整周期')
    start,end=payload['start'],payload['end'];existing=[]
    with ProcessLock(root/'data/collection.lock'):
        for manifest in (root/'data/reports').glob('*/校验清单.json'):
            if (manifest.parent/'已被复核版本替代.md').exists():continue
            doc=json.loads(manifest.read_text(encoding='utf-8-sig'))
            if (doc['start'],doc['end'])==(start,end):existing.append((manifest,doc))
        if len(existing)>1:raise ValueError('此周期有多个快照，先人工核对，不继续导入')
        if existing:manifest,document=existing[0]
        else:
            folder=root/'data/reports'/f"{start.replace('-','')}_{end.replace('-','')}_人工导入"
            manifest=folder/'校验清单.json';document={'start':start,'end':end,'reports':[]}
        entries={r['family']+'/'+r['dimension']:r for r in document['reports']}
        for item in entries.values():
            identity=item.get('identity')
            if not identity and item.get('task') and Path(item['task']).exists():identity=json.loads(Path(item['task']).read_text(encoding='utf-8-sig')).get('identity')
            if not identity or str(identity.get('account_id'))!=str(config['account_id']):raise ValueError('已有快照账户未知或不同，拒绝混入')
        for p,key in zip(parsed,keys):
            if key in entries and entries[key]['sha256']!=p['result']['sha256']:raise ValueError('同周期同维度已有不同快照，保留原件，不覆盖：'+key)
        added=0;batch=root/'data/imports'/uuid.uuid4().hex
        for p,key in zip(parsed,keys):
            if key in entries:continue
            family,dimension=key.split('/');identity={'account':config['account_name'],'account_id':str(config['account_id']),'family':family,'dimension':dimension,'start':start,'end':end,'window':30,'attribution':'下单','gifts':False,'order_state':'成交订单','daily':family=='账户报表','marketing_targets':'user_confirmed','source':'manual'}
            folder=batch/dimension/('account' if family=='账户报表' else 'effect');folder.mkdir(parents=True)
            (folder/'original.csv').write_bytes(p['raw']);(folder/'report.csv').write_bytes(p['normalized'])
            audit={'identity':identity,'original_name':p['name'],'original_sha256':p['raw_sha256'],'sha256':p['result']['sha256'],'imported_at':datetime.now().isoformat(),'note':'归因及账户由用户确认，非CSV自动识别'}
            (folder/'import.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
            target=manifest.parent/f"{family}_{dimension}_{p['result']['sha256'][:12]}.csv";target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(p['normalized'])
            entries[key]={'family':family,'dimension':dimension,'file':str(target),'daily':family=='账户报表','sha256':p['result']['sha256'],'identity':identity,'source':'manual','audit':str(folder/'import.json')};added+=1
        if added:
            document['reports']=list(entries.values());tmp=manifest.with_suffix('.tmp');tmp.write_text(json.dumps(document,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(manifest)
        return {'message':f'导入完成：新增{added}份，重复跳过{len(parsed)-added}份；本周期已有{len(entries)}/14份','added':added,'start':start,'end':end}
