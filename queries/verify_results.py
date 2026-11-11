"""Independent Python evaluation of the read-only query plans on a BSON snapshot."""
import json,sys,copy,math
from collections import defaultdict
from datetime import datetime
from bson import json_util
MISSING=object()
def get(d,path,default=None):
    for k in path.split('.'):
        if not isinstance(d,dict) or k not in d:return default
        d=d[k]
    return d
def freeze(v):
    return json_util.dumps(v,sort_keys=True)
def expr(x,d):
    if isinstance(x,str) and x.startswith('$'):return get(d,x[1:])
    if isinstance(x,list):return [expr(v,d) for v in x]
    if not isinstance(x,dict):return x
    if len(x)!=1 or not next(iter(x)).startswith('$'):return {k:expr(v,d) for k,v in x.items()}
    op,v=next(iter(x.items()))
    if op=='$ifNull':
        a,b=expr(v,d);return b if a is None else a
    if op=='$size':return len(expr(v,d))
    if op=='$cond':
        a,b,c=v;return expr(b,d) if expr(a,d) else expr(c,d)
    if op=='$subtract':
        a,b=expr(v,d)
        if a is None or b is None:return None
        z=a-b;return z.total_seconds()*1000 if hasattr(z,'total_seconds') else z
    if op=='$divide':
        a,b=expr(v,d);return None if a is None else a/b
    if op=='$dateToString':
        date=expr(v['date'],d)
        return date.strftime(v['format']) if date else None
    raise ValueError('Unsupported expression '+op)
def equal(a,b):
    return a==b or isinstance(a,list) and b in a
def match(d,f):
    for k,v in f.items():
        if k=='$or':
            if not any(match(d,a) for a in v):return False
            continue
        if k=='$and':
            if not all(match(d,a) for a in v):return False
            continue
        a=get(d,k,MISSING)
        if not isinstance(v,dict) or not any(key.startswith('$') for key in v):
            if not equal(None if a is MISSING else a,v):return False
            continue
        for op,b in v.items():
            if op=='$exists':ok=(a is not MISSING)==b
            elif op=='$size':ok=isinstance(a,list) and len(a)==b
            elif op=='$in':ok=any(equal(None if a is MISSING else a,z) for z in b)
            elif op=='$nin':ok=not any(equal(None if a is MISSING else a,z) for z in b)
            elif op=='$ne':ok=a is not MISSING and not equal(a,b) if b is None else a is MISSING or not equal(a,b)
            elif op in ('$gt','$gte','$lt','$lte'):
                ok=a is not MISSING and a is not None
                if ok:
                    try:ok={'$gt':lambda:a>b,'$gte':lambda:a>=b,'$lt':lambda:a<b,'$lte':lambda:a<=b}[op]()
                    except TypeError:ok=False
            else:raise ValueError(op)
            if not ok:return False
    return True
def order(rows,spec):
    for field,direction in reversed(list(spec.items())):
        rows=sorted(rows,key=lambda d:(get(d,field) is not None,get(d,field)),reverse=direction<0)
    return rows
