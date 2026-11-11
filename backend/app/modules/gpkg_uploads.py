"""Disk-backed resumable uploads; chunk size is never a whole-file size cap."""
import hashlib,json,os,sqlite3,tempfile,time,uuid,threading,shutil,re
from pathlib import Path
from contextlib import closing
from .qgis_data import ApiError
ROOT=Path(os.getenv('GPKG_UPLOAD_DIR',str(Path(tempfile.gettempdir())/'gis-gpkg')))
CHUNK_BYTES=4*1024*1024
TTL=7*24*3600
_LOCKS=[threading.RLock() for _ in range(64)]
def lock(identifier):return _LOCKS[int(hashlib.sha256(str(identifier).encode()).hexdigest(),16)%len(_LOCKS)]
def quote(name):return '"'+name.replace('"','""')+'"'
def atomic(path,value):
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with open(temp,'x',encoding='utf-8') as stream:
            os.chmod(temp,0o600);json.dump(value,stream,ensure_ascii=False);stream.flush();os.fsync(stream.fileno())
        os.replace(temp,path)
    finally:temp.unlink(missing_ok=True)
def base(identifier,owner):
    try:identifier=str(uuid.UUID(identifier))
    except Exception:raise ApiError(400,'Invalid upload identifier')
    return ROOT/(hashlib.sha256(owner.encode()).hexdigest()[:16]+'-'+identifier)
def manifest(identifier,owner):return Path(str(base(identifier,owner))+'.json')
def load(identifier,owner):
    p=manifest(identifier,owner)
    if not p.is_file():raise ApiError(404,'Upload missing or belongs to another principal')
    if time.time()-p.stat().st_mtime>TTL:raise ApiError(410,'Upload expired; select file again')
    data=json.loads(p.read_text());os.utime(p,None);return data

def connect(path):
    db=sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True);db.row_factory=sqlite3.Row
    db.execute('PRAGMA query_only=ON');deadline=time.monotonic()+60
    db.set_progress_handler(lambda:time.monotonic()>deadline,10000);return db

def tables(db):
    result=[]
    for row in db.execute("SELECT table_name,data_type FROM gpkg_contents WHERE data_type IN ('features','attributes')"):
        name=row['table_name'];kind=db.execute('SELECT type FROM sqlite_master WHERE name=?',(name,)).fetchone()
        if not kind or kind[0]!='table':raise ApiError(422,'Only physical GeoPackage tables are supported')
        cols=[dict(c) for c in db.execute('PRAGMA table_info('+quote(name)+')')]
        geometry=db.execute('SELECT column_name,geometry_type_name,srs_id FROM gpkg_geometry_columns WHERE table_name=?',(name,)).fetchone() if db.execute("SELECT 1 FROM sqlite_master WHERE name='gpkg_geometry_columns'").fetchone() else None
        result.append({'name':name,'fields':[c['name'] for c in cols if not geometry or c['name']!=geometry['column_name']],
            'rows':db.execute('SELECT count(*) FROM '+quote(name)).fetchone()[0],'geometry':dict(geometry) if geometry else None,
            'pk':[c['name'] for c in sorted(cols,key=lambda c:c['pk'] or 999999) if c['pk']]})
    return result

def cleanup():
    """Delete only expired application upload/job cache, never source files or MongoDB."""
    now=time.time();removed=0
    for manifest_path in ROOT.glob('*.json'):
        if not re.fullmatch(r'[0-9a-f]{16}-[0-9a-f-]{36}\.json',manifest_path.name):continue
        with lock(manifest_path.stem[17:]):
            if manifest_path.exists() and now-manifest_path.stat().st_mtime>TTL:
                stem=manifest_path.with_suffix('')
                for candidate in [manifest_path,Path(str(stem)+'.part'),Path(str(stem)+'.gpkg'),*ROOT.glob(stem.name+'-*.job-ref')]:
                    if candidate.exists():candidate.unlink();removed+=1
    for path in ROOT.glob('*.job.sqlite'):
        if not re.fullmatch(r'[0-9a-f]{16}-[0-9a-f-]{36}\.job\.sqlite',path.name):continue
        identifier=path.name[17:-11]
        with lock(identifier):
            if path.exists() and now-path.stat().st_mtime>TTL:
                for candidate in [path,Path(str(path)+'-wal'),Path(str(path)+'-shm')]:
                    if candidate.exists():candidate.unlink();removed+=1
    return removed

