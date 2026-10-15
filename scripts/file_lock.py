"""OS-released process lock; interruption cannot leave an active stale lock."""
import os
class ProcessLock:
    def __init__(self,path):self.path=path;self.file=None
    def acquire(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        stream=open(self.path,'a+b')
        try:
            stream.seek(0,2)
            if not stream.tell():stream.write(b'0');stream.flush()
            stream.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            stream.close();raise RuntimeError('另一进程正在使用采集任务，请等待完成，不重复提交')
        self.file=stream;return self
    def release(self):
        if self.file:self.file.close();self.file=None
    def __enter__(self):return self.acquire()
    def __exit__(self,*args):self.release()
