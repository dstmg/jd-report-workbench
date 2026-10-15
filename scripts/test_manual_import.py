import base64,csv,io,json,shutil,tempfile,unittest
from pathlib import Path
from manual_import import preview,import_files
from workbench_data import load_data
ROOT=Path(__file__).resolve().parents[1]
class ManualImport(unittest.TestCase):
    def test_collection_scopes(self):
        from workbench_collect import selection
        self.assertEqual(selection({'scope':'plan'}),(['计划'],[]))
        self.assertEqual(selection({'scope':'analysis'}),(['计划','关键词'],['搜索词','地域']))
        a,e=selection({});self.assertEqual(len(a)+len(e),14)
        for invalid in ('unknown',[],None):
            with self.assertRaises(ValueError):selection({'scope':invalid})
    def test_selected_collection_publication_and_expansion(self):
        from unittest.mock import patch,AsyncMock
        import workbench_collect as worker
        from report_validation import validate
        root=self.root
        class JournalFixture:
            def __init__(self,unused,identity):
                self.directory=root/'tasks'/identity['dimension'];self.directory.mkdir(parents=True,exist_ok=True)
                self.path=self.directory/'task.json';self.path.write_text(json.dumps({'identity':identity}),encoding='utf-8')
                self.data={'file':'report.csv'}
                request=ManualImport.request(self_outer,identity['dimension'])
                (self.directory/'report.csv').write_bytes(base64.b64decode(request['files'][0]['content']))
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def recover_file(self):return validate(self.directory/'report.csv','2026-01-01','2026-01-01')
        self_outer=self
        request={'start':'2026-01-01','end':'2026-01-01','scope':'plan'}
        with patch.object(worker,'ROOT',root),patch.object(worker,'require_config',return_value={'account_name':'测试','account_id':'123'}),patch.object(worker,'load_data',side_effect=lambda:load_data(root)),patch.object(worker,'Journal',JournalFixture),patch.object(worker.batch,'main',new_callable=AsyncMock) as collect:
            worker.run(request);collect.assert_awaited_once_with(['计划'],[])
            period=load_data(root)['periods'][0];self.assertEqual(period['available_reports'],1)
            worker.run(request);self.assertEqual(collect.await_count,1)
            # A later automatic scope can add dimensions while retaining the plan.
            with patch.dict(worker.SCOPES,{'extra':(['计划','关键词'],[])}):worker.run({**request,'scope':'extra'})
            self.assertEqual(load_data(root)['periods'][0]['available_reports'],2)
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        shutil.copy2(ROOT/'report_catalog.json',self.root/'report_catalog.json')
        (self.root/'config.local.json').write_text(json.dumps({'account_name':'虚拟测试','account_id':'123'}),encoding='utf-8')
    def tearDown(self):self.temp.cleanup()
    def request(self,dim='账户',encoding='utf-8-sig',empty=False):
        spec=next(s for s in json.loads((self.root/'report_catalog.json').read_text(encoding='utf-8')) if s['family']=='账户报表' and s['dimension']==dim)
        row={k:'0' for k in spec['fields']};row.update({'下单时间':'20260101','花费':'100','总订单金额':'300','直接订单金额':'200','间接订单金额':'100','投产比':'3','计划ID':'555','推广计划':'虚拟计划'})
        stream=io.StringIO(newline='');w=csv.writer(stream);w.writerow(spec['fields'])
        if not empty:w.writerow([row[k] for k in spec['fields']])
        return {'start':'2026-01-01','end':'2026-01-01','confirmed':True,'files':[{'name':'人工报表.csv','key':'账户报表/'+dim,'content':base64.b64encode(stream.getvalue().encode(encoding)).decode()}]}
    def test_preview_import_duplicate_partial(self):
        r=self.request();self.assertIn('账户报表/账户',preview(r,self.root)['files'][0]['matches'])
        self.assertEqual(import_files(r,self.root)['added'],1)
        self.assertEqual(import_files(r,self.root)['added'],0)
        p=load_data(self.root)['periods'][0]
        self.assertEqual(p['available_reports'],1);self.assertEqual(sum(x.get('available') is False for x in p['reports']),13)
        self.assertEqual(import_files(self.request('计划','gb18030'),self.root)['added'],1)
        self.assertEqual(load_data(self.root)['periods'][0]['available_reports'],2)
        self.assertEqual(len(list((self.root/'data/imports').rglob('original.csv'))),2)
    def test_conflict_account_dimension(self):
        r=self.request();import_files(r,self.root)
        changed=self.request();text=base64.b64decode(changed['files'][0]['content']).decode('utf-8-sig').replace('100,','200,',1);changed['files'][0]['content']=base64.b64encode(text.encode('utf-8-sig')).decode()
        with self.assertRaises(ValueError):import_files(changed,self.root)
        p=self.request('计划');p['files'][0]['key']='账户报表/账户'
        with self.assertRaises(ValueError):import_files(p,self.root)
        (self.root/'config.local.json').write_text(json.dumps({'account_name':'另一虚拟账户','account_id':'999'}),encoding='utf-8')
        with self.assertRaises(ValueError):import_files(self.request('计划'),self.root)
    def test_empty_date_and_confirmation(self):
        r=self.request('计划',empty=True);self.assertTrue(preview(r,self.root)['files'][0]['empty'])
        r['confirmed']=False
        with self.assertRaises(ValueError):import_files(r,self.root)
        r=self.request();r['start']=r['end']='2026-01-02'
        with self.assertRaises(ValueError):preview(r,self.root)
if __name__=='__main__':unittest.main()
