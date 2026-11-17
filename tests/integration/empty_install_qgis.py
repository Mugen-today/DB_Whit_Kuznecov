"""All 17 empty collections must be usable without a dataset."""
import os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from qgis.core import QgsApplication,QgsProject
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import QTimer,QEventLoop,Qt
from qgis.PyQt.QtWidgets import QMainWindow
from qgis_plugin.mongodb_data_loader_dialog import MongodbDataLoaderDialog
app=QgsApplication([],False);app.initQgis()
class Interface:
    def __init__(self):self.window=QMainWindow();self.canvas=QgsMapCanvas()
    def mainWindow(self):return self.window
    def mapCanvas(self):return self.canvas
    def setActiveLayer(self,l):pass
loader=MongodbDataLoaderDialog(Interface());loader.password_input.setText(os.environ['QGIS_USER_TOKEN']);loader.connect_to_mongodb()
def until(test):
    loop=QEventLoop();timer=QTimer();timer.setInterval(20);timer.timeout.connect(lambda:loop.quit() if test() else None);timer.start();QTimer.singleShot(120000,loop.quit);loop.exec_();timer.stop();assert test(),loader.collections_info.text()
until(lambda:loader._connected)
loader.select_all_collections(Qt.Checked);loader.load_selected_collections();until(lambda:'Загрузка завершена:' in loader.collections_info.text())
assert len(loader.editor.managed_layers)==17
for name,identifier in loader.editor.managed_layers.items():
    layer=QgsProject.instance().mapLayer(identifier);assert layer.isValid() and layer.featureCount()==0,name
geo=QgsProject.instance().mapLayer(loader.editor.managed_layers['Geodata']);assert geo.crs().authid()=='EPSG:4326'
print('PASS actual QGIS: all 17 empty layers/tables, Geodata CRS, connected permissions without source files',flush=True)
loader.close();QgsProject.instance().removeAllMapLayers()
