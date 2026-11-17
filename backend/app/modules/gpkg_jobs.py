"""Durable GPKG error policies, complete paged reports and confirmed receipts."""
import json,uuid,hashlib,sqlite3,time,os
from contextlib import closing
from bson import json_util
from . import gpkg_uploads as files,gpkg_import as mapping,entities,records
from .gpkg_errors import issue,classify,fail,ImportFailure
from .qgis_data import ApiError
from .validation_lookup import LookupDatabase
VALIDATE_BATCH=250
WRITE_BATCH=25

def job_path(identifier,owner):return files.base(identifier,owner).with_suffix('.job.sqlite')
def connect(path):
    db=sqlite3.connect(path,timeout=30);db.row_factory=sqlite3.Row;db.execute('PRAGMA journal_mode=WAL')
    return db

def read(db):return json_util.loads(db.execute('SELECT value FROM state WHERE id=1').fetchone()[0])
def save(db,state):
    db.execute('UPDATE state SET value=? WHERE id=1',(json_util.dumps(state),));db.commit()
def migrate(db,state):
    columns={r[1] for r in db.execute('PRAGMA table_info(rows)')}
    for name,spec in [('valid','INTEGER NOT NULL DEFAULT 1'),('outcome',"TEXT NOT NULL DEFAULT 'pending'"),('receipt',"TEXT NOT NULL DEFAULT '{}'")]:
        if name not in columns:db.execute('ALTER TABLE rows ADD COLUMN '+name+' '+spec)
    db.execute('CREATE TABLE IF NOT EXISTS issues(id INTEGER PRIMARY KEY,severity TEXT NOT NULL,stage TEXT NOT NULL,row_no INTEGER,field TEXT,code TEXT,reason TEXT,retryable INTEGER,source_key TEXT)')
    state.setdefault('error_policy','strict');state.setdefault('position',state.get('applied',0));state.setdefault('successful_rows',state.get('applied',0))
    state.setdefault('valid_rows',state.get('checked',0)-state.get('error_total',0));state.setdefault('rejected_rows',state.get('error_total',0))
    state.setdefault('critical_total',0);state.setdefault('failed_apply_rows',0);state.setdefault('warning_total',0);state.setdefault('documents_present',0)
    state.setdefault('documents_created_by_job',0);state.setdefault('documents_reused',0);state.setdefault('by_collection',{})
    if 'report_v2' not in state:
        old_errors=list(state.get('errors',[]));state['errors']=[]
        for old in old_errors:add_issue(db,state,issue('validation',old.get('detail','Invalid row'),severity='error',row=old.get('row'),code='legacy_error'),count=False)
        state['report_v2']=True
    save(db,state)

def open_job(identifier,owner,role):
    entities.write_role(role);path=job_path(identifier,owner)
    if not path.is_file():raise ApiError(404,'Import job missing or belongs to another principal')
    if time.time()-path.stat().st_mtime>files.TTL:raise ApiError(410,'Import job expired; select file again')
    db=connect(path);state=read(db)
    if state['role']!=role:db.close();raise ApiError(403,'Import job belongs to another role')
    try:migrate(db,state)
    except Exception:db.close();raise
    os.utime(path,None);return db,state

def add_issue(db,state,data,count=True):
    db.execute('INSERT INTO issues(severity,stage,row_no,field,code,reason,retryable,source_key) VALUES(?,?,?,?,?,?,?,?)',
        (data['severity'],data['stage'],data.get('row'),data.get('field'),data['code'],data['reason'],int(data.get('retryable',False)),json_util.dumps(data.get('source_key'))))
    if count and data['severity']=='critical':state['critical_total']+=1
    if count and data['severity']=='warning':state['warning_total']+=1
    if data['severity'] in ('error','critical'):
        state['last_error']=data
        if len(state['errors'])<100:state['errors'].append({**data,'detail':data['reason']})

