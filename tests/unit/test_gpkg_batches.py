"""Real SQLite/disk and deterministic fake MongoDB writes; no Docker needed."""
import unittest,tempfile,sqlite3,json,sys,importlib
from pathlib import Path
from unittest.mock import patch
from backend.app.modules import gpkg_uploads as files,gpkg_jobs as jobs,gpkg_import as mapping
from backend.app.modules.qgis_data import ApiError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integration'))
from gpkg_fixture import build
class NoLinksStore:
    def database(self,role):return self
    def __getitem__(self,name):raise AssertionError('Geometry-only fixture must not query foreign keys')
class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);p=patch.object(files,'ROOT',self.root/'uploads');p.start();self.addCleanup(p.stop)
        self.source=self.root/'source.gpkg';build(self.source)
        db=sqlite3.connect(self.source);template=db.execute('SELECT * FROM cases_points LIMIT 1').fetchone();db.execute('DELETE FROM cases_points')
        db.executemany('INSERT INTO cases_points VALUES(?,?,?,?,?,?,?,?)',[(i,*template[1:]) for i in range(1,1004)]);db.commit();db.close()
        self.info=files.upload(self.source.read_bytes(),'test');self.payload={'upload_id':self.info['upload_id'],'table':'cases_points','mapping':{},'use_geometry':True,'mode':'entities'}
    def ready(self,payload=None):
        state=jobs.start(NoLinksStore(),'user','test',payload or self.payload);identifier=state['job_id'];steps=0
        while state['status']=='validating':
            state=jobs.validate(NoLinksStore(),'user','test',identifier);steps+=1
            self.assertLessEqual(state['checked'],steps*jobs.VALIDATE_BATCH)
        return state,steps
    def test_1003_rows_are_not_a_batch_size_limit_and_restart_is_durable(self):
        state,steps=self.ready();self.assertGreater(steps,1);self.assertEqual(state['checked'],1003);self.assertTrue(state['valid'])
        seen={};calls=[]
        def write(store,role,owner,item,**kwargs):
            calls.append(item['request_id']);seen[item['request_id']]=item
        with patch.object(jobs.entities,'create',side_effect=write):
            state=jobs.apply(NoLinksStore(),'user','test',state['job_id']);self.assertEqual(state['applied'],25)
            # New module has no in-memory cursor/cache: reopen the disk job.
            importlib.reload(jobs)
            while state['status']!='complete':state=jobs.apply(NoLinksStore(),'user','test',state['job_id'])
            jobs.apply(NoLinksStore(),'user','test',state['job_id'])
        self.assertEqual((len(seen),len(calls)),(1003,1003));self.assertEqual(state['applied'],1003)
    def test_late_invalid_row_prevents_any_apply(self):
        db=sqlite3.connect(self.source);db.execute('UPDATE cases_points SET geom=NULL WHERE fid=1003');db.commit();db.close()
        info=files.upload(self.source.read_bytes(),'test');state,steps=self.ready({**self.payload,'upload_id':info['upload_id']})
        self.assertEqual(state['status'],'invalid');self.assertEqual(state['errors'][0]['row'],1003)
        with patch.object(jobs.entities,'create') as write:
            with self.assertRaises(ApiError):jobs.apply(NoLinksStore(),'user','test',state['job_id'])
            write.assert_not_called()
    def test_retry_after_commit_before_checkpoint_does_not_lose_rows(self):
        state,_=self.ready();seen={};failed=[False]
        def write(store,role,owner,item,**kwargs):
            seen[item['request_id']]=item
            if len(seen)==12 and not failed[0]:failed[0]=True;raise OSError('Simulated lost confirmation after MongoDB commit')
        with patch.object(jobs.entities,'create',side_effect=write):
            state=jobs.apply(NoLinksStore(),'user','test',state['job_id']);self.assertEqual(state['status'],'paused');self.assertEqual(state['applied'],11)
            while state['status']!='complete':state=jobs.apply(NoLinksStore(),'user','test',state['job_id'])
        self.assertEqual((state['applied'],len(seen)),(1003,1003))
    def test_upload_replay_and_wrong_owner(self):
        raw=self.source.read_bytes();state=files.begin({'size':len(raw)},'test');identifier=state['upload_id'];part=raw[:100]
        files.chunk(identifier,'test',0,part);self.assertEqual(files.chunk(identifier,'test',0,part)['received'],100)
        with self.assertRaises(ApiError):files.chunk(identifier,'test',0,b'x'*100)
        with self.assertRaises(ApiError):files.status(identifier,'other')
        files.chunk(identifier,'test',100,raw[100:]);self.assertTrue(files.finish(identifier,'test')['complete'])
    def test_composite_key_pages_preserve_all_rows(self):
        with sqlite3.connect(self.source) as db:
            db.executescript("CREATE TABLE attrs(a TEXT,b INTEGER,passport TEXT,age INTEGER,registered TEXT,PRIMARY KEY(a,b)); INSERT INTO gpkg_contents(table_name,data_type,identifier) VALUES('attrs','attributes','attrs');")
            db.executemany('INSERT INTO attrs VALUES(?,?,?,?,?)',[(str(i//7),i,'P'+str(i),20,'2026-11-11') for i in range(1003)])
        info=files.upload(self.source.read_bytes(),'test')
        payload={**self.payload,'upload_id':info['upload_id'],'table':'attrs','use_geometry':False,'mapping':{'Patient.passport':'passport','Patient.age':'age','Patient.reg_date':'registered'}}
        docs=list(mapping.build(payload,'test'));self.assertEqual(len(docs),1003);self.assertEqual(len({d['request_id'] for d in docs}),1003)

    def test_byte_bounded_page_is_not_mistaken_for_end_of_table(self):
        from unittest.mock import MagicMock
        # Valid diagnosis lists make a page exceed 2 MiB before 250 rows.
        db=sqlite3.connect(self.source);db.execute('UPDATE cases_points SET diagnosis=?',(json.dumps(['D'*100]*200),));db.commit();db.close()
        info=files.upload(self.source.read_bytes(),'test')
        payload={**self.payload,'upload_id':info['upload_id'],'use_geometry':False,'mapping':{'Therapy.patient':'passport','Therapy.date_start':'started','Therapy.diagnosis':'diagnosis'}}
        # Supply a well-formed existing Patient ID; fake only its FK lookup.
        db=sqlite3.connect(self.source);db.execute("UPDATE cases_points SET passport='012345678901234567890123'");db.commit();db.close()
        info=files.upload(self.source.read_bytes(),'test');payload['upload_id']=info['upload_id']
        store=MagicMock();store.database.return_value.__getitem__.return_value.find_one.return_value={'_id':'exists'}
        state=jobs.start(store,'user','test',payload);state=jobs.validate(store,'user','test',state['job_id'])
        self.assertLess(state['checked'],250);self.assertEqual(state['status'],'validating')
        while state['status']=='validating':state=jobs.validate(store,'user','test',state['job_id'])
        self.assertEqual((state['status'],state['checked']),('ready',1003))

    def test_expired_cache_removed_but_active_upload_and_unrelated_files_retained(self):
        import os,time
        old=self.info['upload_id'];manifest=files.manifest(old,'test')
        os.utime(manifest,(time.time()-files.TTL-10,)*2)
        unrelated=files.ROOT/'settings.json';unrelated.write_text('{}');os.utime(unrelated,(0,0))
        active=files.begin({'size':16},'test')
        self.assertFalse(manifest.exists());self.assertTrue(unrelated.exists())
        self.assertEqual(files.status(active['upload_id'],'test')['received'],0)
    def test_legacy_next_offset_uses_actual_byte_bounded_import_progress(self):
        from unittest.mock import MagicMock
        db=sqlite3.connect(self.source);db.execute('DELETE FROM cases_points WHERE fid>7')
        db.execute("UPDATE cases_points SET passport='012345678901234567890123',diagnosis=?",(json.dumps(['D'*1900]*200),));db.commit();db.close()
        info=files.upload(self.source.read_bytes(),'test')
        payload={**self.payload,'upload_id':info['upload_id'],'use_geometry':False,'mapping':{'Therapy.patient':'passport','Therapy.date_start':'started','Therapy.diagnosis':'diagnosis','Therapy.effect_treatment':'diagnosis'}}
        store=MagicMock();store.database.return_value.__getitem__.return_value.find_one.return_value={'_id':'exists'}
        calls=[]
        with patch.object(jobs.entities,'create',side_effect=lambda store,role,owner,item:calls.append(item['request_id'])):
            first=jobs.legacy(store,'user','test',payload,True)
            self.assertLess(first['saved'],7);self.assertEqual(first['next_offset'],first['saved'])
            page=first
            while page['next_offset'] is not None:
                page=jobs.legacy(store,'user','test',{**payload,'offset':page['next_offset']},True)
        self.assertEqual((len(calls),len(set(calls))),(7,7))

    def test_attribute_guard_counts_utf8_bytes_not_characters(self):
        db=sqlite3.connect(self.source);db.execute('DELETE FROM cases_points WHERE fid>1')
        db.execute('UPDATE cases_points SET passport=?',('Я'*600000,));db.commit();db.close()
        info=files.upload(self.source.read_bytes(),'test')
        payload={**self.payload,'upload_id':info['upload_id'],'use_geometry':False,'mapping':{'Patient.passport':'passport','Patient.age':'age','Patient.reg_date':'registered'}}
        with self.assertRaisesRegex(ApiError,'per-value'):
            list(mapping.build(payload,'test'))
