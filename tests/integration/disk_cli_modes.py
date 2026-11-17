"""Disposable MongoDB only: all four file modes, repeats and closed GPKG files."""
import os,sys,json,subprocess,tempfile
from pathlib import Path
from backend.app.database.mongodb import MongoDB
from backend.app.modules import records
from gpkg_fixture import build
import import_cli_modes  # real XLSX/JSON CLI modes on the same disposable DB
root=Path(__file__).resolve().parents[2];store=MongoDB();db=store.database('reader')
def counts():return {n:db[n].count_documents({}) for n in [*records.schemas(),'cases']}
try:
 with tempfile.TemporaryDirectory() as folder:
  folder=Path(folder);geo=folder/'source.geojson';geo.write_text(json.dumps({'type':'FeatureCollection','features':[{'type':'Feature','geometry':{'type':'Point','coordinates':[30,60]},'properties':{'Patient':{'passport':'DISK_GEOJSON','age':25,'reg_date':'2026-11-17'}}}]}));gpkg=folder/'source.gpkg';build(gpkg)
  for source in (geo,gpkg):
   before=counts();report=folder/'report.jsonl'
   def run(mode):
    subprocess.run([sys.executable,'-m','app.modules.auto_import',str(source),mode,'--report',str(report)],cwd=root/'backend',env=os.environ,check=True)
    return json.loads(report.read_text().splitlines()[-1])['summary']
   state=run('--dry-run');assert counts()==before and state['status']=='dry-run'
   state=run('--apply');assert state['inserted']['Patient']>0;after=counts();assert after['Patient']>before['Patient'] and after['Geodata']>before['Geodata']
   state=run('--apply');assert counts()==after and all(n==0 for n in state['inserted'].values())
   moved=source.with_name('renamed'+source.suffix);source.rename(moved);moved.unlink()
   print('PASS actual CLI '+source.suffix+' dry-run/apply/repeat and rename/delete after close',flush=True)
  assert db.Geodata.count_documents({})==db.Geodata.count_documents({'geometry.type':'Point','geometry.coordinates.1':{'$exists':True}})
  for collection,field,target,key in [('Foci','id_instance','Instances','instance'),('Foci','location','Location','_id'),('Therapy','patient','Patient','_id')]:
   bad=list(db[collection].aggregate([{'$match':{field:{'$exists':True}}},{'$lookup':{'from':target,'localField':field,'foreignField':key,'as':'target'}},{'$match':{'target':{'$size':0}}},{'$limit':1}]))
   assert not bad,(collection,field)
  print('PASS all synthetic Geodata have Point geometry and core links resolve',flush=True)
finally:store.close()
