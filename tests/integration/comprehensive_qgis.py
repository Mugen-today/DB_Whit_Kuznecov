"""Real PyQGIS: all collection traversal, native edit commit and role switching."""
import os,sys,json,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from qgis.core import QgsApplication,QgsProject,QgsVectorFileWriter,QgsVectorLayer
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import QEventLoop,QTimer,Qt
from qgis.PyQt.QtWidgets import QMainWindow,QMessageBox
from qgis_plugin.mongodb_data_loader_dialog import MongodbDataLoaderDialog
from comprehensive_http import call,console
app=QgsApplication([],False);app.initQgis()
QMessageBox.warning=lambda *args: print('QGIS warning:',args[-1],flush=True)
class Interface:
    def __init__(self):self.window=QMainWindow();self.canvas=QgsMapCanvas();self.current=None
    def mainWindow(self):return self.window
    def mapCanvas(self):return self.canvas
    def setActiveLayer(self,layer):self.current=layer
    def activeLayer(self):return self.current
iface=Interface();loader=MongodbDataLoaderDialog(iface);editor=loader.editor
def settle(finished=None,seconds=240):
    loop=QEventLoop();timer=QTimer();timer.setInterval(50)
    def tick():
        if finished is not None:
            if finished():loop.quit()
        elif editor.client and not editor.client.pending:loop.quit()
    timer.timeout.connect(tick);timer.start();QTimer.singleShot(seconds*1000,loop.quit);loop.exec_();timer.stop()
    if finished is not None:assert finished(),loader.collections_info.text()
    else:assert not editor.client.pending
loader.password_input.setText(os.environ['QGIS_USER_TOKEN']);loader.connect_to_mongodb();settle()
assert loader._connected and editor.session['role']=='user'
loader.select_all_collections(Qt.Checked);loader.load_selected_collections()
settle(lambda:'Загрузка завершена:' in loader.collections_info.text(),seconds=500)
assert len(editor.managed_layers)==17,loader.collections_info.text()
for name,identifier in editor.managed_layers.items():
    layer=QgsProject.instance().mapLayer(identifier)
    assert layer is not None and layer.isValid(),name
    assert layer.featureCount()==console('db.'+name+'.countDocuments({})')['value'],name
geo_check=QgsProject.instance().mapLayer(editor.managed_layers['Geodata'])
assert geo_check.crs().authid()=='EPSG:4326'
assert all(not f.geometry().isNull() and not f.geometry().isEmpty() and -180<=f.geometry().asPoint().x()<=180 and -90<=f.geometry().asPoint().y()<=90 for f in geo_check.getFeatures())
print('PASS Geodata every feature has a nonempty WGS84 Point',flush=True)
print('PASS QGIS all 17 collections and every record, including empty tables',flush=True)
import tempfile
with tempfile.TemporaryDirectory() as folder:
    filename=str(Path(folder)/'all_collections.gpkg')
    for index,(name,identifier) in enumerate(editor.managed_layers.items()):
        layer=QgsProject.instance().mapLayer(identifier)
        options=QgsVectorFileWriter.SaveVectorOptions();options.driverName='GPKG';options.layerName=name
        options.actionOnExistingFile=QgsVectorFileWriter.CreateOrOverwriteFile if index==0 else QgsVectorFileWriter.CreateOrOverwriteLayer
        result=QgsVectorFileWriter.writeAsVectorFormatV3(layer,filename,QgsProject.instance().transformContext(),options)
        assert result[0]==QgsVectorFileWriter.NoError,(name,result)
        exported=QgsVectorLayer(filename+'|layername='+name,name,'ogr')
        assert exported.isValid() and exported.featureCount()==layer.featureCount(),name
    print('PASS all 17 collections exported to GeoPackage and reopened with equal counts',flush=True)
patient_layer=QgsProject.instance().mapLayer(editor.managed_layers['Patient']);iface.setActiveLayer(patient_layer)
feature=next(patient_layer.getFeatures());identifier=str(feature['_key'])
assert patient_layer.startEditing()
patient_layer.changeAttributeValue(feature.id(),patient_layer.fields().indexOf('age'),140)
assert not patient_layer.commitChanges()
assert patient_layer.isEditable() and patient_layer.isModified()
assert console('db.Patient.find({_id:ObjectId("'+identifier+'")})')['records'][0]['age']!=140
patient_layer.changeAttributeValue(feature.id(),patient_layer.fields().indexOf('age'),51)
assert patient_layer.commitChanges(),patient_layer.commitErrors()
saved=console('db.Patient.find({_id:ObjectId("'+identifier+'")})')['records'][0]
assert saved['age']==51,(saved['age'],editor.status.text(),patient_layer.editBuffer(),patient_layer.getFeature(feature.id())['age'])
geo_layer=QgsProject.instance().mapLayer(editor.managed_layers['Geodata']);iface.setActiveLayer(geo_layer)
feature=next(geo_layer.getFeatures());identifier=str(feature['_key'])
assert geo_layer.startEditing()
geo_layer.changeAttributeValue(feature.id(),geo_layer.fields().indexOf('Longitude'),31.111)
assert geo_layer.commitChanges(),geo_layer.commitErrors()
saved=console('db.Geodata.find({_id:ObjectId("'+identifier+'")})')['records'][0]
assert saved['geometry']['coordinates'][0]==31.111
assert abs(geo_layer.getFeature(feature.id()).geometry().asPoint().x()-31.111)<1e-8
if 'Instances' in editor.managed_layers:
    legacy_layer=QgsProject.instance().mapLayer(editor.managed_layers['Instances'])
    for f in legacy_layer.getFeatures():
        if str(f['_key']).startswith('e:'):
            assert legacy_layer.startEditing()
            legacy_layer.changeAttributeValue(f.id(),legacy_layer.fields().indexOf('date'),'2026-11-11')
            assert legacy_layer.commitChanges(),legacy_layer.commitErrors()
            break
print('PASS native QGIS attribute and geometry synchronisation to MongoDB',flush=True)
old_ids=list(editor.managed_layers.values())
loader.username_input.setCurrentText('guest');loader.password_input.setText(os.environ['QGIS_GUEST_TOKEN']);loader.connect_to_mongodb();settle()
assert editor.session['role']=='guest' and not loader.create_button.isEnabled()
assert all(QgsProject.instance().mapLayer(i) is None for i in old_ids)
assert loader.collections_list.count()==13
loader.username_input.setCurrentText('analyst');loader.password_input.setText(os.environ['DASHBOARD_TOKEN']);loader.connect_to_mongodb();settle()
assert editor.session['role']=='reader' and loader.collections_list.count()==17
editor.collection.setCurrentText('Patient');editor.load_all('Patient')
settle(lambda:bool(editor.managed_layers.get('Patient')),seconds=240)
layer=QgsProject.instance().mapLayer(editor.managed_layers['Patient'])
assert layer.readOnly() and not layer.startEditing()
print('PASS user/guest/analyst switching, refreshed collection permissions and read-only layers',flush=True)
loader.close();QgsProject.instance().removeAllMapLayers()

# Exercise file selection/mapping against the same disposable backend.
import subprocess
subprocess.run([sys.executable,str(Path(__file__).with_name('integrated_ui.py'))],check=True,timeout=150)
from gpkg_rejections import run as gpkg_rejections
gpkg_rejections()
