from PySide2.QtWidgets import QDockWidget, QWidget, QBoxLayout, QPushButton, QMenu
from PySide2.QtCore import Qt
from PySide2.QtGui import QContextMenuEvent, QDragEnterEvent, QDropEvent


class DockButton(QPushButton):
    def __init__(self, emoji, index, parent_dock):
        self._parent = parent_dock
        super().__init__(emoji)
        self.index = index
        self.parent_dock = parent_dock
        self.setProperty('class', 'flat')
        self.setFixedSize(30, 30)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"Go to panel {index}")

      
        self.clicked.connect(lambda: self.parent_dock._parent.manager_panel.show_page(self.index))

    def contextMenuEvent(self, event: QContextMenuEvent):
        menu = QMenu(self)
        delete_action = menu.addAction("🗑 حذف")
        action = menu.exec_(event.globalPos())
        if action == delete_action:
            self.parent_dock.remove_button(self)
        self._parent._parent._parent.button_indices = self._parent.current_indices()
        self._parent._parent._parent.save_keys()
        


class DockWidget(QDockWidget):
    emoji_map = {
        0: '🏠', 1: '👤', 2: '👥', 3: '📦',
        4: '📂', 5: '🧾', 6: '📑', 7: '💰',
        8: '📈', 9: '🏭'
    }

    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        self._parent = parent

        
        feats = self.features()
        feats &= ~QDockWidget.DockWidgetFeature.DockWidgetClosable
        feats &= ~QDockWidget.DockWidgetFeature.DockWidgetFloatable
        self.setFeatures(feats)

        self.setAcceptDrops(True)

      
        self.dock_content = QWidget()
        self.dock_layout = QBoxLayout(QBoxLayout.LeftToRight)
        self.dock_layout.setContentsMargins(5, 5, 5, 5)
        self.dock_layout.setSpacing(5)
        self.dock_content.setLayout(self.dock_layout)
        self.setWidget(self.dock_content)

        self.dockLocationChanged.connect(self._onLocationChanged)

    def _onLocationChanged(self, area):
        if area in (Qt.TopDockWidgetArea, Qt.BottomDockWidgetArea):
            self.dock_layout.setDirection(QBoxLayout.LeftToRight)
        else:
            self.dock_layout.setDirection(QBoxLayout.TopToBottom)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasFormat('application/x-panel-index'):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent):
        data = event.mimeData().data('application/x-panel-index')
        idx = int(bytes(data).decode())
        emoji = self.emoji_map.get(idx, '❓')

        btn = DockButton(emoji, idx, self)
        self.dock_layout.addWidget(btn)
        btn.show()
        event.acceptProposedAction()
        self._parent._parent.button_indices = self.current_indices()
        self._parent._parent.save_keys()

    def remove_button(self, btn: QPushButton):
        self.dock_layout.removeWidget(btn)
        btn.setParent(None)
        btn.deleteLater()

    def add_buttons_from_indices(self, indices):
         
            while self.dock_layout.count():
                item = self.dock_layout.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.setParent(None)
                    widget.deleteLater()

         
            for idx in indices or []:
                if idx in self._parent._parent.visible_buttons:
                    emoji = self.emoji_map.get(idx, '❓')
                    btn = DockButton(emoji, idx, self)
                    self.dock_layout.addWidget(btn)
                    btn.show()
    def current_indices(self):
        indices = []
        for i in range(self.dock_layout.count()):
            widget = self.dock_layout.itemAt(i).widget()
            if isinstance(widget, DockButton):
                indices.append(widget.index)
        return indices
    
    
     
