"""Bounded schema exports, validated edits and atomic four-part record creation."""
import copy
import hashlib
import json
import math
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from bson import ObjectId, Regex
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern
from ..models.schema import load_schema
from .qgis_data import ApiError

BLOCKED = {'Social_group', 'Street', 'Building', 'Placement'}
REQUIRED = {'Patient': ['passport', 'age', 'reg_date'], 'Instances': ['date'],
            'Therapy': ['date_start', 'diagnosis'], 'Geodata': ['Longitude', 'Latitude']}
# Actual model direction, including the historical Instances.instance key.
LINKS = {'Region': {'municipality': ('Municipality', '_id')},
 'Municipality': {'settlement': ('Settlement', '_id')},
 'Settlement': {'street': ('Street', '_id')}, 'Street': {'building': ('Building', '_id')},
 'Building': {'placement': ('Placement', '_id')},
 'Patient': {'gender': ('Gender', '_id'), 'social_group': ('Social_group', '_id')},
 'Therapy': {'patient': ('Patient', '_id'), 'severity': ('Severity', '_id'), 'influence': ('Influence', '_id')},
 'Instances': {'patient': ('Patient', '_id'), 'therapy': ('Therapy', '_id'), 'reception': ('Reception', '_id')},
 'Location': {'address.region': ('Region', '_id'), 'address.geodata': ('Geodata', '_id')},
 'Foci': {'location': ('Location', '_id'), 'id_instance': ('Instances', 'instance')}}

@lru_cache(maxsize=1)
def schemas():
    return {k.split('.')[-1]: v['jsonSchema'] for k,v in load_schema()['collections'].items()}

def fail(message):
    raise ApiError(422, message)

def convert(value, spec, path):
    if 'enum' in spec:
        if value not in spec['enum']: fail(path+': invalid enum')
        return value
    types = spec.get('bsonType', [])
    if isinstance(types, str): types = [types]
    if 'object' in types:
        if not isinstance(value, dict): fail(path + ': expected object')
        props = spec.get('properties', {})
        if set(value) - set(props): fail(path + ': unknown fields ' + ', '.join(sorted(set(value)-set(props))))
        return {k: convert(v, props[k], path+'.'+k) for k,v in value.items()}
    if 'objectId' in types:
        try: return ObjectId(value)
        except Exception: fail(path + ': invalid ObjectId')
    if 'date' in types:
        try:
            if not isinstance(value, str): raise ValueError()
            result = datetime.fromisoformat(value.replace('Z','+00:00'))
            return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)
        except ValueError: fail(path + ': expected ISO date or datetime')
    if 'array' in types:
        if not isinstance(value,list) or len(value)>200: fail(path + ': expected array, at most 200 items')
        if path.endswith('.coordinates'):
            if len(value)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in value): fail(path+': invalid coordinates')
            return [float(v) for v in value]
        if any(not isinstance(v,str) or not v.strip() or len(v)>2000 for v in value): fail(path + ': array must contain nonempty strings')
        return value
    if 'regex' in types:
        if isinstance(value,dict) and set(value)=={'pattern','flags'}:
            if not isinstance(value['pattern'],str) or type(value['flags']) is not int: fail(path+': invalid regex')
            return Regex(value['pattern'],value['flags'])
        if not isinstance(value,str): fail(path + ': expected text')
        return Regex(value)
    if 'string' in types and isinstance(value,str) and value.strip() and len(value)<=4000: return value.strip()
    if 'int' in types and type(value) is int and -(2**31)<=value<2**31: return value
    if 'double' in types and type(value) in (int,float) and math.isfinite(value): return float(value)
    if 'bool' in types and type(value) is bool: return value
    fail(path + ': invalid or empty value')

def validate(name, data, creating=False):
    if name not in schemas(): fail('Unknown collection')
    if name=='Geodata':
        from .geometry import normalize
        data=normalize(data)
    props = schemas()[name]['properties']
    allowed = {k:v for k,v in props.items() if not k.startswith('_') and k!='instance'}
    result = convert(data, {'bsonType':'object','properties':allowed}, name)
    for key in REQUIRED.get(name,[]):
        if key not in result or result[key] in (None, '', []): fail(name+'.'+key+': required')
    if name=='Patient':
        if not 0<=result['age']<=130: fail('Patient.age: expected 0..130')
        if creating and not isinstance(result['passport'],str): fail('Patient.passport: use a string to preserve leading zeros')
    if name=='Geodata' and not (-180<=result['Longitude']<=180 and -90<=result['Latitude']<=90): fail('Coordinates out of WGS84 range')
    if name=='Therapy' and 'patient' not in result: fail('Therapy.patient: required link')
    return result

