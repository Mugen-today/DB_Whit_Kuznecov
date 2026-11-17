"""Generate benchmark data ONLY in an explicitly confirmed EMPTY disposable DB."""
import argparse,sys
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from backend.app.database.mongodb import MongoDB
from bson import ObjectId
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--confirm-empty-disposable',action='store_true');p.add_argument('--rows',type=int,default=4000);args=p.parse_args()
if not args.confirm_empty_disposable or args.rows<1:p.error('Requires --confirm-empty-disposable and positive --rows')
store=MongoDB();db=store.database('user');names=('Gender','Patient','Therapy','Instances','Geodata','Location','Foci')
try:
    if any(db[n].count_documents({}) for n in names):raise ValueError('Fixture requires empty collections; no data will be removed')
    gender=[ObjectId(),ObjectId()];db.Gender.insert_many([{'_id':x,'type':str(i),'_owner_id':'qgis-user'} for i,x in enumerate(gender)])
    for offset in range(0,args.rows,250):
        rows={n:[] for n in names if n!='Gender'}
        for i in range(offset,min(offset+250,args.rows)):
            key=ObjectId((i+1).to_bytes(12,'big'));common={'_id':key,'_owner_id':'qgis-user','qgis_revision':0};now=datetime(2026,1,1,tzinfo=timezone.utc)
            rows['Patient'].append({**common,'age':25,'reg_date':now,'gender':gender[i%2],'unused_blob':'p'*8192})
            rows['Therapy'].append({**common,'patient':key,'date_start':now,'diagnosis':['TEST'],'unused_blob':'t'*8192})
            rows['Instances'].append({**common,'instance':key,'patient':key,'therapy':key,'date':now,'Other':'SYNTHETIC','unused_blob':'i'*8192})
            rows['Geodata'].append({**common,'Longitude':30.,'Latitude':60.,'geometry':{'type':'Point','coordinates':[30.,60.]},'_geometry_valid':True,'unused_blob':'g'*8192})
            rows['Location'].append({**common,'address':{'geodata':key}})
            rows['Foci'].append({**common,'id_instance':key,'location':key})
        for name,documents in rows.items():db[name].insert_many(documents)
    print('Created synthetic benchmark fixture:',args.rows,'linked records; no source datasets used')
finally:store.close()
