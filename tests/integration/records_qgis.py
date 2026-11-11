"""Real QGIS/Qt HTTP edit, intended for a disposable test database."""
import os,sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from qgis.core import QgsApplication, QgsProject
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtWidgets import QMainWindow
from qgis.PyQt.QtCore import QEventLoop, QTimer
from qgis_plugin.records_dialog import make_table
from qgis_plugin.records_dialog import RecordsDialog
from records_http import request
app=QgsApplication([],False);app.initQgis()
class Interface:
    def __init__(self):self.window=QMainWindow();self.canvas=QgsMapCanvas()
    def mainWindow(self):return self.window
    def mapCanvas(self):return self.canvas
    def setActiveLayer(self,layer):pass
iface=Interface();dialog=RecordsDialog(iface)
dialog.url.setText(os.environ['QGIS_TEST_BACKEND']);dialog.token.setText(os.environ['QGIS_USER_TOKEN'])
def settle():
    loop=QEventLoop();timer=QTimer();timer.setInterval(30)
    timer.timeout.connect(lambda:loop.quit() if not dialog.client.pending else None)
    timer.start();QTimer.singleShot(15000,loop.quit);loop.exec_();timer.stop()
    assert not dialog.client.pending, 'HTTP timeout'
dialog.collection.setCurrentText('Patient');dialog.reload();settle()
assert dialog.layer.featureCount()>0,dialog.status.text()
feature=next(dialog.layer.getFeatures());dialog.layer.selectByIds([feature.id()])
doc=dialog.documents[str(feature['_id'])]
dialog.json_editor=lambda title,old:{**old,'age':42}
dialog.edit_point();settle()
page=request('GET','/v1/collections/Patient')
assert any(d['_id']==doc['_id'] and d['age']==42 for d in page['records'])
for name in request('GET','/v1/collections')['collections']:
    page=request('GET','/v1/collections/'+name)
    layer=make_table(page)
    assert layer.isValid(),name
    if name=='Geodata' and page['records']:
        assert any(f.hasGeometry() for f in layer.getFeatures()), 'Backend geometry not rendered'
from records_http import sample
data=sample()
dialog.json_editor=lambda title,old:data
dialog.create_point();settle()
assert dialog.pending_record is None,dialog.status.text()
dialog.close();QgsProject.instance().removeAllMapLayers()
print('PASS PyQGIS collection tables and dialog edit roundtrip')
