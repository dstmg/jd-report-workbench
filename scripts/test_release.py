"""Portable release checks; no merchant records or browser profile required."""
import subprocess,sys,tempfile,unittest,json
from pathlib import Path
from file_lock import ProcessLock
from demo_data import build_demo
from local_config import read_config
from workbench_data import load_data
class ReleaseTests(unittest.TestCase):
    def test_empty_checkout(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            self.assertEqual(load_data(root)['periods'],[])
            self.assertFalse(read_config(root)['account_id'])
    def test_demo_independent(self):
        d=build_demo();self.assertTrue(d['demo']);self.assertEqual(len(d['periods'][0]['reports']),14)
        self.assertTrue(all(r['rows'] and r['identity']['account_id']=='DEMO' for r in d['periods'][0]['reports']))
    def test_process_lock_releases(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'task.lock'
            with ProcessLock(path):
                with self.assertRaises(RuntimeError):ProcessLock(path).acquire()
            with ProcessLock(path):pass
    def test_crashed_process_lock_releases(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'task.lock'
            code='from pathlib import Path;from file_lock import ProcessLock;import os;lock=ProcessLock(Path('+repr(str(path))+')).acquire();os._exit(0)'
            subprocess.run([sys.executable,'-c',code],cwd=Path(__file__).parent,check=True)
            with ProcessLock(path):pass
if __name__=='__main__':unittest.main()
