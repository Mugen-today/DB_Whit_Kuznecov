"""Bounded concurrent read load; test backend and test data only."""
import json,time,statistics
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from comprehensive_http import call
requests=96
paths=['/v1/collections/Instances?limit=200','/v1/collections/Geodata?limit=200','/v1/overview?limit=500','/v1/statistics']
def run(i):
    role=('reader','user','guest')[i%3];started=time.perf_counter();data=call('GET',paths[i%len(paths)],role=role)
    assert isinstance(data,dict)
    if role=='guest' and 'records' in data and 'collection' in data:assert data['collection'] not in ('Street','Building','Placement','Social_group')
    return time.perf_counter()-started
started=time.perf_counter()
with ThreadPoolExecutor(max_workers=4) as pool:latencies=list(pool.map(run,range(requests)))
elapsed=time.perf_counter()-started;ordered=sorted(latencies)
result={'requests':requests,'concurrency':4,'failures':0,'elapsed_seconds':elapsed,'requests_per_second':requests/elapsed,'p50_seconds':statistics.median(latencies),'p95_seconds':ordered[int(.95*(len(ordered)-1))]}
(Path(__file__).resolve().parents[1]/'performance/load_results.json').write_text(json.dumps(result,indent=2))
print('PASS concurrent read load '+json.dumps(result),flush=True)
