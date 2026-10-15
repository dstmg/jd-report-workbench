"""Native download detection bound to one backend task, including Chrome suffixes."""
import asyncio,glob,re,time
from pathlib import Path

def files(directory,title):
    pattern=re.compile(re.escape(title)+r'(?: \(\d+\))?\.csv$',re.IGNORECASE)
    result={}
    for path in Path(directory).glob(glob.escape(title)+'*.csv'):
        if pattern.fullmatch(path.name) and path.is_file():
            stat=path.stat();result[path.name]=(stat.st_size,stat.st_mtime_ns)
    return result

def fresh_files(directory,title,baseline,clicked_at):
    current=files(directory,title)
    return {name:stat for name,stat in current.items()
            if list(stat)!=list(baseline.get(name,())) and stat[0]>0 and stat[1]/1e9>=clicked_at
            and not (Path(directory)/(name+'.crdownload')).exists()}

async def wait_file(directory,title,baseline,clicked_at,*,timeout=120):
    deadline=time.monotonic()+timeout;previous=None;stable=0
    while time.monotonic()<deadline:
        current=fresh_files(directory,title,baseline,clicked_at)
        if len(current)>1:raise RuntimeError('同一次下载出现多个新文件，停止人工核对，不重复点击')
        if len(current)==1:
            stable=stable+1 if current==previous else 1
            if stable>=3:return Path(directory)/next(iter(current))
        else:stable=0
        previous=current;await asyncio.sleep(0.4)
    raise RuntimeError('本次原生下载未完成，保留任务，不能重复点击')

def creation_matches(text,started,finished):
    from datetime import datetime,timedelta
    match=re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}',text)
    if not match:return False
    created=datetime.fromisoformat(match.group())
    low=datetime.fromisoformat(started)-timedelta(seconds=5)
    high=datetime.fromisoformat(finished)+timedelta(seconds=5)
    return low<=created<=high
