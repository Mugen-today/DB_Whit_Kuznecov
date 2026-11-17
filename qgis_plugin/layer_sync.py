"""Translate the bounded backend GeoJSON page into a QGIS point provider."""

from qgis.PyQt.QtCore import QVariant
from qgis.core import (
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsVectorLayer,
    QgsVectorFileWriter,
    QgsProject,
)


def make_layer(page):
    layer = QgsVectorLayer("Point?crs=EPSG:4326", "MongoDB Geodata", "memory")
    if not layer.isValid():
        raise ValueError("Cannot create QGIS point layer")
    provider = layer.dataProvider()
    provider.addAttributes(
        [
            QgsField("mongo_id", QVariant.String),
            QgsField("revision", QVariant.Int),
            QgsField("elevation", QVariant.Double),
        ]
    )
    layer.updateFields()
    features = []
    for item in page["features"]:
        point = item["geometry"]["coordinates"]
        values = item["properties"]
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(*point[:2])))
        feature.setAttributes(
            [values["mongo_id"], values["revision"], values.get("elevation")]
        )
        features.append(feature)
    ok, _ = provider.addFeatures(features)
    if not ok:
        raise ValueError("QGIS provider could not add point features")
    layer.updateExtents()
    layer.setReadOnly(True)
    layer.setCustomProperty("gis_mongodb/backend_layer", True)
    return layer


def export_geopackage(layer, filename):
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = "mongodb_geodata"
    options.fileEncoding = "UTF-8"
    result = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, filename, QgsProject.instance().transformContext(), options
    )
    if result[0] != QgsVectorFileWriter.NoError:
        raise ValueError("GeoPackage export failed: " + str(result[1]))