def public(identifier,state,owner,detailed=False):
    failed=state.get('rejected_rows',0)+state.get('failed_apply_rows',0)
    result={k:state.get(k,0) for k in ('total','checked','position','successful_rows','valid_rows','rejected_rows','failed_apply_rows','warning_total','critical_total','documents_present','documents_created_by_job','documents_reused')}
    result.update(job_id=identifier,status=state['status'],applied=state.get('successful_rows',0),error_policy=state.get('error_policy','strict'),
        errors=state['errors'],error_total=state['error_total'],by_collection=state.get('by_collection',{}),failed_rows=failed,
        validation_batch_rows=VALIDATE_BATCH,import_batch_rows=WRITE_BATCH,
        valid=state['status'] in ('ready','importing','complete','complete_with_errors','paused'),
        report_url='/v1/gpkg/jobs/'+identifier+'/report')
    if state.get('last_error'):result['last_error']=state['last_error']
    if detailed:
        result['payload']=state['payload']
        try:result['upload']=files.status(state['payload']['upload_id'],owner)
        except Exception as exc:result.update(upload=None,file_error=classify(exc,'structure'))
    return result

def report(role,owner,identifier,after=0,limit=100):
    if type(after)is not int or after<0 or type(limit)is not int or not 1<=limit<=500:raise ApiError(400,'Invalid report cursor/limit')
    with files.lock(identifier):
        db,state=open_job(identifier,owner,role)
        with closing(db):
            rows=db.execute('SELECT * FROM issues WHERE id>? ORDER BY id LIMIT ?',(after,limit+1)).fetchall();items=[]
            for row in rows[:limit]:items.append({'id':row['id'],'severity':row['severity'],'stage':row['stage'],'row':row['row_no'],'field':row['field'],'code':row['code'],'reason':row['reason'],'retryable':bool(row['retryable']),'source_key':records.wire(json_util.loads(row['source_key']))})
            return {'summary':public(identifier,state,owner),'issues':items,'next':items[-1]['id'] if len(rows)>limit else None,'issues_total':db.execute('SELECT count(*) FROM issues').fetchone()[0]}

def availability(store,role):
    # A read check also for geometry-only imports; otherwise a dead MongoDB
    # connection would only be noticed after validation of the entire file.
    store.database(role).command('ping')

def start(store,role,owner,payload):
    entities.write_role(role)
    policy=payload.get('error_policy','strict')
    if policy not in ('strict','partial'):fail('mapping','error_policy must be strict or partial','error_policy')
    config={k:payload[k] for k in ('upload_id','table','mapping','use_geometry','mode') if k in payload};config['error_policy']=policy
    path,meta,targets,digest=mapping.context(config,owner)
    try:availability(store,role)
    except Exception as exc:raise ImportFailure(503,classify(exc,'connection'))
    identifier=str(uuid.uuid4());target=job_path(identifier,owner)
    state={'payload':config,'role':role,'table':meta,'digest':digest,'error_policy':policy,'status':'validating','checked':0,'applied':0,
        'position':0,'successful_rows':0,'valid_rows':0,'rejected_rows':0,'failed_apply_rows':0,'warning_total':0,
        'critical_total':0,'documents_present':0,'documents_created_by_job':0,'documents_reused':0,'by_collection':{},
        'total':meta['rows'],'last_key':None,'errors':[],'error_total':0,'report_v2':True}
    try:
        with closing(connect(target)) as db:
            db.execute('CREATE TABLE state(id INTEGER PRIMARY KEY,value TEXT NOT NULL)');db.execute('CREATE TABLE rows(seq INTEGER PRIMARY KEY,source_key TEXT UNIQUE NOT NULL,payload TEXT NOT NULL,valid INTEGER NOT NULL DEFAULT 1,outcome TEXT NOT NULL DEFAULT \'pending\',receipt TEXT NOT NULL DEFAULT \'{}\')')
            db.execute('INSERT INTO state VALUES(1,?)',(json_util.dumps(state),));db.commit();migrate(db,state)
            selected={k.split('.')[0] for k in targets}
            if meta['geometry'] and config.get('use_geometry',True):selected.add('Geodata')
            for name in sorted(selected):
                for field in sorted(records.schemas()[name]['properties']):
                    target_field=name+'.'+field
                    if field.startswith('_') or field=='instance' or field in mapping.requirements().get(name,[]) or target_field in targets or field in records.LINKS.get(name,{}):continue
                    if name=='Geodata' and field=='geometry':continue
                    if name=='Geodata' and field in ('Longitude','Latitude') and meta['geometry'] and config.get('use_geometry',True):continue
                    add_issue(db,state,issue('mapping','Optional field is not mapped; it will remain absent',severity='warning',field=target_field,code='optional_mapping'))
            save(db,state)
        os.chmod(target,0o600)
    except Exception:target.unlink(missing_ok=True);raise
    return public(identifier,state,owner)

