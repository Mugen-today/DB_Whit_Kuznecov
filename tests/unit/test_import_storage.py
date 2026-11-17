import tempfile,sqlite3,unittest
from pathlib import Path
from unittest.mock import patch
from backend.app.modules import auto_import,gpkg_uploads
from tests.integration.gpkg_fixture import build
from tests.unit.test_seed_b import Store
class StorageTests(unittest.TestCase):
 def test_stage_uses_configured_disk_directory(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);source=root/'input.json';source.write_text('[{"Geodata":{"Longitude":30,"Latitude":60}}]')
   original=tempfile.TemporaryDirectory
   with patch.object(gpkg_uploads,'ROOT',root/'disk'),patch.object(auto_import.tempfile,'TemporaryDirectory',wraps=original) as stage:
    auto_import.execute(source,Store(),root/'report',apply=False)
    self.assertEqual(stage.call_args.kwargs['dir'],root/'disk')
 def test_source_iterator_is_closed_on_validation_failure(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);source=root/'input.json';source.write_text('[]');closed=[]
   def rows(*args):
    try:yield None,1,{'Geodata':{'Longitude':999,'Latitude':60}}
    finally:closed.append(True)
   with patch.object(gpkg_uploads,'ROOT',root/'disk'),patch.object(auto_import,'sources',rows):
    with self.assertRaises(ValueError):auto_import.execute(source,Store(),root/'report')
   self.assertEqual(closed,[True]);self.assertFalse(list((root/'disk').glob('auto-stage-*')))
 def test_gpkg_connection_closed_when_generator_stops_early(self):
  with tempfile.TemporaryDirectory() as folder:
   source=Path(folder)/'a.gpkg';build(source);opened=[];original=gpkg_uploads.connect
   def connect(*args):
    db=original(*args);opened.append(db);return db
   with patch.object(gpkg_uploads,'connect',connect):
    iterator=auto_import.sources(source);next(iterator);iterator.close()
   for db in opened:
    with self.assertRaises(sqlite3.ProgrammingError):db.execute('SELECT 1')
 def test_partial_batch_failure_is_reported_and_replay_finishes(self):
  import json
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);source=root/'a.json';rows=[{'Patient':{'_id':i,'passport':str(i),'age':25,'reg_date':'2026-11-17'}} for i in range(500)];source.write_text(json.dumps(rows));store=Store();original=auto_import.insert_missing;calls=[]
   def insert(collection,docs):
    calls.append(1)
    if len(calls)==2:raise RuntimeError('simulated interruption')
    return original(collection,docs)
   with patch.object(gpkg_uploads,'ROOT',root/'disk'),patch.object(auto_import,'insert_missing',insert):
    with self.assertRaises(RuntimeError):auto_import.execute(source,store,root/'failed')
   report=[json.loads(x) for x in (root/'failed').read_text().splitlines()];self.assertEqual(report[-1]['summary']['inserted']['Patient'],250);self.assertEqual(report[-2]['stage'],'write')
   with patch.object(gpkg_uploads,'ROOT',root/'disk'):auto_import.execute(source,store,root/'retry')
   self.assertEqual(len(store.db['Patient'].rows),500);self.assertEqual(len(store.db.cases.rows),500)
   self.assertEqual(next(iter(store.db.cases.rows.values()))['raw'],rows[0])
