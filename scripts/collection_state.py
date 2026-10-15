"""Persist identity and policy before submission; never retry an ambiguous click."""
import hashlib
import json
import os
from pathlib import Path
from report_validation import validate
from file_lock import ProcessLock

class Journal:
    def __init__(self,root,identity):
        self.identity=identity
        token=hashlib.sha256(json.dumps(identity,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:24]
        self.directory=Path(root)/'data/tasks'/token;self.directory.mkdir(parents=True,exist_ok=True)
        self.path=self.directory/'task.json';self.lock=self.directory/'task.lock';self.fd=None
        self.data={'identity':identity,'state':'pending'}
    def __enter__(self):
        self.fd=ProcessLock(self.lock).acquire()
        try:
            if self.path.exists():
                self.data=json.loads(self.path.read_text(encoding='utf-8'))
                if self.data['identity']!=self.identity:raise ValueError('任务身份或口径不符')
            return self
        except Exception:self.__exit__();raise
    def __exit__(self,*args):
        if self.fd is not None:self.fd.release();self.fd=None
    def save(self,**changes):
        self.data.update(changes);temporary=self.path.with_suffix('.tmp');temporary.write_text(json.dumps(self.data,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(self.path)
    def recover_file(self):
        state=self.data['state'];filename=self.data.get('file')
        if filename:
            path=self.directory/filename
            if path.parent!=self.directory or not path.is_file():raise ValueError('下载文件缺失或路径不符，停止人工核对')
            result=validate(path,self.identity['start'],self.identity['end'])
            if self.data.get('sha256') and result['sha256']!=self.data['sha256']:raise ValueError('报表文件变化，不能直接跳过')
            self.save(state='validated',sha256=result['sha256'],validation=result);return result
        if state in ('submitting','submitted','downloading','saving'):raise RuntimeError('提交或下载结果不确定，先核对后台任务，不重复点击')
        return None
