"""Role presets and per-resource CRUD permission matrix for administrators."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
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
        self.user_page = 1
        self.user_page_size = 15
        self.user_total = 0
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
        toolbar.addWidget(QLabel("یافتن کاربر"))
        self.user_search = QLineEdit()
        self.user_search.setPlaceholderText("نام کاربری را جست‌وجو کنید…")
        self.user_search.setClearButtonEnabled(True)
        self.user_search.returnPressed.connect(self.refresh)
        self.search_users_button = QPushButton("جست‌وجو")
        self.search_users_button.clicked.connect(self.refresh)
        toolbar.addWidget(self.user_search, 2)
        toolbar.addWidget(self.search_users_button)
        self.user_combo = QComboBox()
        self.user_combo.setMinimumWidth(220)
        self.user_combo.currentIndexChanged.connect(self._select_user)
        toolbar.addWidget(self.user_combo, 2)
        toolbar.addWidget(QLabel("نقش پایه"))
        self.role_combo = QComboBox()
        for role in ("cashier", "inventory", "accountant", "viewer", "kiosk", "custom"):
            self.role_combo.addItem(ROLE_LABELS[role], role)
        self.role_combo.currentIndexChanged.connect(self._apply_role)
        toolbar.addWidget(self.role_combo, 1)
        root.addLayout(toolbar)

        user_pager = QHBoxLayout()
        user_pager.addWidget(QLabel("نتایج در صفحه"))
        self.user_page_size_combo = QComboBox()
        for size in (15, 30, 50):
            self.user_page_size_combo.addItem(str(size), size)
        self.user_page_size_combo.currentIndexChanged.connect(self._user_page_size_changed)
        user_pager.addWidget(self.user_page_size_combo)
        self.user_page_label = QLabel("صفحه ۱ از ۱ · ۰ کاربر")
        self.user_page_label.setObjectName("PageSubtitle")
        user_pager.addWidget(self.user_page_label)
        user_pager.addStretch(1)
        self.user_previous_button = QPushButton("صفحهٔ قبل")
        self.user_next_button = QPushButton("صفحهٔ بعد")
        self.user_previous_button.clicked.connect(self._previous_user_page)
        self.user_next_button.clicked.connect(self._next_user_page)
        user_pager.addWidget(self.user_previous_button)
        user_pager.addWidget(self.user_next_button)
        root.addLayout(user_pager)

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
        self.window.run_api(self._load_users_page, self._populate_users, busy=self.refresh_button)

    def _load_users_page(self):
        return self.window.api.list_users_page(
            q=self.user_search.text().strip() or None,
            page=self.user_page,
            page_size=self.user_page_size,
        )

    def _populate_users(self, payload):
        selected_id = self.user_combo.currentData()
        self.users = list(payload.get("items") or [])
        self.user_page = int(payload.get("page", self.user_page))
        self.user_page_size = int(payload.get("page_size", self.user_page_size))
        self.user_total = int(payload.get("total", len(self.users)))
        self._loading = True
        self.user_combo.clear()
        self.user_combo.addItem("انتخاب کاربر از نتایج…", None)
        for user in self.users:
            parts = [user.get("username", "—")]
            parts.append("مدیر" if user.get("is_admin") else "کاربر")
            parts.append("فعال" if user.get("is_active", True) else "غیرفعال")
            self.user_combo.addItem(" · ".join(parts), user.get("id"))
        idx = self.user_combo.findData(selected_id) if selected_id else -1
        self.user_combo.setCurrentIndex(idx if idx >= 0 else 0)
        pages = max(1, (self.user_total + self.user_page_size - 1) // self.user_page_size)
        self.user_page_label.setText("صفحه {} از {} · {} کاربر".format(self.user_page, pages, self.user_total))
        self.user_previous_button.setEnabled(self.user_page > 1)
        self.user_next_button.setEnabled(self.user_page < pages)
        self._loading = False
        self._select_user()

    def _user_page_size_changed(self, *_args):
        self.user_page_size = int(self.user_page_size_combo.currentData() or 15)
        self.user_page = 1
        if self.window.api:
            self.window.run_api(self._load_users_page, self._populate_users, busy=self.refresh_button)

    def _previous_user_page(self):
        if self.user_page > 1:
            self.user_page -= 1
            self.window.run_api(self._load_users_page, self._populate_users, busy=self.refresh_button)

    def _next_user_page(self):
        pages = max(1, (self.user_total + self.user_page_size - 1) // self.user_page_size)
        if self.user_page < pages:
            self.user_page += 1
            self.window.run_api(self._load_users_page, self._populate_users, busy=self.refresh_button)

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
