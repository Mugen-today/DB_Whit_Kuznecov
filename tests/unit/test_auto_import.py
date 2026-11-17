import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from backend.app.modules.auto_import import execute
from tests.unit.test_seed_b import Store
from tests.integration.gpkg_fixture import build
class AutoTests(unittest.TestCase):
 def test_json_geojson_and_gpkg_without_mapping(self):
  for extension in ('.json','.geojson','.gpkg'):
   with tempfile.TemporaryDirectory() as folder:
    p=Path(folder)/('source'+extension)
    row={'Patient':{'_id':'012345678901234567890123','passport':'000123','age':25,'reg_date':'2026-11-17T00:00:00Z'},'Geodata':{'Longitude':30,'Latitude':60}}
    if extension=='.gpkg':build(p)
    else:p.write_text(json.dumps([row] if extension=='.json' else {'type':'FeatureCollection','features':[{'type':'Feature','properties':row,'geometry':{'type':'Point','coordinates':[30,60]}}]}))
    original=p.read_bytes();store=Store()
    # This fake resolves only source-staged links; fixture contains none external.
    report=execute(p,store,Path(folder)/'report');self.assertEqual(report['status'],'complete');self.assertIn('Geodata',report['documents']);self.assertIn('Patient',report['documents']);self.assertEqual(original,p.read_bytes());self.assertNotIn('unsupported type',(Path(folder)/'report').read_text())
    again=execute(p,store,Path(folder)/'again');self.assertTrue(all(n==0 for n in again['inserted'].values()))
 def test_ambiguous_source_links_are_reported_and_archived(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder)/'data.json';p.write_text(json.dumps([{'Street':{'_id':'012345678901234567890123','name':'Same','building':'012345678901234567890124'}},{'Street':{'_id':'012345678901234567890123','name':'Same','building':'012345678901234567890125'}}]));store=Store();report=execute(p,store,Path(folder)/'report')
   street=next(iter(store.db['Street'].rows.values()));self.assertNotIn('building',street);self.assertEqual(len(store.db.cases.rows),2);self.assertGreater(report['issues'],0)
 def test_excel_instance_alias_preserves_primary_and_foreign_key(self):
  from openpyxl import Workbook
  from backend.app.modules.seed_excel import oid
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder)/'a.xlsx';b=Workbook();s=b.active;s.title='Instances';s.append(['id_instance','date']);s.append([1,'2026-11-17']);s=b.create_sheet('Foci');s.append(['_id','instances']);s.append([1,1]);b.save(p);b.close();store=Store();execute(p,store,Path(folder)/'report')
   instance=next(iter(store.db['Instances'].rows.values()));focus=next(iter(store.db['Foci'].rows.values()))
   self.assertEqual(instance['_id'],oid('test-dataset-a','Instances',1));self.assertEqual(instance['_id'],instance['instance']);self.assertEqual(focus['id_instance'],instance['instance'])
 def test_canonical_foci_reference_is_not_renamed(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder)/'data.json';key='012345678901234567890123';p.write_text(json.dumps([{'Instances':{'_id_instance':key,'date':'2026-11-17'},'Foci':{'_id':'012345678901234567890124','id_instance':key}}]));store=Store();execute(p,store,Path(folder)/'report')
   self.assertEqual(next(iter(store.db['Foci'].rows.values()))['id_instance'],next(iter(store.db['Instances'].rows.values()))['instance'])
