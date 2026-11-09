"""QGIS plugin package."""


def classFactory(iface):
    from .plugin import GisMongoPlugin

    return GisMongoPlugin(iface)
