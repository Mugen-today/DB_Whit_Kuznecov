"""Run against a disposable, pre-populated MongoDB; compare --project versions.
No source datasets are needed. Emits JSON metrics, never modifies source documents.
"""
import argparse,sys,json,time,tracemalloc,hashlib,statistics,tempfile,sqlite3
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--project',type=Path,required=True);parser.add_argument('--mode',choices=['overview','geometry','validation'],required=True);parser.add_argument('--limit',type=int,default=500);args=parser.parse_args()
sys.path.insert(0,str(args.project.resolve()));sys.path.insert(0,str(args.project.resolve()/'tests/integration'))
from backend.app.database.mongodb import MongoDB
from backend.app.modules import export_data,geometry,gpkg_jobs as jobs,gpkg_uploads as files
from pymongo import MongoClient,monitoring
from bson import BSON
class Listener(monitoring.CommandListener):
    def __init__(self):self.count=0;self.bytes=0;self.wire=False
    def started(self,e):self.count+=1
    def succeeded(self,e):
        if self.wire:self.bytes+=len(BSON.encode(e.reply))
    def failed(self,e):pass
listener=Listener()
def factory(*a,**kw):return MongoClient(*a,**kw,event_listeners=[listener])
store=MongoDB(client_factory=factory);store.ready()
def overview():
    digest=hashlib.sha256();after=None;n=0;pages=0
    while True:
        page=export_data.execute(store,role='reader',params={'limit':[str(args.limit)],**({'after':[after]} if after else {})})
        digest.update(json.dumps(page['records'],ensure_ascii=False,sort_keys=True).encode());n+=len(page['records']);pages+=1;after=page['next']
        if not after:break
    return {'rows':n,'pages':pages,'sha256':digest.hexdigest()}
def geometries():
    records=[{'_id':str(i),'geometry':{'type':'Point','coordinates':[3339584.723798207,8399737.889818357],'crs':{'type':'name','properties':{'name':'EPSG:3857'}}}} for i in range(1000)]
    data=geometry.features(records)
    return {'rows':len(data),'sha256':hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()}
def validation():
    from gpkg_fixture import build
    with tempfile.TemporaryDirectory() as folder:
        p=Path(folder)/'shared.gpkg';build(p);db=sqlite3.connect(p);row=db.execute('SELECT * FROM cases_points LIMIT 1').fetchone();db.execute('DELETE FROM cases_points');db.execute('ALTER TABLE cases_points ADD COLUMN patient_id TEXT')
        patient=store.database('user').Patient.find_one({'_owner_id':'qgis-user'},{'_id':1})['_id']
        db.executemany('INSERT INTO cases_points VALUES(?,?,?,?,?,?,?,?,?)',[(i,*row[1:],str(patient)) for i in range(1,1004)]);db.commit();db.close()
        info=files.upload(p.read_bytes(),'qgis-user');payload={'upload_id':info['upload_id'],'table':'cases_points','mapping':{'Therapy.patient':'patient_id','Therapy.date_start':'started','Therapy.diagnosis':'diagnosis'},'use_geometry':False,'mode':'entities'}
        state=jobs.start(store,'user','qgis-user',payload)
        while state['status']=='validating':state=jobs.validate(store,'user','qgis-user',state['job_id'])
        assert state['status']=='ready',state
        return {'rows':state['checked'],'valid_rows':state['valid_rows']}
run={'overview':overview,'geometry':geometries,'validation':validation}[args.mode]
# Warm connection, MongoDB cache, imports and CRS library before measurement.
run();samples=[];peaks=[];commands=[];result=None
for _ in range(3):
    listener.count=0;tracemalloc.start();started=time.perf_counter();result=run();samples.append(time.perf_counter()-started);peaks.append(tracemalloc.get_traced_memory()[1]);tracemalloc.stop();commands.append(listener.count)
listener.count=0;listener.bytes=0;listener.wire=True;check=run();listener.wire=False;assert result==check
print(json.dumps({'mode':args.mode,'project_version':str(args.project),'limit':args.limit,'seconds':samples,'median_seconds':statistics.median(samples),'peak_python_bytes':max(peaks),'commands':commands,'mongo_reply_bson_bytes':listener.bytes,**result}),flush=True)
store.close()
