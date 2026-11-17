"""GeoPackage mapping UI; the backend owns validation, CRS and all writes."""
import json,hashlib,csv,os,tempfile
from pathlib import Path
from qgis.PyQt.QtCore import QTimer,QSettings
from qgis.PyQt.QtWidgets import (QDialog,QVBoxLayout,QFormLayout,QComboBox,QPushButton,QLabel,
    QScrollArea,QWidget,QCheckBox,QFileDialog)
TARGETS=['Geodata.Longitude','Geodata.Latitude','Geodata.Elevation','Instances.date',
    'Patient.passport','Patient.age','Patient.reg_date','Therapy.patient','Therapy.date_start','Therapy.diagnosis']
class GpkgDialog(QDialog):
    def __init__(self,editor,parent):
        super().__init__(parent);self.editor=editor;self.info=None;self.selectors={};self.validated=False
        self._generation=0;self._busy=False;self._closed=False;self._signature=None;self._import_payload=None;self._job_id=None;self._upload_state=None;self._restoring=False;self._report_state={};self._local_issues=[]
        self._timer=QTimer(self);self._timer.setSingleShot(True);self._timer.setInterval(700);self._timer.timeout.connect(self.preview)
        self.setWindowTitle('Импорт GeoPackage в MongoDB');self.resize(740,700)
        layout=QVBoxLayout(self)
        self.status=QLabel('Выберите .gpkg. Файл передаётся частями, все строки проверяются и импортируются пакетами без общего лимита строк.');self.status.setWordWrap(True);self.status.setMaximumHeight(110);layout.addWidget(self.status)
        from qgis.PyQt.QtWidgets import QPlainTextEdit
        self.error_details=QPlainTextEdit();self.error_details.setReadOnly(True);self.error_details.setMaximumHeight(110);self.error_details.hide();layout.addWidget(self.error_details)
        self.choose_button=QPushButton('Выбрать файл .gpkg');self.choose_button.clicked.connect(self.choose);layout.addWidget(self.choose_button)
        self.table=QComboBox();layout.addWidget(self.table)
        self.mode=QComboBox();self.mode.addItem('Отдельные коллекции — частичное сопоставление','entities');self.mode.addItem('Полный связанный набор — четыре группы','bundle');layout.addWidget(self.mode)
        self.error_policy=QComboBox();self.error_policy.addItem('Строгий — ошибка строки запрещает запись файла','strict');self.error_policy.addItem('Частичный — загрузить корректные строки, ошибки в отчёт','partial');layout.addWidget(self.error_policy)
        self.report_summary=QLabel();self.report_summary.setWordWrap(True);layout.addWidget(self.report_summary)
        self.report_button=QPushButton('Сохранить полный отчёт CSV');self.report_button.clicked.connect(self.export_report);self.report_button.setEnabled(False);layout.addWidget(self.report_button)
        self.geometry=QCheckBox('Использовать Point геометрию таблицы; CRS преобразует backend');self.geometry.setChecked(True);layout.addWidget(self.geometry)
        self.required_label=QLabel();self.required_label.setWordWrap(True);layout.addWidget(self.required_label)
        scroll=QScrollArea();scroll.setWidgetResizable(True);holder=QWidget();self.form=QFormLayout(holder);scroll.setWidget(holder);layout.addWidget(scroll)
        self.validate=QPushButton('Проверить все строки сейчас');self.validate.clicked.connect(self.preview);layout.addWidget(self.validate)
        self.apply=QPushButton('Загрузить в MongoDB');self.apply.clicked.connect(lambda:self.save(0));layout.addWidget(self.apply);self.apply.setEnabled(False)
        self.resume=QPushButton('Продолжить после прерывания');self.resume.clicked.connect(self.resume_import);layout.addWidget(self.resume)
        identity=editor.connection_key();self._resume_key='gis_mongodb/import/'+hashlib.sha256((identity[0]+'|'+identity[2]).encode()).hexdigest()
        self.table.currentIndexChanged.connect(self.mapping_form)
        self.error_policy.currentIndexChanged.connect(self.invalidate);self.mode.currentIndexChanged.connect(self.invalidate);self.geometry.stateChanged.connect(self.invalidate)
    def signature(self,payload):return json.dumps(payload,sort_keys=True,ensure_ascii=False)
    def controls(self,busy,validation=False):
        self._busy=busy;editable=not busy or validation
        self.resume.setEnabled(not busy) if hasattr(self,"resume") else None
        self.choose_button.setEnabled(not busy);self.validate.setEnabled(not busy and bool(self.info))
        self.table.setEnabled(editable);self.mode.setEnabled(editable);self.error_policy.setEnabled(editable)
        self.report_button.setEnabled(not busy and bool(self._job_id or self._local_issues))
        self.geometry.setEnabled(editable and self.has_geometry())
        for widget in self.selectors.values():widget.setEnabled(editable)
        self.apply.setEnabled(not busy and self.validated)
    def has_geometry(self):
        return bool(self.info and self.table.currentIndex()>=0 and self.info['tables'][self.table.currentIndex()].get('geometry'))
    def request(self,path,payload,callback,validation=False,method="POST"):
        if self._busy:return False
        generation=self._generation;self.error_details.hide();self.controls(True,validation)
        def finish(data=None,error=None):
            if self._closed:return
            self.controls(False)
            if validation and generation!=self._generation:
                self._timer.start();return
            if error:
                self.validated=False;self._signature=None;self.apply.setEnabled(False)
                message=str(error)
                try:diagnostic=json.loads(message)
                except (ValueError,TypeError):diagnostic={'severity':'critical','stage':'network','row':None,'field':None,'reason':message}
                if not isinstance(diagnostic,dict):diagnostic={'reason':message,'stage':'request','severity':'critical'}
                self._local_issues.append(diagnostic);self.report_button.setEnabled(True)
                if not self._job_id:self.report_summary.setText('Этап: '+str(diagnostic.get('stage','request'))+'. Успешно загружено 0 строк / 0 документов.')
                self.error_details.setPlainText(self.format_issue(diagnostic));self.error_details.show()
                self.status.setText('Проверка / загрузка не выполнена: '+message[:350]+('…' if len(message)>350 else ''));return
            callback(data)
        try:self.editor.api().request(method,path,payload,lambda data:finish(data),lambda message:finish(error=message))
        except Exception as exc:finish(error=str(exc))
        return True
    def remember(self):
        QSettings().setValue(self._resume_key,json.dumps({'job_id':self._job_id,'upload':self._upload_state},ensure_ascii=False))
    def choose(self):
        filename,_=QFileDialog.getOpenFileName(self,'GeoPackage','','GeoPackage (*.gpkg)')
        if not filename:return
        self._timer.stop();self.validated=False;self._signature=None;self.apply.setEnabled(False);self._job_id=None
        try:
            stat=Path(filename).stat()
            self._upload_state={'filename':filename,'size':stat.st_size,'mtime':stat.st_mtime_ns};self.remember()
            self.status.setText('Создание сессии передачи файла…')
            def started(data):
                self._upload_state['upload_id']=data['upload_id'];self.remember();self.upload_chunk(data)
            self.request('/v1/gpkg/uploads',{'filename':Path(filename).name,'size':stat.st_size},started)
        except Exception as exc:self.status.setText(str(exc))
    def upload_chunk(self,state):
        if state.get('complete'):self.uploaded(state);return
        try:
            data=self._upload_state;path=Path(data['filename']);stat=path.stat()
            if (stat.st_size,stat.st_mtime_ns)!=(data['size'],data['mtime']):raise ValueError('Исходный файл изменился; выберите его заново')
            offset=state['received'];size=state['size'];identifier=state['upload_id']
            self.status.setText('Передано %d из %d байт'%(offset,size))
            if offset==size:
                self.request('/v1/gpkg/uploads/'+identifier+'/complete',{},self.uploaded);return
            with path.open('rb') as stream:stream.seek(offset);chunk=stream.read(state['chunk_bytes'])
            if not chunk:raise ValueError('Неожиданный конец исходного файла')
            self.request('/v1/gpkg/uploads/'+identifier+'/chunk?offset='+str(offset),chunk,self.upload_chunk,method='PUT')
        except Exception as exc:self.status.setText(str(exc))
    def resume_import(self):
        if self._busy:return
        try:
            saved=json.loads(QSettings().value(self._resume_key,'{}'));self._job_id=saved.get('job_id');self._upload_state=saved.get('upload')
            if self._job_id:
                def loaded(data):
                    if not data.get('upload'):
                        self.show_report(data);self.status.setText('Исходный файл недоступен. Импорт остановлен; полный отчёт можно сохранить.');return
                    self._restoring=True
                    self.uploaded(data['upload']);self._timer.stop()
                    payload=data['payload'];self.table.setCurrentText(payload['table']);self._timer.stop()
                    self.mode.setCurrentIndex(self.mode.findData(payload.get('mode','entities')))
                    self.error_policy.setCurrentIndex(self.error_policy.findData(payload.get('error_policy','strict')))
                    self.geometry.setChecked(payload.get('use_geometry',True) and self.has_geometry())
                    for target,source in payload['mapping'].items():
                        if target in self.selectors:self.selectors[target].setCurrentIndex(self.selectors[target].findData(source))
                    self._timer.stop();self._import_payload=self.payload();self._signature=self.signature(self._import_payload);self._restoring=False
                    self.validation_progress(data,self._signature)
                    if data['status']=='blocked' and data.get('last_error',{}).get('retryable') and data.get('last_error',{}).get('stage')=='validation':
                        self.request('/v1/gpkg/jobs/'+self._job_id+'/validate',{},lambda result:self.validation_progress(result,self._signature),validation=True)
                    if data['status']=='blocked' and data.get('last_error',{}).get('retryable') and data.get('last_error',{}).get('stage')=='write':self.validated=True
                    if data['status'] in ('ready','importing','paused') or data['status']=='blocked' and data.get('last_error',{}).get('retryable') and data.get('last_error',{}).get('stage')=='write':self.save(0)
                self.request('/v1/gpkg/jobs/'+self._job_id,None,loaded,method='GET')
            elif self._upload_state and self._upload_state.get('upload_id'):
                self.request('/v1/gpkg/uploads/'+self._upload_state['upload_id'],None,self.upload_chunk,method='GET')
            else:self.status.setText('Нет сохранённой сессии импорта для этого подключения')
        except Exception as exc:self.status.setText(str(exc))
    def uploaded(self,data):
        self.info=data;self.table.blockSignals(True);self.table.clear()
        for item in data['tables']:self.table.addItem(item['name'])
        self.table.blockSignals(False);self.mapping_form()
    def invalidate(self,*_):
        if not self._restoring:
            self._report_state={};self._local_issues=[];self.report_summary.setText('Новое сопоставление: успешно загружено 0 строк / 0 документов.');self.report_button.setEnabled(False)
            self._job_id=None
            if self._upload_state:self.remember()
        self._generation+=1;self.validated=False;self._signature=None;self.apply.setEnabled(False);self._timer.stop()
        self.show_requirements()
        if self.info:
            self.status.setText('Сопоставление изменено. Автоматическая проверка всех строк…');self._timer.start()
    def show_requirements(self):
        if not self.info:return
        selected={target.split('.')[0] for target,box in self.selectors.items() if box.currentData()}
        if self.has_geometry() and self.geometry.isChecked():selected.add('Geodata')
        if self.mode.currentData()=='bundle':selected.update(('Patient','Instances','Therapy'))
        fields=[]
        for name in sorted(selected):
            for field in self.info.get('requirements',{}).get(name,[]):
                if name=='Geodata' and self.has_geometry() and self.geometry.isChecked():continue
                from_target={'patient':'Patient','therapy':'Therapy','location':'Location','id_instance':'Instances'}.get(field)
                if from_target in selected:continue
                fields.append(name+'.'+field)
        self.required_label.setText('Обязательные атрибуты выбранных коллекций: '+(', '.join(fields) if fields else 'геометрия / требования проверит backend')+'. Остальные сопоставления можно пропустить.')
    def mapping_form(self,*_):
        self._timer.stop()
        while self.form.rowCount():self.form.removeRow(0)
        self.selectors={}
        if not self.info or self.table.currentIndex()<0:return
        self.geometry.blockSignals(True);self.geometry.setChecked(self.has_geometry());self.geometry.setEnabled(self.has_geometry());self.geometry.blockSignals(False)
        meta=self.info['tables'][self.table.currentIndex()]
        for target in self.info.get('targets',TARGETS):
            combo=QComboBox();combo.addItem('— не сопоставлено —','')
            for field in meta['fields']:combo.addItem(field,field)
            combo.currentIndexChanged.connect(self.invalidate);self.form.addRow(target,combo);self.selectors[target]=combo
        self.invalidate()
    def payload(self):
        if not self.info or self.table.currentIndex()<0:raise ValueError('Выберите файл и таблицу')
        return {'upload_id':self.info['upload_id'],'table':self.table.currentText(),'use_geometry':self.has_geometry() and self.geometry.isChecked(),
                'mode':self.mode.currentData(),'error_policy':self.error_policy.currentData(),'mapping':{target:box.currentData() for target,box in self.selectors.items() if box.currentData()}}
    def preview(self):
        if self._closed:return
        self._timer.stop()
        if self._busy:self._timer.start();return
        try:
            payload=self.payload();signature=self.signature(payload);self._import_payload=payload
            self.status.setText('Backend начинает пакетную проверку…')
            def started(data):
                if signature!=self.signature(self.payload()):self.invalidate();return
                self._job_id=data['job_id'];self.remember();self.validation_progress(data,signature)
            self.request('/v1/gpkg/jobs',payload,started,validation=True)
        except Exception as exc:self.status.setText(str(exc));self.apply.setEnabled(False)
    def format_issue(self,data):
        return '%s | Этап: %s | Запись: %s | Поле: %s | %s'%(data.get('severity','error'),data.get('stage','?'),data.get('row') if data.get('row') is not None else '—',data.get('field') or '—',data.get('reason',data.get('detail','')))
    def show_report(self,data):
        self._report_state=data;self.report_button.setEnabled(bool(self._job_id or self._local_issues))
        self.report_summary.setText('Этап: %s. Проверено %d/%d; принято %d; отклонено %d; успешно строк %d; документов подтверждено %d (создано этим заданием %d, повторно использовано %d). Предупреждений %d.'%(data.get('status','?'),data.get('checked',0),data.get('total',0),data.get('valid_rows',0),data.get('failed_rows',0),data.get('successful_rows',0),data.get('documents_present',0),data.get('documents_created_by_job',0),data.get('documents_reused',0),data.get('warning_total',0)))
        preview=data.get('errors',[])
        if preview:
            self.error_details.setPlainText('Предварительный просмотр; полный отчёт доступен в CSV.\n'+'\n'.join(self.format_issue(d) for d in preview));self.error_details.show()
    def validation_progress(self,data,signature):
        if self._closed:return
        if signature!=self.signature(self.payload()):self.invalidate();return
        self.show_report(data)
        self.status.setText('Проверено %d из %d строк'%(data['checked'],data['total']))
        if data['status']=='validating' or data['status']=='blocked' and data.get('last_error',{}).get('retryable') and data.get('last_error',{}).get('stage')=='validation':
            if data['status']=='blocked':
                self.validated=False;self.apply.setEnabled(False);self.status.setText('Критическая ошибка. '+self.format_issue(data['last_error']));return
            self.request('/v1/gpkg/jobs/'+data['job_id']+'/validate',{},lambda result:self.validation_progress(result,signature),validation=True)
        elif data['status'] in ('invalid','blocked','failed'):
            self.validated=False;self.apply.setEnabled(False)
            self.status.setText('Проверка не выполнена. '+self.format_issue(data.get('last_error',{}))[:300])
        else:
            self.validated=True;self._signature=signature;self.apply.setEnabled(True)
            self.status.setText('Проверены все %d строк. Корректных %d, отклонено %d. Можно загрузить.'%(data['total'],data.get('valid_rows',data['total']),data.get('failed_rows',0)) if data['status'] not in ('complete','complete_with_errors') else 'Импорт завершён: успешно %d строк, отклонено %d.'%(data.get('successful_rows',data['applied']),data.get('failed_rows',0)))
    def save(self,offset):
        if self._busy or not self._job_id or not self.validated:return
        if self._signature!=self.signature(self.payload()):self.invalidate();return
        self._timer.stop()
        def saved(data):
            self.show_report(data)
            self.status.setText('Загружено %d из %d строк'%(data['applied'],data['total']))
            if data['status'] in ('complete','complete_with_errors'):
                self.status.setText('Импорт завершён: успешно %d строк, отклонено %d; документов подтверждено %d.'%(data.get('successful_rows',data['applied']),data.get('failed_rows',0),data.get('documents_present',0)))
            elif data['status'] in ('paused','blocked','failed'):
                self.status.setText('Импорт остановлен. '+self.format_issue(data.get('last_error',{}))[:300])
                self.error_details.setPlainText(self.format_issue(data.get('last_error',{})));self.error_details.show();self.apply.setEnabled(False)
            else:self.save(data.get('position',data['applied']))
        self.request('/v1/gpkg/jobs/'+self._job_id+'/apply',{},saved)
    def export_report(self):
        if self._busy:return
        filename,_=QFileDialog.getSaveFileName(self,'Отчёт импорта','','CSV (*.csv)')
        if not filename:return
        destination=Path(filename);temporary=None
        try:
            fd,temporary=tempfile.mkstemp(prefix='.gpkg-report-',dir=str(destination.parent));stream=os.fdopen(fd,'w',encoding='utf-8-sig',newline='')
            writer=csv.writer(stream);writer.writerow(['severity','stage','row','source_key','field','code','reason'])
            def write_item(item):
                cells=[item.get('severity'),item.get('stage'),item.get('row'),json.dumps(item.get('source_key'),ensure_ascii=False),item.get('field'),item.get('code'),item.get('reason',item.get('detail',''))]
                # Spreadsheet formula injection must not turn source keys/reasons into formulas.
                writer.writerow([("'"+v) if isinstance(v,str) and v[:1] in ('=','+','-','@','\t','\r') else v for v in cells])
            def finish():
                for item in self._local_issues:write_item(item)
                stream.flush();os.fsync(stream.fileno());stream.close();os.replace(temporary,destination);self.status.setText('Полный отчёт сохранён: '+str(destination))
            def failed(message):
                stream.close();Path(temporary).unlink(missing_ok=True);self.status.setText('Не удалось сохранить отчёт: '+str(message));self.controls(False)
            def page(after=0):
                self.controls(True)
                def received(data):
                    if after==0:write_item({'severity':'info','stage':'summary','reason':json.dumps(data['summary'],ensure_ascii=False)})
                    for item in data['issues']:write_item(item)
                    if data['next'] is not None:page(data['next'])
                    else:self.controls(False);finish()
                self.editor.api().request('GET','/v1/gpkg/jobs/'+self._job_id+'/report?limit=100&after='+str(after),None,received,failed)
            if self._job_id:page()
            else:
                write_item({'severity':'info','stage':'summary','reason':json.dumps(self._report_state,ensure_ascii=False)});finish()
        except Exception as exc:
            if temporary:Path(temporary).unlink(missing_ok=True)
            self.status.setText('Не удалось сохранить отчёт: '+str(exc));self.controls(False)
    def closeEvent(self,event):
        self._closed=True;self._timer.stop();self._generation+=1;super().closeEvent(event)