def status(role,owner,identifier):
    with files.lock(identifier):
        db,state=open_job(identifier,owner,role)
        with closing(db):return public(identifier,state,owner,True)

def halt(db,state,exc,stage,row=None,source_key=None):
    data=classify(exc,stage,row,source_key=source_key);add_issue(db,state,data)
    state['status']='blocked' if data['severity']=='critical' else 'failed'
    state['blocked_stage']=stage;save(db,state)
    return data

def validate(store,role,owner,identifier):
    with files.lock(identifier):
        job,state=open_job(identifier,owner,role)
        with closing(job):
            if state['status']=='blocked' and state.get('blocked_stage')=='validation' and state.get('last_error',{}).get('retryable'):state['status']='validating'
            if state['status']!='validating':return public(identifier,state,owner)
            payload=state['payload'];meta=state['table'];targets={}
            try:
                availability(store,role)
                database=LookupDatabase(store.database(role))
                for target,source in payload['mapping'].items():
                    spec=records.schemas()[target.split('.')[0]]
                    for part in target.split('.')[1:]:spec=spec['properties'][part]
                    targets[target]=(source,spec)
                with closing(files.connect(files.path_for(payload['upload_id'],owner))) as source:
                    batch,overflow=mapping.source_page(source,meta,targets,payload,state['last_key'],VALIDATE_BATCH)
                    for row in batch:
                        index=state['checked']+1;key=[row[k] for k in meta['pk']]
                        if any(k is None for k in key):fail('validation','A stable non-null primary key is required',meta['pk'][0],'invalid_primary_key')
                        # Atomic SQLite savepoint keeps an infrastructure failure
                        # from checkpointing half of a source row.
                        job.execute('SAVEPOINT source_row');warnings=[]
                        try:
                            if row[overflow]:raise ApiError(422,'Selected attributes exceed per-value/row limits')
                            item=mapping.row_record(row,meta,targets,payload,state['digest'],owner,source,warnings,index)
                            docs=records.prepare(item,owner) if payload.get('mode','entities')=='bundle' else entities.plan(item,owner)
                            for name,doc in docs.items():
                                entities.check_links(database,role,owner,name,doc,pending=docs)
                                old=database[name].find_one({'_id':doc['_id']},{'_request_hash':1,'_owner_id':1})
                                if old and (old.get('_request_hash')!=doc['_request_hash'] or old.get('_owner_id')!=owner):raise ApiError(409,name+'._id: existing document has a different owner or content')
                            job.execute('INSERT INTO rows(seq,source_key,payload) VALUES(?,?,?)',(index,json_util.dumps(key),json.dumps(item,ensure_ascii=False)))
                            state['valid_rows']+=1
                        except Exception as exc:
                            data=classify(exc,'validation',index,source_key=key)
                            if data['severity']=='critical':
                                job.execute('ROLLBACK TO source_row');job.execute('RELEASE source_row');raise
                            job.execute('INSERT INTO rows(seq,source_key,payload,valid,outcome) VALUES(?,?,?,0,?)',(index,json_util.dumps(key),'{}','rejected'))
                            state['error_total']+=1;state['rejected_rows']+=1;add_issue(job,state,data)
                        for warning in warnings:warning['source_key']=key;add_issue(job,state,warning)
                        job.execute('RELEASE source_row');state['checked']=index;state['last_key']=key
                    if not batch or state['checked']>=state['total']:
                        if state['checked']!=state['total']:fail('validation','Source count mismatch; import stopped',code='source_count')
                        state['status']='invalid' if state['rejected_rows'] and state['error_policy']=='strict' else 'ready' if state['valid_rows'] else 'invalid'
            except Exception as exc:
                halt(job,state,exc,'validation',state['checked']+1)
                return public(identifier,state,owner)
            save(job,state);return public(identifier,state,owner)

