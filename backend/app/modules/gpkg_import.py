"""Read-only GeoPackage inspection and strict field-mapped import; backend only."""
import hashlib,json,math,os,sqlite3,struct,tempfile,time,uuid
from functools import lru_cache
from contextlib import closing
from datetime import datetime
from pathlib import Path
from . import records, entities as entity_api
from .geometry import normalize
from .qgis_data import ApiError
from . import gpkg_uploads as files
ROOT=files.ROOT  # retained for callers which inspect the upload directory
quote=files.quote
connect=files.connect
tables=files.tables
path_for=files.path_for
upload=files.upload
@lru_cache(maxsize=32)
def transformer(source):
    from pyproj import Transformer
    return Transformer.from_crs(source,"EPSG:4326",always_xy=True,allow_ballpark=False,only_best=True)

def point(blob,meta,db):
    if not isinstance(blob,bytes) or len(blob)<29 or blob[:2]!=b'GP' or blob[2]!=0 or blob[3]&16:
        raise ApiError(422,'Missing or invalid GeoPackage point geometry')
    flags=blob[3];env=(flags>>1)&7
    if env not in (0,1,2,3,4):raise ApiError(422,'Invalid geometry envelope')
    offset=8+{0:0,1:32,2:48,3:48,4:64}[env]
    if len(blob)<offset+21:raise ApiError(422,'Truncated geometry')
    if blob[offset] not in (0,1):raise ApiError(422,'Invalid WKB byte order')
    endian='<' if blob[offset]==1 else '>'
    kind=struct.unpack_from(endian+'I',blob,offset+1)[0]
    if kind!=1:raise ApiError(422,'Only 2D Point geometries are supported')
    header_srs=struct.unpack_from('<i' if flags&1 else '>i',blob,4)[0]
    if header_srs!=meta['srs_id']:raise ApiError(422,'Geometry CRS differs from table CRS')
    x,y=struct.unpack_from(endian+'dd',blob,offset+5)
    crs=db.execute('SELECT organization,organization_coordsys_id,definition FROM gpkg_spatial_ref_sys WHERE srs_id=?',(meta['srs_id'],)).fetchone()
    if not crs or meta['srs_id'] in (-1,0):raise ApiError(422,'Unknown source CRS')
    from pyproj import Transformer
    source=('EPSG:'+str(crs['organization_coordsys_id'])) if crs['organization'].upper()=='EPSG' else crs['definition']
    x,y=transformer(source).transform(x,y,errcheck=True)
    return normalize({'Longitude':x,'Latitude':y})
def target_fields():
    out=[]
    def visit(name,spec,path=""):
        for field,child in spec.get('properties',{}).items():
            target=path+field
            if field.startswith('_') or field=='instance' or target=='geometry':continue

            if 'properties' in child:visit(name,child,target+'.')
            else:out.append(name+'.'+target)
    for name,spec in records.schemas().items():
        visit(name,spec)
    return sorted(out)

def requirements():
    # model.json preserves permissive historical data; new-input business rules
    # are merged here, so the UI does not invent a second schema.
    out={}
    for name,spec in records.schemas().items():
        fields=set(spec.get('required',[]))|set(entity_api.REQUIRED.get(name,[]))
        out[name]=sorted(fields-{'_id','instance','qgis_revision'})
    return out

def mapped_value(value,spec,path):
    types=spec.get('bsonType',[]);types=[types] if isinstance(types,str) else types
    if value is None or isinstance(value,str) and not value.strip():return None
    if 'date' in types and isinstance(value,str):
        try:return datetime.fromisoformat(value.replace('Z','+00:00')).isoformat()
        except ValueError:
            for fmt in ('%d.%m.%Y','%d.%m.%Y %H:%M'):
                try:return datetime.strptime(value,fmt).isoformat()
                except ValueError:pass
            raise ApiError(422,path+': unsupported date format')
    if 'array' in types:
        if isinstance(value,str):
            try:parsed=json.loads(value)
            except ValueError:
                if value.lstrip().startswith('['):raise ApiError(422,path+': malformed JSON array')
                parsed=[value]
            return parsed if isinstance(parsed,list) else [value]
    if 'int' in types and 'string' not in types:
        if isinstance(value,bool):return value
        number=float(value)
        if math.isfinite(number) and number.is_integer():return int(number)
        raise ApiError(422,path+': integer required')
    if 'double' in types:return float(value)
    if 'bool' in types:
        if value in (0,1,False,True):return bool(value)
        if str(value).lower() in ('true','false'):return str(value).lower()=='true'
        raise ApiError(422,path+': boolean required')
    if 'string' in types or 'regex' in types:return str(value)
    return value
