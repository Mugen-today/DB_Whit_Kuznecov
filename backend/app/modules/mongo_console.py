"""Parsed Mongo/Python read expressions. No eval, exec, server JavaScript or write pipelines."""
import ast,json,re,math,threading,time,uuid
import pymongo
from datetime import datetime,timezone
from bson import ObjectId,Decimal128,Int64,Regex,json_util
from pymongo.errors import PyMongoError
from . import records
from .qgis_data import ApiError
PRIVATE=['_owner_id','_request_hash','_dataset_source','_geometry_valid','_ambiguous_municipality','_previous_geometry']
TOKEN=re.compile(r'\s*(?:(?P<string>"(?:\\.|[^"\\])*"|\x27(?:\\.|[^\x27\\])*\x27)|(?P<number>\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|(?P<word>[$\w]+)|(?P<punct>[{}\[\](),:.;+*/-]))')
class Parser:
    def __init__(self,source):
        source=source.lstrip('\ufeff')
        self.tokens=[];pos=0
        while pos<len(source):
            if source[pos].isspace():pos+=1;continue
            if source.startswith('//',pos) or source[pos]=='#':
                end=source.find('\n',pos);pos=len(source) if end<0 else end+1;continue
            if source.startswith('/*',pos):
                end=source.find('*/',pos+2)
                if end<0:raise ApiError(400,'Unclosed query comment')
                pos=end+2;continue
            if source[pos]=='/' and (not self.tokens or self.tokens[-1][1] in (':','[',',','(')):
                start=pos;pos+=1;pattern=[];in_class=False
                while pos<len(source):
                    char=source[pos];pos+=1
                    if char=='\\':
                        if pos>=len(source):raise ApiError(400,'Unclosed regex literal')
                        other=source[pos];pos+=1;pattern.append(other if other=='/' else '\\'+other);continue
                    if char=='[':in_class=True
                    elif char==']':in_class=False
                    if char=='/' and not in_class:break
                    pattern.append(char)
                else:raise ApiError(400,'Unclosed regex literal at character '+str(start))
                start_flags=pos
                while pos<len(source) and source[pos].isalpha():pos+=1
                flags=source[start_flags:pos]
                if set(flags)-set('imsxu'):raise ApiError(400,'Supported regex flags: i m s x u')
                self.tokens.append(('regex',Regex(''.join(pattern),flags)));continue
            m=TOKEN.match(source,pos)
            if not m:raise ApiError(400,'Unexpected console syntax at character '+str(pos))
            self.tokens.append((m.lastgroup,m.group(m.lastgroup)));pos=m.end()
        self.i=0
    def peek(self):return self.tokens[self.i][1] if self.i<len(self.tokens) else ''
    def take(self,want=None):
        if self.i>=len(self.tokens):raise ApiError(400,'Incomplete expression')
        token=self.tokens[self.i];self.i+=1
        if want is not None and token[1]!=want:raise ApiError(400,'Expected '+want)
        return token
    def value(self,precedence=0):
        left=self.atom()
        ops={'+':10,'-':10,'*':20,'/':20}
        while self.peek() in ops and ops[self.peek()]>=precedence:
            op=self.take()[1];right=self.value(ops[op]+1)
            if type(left) not in (int,float) or type(right) not in (int,float):raise ApiError(400,'Arithmetic requires numeric literals')
            try:left={'+':lambda:left+right,'-':lambda:left-right,'*':lambda:left*right,'/':lambda:left/right}[op]()
            except ArithmeticError:raise ApiError(400,'Invalid arithmetic literal')
            if not math.isfinite(left) or abs(left)>1e18:raise ApiError(400,'Arithmetic literal out of range')
        return left
    def atom(self):
        kind,text=self.take()
        if kind=='regex':return text
        if text in ('-','+'):
            number=self.value(30)
            if type(number) not in (int,float):raise ApiError(400,'Numeric unary operand required')
            return -number if text=='-' else number
        if text=='{':
            out={}
            while self.peek()!='}':
                k,t=self.take();key=ast.literal_eval(t) if k=='string' else t
                self.take(':');out[key]=self.value()
                if self.peek()!=',':break
                self.take(',')
            self.take('}')
            if len(out)==1 and next(iter(out)) in ('$oid','$date','$numberDecimal','$numberLong','$numberInt','$binary','$timestamp'):
                try:return json_util.loads(json.dumps(out))
                except Exception:raise ApiError(400,'Invalid Extended JSON literal')
            return out
        if text=='[':
            out=[]
            while self.peek()!=']':
                out.append(self.value())
                if self.peek()!=',':break
                self.take(',')
            self.take(']');return out
        if kind=='string':return ast.literal_eval(text)
        if kind=='number':return float(text) if any(x in text for x in '.eE') else int(text)
        if text in ('null','None','true','false','True','False'):return {'null':None,'None':None,'true':True,'True':True,'false':False,'False':False}[text]
        if text=='new':text=self.take()[1]
        if text=='Date' and self.peek()=='.':
            self.take('.');self.take('now')
            if self.args():raise ApiError(400,'Date.now takes no arguments')
            return int(time.time()*1000)
        if text in ('ObjectId','ISODate','Date','NumberDecimal','Decimal128','NumberLong','NumberInt'):
            args=self.args()
            if text in ('ISODate','Date') and not args:return datetime.now(timezone.utc)
            if len(args)!=1:raise ApiError(400,'One constructor argument required')
            value=args[0]
            try:
                if text=='ObjectId':return ObjectId(value)
                if text in ('ISODate','Date'):
                    if type(value) in (int,float):return datetime.fromtimestamp(value/1000,tz=timezone.utc)
                    dt=datetime.fromisoformat(value.replace('Z','+00:00'))
                    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
                if text in ('NumberDecimal','Decimal128'):return Decimal128(str(value))
                if text=='NumberLong':return Int64(value)
                return int(value)
            except Exception:raise ApiError(400,'Invalid BSON constructor')
        raise ApiError(400,'Unsupported literal '+text)
    def args(self):
        self.take('(');args=[]
        while self.peek()!=')':
            args.append(self.value())
            if self.peek()!=',':break
            self.take(',')
        self.take(')');return args
    def parse(self):
        self.take('db')
        if self.peek()=='[':
            self.take('[');collection=self.value();self.take(']')
        else:
            self.take('.');collection=self.take()[1]
            if collection=='getCollection':
                values=self.args()
                if len(values)!=1:raise ApiError(400,'getCollection requires one collection name')
                collection=values[0]
        if not isinstance(collection,str):raise ApiError(400,'Collection name must be text')
        self.take('.');op=self.take()[1];args=self.args();chain=[]
        while self.peek()=='.':
            self.take('.');name=self.take()[1];values=self.args()
            if name in ('pretty','toArray'):
                if values:raise ApiError(400,name+' takes no arguments')
            else:chain.append((name,values))
        if self.peek()==';':self.take(';')
        if self.peek():raise ApiError(400,'One read expression required')
        return collection,op,args,chain
