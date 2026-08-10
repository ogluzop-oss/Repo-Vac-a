"""
Workspace de Misión (Fase 6) — componente visual DENTRO del overlay (no abre ventanas ni modifica
layouts). Muestra el estado vivo de una misión: objetivo + tareas con estado/progreso/especialista.
Se construye con la identidad Enterprise (Foundation tokens). Solo representa; la lógica vive en el
MissionEngine.
"""

from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from src.gui.foundation import tokens as T

_ICONO = {"HECHA": "✓", "EN_CURSO": "⟳", "ESPERANDO_APROBACION": "⏳", "FALLIDA": "✗",
          "OMITIDA": "–", "PENDIENTE": "•"}
_COLOR = {"HECHA": T.OK, "EN_CURSO": T.INFO, "ESPERANDO_APROBACION": T.ADVERTENCIA,
          "FALLIDA": T.CRITICO, "OMITIDA": T.DIM, "PENDIENTE": T.DIM}


class MissionWorkspace(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("soma_ws")
        self.setStyleSheet(f"#soma_ws{{background:{T.BG}; border:1px solid {T.INFO}; "
                           f"border-radius:14px;}}")
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(14, 10, 14, 12)
        self._lay.setSpacing(6)
        self._cab = QLabel("MISIÓN")
        self._cab.setStyleSheet(f"color:{T.INFO}; font-weight:900; font-size:13px; background:transparent;")
        self._lay.addWidget(self._cab)
        self._tareas_box = QVBoxLayout()
        self._tareas_box.setSpacing(4)
        self._lay.addLayout(self._tareas_box)
        self._estado = QLabel("")
        self._estado.setStyleSheet(f"color:{T.DIM}; font-size:10px; background:transparent;")
        self._lay.addWidget(self._estado)

    def actualizar(self, mision: dict):
        if not isinstance(mision, dict):
            return
        self._cab.setText(f"MISIÓN · {(mision.get('objetivo') or '').upper()}")
        # Limpiar filas
        while self._tareas_box.count():
            it = self._tareas_box.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        for t in (mision.get("tareas") or []):
            self._tareas_box.addWidget(self._fila(t))
        self._estado.setText(f"Estado: {mision.get('estado','')} · "
                             f"Especialistas: {', '.join(mision.get('especialistas') or []) or '—'}")

    def _fila(self, t):
        est = t.get("estado", "PENDIENTE")
        fila = QHBoxLayout(); fila.setSpacing(8)
        ic = QLabel(_ICONO.get(est, "•"))
        ic.setStyleSheet(f"color:{_COLOR.get(est, T.DIM)}; font-weight:900; font-size:13px;background:transparent;")
        fila.addWidget(ic)
        tit = QLabel(t.get("titulo", ""))
        tit.setStyleSheet(f"color:{T.TEXT}; font-size:12px; background:transparent;")
        fila.addWidget(tit, 1)
        esp = QLabel(t.get("especialista") or "")
        esp.setStyleSheet(f"color:{T.ANALISIS}; font-size:10px; background:transparent;")
        fila.addWidget(esp)
        pct = QLabel(f"{t.get('progreso', 0)}%" if est == "EN_CURSO" else "")
        pct.setStyleSheet(f"color:{T.DIM}; font-size:10px; background:transparent;")
        fila.addWidget(pct)
        w = QWidget(); w.setStyleSheet("background:transparent;"); w.setLayout(fila)
        return w
