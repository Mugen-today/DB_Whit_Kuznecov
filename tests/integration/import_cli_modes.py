"""Real backend CLI against a disposable MongoDB only; synthetic external files."""
import os,sys,tempfile,json,subprocess
from pathlib import Path
from openpyxl import Workbook
from backend.app.database.mongodb import MongoDB
from backend.app.modules import records
root=Path(__file__).resolve().parents[2];store=MongoDB();db=store.database('reader')
def counts():return {n:db[n].count_documents({}) for n in [*records.schemas(),'cases']}
try:
 with tempfile.TemporaryDirectory() as td:
  folder=Path(td);xlsx=folder/'all sheets.xlsx';b=Workbook();s=b.active;s.title='Patient';s.append(['_id','passport','age','reg_date']);s.append([920001,'CLI_XLSX',25,'2026-11-17']);s=b.create_sheet('Geodata');s.append(['_id','Longitude','Latitude']);s.append([920002,30,60]);b.save(xlsx);b.close()
  js=folder/'testB.json';js.write_text(json.dumps([{'Patient':{'_id':'012345678901234567899991','passport':'CLI_JSON','age':25,'reg_date':'2026-11-17T00:00:00Z'},'Address_Refs':{'Geodata':{'_id':'012345678901234567899992','Longitude':31,'Latitude':61}}}]))
  for source in (xlsx,js):
   before=counts()
   for mode in ('--dry-run','--apply','--apply'):
    report=folder/'report.jsonl';subprocess.run([sys.executable,'-m','app.modules.auto_import',str(source),mode,'--report',str(report)],cwd=root/'backend',env=os.environ,check=True)
    summary=json.loads(report.read_text().splitlines()[-1])['summary']
    if mode=='--dry-run':assert counts()==before and summary['status']=='dry-run'
    elif before==counts():assert all(n==0 for n in summary['inserted'].values())
    else:before=counts();assert summary['inserted']['Patient']==1
   print('PASS real CLI dry-run/apply/repeat, automatic '+source.suffix,flush=True)
finally:store.close()
