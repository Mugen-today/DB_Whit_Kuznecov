"""Python-syntax Mongo query subset. No eval/exec or host Python execution."""
import ast
from .qgis_data import ApiError
from . import records

def execute(store,role,owner,payload):
    source=payload.get('code','')
    if not isinstance(source,str) or len(source)>32000: raise ApiError(400,'Invalid console input')
    try: node=ast.parse(source,mode='eval').body
    except SyntaxError: raise ApiError(400,'One Python expression required')
    try:
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name):
            args=[ast.literal_eval(a) for a in node.args]
            if node.keywords: raise ValueError()
            if node.func.id=='create_record' and len(args)==1: return records.create(store,role,owner,args[0])
            if node.func.id=='update_record' and len(args)==4: return records.edit(store,role,owner,args[0],args[1],{'revision':args[2],'changes':args[3]})
            raise ValueError()
        limit=100
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='limit':
            if len(node.args)!=1 or node.keywords: raise ValueError()
            limit=ast.literal_eval(node.args[0]);node=node.func.value
        if type(limit) is not int or not 1<=limit<=200: raise ValueError()
        if not isinstance(node,ast.Call) or node.keywords or len(node.args)>1 or not isinstance(node.func,ast.Attribute) or node.func.attr!='find':raise ValueError()
        col=node.func.value
        if not isinstance(col,ast.Attribute) or not isinstance(col.value,ast.Name) or col.value.id!='db':raise ValueError()
        name=col.attr;records.authorized(name,role)
        filt=ast.literal_eval(node.args[0]) if node.args else {}
        if not isinstance(filt,dict):raise ValueError()
        allowed=(set(records.schemas()[name]['properties'])|{'_id'})-{'_owner_id'}
        for key,value in filt.items():
            if key not in allowed or key.startswith('$'):raise ValueError()
            if isinstance(value,dict):
                if set(value)-{'$eq','$ne','$gt','$gte','$lt','$lte','$in'}:raise ValueError()
                if any(isinstance(v,dict) or (isinstance(v,list) and len(v)>100) for v in value.values()):raise ValueError()
            elif isinstance(value,(list,dict)):raise ValueError()
        props=records.schemas()[name]['properties']
        for key,value in list(filt.items()):
            spec=props.get(key,{'bsonType':'objectId'})
            types=spec.get('bsonType',[])
            if isinstance(types,str):types=[types]
            if 'objectId' in types or 'date' in types:
                if isinstance(value,dict):
                    filt[key]={op:[records.convert(v,spec,key) for v in val] if op=='$in' else records.convert(val,spec,key) for op,val in value.items()}
                else:filt[key]=records.convert(value,spec,key)
        query={'$and':[records.scope(role,owner),filt]}
        docs=list(store.database(role)[name].find(query,max_time_ms=2000).limit(limit))
        result=[records.public(d) for d in docs]
        import json
        if len(json.dumps(result).encode())>1500000:raise ApiError(413,'Result too large; narrow query')
        return {'records':result,'limit':limit}
    except (ValueError,TypeError,AttributeError,KeyError,RecursionError):raise ApiError(400,'Supported: db.Patient.find({...}).limit(100), create_record({...}), update_record(collection,id,revision,changes)')
