"""Conversion tests require backend/requirements.txt; no database is used."""
import importlib.util
import unittest

available=all(importlib.util.find_spec(name) for name in ('bson','pymongo','openpyxl'))

@unittest.skipUnless(available,'Install backend requirements to test Excel conversion')
class ExcelTests(unittest.TestCase):
    def test_ids_preserve_references(self):
        from backend.app.modules.import_excel import oid,convert
        self.assertEqual(oid('a','Patient',1),convert('1',{'bsonType':'objectId'},'Instances.patient','a'))
        self.assertNotEqual(oid('a','Patient',1),oid('b','Patient',1))
        self.assertNotEqual(oid('a','Patient',1),oid('a','Geodata',1))

    def test_types_and_no_imputation(self):
        from backend.app.modules.import_excel import convert
        self.assertEqual(convert('0',{'bsonType':'int'},'Patient.age','a'),0)
        self.assertIs(convert('false',{'bsonType':'bool'},'Therapy.hospitalization','a'),False)
        for value,spec,path in [('NaN',{'bsonType':'double'},'Geodata.Longitude'),
                                ('181',{'bsonType':'double'},'Geodata.Longitude'),
                                ('31.02.2024',{'bsonType':'date'},'Instances.date')]:
            with self.assertRaises(ValueError): convert(value,spec,path,'a')
        self.assertEqual(convert('01.08.2024 00:13',{'bsonType':'date'},'Instances.date','a').month,8)

    def test_structured_cells(self):
        from backend.app.modules.import_excel import convert,oid
        address=convert('10;1',{'bsonType':'object','properties':{'region':{'bsonType':'objectId'},'geodata':{'bsonType':'objectId'}}},'Location.address','a')
        self.assertEqual(address['region'],oid('a','Region',10))
        self.assertEqual(address['geodata'],oid('a','Geodata',1))
        record=convert(';Вакцина',{'bsonType':'object','properties':{'chronic_diseases':{'bsonType':'regex'},'vaccine':{'bsonType':'regex'}}},'Patient.medical_record','a')
        self.assertEqual(record['vaccine'].pattern,'Вакцина')
        self.assertNotIn('chronic_diseases',record)
