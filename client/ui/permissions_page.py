"""Role presets and per-resource CRUD permission matrix for administrators."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget, QCheckBox,
)

from client.ui.permissions import (
    ACTION_LABELS, RESOURCE_LABELS, ROLE_GRANTS, ROLE_LABELS,
    can_access, encode_grants, parse_grants,
)


class PermissionsPage(QFrame):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.users = []
        self.checkboxes = {}
        self._loading = False
        self.setObjectName("Card")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("نقش‌ها و مجوزهای دسترسی")
        title.setObjectName("PageTitle")
        subtitle = QLabel("مجوزها برای هر منبع و هر عملیات جدا ذخیره و در سمت API بررسی می‌شوند.")
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)
        self.refresh_button = QPushButton("بازخوانی کاربران")
        self.refresh_button.clicked.connect(self.refresh)
        header.addWidget(self.refresh_button)
        root.addLayout(header)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("کاربر"))
        self.user_combo = QComboBox()
        self.user_combo.setMinimumWidth(220)
        self.user_combo.currentIndexChanged.connect(self._select_user)
        toolbar.addWidget(self.user_combo, 2)
        toolbar.addWidget(QLabel("نقش پایه"))
        self.role_combo = QComboBox()
        for role in ("cashier", "inventory", "accountant", "viewer", "custom"):
            self.role_combo.addItem(ROLE_LABELS[role], role)
        self.role_combo.currentIndexChanged.connect(self._apply_role)
        toolbar.addWidget(self.role_combo, 1)
        root.addLayout(toolbar)

        matrix_host = QWidget()
        matrix_host.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        matrix = QGridLayout(matrix_host)
        matrix.setContentsMargins(4, 4, 4, 4)
        matrix.setHorizontalSpacing(18)
        matrix.setVerticalSpacing(8)
        matrix.addWidget(QLabel("بخش برنامه"), 0, 0)
        for col, (_code, label) in enumerate(ACTION_LABELS, 1):
            header_label = QLabel(label)
            header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            header_label.setObjectName("MetricLabel")
            matrix.addWidget(header_label, 0, col)
        for row, (resource, label) in enumerate(RESOURCE_LABELS.items(), 1):
            name = QLabel(label)
            name.setMinimumWidth(180)
            matrix.addWidget(name, row, 0)
            for col, (code, action_label) in enumerate(ACTION_LABELS, 1):
                check = QCheckBox()
                check.setToolTip("{} — {}".format(label, action_label))
                check.setAccessibleName("{} — {}".format(label, action_label))
                check.setChecked(False)
                check.toggled.connect(self._manual_change)
                matrix.addWidget(check, row, col, alignment=Qt.AlignmentFlag.AlignCenter)
                self.checkboxes[(resource, code)] = check
        matrix_host.setMinimumWidth(620)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(matrix_host)
        root.addWidget(scroll, 1)

        actions = QHBoxLayout()
        self.notice = QLabel("مدیر سیستم همواره دسترسی کامل دارد؛ این جدول مجوز کاربران غیرمدیر را تعیین می‌کند.")
        self.notice.setObjectName("PageSubtitle")
        self.notice.setWordWrap(True)
        self.save_button = QPushButton("ذخیرهٔ مجوزها")
        self.save_button.setObjectName("PrimaryButton")
        self.save_button.clicked.connect(self.save_permissions)
        actions.addWidget(self.notice, 1)
        actions.addWidget(self.save_button)
        root.addLayout(actions)
        self.refresh()

    def set_permissions(self, user):
        self.save_button.setVisible(bool(user and user.get("is_admin")))
        self.refresh_button.setVisible(bool(user and user.get("is_admin")))

    def refresh(self):
        if not self.window.api or not (self.window.current_user or {}).get("is_admin"):
            return
        self.window.run_api(self._load_all_users, self._populate_users, busy=self.refresh_button)

    def _load_all_users(self):
        users = []
        page = 1
        page_size = 200
        while True:
            result = self.window.api.list_users_page(page=page, page_size=page_size)
            batch = list(result.get("items") or [])
            users.extend(batch)
            total = int(result.get("total", len(users)))
            if not batch or len(users) >= total:
                break
            page += 1
        return users

    def _populate_users(self, users):
        selected_id = self.user_combo.currentData()
        self.users = list(users or [])
        self._loading = True
        self.user_combo.clear()
        self.user_combo.addItem("انتخاب کاربر…", None)
        for user in self.users:
            suffix = " · مدیر" if user.get("is_admin") else ""
            self.user_combo.addItem(user.get("username", "—") + suffix, user.get("id"))
        idx = self.user_combo.findData(selected_id) if selected_id else -1
        self.user_combo.setCurrentIndex(idx if idx >= 0 else (1 if self.users else 0))
        self._loading = False
        self._select_user()

    def _selected_user(self):
        uid = self.user_combo.currentData()
        return next((user for user in self.users if user.get("id") == uid), None)

    def _select_user(self, *_args):
        if self._loading:
            return
        user = self._selected_user()
        if not user:
            self._set_matrix({}, "custom")
            return
        grants, role = parse_grants(user.get("buttons", ""))
        self._set_matrix(grants, role)

    def _set_matrix(self, grants, role):
        self._loading = True
        for (resource, code), checkbox in self.checkboxes.items():
            checkbox.setChecked(code in grants.get(resource, ""))
        idx = self.role_combo.findData(role)
        self.role_combo.setCurrentIndex(idx if idx >= 0 else self.role_combo.findData("custom"))
        self._loading = False

    def _apply_role(self, *_args):
        if self._loading:
            return
        role = self.role_combo.currentData()
        if role not in ROLE_GRANTS:
            return
        grants = ROLE_GRANTS[role]
        self._loading = True
        for (resource, code), checkbox in self.checkboxes.items():
            checkbox.setChecked(code in grants.get(resource, ""))
        self._loading = False

    def _manual_change(self, _checked):
        if self._loading:
            return
        idx = self.role_combo.findData("custom")
        if idx >= 0 and self.role_combo.currentIndex() != idx:
            self._loading = True
            self.role_combo.setCurrentIndex(idx)
            self._loading = False

    def save_permissions(self):
        user = self._selected_user()
        if not user:
            self.window.show_error("ابتدا کاربر موردنظر را انتخاب کنید.")
            return
        if user.get("is_admin"):
            QMessageBox.information(self, "مدیر سیستم", "مدیر سیستم همواره مجوز کامل دارد.")
            return
        grants = {}
        for (resource, code), checkbox in self.checkboxes.items():
            if checkbox.isChecked():
                grants.setdefault(resource, "")
                grants[resource] += code
        # Keep action order deterministic and save a compact policy in User.buttons.
        for resource, actions in list(grants.items()):
            grants[resource] = "".join(code for code, _label in ACTION_LABELS if code in actions)
        role = self.role_combo.currentData() or "custom"
        encoded = encode_grants(grants, role)
        self.window.run_api(
            lambda: self.window.api.update_user(user["id"], buttons=encoded),
            lambda updated: self._saved(updated, encoded),
            busy=self.save_button,
        )

    def _saved(self, updated, encoded):
        selected_id = self.user_combo.currentData()
        for index, user in enumerate(self.users):
            if user.get("id") == selected_id:
                user["buttons"] = updated.get("buttons", encoded)
                self.users[index] = user
                break
        self.window.set_status("مجوزها ذخیره شد و از درخواست بعدی در سرور اعمال می‌شود.")
        QMessageBox.information(self, "مجوزها ذخیره شد", "سیاست دسترسی کاربر در سرور به‌روزرسانی شد.")
