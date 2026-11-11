"""Restored original layout: real QGIS HTTP collection loading."""
import sys,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from qgis.core import QgsApplication,QgsProject
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtWidgets import QMainWindow
from qgis.PyQt.QtCore import QEventLoop,QTimer,Qt
from qgis_plugin.mongodb_data_loader_dialog import MongodbDataLoaderDialog
app=QgsApplication([],False);app.initQgis()
class Interface:
    def __init__(self):self.window=QMainWindow();self.canvas=QgsMapCanvas()
    def mainWindow(self):return self.window
    def mapCanvas(self):return self.canvas
    def setActiveLayer(self,l):pass
d=MongodbDataLoaderDialog(Interface());d.password_input.setText(os.environ['QGIS_USER_TOKEN'])
def settle():
    loop=QEventLoop();timer=QTimer();timer.setInterval(50)
    timer.timeout.connect(lambda:loop.quit() if not d.editor.client.pending else None)
    timer.start();QTimer.singleShot(20000,loop.quit);loop.exec_();timer.stop()
    assert not d.editor.client.pending
d.connect_to_mongodb();settle()
assert d.collections_list.count()==17
for i in range(d.collections_list.count()):
    if d.collections_list.item(i).text()=='Geodata':d.collections_list.item(i).setCheckState(Qt.Checked)
d.load_selected_collections();settle()
assert d.editor.layer.featureCount()==100
assert any(f.hasGeometry() for f in d.editor.layer.getFeatures())
for i in range(d.collections_list.count()):
    item=d.collections_list.item(i)
    item.setCheckState(Qt.Checked if item.text()=='Patient' else Qt.Unchecked)
d.load_selected_collections();settle()
f=next(d.editor.layer.getFeatures());d.editor.layer.selectByIds([f.id()])
d.editor.json_editor=lambda title,old:{**old,'age':42,'passport':old.get('passport') or 'TEST_ONLY'}
d.edit_record();settle()
assert any(doc['age']==42 for doc in d.editor.documents.values())
from records_http import sample
payload=sample();d.editor.json_editor=lambda title,old:payload
d.create_record();settle()
assert d.editor.pending_record is None
d.close();QgsProject.instance().removeAllMapLayers()
print('PASS restored Data Loader layout and real seeded Geodata load')
