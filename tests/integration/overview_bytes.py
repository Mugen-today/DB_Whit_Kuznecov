"""Variable byte-bound pages must retain every source row, without lost cursors."""
import json
from comprehensive_http import call
from backend.app.database.mongodb import MongoDB
store=MongoDB();db=store.database('user')
try:
    db.Therapy.update_many({'_owner_id':'qgis-user'},{'$set':{'other':'x'*3900}})
    expected=db.Instances.count_documents({'_owner_id':'qgis-user'});seen=[];after=None;pages=0
    while True:
        page=call('GET','/v1/overview?limit=1000'+('&after='+after if after else ''),role='reader')
        assert len(json.dumps(page,ensure_ascii=False).encode())<1600000
        seen += [r['id'] for r in page['records']];after=page['next'];pages+=1
        if not after:break
    assert len(seen)==len(set(seen))==expected
    assert pages>4
    print('PASS overview byte-bound pagination: every row exactly once, responses below 1.6 MB',flush=True)
finally:
    db.Therapy.update_many({'_owner_id':'qgis-user'},{'$unset':{'other':''}});store.close()
