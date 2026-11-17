import unittest
from backend.app.modules.query_api import parse,execute
from backend.app.modules.qgis_data import ApiError
class QueryTests(unittest.TestCase):
    def test_xml_typed_range(self):
        p=parse('<gisQuery><collection>Patient</collection><limit>20</limit><filters><condition field="age" operator="gte" type="int">30</condition></filters></gisQuery>','application/xml')
        self.assertEqual(p['filter'],{'age':{'$gte':30}});self.assertEqual(p['limit'],20)
    def test_xml_entities_and_malformed(self):
        for xml in ('<!DOCTYPE a><a/>','<bad'):
            with self.assertRaises(ApiError):parse(xml,'application/xml')
    def test_role_not_taken_from_payload(self):
        with self.assertRaises(ApiError):execute(None,'guest','qgis-guest',{'collection':'Street','role':'reader'})
    def test_operator_injection(self):
        with self.assertRaises(ApiError):execute(None,'user','qgis-user',{'collection':'Patient','filter':{'age':{'$where':'evil()'}}})
