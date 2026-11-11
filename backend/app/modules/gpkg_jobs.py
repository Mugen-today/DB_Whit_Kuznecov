"""Durable, bounded validation and import. No total row count limit."""
import json,uuid,hashlib,sqlite3,time,os
from contextlib import closing
from bson import json_util
from . import gpkg_uploads as files, gpkg_import as mapping, entities, records
from .qgis_data import ApiError
VALIDATE_BATCH=250
WRITE_BATCH=25

def job_path(identifier,owner):return files.base(identifier,owner).with_suffix('.job.sqlite')
def connect(path):
    db=sqlite3.connect(path,timeout=30);db.row_factory=sqlite3.Row;db.execute('PRAGMA journal_mode=WAL');return db

def read(db):return json_util.loads(db.execute('SELECT value FROM state WHERE id=1').fetchone()[0])
def save(db,state):
    db.execute('UPDATE state SET value=? WHERE id=1',(json_util.dumps(state),));db.commit()
def open_job(identifier,owner,role):
    entities.write_role(role);path=job_path(identifier,owner)
    if not path.is_file():raise ApiError(404,'Import job missing or belongs to another principal')
    if time.time()-path.stat().st_mtime>files.TTL:raise ApiError(410,'Import job expired; select file again')
    db=connect(path);state=read(db)
    if state['role']!=role:db.close();raise ApiError(403,'Import job belongs to another role')
    try:files.path_for(state['payload']['upload_id'],owner)
    except Exception:db.close();raise
    os.utime(path,None);return db,state

def public(identifier,state,owner,detailed=False):
    result={'job_id':identifier,'status':state['status'],'total':state['total'],'checked':state['checked'],
        'applied':state['applied'],'errors':state['errors'],'error_total':state['error_total'],
        'validation_batch_rows':VALIDATE_BATCH,'import_batch_rows':WRITE_BATCH,'valid':state['status'] in ('ready','importing','complete')}
    if state.get('last_error'):result['last_error']=state['last_error']
    if detailed:result.update(payload=state['payload'],upload=files.status(state['payload']['upload_id'],owner))
    return result

def start(store,role,owner,payload):
    entities.write_role(role)
    config={k:payload[k] for k in ('upload_id','table','mapping','use_geometry','mode') if k in payload}
    path,meta,targets,digest=mapping.context(config,owner)
    identifier=str(uuid.uuid4());target=job_path(identifier,owner)
    state={'payload':config,'role':role,'table':meta,'digest':digest,'status':'validating','checked':0,'applied':0,
        'total':meta['rows'],'last_key':None,'errors':[],'error_total':0}
    try:
        with closing(connect(target)) as db:
            db.execute('CREATE TABLE state(id INTEGER PRIMARY KEY,value TEXT NOT NULL)')
            db.execute('CREATE TABLE rows(seq INTEGER PRIMARY KEY, source_key TEXT UNIQUE NOT NULL, payload TEXT NOT NULL)')
            db.execute('INSERT INTO state VALUES(1,?)',(json_util.dumps(state),));db.commit()
        os.chmod(target,0o600)
    except Exception:target.unlink(missing_ok=True);raise
    return public(identifier,state,owner)

def status(role,owner,identifier):
    with files.lock(identifier):
        db,state=open_job(identifier,owner,role)
        with closing(db):return public(identifier,state,owner,True)

