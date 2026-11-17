import tempfile,unittest,sys,json
from pathlib import Path
from unittest.mock import patch
from openpyxl import Workbook
from backend.app.modules.auto_import import execute
from tests.unit.test_seed_b import Store
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import import_launcher
class ImportCliTests(unittest.TestCase):
 def test_launcher_default_dry_run_explicit_apply_and_readonly_path(self):
  with tempfile.TemporaryDirectory() as td:
   for ext in ('.xlsx','.json'):
    p=Path(td)/('source with spaces'+ext);p.write_text('test')
    for flags,expected in [([], '--dry-run'),(['--dry-run'],'--dry-run'),(['--apply'],'--apply')]:
     with patch.object(import_launcher.subprocess,'run') as run,patch.object(import_launcher.manage,'compose_environment',return_value={}):
      import_launcher.main({ext},[str(p),*flags])
     command=run.call_args.args[0];self.assertEqual(command[-1],expected);self.assertIn(str(p)+':/input/source'+ext+':ro',command);self.assertNotIn('--sheet',command)
 def test_dry_run_all_excel_sheets_never_inserts(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'all.xlsx';b=Workbook();s=b.active;s.title='Patient';s.append(['_id','passport','age','reg_date']);s.append([7,'0007',25,'2026-11-17']);s=b.create_sheet('Geodata');s.append(['_id','Longitude','Latitude']);s.append([8,30,60]);b.save(p);b.close();store=Store()
   state=execute(p,store,Path(td)/'report',apply=False)
   self.assertEqual(state['status'],'dry-run');self.assertEqual(state['documents'],{'Geodata':1,'Patient':1});self.assertFalse(store.db.cols)
   state=execute(p,store,Path(td)/'apply',apply=True);self.assertEqual(state['inserted']['Patient'],1)
 def test_modes_are_mutually_exclusive(self):
  with self.assertRaises(SystemExit):import_launcher.main(argv=['x.xlsx','--dry-run','--apply'])
