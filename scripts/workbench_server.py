"""Loopback dashboard and explicit same-origin local collection actions."""
import argparse,json,mimetypes,subprocess,sys,threading
from datetime import date
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlsplit
from pathlib import Path
from workbench_data import load_data,ROOT
from local_config import read_config,save_config
from demo_data import build_demo
from manual_import import preview,import_files
from workbench_collect import selection
WEB=ROOT/'web'
LOCK=threading.Lock()
JOB={'state':'idle','message':'尚未启动采集'}
STATE=ROOT/'data/workbench-job.json'
if STATE.exists():
    try:
        JOB=json.loads(STATE.read_text(encoding='utf-8'))
        if JOB['state']=='running':JOB.update(state='interrupted',message='服务曾中断，请核对专用浏览器后重试原日期；已保存任务将核验恢复')
    except (ValueError,KeyError):JOB={'state':'error','message':'上次状态文件损坏；任务原件保留，请人工核对'}
def persist_job():
    STATE.parent.mkdir(parents=True,exist_ok=True);tmp=STATE.with_suffix('.tmp');tmp.write_text(json.dumps(JOB,ensure_ascii=False),encoding='utf-8');tmp.replace(STATE)
def run_job(payload):
    global JOB
    try:
        command=[sys.executable,'-X','utf8',str(ROOT/'scripts/workbench_collect.py'),json.dumps(payload)]
        with subprocess.Popen(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8') as process:
            for line in process.stdout:
                with LOCK:JOB['message']=line.strip();JOB['lines']=(JOB.get('lines',[])+[line.strip()])[-40:];persist_job()
            code=process.wait()
        with LOCK:JOB['state']='complete' if code==0 else 'error';persist_job()
    except Exception as error:
        with LOCK:JOB.update(state='error',message=str(error));persist_job()
class Handler(BaseHTTPRequestHandler):
    def write_json(self,body,status=200):
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(json.dumps(body,ensure_ascii=False).encode())
    def do_POST(self):
        global JOB
        origin='http://'+self.headers.get('Host','')
        if self.headers.get('Host') not in ('127.0.0.1:'+str(self.server.server_port),'localhost:'+str(self.server.server_port)) or self.headers.get('Origin')!=origin or self.headers.get('Content-Type')!='application/json':
            self.write_json({'error':'仅允许本机工作台请求'},403);return
        try:
            size=int(self.headers.get('Content-Length','0'))
            limit=32*1024*1024 if urlsplit(self.path).path.startswith('/api/import/') else 8192
            if not 0<size<limit:raise ValueError('请求过大：批次最多约24MB原文件，请分批导入')
            payload=json.loads(self.rfile.read(size));path=urlsplit(self.path).path
            if path in ('/api/import/preview','/api/import/confirm'):
                with LOCK:
                    if JOB['state']=='running':raise ValueError('采集运行中不能同时导入')
                    result=preview(payload) if path.endswith('preview') else import_files(payload)
                self.write_json(result);return
            if path=='/api/config':
                with LOCK:
                    if JOB['state']=='running':raise ValueError('采集中不能修改账户')
                    save_config(payload.get('account'),payload.get('account_id'))
                self.write_json({'message':'目标账户已保存到本机；不含登录凭证'});return
            if path=='/api/collect':
                accounts,effects=selection(payload)
                start=date.fromisoformat(payload['start']);end=date.fromisoformat(payload['end'])
                if start>end or (end-start).days>365 or end>=date.today():raise ValueError('请选择昨天或更早日期，且不超过366天')
                if payload.get('login_confirmed') is not True:raise ValueError('请先人工核对登录')
                with LOCK:
                    if JOB['state']=='running':raise ValueError('已有采集任务正在进行')
                    JOB={'state':'running','message':f'正在核验已有任务，本次选择{len(accounts)+len(effects)}份，先生成再统一下载','lines':[],'start':payload['start'],'end':payload['end'],'scope':payload.get('scope','all')}
                    persist_job()
                    threading.Thread(target=run_job,args=({'start':payload['start'],'end':payload['end'],'scope':payload.get('scope','all')},),daemon=True).start()
                self.write_json({'message':'采集已启动'});return
            if path not in ('/api/browser','/api/shortcut'):self.write_json({'error':'未知操作'},404);return
            with LOCK:
                if JOB['state']=='running':raise ValueError('采集运行中，请等待完成再执行此操作')
                if path=='/api/browser':command=[sys.executable,'-X','utf8',str(ROOT/'scripts/launch_browser.py')]
                else:command=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'添加桌面快捷方式.ps1')]
                result=subprocess.run(command,cwd=ROOT,capture_output=True,timeout=25)
            if result.returncode:raise ValueError(result.stderr.decode('utf-8',errors='replace') or '操作未成功，请检查是否已有同名快捷方式')
            self.write_json({'message':'专用 Chrome 已打开或复用，请人工核对登录' if path=='/api/browser' else '桌面快捷方式已创建，双击可启动工作台'} )
        except Exception as error:self.write_json({'error':str(error)},400)
    def do_GET(self):
        if self.headers.get('Host') not in ('127.0.0.1:'+str(self.server.server_port),'localhost:'+str(self.server.server_port)):
            self.send_error(403);return
        path=urlsplit(self.path).path
        try:
            if path=='/api/job':
                with LOCK:body=json.dumps(JOB,ensure_ascii=False).encode()
                mime='application/json'
            elif path=='/api/config':
                config=read_config()
                body=json.dumps({'account':config.get('account_name'),'account_id':config.get('account_id')},ensure_ascii=False).encode();mime='application/json'
            elif path=='/api/data':body=json.dumps(load_data(),ensure_ascii=False).encode();mime='application/json'
            elif path=='/api/demo':body=json.dumps(build_demo(),ensure_ascii=False).encode();mime='application/json'
            elif path in ('/','/app.js','/jd-plan.js','/manual-import.js','/style.css'):
                file=WEB/('index.html' if path=='/' else path[1:]);body=file.read_bytes();mime=mimetypes.guess_type(file.name)[0] or 'text/plain'
            else:self.send_error(404);return
            self.send_response(200);self.send_header('Content-Type',mime+'; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'");self.end_headers();self.wfile.write(body)
        except Exception as error:
            body=json.dumps({'error':str(error)},ensure_ascii=False).encode();self.send_response(500);self.send_header('Content-Type','application/json; charset=utf-8');self.end_headers();self.wfile.write(body)
    def log_message(self,*args):pass
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=5192);args=parser.parse_args()
    print(f'京东工作台 http://127.0.0.1:{args.port}/',flush=True)
    ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
