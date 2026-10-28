"""Administrative views for account activation, device sessions, and custom schemas."""
import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QInputDialog,
    QLabel, QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget, QHeaderView,
)
from client.ui.data_pages import display_value
from client.ui.forms import RecordDialog


class SessionsPage(QFrame):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.records = []
        self.setObjectName("Card")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QVBoxLayout(self); layout.setContentsMargins(18,18,18,18); layout.setSpacing(12)
        header=QHBoxLayout(); texts=QVBoxLayout()
        title=QLabel("نشست‌ها و فعال‌سازی دستگاه‌ها");title.setObjectName("PageTitle")
        sub=QLabel("درخواست‌های ورود جدید در این صفحه تأیید یا لغو می‌شوند. لغو نشست فوراً دسترسی API آن را قطع می‌کند.")
        sub.setObjectName("PageSubtitle");sub.setWordWrap(True)
        texts.addWidget(title);texts.addWidget(sub);header.addLayout(texts,1)
        self.refresh_button=QPushButton("↻ بازخوانی");self.refresh_button.clicked.connect(self.refresh)
        self.revoke_all_button=QPushButton("لغو همه نشست‌ها");self.revoke_all_button.setObjectName("DangerButton")
        self.revoke_all_button.clicked.connect(self.revoke_all)
        header.addWidget(self.refresh_button);header.addWidget(self.revoke_all_button);layout.addLayout(header)

        filters=QHBoxLayout()
        self.state_filter=QComboBox()
        for label,state in [("همه نشست‌ها","all"),("در انتظار تأیید","pending"),("فعال","active"),
                            ("لغوشده","revoked"),("منقضی","expired")]:
            self.state_filter.addItem(label,state)
        self.state_filter.currentIndexChanged.connect(self.refresh)
        self.search=QLineEdit();self.search.setPlaceholderText("فیلتر نام کاربری");self.search.returnPressed.connect(self.refresh)
        self.search_button=QPushButton("اعمال فیلتر");self.search_button.clicked.connect(self.refresh)
        filters.addWidget(self.state_filter);filters.addWidget(self.search,1);filters.addWidget(self.search_button)
        layout.addLayout(filters)

        self.table=QTableWidget(0,8)
        self.table.setHorizontalHeaderLabels(["شناسه","وضعیت","کاربر","دستگاه","نشانی","ایجاد","آخرین فعالیت","انقضا"])
        self.table.setColumnHidden(0,True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True);self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._update_actions)
        layout.addWidget(self.table,1)
        actions=QHBoxLayout()
        self.activate_button=QPushButton("✓  تأیید و فعال‌سازی");self.activate_button.setObjectName("PrimaryButton")
        self.activate_button.clicked.connect(self.activate_selected)
        self.revoke_button=QPushButton("لغو نشست انتخاب‌شده");self.revoke_button.setObjectName("DangerButton")
        self.revoke_button.clicked.connect(self.revoke_selected)
        actions.addWidget(self.activate_button);actions.addWidget(self.revoke_button);actions.addStretch(1)
        layout.addLayout(actions)
        self.pending_note=QLabel("حساب‌هایی که گزینهٔ «تأیید مدیر برای ورود هر دستگاه» را دارند، تا تأیید این صفحه به API دسترسی نخواهند داشت.")
        self.pending_note.setObjectName("StatusPill");self.pending_note.setWordWrap(True);layout.addWidget(self.pending_note)

    def _update_actions(self):
        record = self.selected()
        pending = bool(record and record.get("status") == "pending")
        active = bool(record and record.get("status") == "active")
        self.activate_button.setEnabled(pending)
        self.revoke_button.setEnabled(pending or active)

    def refresh(self):
        if self.window.api is None:return
        state=self.state_filter.currentData();query=self.search.text().strip() or None
        self.window.run_api(lambda:self.window.api.list_admin_sessions(state,q=query),self.populate,busy=self.refresh_button)

    def populate(self, records):
        self.records=list(records or []);self.table.setRowCount(0)
        for row,record in enumerate(self.records):
            self.table.insertRow(row)
            values=[record["id"],display_value("status",record["status"]),record["username"],record["client_name"],
                    record.get("remote_addr"),record["created_at"],record.get("last_seen_at"),record["expires_at"]]
            for col,value in enumerate(values):
                item=QTableWidgetItem("—" if value is None else str(value))
                if col==0:item.setData(Qt.ItemDataRole.UserRole,record)
                self.table.setItem(row,col,item)
        chosen=self.selected()
        pending=bool(chosen and chosen.get("status")=="pending")
        active=bool(chosen and chosen.get("status")=="active")
        self.activate_button.setEnabled(pending)
        self.revoke_button.setEnabled(pending or active)

    def selected(self):
        row=self.table.currentRow();item=self.table.item(row,0) if row>=0 else None
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def activate_selected(self):
        record=self.selected()
        if not record:self.window.show_error("ابتدا یک نشست در انتظار تأیید را انتخاب کنید.");return
        self.window.run_api(lambda:self.window.api.activate_session(record["id"]),lambda _r:self._finished("نشست دستگاه فعال شد."),busy=self.activate_button)

    def revoke_selected(self):
        record=self.selected()
        if not record:self.window.show_error("ابتدا یک نشست را انتخاب کنید.");return
        answer=QMessageBox.question(self,"لغو نشست","دسترسی دستگاه «{}» فوراً قطع شود؟".format(record["client_name"]),
                    QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
        if answer!=QMessageBox.StandardButton.Yes:return
        self.window.run_api(lambda:self.window.api.revoke_session(record["id"]),lambda _r:self._finished("نشست لغو شد."),busy=self.revoke_button)

    def revoke_all(self):
        answer=QMessageBox.question(self,"لغو همه نشست‌ها","تمام نشست‌های فعال و در انتظار تأیید خاتمه یابند؟ حتی مدیر باید دوباره وارد شود.",
                    QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
        if answer!=QMessageBox.StandardButton.Yes:return
        self.window.run_api(self.window.api.revoke_all_sessions,lambda result:self._revoked_all(result))

    def _revoked_all(self,result):
        self.window.set_status("{} نشست لغو شد؛ برای ادامه دوباره وارد شوید.".format(result.get("revoked_count",0)))
        QMessageBox.information(self,"نشست‌ها","همهٔ نشست‌ها لغو شدند. این برنامه هم باید دوباره وارد شود.")
        self.window.force_logout()
    
    def _finished(self,message):
        self.window.set_status(message);self.refresh();self.window.refresh_dashboard_data()

    def currentChanged(self):
        self.populate(self.records)


class SchemaPage(QFrame):
    def __init__(self, window):
        super().__init__()
        self.window=window;self.entities=[];self.fields=[];self.records=[];self.selected_record_id=None
        self.setObjectName("Card");self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout=QVBoxLayout(self);layout.setContentsMargins(18,18,18,18);layout.setSpacing(12)
        h=QLabel("فیلدها و مدل‌های سفارشی");h.setObjectName("PageTitle")
        sub=QLabel("تعریف فیلدهای تکمیلی برای مدل‌های اصلی یا ساخت مدل سفارشی؛ اعتبارسنجی مقادیر در سرور انجام می‌شود.")
        sub.setObjectName("PageSubtitle");sub.setWordWrap(True);layout.addWidget(h);layout.addWidget(sub)
        tools=QHBoxLayout()
        self.entity_combo=QComboBox();self.entity_combo.setMinimumWidth(260)
        self.entity_combo.currentIndexChanged.connect(self.refresh_details)
        self.new_model_button=QPushButton("＋ مدل سفارشی");self.new_model_button.clicked.connect(self.create_model_field)
        self.add_field_button=QPushButton("تعریف فیلد");self.add_field_button.clicked.connect(self.add_field)
        self.refresh_button=QPushButton("↻ بازخوانی");self.refresh_button.clicked.connect(self.refresh_entities)
        tools.addWidget(QLabel("مدل"));tools.addWidget(self.entity_combo,1);tools.addWidget(self.refresh_button)
        tools.addWidget(self.add_field_button);tools.addWidget(self.new_model_button);layout.addLayout(tools)

        split=QSplitter(Qt.Orientation.Horizontal)
        field_container=QWidget();field_layout=QVBoxLayout(field_container)
        field_layout.addWidget(QLabel("تعریف فیلدها"))
        self.field_table=QTableWidget(0,4);self.field_table.setHorizontalHeaderLabels(["کلید","عنوان","نوع","اجباری"])
        self.field_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        field_layout.addWidget(self.field_table)
        record_container=QWidget();record_layout=QVBoxLayout(record_container)
        record_layout.addWidget(QLabel("رکوردها"))
        self.record_table=QTableWidget(0,2);self.record_table.setHorizontalHeaderLabels(["شناسه","عنوان"])
        self.record_table.setColumnHidden(0,True);self.record_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.record_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.record_table.itemSelectionChanged.connect(self.load_values);record_layout.addWidget(self.record_table)
        split.addWidget(field_container);split.addWidget(record_container);split.setSizes([1,1]);layout.addWidget(split,2)

        lay=QHBoxLayout();lay.addWidget(QLabel("مقادیر سفارشی (JSON)"));lay.addStretch(1)
        self.save_values_button=QPushButton("ذخیره مقادیر");self.save_values_button.setObjectName("PrimaryButton")
        self.save_values_button.clicked.connect(self.save_values)
        self.create_record_button=QPushButton("ساخت رکورد");self.create_record_button.clicked.connect(self.create_record)
        self.delete_record_button=QPushButton("حذف رکورد");self.delete_record_button.setObjectName("DangerButton")
        self.delete_record_button.clicked.connect(self.delete_record)
        lay.addWidget(self.create_record_button);lay.addWidget(self.delete_record_button);lay.addWidget(self.save_values_button);layout.addLayout(lay)
        self.editor=QTextEdit();self.editor.setPlaceholderText('{"reference_code": "ABC-123"}');layout.addWidget(self.editor,1)

    def refresh_entities(self):
        if self.window.api is None:return
        self.window.run_api(self.window.api.list_schema_entities,self._entities_loaded,busy=self.refresh_button)

    def _entities_loaded(self,entities):
        previous=self.entity_combo.currentData();self.entities=entities or []
        self.entity_combo.blockSignals(True);self.entity_combo.clear()
        for entity in self.entities:self.entity_combo.addItem("{} · {}".format(entity.get("label"),entity.get("key")),entity.get("key"))
        if previous:
            index=self.entity_combo.findData(previous)
            if index>=0:self.entity_combo.setCurrentIndex(index)
        self.entity_combo.blockSignals(False);self.refresh_details()

    def entity_key(self):
        return self.entity_combo.currentData()

    def refresh_details(self,*_):
        key=self.entity_key()
        if not key or not self.window.api:return
        self.window.run_api(lambda:(self.window.api.list_schema_fields(key),self.window.api.list_schema_records(key)),
                            self._details_loaded)

    def _details_loaded(self,result):
        self.fields,self.records=result
        self.field_table.setRowCount(0)
        for row,field in enumerate(self.fields):
            self.field_table.insertRow(row)
            for col,value in enumerate((field["key"],field["label"],field["type"],"بله" if field["required"] else "خیر")):
                self.field_table.setItem(row,col,QTableWidgetItem(str(value)))
        self.record_table.setRowCount(0)
        for row,record in enumerate(self.records):
            self.record_table.insertRow(row)
            for col,key in enumerate(("id","label")):
                item=QTableWidgetItem(str(record.get(key,"")))
                if col==0:item.setData(Qt.ItemDataRole.UserRole,record)
                self.record_table.setItem(row,col,item)
        current=next((e for e in self.entities if e.get("key")==self.entity_key()),{})
        is_custom=not bool(current.get("builtin"))
        self.create_record_button.setVisible(is_custom);self.delete_record_button.setVisible(is_custom)
        self.editor.clear();self.selected_record_id=None

    def add_field(self):
        entity=self.entity_key()
        if not entity:self.window.show_error("ابتدا مدل را انتخاب کنید.");return
        key,ok=QInputDialog.getText(self,"تعریف فیلد","کلید انگلیسی (snake_case):")
        if not ok or not key.strip():return
        label,ok=QInputDialog.getText(self,"تعریف فیلد","عنوان فارسی:")
        if not ok or not label.strip():return
        kind,ok=QInputDialog.getItem(self,"نوع داده","نوع:",["text","integer","decimal","boolean","date"],0,False)
        if not ok:return
        required=QMessageBox.question(self,"فیلد اجباری","مقدار این فیلد اجباری باشد؟",
                    QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)==QMessageBox.StandardButton.Yes
        current=next((e for e in self.entities if e.get("key")==entity),{})
        self._register_field(entity,key.strip(),label.strip(),kind,required,current.get("label",""))

    def create_model_field(self):
        model_key,ok=QInputDialog.getText(self,"مدل سفارشی","کلید انگلیسی مدل (snake_case):")
        if not ok or not model_key.strip():return
        model_label,ok=QInputDialog.getText(self,"مدل سفارشی","عنوان فارسی مدل:")
        if not ok or not model_label.strip():return
        field_key,ok=QInputDialog.getText(self,"اولین فیلد","کلید فیلد انگلیسی:")
        if not ok or not field_key.strip():return
        field_label,ok=QInputDialog.getText(self,"اولین فیلد","عنوان فارسی فیلد:")
        if not ok or not field_label.strip():return
        kind,ok=QInputDialog.getItem(self,"نوع داده","نوع:",["text","integer","decimal","boolean","date"],0,False)
        if not ok:return
        self._register_field(model_key.strip(),field_key.strip(),field_label.strip(),kind,False,model_label.strip())

    def _register_field(self,entity,key,label,kind,required,model_label):
        row={"model_key":entity,"model_label":model_label,"field_key":key,"field_label":label,
             "field_type":kind,"is_required":required}
        self.window.run_api(lambda:self.window.api.register_schema_fields([row]),lambda _r:self._schema_saved(),busy=self.add_field_button)

    def create_record(self):
        entity=self.entity_key()
        if not entity or not self.fields:return
        fields=[{"key":f["key"],"label":f["label"],"kind":{"decimal":"number","boolean":"bool"}.get(f["type"],f["type"]),
                 "required":f["required"]} for f in self.fields]
        dialog=RecordDialog("رکورد سفارشی",fields,parent=self)
        if dialog.exec()!=dialog.DialogCode.Accepted:return
        try:values=dialog.values()
        except ValueError as exc:self.window.show_error(exc);return
        self.window.run_api(lambda:self.window.api.create_custom_record(entity,values),lambda _r:self._schema_saved())

    def load_values(self):
        row=self.record_table.currentRow()
        item=self.record_table.item(row,0) if row>=0 else None
        if item is None:return
        record=item.data(Qt.ItemDataRole.UserRole)
        self.selected_record_id=record["id"];entity=self.entity_key()
        self.window.run_api(lambda:self.window.api.entity_values(entity,self.selected_record_id),
                            lambda values:self.editor.setPlainText(json.dumps(values,ensure_ascii=False,indent=2)))

    def save_values(self):
        entity=self.entity_key()
        if not entity or not self.selected_record_id:self.window.show_error("ابتدا یک رکورد را انتخاب کنید.");return
        try:
            values=json.loads(self.editor.toPlainText() or "{}")
            if not isinstance(values,dict):raise ValueError("مقادیر باید یک شیء JSON باشند.")
        except (ValueError,json.JSONDecodeError) as exc:self.window.show_error("JSON نامعتبر: {}".format(exc));return
        self.window.run_api(lambda:self.window.api.save_entity_values(entity,self.selected_record_id,values),
                            lambda _r:self.window.set_status("مقادیر سفارشی ذخیره شد."),busy=self.save_values_button)

    def delete_record(self):
        entity=self.entity_key()
        if not entity or not self.selected_record_id:return
        answer=QMessageBox.question(self,"حذف رکورد","رکورد سفارشی حذف شود؟",
                    QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
        if answer!=QMessageBox.StandardButton.Yes:return
        self.window.run_api(lambda:self.window.api.delete_schema_record(entity,self.selected_record_id),
                            lambda _r:self._schema_saved())

    def _schema_saved(self):
        self.window.set_status("ساختار سفارشی به‌روزرسانی شد.");self.refresh_entities()