def apply(store,role,owner,identifier):
    with files.lock(identifier):
        job,state=open_job(identifier,owner,role)
        with closing(job):
            if state['status'] in ('complete','complete_with_errors'):return public(identifier,state,owner)
            if state['status']=='blocked' and state.get('blocked_stage')=='write' and state.get('last_error',{}).get('retryable'):state['status']='paused'
            if state['status'] not in ('ready','importing','paused'):raise ApiError(409,'All rows must be checked; strict mode rejects any invalid row')
            try:
                files.path_for(state['payload']['upload_id'],owner);availability(store,role)
            except Exception as exc:
                halt(job,state,exc,'write',state['position']+1);return public(identifier,state,owner)
            cursor=job.execute('SELECT * FROM rows WHERE seq>? ORDER BY seq LIMIT ?',(state['position'],WRITE_BATCH));batch=[];size=0
            for row in cursor:
                batch.append(row);size+=len(row['payload'].encode('utf-8'))
                if size>=2097152:break
            cursor.close();state['status']='importing'
            for row in batch:
                if row['seq']!=state['position']+1:
                    halt(job,state,ApiError(503,'Staged row gap; no rows were skipped'),'write',state['position']+1);break
                if not row['valid']:
                    state['position']=row['seq'];save(job,state);continue
                item=json.loads(row['payload']);key=json_util.loads(row['source_key'])
                try:
                    if state['payload'].get('mode','entities')=='bundle':records.prepare(item,owner)
                    receipt=entities.create(store,role,owner,item,ingestion={'job_id':identifier})
                except Exception as exc:
                    data=classify(exc,'write',row['seq'],source_key=key);add_issue(job,state,data)
                    if data['severity']=='critical':state['status']='blocked';state['blocked_stage']='write';save(job,state);break
                    if state['error_policy']=='strict':state['status']='failed';state['failed_apply_rows']+=1;state['error_total']+=1;save(job,state);break
                    state['failed_apply_rows']+=1;state['error_total']+=1;state['position']=row['seq']
                    job.execute("UPDATE rows SET outcome='rejected_write' WHERE seq=?",(row['seq'],));save(job,state);continue
                receipt=receipt or {};ids=receipt.get('ids',{});created=receipt.get('created_by_job',{})
                state['position']=row['seq'];state['successful_rows']+=1;state['applied']=state['successful_rows']
                state['documents_present']+=len(ids);state['documents_created_by_job']+=sum(created.values())
                state['documents_reused']+=sum(1 for name in ids if not created.get(name))
                for name in ids:state['by_collection'][name]=state['by_collection'].get(name,0)+1
                job.execute("UPDATE rows SET outcome='written',receipt=? WHERE seq=?",(json.dumps(receipt),row['seq']));save(job,state)
            if state['status']=='importing':
                if state['position']==state['total']:state['status']='complete_with_errors' if state['rejected_rows']+state['failed_apply_rows'] else 'complete'
                elif not batch:halt(job,state,ApiError(503,'Staged row gap; import stopped'),'write',state['position']+1)
            save(job,state);return public(identifier,state,owner)

def legacy(store,role,owner,payload,apply_rows=False):
    entities.write_role(role)
    if payload.get('error_policy','strict')!='strict':fail('mapping','Partial mode requires the jobs API and its full report','error_policy')
    config={k:payload[k] for k in ('upload_id','table','mapping','use_geometry','mode','error_policy') if k in payload}
    key=hashlib.sha256(json.dumps([role,config],sort_keys=True).encode()).hexdigest()
    alias=files.base(config.get('upload_id'),owner).with_name(files.base(config.get('upload_id'),owner).name+'-'+key+'.job-ref')
    with files.lock(str(alias)):
        if alias.exists():identifier=alias.read_text()
        else:identifier=start(store,role,owner,config)['job_id'];alias.write_text(identifier);alias.chmod(0o600)
    data=status(role,owner,identifier)
    while data['status']=='validating':data=validate(store,role,owner,identifier)
    if data['status'] not in ('ready','importing','complete','paused'):
        raise ImportFailure(422 if data['status']=='invalid' else 503,data.get('last_error') or issue('validation','No records written; fix input',code='invalid_rows'))
    if not apply_rows:return {'valid':True,'rows':data['total'],'job_id':identifier}
    offset=payload.get('offset',0)
    if type(offset)is not int or not 0<=offset<data['total']:raise ApiError(400,'Invalid offset')
    if offset>data['position']:raise ApiError(409,'Cannot skip an import batch')
    if offset==data['position']:data=apply(store,role,owner,identifier)
    if data['status'] in ('blocked','failed'):raise ImportFailure(503 if data['status']=='blocked' else 409,data['last_error'])
    end=min(offset+WRITE_BATCH,data['total'],data['position'])
    return {'saved':end-offset,'next_offset':end if end<data['total'] else None,'total':data['total'],'job_id':identifier}
