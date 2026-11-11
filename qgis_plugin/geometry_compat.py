"""Decode backend geometries using APIs available in QGIS 3.28+. No CRS work here."""
import json
from qgis.core import QgsGeometry,QgsJsonUtils

def decode_geometry(geometry,wkt=None):
    if wkt:
        result=QgsGeometry.fromWkt(wkt)
    elif geometry:
        # geometryFromGeoJson is only available from QGIS 3.36.
        features=QgsJsonUtils.stringToFeatureList(json.dumps({'type':'Feature','properties':{},'geometry':geometry}))
        result=features[0].geometry() if features else QgsGeometry()
    else:return QgsGeometry()
    if result.isNull():raise ValueError('Backend returned an unreadable geometry')
    return result
