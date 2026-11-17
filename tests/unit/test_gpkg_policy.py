import unittest,tempfile,sqlite3,json,sys,hashlib
from pathlib import Path
from unittest.mock import patch
from pymongo.errors import AutoReconnect,OperationFailure
from backend.app.modules import gpkg_uploads as files,gpkg_jobs as jobs,gpkg_import as mapping,entities
from backend.app.modules.gpkg_errors import ImportFailure
from backend.app.modules.qgis_data import ApiError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integration'))
from gpkg_fixture import build
class Store:
    def database(self,role):return self
    def command(self,*args):return {'ok':1}
    def __getitem__(self,name):return self
    def find_one(self,*args,**kwargs):return None
class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        p=patch.object(files,'ROOT',self.root/'cache');p.start();self.addCleanup(p.stop)
        self.source=self.root/'data.gpkg';build(self.source)
        self.targets={'Patient.passport':'passport','Patient.age':'age','Patient.reg_date':'registered'}
    def upload(self,policy='strict',mapping_fields=None):
        info=files.upload(self.source.read_bytes(),'owner')
        return {'upload_id':info['upload_id'],'table':'cases_points','mapping':self.targets if mapping_fields is None else mapping_fields,'use_geometry':True,'mode':'entities','error_policy':policy}
    def ready(self,payload,store=None):
        store=store or Store();state=jobs.start(store,'user','owner',payload)
        while state['status']=='validating':state=jobs.validate(store,'user','owner',state['job_id'])
        return state
    def test_strict_and_partial_do_not_substitute_or_drop_invalid_row(self):
        db=sqlite3.connect(self.source);db.execute('UPDATE cases_points SET age=NULL WHERE fid=2');db.commit();db.close()
        original=self.source.read_bytes()
        strict=self.ready(self.upload());self.assertEqual((strict['status'],strict['rejected_rows'],strict['successful_rows']),('invalid',1,0))
        with patch.object(entities,'create') as write:
            with self.assertRaises(ApiError):jobs.apply(Store(),'user','owner',strict['job_id'])
            write.assert_not_called()
        partial=self.ready(self.upload('partial'));self.assertEqual((partial['status'],partial['valid_rows'],partial['rejected_rows']),('ready',1,1))
        received=[]
        def create(store,role,owner,item,**kwargs):
            received.append(item);return {'ids':{'Patient':'p','Geodata':'g'},'created_by_job':{'Patient':1,'Geodata':1}}
        with patch.object(entities,'create',side_effect=create):partial=jobs.apply(Store(),'user','owner',partial['job_id'])
        self.assertEqual((partial['status'],partial['position'],partial['successful_rows'],partial['documents_present']),('complete_with_errors',2,1,2))
        self.assertEqual(received[0]['entities']['Patient']['age'],25)
        self.assertEqual(self.source.read_bytes(),original)
        page=jobs.report('user','owner',partial['job_id']);bad=next(x for x in page['issues'] if x['severity']=='error')
        self.assertEqual((bad['stage'],bad['row'],bad['field']),('validation',2,'Patient.age'))
    def test_missing_required_mapping_is_critical_for_both_policies(self):
        for policy in ('strict','partial'):
            payload=self.upload(policy,{'Patient.age':'age'})
            with self.assertRaises(ImportFailure) as caught:jobs.start(Store(),'user','owner',payload)
            self.assertEqual(caught.exception.issue['severity'],'critical');self.assertEqual(caught.exception.issue['stage'],'mapping')
    def test_unknown_crs_is_critical_before_any_row(self):
        db=sqlite3.connect(self.source);db.execute('UPDATE gpkg_spatial_ref_sys SET organization_coordsys_id=999999999');db.commit();db.close()
        with self.assertRaises(ImportFailure) as caught:self.ready(self.upload('partial'))
        self.assertEqual(caught.exception.issue['code'],'unknown_crs')
    def test_database_unavailable_is_not_a_record_skip(self):
        store=Store()
        with patch.object(store,'command',side_effect=AutoReconnect('offline')):
            with self.assertRaises(ImportFailure) as caught:jobs.start(store,'user','owner',self.upload('partial'))
        self.assertEqual(caught.exception.issue['code'],'mongodb_unavailable')
    def test_record_geometry_failure_rejects_the_whole_source_row(self):
        db=sqlite3.connect(self.source);db.execute('UPDATE cases_points SET geom=NULL WHERE fid=2');db.commit();db.close()
        state=self.ready(self.upload('partial'));self.assertEqual((state['valid_rows'],state['rejected_rows']),(1,1))
        item=next(x for x in state['errors'] if x['row']==2);self.assertEqual(item['field'],'Geodata.geometry')
    def test_all_diagnostics_survive_more_than_100_errors(self):
        db=sqlite3.connect(self.source);row=db.execute('SELECT * FROM cases_points LIMIT 1').fetchone();db.execute('DELETE FROM cases_points')
        db.executemany('INSERT INTO cases_points VALUES(?,?,?,?,?,?,?,?)',[(i,row[1],row[2],'invalid',*row[4:]) for i in range(1,306)]);db.commit();db.close()
        state=self.ready(self.upload('partial'));self.assertEqual(state['error_total'],305)
        items=[];after=0
        while True:
            page=jobs.report('user','owner',state['job_id'],after,37);items+=page['issues']
            if page['next'] is None:break
            after=page['next']
        self.assertEqual({x['row'] for x in items if x['severity']=='error'},set(range(1,306)))
        self.assertEqual(len({x['id'] for x in items}),len(items))
    def test_optional_null_is_warning_not_error(self):
        db=sqlite3.connect(self.source);db.execute('ALTER TABLE cases_points ADD COLUMN height REAL');db.commit();db.close()
        state=self.ready(self.upload('partial',{**self.targets,'Geodata.Elevation':'height'}))
        self.assertEqual((state['status'],state['error_total']),('ready',0));self.assertGreaterEqual(state['warning_total'],2)
        self.assertTrue(any(x['field']=='Geodata.Elevation' for x in jobs.report('user','owner',state['job_id'])['issues']))
    def test_infrastructure_failure_stops_and_resumes_same_row(self):
        state=self.ready(self.upload('partial'));calls=[]
        def create(store,role,owner,item,**kwargs):
            calls.append(item['request_id'])
            if len(calls)==1:raise AutoReconnect('ack lost')
            return {'ids':{'Patient':'p','Geodata':'g'},'created_by_job':{'Patient':1,'Geodata':1}}
        with patch.object(entities,'create',side_effect=create):
            state=jobs.apply(Store(),'user','owner',state['job_id']);self.assertEqual((state['status'],state['position']),('blocked',0))
            state=jobs.apply(Store(),'user','owner',state['job_id'])
        self.assertEqual(calls[0],calls[1]);self.assertEqual((state['status'],state['successful_rows'],state['documents_present']),('complete',2,4))
    def test_write_forbidden_never_continues_partial_file(self):
        state=self.ready(self.upload('partial'))
        with patch.object(entities,'create',side_effect=OperationFailure('denied',13)) as writer:
            state=jobs.apply(Store(),'user','owner',state['job_id']);self.assertEqual(writer.call_count,1)
        self.assertEqual((state['status'],state['position']),('blocked',0));self.assertEqual(state['last_error']['code'],'mongodb_forbidden')
    def test_row_write_error_partial_has_explicit_rejection_strict_stops(self):
        for policy in ('strict','partial'):
            state=self.ready(self.upload(policy));calls=[]
            def create(store,role,owner,item,**kwargs):
                calls.append(item)
                if len(calls)==1:raise ApiError(422,'Therapy.patient: target missing or not accessible')
                return {'ids':{'Patient':'p','Geodata':'g'},'created_by_job':{'Patient':1,'Geodata':1}}
            with patch.object(entities,'create',side_effect=create):state=jobs.apply(Store(),'user','owner',state['job_id'])
            self.assertEqual(state['status'],'failed' if policy=='strict' else 'complete_with_errors')
            self.assertEqual(state['successful_rows'],0 if policy=='strict' else 1)
            self.assertEqual(state['last_error']['field'],'Therapy.patient')
    def test_corrupt_uploaded_file_blocks_validation_and_keeps_report(self):
        state=jobs.start(Store(),'user','owner',self.upload('partial'));path=files.path_for(jobs.status('user','owner',state['job_id'])['payload']['upload_id'],'owner');path.write_bytes(b'broken')
        state=jobs.validate(Store(),'user','owner',state['job_id']);self.assertEqual(state['status'],'blocked')
        self.assertEqual(state['last_error']['severity'],'critical');self.assertTrue(jobs.report('user','owner',state['job_id'])['issues'])

    def test_transform_failure_is_record_geometry_error(self):
        from pyproj.exceptions import ProjError
        with patch.object(mapping,'point',side_effect=ProjError('Invalid coordinate')):
            state=self.ready(self.upload('partial'))
        self.assertEqual((state['status'],state['rejected_rows'],state['critical_total']),('invalid',2,0))
        self.assertTrue(all(x['field']=='Geodata.geometry' for x in state['errors']))
    def test_legacy_job_upgrade_keeps_rows_and_does_not_repeat_issues(self):
        from bson import json_util
        state=self.ready(self.upload());identifier=state['job_id']
        path=jobs.job_path(identifier,'owner');db=sqlite3.connect(path)
        original_rows=db.execute('SELECT seq,source_key,payload FROM rows').fetchall()
        old=json_util.loads(db.execute('SELECT value FROM state').fetchone()[0]);old.pop('report_v2')
        old['errors']=[{'row':2,'detail':'historical error'}]
        db.execute('DROP TABLE issues');db.execute('ALTER TABLE rows RENAME TO old_rows')
        db.execute('CREATE TABLE rows(seq INTEGER PRIMARY KEY,source_key TEXT UNIQUE NOT NULL,payload TEXT NOT NULL)')
        db.executemany('INSERT INTO rows VALUES(?,?,?)',original_rows);db.execute('DROP TABLE old_rows')
        db.execute('UPDATE state SET value=?',(json_util.dumps(old),));db.commit();db.close()
        for _ in range(2):
            self.assertEqual(jobs.report('user','owner',identifier)['issues_total'],1)
        db=sqlite3.connect(path);self.assertEqual(db.execute('SELECT seq,source_key,payload FROM rows').fetchall(),original_rows);db.close()
