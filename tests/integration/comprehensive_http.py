"""Comprehensive live API regression. Run only on the disposable snapshot database."""
import os,json,tempfile,sqlite3
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from gpkg_fixture import build,MAPPING
BASE=os.getenv('QGIS_TEST_BACKEND','http://127.0.0.1:8000')
KEYS={'user':'QGIS_USER_TOKEN','reader':'DASHBOARD_TOKEN','guest':'QGIS_GUEST_TOKEN','admin':'QGIS_ADMIN_TOKEN'}
def call(method,path,payload=None,role='user',username=None,status=200):
    headers={'Authorization':'Bearer '+os.environ[KEYS[role]],'Content-Type':'application/octet-stream' if isinstance(payload,bytes) else 'application/json'}
    if username:headers['X-GIS-User']=username
    req=Request(BASE+path,data=payload if isinstance(payload,bytes) else json.dumps(payload).encode() if payload is not None else None,headers=headers,method=method)
    try:res=urlopen(req,timeout=90)
    except HTTPError as e:res=e
    with res:
        data=json.load(res);assert res.status==status,(path,res.status,data);return data
def console(code,role='user',status=200):
    return call('POST','/v1/console',{'code':code},role,status=status)
def exhaust(page,role='user'):
    rows=page.get('records',[])
    while page.get('cursor'):
        page=call('POST','/v1/console',{'cursor':page['cursor']},role);rows+=page['records']
    return rows
