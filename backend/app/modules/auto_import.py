"""Explicit, insert-only historical importer; no source files bundled."""
import argparse,hashlib,json,sqlite3,tempfile,sys,os,zlib
from . import gpkg_uploads as staging_files
from pathlib import Path
from datetime import datetime,timezone
from contextlib import closing,ExitStack
from bson import json_util
from openpyxl import load_workbook
from . import records,entities
from .seed_excel import oid,convert,insert_missing,REFERENCES
from .geometry import normalize
ALIASES={'Bouilding':'Building','Settelment':'Settlement','Setlement':'Settlement'}
FIELDS={'_id_instance':'instance','id_instance':'instance','treatment_procedure':'treatment_procedures','courpus':'corpus'}

def json_rows(path):
    # Incremental array reader; a FeatureCollection wrapper uses the same row path.
    with path.open(encoding='utf-8-sig') as f:
        first=f.read(1)
        while first and first.isspace():first=f.read(1)
        if first!='[':
            f.seek(0);data=json.load(f)
            if data.get('type')=='FeatureCollection':
                crs=data.get('crs')
                if crs and crs.get('properties',{}).get('name') not in ('EPSG:4326','urn:ogc:def:crs:OGC:1.3:CRS84'):raise ValueError('GeoJSON must use EPSG:4326/CRS84; unsupported explicit CRS')
                yield from data['features']
            elif isinstance(data,dict):yield data
            return
        decoder=json.JSONDecoder();buffer='';ended=False;expect_value=True;saw_value=False
        while not ended:
            chunk=f.read(65536);buffer+=chunk
            while True:
                buffer=buffer.lstrip()
                if not buffer:break
                if buffer[0]==']':
                    if expect_value and saw_value:raise ValueError('Trailing comma in JSON array')
                    ended=True;buffer=buffer[1:];break
                if not expect_value:
                    if buffer[0]!=',':raise ValueError('Expected JSON comma')
                    buffer=buffer[1:];expect_value=True;continue
                try:item,end=decoder.raw_decode(buffer)
                except json.JSONDecodeError:
                    if not chunk:raise
                    break
                yield item;buffer=buffer[end:];expect_value=False;saw_value=True
            if not chunk and not ended:raise ValueError('Truncated JSON array')
        if buffer.strip() or f.read().strip():raise ValueError('Trailing JSON content')

def sources(path):
    suffix=path.suffix.lower()
    if suffix=='.xlsx':
        book=load_workbook(path,read_only=True,data_only=False,keep_links=False)
        try:
            for sheet in book:
                iterator=sheet.iter_rows(values_only=True);headers=next(iterator,())
                for number,row in enumerate(iterator,2):
                    if any(v not in (None,'') for v in row):
                        data={str(k):v for k,v in zip(headers,row) if k not in (None,'') and v not in (None,'')}
                        extra={str(i+1):v for i,v in enumerate(row) if v not in (None,'') and (i>=len(headers) or headers[i] in (None,''))}
                        if extra:data['_unmapped_cells']=extra
                        yield sheet.title,number,data
        finally:book.close()
    elif suffix in ('.json','.geojson'):
        for number,row in enumerate(json_rows(path),1):yield None,number,row
    elif suffix=='.gpkg':
        from . import gpkg_uploads as files
        with closing(files.connect(path)) as db:
            if db.execute('PRAGMA application_id').fetchone()[0]!=1196444487:raise ValueError('Not a GeoPackage')
            if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('Corrupt GeoPackage')
            for table in files.tables(db):
                for number,row in enumerate(db.execute('SELECT * FROM '+files.quote(table['name'])),1):
                    data=dict(row)
                    if table['geometry']:
                        from .gpkg_import import point
                        data.update(point(data.pop(table['geometry']['column_name']),table['geometry'],db))
                    yield table['name'],number,data
    else:raise ValueError('Supported files: .xlsx .json .geojson .gpkg')

