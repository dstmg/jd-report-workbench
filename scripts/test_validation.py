"""Synthetic validation and task identity checks without merchant files."""
import tempfile
import unittest
from pathlib import Path
from report_validation import validate
from collection_state import Journal

class Tests(unittest.TestCase):
    def test_csv_and_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'sample.csv';header='下单时间,花费,总订单金额,直接订单金额,间接订单金额,投产比\n'
            path.write_text(header+'20260101,100,300,200,100,3\n',encoding='utf-8-sig')
            self.assertEqual(validate(path,'2026-01-01','2026-01-01')['roi_checks'],1)
            for row in ('20260102,100,300,200,100,3','20260101,NaN,300,200,100,3','20260101,100,300,200,100,2','20260101,100,300,100,100,3'):
                path.write_text(header+row+'\n',encoding='utf-8-sig')
                with self.assertRaises(ValueError):validate(path,'2026-01-01','2026-01-01')
            path.write_text(header,encoding='utf-8-sig');self.assertTrue(validate(path,'2026-01-01','2026-01-01')['empty'])
    def test_policy_changes_and_uncertain_submit(self):
        with tempfile.TemporaryDirectory() as directory:
            identity={'account_id':'synthetic','start':'2026-01-01','end':'2026-01-01','window':30,'attribution':'下单','dimension':'计划'}
            first=Journal(directory,identity);other=Journal(directory,{**identity,'window':15});self.assertNotEqual(first.directory,other.directory)
            with first:first.save(state='submitting')
            with Journal(directory,identity) as resumed:
                with self.assertRaises(RuntimeError):resumed.recover_file()

if __name__=='__main__':unittest.main()
