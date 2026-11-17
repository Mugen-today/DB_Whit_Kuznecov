import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from backend.app.modules.seed_b import execute
class Collection:
    def __init__(self):self.rows={}
    def find(self,f,p=None):return [{'_id':i} for i in f['_id']['$in'] if i in self.rows]
    def insert_many(self,docs,ordered=False):
        self.rows.update({d['_id']:d for d in docs});return SimpleNamespace(inserted_ids=[d['_id'] for d in docs])
class Database:
    def __init__(self):self.cols={}
    def __getitem__(self,n):return self.cols.setdefault(n,Collection())
    @property
    def cases(self):return self['cases']
class Store:
    def __init__(self):self.db=Database()
    def database(self,role):return self.db
class SeedBTests(unittest.TestCase):
    def test_links_no_fabrication_and_repeat(self):
        row={'location':{'type':'Point','coordinates':[30,60]},'patient':{'age':None,'reg_date':'2023-02-20 00:00:00'},
             'therapy':{'diagnosis':['A15.0'],'date_start':'2023-02-21 00:00:00','died_tb':False},
             'foci':{'address':'source address','region':'source region','municipality':None}}
        store=Store()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'part.json';path.write_text(json.dumps([row]))
            execute(path,'test',store)
            patient=next(iter(store.db['Patient'].rows.values()))
            self.assertNotIn('age',patient);self.assertNotIn('passport',patient)
            therapy=next(iter(store.db['Therapy'].rows.values()))
            self.assertEqual(therapy['patient'],patient['_id']);self.assertNotIn('result',therapy)
            instance=next(iter(store.db['Instances'].rows.values()));focus=next(iter(store.db['Foci'].rows.values()))
            self.assertEqual(focus['id_instance'],instance['instance'])
            self.assertTrue(all(n==0 for n in execute(path,'test',store)['inserted'].values()))
