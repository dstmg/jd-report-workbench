"""Public-safe local account setup. Never includes login credentials."""
import json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read_config(root=ROOT):
    path=root/'config.local.json'
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {'account_name':'','account_id':''}
def save_config(name,account_id):
    name=str(name).strip();account_id=str(account_id).strip()
    if not name or len(name)>100 or not re.fullmatch(r'\d{1,30}',account_id):raise ValueError('请输入账户名称和纯数字账户ID；不是密码或登录凭证')
    config={'account_name':name,'account_id':account_id,'window':30,'attribution':'下单','gifts':False,'order_state':'成交订单','alerts_enabled':False}
    path=ROOT/'config.local.json';tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(path)
def require_config():
    config=read_config()
    if not config.get('account_name') or not re.fullmatch(r'\d{1,30}',str(config.get('account_id',''))):raise ValueError('请先在数据管理保存目标账户名称与ID')
    return config
