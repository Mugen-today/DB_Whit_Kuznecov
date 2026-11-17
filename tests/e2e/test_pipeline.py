"""An explicit outstanding test, not a fake successful full pipeline."""

import unittest


class FuturePipeline(unittest.TestCase):
    @unittest.skip(
        "Business API, dashboard and QGIS plugin are not implemented in Storage phase"
    )
    def test_import_query_export_sync(self):
        raise NotImplementedError
