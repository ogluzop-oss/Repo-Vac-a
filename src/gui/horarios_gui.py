"""
Horarios — módulo standalone (extraído de la pestaña "HORARIO EMPLEADOS" de `ConfiguracionWindow`
en `gestion_usuarios.py`, restructuración 2026-09). Rejilla semanal de turnos por empleado
(añadir semana/empleado, ausencias, imprimir, eliminar, guardar).

Acceso: ADMINISTRADOR y SUPERADMIN con edición completa; OPERARIO en modo SOLO LECTURA (RRHH
Fase E, bolsa de horas) — ver el docstring de `HorariosWindow` más abajo para el detalle del modo
de solo lectura. (Nota histórica: una instrucción anterior del usuario excluía también a
SUPERADMIN de este módulo, y a OPERARIO por completo — ver
`services/seguridad/modulos_menu.py::DEFAULT_OPERARIO`. El usuario ha revertido explícitamente
ambas exclusiones: SUPERADMIN tiene el mismo acceso que ADMINISTRADOR, y OPERARIO entra en modo
solo lectura para poder usar el botón "Bolsa de horas" sobre su propia ficha. El gate real vive en
`menu_principal.py`, tanto en la condición que crea la tarjeta del menú como en el guard de
`abrir_ventana_por_id`.)

Pura relocación de UI: la lógica de negocio (guardado/carga de `documentos/horarios.json`) es
prácticamente la misma que ya vivía aquí — la única novedad (Fase E) es normalizar cada `grid`
cargado con `id_empleado` reales (`rrhh.horarios_vinculo_empleado.cargar_horarios_json_normalizado`)
antes de pasarlo a la rejilla, y recalcular los avisos de descanso mínimo al guardar. Los widgets
de la rejilla en sí (`_HorarioSemana`/`_HorarioContainer`/etc.) ya estaban extraídos a
`src/rrhh/gui/horarios.py` (F3.0.2); este módulo solo relocaliza el CONTENEDOR de nivel superior
(antes una pestaña dentro de Configuración, ahora una ventana propia del menú principal).
"""

import json
import os

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from assets.estilo_global import _blindar_tamano_fijo, mostrar_mensaje
from src.rrhh.gui.horarios import _HorarioContainer, _HorarioSemana
from src.utils.i18n import tr

_CIAN = "#00FFC6"
_FONDO = "#0E1117"
_PANEL_BG = "#161B22"
_BORDE = "#30363D"