def guard(value):
    if isinstance(value,dict):
        for key,item in value.items():
            if key in ('$where','$function','$accumulator','$out','$merge'):raise ApiError(403,'Executable/write operators are forbidden')
            if any(p.startswith('_') and p!='_id' for p in key.lstrip('$').split('.')):raise ApiError(403,'Private fields are not queryable')
            guard(item)
    elif isinstance(value,list):
        for item in value:guard(item)
    elif isinstance(value,str) and value.startswith('$') and not value.startswith('$$'):
        if any(p.startswith('_') and p!='_id' for p in value[1:].split('.')):raise ApiError(403,'Private fields are not queryable')
def scoped_filter(name,filt,role,owner):
    if not isinstance(filt,dict):raise ApiError(400,'Filter must be an object')
    guard(filt)
    clauses=[records.scope(role,owner),filt]
    if name=='Geodata' and any(op in json_util.dumps(filt) for op in ('$near','$nearSphere','$geoWithin','$geoIntersects')):
        clauses.append({'_geometry_valid':True})
    return {'$and':clauses}
STAGES={'$match','$group','$project','$unwind','$lookup','$sort','$limit','$skip','$count','$addFields','$set','$unset','$replaceRoot','$replaceWith','$facet','$bucket','$bucketAuto','$geoNear','$sample','$sortByCount'}
def pipeline(name,stages,role,owner,fresh=True):
    records.authorized(name,role)
    if not isinstance(stages,list) or len(stages)>100:raise ApiError(400,'Pipeline must contain at most 100 stages')
    guard(stages);out=[]
    for stage in stages:
        if not isinstance(stage,dict) or len(stage)!=1:raise ApiError(400,'One operator per stage required')
        op,value=next(iter(stage.items()))
        if op not in STAGES:raise ApiError(403,'Unsupported read stage '+op)
        if op=='$lookup':
            if not isinstance(value,dict) or not isinstance(value.get('from'),str):raise ApiError(400,'lookup.from must name a model collection')
            value=dict(value);value['pipeline']=pipeline(value['from'],value.get('pipeline',[]),role,owner)
        if op=='$facet':
            value={k:pipeline(name,v,role,owner,False) for k,v in value.items()}
        if op=='$geoNear':
            if out or name!='Geodata' or not fresh:raise ApiError(400,'geoNear must be first and operate on Geodata')
            value=dict(value);value['query']=scoped_filter(name,value.get('query',{}),role,owner)
            value['query']['$and'].append({'_geometry_valid':True});value['key']='geometry'
        out.append({op:value})
    if fresh:
        if out and '$geoNear' in out[0]:out.insert(1,{'$unset':PRIVATE})
        else:
            source_scope=records.scope(role,owner)
            if name=='Geodata' and any(op in json_util.dumps(stages) for op in ('$geoWithin','$geoIntersects')):source_scope={**source_scope,'_geometry_valid':True}
            out=[{'$match':source_scope},{'$unset':PRIVATE}]+out
    return out
