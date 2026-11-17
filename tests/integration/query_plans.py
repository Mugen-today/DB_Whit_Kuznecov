"""Read-only index/execution checks against an isolated, populated test DB."""
import json
from pathlib import Path
from backend.app.database.mongodb import MongoDB

def check():
    store=MongoDB();db=store.database('user')
    try:
        required={'cases':[('_owner_id',1),('_id',1)],'Foci':[('_owner_id',1),('id_instance',1)],'Instances':[('_owner_id',1),('date',1)]}
        for name,key in required.items():assert any(list(i['key'].items())==key for i in store.database('reader')[name].list_indexes()),name
        tail=list(db.Geodata.find({'_owner_id':'qgis-user'},{'_id':1}).sort('_id',-1).limit(101));assert len(tail)==101
        result=db.command('explain',{'find':'Geodata','filter':{'_owner_id':'qgis-user','$expr':{'$gt':['$_id',{'$literal':tail[-1]['_id']}] }},'sort':{'_id':1},'limit':100,'projection':{'_id':1}},verbosity='executionStats')
        stats=result['executionStats'];assert stats['nReturned']==100 and stats['totalDocsExamined']<=200,stats
        summary={k:stats[k] for k in ('nReturned','totalDocsExamined','totalKeysExamined')}
        summary['winningPlan']=result['queryPlanner']['winningPlan']
        (Path(__file__).resolve().parents[1]/'performance/query_plans.json').write_text(json.dumps(summary,indent=2,default=str))
        print('PASS pagination executionStats and additive indexes: '+json.dumps({k:stats[k] for k in ('nReturned','totalDocsExamined','totalKeysExamined')}),flush=True)
    finally:store.close()
if __name__=='__main__':check()
