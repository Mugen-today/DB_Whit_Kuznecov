"""Schema-level partial entities and revision-controlled patches; no data deletion."""
import copy,hashlib,json,uuid
from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern
from . import records
from .qgis_data import ApiError
from .geometry import normalize
REQUIRED={**records.REQUIRED,'Therapy':['date_start','diagnosis','patient'],'Region':['name'],'Municipality':['name'],'Settlement':['name'],'Street':['name'],'Building':['house'],'Foci':['location','id_instance']}
def write_role(role):
    if role not in ('user','admin'):raise ApiError(403,'Read only principal')
def typed(name,data,creating=False):
    if name not in records.schemas():raise ApiError(404,'Unknown collection')
    if not isinstance(data,dict):records.fail('Entity must be an object')
    if any(k.startswith('_') or k in ('instance','qgis_revision') for k in data):records.fail('Identifiers and metadata are generated')
    if name=='Geodata':data=normalize(data)
    props={k:v for k,v in records.schemas()[name]['properties'].items() if not k.startswith('_') and k!='instance'}
    result=records.convert(data,{'bsonType':'object','properties':props},name)
    for field in REQUIRED.get(name,[]):
        if (creating or field in data) and (field not in result or result[field] in (None,'',[])):
            records.fail(name+'.'+field+': required')
    if name=='Patient' and 'age' in result and not 0<=result['age']<=130:records.fail('Patient.age: 0..130 required')
    if name=='Patient' and creating and 'passport' in result and not isinstance(result['passport'],str):records.fail('passport must be text')
    if name=='Location' and creating and not (result.get('address',{}).get('region') or result.get('address',{}).get('geodata')):
        records.fail('Location requires region or geodata reference')
    return result
def get_path(doc,path):
    for part in path.split('.'):
        if not isinstance(doc,dict):return None
        doc=doc.get(part)
    return doc
def set_path(doc,path,value):
    parts=path.split('.');parent=doc
    for p in parts[:-1]:parent=parent.setdefault(p,{})
    parent[parts[-1]]=value
def check_links(db,role,owner,name,doc,session=None,pending=None):
    for path,(target,key) in records.LINKS.get(name,{}).items():
        value=get_path(doc,path)
        if value is None:continue
        if pending and target in pending and pending[target].get(key)==value:continue
        if not db[target].find_one({**records.scope(role,owner),key:value},{'_id':1},session=session):
            records.fail(name+'.'+path+': target missing or not accessible')
    if name=='Instances' and doc.get('patient') is not None and doc.get('therapy') is not None:
        therapy=pending.get('Therapy') if pending else None
        if not therapy or therapy['_id']!=doc['therapy']:
            therapy=db.Therapy.find_one({**records.scope(role,owner),'_id':doc['therapy']},session=session)
        if therapy and therapy.get('patient') is not None and therapy['patient']!=doc['patient']:
            records.fail('Instances.patient conflicts with Therapy.patient')

def plan(payload,owner):
    try:request=str(uuid.UUID(payload['request_id']))
    except Exception:records.fail('request_id must be UUID')
    data=copy.deepcopy(payload.get('entities'))
    if not isinstance(data,dict) or not data:records.fail('Map at least one collection')
    if set(data)-set(records.schemas()):records.fail('Unknown collection')
    if 'Instances' in data and ('Geodata' in data or 'Region' in data):data.setdefault('Location',{})
    if 'Instances' in data and 'Location' in data:data.setdefault('Foci',{})
    ids={n:ObjectId(hashlib.sha256((owner+'|'+request+'|'+n).encode()).hexdigest()[:24]) for n in data}
    for name,doc in data.items():
        if not isinstance(doc,dict):records.fail('Entity must be an object')
        for path,(target,_) in records.LINKS.get(name,{}).items():
            if target in ids:
                explicit=get_path(doc,path)
                if explicit is not None and str(explicit)!=str(ids[target]):records.fail('Explicit reference conflicts with new row entity: '+name+'.'+path)
                set_path(doc,path,str(ids[target]))
    digest=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    out={}
    for name,doc in data.items():
        converted=typed(name,doc,True)
        converted.update(_id=ids[name],_owner_id=owner,qgis_revision=1,_request_hash=digest)
        if name=='Instances':converted['instance']=ids[name]
        if name=='Geodata':converted['_geometry_valid']=True
        out[name]=converted
    return out
