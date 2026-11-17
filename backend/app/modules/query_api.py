"""Authenticated bounded JSON/XML query API for the updated dashboard."""
import json,math,xml.etree.ElementTree as ET
from . import records
from .qgis_data import ApiError
def parse(raw,content_type):
    if 'xml' not in content_type:return json.loads(raw,parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON number')))
    if '<!DOCTYPE' in raw.upper() or '<!ENTITY' in raw.upper():raise ApiError(400,'XML declarations not allowed')
    try:root=ET.fromstring(raw)
    except ET.ParseError:raise ApiError(400,'Malformed XML query')
    f={}
    for c in root.findall('./filters/condition'):
        value=c.text or '';kind=c.get('type','string');op=c.get('operator','eq')
        if kind=='int':value=int(value)
        elif kind=='float':value=float(value)
        elif kind=='bool':value=value.lower()=='true'
        if op=='eq':f[c.get('field')]=value
        elif op in ('gt','gte','lt','lte','ne','regex'):f.setdefault(c.get('field'),{})['$'+op]=value
        else:raise ApiError(400,'Unsupported comparison')
    return {'collection':root.findtext('collection'),'filter':f,'limit':int(root.findtext('limit') or 100)}
def execute(store,role,owner,payload):
    name=payload.get('collection','Patient')
    if not isinstance(name,str):raise ApiError(400,'Collection must be a string')
    name=name.removeprefix('Schema.')
    records.authorized(name,role)
    limit=payload.get('limit',100)
    if type(limit) is not int or not 1<=limit<=200:raise ApiError(400,'limit must be 1..200')
    filt=payload.get('filter',{})
    if not isinstance(filt,dict):raise ApiError(400,'filter must be an object')
    props=records.schemas()[name]['properties']
    def spec_for(key):
        if key=='_id':return {'bsonType':'objectId'}
        spec={'properties':props}
        for part in key.split('.'):
            if part.startswith('_') or part not in spec.get('properties',{}):raise ApiError(400,'Unknown field '+key)
            spec=spec['properties'][part]
        return spec
    def convert(value,spec,key):
        if isinstance(value,float) and not math.isfinite(value):raise ApiError(400,'Nonfinite number')
        types=spec.get('bsonType',[]);types=[types] if isinstance(types,str) else types
        return records.convert(value,spec,key) if value is not None and ('objectId' in types or 'date' in types) else value
    checked={}
    for key,value in filt.items():
        spec=spec_for(key)
        if isinstance(value,dict):
            if set(value)-{'$eq','$ne','$gt','$gte','$lt','$lte','$in','$regex','$options','$exists'}:raise ApiError(400,'Unsupported filter')
            if '$options' in value and (value['$options'] not in ('','i') or '$regex' not in value):raise ApiError(400,'Invalid regex options')
            if '$regex' in value and (not isinstance(value['$regex'],str) or len(value['$regex'])>128):raise ApiError(400,'Regex too long')
            out={}
            for op,v in value.items():
                if isinstance(v,dict):raise ApiError(400,'Nested operators not allowed')
                if op=='$in':
                    if not isinstance(v,list) or len(v)>100:raise ApiError(400,'Invalid $in')
                    out[op]=[convert(x,spec,key) for x in v]
                elif op in ('$regex','$options','$exists'):out[op]=v
                else:out[op]=convert(v,spec,key)
            checked[key]=out
        else:checked[key]=convert(value,spec,key)
    docs=list(store.database(role)[name].find({'$and':[records.scope(role,owner),checked]},max_time_ms=2000).limit(limit))
    result=[records.public(d) for d in docs]
    if len(json.dumps(result).encode())>1500000:raise ApiError(413,'Result exceeds response limit')
    return {'results':result,'matched_count':len(result),'limit':limit,'role_used':role}
