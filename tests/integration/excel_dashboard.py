"""Real MongoDB, full XLSX, backend and Streamlit regression. ISOLATED test only."""
import json
import os
from pathlib import Path
import sys
import time
import urllib.request

if os.getenv('ISOLATED_STORAGE_TEST')!='1': raise RuntimeError('Isolated test required')
root=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(root/'backend'),str(root/'dashboard')]
from app.database.mongodb import MongoDB
from app.modules.import_excel import execute
store=MongoDB()
try:
    start=time.monotonic()
    report=execute(os.environ['TEST_XLSX'],'test-dataset-a',store)
    assert report['documents']['Patient']==37662
    assert report['documents']['Geodata']==14233
    assert report['documents']['Region']==61
    db=store.database('reader')
    source_count=sum(report['rows'].values())
    assert db.cases.count_documents({'source':'xlsx:'+report['sha256']})==source_count
    assert db.Instances.count_documents({'patient':{'$type':'objectId'}})==37662
    assert db.Patient.count_documents({'gender':{'$type':'objectId'}})==37662
    assert db.Foci.count_documents({})==0
    assert db.Therapy.count_documents({})==0
    assert db.Patient.count_documents({'medical_record.vaccine':{'$type':'regex'}})>0
    first=db.Geodata.find_one({})
    store.database('processor').Geodata.update_one({'_id':first['_id']},{'$set':{'Elevation':123.0}})
    again=execute(os.environ['TEST_XLSX'],'test-dataset-a',store)
    assert all(value==0 for value in again['inserted'].values()),again['inserted']
    assert db.Geodata.find_one({'_id':first['_id']})['Elevation']==123.0
    for route in ('/v1/statistics','/v1/overview?role=reader','/v1/overview?role=guest'):
        with urllib.request.urlopen('http://127.0.0.1:8000'+route,timeout=30) as response: data=json.load(response)
        if route=='/v1/statistics':
            assert data['counts']['Patient']==37662
            assert sum(x['count'] for x in data['ages'])==37662
            assert sum(x['count'] for x in data['dates'])==37662
            assert data['map_shown']==5000
        else:
            assert len(data['records'])==2500
            assert all(r['severity']=='Не указана' for r in data['records'])
    os.environ['BACKEND_URL']='http://127.0.0.1:8000'
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_file(str(root/'dashboard/app.py'),default_timeout=45).run()
    assert not app.exception, [e.message for e in app.exception]
    assert not app.error, [e.value for e in app.error]
    app.sidebar.selectbox[0].select(('guest','Внешний исследователь (Гость — адреса скрыты)')).run()
    assert not app.exception and not app.error
    Path(os.environ['TEST_REPORT']).write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print('PASS full XLSX import, repeat without duplicates, preserve edits, HTTP statistics, Streamlit reader/guest;',
          source_count,'source rows;',round(time.monotonic()-start,1),'seconds',flush=True)
finally: store.close()