def validate(store,role,owner,identifier):
    with files.lock(identifier):
        job,state=open_job(identifier,owner,role)
        with closing(job):
            if state['status']!='validating':return public(identifier,state,owner)
            payload=state['payload'];meta=state['table']
            # Targets and schema are checked once per bounded page; the source
            # file/catalog/digest are not scanned or hashed again.
            targets={}
            for target,source in payload['mapping'].items():
                spec=records.schemas()[target.split('.')[0]]
                for part in target.split('.')[1:]:spec=spec['properties'][part]
                targets[target]=(source,spec)
            with closing(files.connect(files.path_for(payload['upload_id'],owner))) as source:
                batch,overflow=mapping.source_page(source,meta,targets,payload,state['last_key'],VALIDATE_BATCH)
                for row in batch:
                    index=state['checked']+1
                    try:
                        if row[overflow]:raise ApiError(422,'Selected attributes exceed per-value (1 MiB) or per-row (2 MiB) limits')
                        item=mapping.row_record(row,meta,targets,payload,state['digest'],owner,source)
                        docs=records.prepare(item,owner) if payload.get('mode','entities')=='bundle' else entities.plan(item,owner)
                        for name,doc in docs.items():entities.check_links(store.database(role),role,owner,name,doc,pending=docs)
                        job.execute('INSERT INTO rows VALUES(?,?,?)',(index,json_util.dumps([row[k] for k in meta['pk']]),json.dumps(item,ensure_ascii=False)))
                    except (ApiError,ValueError,TypeError,OverflowError,sqlite3.IntegrityError) as exc:
                        state['error_total']+=1
                        if len(state['errors'])<100:state['errors'].append({'row':index,'detail':str(exc)})
                    state['checked']=index
                if batch:state['last_key']=[batch[-1][k] for k in meta['pk']]
                if not batch or state['checked']>=state['total']:
                    if state['checked']!=state['total']:
                        state['error_total']+=1;state['errors'].append({'detail':'Source count mismatch; no import permitted'})
                    state['status']='invalid' if state['error_total'] else 'ready'
            save(job,state)
            return public(identifier,state,owner)

def apply(store,role,owner,identifier):
    with files.lock(identifier):
        job,state=open_job(identifier,owner,role)
        with closing(job):
            if state['status']=='complete':return public(identifier,state,owner)
            if state['status'] not in ('ready','importing','paused'):raise ApiError(409,'Validate all source rows successfully before importing')
            cursor=job.execute('SELECT seq,payload FROM rows WHERE seq>? ORDER BY seq LIMIT ?',(state['applied'],WRITE_BATCH))
            batch=[];size=0
            for row in cursor:
                batch.append(row);size+=len(row['payload'].encode('utf-8'))
                if size>=2097152:break
            cursor.close()
            state['status']='importing';state.pop('last_error',None)
            for row in batch:
                item=json.loads(row['payload'])
                try:
                    if state['payload'].get('mode','entities')=='bundle':records.create(store,role,owner,item)
                    else:entities.create(store,role,owner,item)
                except Exception as exc:
                    # A timeout can be retried: deterministic IDs prevent duplicates
                    # if MongoDB committed before the HTTP response was lost.
                    state['status']='paused';state['last_error']={'row':row['seq'],'detail':str(exc)[:1000]};save(job,state)
                    return public(identifier,state,owner)
                state['applied']=row['seq'];save(job,state)
            if state['applied']==state['total']:state['status']='complete'
            elif not batch:raise ApiError(409,'Staged row gap; import stopped without skipping records')
            save(job,state);return public(identifier,state,owner)

def legacy(store,role,owner,payload,apply_rows=False):
    entities.write_role(role)
    # Compatibility routes retain their response shape; new clients explicitly
    # step jobs so arbitrarily large validation never needs one long HTTP request.
    config={k:payload[k] for k in ('upload_id','table','mapping','use_geometry','mode') if k in payload}
    key=hashlib.sha256(json.dumps([role,config],sort_keys=True).encode()).hexdigest()
    alias=files.base(config.get('upload_id'),owner).with_name(files.base(config.get('upload_id'),owner).name+'-'+key+'.job-ref')
    with files.lock(str(alias)):
        if alias.exists():identifier=alias.read_text()
        else:
            identifier=start(store,role,owner,config)['job_id'];alias.write_text(identifier);alias.chmod(0o600)
    data=status(role,owner,identifier)
    while data['status']=='validating':data=validate(store,role,owner,identifier)
    if data['status']=='invalid':raise ApiError(422,json.dumps({'message':'No records written; fix mapping/data','errors':data['errors'],'error_total':data['error_total']},ensure_ascii=False))
    if not apply_rows:return {'valid':True,'rows':data['total'],'job_id':identifier}
    offset=payload.get('offset',0)
    if type(offset) is not int or not 0<=offset<data['total']:raise ApiError(400,'Invalid offset')
    if offset>data['applied']:raise ApiError(409,'Cannot skip an import batch')
    if offset==data['applied']:data=apply(store,role,owner,identifier)
    if data['status']=='paused':raise ApiError(409,json.dumps(data,ensure_ascii=False))
    end=min(offset+WRITE_BATCH,data['total'],data['applied'])
    return {'saved':end-offset,'next_offset':end if end<data['total'] else None,'total':data['total'],'job_id':identifier}
