"""HTTP contract smoke test. Safe only against disposable test databases."""
import json, os, uuid, copy
from urllib.request import Request, urlopen
from urllib.error import HTTPError
BASE=os.getenv('QGIS_TEST_BACKEND','http://backend:8000')
def request(method,path,payload=None,token=None,expected=200):
    req=Request(BASE+path,data=json.dumps(payload).encode() if payload is not None else None,
        headers={'Authorization':'Bearer '+(token if token is not None else os.environ['QGIS_USER_TOKEN']),'Content-Type':'application/json'},method=method)
    try: res=urlopen(req,timeout=20)
    except HTTPError as e:res=e
    with res:
        data=json.load(res)
        assert res.status==expected,(method,path,res.status,data)
        return data
def sample():
    return {'request_id':str(uuid.uuid4()),'entities':{
        'Geodata':{'Longitude':30.0,'Latitude':60.0},'Instances':{'date':'2026-11-10'},
        'Patient':{'passport':'0012345678','age':29,'reg_date':'2026-11-10'},
        'Therapy':{'date_start':'2026-11-10','diagnosis':['A00']}}}
def run():
    request('GET','/v1/collections',token='',expected=401)
    for name,keys in {'Geodata':['Longitude','Latitude'],'Instances':['date'],'Patient':['passport','age','reg_date'],'Therapy':['date_start','diagnosis']}.items():
        for key in keys:
            p=sample();del p['entities'][name][key]
            request('POST','/v1/records',p,expected=422)
    for name in sample()['entities']:
        p=sample();del p['entities'][name]
        request('POST','/v1/records',p,expected=422)
    p=sample();first=request('POST','/v1/records',p)
    assert first==request('POST','/v1/records',p)
    changed=copy.deepcopy(p);changed['entities']['Patient']['age']=30
    request('POST','/v1/records',changed,expected=409)
    request('POST','/v1/records',sample(),token=os.environ['QGIS_GUEST_TOKEN'],expected=403)
    request('GET','/v1/collections/Street',token=os.environ['QGIS_GUEST_TOKEN'],expected=403)
    request('POST','/v1/qgis/points',{'longitude':0,'latitude':0},expected=422)
    request('POST','/v1/import-gpkg',{},expected=422)
    request('POST','/v1/collections/Patient',{},expected=405)
    for name in first['ids']:
        page=request('GET','/v1/collections/'+name+'?limit=1')
        assert len(page['records'])<=1
    path='/v1/collections/Patient/'+first['ids']['Patient']
    edit={'revision':1,'changes':{'age':30}}
    assert request('PATCH',path,edit)['age']==30
    request('PATCH',path,edit,expected=409)
    request('PATCH',path,{'revision':2,'changes':{'passport':''}},expected=422)
    request('PATCH',path,{'revision':2,'changes':{'_id':'a'}},expected=422)
    return first
if __name__=='__main__':
    run();print('PASS strict records HTTP')
