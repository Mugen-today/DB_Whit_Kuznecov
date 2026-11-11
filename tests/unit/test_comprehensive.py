import json,unittest,os
from unittest.mock import patch
from bson import ObjectId,Decimal128,Binary
from backend.app.modules import mongo_console,records,entities
from backend.app.auth.principals import identity
from backend.app.modules.qgis_data import ApiError
class ComprehensiveTests(unittest.TestCase):
    def test_mongo_syntax_and_constructors(self):
        name,op,args,chain=mongo_console.Parser('db.Patient.find({_id:ObjectId("012345678901234567890123"),age:{$gte:-1}}).sort({age:-1}).limit(0)').parse()
        self.assertEqual(name,'Patient');self.assertIsInstance(args[0]['_id'],ObjectId);self.assertEqual(chain[-1],('limit',[0]))
        _,_,args,_=mongo_console.Parser('db.Instances.find({date:{$gte:new Date(Date.now()-30*24*60*60*1000)}})').parse()
        self.assertTrue(hasattr(args[0]['date']['$gte'],'year'))
    def test_reader_pipeline_security_and_lookup_scope(self):
        with self.assertRaises(ApiError):mongo_console.pipeline('Patient',[{'$facet':{'x':[{'$merge':'Patient'}]}}],'user','alice')
        with self.assertRaises(ApiError):mongo_console.pipeline('Patient',[{'$lookup':{'from':'Social_group','as':'s','pipeline':[]}}],'guest','g')
        p=mongo_console.pipeline('Patient',[{'$lookup':{'from':'Gender','localField':'gender','foreignField':'_id','as':'g'}}],'user','alice')
        self.assertEqual(p[0],{'$match':{'_owner_id':'alice'}})
        self.assertEqual(p[2]['$lookup']['pipeline'][0],{'$match':{'_owner_id':'alice'}})
    def test_bson_and_legacy_identifiers(self):
        for identifier in (ObjectId(),1,'legacy',{'region':1,'local':2}):
            self.assertEqual(records.id_for_key(records.key_for_id(identifier)),identifier)
        d=records.public({'_id':ObjectId(),'value':Decimal128('12.34'),'blob':Binary(b'abc'),'_owner_id':'private'})
        json.dumps(d)
        self.assertEqual(d['value'],{'$numberDecimal':'12.34'});self.assertNotIn('_owner_id',d)
    def test_partial_entity_required_fields(self):
        self.assertEqual(entities.typed('Patient',{'age':41})['age'],41)
        with self.assertRaises(ApiError):entities.typed('Patient',{'age':41},True)
        d=entities.typed('Geodata',{'Longitude':0,'Latitude':0},True)
        self.assertEqual(d['geometry']['coordinates'],[0,0])
    def test_bound_username_token(self):
        with patch.dict(os.environ,{'QGIS_USER_TOKEN':'user-secret','QGIS_GUEST_TOKEN':'guest-secret','DASHBOARD_TOKEN':'reader-secret','QGIS_ADMIN_TOKEN':'admin-secret','QGIS_IDENTITIES_JSON':'[]'}):
            self.assertEqual(identity('Bearer user-secret','qgis-user'),('user','qgis-user'))
            self.assertEqual(identity('Bearer reader-secret','analyst')[0],'reader')
            with self.assertRaises(ApiError):identity('Bearer user-secret','admin')

    def test_invalid_principal_configuration(self):
        with patch.dict(os.environ,{'QGIS_IDENTITIES_JSON':'{}'}):
            with self.assertRaises(ApiError):identity('Bearer anything')
        with patch.dict(os.environ,{'QGIS_IDENTITIES_JSON':'[{"username":"alice","token":"separate-secret","role":"user","owner":"alice"}]'}):
            self.assertEqual(identity('Bearer separate-secret','alice'),('user','alice'))

    def test_point_geometry_cannot_be_removed(self):
        from unittest.mock import Mock
        oid=ObjectId();collection=Mock();collection.find_one.return_value={'_id':oid,'Longitude':30,'Latitude':60,'geometry':{'type':'Point','coordinates':[30,60]}}
        with self.assertRaises(ApiError):
            entities.patch({'Geodata':collection},'user','qgis-user','Geodata',str(oid),{'revision':0,'changes':{'geometry':None}})
        collection.find_one_and_update.assert_not_called()