class HorariosWindow(QWidget):
    """Horario semanal de empleados. ADMINISTRADOR y SUPERADMIN con edición completa; OPERARIO en
    modo SOLO LECTURA (ver docstring del módulo) — sin "NUEVA SEMANA"/"GUARDAR HORARIOS" ni ningún
    botón de edición dentro de cada tabla; el único botón que ve es "Bolsa de horas"
    (`_HorarioSemana`, RRHH Fase E). Ventana de nivel superior — antes pestaña "HORARIO EMPLEADOS"
    de Configuración."""

    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self.callback_vuelta = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background-color: {_FONDO};")
        self.setWindowTitle("HORARIO EMPLEADOS")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Cabecera con título + botón de regreso (mismo patrón que otras ventanas de nivel
        # superior extraídas de Configuración, p. ej. `GestionCajaWindow` en gestion_usuarios.py).
        header = QFrame()
        header.setFixedHeight(64)
        header.setStyleSheet(f"background-color:{_FONDO};")
        h_ly = QHBoxLayout(header)
        h_ly.setContentsMargins(28, 0, 28, 0)
        titulo = QLabel(tr("cfg.horario_title", default="HORARIO EMPLEADOS"))
        titulo.setStyleSheet(f"color:{_CIAN};font-weight:900;font-size:16px;letter-spacing:1px;")
        h_ly.addWidget(titulo)
        h_ly.addStretch()
        btn_volver = QPushButton("✕")
        btn_volver.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_volver.setFixedSize(50, 50)
        btn_volver.setStyleSheet(
            "QPushButton{background:transparent;color:#F85149;border:none;"
            "border-radius:25px;padding:0;font-family:'Segoe UI';font-weight:900;font-size:18px;}"
            "QPushButton:hover{background:#F85149;color:#0E1117;}"
        )
        btn_volver.setProperty("sin_glow", True)
        _blindar_tamano_fijo(btn_volver, 50, 50)
        btn_volver.clicked.connect(self.ejecutar_regreso)
        h_ly.addWidget(btn_volver)
        root.addWidget(header)

        root.addWidget(self._crear_contenido(), 1)

    def ejecutar_regreso(self):
        if self.callback_vuelta:
            self.callback_vuelta()
        self.close()

    # --- CONTENIDO: HORARIO SEMANAL ---
    # (extraído verbatim de `ConfiguracionWindow._crear_page_horarios` en gestion_usuarios.py.)
    def _crear_contenido(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(20, 16, 20, 12)
        outer.setSpacing(10)
        hdr_row = QHBoxLayout()
        hdr_row.addStretch()
        # Mismo diseño que el botón "Imprimir" de cada tabla de horario (contorno cian, relleno
        # oscuro en reposo, hover invierte a relleno cian) — ver `src/rrhh/gui/horarios.py::btn_print`.
        btn_new = QPushButton("＋  " + tr("cfg.nueva_semana", default="NUEVA SEMANA"))
        btn_new.setFixedHeight(38)
        btn_new.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_new.setStyleSheet(f"""
            QPushButton {{
                background: #11181D; border: 1px solid {_CIAN};
                border-radius: 8px; color: {_CIAN};
                font-family: 'Segoe UI'; font-weight: bold; font-size: 13px;
                padding: 0 16px;
            }}
            QPushButton:hover {{ background: {_CIAN}; color: #0E1117; }}
        """)
        btn_new.clicked.connect(self._h_nueva_semana)
        hdr_row.addWidget(btn_new)
        outer.addLayout(hdr_row)
        self._btn_new_semana = btn_new
        self._h_vscroll = QScrollArea()
        self._h_vscroll.setWidgetResizable(True)
        self._h_vscroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._h_vscroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._h_container = _HorarioContainer()
        self._h_vscroll.setWidget(self._h_container)
        self._h_container._scroll_area = self._h_vscroll
        outer.addWidget(self._h_vscroll)
        save_row = QHBoxLayout()
        save_row.addStretch()
        btn_save = QPushButton("  " + tr("cfg.guardar_horarios", default="Guardar horarios"))
        btn_save.setFixedHeight(42)
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.setStyleSheet("""
            QPushButton {
                background: #161B22; border: 2px solid #22C55E; border-radius: 10px;
                color: #22C55E;
                font-family: 'Segoe UI'; font-weight: bold; font-size: 13px;
                padding: 0 28px;
            }
            QPushButton:hover { background: #22C55E; color: #0E1117; border-color: #22C55E; }
        """)
        btn_save.clicked.connect(self._h_guardar_horarios)
        save_row.addWidget(btn_save)
        outer.addLayout(save_row)
        self._btn_save_row = save_row
        self._btn_save = btn_save

        # RRHH Fase E, punto 2: OPERARIO no ve NINGÚN botón de edición en esta ventana — el único
        # que ve está dentro de cada tabla semanal ("Bolsa de horas", `_HorarioSemana`).
        if self._es_operario():
            self._btn_new_semana.setVisible(False)
            self._btn_save.setVisible(False)

        # Construcción síncrona, como el resto de páginas/ventanas de la app: el contenido se
        # entrega ya completo. A diferencia de cuando esto era una pestaña dentro del
        # `QStackedWidget` de `ConfiguracionWindow` (con animación de deslizamiento entre pestañas
        # que había que esperar a propósito, ver historial de `_h_marcar_listo`), esta ventana de
        # nivel superior ya tiene su propia animación de entrada gestionada por
        # `menu_principal.manejar_apertura` — no hace falta diferir nada aquí.
        self._h_cargar_horarios()
        return page

    def _es_operario(self) -> bool:
        return str((self.usuario or {}).get("perfil") or "").upper() == "OPERARIO"

    def _h_nueva_semana(self):
        semana = _HorarioSemana(usuario=self.usuario)
        self._h_container.add_semana(semana)
        QTimer.singleShot(60, lambda: (
            self._h_vscroll.verticalScrollBar().setValue(
                self._h_vscroll.verticalScrollBar().maximum()
            )
        ))

    def _h_cargar_horarios(self):
        """Construye el contenido. `_HorarioTable` difiere su propio relleno de celdas un tick
        (`QTimer.singleShot(0, self._build_table)`, interno, sin tocar).

        RRHH Fase E: cada `grid` cargado se normaliza con `id_empleado` reales
        (`rrhh.horarios_vinculo_empleado.cargar_horarios_json_normalizado`, best-effort desde el
        texto libre histórico) antes de pasarlo a `_HorarioSemana.set_state` — la rejilla ya
        entiende la clave `"ids"` (ver `_HorarioTable.set_state`)."""
        loaded = False
        pendientes = []
        try:
            from src.rrhh.horarios_vinculo_empleado import cargar_horarios_json_normalizado
            data = cargar_horarios_json_normalizado()
        except Exception:
            data = []
        if data:
            for item in data:
                # Pass employee count upfront to avoid a double build.
                grid_data = item.get("grid", {})
                n_emp = max(1, len(grid_data.get("names", [])), len(grid_data.get("ids", [])))
                semana = _HorarioSemana(n_emp=n_emp, usuario=self.usuario)
                self._h_container.add_semana(semana)
                pendientes.append(semana)
                # set_state solo puede aplicarse una vez la rejilla está construida.
                def _make_handler(s, d):
                    def _handler():
                        s._grid.build_complete.disconnect(_handler)
                        s.set_state(d)
                        self._h_marcar_listo(s)
                    return _handler
                semana._grid.build_complete.connect(_make_handler(semana, item))
            loaded = True
        if not loaded:
            semana = _HorarioSemana(usuario=self.usuario)
            self._h_container.add_semana(semana)
            pendientes.append(semana)
            semana._grid.build_complete.connect(lambda s=semana: self._h_marcar_listo(s))
        self._h_pendientes = set(pendientes)

    def _h_marcar_listo(self, semana):
        self._h_pendientes.discard(semana)
        if self._h_pendientes:
            return
        self._h_datos_listos = True

    def _h_guardar_horarios(self):
        try:
            # RRHH Fase E, punto 4: recalcula avisos de descanso mínimo (12h diario / 1,5 días
            # semanal) ANTES de persistir — los iconos "!" quedan al día con lo que se guarda.
            for s in self._h_container._semanas:
                try:
                    s.aplicar_avisos_descanso()
                except Exception:
                    pass
            path = os.path.normpath(
                os.path.join(os.path.dirname(__file__), "..", "..", "documentos", "horarios.json")
            )
            os.makedirs(os.path.dirname(path), exist_ok=True)
            data = [s.get_state() for s in self._h_container._semanas]
            # RRHH: sincroniza automáticamente los días marcados como VACACIONES en la rejilla
            # contra `rrhh_vacaciones` (mismo motor real que el diálogo "Vacaciones y ausencias",
            # ver `rrhh.horarios_vinculo_empleado.sincronizar_vacaciones_horario`) — así Finiquito
            # y el propio diálogo ven de inmediato lo marcado aquí, sin doble registro manual.
            # Bulletproof: nunca debe impedir guardar el horario en sí.
            try:
                from src.rrhh.horarios_vinculo_empleado import sincronizar_vacaciones_horario
                sincronizar_vacaciones_horario(data)
            except Exception:
                pass
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            mostrar_mensaje(self, tr("cfg.saved_title", default="Guardado"), tr("cfg.horarios_saved", default="Horarios guardados correctamente."), "info")
        except Exception as exc:
            mostrar_mensaje(self, tr("cfg.error_title", default="Error"), tr("cfg.horarios_save_err", default="No se pudo guardar: {exc}", exc=exc), "error")
