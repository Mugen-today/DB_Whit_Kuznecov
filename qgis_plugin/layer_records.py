"""QGIS native edit buffers -> transactional backend batches, with conflict retention."""
import json
from qgis.PyQt.QtCore import QVariant,QEventLoop,QTimer
from qgis.core import QgsVectorLayer,QgsField,QgsFeature,QgsProject,QgsVariantUtils
from qgis.PyQt.QtWidgets import QMessageBox
from .geometry_compat import decode_geometry
def key(doc):return doc.get('_key',str(doc['_id']))
def make_layer(page):
    rows=page['records'];name=page['collection'];spatial=name=='Geodata'
    layer=QgsVectorLayer('Point?crs=EPSG:4326' if spatial else 'None','MongoDB '+name,'memory')
    schema=page.get('schema',{}).get('properties',{})
    fields=list(dict.fromkeys(['_id','_key','qgis_revision']+[k for k in schema if not k.startswith('_')]+[k for row in rows for k in row]))
    def kind(field):
        if field=='qgis_revision':return QVariant.LongLong
        if any(isinstance(d.get(field),(dict,list)) for d in rows):return QVariant.String
        types=schema.get(field,{}).get('bsonType',[])
        if isinstance(types,str):types=[types]
        if 'string' in types or field in ('_id','_key'):return QVariant.String
        if 'int' in types or 'long' in types:return QVariant.LongLong
        if 'double' in types:return QVariant.Double
        if 'bool' in types:return QVariant.Bool
        return QVariant.String
    kinds={field:kind(field) for field in fields}
    layer.dataProvider().addAttributes([QgsField(k,kinds[k]) for k in fields]);layer.updateFields()
    geo={str(f['id']):f for f in page.get('features',[])}
    features=[]
    for row in rows:
        f=QgsFeature(layer.fields());values=[]
        for field in fields:
            value=row.get(field)
            if value is not None and kinds[field]==QVariant.String:
                value=json.dumps(value,ensure_ascii=False) if isinstance(value,(dict,list)) else str(value)
            values.append(value)
        f.setAttributes(values)
        if spatial:
            item=geo.get(str(key(row)),geo.get(str(row['_id']),{}))
            if item.get('geometry'):f.setGeometry(decode_geometry(item['geometry'],item.get('geometry_wkt')))
        features.append(f)
    layer.dataProvider().addFeatures(features);layer.updateExtents()
    from .guarded_memory import guarded
    layer=guarded(layer)
    config=layer.editFormConfig()
    for field in ('_id','_key','qgis_revision','instance'):
        index=layer.fields().indexOf(field)
        if index>=0:config.setReadOnly(index,True)
    layer.setEditFormConfig(config)
    return layer
def bind(editor,layer,page):
    docs={key(d):d for d in page['records']}
    layer.setReadOnly(not page.get('can_write',False))
    binding={'layer':layer,'documents':docs,'identity':editor.connection_key(),'collection':page['collection'],'sending':False}
    editor.bindings[layer.id()]=binding
    def before_commit(*_):
        if binding['sending']:return
        layer.dataProvider().confirmed=False
        if editor.connection_key()!=binding['identity']:
            editor.status.setText('Подключение изменилось; загрузите слой заново');return
        buffer=layer.editBuffer()
        if buffer.addedFeatures() or buffer.deletedFeatureIds():
            editor.status.setText('Создание — через форму/импорт. Удаление документов не разрешено.');return
        ids=set(buffer.changedAttributeValues())|set(buffer.changedGeometries())
        if not ids:layer.dataProvider().confirmed=True;return
        edits=[]
        try:
            for fid in ids:
                f=layer.getFeature(fid);identifier=str(f['_key']);doc=docs[identifier];changes={}
                for idx,value in buffer.changedAttributeValues().get(fid,{}).items():
                    field=layer.fields()[idx].name()
                    if field.startswith('_') or field in ('instance','qgis_revision'):raise ValueError('Служебные поля неизменяемы')
                    if QgsVariantUtils.isNull(value):value=None
                    original=doc.get(field)
                    if isinstance(original,(dict,list)) and isinstance(value,str):value=json.loads(value)
                    changes[field]=value
                if fid in buffer.changedGeometries():changes['geometry']=json.loads(buffer.changedGeometries()[fid].asJson())
                if changes:edits.append({'_id':identifier,'revision':doc.get('qgis_revision',0),'changes':changes})
        except Exception as exc:
            editor.status.setText(str(exc));return
        binding['sending']=True
        try:
            for start in range(0,len(edits),200):
                loop=QEventLoop();result=[];errors=[]
                editor.api().request('POST','/v1/collections/'+binding['collection']+'/batch',{'edits':edits[start:start+200]},
                    lambda data:(result.append(data),loop.quit()),lambda message:(errors.append(message),loop.quit()))
                QTimer.singleShot(65000,loop.quit);loop.exec_()
                if not result:raise ValueError(errors[0] if errors else 'Сохранение не подтверждено. Повторите после проверки связи.')
                for updated in result[0]['records']:docs[key(updated)]=updated
            layer.dataProvider().confirmed=True
            # Update revision values in the same local edit buffer.
            for fid in ids:
                identifier=str(layer.getFeature(fid)['_key']);updated=docs[identifier]
                for index,field in enumerate(layer.fields()):
                    value=updated.get(field.name())
                    if value is not None and field.type()==QVariant.String:
                        value=json.dumps(value,ensure_ascii=False) if isinstance(value,(dict,list)) else str(value)
                    layer.changeAttributeValue(fid,index,value)
                if binding['collection']=='Geodata' and updated.get('geometry'):
                    layer.changeGeometry(fid,decode_geometry(updated['geometry']))
            editor.documents=docs if editor.layer_id==layer.id() else editor.documents
            editor.status.setText('Правки сохранены в MongoDB')
        except Exception as exc:
            editor.status.setText('MongoDB: '+str(exc)+'. Буфер правок сохранён.')
            QMessageBox.warning(editor,'Изменения не сохранены',str(exc))
        finally:binding['sending']=False
    layer.beforeCommitChanges.connect(before_commit)