def main():
    session=call('GET','/v1/session');assert len(session['collections'])==17 and session['can_write']
    assert len(call('GET','/v1/session',role='guest')['collections'])==13
    assert call('GET','/v1/session',role='reader')['can_write'] is False
    assert call('GET','/v1/session',role='admin',username='admin')['can_write']
    call('GET','/v1/session',username='guest',status=401)
    before=console('db.Patient.countDocuments({})')['value']
    assert before==41938
    all_rows=exhaust(console('db.Patient.find({})'))
    assert len(all_rows)==before and len({d['_id'] for d in all_rows})==before
    for name in session['collections']:
        docs=[];after=None
        while True:
            page=call('GET','/v1/collections/'+name+'?limit=200'+('&after='+after if after else ''))
            docs+=page['records'];after=page.get('next')
            if not after:break
        assert len(docs)==console('db.'+name+'.countDocuments({})')['value'],name
    print('PASS complete pagination of all 17 collections',flush=True)
    aggregate=exhaust(console('db.Patient.aggregate([{$group:{_id:null,n:{$sum:1}}}])'))
    assert aggregate[0]['n']==before
    genders=exhaust(console('db.Gender.distinct("type")'));assert len(genders)==2
    lookup=exhaust(console('db.Patient.aggregate([{$lookup:{from:"Gender",localField:"gender",foreignField:"_id",as:"g"}},{$unwind:"$g"},{$count:"n"}])'))
    assert lookup[0]['n']==console('db.Patient.countDocuments({gender:{$exists:true}})')['value']
    console('db.Patient.aggregate([{$merge:"Patient"}])',status=403)
    console('db.Patient.aggregate([{$lookup:{from:"Social_group",localField:"social_group",foreignField:"_id",as:"s"}}])','guest',403)
    console('db.Patient.aggregate([{$facet:{bad:[{$out:"Patient"}]}}])',status=403)
    near=exhaust(console('db.Geodata.aggregate([{$geoNear:{near:{type:"Point",coordinates:[30,60]},distanceField:"distance",spherical:true,maxDistance:1000000}},{$limit:5}])'))
    assert len(near)==5 and all(near[i]['distance']<=near[i+1]['distance'] for i in range(4))
    within=exhaust(console('db.Geodata.find({geometry:{$geoWithin:{$geometry:{type:"Polygon",coordinates:[[[20,50],[40,50],[40,65],[20,65],[20,50]]]}}}}).limit(7)'))
    assert len(within)==7
    near_find=exhaust(console('db.Geodata.find({geometry:{$near:{$geometry:{type:"Point",coordinates:[30,60]},$maxDistance:1000000}}}).limit(3)'))
    assert len(near_find)==3
    assert console('db.Patient.find({_id:ObjectId("'+all_rows[0]['_id']+'")})')['records'][0]['_id']==all_rows[0]['_id']
    print('PASS aggregate, scoped lookup, distinct, countDocuments, BSON and spatial queries',flush=True)
    # Historical missing passport must not block a valid age edit.
    doc=call('GET','/v1/collections/Patient?limit=1')['records'][0];old_age=doc.get('age')
    changed=call('PATCH','/v1/collections/Patient/'+doc['_key'],{'revision':doc['qgis_revision'],'changes':{'age':43}})
    assert changed['age']==43 and 'passport' not in changed
    call('PATCH','/v1/collections/Patient/'+doc['_key'],{'revision':doc['qgis_revision'],'changes':{'age':44}},status=409)
    call('PATCH','/v1/collections/Patient/'+doc['_key'],{'revision':changed['qgis_revision'],'changes':{'gender':'000000000000000000000000'}},status=422)
    call('PATCH','/v1/collections/Patient/'+doc['_key'],{'revision':changed['qgis_revision'],'changes':{'age':44}},role='reader',status=403)
    # Full traversal of analyst export, not only the first 2500 rows.
    exported=[];after=None
    while True:
        page=call('GET','/v1/overview?limit=500'+('&after='+after if after else ''),role='reader')
        exported+=page['records'];after=page.get('next')
        if not after:break
    assert len(exported)==41938
    print('PASS full analyst export and legacy document editing',flush=True)
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'points.gpkg';build(path)
        info=call('POST','/v1/gpkg/upload',path.read_bytes())
        partial={'upload_id':info['upload_id'],'table':'cases_points','mapping':{},'use_geometry':True,'mode':'entities'}
        assert call('POST','/v1/gpkg/validate',partial)['rows']==2
        patient_count=console('db.Patient.countDocuments({})')['value']
        geo_count=console('db.Geodata.countDocuments({})')['value']
        call('POST','/v1/gpkg/apply',partial);call('POST','/v1/gpkg/apply',partial)
        assert console('db.Patient.countDocuments({})')['value']==patient_count
        assert console('db.Geodata.countDocuments({})')['value']==geo_count+2
        call('POST','/v1/gpkg/validate',{**partial,'mode':'bundle'},status=422)
        # Partial Patient mapping: required fields only, no other collections required.
        db=sqlite3.connect(path);db.execute("UPDATE cases_points SET passport='PART_'||fid");db.commit();db.close()
        info=call('POST','/v1/gpkg/upload',path.read_bytes())
        patient_only={'upload_id':info['upload_id'],'table':'cases_points','mapping':{k:v for k,v in MAPPING.items() if k.startswith('Patient.')},'use_geometry':False,'mode':'entities'}
        call('POST','/v1/gpkg/validate',patient_only);call('POST','/v1/gpkg/apply',patient_only)
        assert console('db.Patient.countDocuments({})')['value']==patient_count+2
        bad={**patient_only,'mapping':{'Patient.age':'age'}}
        call('POST','/v1/gpkg/validate',bad,status=422)
        # Foreign key import into Therapy without creating a dummy Patient.
        db=sqlite3.connect(path);db.execute('ALTER TABLE cases_points ADD COLUMN patient_id TEXT')
        db.execute('UPDATE cases_points SET patient_id=?',(doc['_id'],));db.commit();db.close()
        info=call('POST','/v1/gpkg/upload',path.read_bytes())
        therapy={'upload_id':info['upload_id'],'table':'cases_points','mapping':{'Therapy.patient':'patient_id','Therapy.date_start':'started','Therapy.diagnosis':'diagnosis'},'use_geometry':False,'mode':'entities'}
        call('POST','/v1/gpkg/validate',therapy);call('POST','/v1/gpkg/apply',therapy)
        assert console('db.Patient.countDocuments({})')['value']==patient_count+2
    print('PASS partial GPKG entity import, strict bundle and validated existing foreign keys',flush=True)
if __name__=='__main__':main()
