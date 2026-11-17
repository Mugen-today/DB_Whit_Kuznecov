import tempfile,unittest,sqlite3
from pathlib import Path
from unittest.mock import patch
from openpyxl import Workbook
from backend.app.modules import import_excel as excel,gpkg_jobs as jobs,gpkg_uploads as files,entities
from backend.app.modules.validation_lookup import LookupDatabase
from backend.app.modules.gpkg_errors import ImportFailure
from tests.unit.test_gpkg_policy import Store
class OptimizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        p=patch.object(files,'ROOT',self.root/'cache');p.start();self.addCleanup(p.stop)
    def workbook(self,age=25):
        p=self.root/'input.xlsx';b=Workbook();s=b.active;s.title='Cases'
        s.append(['Patient.passport','Patient.age','Patient.reg_date','Geodata.Longitude','Geodata.Latitude'])
        s.append(['00001',25,'2026-01-01',30,60]);s.append(['00002',age,'2026-01-02',31,61]);b.save(p);b.close();return p
    def test_excel_optional_strict_partial_repeat_identity_and_original(self):
        p=self.workbook(None);original=p.read_bytes()
        state=excel.execute(p,store=Store(),mode='entities');self.assertEqual((state['status'],state['successful_rows']),('invalid',0))
        with patch.object(entities,'create',return_value={'ids':{'Patient':'p','Geodata':'g'},'created_by_job':{'Patient':1,'Geodata':1}}) as create:
            state=excel.execute(p,store=Store(),mode='entities',error_policy='partial',apply=True)
            self.assertEqual((state['status'],state['successful_rows'],state['documents_present']),('complete_with_errors',1,2))
            self.assertEqual(create.call_args.args[3]['entities']['Patient']['passport'],'00001')
        self.assertEqual(p.read_bytes(),original)
        a=excel.stage(p,'qgis-user');b=excel.stage(p,'qgis-user')
        self.assertEqual(files.fingerprint(a['upload_id'],'qgis-user'),files.fingerprint(b['upload_id'],'qgis-user'))
    def test_excel_formula_and_missing_column_stop_before_writes(self):
        with self.assertRaises(ImportFailure):excel.execute(self.workbook('=1+1'),store=Store(),mode='entities',apply=True)
        p=self.workbook();b=Workbook();s=b.active;s.append(['Patient.age']);s.append([25]);b.save(p);b.close()
        with self.assertRaises(ImportFailure):excel.execute(p,store=Store(),mode='entities',apply=True)
    def test_lookup_cache_is_scoped_bounded_and_per_page(self):
        class Collection:
            def __init__(self):self.calls=0
            def find_one(self,q,p=None,**kw):self.calls+=1;return {'_id':self.calls}
        c=Collection()
        class Database:
            def __getitem__(self,n):return c
        db=Database();cache=LookupDatabase(db)
        self.assertEqual(cache.Patient.find_one({'_owner_id':'a'}),cache.Patient.find_one({'_owner_id':'a'}));self.assertEqual(c.calls,1)
        cache.Patient.find_one({'_owner_id':'b'});self.assertEqual(c.calls,2)
        LookupDatabase(db).Patient.find_one({'_owner_id':'a'});self.assertEqual(c.calls,3)
        for i in range(1100):cache.Patient.find_one({'_id':i})
        self.assertLessEqual(len(cache.cache),1024);self.assertLessEqual(cache.bytes,1048576)
