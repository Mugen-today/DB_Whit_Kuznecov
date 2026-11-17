"""Error policies on real MongoDB; run only in the disposable A+B database."""
import tempfile,sqlite3,json,hashlib
from pathlib import Path
from comprehensive_http import call,console
from gpkg_fixture import build,MAPPING

def job(payload):
    state=call('POST','/v1/gpkg/jobs',payload)
    while state['status']=='validating':state=call('POST','/v1/gpkg/jobs/'+state['job_id']+'/validate',{})
    return state

def finish(state):
    while state['status'] in ('ready','importing'):state=call('POST','/v1/gpkg/jobs/'+state['job_id']+'/apply',{})
    return state

def main():
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'policy.gpkg';build(path)
        db=sqlite3.connect(path);row=db.execute('SELECT * FROM cases_points LIMIT 1').fetchone();db.execute('DELETE FROM cases_points')
        db.executemany('INSERT INTO cases_points VALUES(?,?,?,?,?,?,?,?)',[(i,row[1],'POLICY_'+str(i),25 if i!=2 else None,*row[4:]) for i in range(1,5)]);db.commit();db.close()
        digest=hashlib.sha256(path.read_bytes()).hexdigest();info=call('POST','/v1/gpkg/upload',path.read_bytes())
        payload={'upload_id':info['upload_id'],'table':'cases_points','mapping':{k:v for k,v in MAPPING.items() if k.startswith('Patient.')},'use_geometry':True,'mode':'entities'}
        before={n:console('db.'+n+'.countDocuments({})')['value'] for n in ('Patient','Geodata','Instances')}
        strict=job({**payload,'error_policy':'strict'});assert strict['status']=='invalid' and strict['documents_present']==0
        call('POST','/v1/gpkg/jobs/'+strict['job_id']+'/apply',{},status=409)
        assert all(console('db.'+n+'.countDocuments({})')['value']==v for n,v in before.items())
        partial=job({**payload,'error_policy':'partial'});assert partial['status']=='ready' and partial['rejected_rows']==1
        partial=finish(partial)
        assert (partial['status'],partial['successful_rows'],partial['documents_present'],partial['documents_created_by_job'])==('complete_with_errors',3,6,6),partial
        assert partial['by_collection']=={'Patient':3,'Geodata':3}
        assert console('db.Patient.countDocuments({passport:"POLICY_2"})')['value']==0
        assert console('db.Geodata.countDocuments({})')['value']==before['Geodata']+3
        assert console('db.Instances.countDocuments({})')['value']==before['Instances']
        report=call('GET','/v1/gpkg/jobs/'+partial['job_id']+'/report?limit=2');issues=[]
        while True:
            issues+=report['issues']
            if report['next'] is None:break
            report=call('GET','/v1/gpkg/jobs/'+partial['job_id']+'/report?limit=2&after='+str(report['next']))
        error=next(x for x in issues if x['severity']=='error');assert (error['stage'],error['row'],error['field'])==('validation',2,'Patient.age')
        # Retry entire file under another job: deterministic IDs, real receipts.
        repeated=finish(job({**payload,'error_policy':'partial'}))
        assert (repeated['documents_present'],repeated['documents_created_by_job'],repeated['documents_reused'])==(6,0,6)
        assert console('db.Patient.countDocuments({passport:/^POLICY_/})')['value']==3
        assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
        # Missing mappings and unknown CRS stop both modes before row processing.
        critical=call('POST','/v1/gpkg/jobs',{**payload,'mapping':{'Patient.age':'age'},'error_policy':'partial'},status=422)
        assert critical['issue']['severity']=='critical' and critical['issue']['stage']=='mapping'
        forbidden=call('POST','/v1/gpkg/jobs',payload,role='guest',status=403);assert forbidden['issue']['stage']=='authorization'
        print('PASS strict zero writes; partial row-level atomicity, geometry, real document receipts, complete report and idempotent replay',flush=True)
        # Existing FK failure is a row error, not a privilege/connection failure.
        db=sqlite3.connect(path);db.execute('ALTER TABLE cases_points ADD COLUMN patient_id TEXT');db.execute("UPDATE cases_points SET patient_id='000000000000000000000000'");db.commit();db.close()
        info=call('POST','/v1/gpkg/upload',path.read_bytes());bad={**payload,'upload_id':info['upload_id'],'use_geometry':False,'mapping':{'Therapy.patient':'patient_id','Therapy.date_start':'started','Therapy.diagnosis':'diagnosis'},'error_policy':'partial'}
        blocked=job(bad);assert blocked['status']=='invalid' and blocked['rejected_rows']==4
        assert all(x['field']=='Therapy.patient' for x in blocked['errors'])
        print('PASS missing/inaccessible foreign keys reported per row without fabricated references',flush=True)
        # Simulate a lost acknowledgement AFTER a real transaction commits.
        from backend.app.database.mongodb import MongoDB
        from backend.app.modules import gpkg_jobs,entities
        from pymongo.errors import AutoReconnect
        from unittest.mock import patch
        db=sqlite3.connect(path);db.execute("UPDATE cases_points SET age=25,passport='RECEIPT_'||fid");db.commit();db.close()
        info=call('POST','/v1/gpkg/upload',path.read_bytes());retry_payload={**payload,'upload_id':info['upload_id'],'error_policy':'strict'}
        checkpoint=job(retry_payload);assert checkpoint['status']=='ready'
        original_create=entities.create;lost=[False];store=MongoDB()
        def commit_then_lose(*args,**kwargs):
            result=original_create(*args,**kwargs)
            if not lost[0]:lost[0]=True;raise AutoReconnect('simulated acknowledgement loss after actual commit')
            return result
        try:
            with patch.object(entities,'create',side_effect=commit_then_lose):stopped=gpkg_jobs.apply(store,'user','qgis-user',checkpoint['job_id'])
            assert stopped['status']=='blocked' and stopped['successful_rows']==0
        finally:store.close()
        recovered=finish({**stopped,'status':'ready'})
        assert (recovered['successful_rows'],recovered['documents_present'],recovered['documents_created_by_job'])==(4,8,8),recovered
        assert console('db.Patient.countDocuments({passport:/^RECEIPT_/})')['value']==4
        print('PASS actual MongoDB commit followed by lost acknowledgement: safe replay and exact per-job document counts',flush=True)

if __name__=='__main__':main()