def expand(name,row):
    if name and ALIASES.get(name,name) in records.schemas():return {ALIASES.get(name,name):row}
    if row.get('type')=='Feature':
        props=row.get('properties') or {};out=expand(None,props)
        geo=normalize({'geometry':row.get('geometry')});out['Geodata']={**out.get('Geodata',{}),**geo};return out
    out={ALIASES.get(k,k):dict(v) for k,v in row.items() if ALIASES.get(k,k) in records.schemas() and isinstance(v,dict)}
    for k,v in (row.get('Address_Refs') or {}).items():
        if ALIASES.get(k,k) in records.schemas():out[ALIASES.get(k,k)]=dict(v)
    if not out:
        for k,v in row.items():
            if '.' in k:
                collection,field=k.split('.',1)
                if collection in records.schemas():out.setdefault(collection,{})[field]=v
        if not out:
            aliases={'registered':'Patient.reg_date','started':'Therapy.date_start','event_date':'Instances.date'}
            for key,value in row.items():
                candidates=[n+'.'+key for n,spec in records.schemas().items() if key in spec['properties'] and not key.startswith('_') and key not in ('instance','qgis_revision')]
                target=aliases.get(key) or (candidates[0] if len(candidates)==1 else None)
                if target:
                    collection,field=target.split('.',1);out.setdefault(collection,{})[field]=value
    if not out:return {}
    if 'Instances' in out and ('Geodata' in out or 'Region' in out):
        out.setdefault('Location',{'address':{}});out.setdefault('Foci',{})
    # Adapt the supplied final JSON graph to the model's actual FK directions.
    chain=['Region','Municipality','Settlement','Street','Building','Placement']
    for a,b in zip(chain,chain[1:]):
        if a in out and b in out and out[b].get('_id'):out[a].setdefault(b.lower(),out[b]['_id'])
    if 'Therapy' in out:
        therapy=out['Therapy'];result=therapy.get('result')
        if isinstance(result,dict):
            for source,target in [('Saved','Saved'),('recovery','recovery'),('side_effect','side effect')]:
                if therapy.get(source) is not None:result[target]=therapy[source]
    if 'Location' in out:
        loc=out['Location'];addr=loc.get('address')
        if isinstance(addr,dict):loc['address']={k:v for k,v in addr.items() if k in ('region','geodata')}
        if loc.get('geodata'):loc.setdefault('address',{})['geodata']=loc['geodata']
        if 'Geodata' in out and out['Geodata'].get('_id'):loc.setdefault('address',{})['geodata']=out['Geodata']['_id']
    if 'Foci' in out:
        f=out['Foci']
        if 'Location' in out and out['Location'].get('_id'):f['location']=out['Location']['_id']
        if 'instances' in f:f['id_instance']=f['instances']
    return out

