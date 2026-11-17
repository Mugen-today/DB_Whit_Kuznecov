"""Installable QGIS interface to the backend point API."""

import uuid
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import (
    QAction,
    QDialog,
    QFormLayout,
    QLineEdit,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QDoubleSpinBox,
    QFileDialog,
    QMessageBox,
)
from qgis.core import QgsProject, QgsVariantUtils
from .api_client import GisApiClient
from .layer_sync import make_layer, export_geopackage


class GisMongoPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.dialog = None
        self.action = None

    def initGui(self):
        self.action = QAction("MongoDB через backend", self.iface.mainWindow())
        self.action.triggered.connect(self.open_dialog)
        self.iface.addPluginToMenu("GIS MongoDB", self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        if self.dialog:
            self.dialog.close()
            self.dialog.deleteLater()
            self.dialog = None
        if self.action:
            self.iface.removePluginMenu("GIS MongoDB", self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action.deleteLater()
            self.action = None

    def open_dialog(self):
        if self.dialog is None:
            from .records_dialog import RecordsDialog
            self.dialog = RecordsDialog(self.iface)
        self.dialog.show()
        self.dialog.raise_()


class PointDialog(QDialog):
    def __init__(self, iface):
        super().__init__(iface.mainWindow())
        self.iface = iface
        self.client = None
        self.layer = None
        self.layer_id = None
        self.loaded_identity = None
        self.cursor = None
        self.identity = None
        self.retry_create = None
        self.setWindowTitle("MongoDB — точки Geodata")
        self.resize(560, 300)
        self.url = QLineEdit(
            QSettings().value("gis_mongodb/url", "http://127.0.0.1:8000")
        )
        self.token = QLineEdit()
        self.token.setEchoMode(QLineEdit.Password)
        self.status = QLabel("Введите API-токен из .env backend")
        self.status.setWordWrap(True)
        self.longitude = QDoubleSpinBox()
        self.longitude.setRange(-180, 180)
        self.latitude = QDoubleSpinBox()
        self.latitude.setRange(-90, 90)
        for spin in (self.longitude, self.latitude):
            spin.setDecimals(8)
        self.longitude.setValue(30.3)
        self.latitude.setValue(59.94)
        self.height = QLineEdit()
        self.height.setPlaceholderText("Необязательно")
        form = QFormLayout()
        for label, widget in (
            ("Backend URL", self.url),
            ("API-токен", self.token),
            ("Долгота WGS84", self.longitude),
            ("Широта WGS84", self.latitude),
            ("Высота", self.height),
        ):
            form.addRow(label, widget)
        self.buttons = []
        row = QHBoxLayout()
        for title, action in (
            ("Загрузить", self.reload),
            ("Следующая страница", self.next_page),
            ("Создать точку", self.create_point),
            ("Изменить выбранную", self.edit_point),
            ("GeoPackage", self.export),
        ):
            button = QPushButton(title)
            button.clicked.connect(action)
            self.buttons.append(button)
            row.addWidget(button)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(row)
        layout.addWidget(self.status)

    def connection_key(self):
        return (self.url.text(),self.token.text(),getattr(self,"username",""))

    def api(self):
        identity = self.connection_key()
        if identity != self.identity:
            if self.client:
                self.client.close()
            self.client = GisApiClient(*identity)
            self.identity = identity
            self.retry_create = None
        QSettings().setValue("gis_mongodb/url", self.url.text())
        return self.client

    def busy(self, value):
        for widget in self.buttons + [self.url, self.token]:
            widget.setEnabled(not value)

    def send(self, method, path, payload, callback):
        try:
            client = self.api()
            self.busy(True)

            def success(data):
                self.busy(False)
                callback(data)

            def failure(message):
                self.busy(False)
                self.status.setText(message)

            client.request(method, path, payload, success, failure)
        except Exception as error:
            self.busy(False)
            self.status.setText(str(error))

    def reload(self):
        self.load_page("")

    def next_page(self):
        if self.cursor:
            self.load_page(self.cursor)
        else:
            self.status.setText(
                "Следующей страницы нет. Нажмите «Загрузить» для обновления"
            )

    def load_page(self, cursor):
        path = "/v1/qgis/points?limit=200" + ("&after=" + cursor if cursor else "")

        self.send("GET", path, None, self.display_page)

    def display_page(self, page):
        layer = make_layer(page)
        if self.layer_id and QgsProject.instance().mapLayer(self.layer_id):
            QgsProject.instance().removeMapLayer(self.layer_id)
        self.layer = layer
        self.layer_id = layer.id()
        self.loaded_identity = self.identity
        QgsProject.instance().addMapLayer(layer)
        self.iface.setActiveLayer(layer)
        if layer.featureCount():
            self.iface.mapCanvas().setExtent(layer.extent())
            self.iface.mapCanvas().refresh()
        self.cursor = page.get("next")
        self.status.setText(
            "Загружено %d точек. Пропущено без координат %d. Роль %s"
            % (layer.featureCount(), page.get("skipped", 0), page["role"])
        )

    def saved_point(self, feature):
        self.display_page({"features": [feature], "role": "user", "next": None})
        self.status.setText(
            "Точка сохранена в MongoDB. «Загрузить» вернёт общий список"
        )

    def values(self):
        return {
            "longitude": self.longitude.value(),
            "latitude": self.latitude.value(),
            "elevation": (
                float(self.height.text()) if self.height.text().strip() else None
            ),
        }

    def create_point(self):
        try:
            values = self.values()
            self.api()
            if not self.retry_create or self.retry_create[0] != values:
                self.retry_create = (values, str(uuid.uuid4()))
            payload = {**values, "request_id": self.retry_create[1]}

            def saved(feature):
                self.retry_create = None
                self.saved_point(feature)

            self.send("POST", "/v1/qgis/points", payload, saved)
        except Exception as error:
            self.status.setText(str(error))

    def edit_point(self):
        self.layer = (
            QgsProject.instance().mapLayer(self.layer_id) if self.layer_id else None
        )
        if not self.layer:
            self.status.setText(
                "Сначала загрузите слой и выберите одну точку инструментом QGIS"
            )
            return
        if self.connection_key() != self.loaded_identity:
            self.status.setText(
                "Подключение изменилось. Загрузите слой заново перед редактированием"
            )
            return
        selected = self.layer.selectedFeatures()
        if len(selected) != 1:
            self.status.setText("Выберите ровно одну точку в слое MongoDB Geodata")
            return
        feature = selected[0]
        point = feature.geometry().asPoint()
        editor = QDialog(self)
        editor.setWindowTitle("Изменить выбранную точку")
        lon, lat = QDoubleSpinBox(), QDoubleSpinBox()
        lon.setRange(-180, 180)
        lat.setRange(-90, 90)
        for spin in (lon, lat):
            spin.setDecimals(8)
        lon.setValue(point.x())
        lat.setValue(point.y())
        elevation = feature["elevation"]
        height = QLineEdit("" if QgsVariantUtils.isNull(elevation) else str(elevation))
        form = QFormLayout(editor)
        form.addRow("Долгота", lon)
        form.addRow("Широта", lat)
        form.addRow("Высота", height)
        save = QPushButton("Сохранить в MongoDB")
        save.clicked.connect(editor.accept)
        form.addRow(save)
        if editor.exec_() != QDialog.Accepted:
            return
        try:
            payload = {
                "longitude": lon.value(),
                "latitude": lat.value(),
                "elevation": float(height.text()) if height.text().strip() else None,
                "revision": feature["revision"],
            }
            self.send(
                "PUT",
                "/v1/qgis/points/" + feature["mongo_id"],
                payload,
                self.saved_point,
            )
        except Exception as error:
            self.status.setText(str(error))

    def export(self):
        self.layer = (
            QgsProject.instance().mapLayer(self.layer_id) if self.layer_id else None
        )
        if not self.layer:
            return
        filename, _ = QFileDialog.getSaveFileName(
            self, "GeoPackage для DB Manager", "", "GeoPackage (*.gpkg)"
        )
        if not filename:
            return
        if not filename.lower().endswith(".gpkg"):
            filename += ".gpkg"
        try:
            export_geopackage(self.layer, filename)
            self.status.setText(
                "Сохранена текущая страница. Откройте GeoPackage через Browser или DB Manager"
            )
        except Exception as error:
            self.status.setText(str(error))

    def closeEvent(self, event):
        if self.client:
            self.client.close()
        self.token.clear()
        self.client = None
        self.identity = None
        super().closeEvent(event)
