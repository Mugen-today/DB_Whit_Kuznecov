"""Bundled historical dataset bootstrap; not an interactive ingestion bypass."""
import hashlib,json,os
from pathlib import Path
from ..database.mongodb import MongoDB
from .seed_excel import execute
def main():
    base=Path(os.getenv('SEED_DATA_DIR','/opt/data'))
    manifest=json.loads((base/'manifest.json').read_text())
    path=base/manifest['filename']
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if digest!=manifest['sha256']:raise ValueError('Bundled Excel checksum mismatch')
    store=MongoDB()
    try:
        cases=store.database('ingest').cases
        marker='bundled-seed:'+digest
        if cases.find_one({'_id':marker}):
            print('Bundled Excel already loaded; existing edits retained')
        else:
            report=execute(str(path),manifest['namespace'],store)
            cases.insert_one({'_id':marker,'source':marker,'report':report})
            print(json.dumps(report,ensure_ascii=False))
        part=manifest['part_b'];part_path=base/part['filename']
        digest_b=hashlib.sha256(part_path.read_bytes()).hexdigest()
        if digest_b!=part['sha256']:raise ValueError('test_B checksum mismatch')
        marker_b='bundled-seed:'+digest_b
        if not cases.find_one({'_id':marker_b}):
            from .seed_b import execute as load_b
            report_b=load_b(part_path,digest_b,store)
            cases.insert_one({'_id':marker_b,'source':marker_b,'report':report_b})
            print(json.dumps(report_b,ensure_ascii=False))
        else:print('Bundled test_B already loaded; edits retained')
    finally:store.close()
if __name__=='__main__':main()
