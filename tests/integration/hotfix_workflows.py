"""Actual Qt/network workflows; only against the disposable A+B test database."""
import os,sys,json,tempfile,sqlite3
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from qgis.core import QgsApplication
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtWidgets import QMainWindow,QFileDialog
from qgis.PyQt.QtCore import QTimer,QEventLoop
from qgis_plugin.mongodb_data_loader_dialog import MongodbDataLoaderDialog
from qgis_plugin.console_dialog import MongoConsoleDialog
from qgis_plugin.gpkg_dialog import GpkgDialog
from qgis_plugin.geometry_compat import decode_geometry
from gpkg_fixture import build
from comprehensive_http import console
app=QgsApplication([],False);app.initQgis()
class Interface:
    def __init__(self):self.window=QMainWindow();self.canvas=QgsMapCanvas()
    def mainWindow(self):return self.window
    def mapCanvas(self):return self.canvas
    def setActiveLayer(self,layer):pass
loader=MongodbDataLoaderDialog(Interface());loader.password_input.setText(os.environ['QGIS_USER_TOKEN']);loader.connect_to_mongodb();editor=loader.editor

def until(predicate,seconds=90):
    loop=QEventLoop();timer=QTimer();timer.setInterval(20);timer.timeout.connect(lambda:loop.quit() if predicate() else None)
    timer.start();QTimer.singleShot(seconds*1000,loop.quit);loop.exec_();timer.stop();assert predicate(),'Workflow timeout: '+loader.collections_info.text()
until(lambda:loader._connected)
# Legacy-compatible path intentionally supplies no WKT and never calls the 3.36 API.
for wkt in (None,'POINT (30 60)'):
    g=decode_geometry({'type':'Point','coordinates':[30,60]},wkt);assert not g.isNull() and g.asPoint().x()==30
print('PASS compatible GeoJSON/WKT decoding without geometryFromGeoJson',flush=True)
c=MongoConsoleDialog(editor)
queries=['db["Patient"].find({age: {$gte: 30}}).limit(3).pretty()',
 '/* custom */ db.getCollection("Geodata").find({"geometry.type": /^point$/i}).limit(2)',
 'db.Patient.countDocuments({age: {$gte: 30}})',
 'db.Geodata.aggregate([{$match: {"geometry.type": /^Point$/}}, {$count: "n"}]).toArray()',
 'db.Patient.distinct("age", {age: {$gte: 30}})']
for text in queries:
    c.code.setPlainText(text);c.run.click();until(lambda:c.run.isEnabled())
    assert not c.status.text().startswith('Ошибка'),(text,c.status.text())
    result=json.loads(c.output.toPlainText());assert 'records' in result or 'value' in result
c.code.setPlainText('db.Patient.find({age: )');c.run.click();until(lambda:c.run.isEnabled());assert c.status.text().startswith('Ошибка')
c.code.setPlainText('db.Patient.aggregate([{$out: "Patient"}])');c.run.click();until(lambda:c.run.isEnabled());assert c.status.text().startswith('Ошибка')
print('PASS actual user query text through QGIS -> HTTP -> MongoDB; find/aggregate/count/distinct/regex and useful errors',flush=True)
with tempfile.TemporaryDirectory() as folder:
    p=Path(folder)/'automatic.gpkg';build(p)
    db=sqlite3.connect(p);db.execute("UPDATE cases_points SET passport='AUTO_HOTFIX_'||fid")
    db.execute('ALTER TABLE cases_points ADD COLUMN optional_elevation REAL');db.commit();db.close()
    d=GpkgDialog(editor,loader);QFileDialog.getOpenFileName=lambda *args,**kwargs:(str(p),'')
    d.choose_button.click();until(lambda:bool(d.info) and not d._busy)
    for target,source in {'Patient.passport':'passport','Patient.age':'age','Patient.reg_date':'registered','Geodata.Elevation':'optional_elevation'}.items():
        box=d.selectors[target];box.setCurrentIndex(box.findData(source))
    # No click on Validate: this is the previously blocked user path.
    until(lambda:d.apply.isEnabled());assert d.validated
    before={name:console('db.'+name+'.countDocuments({})')['value'] for name in ('Patient','Geodata','Instances')}
    d.apply.click();until(lambda:'Импорт завершён' in d.status.text())
    after={name:console('db.'+name+'.countDocuments({})')['value'] for name in before}
    assert after['Patient']==before['Patient']+2 and after['Geodata']==before['Geodata']+2 and after['Instances']==before['Instances']
    d.selectors['Patient.reg_date'].setCurrentIndex(0);assert not d.apply.isEnabled()
    until(lambda:'не выполнена' in d.status.text());assert not d.apply.isEnabled() and 'reg_date' in d.status.text(),d.status.text()
    box=d.selectors['Patient.reg_date'];box.setCurrentIndex(box.findData('registered'));until(lambda:d.apply.isEnabled())
    d.apply.click();until(lambda:'Импорт завершён' in d.status.text())
    assert console('db.Patient.countDocuments({})')['value']==after['Patient']
    d.close()
print('PASS automatic validation enables import, optional NULL accepted, missing required field disables import, repeat has no duplicates',flush=True)
loader.username_input.setCurrentText('guest');loader.password_input.setText(os.environ['QGIS_GUEST_TOKEN']);loader.connect_to_mongodb();until(lambda:loader._connected)
c.code.setPlainText('db["Social_group"].find({})');c.run.click();until(lambda:c.run.isEnabled());assert c.status.text().startswith('Ошибка')
print('PASS new console syntax preserves guest access restrictions',flush=True)
c.close();loader.close()
