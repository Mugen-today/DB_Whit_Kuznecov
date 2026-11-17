"""Bounded lookup reuse during ONE validation page; never used during writes."""
from collections import OrderedDict
from bson import json_util

class LookupDatabase:
    def __init__(self,database):
        self.database=database;self.cache=OrderedDict();self.bytes=0
    def __getitem__(self,name):return LookupCollection(self,name)
    def __getattr__(self,name):return self[name]

class LookupCollection:
    def __init__(self,parent,name):self.parent=parent;self.name=name
    def find_one(self,query,projection=None,**kwargs):
        key=json_util.dumps([self.name,query,projection],sort_keys=True)
        cache=self.parent.cache
        if key in cache:
            cache.move_to_end(key);return cache[key][0]
        result=self.parent.database[self.name].find_one(query,projection,**kwargs)
        size=len(key.encode())+len(json_util.dumps(result).encode())
        if size<=65536:
            while cache and (len(cache)>=1024 or self.parent.bytes+size>1048576):
                _,(_,old_size)=cache.popitem(last=False);self.parent.bytes-=old_size
            cache[key]=(result,size);self.parent.bytes+=size
        return result
