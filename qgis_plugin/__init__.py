def classFactory(iface):
    from .mongodb_data_loader import MongodbDataLoader
    return MongodbDataLoader(iface)
