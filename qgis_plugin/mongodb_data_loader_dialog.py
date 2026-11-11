"""Original MongoDB Data Loader window, routed through the backend."""
import json
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QDialog,QVBoxLayout,QFormLayout,QLineEdit,QPushButton,QLabel,QListWidget,QListWidgetItem,QGroupBox,QCheckBox,QSpinBox,QMessageBox,QHBoxLayout,QPlainTextEdit,QComboBox)
from .records_dialog import RecordsDialog

class MongodbDataLoaderDialog(QDialog):
    def __init__(self,iface):
        super().__init__(iface.mainWindow())
        self.setWindowTitle("MongoDB Data Loader")
        self.resize(520,620)
        self.editor=RecordsDialog(iface)
        self._connected=False
        self._updating=False
        self._active_fields=None
        self.setup_interface()
        self.editor.status=self.collections_info

    def setup_interface(self):
        main_layout = QVBoxLayout(self)

        # Подключение
        connection_group = QGroupBox("Подключение через backend")
        connection_layout = QFormLayout(connection_group)

        self.host_input = QLineEdit("127.0.0.1")

        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(8000)

        self.database_input = QLineEdit("Schema")
        self.database_input.setReadOnly(True)
        self.username_input = QComboBox()
        self.username_input.setEditable(True)
        self.username_input.addItems(["qgis-user","guest","analyst","admin"])
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)

        connection_layout.addRow("Хост:", self.host_input)
        connection_layout.addRow("Порт:", self.port_input)
        connection_layout.addRow("База данных:", self.database_input)
        connection_layout.addRow("Пользователь:", self.username_input)
        connection_layout.addRow("API-токен:", self.password_input)

        self.connect_button = QPushButton("Подключиться")
        connection_layout.addRow(self.connect_button)

        main_layout.addWidget(connection_group)

        # Коллекции
        collections_group = QGroupBox("Коллекции базы данных")
        collections_layout = QVBoxLayout(collections_group)

        self.select_all_checkbox = QCheckBox("Выбрать все")
        collections_layout.addWidget(self.select_all_checkbox)

        self.collections_list = QListWidget()
        collections_layout.addWidget(self.collections_list)

        self.collections_info = QLabel(
            "Сначала подключитесь к MongoDB"
        )
        collections_layout.addWidget(self.collections_info)

        main_layout.addWidget(collections_group)

        # Загрузка
        self.load_button = QPushButton(
            "Загрузить выбранные коллекции полностью"
        )
        self.load_button.setEnabled(False)
        main_layout.addWidget(self.load_button)

        row=QHBoxLayout()
        for text,action in (("Следующая страница",self.next_page),("Новая запись",self.create_record),("Изменить выбранную",self.edit_record),("Консоль MongoDB",self.open_console)):
            button=QPushButton(text);button.clicked.connect(action);row.addWidget(button)
            if text=="Новая запись":self.create_button=button
            if text=="Изменить выбранную":self.edit_button=button
        main_layout.addLayout(row)
        gpkg=QPushButton("Загрузить файл .gpkg в MongoDB");gpkg.clicked.connect(self.import_gpkg);main_layout.addWidget(gpkg);self.gpkg_button=gpkg
        self.close_button = QPushButton("Закрыть")
        main_layout.addWidget(self.close_button)

        # Сигналы
        self.connect_button.clicked.connect(self.connect_to_mongodb)
        self.load_button.clicked.connect(self.load_selected_collections)

        self.select_all_checkbox.stateChanged.connect(
            self.select_all_collections
        )

        self.close_button.clicked.connect(self.close)
        self.username_input.currentTextChanged.connect(self.credentials_changed)
        self.password_input.textChanged.connect(self.credentials_changed)
        self.host_input.textChanged.connect(self.credentials_changed)
        self.port_input.valueChanged.connect(self.credentials_changed)
        self.username_input.activated.connect(lambda _:self.connect_to_mongodb())
        self.username_input.lineEdit().editingFinished.connect(self.connect_to_mongodb)
        self.password_input.editingFinished.connect(self.connect_to_mongodb)
        self.set_permissions(False)


    def configure_editor(self):
        host=self.host_input.text().strip()
        if "://" not in host:host="http://"+host
        self.editor.url.setText(host.rstrip("/")+":"+str(self.port_input.value()))
        self.editor.token.setText(self.password_input.text())
        self.editor.username=self.username_input.currentText().strip()
        return self.editor

    def set_permissions(self,write):
        self.load_button.setEnabled(self._connected)
        for widget in (self.create_button,self.edit_button,self.gpkg_button):widget.setEnabled(self._connected and write)

    def fields(self):
        return (self.host_input.text(),self.port_input.value(),self.username_input.currentText(),self.password_input.text())

    def credentials_changed(self,*_):
        if self._updating:return
        if any(b.get('sending') for b in self.editor.bindings.values()):
            if self._active_fields:
                self._updating=True
                host,port,user,token=self._active_fields
                self.host_input.setText(host);self.port_input.setValue(port);self.username_input.setCurrentText(user);self.password_input.setText(token)
                self._updating=False
            self.collections_info.setText("Дождитесь завершения сохранения")
            return
        from qgis.core import QgsProject
        dirty=[QgsProject.instance().mapLayer(i) for i in self.editor.managed_layers.values()]
        if any(l and l.isEditable() and l.isModified() for l in dirty):
            if QMessageBox.question(self,"Смена пользователя","Отменить несохранённые локальные правки и сменить пользователя?",QMessageBox.Yes|QMessageBox.No)!=QMessageBox.Yes:
                if self._active_fields:
                    self._updating=True
                    host,port,user,token=self._active_fields
                    self.host_input.setText(host);self.port_input.setValue(port);self.username_input.setCurrentText(user);self.password_input.setText(token)
                    self._updating=False
                return
        self._connected=False;self.set_permissions(False)
        self.editor.load_generation+=1
        if self.editor.client:self.editor.client.close()
        self.editor.session={}
        for identifier in list(self.editor.managed_layers.values()):
            if QgsProject.instance().mapLayer(identifier):QgsProject.instance().removeMapLayer(identifier)
        self.editor.managed_layers.clear();self.editor.bindings.clear();self.editor.documents={};self.editor.geometry_warnings.clear()
        self.collections_list.clear();self.collections_info.setText("Подключение изменилось. Подтвердите пользователя и API-токен.")

    def connect_to_mongodb(self):
        if not self.password_input.text().strip():return
        editor=self.configure_editor();expected=editor.connection_key();generation=editor.load_generation
        def loaded(data):
            if editor.connection_key()!=expected or editor.load_generation!=generation:return
            self.collections_list.clear()
            for name in sorted(data["collections"]):
                item=QListWidgetItem(name);item.setFlags(item.flags()|Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Unchecked);self.collections_list.addItem(item)
            self.select_all_checkbox.blockSignals(True);self.select_all_checkbox.setChecked(False);self.select_all_checkbox.blockSignals(False)
            self._connected=True;self._active_fields=self.fields();editor.session=data
            self.set_permissions(data["can_write"])
            self.collections_info.setText("Профиль: "+data["role"]+"; владелец: "+data["owner"]+"; коллекций: "+str(self.collections_list.count())+"; backend: "+data.get("backend_version","версия не сообщена — обновите backend вместе с плагином"))
        editor.send("GET","/v1/session",None,loaded)

    def select_all_collections(self,state):
        for i in range(self.collections_list.count()):
            self.collections_list.item(i).setCheckState(Qt.Checked if state==Qt.Checked else Qt.Unchecked)

    def load_selected_collections(self):
        if not self._connected:return
        selected=[self.collections_list.item(i).text() for i in range(self.collections_list.count()) if self.collections_list.item(i).checkState()==Qt.Checked]
        editor=self.configure_editor();generation=editor.load_generation
        results=[];errors=[]
        def next_one(error=None):
            if generation!=editor.load_generation:return
            if error:errors.append(error)
            if not selected:
                self.collections_info.setText("Загрузка завершена: "+str(len(results)-len(errors))+" коллекций; ошибок: "+str(len(errors))+(" — "+"; ".join(errors) if errors else "")+("; предупреждений геометрии: "+str(sum(editor.geometry_warnings.values())) if any(editor.geometry_warnings.values()) else ""))
                return
            name=selected.pop(0);results.append(name);editor.collection.setCurrentText(name)
            editor.load_all(name,next_one)
        next_one()

    def import_gpkg(self):
        from .gpkg_dialog import GpkgDialog
        GpkgDialog(self.configure_editor(),self).exec_()

    def next_page(self):self.configure_editor().next_page()

    def create_record(self):self.configure_editor().create_point()
    def edit_record(self):
        editor=self.configure_editor();editor.api();editor.edit_point()
    def open_console(self):
        from .console_dialog import MongoConsoleDialog
        MongoConsoleDialog(self.configure_editor(),self).exec_()
    def closeEvent(self,event):
        self.editor.close();self.password_input.clear();super().closeEvent(event)