def sanitize(value):
    if isinstance(value,dict):return {k:sanitize(v) for k,v in value.items() if k=='_id' or not k.startswith('_')}
    if isinstance(value,list):return [sanitize(v) for v in value]
    return records.wire(value)
JOBS={};LOCK=threading.RLock()
def close(job):
    if hasattr(job['iterator'],'close'):job['iterator'].close()
def _read_page(identifier,role,owner):
    with LOCK:
        job=JOBS.get(identifier)
        if not job or job['identity']!=(role,owner):raise ApiError(404,'Query cursor missing or belongs to another principal')
        if job['expires']<time.monotonic():
            close(job);del JOBS[identifier];raise ApiError(410,'Query expired; execute it again')
        output=[];size=0
        for _ in range(200):
            try:
                item=job.pop('pending') if 'pending' in job else next(job['iterator'])
            except StopIteration:break
            encoded=sanitize(item);length=len(json.dumps(encoded,ensure_ascii=False).encode())
            if output and size+length>1500000:job['pending']=item;break
            output.append(encoded);size+=length
        if 'pending' not in job:
            try:job['pending']=next(job['iterator'])
            except StopIteration:pass
        more='pending' in job
        if not more:close(job);del JOBS[identifier]
        else:job['expires']=time.monotonic()+900
        return {'records':output,'cursor':identifier if more else None,'operation':job['operation']}
def read_page(identifier,role,owner):
    try:
        with pymongo.timeout(125):return _read_page(identifier,role,owner)
    except PyMongoError:
        with LOCK:
            job=JOBS.get(identifier)
            if job and job['identity']==(role,owner):close(JOBS.pop(identifier))
        raise

