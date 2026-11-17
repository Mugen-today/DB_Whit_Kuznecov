"""Empty installation must never depend on user datasets."""
import ast,importlib.util,io,unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
class InitializationTests(unittest.TestCase):
    def test_up_never_builds_or_runs_import(self):
        spec=importlib.util.spec_from_file_location('empty_manager',ROOT/'scripts/manage.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        with patch.object(Path,'is_file',return_value=True),patch.object(m.shutil,'which',return_value='docker'),patch.object(m,'prevent_double_mount'),patch.object(m,'execute') as run:
            self.assertEqual(m.main(['up','--connections']),0)
        commands=[c.args[0] for c in run.call_args_list]
        self.assertTrue(any('backend' in c and '--build' in c for c in commands))
        self.assertFalse(any('excel-import' in c or 'app.modules.seed' in c for c in commands))
        self.assertTrue(any('/opt/storage/provision.js' in c for c in commands))
        self.assertFalse(any('/opt/storage/geospatial-index.js' in c for c in commands))
    def test_no_bundled_sources_or_implicit_mount(self):
        self.assertFalse((ROOT/'data').exists())
        compose=(ROOT/'docker-compose.yml').read_text();self.assertNotIn('./data:',compose)
        self.assertNotIn('app.modules.seed',compose)
        for p in ROOT.rglob('*'):
            if p.is_file():self.assertNotIn(p.suffix.lower(),('.xlsx','.gpkg','.xls'))
    def test_seed_requires_explicit_path_before_database(self):
        from backend.app.modules import seed,import_excel
        with patch('sys.argv',['seed']),redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:import_excel.main()
        self.assertEqual(caught.exception.code,2)
