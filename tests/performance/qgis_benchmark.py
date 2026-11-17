"""Native QGIS layer construction; each version runs in its own process."""
import sys,time,json,resource,argparse
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--project',type=Path,required=True);parser.add_argument('--rows',type=int,default=40000);args=parser.parse_args();sys.path.insert(0,str(args.project.resolve()))
from qgis.core import QgsApplication
from qgis_plugin.layer_records import make_layer
app=QgsApplication([],False);app.initQgis()
rows=[{'_id':str(i),'_key':str(i),'qgis_revision':0,'age':25,'passport':'000'+str(i),'reg_date':'2026-11-14','gender':'example','social_group':'example','note':'x'*100} for i in range(args.rows)]
page={'collection':'Patient','records':rows,'schema':{'properties':{'age':{'bsonType':'int'}}}}
started=time.perf_counter();layer=make_layer(page);elapsed=time.perf_counter()-started
assert layer.isValid() and layer.featureCount()==args.rows
assert sum(f['age'] for f in layer.getFeatures())==args.rows*25
print(json.dumps({'rows':args.rows,'seconds':elapsed,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}),flush=True)
