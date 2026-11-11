"""MongoDB expression editor. Query text is sent verbatim, never executed in QGIS."""
import json
from qgis.PyQt.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QComboBox,QPlainTextEdit,QPushButton,QLabel
EXAMPLES=[('find','db.Patient.find({age: {$gte: 40}}).sort({age: -1}).limit(20)'),
 ('aggregate','db.Instances.aggregate([{$group: {_id: "$patient", n: {$sum: 1}}}, {$sort: {n: -1}}])'),
 ('countDocuments','db.Patient.countDocuments({age: {$gte: 40}})'),
 ('distinct','db.Patient.distinct("age")'),
 ('Пространственный поиск','db.Geodata.find({geometry: {$near: {$geometry: {type: "Point", coordinates: [30, 60]}, $maxDistance: 10000}}})')]
class MongoConsoleDialog(QDialog):
    def __init__(self,editor,parent=None):
        super().__init__(parent);self.editor=editor;self.cursor=None;self._serial=0
        self.setWindowTitle('Консоль MongoDB');self.resize(820,620)
        layout=QVBoxLayout(self)
        hint=QLabel('Запросы MongoDB: db.Patient.find(...), aggregate, countDocuments, distinct.\nПоддержаны db["Patient"], db.getCollection("Patient"), ObjectId, ISODate, /regex/i. Это не произвольный Python-код.');hint.setWordWrap(True);layout.addWidget(hint)
        row=QHBoxLayout();self.examples=QComboBox()
        for name,code in EXAMPLES:self.examples.addItem(name,code)
        insert=QPushButton('Вставить пример');insert.clicked.connect(lambda:self.code.setPlainText(self.examples.currentData()));row.addWidget(self.examples);row.addWidget(insert);layout.addLayout(row)
        self.code=QPlainTextEdit('db.Patient.find({})');layout.addWidget(self.code)
        self.run=QPushButton('Выполнить запрос');self.run.clicked.connect(self.execute);layout.addWidget(self.run)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        self.output=QPlainTextEdit();self.output.setReadOnly(True);layout.addWidget(self.output)
        self.next=QPushButton('Следующая страница результата');self.next.setEnabled(False);self.next.clicked.connect(self.continue_query);layout.addWidget(self.next)
    def execute(self):
        code=self.code.toPlainText()
        if not code.strip():self.status.setText('Введите запрос');return
        self.cursor=None;self._serial+=1;self.send({'code':code})
    def continue_query(self):
        if self.cursor:self.send({'cursor':self.cursor})
    def send(self,payload):
        serial=self._serial;identity=self.editor.connection_key();self.run.setEnabled(False);self.next.setEnabled(False);self.status.setText('Backend выполняет запрос…')
        def active():return serial==self._serial and identity==self.editor.connection_key()
        def received(data):
            if not active():return
            self.run.setEnabled(True);self.cursor=data.get('cursor');self.next.setEnabled(bool(self.cursor))
            self.output.setPlainText(json.dumps(data,ensure_ascii=False,indent=2))
            self.status.setText('Получено строк: '+str(len(data.get('records',[])))+('. Есть следующая страница.' if self.cursor else '. Запрос завершён.') if 'records' in data else 'Запрос выполнен')
        def failed(message):
            if not active():return
            self.run.setEnabled(True);self.cursor=None;self.next.setEnabled(False);self.status.setText('Ошибка запроса: '+str(message))
        try:self.editor.api().request('POST','/v1/console',payload,received,failed)
        except Exception as exc:failed(str(exc))
    def closeEvent(self,event):self._serial+=1;super().closeEvent(event)
