"""Real HTTP + MongoDB + PyQGIS regression. Run ONLY in the disposable test database."""

import json
import os
from pathlib import Path
import sys
import tempfile
import time
import uuid
from urllib.request import Request, urlopen
from urllib.error import HTTPError

if os.environ.get("ISOLATED_STORAGE_TEST") != "1":
    raise RuntimeError("Run only in the disposable integration database")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from qgis.PyQt.QtCore import QEventLoop, QTimer
from qgis.PyQt.QtWidgets import QMainWindow, QDoubleSpinBox, QDialog
from qgis.core import QgsApplication, QgsProject, QgsVectorLayer
from qgis.gui import QgsMapCanvas
from qgis_plugin.api_client import GisApiClient
from qgis_plugin.layer_sync import make_layer, export_geopackage
from qgis_plugin.plugin import GisMongoPlugin

BASE = os.environ.get("QGIS_TEST_BACKEND", "http://127.0.0.1:8000")
TOKEN = os.environ["QGIS_USER_TOKEN"]
GUEST = os.environ["QGIS_GUEST_TOKEN"]


def http(method, path, payload=None, token=TOKEN, expected=200):
    data = None if payload is None else json.dumps(payload).encode()
    request = Request(
        BASE + path,
        data=data,
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        response = urlopen(request, timeout=10)
    except HTTPError as error:
        response = error
    with response:
        body = json.load(response)
        assert response.status == expected, (response.status, body)
        return body


app = QgsApplication([], False)
app.initQgis()
client = GisApiClient(BASE, TOKEN)


def qt_request(method, path, payload=None):
    loop = QEventLoop()
    result = []

    def done(data):
        result.append(data)
        loop.quit()

    def failed(message):
        result.append(RuntimeError(message))
        loop.quit()

    client.request(method, path, payload, done, failed)
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(25000)
    loop.exec_()
    timer.stop()
    assert result, "QGIS request timed out"
    if isinstance(result[0], Exception):
        raise result[0]
    return result[0]


try:
    http("GET", "/v1/qgis/points", token="wrong", expected=401)
    payload = {
        "longitude": 30.31,
        "latitude": 59.95,
        "elevation": None,
        "request_id": str(uuid.uuid4()),
    }
    started = time.monotonic()
    first = qt_request("POST", "/v1/qgis/points", payload)
    create_ms = (time.monotonic() - started) * 1000
    again = qt_request("POST", "/v1/qgis/points", payload)
    assert first["id"] == again["id"], "Retry duplicated the document"
    identifier = first["id"]
    http("POST", "/v1/qgis/points", {**payload, "longitude": 31.0}, expected=409)
    for invalid in (
        {**payload, "latitude": 91},
        {**payload, "longitude": True},
        {**payload, "_owner_id": "other"},
    ):
        http("POST", "/v1/qgis/points", invalid, expected=400)
    http("GET", "/v1/qgis/points?after=invalid", expected=400)
    http("GET", "/v1/qgis/points?limit=0", expected=400)
    page = qt_request("GET", "/v1/qgis/points?limit=1")
    assert page["features"][0]["id"] == identifier
    layer = make_layer(page)
    QgsProject.instance().addMapLayer(layer)
    assert layer.isValid() and layer.featureCount() == 1 and layer.readOnly()
    feature = next(layer.getFeatures())
    assert feature["mongo_id"] == identifier
    assert abs(feature.geometry().asPoint().x() - 30.31) < 1e-8
    updated = qt_request(
        "PUT",
        "/v1/qgis/points/" + identifier,
        {"longitude": 30.4, "latitude": 60.0, "elevation": 12.5, "revision": 1},
    )
    assert updated["properties"]["revision"] == 2
    http(
        "PUT",
        "/v1/qgis/points/" + identifier,
        {"longitude": 30.5, "latitude": 60.1, "revision": 1},
        expected=409,
    )
    http(
        "PUT",
        "/v1/qgis/points/" + identifier,
        {"longitude": 30.5, "latitude": 60.1, "revision": 2},
        token=GUEST,
        expected=403,
    )
    guest_page = http("GET", "/v1/qgis/points", token=GUEST)
    assert any(f["id"] == identifier for f in guest_page["features"])
    # Confirm the actual BSON stored by the backend and an owner isolation check.
    from pymongo import MongoClient
    from bson import ObjectId

    connection = MongoClient(
        os.environ.get("MONGO_HOST", "127.0.0.1"),
        27017,
        username="storage_admin",
        password=os.environ["MONGO_ROOT_PASSWORD"],
        authSource="admin",
    )
    db = connection.Schema
    stored = db.Geodata.find_one({"_id": ObjectId(identifier)})
    assert (
        stored["Longitude"] == 30.4
        and stored["Latitude"] == 60.0
        and stored["Elevation"] == 12.5
    )
    assert stored["_owner_id"] == "qgis-user" and stored["qgis_revision"] == 2
    other = db.Geodata.insert_one(
        {"Longitude": 30.7, "Latitude": 60.1, "_owner_id": "other"}
    ).inserted_id
    own = http("GET", "/v1/qgis/points")
    assert str(other) not in {f["id"] for f in own["features"]}
    http(
        "PUT",
        "/v1/qgis/points/" + str(other),
        {"longitude": 1, "latitude": 2, "revision": 0},
        expected=409,
    )
    assert db.Geodata.find_one({"_id": other})["Longitude"] == 30.7
    assert db.cases.count_documents({}) == 1, "Original imported records changed"
    with tempfile.TemporaryDirectory() as folder:
        filename = str(Path(folder) / "points.gpkg")
        export_geopackage(layer, filename)
        ogr = QgsVectorLayer(filename, "GeoPackage", "ogr")
        assert ogr.isValid() and ogr.featureCount() == 1
        del ogr

    class Iface:
        def __init__(self):
            self.window = QMainWindow()
            self.actions = []
            self.canvas = QgsMapCanvas()

        def mainWindow(self):
            return self.window

        def addPluginToMenu(self, menu, action):
            self.actions.append(action)

        def addToolBarIcon(self, action):
            pass

        def removePluginMenu(self, menu, action):
            self.actions.remove(action)

        def removeToolBarIcon(self, action):
            pass

        def setActiveLayer(self, layer):
            pass

        def mapCanvas(self):
            return self.canvas

    iface = Iface()
    plugin = GisMongoPlugin(iface)
    plugin.initGui()
    assert iface.actions
    plugin.open_dialog()
    dialog = plugin.dialog
    dialog.url.setText(BASE)
    dialog.token.setText(TOKEN)
    loop = QEventLoop()
    poll = QTimer()
    poll.timeout.connect(lambda: loop.quit() if dialog.layer is not None else None)
    poll.start(25)
    QTimer.singleShot(15000, loop.quit)
    dialog.reload()
    loop.exec_()
    poll.stop()
    assert (
        dialog.layer is not None and dialog.layer.featureCount() >= 1
    ), dialog.status.text()
    dialog.layer.selectAll()

    # Exercise the real modal edit action with timed input.
    def accept_editor():
        for child in dialog.findChildren(QDialog):
            if child.windowTitle() == "Изменить выбранную точку":
                spins = child.findChildren(QDoubleSpinBox)
                spins[0].setValue(30.45)
                spins[1].setValue(60.05)
                child.accept()

    QTimer.singleShot(100, accept_editor)
    dialog.edit_point()
    loop = QEventLoop()
    timer = QTimer()
    timer.timeout.connect(lambda: loop.quit() if not dialog.client.pending else None)
    timer.start(30)
    QTimer.singleShot(15000, loop.quit)
    loop.exec_()
    timer.stop()
    stored = db.Geodata.find_one({"_id": ObjectId(identifier)})
    assert (
        stored["Longitude"] == 30.45 and stored["qgis_revision"] == 3
    ), dialog.status.text()
    QgsProject.instance().removeMapLayer(dialog.layer_id)
    dialog.edit_point()
    assert "Сначала" in dialog.status.text()
    plugin.unload()
    assert not iface.actions
    connection.close()
    print("QGIS create request completed in %.1f ms on this test host" % create_ms)
    print(
        "PASS PyQGIS networking, point provider, plugin GUI edit -> HTTP -> MongoDB, ownership, guest, revisions, idempotency and GeoPackage/OGR"
    )
finally:
    client.close()
    QgsProject.instance().removeAllMapLayers()
    app.exitQgis()