def wire(value):
    if value is None or type(value) in (str,bool,int):return value
    if type(value) is float and math.isfinite(value):return value
    if isinstance(value,ObjectId): return str(value)
    if isinstance(value,datetime): return value.isoformat()
    if isinstance(value,Regex): return {'pattern':value.pattern,'flags':int(value.flags)}
    if isinstance(value,dict): return {k:wire(v) for k,v in value.items()}
    if isinstance(value,list): return [wire(v) for v in value]
    from bson import json_util
    return json.loads(json_util.dumps(value))

def key_for_id(value):
    if isinstance(value,ObjectId):return str(value)
    import base64
    from bson import json_util
    return 'e:'+base64.urlsafe_b64encode(json_util.dumps(value,json_options=json_util.CANONICAL_JSON_OPTIONS).encode()).decode()

def id_for_key(value):
    if isinstance(value,str) and value.startswith('e:'):
        import base64
        from bson import json_util
        if len(value)>8192:fail('Identifier too long')
        try:return json_util.loads(base64.urlsafe_b64decode(value[2:]).decode())
        except Exception:fail('Invalid encoded identifier')
    try:return ObjectId(value)
    except Exception:fail('Invalid document identifier')

def public(doc):
    result={k:v for k,v in doc.items() if k=='_id' or not k.startswith('_')}
    result['qgis_revision']=doc.get('qgis_revision',0)
    if '_id' in doc:result['_key']=key_for_id(doc['_id'])
    return wire(result)

def scope(role,owner):
    return {'_owner_id':owner} if role=='user' else {}

def authorized(name,role):
    if name not in schemas(): raise ApiError(404,'Unknown collection')
    if role=='guest' and name in BLOCKED: raise ApiError(403,'Collection is not available to guests')

def catalog(role):
    return {'collections':{name:{'schema':spec,'required':REQUIRED.get(name,[]),'links':LINKS.get(name,{})}
             for name,spec in schemas().items() if role!='guest' or name not in BLOCKED},
            'create_endpoint':'/v1/records','page_max':200}

def page(store,role,owner,name,params):
    authorized(name,role)
    filt=scope(role,owner)
    try:
        limit=int(params.get('limit',['100'])[0])
        if not 1<=limit<=200: raise ValueError()
        after=params.get('after',[''])[0]
        if after:filt['$expr']={'$gt':['$_id',{'$literal':id_for_key(after)}]}
    except Exception: raise ApiError(400,'Invalid limit or cursor')
    fields=params.get('fields',[''])[0]
    projection=None
    if fields:
        names=fields.split(',')
        if set(names)-(set(schemas()[name]['properties'])|{'_id','qgis_revision'}): raise ApiError(400,'Unknown projection fields')
        projection={k:1 for k in names};projection.update(_id=1,qgis_revision=1)
    cursor=store.database(role)[name].find(filt,projection,max_time_ms=10000).sort('_id',1).batch_size(64).limit(limit+1)
    visible=[];size=0;more=False;lastid=None
    try:
        for doc in cursor:
            item=public(doc)
            item_size=len(json.dumps(item,ensure_ascii=False).encode('utf-8'))
            if len(visible)>=limit or visible and size+item_size>1500000:
                more=True;break
            visible.append(item);size+=item_size;lastid=doc['_id']
    finally:cursor.close()
    from .geometry import features
    return {'collection':name,'records':visible,'features':features(visible) if name=='Geodata' else [],'role':role,
            'next':key_for_id(lastid) if more else None}

def edit(store,role,owner,name,identifier,payload):
    authorized(name,role)
    if role not in ('user','admin'): raise ApiError(403,'Read only')
    if set(payload)!={'revision','changes'} or type(payload['revision']) is not int or payload['revision']<0: fail('revision and changes required')
    try: oid=ObjectId(identifier)
    except Exception: fail('Invalid document id')
    changes=payload['changes']
    if not isinstance(changes,dict) or not changes: fail('Nonempty changes object required')
    if any(k.startswith('_') or k in ('instance','qgis_revision') for k in changes): fail('Identifiers and metadata are immutable')
    # Relations are immutable in the entity editor; bundles establish relationships.
    if any(k==p.split('.')[0] for k in changes for p in LINKS.get(name,{})): fail('Relationship fields are immutable')
    db=store.database(role);filt={**scope(role,owner),'_id':oid}
    doc=db[name].find_one(filt)
    if not doc: raise ApiError(404,'Document unavailable')
    current={k:wire(v) for k,v in doc.items() if k in schemas()[name]['properties'] and not k.startswith('_') and k!='instance'}
    if name=='Geodata':
        if 'geometry' in changes:
            current.pop('Longitude',None);current.pop('Latitude',None)
        elif 'Longitude' in changes or 'Latitude' in changes: current.pop('geometry',None)
    converted=validate(name,{**current,**changes})
    if name=='Geodata': changes={**changes,**{k:converted[k] for k in ('Longitude','Latitude','geometry')}}
    revision=payload['revision']
    filt['$or']=[{'qgis_revision':revision}]+([{'qgis_revision':{'$exists':False}}] if revision==0 else [])
    result=db[name].find_one_and_update(filt,{'$set':{k:converted[k] for k in changes},'$inc':{'qgis_revision':1}},return_document=ReturnDocument.AFTER)
    if not result: raise ApiError(409,'Revision conflict; reload before editing')
    return public(result)

