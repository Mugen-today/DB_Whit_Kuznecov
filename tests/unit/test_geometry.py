import unittest
from backend.app.modules.geometry import normalize
from backend.app.modules.qgis_data import ApiError
class GeometryTests(unittest.TestCase):
    def test_coordinates(self):
        self.assertEqual(normalize({'Longitude':0,'Latitude':0})['geometry'],{'type':'Point','coordinates':[0.0,0.0]})
    def test_geometry(self):
        self.assertEqual(normalize({'geometry':{'type':'Point','coordinates':[30,60]}})['Longitude'],30)
    def test_conflict_and_invalid(self):
        for value in [
            {'Longitude':0,'Latitude':0,'geometry':{'type':'Point','coordinates':[1,0]}},
            {'geometry':{'type':'Point','coordinates':[0,91]}},
            {'geometry':{'type':'Point','coordinates':[True,0]}},
            {'geometry':{'type':'Polygon','coordinates':[]}}]:
            with self.assertRaises(ApiError):normalize(value)