def context(payload,owner):
    if payload.get('mode','entities') not in ('entities','bundle'):raise ApiError(422,'Unknown import mode')
    path=path_for(payload.get('upload_id'),owner)
    mapping=payload.get('mapping')
    if not isinstance(mapping,dict):raise ApiError(422,'Field mapping must be an object')
    with closing(connect(path)) as db:
        choices={t['name']:t for t in tables(db)}
    table=payload.get('table')
    if table not in choices:raise ApiError(422,'Unknown table')
    meta=choices[table]
    if not mapping and not (meta['geometry'] and payload.get('use_geometry',True)):raise ApiError(422,'Map at least one collection or use table geometry')
    if meta['rows']<1:raise ApiError(422,'Selected table is empty')
    if not meta['pk']:raise ApiError(422,'Stable primary key required')
    targets={}
    for target,source in mapping.items():
        pieces=target.split('.')
        if len(pieces)<2 or pieces[0] not in records.schemas():raise ApiError(422,'Unknown target field')
        name=pieces[0];spec=records.schemas()[name]
        for part in pieces[1:]:
            if part.startswith('_') or part=='instance' or part not in spec.get('properties',{}):raise ApiError(422,'Unknown or generated target field')
            spec=spec['properties'][part]
        if source not in meta['fields']:raise ApiError(422,'Unknown source field')
        targets[target]=(source,spec)
    return path,meta,targets,files.fingerprint(payload['upload_id'],owner)

def source_page(db,meta,targets,payload,last_key=None,limit=250):
    columns=set(meta['pk'])|{source for source,spec in targets.values()}
    if meta['geometry'] and payload.get('use_geometry',True):columns.add(meta['geometry']['column_name'])
    # Do not read unmapped blobs/text. Reject oversized selected cells before
    # loading their contents; never silently truncate a value.
    names=sorted(columns);overflow='__gis_size_'+uuid.uuid4().hex
    size_sql='('+'+'.join('COALESCE(length(CAST('+quote(c)+' AS BLOB)),0)' for c in names)+')'
    oversized='('+size_sql+'>2097152 OR '+' OR '.join('length(CAST('+quote(c)+' AS BLOB))>1048576' for c in names)+')'
    selected=[]
    for c in names:
        condition='length(CAST('+quote(c)+' AS BLOB))>1048576' if c in meta['pk'] else oversized
        selected.append('CASE WHEN '+condition+' THEN NULL ELSE '+quote(c)+' END AS '+quote(c))
    selected.append(oversized+' AS '+quote(overflow))
    sql='SELECT '+','.join(selected)+' FROM '+quote(meta['name'])
    args=[]
    if last_key is not None:
        keys=','.join(quote(c) for c in meta['pk']);marks=','.join('?' for _ in last_key)
        sql+=' WHERE ('+keys+') > ('+marks+')';args+=last_key
    sql+=' ORDER BY '+','.join(quote(c) for c in meta['pk'])+' LIMIT ?';args.append(limit)
    cursor=db.execute(sql,args);rows=[];size=0
    for row in cursor:
        rows.append(row)
        size+=sum(len(value.encode('utf-8')) if isinstance(value,str) else len(value) if isinstance(value,bytes) else 16 for value in row)
        if size>=2097152:break
    cursor.close()
    return rows,overflow

def row_record(row,meta,targets,payload,fingerprint,owner,db):
    keys=[row[k] for k in meta['pk']]
    if any(k is None for k in keys):raise ApiError(422,'Primary key cannot be NULL')
    entities={}
    for target,(source,spec) in targets.items():
        parts=target.split('.');obj=entities.setdefault(parts[0],{})
        value=mapped_value(row[source],spec,target)
        if value is None:continue
        for part in parts[1:-1]:obj=obj.setdefault(part,{})
        obj[parts[-1]]=value
    if meta['geometry'] and payload.get('use_geometry',True):
        geo=point(row[meta['geometry']['column_name']],meta['geometry'],db)
        entities['Geodata']=normalize({**geo,**entities.get('Geodata',{})})
    identity=fingerprint+'|'+meta['name']+'|'+json.dumps(keys,default=str)
    record={'request_id':str(uuid.uuid5(uuid.NAMESPACE_URL,identity)),'entities':entities}
    if payload.get('mode','entities')=='bundle':records.prepare(record,owner)
    else:entity_api.plan(record,owner)
    return record

def build(payload,owner,store=None,role='user'):
    """Streaming diagnostic iterator; HTTP imports use durable staged jobs."""
    path,meta,targets,digest=context(payload,owner)
    last=None
    with closing(connect(path)) as db:
        while True:
            rows,overflow=source_page(db,meta,targets,payload,last)
            if not rows:break
            for row in rows:
                if row[overflow]:raise ApiError(422,'Selected attributes exceed per-value (1 MiB) or per-row (2 MiB) limits')
                try:item=row_record(row,meta,targets,payload,digest,owner,db)
                except (ValueError,TypeError,OverflowError) as exc:raise ApiError(422,str(exc))
                if store:
                    docs=entity_api.plan(item,owner) if payload.get('mode','entities')!='bundle' else records.prepare(item,owner)
                    for name,doc in docs.items():entity_api.check_links(store.database(role),role,owner,name,doc,pending=docs)
                yield item
            last=[rows[-1][k] for k in meta['pk']]

def execute(store,role,owner,payload,apply=False):
    from . import gpkg_jobs
    return gpkg_jobs.legacy(store,role,owner,payload,apply)
