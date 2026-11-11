"""Read-only XLSX staging, immutable source archive, insert-only normalized import."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

from bson import ObjectId, Regex, json_util
from pymongo.errors import BulkWriteError
from openpyxl import load_workbook

ALIASES = {'Instances': {'id_instance':'instance'}, 'Foci': {'instances':'id_instance'},
           'Therapy': {'treatment_procedure':'treatment_procedures'}}
REFERENCES = {'Instances.reception':'Reception', 'Instances.patient':'Patient', 'Instances.therapy':'Therapy',
 'Patient.gender':'Gender','Patient.social_group':'Social_group','Therapy.patient':'Patient',
 'Therapy.severity':'Severity','Therapy.influence':'Influence','Region.municipality':'Municipality',
 'Municipality.settlement':'Settlement','Settlement.street':'Street','Street.building':'Building',
 'Building.placement':'Placement','Foci.location':'Location','Foci.id_instance':'Instances',
 'Location.address.region':'Region','Location.address.geodata':'Geodata'}

def oid(namespace, collection, value):
    if isinstance(value, ObjectId): return value
    text = str(value).strip()
    if ObjectId.is_valid(text): return ObjectId(text)
    try:
        number = float(text)
        if number.is_integer(): text = str(int(number))
    except ValueError: pass
    return ObjectId(hashlib.sha256(f'{namespace}:{collection}:{text}'.encode()).hexdigest()[:24])

def convert(value, spec, path, namespace):
    kind = spec.get('bsonType'); kind = kind[0] if isinstance(kind,list) else kind
    if kind == 'objectId': return oid(namespace, REFERENCES.get(path, path.split('.')[0]), value)
    if kind == 'string': return str(value)
    if kind == 'int':
        number = float(value)
        if not math.isfinite(number) or not number.is_integer() or not -2**31 <= number < 2**31: raise ValueError('expected int32')
        return int(number)
    if kind == 'double':
        number = float(value)
        if not math.isfinite(number): raise ValueError('nonfinite number')
        if path.endswith('Longitude') and not -180 <= number <= 180: raise ValueError('longitude out of range')
        if path.endswith('Latitude') and not -90 <= number <= 90: raise ValueError('latitude out of range')
        return number
    if kind == 'date':
        if isinstance(value, datetime): return value.replace(tzinfo=timezone.utc)
        for fmt in ('%d.%m.%Y %H:%M','%d.%m.%Y','%Y-%m-%d','%Y-%m-%dT%H:%M:%S'):
            try: return datetime.strptime(str(value),fmt).replace(tzinfo=timezone.utc)
            except ValueError: pass
        raise ValueError('unrecognized date')
    if kind == 'bool':
        if value in (True,1,'1','true','True','да'): return True
        if value in (False,0,'0','false','False','нет'): return False
        raise ValueError('expected boolean')
    if kind == 'regex': return Regex(str(value))
    if kind == 'array':
        parsed = json.loads(value) if isinstance(value,str) else value
        if not isinstance(parsed,list): raise ValueError('expected JSON array')
        return parsed
    if kind == 'object':
        if isinstance(value,str):
            if path == 'Location.address' and ';' in value:
                parts=value.split(';')
                if len(parts)!=2: raise ValueError('address expects region;geodata')
                value=dict(zip(('region','geodata'),parts))
            elif path == 'Patient.medical_record' and ';' in value:
                parts=value.split(';')
                if len(parts)!=2: raise ValueError('medical record expects chronic_diseases;vaccine')
                value=dict(zip(('chronic_diseases','vaccine'),parts))
            else: value=json.loads(value)
        if not isinstance(value,dict): raise ValueError('expected JSON object')
        if set(value)-set(spec['properties']): raise ValueError('unknown nested field')
        return {k:convert(v,spec['properties'][k],path+'.'+k,namespace) for k,v in value.items() if v not in (None,'')}
    raise ValueError('unsupported type')

def insert_missing(collection, documents):
    """Never update existing documents, including source archive and user edits."""
    if not documents: return 0
    existing={d['_id'] for d in collection.find({'_id':{'$in':[d['_id'] for d in documents]}},{'_id':1})}
    pending=[d for d in documents if d['_id'] not in existing]
    if not pending: return 0
    try:
        return len(collection.insert_many(pending,ordered=False).inserted_ids)
    except BulkWriteError as exc:
        if exc.details.get('writeConcernErrors') or any(e['code']!=11000 for e in exc.details.get('writeErrors',[])): raise
        return exc.details.get('nInserted',0)

def execute(filename, namespace, store=None):
    """Plan without DB; apply archives rows first, then validated documents, batches of 250."""
    if store is not None:
        raise ValueError("Legacy partial Excel import disabled. Plan remains available; submit complete records through /v1/records.")
    schema_path=Path(os.getenv('STORAGE_SCHEMA_PATH',Path(__file__).resolve().parents[3]/'storage/schema/model.json'))
    model=json.loads(schema_path.read_text())['collections']
    specs={k.split('.',1)[1]:v['jsonSchema'] for k,v in model.items()}
    with open(filename,'rb') as source: digest=hashlib.file_digest(source,'sha256').hexdigest()
    report={'sha256':digest,'namespace':namespace,'mode':'apply' if store else 'plan','rows':{},'documents':{},'issues':Counter(),'examples':[], 'inserted':{}}
    def issue(sheet,row,detail):
        report['issues'][detail]+=1
        if len(report['examples'])<60: report['examples'].append({'sheet':sheet,'row':row,'issue':detail})
    with tempfile.TemporaryDirectory() as tmp:
        stage=sqlite3.connect(str(Path(tmp)/'stage.db'))
        stage.execute('create table docs (col text, id text, doc text, primary key(col,id))')
        stage.execute('create table raw (id text primary key, doc text)')
        book=load_workbook(filename,read_only=True,data_only=False,keep_links=False)
        cached=load_workbook(filename,read_only=True,data_only=True,keep_links=False)
        try:
            for sheet in book:
                rows=sheet.iter_rows(values_only=True); headers=next(rows,())
                # Ignore formatting-only trailing columns, but never unnamed data.
                width=max((i+1 for i,h in enumerate(headers) if h not in (None,'')),default=0)
                report['rows'][sheet.title]=0
                cached_rows=cached[sheet.title].iter_rows(min_row=2,values_only=True)
                for rowno,(row, cached_row) in enumerate(zip(rows,cached_rows),2):
                    if not any(v not in (None,'') for v in row): continue
                    report['rows'][sheet.title]+=1
                    raw={'_id':oid(digest,sheet.title,rowno),'source':'xlsx:'+digest,'imported_at':datetime.now(timezone.utc),
                         'sheet':sheet.title,'row':rowno,'headers':list(headers[:width]),'values':list(row[:max(width,max((i+1 for i,v in enumerate(row) if v not in (None,'')),default=0))])}
                    stage.execute('insert into raw values (?,?)',(str(raw['_id']),json_util.dumps(raw)))
                    if sheet.title not in specs: continue
                    if any(isinstance(v,str) and v.startswith('=') for v in row):
                        issue(sheet.title,rowno,'formula: using Excel cached value; source formula archived')
                    row=cached_row
                    values={ALIASES.get(sheet.title,{}).get(str(h),str(h)):v for h,v in zip(headers,row) if h not in (None,'') and v not in (None,'')}
                    key='instance' if sheet.title=='Instances' else '_id'
                    if key not in values:
                        issue(sheet.title,rowno,'missing identifier; raw only'); continue
                    doc={'_id':oid(namespace,sheet.title,values[key]),'_owner_id':'qgis-user'}
                    for field,value in values.items():
                        if field=='_id': continue
                        if field not in specs[sheet.title]['properties']:
                            issue(sheet.title,rowno,'unknown field '+field); continue
                        try: doc[field]=convert(value,specs[sheet.title]['properties'][field],sheet.title+'.'+field,namespace)
                        except (ValueError,TypeError,OverflowError): issue(sheet.title,rowno,'invalid field '+field)
                    if any(k not in doc for k in specs[sheet.title].get('required',[])):
                        issue(sheet.title,rowno,'missing required value; raw only'); continue
                    previous=stage.execute('select doc from docs where col=? and id=?',(sheet.title,str(doc['_id']))).fetchone()
                    if previous:
                        old=json_util.loads(previous[0]); conflicts=[k for k in set(old)|set(doc) if old.get(k)!=doc.get(k)]
                        if sheet.title=='Region' and all(k=='municipality' for k in conflicts):
                            old.pop('municipality',None); old['_ambiguous_municipality']=True
                            doc=old; issue(sheet.title,rowno,'ambiguous Region.municipality omitted')
                        elif sheet.title=='Region' and old.get('_ambiguous_municipality') and old.get('name')==doc.get('name'):
                            doc=old; issue(sheet.title,rowno,'ambiguous Region.municipality omitted')
                        elif conflicts: raise ValueError(f'Conflicting identifier at {sheet.title}:{rowno}; no database writes performed')
                    stage.execute('insert or replace into docs values (?,?,?)',(sheet.title,str(doc['_id']),json_util.dumps(doc)))
                stage.commit()
                print(f"Staged {sheet.title}: {report['rows'][sheet.title]} rows", file=sys.stderr, flush=True)
        finally:
            book.close()
            cached.close()
        # Remove dangling references, while retaining exact cells in cases.
        for col,identifier,payload in stage.execute('select col,id,doc from docs').fetchall():
            doc=json_util.loads(payload)
            for path,target in REFERENCES.items():
                if not path.startswith(col+'.'): continue
                parts=path.split('.')[1:]; parent=doc
                for part in parts[:-1]: parent=parent.get(part,{})
                value=parent.get(parts[-1])
                if value is not None and not stage.execute('select 1 from docs where col=? and id=?',(target,str(value))).fetchone():
                    parent.pop(parts[-1]); issue(col,identifier,'unresolved '+path)
            stage.execute('update docs set doc=? where col=? and id=?',(json_util.dumps(doc),col,identifier))
        stage.commit()
        report['documents']=dict(stage.execute('select col,count(*) from docs group by col'))
        if store:
            print('Writing immutable source rows to cases...', file=sys.stderr, flush=True)
            cursor=stage.execute('select doc from raw')
            inserted=0
            while batch:=cursor.fetchmany(250): inserted+=insert_missing(store.database('ingest').cases,[json_util.loads(r[0]) for r in batch])
            report['inserted']['cases']=inserted
            for col in report['documents']:
                cursor=stage.execute('select doc from docs where col=?',(col,)); inserted=0
                while batch:=cursor.fetchmany(250): inserted+=insert_missing(store.database('processor')[col],[json_util.loads(r[0]) for r in batch])
                report['inserted'][col]=inserted
                print(f'Inserted {col}: {inserted}', file=sys.stderr, flush=True)
        stage.close()
    report['issues']=dict(report['issues'])
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file'); parser.add_argument('--namespace',required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args(); store=None
    try:
        if args.apply:
            from ..database.mongodb import MongoDB
            store=MongoDB()
        print(json.dumps(execute(args.file,args.namespace,store),ensure_ascii=False,indent=2))
    finally:
        if store: store.close()
if __name__=='__main__': main()
