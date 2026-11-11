"""Real QGIS: >32 MiB file, >1000 rows, interrupted dialog and lossless resume."""
import os,sys,sqlite3,tempfile,json,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from qgis.core import QgsApplication
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtWidgets import QMainWindow,QFileDialog
from qgis.PyQt.QtCore import QTimer,QEventLoop
from qgis_plugin.mongodb_data_loader_dialog import MongodbDataLoaderDialog
from qgis_plugin.gpkg_dialog import GpkgDialog
from gpkg_fixture import build
from comprehensive_http import console,call
app=QgsApplication([],False);app.initQgis()
class Interface:
    def __init__(self):self.window=QMainWindow();self.canvas=QgsMapCanvas()
    def mainWindow(self):return self.window
    def mapCanvas(self):return self.canvas
    def setActiveLayer(self,layer):pass
loader=MongodbDataLoaderDialog(Interface());loader.password_input.setText(os.environ['QGIS_USER_TOKEN']);loader.connect_to_mongodb();editor=loader.editor

def until(predicate,seconds=240):
    loop=QEventLoop();timer=QTimer();timer.setInterval(20);timer.timeout.connect(lambda:loop.quit() if predicate() else None)
    timer.start();QTimer.singleShot(seconds*1000,loop.quit);loop.exec_();timer.stop();assert predicate(),'Timed out: '+(d.status.text() if 'd' in globals() else loader.collections_info.text())
until(lambda:loader._connected)
with tempfile.TemporaryDirectory() as folder:
    path=Path(folder)/'large.gpkg';build(path)
    db=sqlite3.connect(path);template=db.execute('SELECT * FROM cases_points LIMIT 1').fetchone();db.execute('DELETE FROM cases_points')
    db.execute('ALTER TABLE cases_points ADD COLUMN unused_padding BLOB')
    count=5003
    db.executemany('INSERT INTO cases_points VALUES(?,?,?,?,?,?,?,?,zeroblob(8192))',[(i,template[1],'BULK_QT_'+str(i),25,'2026-11-11',template[5],template[6],template[7]) for i in range(1,count+1)])
    db.commit();db.close();assert path.stat().st_size>32*1024*1024
    print('PASS large GeoPackage fixture:',count,'rows,',path.stat().st_size,'bytes',flush=True)
    before={name:console('db.'+name+'.countDocuments({})')['value'] for name in ('Patient','Geodata','Instances')}
    d=GpkgDialog(editor,loader);QFileDialog.getOpenFileName=lambda *a,**k:(str(path),'')
    d.choose_button.click();until(lambda:bool(d.info) and not d._busy)
    for target,source in {'Patient.passport':'passport','Patient.age':'age','Patient.reg_date':'registered'}.items():
        box=d.selectors[target];box.setCurrentIndex(box.findData(source))
    until(lambda:d.apply.isEnabled());job=d._job_id
    progress=call('GET','/v1/gpkg/jobs/'+job);assert progress['checked']==count and progress['status']=='ready'
    d.apply.click()
    until(lambda:d.status.text().startswith('Загружено ') and int(d.status.text().split()[1])>=50)
    d.close()
    # The last in-flight request may finish; resume from the server checkpoint,
    # not a locally estimated offset. A brand new dialog loads saved QSettings.
    d=GpkgDialog(editor,loader);d.resume.click();until(lambda:'Импорт завершён' in d.status.text())
    progress=call('GET','/v1/gpkg/jobs/'+job);assert progress['applied']==count and progress['status']=='complete'
    after={name:console('db.'+name+'.countDocuments({})')['value'] for name in before}
    assert after['Patient']==before['Patient']+count and after['Geodata']==before['Geodata']+count and after['Instances']==before['Instances']
    assert console('db.Patient.countDocuments({passport:/^BULK_QT_/})')['value']==count
    d.resume.click();until(lambda:'Импорт завершён' in d.status.text())
    assert console('db.Patient.countDocuments({passport:/^BULK_QT_/})')['value']==count
    print('PASS real QGIS chunk upload >32 MiB, all 5003 rows, interrupted dialog resume, repeat without duplicates',flush=True)
    # Invalid last row must be caught after all earlier validation batches, with
    # no additional documents written.
    db=sqlite3.connect(path);db.execute('UPDATE cases_points SET age=NULL WHERE fid=?',(count,));db.commit();db.close()
    d.choose_button.click();until(lambda:bool(d.info) and d.info['upload_id']!=progress['payload']['upload_id'] and not d._busy)
    for target,source in {'Patient.passport':'passport','Patient.age':'age','Patient.reg_date':'registered'}.items():
        box=d.selectors[target];box.setCurrentIndex(box.findData(source))
    until(lambda:'Проверка не выполнена' in d.status.text());assert not d.apply.isEnabled()
    assert str(count) in d.error_details.toPlainText()
    for name,total in after.items():assert console('db.'+name+'.countDocuments({})')['value']==total
    print('PASS invalid row 5003 prevents any writes after full multi-page validation',flush=True)
    d.close()
loader.close()
