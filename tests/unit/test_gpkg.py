import tempfile,unittest,sys,uuid
from pathlib import Path
from backend.app.modules import gpkg_import
from backend.app.modules.qgis_data import ApiError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integration'))
from gpkg_fixture import build,MAPPING
class GpkgTests(unittest.TestCase):
    def fixture(self,invalid=False):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        p=Path(tmp.name)/'input.gpkg';build(p,invalid)
        info=gpkg_import.upload(p.read_bytes(),'test-owner')
        return {'upload_id':info['upload_id'],'table':'cases_points','mapping':MAPPING,'use_geometry':True}
    def test_transform_mapping_and_stable_ids(self):
        p=self.fixture();data=list(gpkg_import.build(p,'test-owner'))
        self.assertEqual(len(data),2)
        self.assertAlmostEqual(data[0]['entities']['Geodata']['Longitude'],30,places=7)
        self.assertAlmostEqual(data[0]['entities']['Geodata']['Latitude'],60,places=7)
        self.assertEqual(data,list(gpkg_import.build(p,'test-owner')))
        changed={**p,'mapping':{**MAPPING,'Therapy.diagnosis':'passport'}}
        self.assertEqual(data[0]['request_id'],list(gpkg_import.build(changed,'test-owner'))[0]['request_id'])
        self.assertIn('Patient.medical_record.vaccine',gpkg_import.target_fields())
    def test_missing_required_rejects_whole_table(self):
        p=self.fixture(True)
        with self.assertRaises(ApiError):list(gpkg_import.build(p,'test-owner'))
    def test_upload_ownership_and_identifier(self):
        p=self.fixture()
        with self.assertRaises(ApiError):list(gpkg_import.build(p,'another-owner'))
        p['table']='cases_points"; DROP TABLE cases_points;--'
        with self.assertRaises(ApiError):list(gpkg_import.build(p,'test-owner'))
    def test_invalid_file(self):
        with self.assertRaises(ApiError):gpkg_import.upload(b'not a geopackage','owner')
    def modified(self,sql):
        import sqlite3
        payload=self.fixture();path=gpkg_import.path_for(payload['upload_id'],'test-owner')
        db=sqlite3.connect(path);db.execute(sql);db.commit();db.close()
        return payload
    def test_crs_header_must_match_metadata(self):
        p=self.modified('UPDATE gpkg_geometry_columns SET srs_id=4326')
        with self.assertRaises(ApiError):list(gpkg_import.build(p,'test-owner'))
    def test_invalid_numeric_field_rejected(self):
        p=self.modified("UPDATE cases_points SET age='invalid integer'")
        with self.assertRaises(ApiError):list(gpkg_import.build(p,'test-owner'))
    def test_mapped_foreign_key_type_rejected(self):
        p=self.fixture();p.update(use_geometry=False,mapping={'Therapy.patient':'passport','Therapy.date_start':'started','Therapy.diagnosis':'diagnosis'})
        with self.assertRaises(ApiError):list(gpkg_import.build(p,'test-owner'))
