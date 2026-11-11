import copy
import unittest
import uuid
from backend.app.modules.records import prepare, ApiError, validate

def payload():
    return {'request_id':str(uuid.uuid4()),'entities':{
        'Geodata':{'Longitude':0,'Latitude':0},'Instances':{'date':'2026-11-10'},
        'Patient':{'passport':'0012345678','age':0,'reg_date':'2026-11-10'},
        'Therapy':{'date_start':'2026-11-10','diagnosis':['A00']}}}

class StrictRecords(unittest.TestCase):
    def test_every_required_field(self):
        for name,keys in {'Geodata':['Longitude','Latitude'],'Instances':['date'],
                          'Patient':['passport','age','reg_date'],'Therapy':['date_start','diagnosis']}.items():
            for key in keys:
                data=payload();del data['entities'][name][key]
                with self.subTest(name=name,key=key), self.assertRaises(ApiError):prepare(data,'a')
    def test_every_group(self):
        for name in payload()['entities']:
            data=payload();del data['entities'][name]
            with self.subTest(name=name),self.assertRaises(ApiError):prepare(data,'a')
    def test_generated_links(self):
        data=payload();docs=prepare(data,'a')
        self.assertEqual(docs['Therapy']['patient'],docs['Patient']['_id'])
        self.assertEqual(docs['Instances']['therapy'],docs['Therapy']['_id'])
        self.assertEqual(docs['Foci']['id_instance'],docs['Instances']['instance'])
        self.assertEqual(docs['Location']['address']['geodata'],docs['Geodata']['_id'])
        self.assertEqual(docs,prepare(data,'a'))
        self.assertNotEqual(docs['Patient']['_id'],prepare(data,'b')['Patient']['_id'])
    def test_bad_values(self):
        for name,key,value in [('Patient','age',True),('Patient','age',131),('Patient','passport',' '),
            ('Therapy','diagnosis',[]),('Therapy','diagnosis',['']),('Instances','date','2026-02-30'),
            ('Geodata','Latitude',91),('Geodata','Longitude',float('nan'))]:
            data=payload();data['entities'][name][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ApiError):prepare(data,'a')
    def test_address(self):
        data=payload();del data['entities']['Geodata']
        data['entities'].update(Region={'name':'R'},Municipality={'name':'M'},Settlement={'name':'S','type':'city'},
            Street={'name':'St'},Building={'house':1,'corpus':0,'edificate':0,'fraction':0,'letters':0})
        docs=prepare(data,'a')
        self.assertNotIn('Geodata',docs)
        self.assertEqual(docs['Region']['municipality'],docs['Municipality']['_id'])
        self.assertEqual(docs['Street']['building'],docs['Building']['_id'])
        del data['entities']['Building']['corpus']
        with self.assertRaises(ApiError):prepare(data,'a')
    def test_protected_fields(self):
        for key in ('_id','_owner_id','gender','$set'):
            data=payload();data['entities']['Patient'][key]='x'
            with self.assertRaises(ApiError):prepare(data,'a')
