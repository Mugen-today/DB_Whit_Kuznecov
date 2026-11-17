"""UI strict/partial selection and complete CSV report against the test backend."""
import os,sys,json,tempfile,sqlite3,csv
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from qgis.core import QgsApplication
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtWidgets import QMainWindow,QFileDialog
from qgis.PyQt.QtCore import QTimer,QEventLoop
from qgis_plugin.mongodb_data_loader_dialog import MongodbDataLoaderDialog
from qgis_plugin.gpkg_dialog import GpkgDialog
from gpkg_fixture import build
from comprehensive_http import call,console
app=QgsApplication([],False);app.initQgis()
class Interface:
    def __init__(self):self.window=QMainWindow();self.canvas=QgsMapCanvas()
    def mainWindow(self):return self.window
    def mapCanvas(self):return self.canvas
    def setActiveLayer(self,layer):pass
loader=MongodbDataLoaderDialog(Interface());loader.password_input.setText(os.environ['QGIS_USER_TOKEN']);loader.connect_to_mongodb();editor=loader.editor

def until(predicate,seconds=120):
    loop=QEventLoop();timer=QTimer();timer.setInterval(20);timer.timeout.connect(lambda:loop.quit() if predicate() else None)
    timer.start();QTimer.singleShot(seconds*1000,loop.quit);loop.exec_();timer.stop();assert predicate(),d.status.text() if 'd' in globals() else 'Session timeout'
until(lambda:loader._connected)
with tempfile.TemporaryDirectory() as folder:
    source=Path(folder)/'policy.gpkg';build(source)
    db=sqlite3.connect(source);row=db.execute('SELECT * FROM cases_points LIMIT 1').fetchone();db.execute('DELETE FROM cases_points')
    # More than a preview page, and 121 invalid rows to exercise full export.
    db.executemany('INSERT INTO cases_points VALUES(?,?,?,?,?,?,?,?)',[(i,row[1],'UI_POLICY_'+str(i),25 if i%2==0 else None,*row[4:]) for i in range(1,244)]);db.commit();db.close()
    before=console('db.Patient.countDocuments({passport:/^UI_POLICY_/})')['value'];assert before==0
    d=GpkgDialog(editor,loader);QFileDialog.getOpenFileName=lambda *a,**k:(str(source),'')
    d.choose_button.click();until(lambda:bool(d.info) and not d._busy)
    for target,field in {'Patient.passport':'passport','Patient.age':'age','Patient.reg_date':'registered'}.items():
        box=d.selectors[target];box.setCurrentIndex(box.findData(field))
    until(lambda:d._report_state.get('status')=='invalid');assert not d.apply.isEnabled()
    assert console('db.Patient.countDocuments({passport:/^UI_POLICY_/})')['value']==0
    d.error_policy.setCurrentIndex(d.error_policy.findData('partial'));until(lambda:d.apply.isEnabled())
    assert d._report_state['rejected_rows']==122 and d._report_state['valid_rows']==121
    d.apply.click();until(lambda:d._report_state.get('status')=='complete_with_errors')
    assert d._report_state['documents_present']==242 and d._report_state['successful_rows']==121
    destination=Path(folder)/'report.csv';QFileDialog.getSaveFileName=lambda *a,**k:(str(destination),'')
    d.report_button.click();until(lambda:destination.exists())
    with destination.open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.DictReader(stream))
    rejected=[x for x in rows if x['severity']=='error'];assert len(rejected)==122
    assert {int(x['row']) for x in rejected}==set(range(1,244,2))
    assert all(x['field']=='Patient.age' and x['stage']=='validation' and x['reason'] for x in rejected)
    assert console('db.Patient.countDocuments({passport:/^UI_POLICY_/})')['value']==121
    assert '242' in d.report_summary.text()
    print('PASS actual QGIS strict/partial UI, 243 source rows, 121 successes / 122 explicit rejects, complete CSV beyond 100 errors',flush=True)
    d.close()
loader.close()
