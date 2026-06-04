"""Signal bus between TPVWindow and CustomerDisplayWindow."""
from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal


class _CustomerDisplayBridge(QObject):
    # Every cart change: (items: list[dict], total: float, discount: float)
    cart_updated   = pyqtSignal(list, float, float)
    # Cart explicitly cleared (cancel / back to menu)
    cart_cleared   = pyqtSignal()
    # Sale completed: (forma_pago: str, cambio: float)
    sale_completed = pyqtSignal(str, float)
    # Status message: (message: str, level: str)  level ∈ {info, ok, warn, error}
    status_changed = pyqtSignal(str, str)


customer_display_bridge = _CustomerDisplayBridge()
