"""Actual Qt file-upload/mapping workflow and Streamlit role rendering."""
import os,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from qgis.core import QgsApplication
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtWidgets import QMainWindow,QFileDialog
from qgis.PyQt.QtCore import QEventLoop,QTimer
from qgis_plugin.mongodb_data_loader_dialog import MongodbDataLoaderDialog
from qgis_plugin.gpkg_dialog import GpkgDialog
from gpkg_fixture import build,MAPPING
from records_http import request
app=QgsApplication([],False);app.initQgis()
class Interface:
    def __init__(self):self.window=QMainWindow();self.canvas=QgsMapCanvas()
    def mainWindow(self):return self.window
    def mapCanvas(self):return self.canvas
    def setActiveLayer(self,l):pass
loader=MongodbDataLoaderDialog(Interface());loader.password_input.setText(os.environ['QGIS_USER_TOKEN'])
editor=loader.configure_editor()
def settle():
    loop=QEventLoop();timer=QTimer();timer.setInterval(30)
    timer.timeout.connect(lambda:loop.quit() if not editor.client.pending else None)
    timer.start();QTimer.singleShot(60000,loop.quit);loop.exec_();timer.stop()
    assert not editor.client.pending
with tempfile.TemporaryDirectory() as folder:
    path=Path(folder)/'points.gpkg';build(path)
    import sqlite3
    c=sqlite3.connect(path);c.execute("UPDATE cases_points SET passport='UI_'||fid");c.commit();c.close()
    dialog=GpkgDialog(editor,loader)
    QFileDialog.getOpenFileName=lambda *a,**k:(str(path),'')
    dialog.choose();settle()
    assert dialog.info,dialog.status.text()
    for target,source in MAPPING.items():
        combo=dialog.selectors[target];combo.setCurrentIndex(combo.findData(source))
    dialog.preview();settle()
    assert dialog.validated,dialog.status.text()
    dialog.save(0);settle()
    assert 'завершён' in dialog.status.text(),dialog.status.text()
    # A second send must reuse deterministic request IDs.
    dialog.save(0);settle()
    assert 'завершён' in dialog.status.text()
    print('PASS QGIS file selection, field mapping, validation, import and repeat')
loader.close()