def execute(filename,store,report_path=None,*,apply=True):
    path=Path(filename).resolve(strict=True)
    with path.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
    report_path=Path(report_path or str(path)+'.import-report.jsonl')
    if report_path.resolve()==path:raise ValueError('Report must not replace source')
    summary={'source_sha256':digest,'source_rows':0,'documents':{},'inserted':{},'issues':0,'status':'validating','archive_only_rows':{}}
    namespace='test-dataset-a' if path.suffix.lower()=='.xlsx' else 'external:'+digest
    staging_files.ROOT.mkdir(parents=True,exist_ok=True)
    with report_path.open('w',encoding='utf-8') as report,tempfile.TemporaryDirectory(prefix='auto-stage-',dir=staging_files.ROOT) as tmp,ExitStack() as resources:
        phase='validation'
        def issue(col,row,field,reason,severity='warning'):
            summary['issues']+=1;report.write(json.dumps({'stage':phase,'collection':col,'row':row,'field':field,'reason':reason,'severity':severity},ensure_ascii=False)+'\n')
        db=None;source_rows=sources(path);cursor=None
        try:
            db=resources.enter_context(closing(sqlite3.connect(str(Path(tmp)/'stage.sqlite'))));db.execute('PRAGMA journal_mode=DELETE');db.execute('PRAGMA temp_store=FILE');db.execute('PRAGMA cache_size=-2048');db.execute('CREATE TABLE docs(col TEXT,id TEXT,doc TEXT,PRIMARY KEY(col,id))');db.execute('CREATE TABLE raw(doc TEXT)');db.execute("CREATE INDEX instance_lookup ON docs(col,json_extract(doc,'$.instance.\"$oid\"'))")
            for name,number,raw in source_rows:
                summary['source_rows']+=1
                db.execute('INSERT INTO raw VALUES(?)',(zlib.compress(json_util.dumps({'_id':oid(digest,name or 'json',number),'source':'auto:'+digest,'imported_at':datetime.now(timezone.utc),'sheet':name,'row':number,'raw':raw}).encode('utf-8'),level=1),))
                expanded=expand(name,raw)
                if not expanded:
                    if name and path.suffix.lower()=='.xlsx':
                        summary['archive_only_rows'][name]=summary['archive_only_rows'].get(name,0)+1
                        if summary['archive_only_rows'][name]==1:issue(name,number,None,'Supplementary sheet archived in cases; normalized collection sheets are processed separately; see archive_only_rows for count')
                    else:issue(name,number,None,'Source row retained only in cases: no known collection')
                    continue
                ids={n:oid(namespace,n,d.get('_id',d.get('_id_instance',d.get('instance',d.get('id_instance',str(number)+':'+n))))) for n,d in expanded.items()}
                for col,data in expanded.items():
                    props=records.schemas()[col]['properties'];doc={'_id':ids[col],'_owner_id':'qgis-user'}
                    for key,value in data.items():
                        field=FIELDS.get(key,key)
                        if col!='Instances' and key in ('id_instance','_id_instance'):field=key
                        if col=='Foci' and key=='instances':field='id_instance'
                        if field=='_id' or value is None or value=='':continue
                        if field not in props:issue(col,number,field,'Not in model; original retained in cases');continue
                        try:
                            spec=props[field];types=spec.get('bsonType');types=types if isinstance(types,list) else [types]
                            if 'date' in types and isinstance(value,str) and 'T' in value:value=datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(timezone.utc)
                            if 'array' in types and isinstance(value,str) and not value.lstrip().startswith('['):value=[value]
                            if col=='Therapy' and field=='result':
                                if isinstance(value,str):
                                    issue(col,number,field,'Historical result text retained in cases; not guessed as object');value={}
                                unknown=set(value)-set(spec.get('properties',{}))
                                if unknown:issue(col,number,field,'Nested fields outside model retained in cases: '+','.join(sorted(unknown)))
                                value={k:v for k,v in value.items() if k in spec.get('properties',{}) and v is not None}
                            doc[field]=records.convert(value,spec,col+'.'+field) if col=='Geodata' and field=='geometry' else convert(value,spec,col+'.'+field,namespace)
                        except Exception as exc:issue(col,number,field,str(exc),'error')
                    if col=='Instances':doc.setdefault('instance',ids[col])
                    if col=='Geodata':
                        try:
                            doc=normalize(doc)
                            if not doc.get('geometry'):raise ValueError('Geodata requires a valid Point or coordinate pair')
                            doc['_geometry_valid']=True
                        except Exception as exc:raise ValueError('Invalid Geodata geometry at row '+str(number)) from exc
                    for field in entities.REQUIRED.get(col,[]):
                        if field not in doc and records.LINKS.get(col,{}).get(field,(None,None))[0] not in ids:issue(col,number,field,'Historical required value absent; no substitute created')
                    for field,(target,_) in records.LINKS.get(col,{}).items():
                        if entities.get_path(doc,field) is None and target in ids:entities.set_path(doc,field,ids[target])
                    encoded=json_util.dumps(doc,sort_keys=True)
                    old=db.execute('SELECT doc FROM docs WHERE col=? AND id=?',(col,str(doc['_id']))).fetchone()
                    if old and old[0]!=encoded:
                        previous=json_util.loads(old[0]);ambiguous=set(previous.get('_ambiguous_links',[]))
                        for field in ambiguous:doc.pop(field,None)
                        previous.pop('_ambiguous_links',None)
                        different={k for k in set(previous)|set(doc) if previous.get(k)!=doc.get(k)}
                        links={f for f in records.LINKS.get(col,{}) if '.' not in f}
                        if different<=links:
                            ambiguous|=different
                            for field in ambiguous:doc.pop(field,None)
                            if ambiguous:doc['_ambiguous_links']=sorted(ambiguous)
                            encoded=json_util.dumps(doc,sort_keys=True);db.execute('DELETE FROM docs WHERE col=? AND id=?',(col,str(doc['_id'])))
                            if different:issue(col,number,','.join(sorted(different)),'Ambiguous historical single-valued links omitted; all source relationships retained in cases')
                        else:raise ValueError('Conflicting source ID: '+col+' '+str(doc['_id']))
                    db.execute('INSERT OR IGNORE INTO docs VALUES(?,?,?)',(col,str(doc['_id']),encoded))
            db.commit()
            # Resolve only real source/database targets, never create dummy entities.
            for col,key,encoded in db.execute('SELECT col,id,doc FROM docs'):
                doc=json_util.loads(encoded)
                for field,(target,targetkey) in records.LINKS.get(col,{}).items():
                    value=entities.get_path(doc,field)
                    if value is None:continue
                    exists=db.execute('SELECT 1 FROM docs WHERE col=? AND id=?',(target,str(value))).fetchone()
                    if not exists and targetkey!='_id':
                        exists=db.execute('SELECT 1 FROM docs WHERE col=? AND json_extract(doc,?)=?',(target,'$.'+targetkey+'."$oid"',str(value))).fetchone()
                    if not exists:exists=store.database('processor')[target].find_one({targetkey:value},{'_id':1})
                    if not exists:
                        issue(col,key,field,'Unresolved FK omitted from normalized document; original retained in cases','error')
                        parent=doc
                        for part in field.split('.')[:-1]:parent=parent[part]
                        parent.pop(field.split('.')[-1],None)
                db.execute('UPDATE docs SET doc=? WHERE col=? AND id=?',(json_util.dumps(doc),col,key))
            db.commit();summary['staging_bytes']=(Path(tmp)/'stage.sqlite').stat().st_size;summary['documents']=dict(db.execute('SELECT col,count(*) FROM docs GROUP BY col'))
            if not apply:
                summary['status']='dry-run';summary['archive_rows']=summary['source_rows']
            else:
                phase='write'
                for col in summary['documents']:
                    cursor=db.execute('SELECT doc FROM docs WHERE col=?',(col,));summary['inserted'][col]=0
                    while batch:=cursor.fetchmany(250):summary['inserted'][col]+=insert_missing(store.database('processor')[col],[json_util.loads(x[0]) for x in batch])
                cursor=db.execute('SELECT doc FROM raw');summary['inserted']['cases']=0
                while batch:=cursor.fetchmany(250):summary['inserted']['cases']+=insert_missing(store.database('ingest').cases,[json_util.loads(zlib.decompress(x[0]).decode('utf-8')) for x in batch])
                summary['status']='complete'
        except Exception as exc:
            summary['status']='failed';summary['counts_are_confirmed_only']=True;issue(None,None,None,str(exc),'critical');raise
        finally:
            source_rows.close()
            if cursor is not None:cursor.close()
            if db is not None:db.close()
            report.write(json.dumps({'summary':summary},ensure_ascii=False)+'\n')
    return summary

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('file');p.add_argument('--report');mode=p.add_mutually_exclusive_group();mode.add_argument('--dry-run',action='store_true');mode.add_argument('--apply',action='store_true');a=p.parse_args()
    from ..database.mongodb import MongoDB
    store=MongoDB({**os.environ,"MONGO_OPERATION_TIMEOUT_MS":os.getenv("IMPORT_OPERATION_TIMEOUT_MS","30000")})
    try:
        if a.report:print(json.dumps(execute(a.file,store,a.report,apply=a.apply),ensure_ascii=False))
        else:
            staging_files.ROOT.mkdir(parents=True,exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='auto-report-',dir=staging_files.ROOT) as folder:
                target=Path(folder)/'report.jsonl'
                try:execute(a.file,store,target,apply=a.apply)
                finally:
                    if target.exists():
                        with target.open(encoding='utf-8') as stream:
                            for line in stream:sys.stdout.write(line)
    finally:store.close()
if __name__=='__main__':main()