def transaction(db,callback):
    if not db.client.admin.command('hello').get('setName'):raise ApiError(503,'Replica set required for atomic writes')
    with db.client.start_session() as session:
        return session.with_transaction(callback,read_concern=ReadConcern('snapshot'),write_concern=WriteConcern('majority'),max_commit_time_ms=5000)
def create(store,role,owner,payload,validate_only=False):
    write_role(role);docs=plan(payload,owner);db=store.database(role)
    for name,doc in docs.items():check_links(db,role,owner,name,doc,pending=docs)
    if validate_only:return docs
    def write(session):
        for name,doc in docs.items():
            old=db[name].find_one({'_id':doc['_id']},session=session)
            if old:
                if old.get('_request_hash')!=doc['_request_hash']:raise ApiError(409,'Request already used with different data')
                continue
            check_links(db,role,owner,name,doc,session,docs)
            db[name].insert_one(doc,session=session)
        return {'ids':{n:str(d['_id']) for n,d in docs.items()}}
    return transaction(db,write)
def patch(db,role,owner,name,identifier,payload,session=None):
    records.authorized(name,role);write_role(role)
    oid=records.id_for_key(identifier)
    if set(payload)!={'revision','changes'} or type(payload['revision']) is not int or payload['revision']<0:records.fail('revision and changes required')
    changes=copy.deepcopy(payload['changes'])
    if not isinstance(changes,dict) or not changes:records.fail('Nonempty changes required')
    filt={**records.scope(role,owner),'_id':oid}
    old=db[name].find_one(filt,session=session)
    if not old:raise ApiError(404,'Document not accessible')
    unset={}
    for key,value in list(changes.items()):
        if value is None:
            if name=='Geodata' and key=='geometry':records.fail('Geodata.geometry cannot be cleared; edit coordinates or geometry')
            if key in REQUIRED.get(name,[]):records.fail(key+': required')
            if key not in records.schemas()[name]['properties'] or key.startswith('_'):records.fail('Unknown field')
            unset[key]='';del changes[key]
    if name=='Geodata' and any(k in changes for k in ('Longitude','Latitude','geometry')):
        geom={k:old[k] for k in ('Longitude','Latitude','geometry','Elevation') if k in old}
        if 'geometry' in changes:
            geom.pop('Longitude',None);geom.pop('Latitude',None)
        else:geom.pop('geometry',None)
        for field in unset:geom.pop(field,None)
        converted=typed(name,{**geom,**changes})
    else:converted=typed(name,changes)
    check_links(db,role,owner,name,converted,session)
    if name=='Instances' and any(k in converted for k in ('patient','therapy')):
        check_links(db,role,owner,name,{**old,**converted},session)
    revision=payload['revision']
    filt['$or']=[{'qgis_revision':revision}]+([{'qgis_revision':{'$exists':False}}] if revision==0 else [])
    operation={'$inc':{'qgis_revision':1}}
    if converted:operation['$set']=converted
    if name=='Geodata' and 'geometry' in converted:operation.setdefault('$set',{})['_geometry_valid']=True
    if unset:operation['$unset']=unset
    result=db[name].find_one_and_update(filt,operation,session=session,return_document=ReturnDocument.AFTER)
    if not result:raise ApiError(409,'Revision conflict: reload the document')
    return records.public(result)
def edit(store,role,owner,name,identifier,payload):
    return patch(store.database(role),role,owner,name,identifier,payload)
def edit_batch(store,role,owner,name,payload):
    write_role(role)
    edits=payload.get('edits')
    if not isinstance(edits,list) or not 1<=len(edits)<=200:records.fail('1..200 edits required per batch')
    db=store.database(role)
    def write(session):return {'records':[patch(db,role,owner,name,e['_id'],{'revision':e['revision'],'changes':e['changes']},session) for e in edits]}
    return transaction(db,write)
