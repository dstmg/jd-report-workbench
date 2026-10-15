import asyncio,os,tempfile,time,unittest
from pathlib import Path
from report_download import files,fresh_files,wait_file,creation_matches

class DownloadFiles(unittest.IsolatedAsyncioTestCase):
    async def test_suffixes_old_files_and_partial_download(self):
        with tempfile.TemporaryDirectory() as folder:
            title='报表[计划]';root=Path(folder);old=root/(title+'.csv')
            old.write_text('old');baseline=files(root,title);clicked=time.time()
            fresh=root/(title+' (7).csv');fresh.write_text('new')
            os.utime(fresh,(clicked+1,clicked+1))
            partial=root/(fresh.name+'.crdownload');partial.write_text('pending')
            self.assertEqual(fresh_files(root,title,baseline,clicked),{})
            partial.unlink()
            self.assertEqual(await wait_file(root,title,baseline,clicked,timeout=3),fresh)
            self.assertEqual(old.read_text(),'old')
    async def test_multiple_new_files_never_choose_the_first(self):
        with tempfile.TemporaryDirectory() as folder:
            clicked=time.time()
            for name in ['report.csv','report (1).csv']:
                path=Path(folder)/name;path.write_text('data');os.utime(path,(clicked+1,clicked+1))
            with self.assertRaisesRegex(RuntimeError,'多个新文件'):await wait_file(folder,'report',{},clicked,timeout=2)
    async def test_creation_interval_accepts_slow_response_and_rejects_old_task(self):
        self.assertTrue(creation_matches('2026-10-14 12:00:18','2026-10-14T12:00:00','2026-10-14T12:00:25'))
        self.assertFalse(creation_matches('2026-10-14 11:59:40','2026-10-14T12:00:00','2026-10-14T12:00:25'))

if __name__=='__main__':unittest.main()
