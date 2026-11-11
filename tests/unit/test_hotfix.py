import json,unittest,sqlite3,tempfile,sys
from pathlib import Path
from bson import Decimal128,Regex
from backend.app.modules import geometry,mongo_console,gpkg_import
from backend.app.modules.qgis_data import ApiError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integration'))
from gpkg_fixture import build,MAPPING
class HotfixTests(unittest.TestCase):
    def test_console_collection_access_comments_and_regex(self):
        for name in ('db.Patient','db["Patient"]','db.getCollection("Patient")'):
            n,op,args,chain=mongo_console.Parser('/* leading */ '+name+'.find({passport:/^ab\\/c/i,age:{$gte:10/2}}).pretty().toArray(); // end').parse()
            self.assertEqual((n,op,chain),('Patient','find',[]));self.assertIsInstance(args[0]['passport'],Regex)
            self.assertEqual(args[0]['passport'].pattern,'^ab/c');self.assertEqual(args[0]['age']['$gte'],5)
    def test_console_rejects_unsupported_statements_and_flags(self):
        for text in ('import os','db.Patient.find({passport:/a/g})','db.Patient.find({}); db.Patient.find({})'):
            with self.assertRaises(ApiError):mongo_console.Parser(text).parse()
    def test_historical_coordinate_bson_and_text(self):
        for x in (Decimal128('30'),{'$numberDecimal':'30'},'30',30):
            g,w=geometry.read_geometry({'Longitude':x,'Latitude':'60'})
            self.assertEqual(g['coordinates'],[30.0,60.0]);self.assertIsNone(w)
    def test_geometry_metadata_crs_and_fallback(self):
        g,w=geometry.read_geometry({'geometry':'broken','Longitude':'30','Latitude':'60'})
        self.assertEqual(g['coordinates'],[30,60]);self.assertIn('Invalid',w)
        g,w=geometry.read_geometry({'geometry':{'type':'Point','coordinates':[30,60],'bbox':[30,60,30,60]}})
        self.assertEqual(g['coordinates'],[30,60]);self.assertIsNone(w)
        g,w=geometry.read_geometry({'geometry':{'type':'Point','coordinates':[3339584.723798207,8399737.889818357],'crs':{'type':'name','properties':{'name':'EPSG:3857'}}}})
        self.assertAlmostEqual(g['coordinates'][0],30,places=7);self.assertAlmostEqual(g['coordinates'][1],60,places=7)
    def test_invalid_geometry_row_retained_and_wkt_key(self):
        features=geometry.features([{'_id':1,'_key':'legacy-key','Longitude':30,'Latitude':60},{'_id':'bad','Longitude':999,'Latitude':60}])
        self.assertEqual(features[0]['id'],'legacy-key');self.assertEqual(features[0]['geometry_wkt'],'POINT (30 60)')
        self.assertEqual(len(features),2);self.assertIsNone(features[1]['geometry']);self.assertIn('geometry_warning',features[1])
    def test_gpkg_all_null_selected_entity_is_not_silently_skipped(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'null.gpkg';build(p)
            db=sqlite3.connect(p);db.execute('UPDATE cases_points SET passport=NULL, age=NULL, registered=NULL');db.commit();db.close()
            info=gpkg_import.upload(p.read_bytes(),'hotfix-unit')
            payload={'upload_id':info['upload_id'],'table':'cases_points','mapping':{k:v for k,v in MAPPING.items() if k.startswith('Patient.')},'use_geometry':True,'mode':'entities'}
            with self.assertRaises(ApiError):list(gpkg_import.build(payload,'hotfix-unit'))
    def test_requirements_merge_business_rules_and_generated_ids(self):
        contract=gpkg_import.requirements()
        self.assertEqual(set(contract['Patient']),{'passport','age','reg_date'})
        self.assertTrue(all('_id' not in v and 'instance' not in v for v in contract.values()))

    def test_empty_optional_numeric_attribute_is_skipped(self):
        for value in (None,'','   '):
            self.assertIsNone(gpkg_import.mapped_value(value,{'bsonType':'double'},'Geodata.Elevation'))
        self.assertEqual(gpkg_import.mapped_value(0,{'bsonType':'double'},'Geodata.Elevation'),0)
    def test_session_reports_backend_version(self):
        import os
        from unittest.mock import patch
        from backend.app.main import create_app
        with patch.dict(os.environ,{'QGIS_USER_TOKEN':'hotfix-session-token','QGIS_IDENTITIES_JSON':'[]'}):
            statuses=[]
            response=create_app(None)({'PATH_INFO':'/v1/session','REQUEST_METHOD':'GET','HTTP_AUTHORIZATION':'Bearer hotfix-session-token'},lambda status,headers:statuses.append(status))
            self.assertEqual(statuses,['200 OK'])
            self.assertEqual(json.loads(b''.join(response))['backend_version'],'0.8.0')