def prepare(payload,owner):
    if not isinstance(payload,dict) or set(payload)-{'request_id','entities'}: fail('Expected request_id and entities')
    try: request=str(uuid.UUID(payload['request_id']))
    except Exception: fail('request_id must be UUID')
    entities=copy.deepcopy(payload.get('entities'))
    if not isinstance(entities,dict): fail('entities must be an object')
    if set(entities)-set(schemas()): fail('Unknown collection in entities')
    if not {'Patient','Instances','Therapy'}<=set(entities): fail('Patient, Instances and Therapy are all mandatory')
    address={'Region','Municipality','Settlement','Street','Building'}
    has_address=bool(address & set(entities))
    if has_address and not address<=set(entities): fail('All five address collections are required')
    if 'Geodata' not in entities and not has_address: fail('Coordinates or a complete address required')
    if 'Location' in entities or 'Foci' in entities: fail('Location and Foci are generated automatically')
    # Every user-entered address attribute is required. PKs, FKs and ownership are generated.
    if has_address:
        for name in address:
            keys=set(schemas()[name]['properties'])-{'_id','_owner_id'}-set(LINKS.get(name,{}))
            if not isinstance(entities[name],dict) or not keys<=set(entities[name]): fail(name+': all descriptive address fields required: '+', '.join(sorted(keys)))
    entities['Location']={};entities['Foci']={}
    ids={name:ObjectId(hashlib.sha256((owner+'|'+request+'|'+name).encode()).hexdigest()[:24]) for name in entities}
    for name,data in entities.items():
        if not isinstance(data,dict): fail(name+': expected object')
        # No user-supplied keys/links: reference collections may be included in this bundle.
        if any(k.startswith('_') or k=='instance' or k in {p.split('.')[0] for p in LINKS.get(name,{})} for k in data): fail(name+': ids and links are generated by backend')
        for path,(target,_) in LINKS.get(name,{}).items():
            if target not in ids: continue
            if '.' in path:
                parent,key=path.split('.');data.setdefault(parent,{})[key]=str(ids[target])
            else: data[path]=str(ids[target])
    docs={}
    digest=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    for name,data in entities.items():
        doc=validate(name,data,creating=True)
        doc.update(_id=ids[name],_owner_id=owner,qgis_revision=1,_request_hash=digest)
        if name=='Instances': doc['instance']=ids[name]
        docs[name]=doc
    return docs

def create(store,role,owner,payload):
    if role not in ('user','admin'): raise ApiError(403,'Read only')
    docs=prepare(payload,owner) # All validation occurs before the first write.
    if 'Geodata' in docs:docs['Geodata']['_geometry_valid']=True
    db=store.database(role)
    if not db.client.admin.command('hello').get('setName'): raise ApiError(503,'Atomic creation requires a replica set; run manage.py up')
    marker=docs['Instances']
    def write(session):
        old=db.Instances.find_one({'_id':marker['_id']},session=session)
        if old:
            if old.get('_request_hash')!=marker['_request_hash']: raise ApiError(409,'request_id already used for different data')
            return
        for name,doc in docs.items(): db[name].insert_one(doc,session=session)
    try:
        with db.client.start_session() as session:
            session.with_transaction(write,read_concern=ReadConcern('snapshot'),write_concern=WriteConcern('majority'),max_commit_time_ms=5000)
    except DuplicateKeyError:
        old=db.Instances.find_one({'_id':marker['_id']})
        if not old or old.get('_request_hash')!=marker['_request_hash']: raise ApiError(409,'Conflicting request; reload')
    return {'status':'saved','ids':{name:str(doc['_id']) for name,doc in docs.items()}}