def _execute(store,role,owner,payload):
    if payload.get('cursor'):return read_page(payload['cursor'],role,owner)
    source=payload.get('code')
    if isinstance(source,str):
        if source.lstrip().startswith('{'):
            try:return execute(store,role,owner,json_util.loads(source))
            except ValueError:raise ApiError(400,'Invalid JSON query')
        if len(source)>128000:raise ApiError(413,'Console expression too large')
        if source.strip().startswith(('create_record(','update_record(')):
            parser=Parser(source);helper=parser.take()[1];args=parser.args()
            if parser.peek():raise ApiError(400,'One helper call required')
            if helper=='create_record' and len(args)==1:return records.create(store,role,owner,args[0])
            if helper=='update_record' and len(args)==4:
                from . import entities
                return entities.edit(store,role,owner,args[0],args[1],{'revision':args[2],'changes':args[3]})
            raise ApiError(400,'Invalid helper arguments')
        name,op,args,chain=Parser(source).parse()
    else:
        name=payload.get('collection');op=payload.get('operation','find');chain=[]
        args={'find':[payload.get('filter',{}),payload.get('projection',{})],'aggregate':[payload.get('pipeline',[])],
              'countDocuments':[payload.get('filter',{})],'distinct':[payload.get('field'),payload.get('filter',{})]}.get(op,[])
    records.authorized(name,role);db=store.database(role)
    timeout=120000 if role in ('reader','admin') else 60000
    if op=='countDocuments':
        if chain or len(args)>1:raise ApiError(400,'Invalid countDocuments arguments')
        return {'value':db[name].count_documents(scoped_filter(name,args[0] if args else {},role,owner),maxTimeMS=timeout),'operation':op}
    if op=='aggregate':
        if len(args)!=1 or chain:raise ApiError(400,'aggregate requires one pipeline')
        iterator=db[name].aggregate(pipeline(name,args[0],role,owner),allowDiskUse=True,maxTimeMS=timeout,batchSize=200)
    elif op=='distinct':
        if not 1<=len(args)<=2 or chain or not isinstance(args[0],str) or args[0].startswith('_') and args[0]!='_id':raise ApiError(400,'distinct requires a public field name')
        guard('$'+args[0]);field=args[0]
        query=scoped_filter(name,args[1] if len(args)==2 else {},role,owner)
        stages=[{'$match':query},{'$match':{field:{'$exists':True}}},{'$project':{'v':{'$cond':[{'$isArray':'$'+field},'$'+field,['$'+field]]}}},{'$unwind':'$v'},{'$group':{'_id':'$v'}}]
        iterator=(d['_id'] for d in db[name].aggregate(stages,allowDiskUse=True,maxTimeMS=timeout,batchSize=200))
    elif op=='find':
        if len(args)>2:raise ApiError(400,'find accepts filter and projection')
        filt=scoped_filter(name,args[0] if args else {},role,owner)
        projection=args[1] if len(args)>1 and args[1] else None
        if projection:guard(projection)
        cursor=db[name].find(filt,projection,max_time_ms=timeout).batch_size(200)
        for method,arguments in chain:
            if len(arguments)!=1 or method not in ('sort','limit','skip'):raise ApiError(400,'Supported cursor modifiers: sort, limit, skip')
            value=arguments[0]
            if method=='sort':
                guard(value)
                if not isinstance(value,dict) or any(v not in (1,-1) for v in value.values()):raise ApiError(400,'sort requires field:1/-1')
                cursor=cursor.sort(list(value.items()))
            else:
                if type(value) is not int or value<0:raise ApiError(400,'Nonnegative integer required')
                cursor=getattr(cursor,method)(value)
        iterator=cursor
    else:raise ApiError(400,'Supported: find, aggregate, countDocuments, distinct')
    with LOCK:
        for key,job in list(JOBS.items()):
            if job['expires']<time.monotonic():close(job);del JOBS[key]
        if len(JOBS)>=64:raise ApiError(429,'Too many open query cursors')
        identifier=str(uuid.uuid4());JOBS[identifier]={'iterator':iter(iterator),'operation':op,'identity':(role,owner),'expires':time.monotonic()+900}
    try:return read_page(identifier,role,owner)
    except PyMongoError as exc:
        with LOCK:
            if identifier in JOBS:close(JOBS.pop(identifier))
        raise


def execute(store,role,owner,payload):
    try:
        with pymongo.timeout(125):
            return _execute(store,role,owner,payload)
    except (RecursionError,OverflowError):
        raise ApiError(400,'Query is too deeply nested or contains an out-of-range literal')
    except PyMongoError as exc:
        details=getattr(exc,'details',None) or {}
        message=str(details.get('errmsg','Check query syntax, operators, indexes or execution time'))[:600]
        raise ApiError(400,'MongoDB query failed (code '+str(getattr(exc,'code','unknown'))+'): '+message)
