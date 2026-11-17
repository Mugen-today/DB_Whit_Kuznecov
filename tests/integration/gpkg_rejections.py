import os,json,tempfile
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from gpkg_fixture import build,MAPPING
from records_http import request
BASE=os.environ['QGIS_TEST_BACKEND']
def upload(path,guest=False):
    key='QGIS_GUEST_TOKEN' if guest else 'QGIS_USER_TOKEN'
    req=Request(BASE+'/v1/gpkg/upload',data=path.read_bytes(),headers={'Content-Type':'application/octet-stream','Authorization':'Bearer '+os.environ[key]},method='POST')
    try:res=urlopen(req,timeout=20)
    except HTTPError as e:res=e
    with res:
        data=json.load(res);assert res.status==(403 if guest else 200),(res.status,data);return data
def run():
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'invalid.gpkg';build(path,invalid=True)
        upload(path,guest=True);info=upload(path)
        payload={'upload_id':info['upload_id'],'table':'cases_points','mapping':MAPPING,'use_geometry':True}
        request('POST','/v1/gpkg/validate',payload,expected=422)
        request('POST','/v1/gpkg/apply',payload,expected=422)
        request('POST','/v1/gpkg/validate',payload,token=os.environ['QGIS_GUEST_TOKEN'],expected=403)
        payload['table']='cases_points"; DROP TABLE cases_points;--'
        request('POST','/v1/gpkg/validate',payload,expected=422)
    from comprehensive_http import call,console
    count=console('db.Geodata.countDocuments({})')['value']
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'bad-crs.gpkg';build(path)
        import sqlite3
        db=sqlite3.connect(path);db.execute('UPDATE gpkg_geometry_columns SET srs_id=4326');db.commit();db.close()
        info=upload(path)
        partial={'upload_id':info['upload_id'],'table':'cases_points','mapping':{},'use_geometry':True,'mode':'entities'}
        call('POST','/v1/gpkg/validate',partial,status=422);call('POST','/v1/gpkg/apply',partial,status=422)
        info=upload(path)
        invalid_fk={**partial,'upload_id':info['upload_id'],'use_geometry':False,'mapping':{'Therapy.patient':'passport','Therapy.date_start':'started','Therapy.diagnosis':'diagnosis'}}
        call('POST','/v1/gpkg/validate',invalid_fk,status=422)
        db=sqlite3.connect(path);db.execute("UPDATE cases_points SET age='invalid integer'");db.commit();db.close()
        info=upload(path)
        wrong_type={**partial,'upload_id':info['upload_id'],'use_geometry':False,'mapping':{k:v for k,v in MAPPING.items() if k.startswith('Patient.')}}
        call('POST','/v1/gpkg/validate',wrong_type,status=422)
    assert console('db.Geodata.countDocuments({})')['value']==count
    print('PASS CRS mismatch, invalid FK/type and no writes on failed validation')
    print('PASS GPKG rejection of invalid row, forged table and guest writes')
if __name__=='__main__':run()
