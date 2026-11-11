"""Optional native regression: MONGOD_BINARY, MONGOSH_BINARY, QGIS_PYTHON; disposable data only."""
from pathlib import Path
import tempfile, subprocess, os, time, socket, sys, importlib.util, json
ROOT=Path(__file__).resolve().parents[2]
MONGOD=os.environ['MONGOD_BINARY']
MONGOSH=os.environ['MONGOSH_BINARY']
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests/integration'))
from pymongo import MongoClient
from bson import ObjectId
import records_http
records_http.BASE="http://127.0.0.1:8000"
from records_http import run,request,sample
spec=importlib.util.spec_from_file_location('manage',ROOT/'scripts/manage.py')
manage=importlib.util.module_from_spec(spec);spec.loader.exec_module(manage)
def wait(port,p):
    for _ in range(150):
        if p.poll() is not None: raise RuntimeError('Process failed '+str(p.returncode))
        try:
            with socket.create_connection(('127.0.0.1',port),.2):return
        except OSError:time.sleep(.1)
    raise RuntimeError('Start timeout')
for port in (27917,8000):
    try:
        check=socket.create_connection(('127.0.0.1',port),.2)
    except OSError:
        continue
    check.close()
    raise RuntimeError('Test port already occupied: '+str(port))
for n in (1,2):
    with tempfile.TemporaryDirectory(prefix='strict-native-') as folder:
        tmp=Path(folder);(tmp/'data').mkdir()
        manage.initialize(tmp/'.env')
        env=os.environ|manage.env_values(tmp/'.env')
        env.update(MONGO_INITDB_ROOT_USERNAME=env['MONGO_ROOT_USER'],MONGO_INITDB_ROOT_PASSWORD=env['MONGO_ROOT_PASSWORD'],
            MONGO_HOST='127.0.0.1',MONGO_PORT='27917',STORAGE_SCHEMA_PATH=str(ROOT/'storage/schema/model.json'),
            PYTHONPATH=os.environ.get('PYTHONPATH','')+os.pathsep+str(ROOT),QGIS_TEST_BACKEND='http://127.0.0.1:8000',QT_QPA_PLATFORM='offscreen')
        os.environ.update({k:v for k,v in env.items() if 'TOKEN' in k or k=='QGIS_TEST_BACKEND'})
        for source,target in [('storage/init','init'),('storage/scripts','storage')]:
            (tmp/target).mkdir()
            for f in (ROOT/source).glob('*.js'):
                text=f.read_text().replace('/opt/schema/',str(ROOT/'storage/schema')+'/').replace('/opt/',str(tmp)+'/').replace('127.0.0.1:27017','127.0.0.1:27917').replace('storage:27017','127.0.0.1:27917')
                (tmp/target/f.name).write_text(text)
        log=open(str(Path(tempfile.gettempdir())/f'strict-mongo-{n}.log'),'w')
        mongo=subprocess.Popen([MONGOD,'--dbpath',str(tmp/'data'),'--port','27917','--bind_ip','127.0.0.1','--nounixsocket','--wiredTigerCacheSizeGB','0.25'],stdout=log,stderr=log)
        backend=None
        try:
            wait(27917,mongo)
            admin=MongoClient('mongodb://127.0.0.1:27917/?directConnection=true')
            admin.admin.command('createUser',env['MONGO_ROOT_USER'],pwd=env['MONGO_ROOT_PASSWORD'],roles=['root'])
            subprocess.run([MONGOSH,'mongodb://127.0.0.1:27917/Schema','--quiet',str(tmp/'init/bootstrap.js')],env=env,check=True,timeout=60)
            # Restart with authentication and the same replica data before API testing.
            import base64
            key=tmp/'replica.key';key.write_bytes(base64.b64encode(os.urandom(512)));key.chmod(0o600)
            mongo.terminate();mongo.wait(timeout=20);admin.close()
            mongo=subprocess.Popen([MONGOD,'--dbpath',str(tmp/'data'),'--port','27917','--bind_ip','127.0.0.1','--nounixsocket','--replSet','rs0','--keyFile',str(key),'--auth','--wiredTigerCacheSizeGB','0.25'],stdout=log,stderr=log)
            wait(27917,mongo)
            subprocess.run([MONGOSH,'--nodb','--quiet',str(tmp/'storage/provision.js')],env=env,check=True,timeout=60)
            admin=MongoClient('127.0.0.1',27917,username=env['MONGO_ROOT_USER'],password=env['MONGO_ROOT_PASSWORD'],authSource='admin',serverSelectionTimeoutMS=10000)
            for _ in range(100):
                if admin.admin.command('hello')['isWritablePrimary']:break
                time.sleep(.1)
            db=admin.Schema
            with open(str(Path(tempfile.gettempdir())/f'strict-backend-{n}.log'),'w') as output:
                backend=subprocess.Popen([sys.executable,'-m','app.main'],cwd=ROOT/'backend',env=env,stdout=output,stderr=output)
            wait(8000,backend)
            result=run()
            geo=db.Geodata.find_one()
            assert geo['geometry']['coordinates']==[geo['Longitude'],geo['Latitude']]
            request('POST','/v1/console',{'code':'__import__("os").system("id")'},expected=400)
            assert request('POST','/v1/console',{'code':'db.Patient.find({}).limit(10)'})['records']

            pat=db.Patient.find_one({'_id':ObjectId(result['ids']['Patient'])})
            assert pat['age']==30 and pat['passport']=='0012345678'
            assert db.Therapy.find_one()['patient']==pat['_id']
            # Deliberately reject the last collection: earlier inserts must roll back.
            counts={name:db[name].count_documents({}) for name in db.list_collection_names()}
            db.command('collMod','Foci',validator={'_rollback_test':{'$exists':True}},validationAction='error')
            request('POST','/v1/records',sample(),expected=503)
            assert counts=={name:db[name].count_documents({}) for name in db.list_collection_names()}
            subprocess.run([MONGOSH,'mongodb://127.0.0.1:27917/Schema','--quiet','--eval',"load('"+str(tmp/'storage/admin.js')+"');load('"+str(tmp/'init/schema.js')+"');"],env=env,check=True,timeout=35)
            address=sample();del address['entities']['Geodata']
            address['entities'].update(Region={'name':'R'},Municipality={'name':'M'},Settlement={'name':'S','type':'city'},
                Street={'name':'St'},Building={'house':1,'corpus':0,'edificate':0,'fraction':0,'letters':0})
            # Concurrent retry must return a single set of IDs.
            from concurrent.futures import ThreadPoolExecutor
            concurrent=sample()
            with ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(lambda _:request('POST','/v1/records',concurrent), range(2)))
            assert results[0]==results[1]
            # Foreign-owned documents cannot be changed.
            foreign=ObjectId()
            db.Patient.insert_one({'_id':foreign,'_owner_id':'another-user','passport':'000','age':25,'reg_date':__import__('datetime').datetime.now()})
            request('PATCH','/v1/collections/Patient/'+str(foreign),{'revision':0,'changes':{'age':26}},expected=404)
            assert str(foreign) not in {d['_id'] for d in request('GET','/v1/collections/Patient')['records']}
            a=request('POST','/v1/records',address)
            assert db.Region.find_one()['municipality']==ObjectId(a['ids']['Municipality'])
            request('GET','/v1/statistics',token=env['DASHBOARD_TOKEN'])
            request('GET','/v1/dashboard',token=env['DASHBOARD_TOKEN'])
            subprocess.run([os.environ.get('QGIS_PYTHON',sys.executable),str(ROOT/'tests/integration/records_qgis.py')],env=env,check=True,timeout=60)
            assert db.Patient.count_documents({'age':42})>=1
            # A server restart must preserve the committed records.
            total=db.Patient.count_documents({})
            mongo.terminate();mongo.wait(timeout=20)
            mongo=subprocess.Popen([MONGOD,'--dbpath',str(tmp/'data'),'--port','27917','--bind_ip','127.0.0.1','--nounixsocket','--replSet','rs0','--keyFile',str(key),'--auth','--wiredTigerCacheSizeGB','0.25'],stdout=log,stderr=log)
            wait(27917,mongo)
            from pymongo.errors import OperationFailure, AutoReconnect
            for attempt in range(100):
                try:
                    assert db.Patient.count_documents({})==total
                    break
                except (OperationFailure,AutoReconnect):
                    if attempt==99:raise
                    time.sleep(.2)
            print('PASS cycle',n,'HTTP, all fields, linked IDs, retry, revision, rollback, address, dashboard, PyQGIS',flush=True)
        finally:
            if backend:backend.terminate();backend.wait(timeout=10)
            mongo.terminate();mongo.wait(timeout=20);log.close()
