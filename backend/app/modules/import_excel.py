"""Explicit XLSX import. Flat records share GPKG validation, jobs and receipts."""
import argparse,hashlib,json,os,sqlite3,sys,tempfile
from contextlib import closing
from datetime import date,datetime
from pathlib import Path
from openpyxl import load_workbook
from .seed_excel import oid,convert  # compatible conversion API; one implementation
from . import gpkg_uploads as files,gpkg_jobs as jobs
from .gpkg_errors import fail,classify

def stage(filename,owner,sheet=None):
    source=Path(filename).resolve(strict=True)
    if source.suffix.lower()!='.xlsx':raise ValueError('Select an .xlsx file')
    with source.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    book=load_workbook(source,read_only=True,data_only=False,keep_links=False)
    files.ROOT.mkdir(mode=0o700,parents=True,exist_ok=True)
    try:
        selected=book[sheet] if sheet else book.worksheets[0]
        rows=selected.iter_rows(values_only=True);headers=list(next(rows,()))
        while headers and headers[-1] is None:headers.pop()
        if not headers or any(not isinstance(h,str) or not h.strip() for h in headers) or len(set(headers))!=len(headers):
            fail('mapping','Excel headers must be unique Collection.field names')
        with tempfile.TemporaryDirectory(dir=files.ROOT) as folder:
            target=Path(folder)/'source.gpkg'
            with closing(sqlite3.connect(target)) as db:
                db.execute('PRAGMA application_id=1196444487')
                db.execute('CREATE TABLE gpkg_contents(table_name TEXT PRIMARY KEY,data_type TEXT)')
                table=selected.title;columns=['c'+str(i) for i in range(len(headers))]
                db.execute('INSERT INTO gpkg_contents VALUES(?,?)',(table,'attributes'))
                db.execute('CREATE TABLE '+files.quote(table)+' (_source_row INTEGER PRIMARY KEY,'+','.join(files.quote(c) for c in columns)+')')
                insert='INSERT INTO '+files.quote(table)+' VALUES('+','.join('?' for _ in range(len(headers)+1))+')'
                for number,row in enumerate(rows,2):
                    if not any(v is not None for v in row):continue
                    if any(v is not None for v in row[len(headers):]):fail('structure','Excel row has values without headers',code='unnamed_column')
                    values=[]
                    for value in row[:len(headers)]:
                        if isinstance(value,str) and value.startswith('='):fail('structure','Excel formulas are not supported; supply explicit values',code='formula')
                        values.append(value.isoformat() if isinstance(value,(date,datetime)) else value)
                    values += [None]*(len(headers)-len(values))
                    db.execute(insert,[number,*values])
                db.commit()
            info=files.begin({'size':target.stat().st_size,'filename':source.name},owner)
            os.replace(target,Path(str(files.base(info['upload_id'],owner))+'.part'))
            info=files.finish(info['upload_id'],owner)
            meta=files.load(info['upload_id'],owner);meta['sha256']='xlsx:'+digest
            meta['source_sha256']=digest;files.atomic(files.manifest(info['upload_id'],owner),meta)
            return {'upload_id':info['upload_id'],'table':table,'mapping':dict(zip(headers,columns)),'use_geometry':False}
    finally:book.close()

def execute(filename,namespace=None,store=None,*,owner='qgis-user',role='user',sheet=None,apply=False,error_policy='strict',mode='bundle'):
    if store is None:raise ValueError('A database connection is required to validate foreign keys')
    payload=stage(filename,owner,sheet);payload.update(error_policy=error_policy,mode=mode)
    state=jobs.start(store,role,owner,payload)
    while state['status']=='validating':state=jobs.validate(store,role,owner,state['job_id'])
    while apply and state['status'] in ('ready','importing'):state=jobs.apply(store,role,owner,state['job_id'])
    return state

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file');parser.add_argument('--sheet');parser.add_argument('--namespace',default='test-dataset-a')
    parser.add_argument('--format',choices=('records','collections'),default='records')
    parser.add_argument('--apply',action='store_true');parser.add_argument('--historical',action='store_true')
    parser.add_argument('--mode',choices=('bundle','entities'),default='bundle')
    parser.add_argument('--error-policy',choices=('strict','partial'),default='strict')
    args=parser.parse_args()
    if args.format=='collections':
        if args.apply and not args.historical:parser.error('Historical collection-sheet apply requires --historical; use records for strict validated import')
        from .seed_excel import execute as historical
        store=None
        try:
            if args.apply:
                from ..database.mongodb import MongoDB
                store=MongoDB()
            print(json.dumps(historical(args.file,args.namespace,store),ensure_ascii=False))
        finally:
            if store:store.close()
        return
    from ..database.mongodb import MongoDB
    store=MongoDB()
    try:
        state=execute(args.file,store=store,sheet=args.sheet,apply=args.apply,error_policy=args.error_policy,mode=args.mode)
        print(json.dumps({'summary':state},ensure_ascii=False));after=0
        while True:
            page=jobs.report('user','qgis-user',state['job_id'],after)
            for diagnostic in page['issues']:print(json.dumps(diagnostic,ensure_ascii=False))
            if page['next'] is None:break
            after=page['next']
        if state['status'] in ('invalid','failed','blocked'):raise SystemExit(2)
    except Exception as exc:
        print(json.dumps({'issue':classify(exc,'structure')},ensure_ascii=False));raise SystemExit(2) from None
    finally:store.close()

if __name__=='__main__':main()
