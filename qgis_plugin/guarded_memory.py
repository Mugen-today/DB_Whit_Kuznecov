"""Memory-backed QGIS provider which rejects commits until backend confirms them.

setAllowCommit is not exposed by PyQGIS. Provider failure is the supported edit
buffer contract: failed commits keep the buffer without accepting local changes.
"""
import uuid
from qgis.core import (QgsVectorDataProvider,QgsProviderMetadata,QgsProviderRegistry,QgsVectorLayer)
_pending={}
_created={}
_metadata=None
class GuardedMemory(QgsVectorDataProvider):
    def __init__(self,uri,options,flags):
        super().__init__(uri,options,flags)
        self.available=uri in _pending
        self.memory=_pending.pop(uri,None) or QgsVectorLayer('None','Expired MongoDB cache','memory')
        self.delegate=self.memory.dataProvider();self.confirmed=False
    def name(self):return 'gis_mongodb'
    def description(self):return 'Backend-confirmed MongoDB memory layer'
    def storageType(self):return 'MongoDB through backend (memory cache)'
    def isValid(self):return self.available and self.memory.isValid()
    def fields(self):return self.delegate.fields()
    def wkbType(self):return self.delegate.wkbType()
    def crs(self):return self.delegate.crs()
    def extent(self):return self.delegate.extent()
    def featureCount(self):return self.delegate.featureCount()
    def getFeatures(self,request):return self.delegate.getFeatures(request)
    def featureSource(self):return self.delegate.featureSource()
    def capabilities(self):return self.ChangeAttributeValues|self.ChangeGeometries|self.ChangeFeatures|self.SelectAtId
    def changeAttributeValues(self,changes):
        if not self.confirmed:self.pushError('MongoDB has not confirmed this edit');return False
        return self.delegate.changeAttributeValues(changes)
    def changeGeometryValues(self,changes):
        if not self.confirmed:self.pushError('MongoDB has not confirmed this edit');return False
        return self.delegate.changeGeometryValues(changes)
    def changeFeatures(self,attributes,geometries):
        return self.changeAttributeValues(attributes) and self.changeGeometryValues(geometries)
class Metadata(QgsProviderMetadata):
    def __init__(self):super().__init__('gis_mongodb','MongoDB backend memory cache')
    def createProvider(self,uri,options,flags):
        provider=GuardedMemory(uri,options,flags);_created[uri]=provider;return provider
def guarded(memory):
    global _metadata
    registry=QgsProviderRegistry.instance()
    if not registry.providerMetadata('gis_mongodb'):
        _metadata=Metadata();registry.registerProvider(_metadata)
    token=str(uuid.uuid4());_pending[token]=memory
    layer=QgsVectorLayer(token,memory.name(),'gis_mongodb')
    layer._mongodb_provider=_created.pop(token,None)
    if not layer.isValid():raise ValueError('Cannot initialise MongoDB layer provider')
    return layer
