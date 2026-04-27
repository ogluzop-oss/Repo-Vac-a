# src/utils/mensajes.py
from PyQt6.QtWidgets import QLabel, QWidget
from PyQt6.QtCore import QTimer, Qt


class Toast(QWidget):
    def __init__(self, parent, message, duration=2500):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.label = QLabel(message, self)
        self.label.setStyleSheet(
            """
            background: #DCF8C6;
            padding: 10px 14px;
            border-radius: 10px;
            color: #1b1b1b;
            font-weight: 500;
        """
        )
        self.label.adjustSize()
        self.resize(self.label.size())
        # position bottom-left-ish (but not overlapping controls)
        parent_geo = parent.geometry()
        x = parent_geo.x() + 20
        y = parent_geo.y() + parent_geo.height() - self.height() - 20
        self.move(x, y)
        QTimer.singleShot(duration, self.close)
        self.show()
