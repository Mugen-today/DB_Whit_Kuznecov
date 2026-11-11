import hashlib,json,unittest
from pathlib import Path
class BundledDatasetTests(unittest.TestCase):
    def test_exact_source_and_stable_namespace(self):
        root=Path(__file__).resolve().parents[2]
        manifest=json.loads((root/'data/manifest.json').read_text())
        self.assertEqual(manifest['namespace'],'test-dataset-a')
        part=manifest['part_b']
        self.assertEqual(hashlib.sha256((root/'data'/part['filename']).read_bytes()).hexdigest(),part['sha256'])
        self.assertEqual(hashlib.sha256((root/'data'/manifest['filename']).read_bytes()).hexdigest(),
            'a576414b4d5157c3a209edf94be89c8c2e6de102d9cc20ad0c842c4856fd7fce')
        self.assertEqual(manifest['sha256'],'a576414b4d5157c3a209edf94be89c8c2e6de102d9cc20ad0c842c4856fd7fce')
