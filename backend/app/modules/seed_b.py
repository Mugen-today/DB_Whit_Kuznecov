"""Loss-preserving, insert-only bootstrap of the supplied historical test_B."""
import json,hashlib
from datetime import datetime,timezone
from bson import ObjectId,Regex
from .seed_excel import insert_missing
from .geometry import normalize

def oid(digest,name,value):
    return ObjectId(hashlib.sha256((digest+':'+name+':'+str(value)).encode()).hexdigest()[:24])
def date(value):
    if value in (None,''):return None
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
def execute(path,digest,store):
    rows=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(rows,list):raise ValueError('test_B must be an array')
    cols={name:[] for name in ('Patient','Instances','Therapy','Geodata','Location','Foci','Region','Municipality')}
    archive=[];now=datetime.now(timezone.utc)
    for i,row in enumerate(rows):
        archive.append({'_id':oid(digest,'raw',i),'source':'json:'+digest,'imported_at':now,'raw':row})
        ids={n:oid(digest,n,i) for n in cols}
        p=row.get('patient') or {};t=row.get('therapy') or {};f=row.get('foci') or {}
        common={'_owner_id':'qgis-user','_dataset_source':'test_B'}
        patient={'_id':ids['Patient'],**common}
        if p.get('reg_date'):patient['reg_date']=date(p['reg_date'])
        if type(p.get('age')) is int:patient['age']=p['age']
        # No synthetic passport, age, sex or social category.
        therapy={'_id':ids['Therapy'],'patient':ids['Patient'],**common}
        if t.get('date_start'):therapy['date_start']=date(t['date_start'])
        if isinstance(t.get('diagnosis'),list):therapy['diagnosis']=t['diagnosis']
        if type(t.get('relapse')) is bool:therapy['relapse']=t['relapse']
        if t.get('chemo_regimen'):therapy['treatment_procedures']=Regex(str(t['chemo_regimen']))
        if f.get('address'):therapy['other']=str(f['address'])
        if t.get('died_tb') is True or t.get('died_other') is True:therapy['result']={'Saved':False}
        instance={'_id':ids['Instances'],'instance':ids['Instances'],'patient':ids['Patient'],'therapy':ids['Therapy'],'Other':'Туберкулёз / test_B',**common}
        if p.get('reg_date'):instance['date']=date(p['reg_date'])
        location={'_id':ids['Location'],'address':{},**common}
        geometry=row.get('location')
        if geometry:
            geo=normalize({'geometry':geometry})
            cols['Geodata'].append({'_id':ids['Geodata'],**geo,'_geometry_valid':True,**common})
            location['address']['geodata']=ids['Geodata']
        if f.get('region'):
            region={'_id':ids['Region'],'name':str(f['region']),**common}
            if f.get('municipality'):
                region['municipality']=ids['Municipality']
                cols['Municipality'].append({'_id':ids['Municipality'],'name':str(f['municipality']),**common})
            cols['Region'].append(region);location['address']['region']=ids['Region']
        cols['Patient'].append(patient);cols['Therapy'].append(therapy);cols['Instances'].append(instance)
        cols['Location'].append(location);cols['Foci'].append({'_id':ids['Foci'],'location':ids['Location'],'id_instance':ids['Instances'],**common})
    inserted={}
    for offset in range(0,len(archive),250):insert_missing(store.database('ingest').cases,archive[offset:offset+250])
    for name,docs in cols.items():
        inserted[name]=0
        for offset in range(0,len(docs),250):inserted[name]+=insert_missing(store.database('processor')[name],docs[offset:offset+250])
    return {'source_rows':len(rows),'inserted':inserted,'note':'Historical bootstrap: missing passport/age retained, not fabricated'}
