"""Deterministic Qt regressions; does not use MongoDB or change any database."""
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from qgis.core import QgsApplication,QgsJsonUtils
from qgis_plugin import geometry_compat
from qgis_plugin.gpkg_dialog import GpkgDialog
app=QgsApplication([],False);app.initQgis()
# Simulate the older API surface: geometryFromGeoJson is deliberately absent.
geometry_compat.QgsJsonUtils=SimpleNamespace(stringToFeatureList=QgsJsonUtils.stringToFeatureList)
assert geometry_compat.decode_geometry({'type':'Point','coordinates':[30,60]}).asPoint().y()==60
class API:
    def __init__(self):self.calls=[]
    def request(self,method,path,payload,success,failure):self.calls.append((payload,success,failure))
class Editor:
    def __init__(self):self.client=API()
    def api(self):return self.client
    def connection_key(self):return ("http://localhost:8000","not-a-real-token","test")
editor=Editor();d=GpkgDialog(editor,None)
d.uploaded({'upload_id':'test','tables':[{'name':'attributes','geometry':None,'fields':['age','passport','registered'],'rows':2}],
 'targets':['Patient.age','Patient.passport','Patient.reg_date'],'requirements':{'Patient':['age','passport','reg_date']}})
d.selectors['Patient.age'].setCurrentIndex(1);d.preview();old=editor.client.calls[-1]
d.selectors['Patient.passport'].setCurrentIndex(2);old[1]({'valid':True,'rows':2})
assert not d.validated and not d.apply.isEnabled()
d.preview();latest=editor.client.calls[-1];latest[1]({'job_id':'fake-job','status':'ready','checked':2,'total':2,'applied':0,'errors':[],'error_total':0})
assert d.validated and d.apply.isEnabled()
d.selectors['Patient.reg_date'].setCurrentIndex(3);assert not d.apply.isEnabled();d.preview()
editor.client.calls[-1][2]('Patient.reg_date: required\n'+'details '*2000)
assert not d.apply.isEnabled() and d.validate.isEnabled() and 'reg_date' in d.status.text()
assert len(d.status.text())<500 and len(d.error_details.toPlainText())>10000
assert not d.geometry.isChecked()
d.close()
print('PASS legacy QGIS API decoder; stale validation discarded; edits invalidate apply; long errors retain full details and retry')