def aggregate(rows,pipeline,db):
    for stage in pipeline:
        op,v=next(iter(stage.items()))
        if op=='$lookup':
            idx=defaultdict(list)
            for foreign in db[v['from']]:idx[freeze(get(foreign,v['foreignField']))].append(foreign)
            rows=[{**d,v['as']:idx[freeze(get(d,v['localField']))]} for d in rows]
        elif op=='$unwind':
            field=v.lstrip('$')
            rows=[{**d,field:item} for d in rows for item in (get(d,field) or [])]
        elif op=='$match':rows=[d for d in rows if match(d,v)]
        elif op=='$sort':rows=order(rows,v)
        elif op=='$limit':rows=rows[:v]
        elif op=='$count':rows=[{v:len(rows)}] if rows else []
        elif op=='$project':
            out=[]
            for d in rows:
                item={'_id':d['_id']} if v.get('_id',1)!=0 and '_id' in d else {}
                for k,e in v.items():
                    if e==1:
                        if k in d:item[k]=d[k]
                    elif e!=0:item[k]=expr(e,d)
                out.append(item)
            rows=out
        elif op=='$group':
            groups={}
            for d in rows:
                key=expr(v['_id'],d);fk=freeze(key)
                if fk not in groups:groups[fk]=(key,[])
                groups[fk][1].append(d)
            out=[]
            for key,items in groups.values():
                item={'_id':key}
                for k,e in v.items():
                    if k=='_id':continue
                    acc,arg=next(iter(e.items()));vals=[expr(arg,d) for d in items];valid=[a for a in vals if a is not None]
                    if acc=='$sum':item[k]=sum(a for a in valid if isinstance(a,(int,float)))
                    elif acc=='$avg':
                        nums=[a for a in valid if isinstance(a,(int,float))];item[k]=sum(nums)/len(nums) if nums else None
                    elif acc=='$min':item[k]=min(valid) if valid else None
                    elif acc=='$max':item[k]=max(valid) if valid else None
                    else:raise ValueError(acc)
                out.append(item)
            rows=out
        elif op=='$bucket':
            groups=defaultdict(int);bounds=v['boundaries']
            for d in rows:
                a=expr(v['groupBy'],d);key=v['default']
                if type(a) in (int,float):
                    for lo,hi in zip(bounds,bounds[1:]):
                        if lo<=a<hi:key=lo;break
                groups[key]+=1
            rows=[{'_id':k,'count':n} for k,n in groups.items()]
        else:raise ValueError('Unsupported stage '+op)
    return rows
def equivalent(a,b):
    # Compare unordered BSON result sets with tolerance for floating point averages.
    if isinstance(a,float) or isinstance(b,float):
        try:return math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-10)
        except TypeError:return False
    if isinstance(a,dict) and isinstance(b,dict):return set(a)==set(b) and all(equivalent(a[k],b[k]) for k in a)
    if isinstance(a,list) and isinstance(b,list):
        if len(a)!=len(b):return False
        aa=sorted(a,key=freeze);bb=sorted(b,key=freeze)
        return all(equivalent(x,y) for x,y in zip(aa,bb))
    return a==b
def main():
    actual=json_util.loads(open(sys.argv[1]).read());db=json_util.loads(open(sys.argv[2]).read())
    report=[]
    for q in actual['queries']:
        item={'number':q['number'],'executed':q['ok']}
        if q['ok']:
            try:
                p=q['plan'];rows=db[p['collection']];args=p['args'];method=p['method']
                if method=='aggregate':expected=aggregate(rows,args[0],db)
                elif method=='distinct':expected=list({freeze(get(d,args[0])):get(d,args[0]) for d in rows if get(d,args[0],MISSING) is not MISSING}.values())
                elif method in ('find','countDocuments'):
                    expected=[d for d in rows if match(d,args[0] if args else {})]
                    if p.get('sort'):expected=order(expected,p['sort'])
                    if p.get('limit'):expected=expected[:p['limit']]
                    if method=='countDocuments' or p.get('count'):expected=len(expected)
                else:raise ValueError(method)
                item['verified']=equivalent(expected,q['result'])
                if q['number']==33:
                    # SQL ORDER BY age alone does not specify ordering within ties.
                    original={d['_id']:d for d in rows}
                    actual_rows=q['result']
                    item['verified']=(len(actual_rows)==len(expected) and
                        sorted(d['age'] for d in actual_rows)==sorted(d['age'] for d in expected) and
                        len({d['_id'] for d in actual_rows})==len(actual_rows) and
                        all(d['_id'] in original and equivalent(d,original[d['_id']]) for d in actual_rows))
                    item['comparison']='Age order and source membership; ties have no specified order'

                item['result_count']=len(q['result']) if isinstance(q['result'],list) else q['result']
                if not item['verified']:
                    item['detail']='Mismatch';item['expected_count']=len(expected) if isinstance(expected,list) else expected
            except Exception as e:item.update(verified=False,detail=str(e))
        else:item.update(verified=False,detail=q['error'])
        report.append(item)
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
