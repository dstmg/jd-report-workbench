"""Launch ordinary installed Chrome before automation attaches; local endpoint only."""
import argparse
import json
import os
import socket
import subprocess
import time
from pathlib import Path
from urllib.request import urlopen
import psutil

ROOT = Path(__file__).resolve().parents[1]


def owned(record):
    port, pid = int(record['port']), int(record['pid'])
    expected_profile = Path(os.environ['LOCALAPPDATA']) / 'JdReportDownloader/browser-profile-chrome'
    if Path(record['profile']) != expected_profile or not 1 <= port <= 65535:
        raise RuntimeError('启动记录的登录目录或端口无效')
    try:
        process=psutil.Process(pid)
        arguments=process.cmdline()
        profile_args=[arg.split('=',1)[1] for arg in arguments if arg.startswith('--user-data-dir=')]
        connections=[c for c in process.net_connections(kind='tcp') if c.status==psutil.CONN_LISTEN and c.laddr.port==port]
        if Path(process.exe())!=Path(record['chrome']) or profile_args!=[str(expected_profile)] or len(connections)!=1 or connections[0].laddr.ip!='127.0.0.1':
            raise RuntimeError('浏览器程序、登录目录或本机端口归属不符，停止连接')
    except psutil.NoSuchProcess:
        return False
    except psutil.AccessDenied as exc:
        raise RuntimeError('无法核验浏览器进程，不连接或结束未知窗口') from exc
    return True


def launch():
    # Serialize Chrome startup across project copies sharing the dedicated profile.
    import ctypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_bool,ctypes.c_wchar_p]
    kernel.CreateMutexW.restype=ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
    kernel.ReleaseMutex.argtypes=[ctypes.c_void_p]
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    handle=kernel.CreateMutexW(None,False,'Local\\JdReportDownloaderChromeLauncher')
    if not handle:raise RuntimeError('无法创建浏览器启动互斥锁')
    acquired=kernel.WaitForSingleObject(handle,0) in (0,128)
    if not acquired:
        kernel.CloseHandle(handle)
        raise RuntimeError('另一个启动操作正在进行，请稍后重试')
    try:_launch()
    finally:kernel.ReleaseMutex(handle);kernel.CloseHandle(handle)


def _launch():
    record_path = ROOT / 'data/browser-launch.json'
    if record_path.exists():
        record = json.loads(record_path.read_text(encoding='utf-8'))
        if owned(record):
            print('已核验并复用现有专用Chrome，无需重新扫码。')
            print(json.dumps({'pid': record['pid'], 'port': record['port'], 'reused': True}, ensure_ascii=False))
            return
    # A prior launch may have created Chrome but failed before saving the record.
    # Verify the exact dedicated profile, executable and listener before reuse.
    expected_profile=Path(os.environ['LOCALAPPDATA'])/'JdReportDownloader/browser-profile-chrome'
    existing=[]
    for process in psutil.process_iter(['pid','name']):
        if (process.info['name'] or '').lower()!='chrome.exe':continue
        try:
            arguments=process.cmdline()
            profiles=[arg.split('=',1)[1] for arg in arguments if arg.startswith('--user-data-dir=')]
            if profiles!=[str(expected_profile)]:continue
            ports=[int(arg.split('=',1)[1]) for arg in arguments if arg.startswith('--remote-debugging-port=')]
            if len(ports)!=1:raise RuntimeError('京东专用窗口缺少唯一调试端口，不再打开其他窗口')
            candidate={'pid':process.pid,'port':ports[0],'chrome':process.exe(),'profile':str(expected_profile),'launch_method':'verified_ordinary_chrome_recovery','automation_attached':False}
            candidates=[Path(os.environ.get('PROGRAMFILES','C:/Program Files'))/'Google/Chrome/Application/chrome.exe',Path(os.environ['LOCALAPPDATA'])/'Google/Chrome/Application/chrome.exe']
            if Path(candidate['chrome']) not in candidates:raise RuntimeError('京东窗口不是预期Chrome程序')
            if owned(candidate):existing.append(candidate)
        except psutil.NoSuchProcess:continue
        except psutil.AccessDenied:raise RuntimeError('无法检查Chrome进程，请人工处理，不继续打开窗口')
    if len(existing)>1:raise RuntimeError('多个京东专用窗口进程，不选择其中之一')
    if existing:
        directory=ROOT/'data';directory.mkdir(exist_ok=True)
        temporary=directory/'browser-launch.tmp';temporary.write_text(json.dumps(existing[0],ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(record_path)
        print('已核验并恢复唯一京东专用窗口，不额外打开Chrome。',flush=True)
        return
    candidates = [Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Google/Chrome/Application/chrome.exe',
                  Path(os.environ['LOCALAPPDATA']) / 'Google/Chrome/Application/chrome.exe']
    chrome = next((path for path in candidates if path.is_file()), None)
    if chrome is None:
        raise RuntimeError('未找到Google Chrome；请配置已安装的浏览器路径')
    profile = Path(os.environ['LOCALAPPDATA']) / 'JdReportDownloader/browser-profile-chrome'
    # Reuse the same dedicated profile to vary the launch method alone.
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    args = [str(chrome), f'--user-data-dir={profile}', f'--remote-debugging-port={port}',
            '--remote-debugging-address=127.0.0.1', '--no-first-run', '--no-default-browser-check',
            '--disable-features=CalculateNativeWinOcclusion',
            '--disable-background-timer-throttling', '--disable-renderer-backgrounding',
            'https://jzt.jd.com/']
    process = subprocess.Popen(args)
    record = {'pid': process.pid, 'port': port, 'chrome': str(chrome), 'profile': str(profile),
              'launch_method': 'ordinary_chrome_before_cdp', 'automation_attached': False}
    deadline=time.monotonic()+15
    while True:
        if process.poll() is not None:
            raise RuntimeError('Chrome进程未独立启动；可能另一工程已打开相同专用环境。保留原启动记录，不接管未知窗口')
        try:
            if owned(record):break
        except RuntimeError:
            if time.monotonic()>=deadline:raise
        if time.monotonic()>=deadline:raise RuntimeError('独立Chrome端点未就绪，保留原记录供核验')
        time.sleep(0.25)
    directory = ROOT / 'data'
    directory.mkdir(exist_ok=True)
    path = directory / 'browser-launch.json'
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(path)
    print(json.dumps(record, ensure_ascii=False))
    print('普通Chrome已启动，当前没有连接自动化。请先人工核对登录；不要反复扫码。')


def check():
    record = json.loads((ROOT / 'data/browser-launch.json').read_text(encoding='utf-8'))
    if not owned(record):
        raise RuntimeError('记录中的专用Chrome已经退出')
    endpoint = f"http://127.0.0.1:{int(record['port'])}/json/version"
    with urlopen(endpoint, timeout=3) as response:
        version = json.load(response)
    # Do not read profile storage, cookies, page requests, or WebSocket IDs.
    print(json.dumps({'port': record['port'], 'browser': version.get('Browser'),
                      'protocol': version.get('Protocol-Version'), 'endpoint_reachable': True}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    check() if args.check else launch()