def begin(payload,owner):
    size=payload.get('size')
    if type(size) is not int or size<1:raise ApiError(422,'Positive file size required')
    ROOT.mkdir(mode=0o700,parents=True,exist_ok=True);cleanup()
    identifier=str(uuid.uuid4());meta={'size':size,'filename':Path(str(payload.get('filename','data.gpkg'))).name,'complete':False}
    atomic(manifest(identifier,owner),meta)
    part=Path(str(base(identifier,owner))+'.part');part.touch(mode=0o600)
    return status(identifier,owner)

def status(identifier,owner):
    meta=load(identifier,owner);p=Path(str(base(identifier,owner))+('.gpkg' if meta['complete'] else '.part'))
    if not p.exists() and not meta['complete']:
        renamed=Path(str(base(identifier,owner))+'.gpkg')
        if renamed.exists():p=renamed
    received=p.stat().st_size if p.exists() else 0
    result={'upload_id':identifier,'received':received,'size':meta['size'],'complete':meta['complete'],'chunk_bytes':CHUNK_BYTES,'expires_seconds':TTL}
    if meta['complete']:
        from .gpkg_import import target_fields,requirements
        result.update(tables=meta['tables'],targets=target_fields(),requirements=requirements(),batch_rows=250)
    return result

def chunk(identifier,owner,offset,data):
    if type(offset) is not int or offset<0 or not 0<len(data)<=CHUNK_BYTES:raise ApiError(422,'Invalid chunk offset/size')
    with lock(identifier):
        meta=load(identifier,owner)
        if meta['complete']:return status(identifier,owner)
        path=Path(str(base(identifier,owner))+'.part')
        if not path.exists():path=Path(str(base(identifier,owner))+'.gpkg')
        received=path.stat().st_size
        if offset>received or offset+len(data)>meta['size']:raise ApiError(409,'Chunk offset does not match received file')
        overlap=min(len(data),received-offset)
        with open(path,'r+b') as stream:
            stream.seek(offset)
            if overlap and stream.read(overlap)!=data[:overlap]:raise ApiError(409,'Retry chunk differs from previously received bytes')
            if offset+len(data)>received:
                if shutil.disk_usage(ROOT).free<len(data)-overlap+16*1024*1024:raise ApiError(507,'Not enough upload disk space')
                stream.seek(received);stream.write(data[overlap:]);stream.flush();os.fsync(stream.fileno())
        return status(identifier,owner)

def finish(identifier,owner):
    with lock(identifier):
        meta=load(identifier,owner)
        if meta['complete']:return status(identifier,owner)
        source=Path(str(base(identifier,owner))+'.part');target=Path(str(base(identifier,owner))+'.gpkg')
        # A restart after rename but before manifest commit is safe.
        source=source if source.exists() else target
        if source.stat().st_size!=meta['size']:raise ApiError(409,'File is not completely uploaded')
        h=hashlib.sha256()
        with open(source,'rb') as stream:
            if stream.read(16)!=b'SQLite format 3\0':raise ApiError(422,'Not a GeoPackage SQLite file')
            stream.seek(0)
            while block:=stream.read(CHUNK_BYTES):h.update(block)
        try:
            with closing(connect(source)) as db:
                if db.execute('PRAGMA application_id').fetchone()[0]!=1196444487:raise ValueError('Not a GeoPackage')
                catalog=tables(db)
                if not catalog:raise ValueError('No supported physical tables')
                if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('SQLite integrity check failed')
        except (sqlite3.Error,ValueError):raise ApiError(422,'Invalid GeoPackage structure/integrity')
        if source!=target:os.replace(source,target)
        meta.update(complete=True,sha256=h.hexdigest(),tables=catalog);atomic(manifest(identifier,owner),meta)
        return status(identifier,owner)

def path_for(identifier,owner):
    meta=load(identifier,owner)
    if not meta['complete']:raise ApiError(409,'Complete upload before reading it')
    path=Path(str(base(identifier,owner))+'.gpkg')
    if not path.is_file():raise ApiError(404,'Uploaded file missing; select file again')
    return path
def fingerprint(identifier,owner):return load(identifier,owner)['sha256']
def upload(data,owner):
    """Compatibility for a single bounded HTTP body. New clients use chunks."""
    if not data:raise ApiError(422,'Select a GeoPackage')
    state=begin({'size':len(data)},owner);identifier=state['upload_id']
    for offset in range(0,len(data),CHUNK_BYTES):chunk(identifier,owner,offset,data[offset:offset+CHUNK_BYTES])
    return finish(identifier,owner)
