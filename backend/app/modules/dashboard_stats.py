"""Whole-database statistics and a bounded, independent Geodata map."""
def execute(store):
    db=store.database('reader')
    def groups(collection,field):
        return list(db[collection].aggregate([
            {'$group':{'_id':'$'+field,'count':{'$sum':1}}},
            {'$sort':{'_id':1}}],maxTimeMS=2500))
    points=[]
    for d in db.Geodata.find({'Longitude':{'$gte':-180,'$lte':180},'Latitude':{'$gte':-90,'$lte':90}},
                             {'Longitude':1,'Latitude':1,'Elevation':1}).sort('_id',1).limit(5000):
        points.append({'id':str(d['_id']),'lon':d['Longitude'],'lat':d['Latitude'],'elevation':d.get('Elevation'),
                       'severity':'Не указана','diagnosis':'Связь с терапией не установлена','age':None})
    dates=list(db.Instances.aggregate([
        {'$match':{'date':{'$type':'date'}}},
        {'$group':{'_id':{'$dateToString':{'format':'%Y-%m-%d','date':'$date'}},'count':{'$sum':1}}},
        {'$sort':{'_id':1}}],maxTimeMS=2500))
    counts={name:db[name].count_documents({},maxTimeMS=2500) for name in
            ('Patient','Instances','Therapy','Foci','Geodata','cases')}
    return {'counts':counts,'ages':groups('Patient','age'),'dates':dates,'points':points,
            'map_limit':5000,'map_shown':len(points),'scope':'whole_database'}
