"""All-collection QGIS browser and server-validated record editor."""
import json
import uuid
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QComboBox, QPushButton, QDialog, QVBoxLayout, QPlainTextEdit, QLabel
from qgis.core import QgsVectorLayer, QgsField, QgsFeature, QgsGeometry, QgsPointXY, QgsProject
from .plugin import PointDialog

TEMPLATE = {
    "request_id": "",
    "entities": {
        "Geodata": {"Longitude": None, "Latitude": None},
        "Instances": {"date": ""},
        "Patient": {"passport": "", "age": None, "reg_date": ""},
        "Therapy": {"date_start": "", "diagnosis": []}
    }
}

def make_table(page):
    from .layer_records import make_layer
    return make_layer(page)

class RecordsDialog(PointDialog):
    def __init__(self,iface):
        super().__init__(iface)
        self.setWindowTitle('MongoDB — коллекции и связанные записи')
        self.resize(900,450)
        self.documents={}
        self.bindings={}
        self.managed_layers={}
        self.geometry_warnings={}
        self.session={}
        self.load_generation=0
        self.current_collection=None
        self.pending_record=None
        self.collection=QComboBox()
        self.collection.addItems(['Geodata','Patient','Instances','Therapy','Region','Municipality','Settlement',
            'Street','Building','Placement','Reception','Gender','Social_group','Severity','Influence','Foci','Location'])
        self.layout().insertWidget(0,self.collection)
        self.collection.currentTextChanged.connect(self.changed_collection)
        # Existing form fields only belonged to the point-only creation flow.
        for w in (self.longitude,self.latitude,self.height):
            w.hide()
            label=self.layout().itemAt(1).layout().labelForField(w)
            if label: label.hide()
        self.buttons[2].setText('Новый связанный набор')
        self.buttons[3].setText('Редактировать выбранную запись')
        self.status.setText('Выберите коллекцию. Правки отправляются через форму в backend. Новый набор требует все четыре группы.')

    def busy(self,value):
        super().busy(value)
        self.collection.setEnabled(not value)

    def changed_collection(self):
        self.cursor=None
        self.status.setText('Коллекция изменена — нажмите «Загрузить»')

    def load_page(self,cursor):
        self.load_all(self.collection.currentText())

    def load_all(self,name,done=None):
        old=self.managed_layers.get(name)
        layer=QgsProject.instance().mapLayer(old) if old else None
        if layer and layer.isEditable() and layer.isModified():
            from qgis.PyQt.QtWidgets import QMessageBox
            if QMessageBox.question(self,"Перезагрузка","Сбросить несохранённый буфер слоя?",QMessageBox.Yes|QMessageBox.No)!=QMessageBox.Yes:
                if done:done("Перезагрузка отменена")
                return
        generation=self.load_generation
        records=[];features=[];last={}
        def next_page(after=None):
            if generation!=self.load_generation:return
            path='/v1/collections/'+name+'?limit=200'+('&after='+after if after else '')
            def received(page):
                if generation!=self.load_generation:return
                records.extend(page['records']);features.extend(page.get('features',[]));last.update(page)
                self.status.setText(name+': получено '+str(len(records)))
                if page.get('next'):next_page(page['next'])
                else:
                    complete={**last,'records':records,'features':features,'next':None,
                              'schema':self.session.get('collections',{}).get(name,{}).get('schema',{}),
                              'can_write':self.session.get('can_write',False)}
                    self.display_page(complete)
                    if done:done(None)
            def failed(message):
                self.status.setText(name+': '+message)
                if done:done(message)
            try:self.api().request('GET',path,None,received,failed)
            except Exception as exc:failed(str(exc))
        next_page()

    def display_page(self,page):
        from .layer_records import bind,key
        layer=make_table(page)
        old=self.managed_layers.get(page['collection'])
        if old and QgsProject.instance().mapLayer(old):
            QgsProject.instance().removeMapLayer(old);self.bindings.pop(old,None)
        self.layer=layer;self.layer_id=layer.id();self.current_collection=page['collection']
        self.managed_layers[self.current_collection]=layer.id()
        self.documents={key(d):d for d in page['records']}
        self.loaded_identity=self.connection_key();self.cursor=None
        QgsProject.instance().addMapLayer(layer);self.iface.setActiveLayer(layer)
        bind(self,layer,page)
        warnings=sum(bool(item.get('geometry_warning')) for item in page.get('features',[]))
        self.geometry_warnings[self.current_collection]=warnings
        self.status.setText('%s: загружено %d записей%s'%(self.current_collection,len(page['records']),' (пустая таблица)' if not page['records'] else '')+('; предупреждений геометрии: '+str(warnings) if warnings else ''))

    def activate_layer(self):
        layer=self.iface.activeLayer() if hasattr(self.iface,'activeLayer') else self.layer
        if layer and layer.id() in self.bindings:
            self.layer=layer;self.layer_id=layer.id()
            binding=self.bindings[layer.id()]
            self.current_collection=binding['collection'];self.collection.setCurrentText(self.current_collection)
            self.documents=binding['documents'];self.loaded_identity=binding['identity']

    def json_editor(self,title,value):
        dialog=QDialog(self);dialog.setWindowTitle(title);dialog.resize(720,580)
        layout=QVBoxLayout(dialog)
        layout.addWidget(QLabel('Даты: YYYY-MM-DD. diagnosis: список строк. passport: строка. Ссылки создаются сервером.'))
        editor=QPlainTextEdit(json.dumps(value,ensure_ascii=False,indent=2));layout.addWidget(editor)
        save=QPushButton('Проверить и отправить в MongoDB');save.clicked.connect(dialog.accept);layout.addWidget(save)
        if dialog.exec_()!=QDialog.Accepted:return None
        try:return json.loads(editor.toPlainText())
        except ValueError:
            self.status.setText('Некорректный JSON. Данные не отправлены.')
            return None

    def create_point(self):
        value=self.pending_record or json.loads(json.dumps(TEMPLATE))
        if not value['request_id']:value['request_id']=str(uuid.uuid4())
        result=self.json_editor('Новая запись — все четыре группы обязательны',value)
        if result is None:return
        self.pending_record=result
        def saved(data):
            self.pending_record=None
            self.reload()
        self.send('POST','/v1/records',result,saved)

    def edit_point(self):
        self.activate_layer()
        layer=QgsProject.instance().mapLayer(self.layer_id) if self.layer_id else None
        if not layer or self.current_collection!=self.collection.currentText():
            self.status.setText('Загрузите выбранную коллекцию');return
        if self.loaded_identity!=self.connection_key():
            self.status.setText('Подключение изменилось — загрузите данные заново');return
        if layer.isEditable() and layer.isModified():
            self.status.setText('Сначала сохраните или отмените правки таблицы');return
        selected=layer.selectedFeatures()
        if len(selected)!=1:
            self.status.setText('Выберите ровно одну строку в последней загруженной таблице');return
        doc=self.documents[str(selected[0]['_key'])]
        # Display immutable relation fields, then send only changed attributes.
        original={k:v for k,v in doc.items() if k not in ('_id','_key','instance','qgis_revision')}
        edited=self.json_editor('Редактирование '+self.current_collection,original)
        if edited is None:return
        if not isinstance(edited,dict) or set(original)-set(edited):
            self.status.setText('Удаление полей не поддерживается');return
        changes={k:v for k,v in edited.items() if k not in original or original[k]!=v}
        if not changes:
            self.status.setText('Изменений нет');return
        self.send('PATCH','/v1/collections/'+self.current_collection+'/'+doc.get('_key',str(doc['_id'])),
            {'revision':doc['qgis_revision'],'changes':changes},lambda _:self.reload())
