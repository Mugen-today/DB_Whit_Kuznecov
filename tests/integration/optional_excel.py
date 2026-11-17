"""Explicit XLSX ingestion through the common strict job engine; disposable DB only."""
import tempfile,hashlib
from pathlib import Path
from openpyxl import Workbook
from backend.app.database.mongodb import MongoDB
from backend.app.modules.import_excel import execute
from comprehensive_http import console
store=MongoDB()
try:
 with tempfile.TemporaryDirectory() as td:
    p=Path(td)/'chosen.xlsx';book=Workbook();sheet=book.active
    sheet.append(['Patient.passport','Patient.age','Patient.reg_date','Instances.date','Therapy.date_start','Therapy.diagnosis','Geodata.Longitude','Geodata.Latitude'])
    for i in range(1,1004):sheet.append(['XLSX_'+str(i),None if i==1003 else 25,'2026-11-14','2026-11-14','2026-11-14','["TEST"]',30,60])
    book.save(p);book.close();digest=hashlib.sha256(p.read_bytes()).hexdigest()
    strict=execute(p,store=store,apply=True);assert strict['status']=='invalid' and strict['successful_rows']==0
    assert console('db.Patient.countDocuments({passport:/^XLSX_/})')['value']==0
    partial=execute(p,store=store,apply=True,error_policy='partial');assert (partial['status'],partial['successful_rows'],partial['documents_created_by_job'])==('complete_with_errors',1002,6012),partial
    repeat=execute(p,store=store,apply=True,error_policy='partial');assert repeat['documents_created_by_job']==0 and repeat['documents_reused']==6012
    assert console('db.Patient.countDocuments({passport:/^XLSX_/})')['value']==1002
    assert hashlib.sha256(p.read_bytes()).hexdigest()==digest
    print('PASS optional XLSX: 1003 rows, strict zero writes; partial 1002 linked bundles / 6012 documents, repeat without duplicates; original unchanged',flush=True)
finally:store.close()
