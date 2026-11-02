"""
Panel Automatización — pestaña alojada en Aprobaciones (Workflow). Muestra reglas, ejecuciones y el
panel-resumen del AutomationService. Orquesta el servicio; no calcula ni ejecuta lógica de negocio.
Construido con componentes Enterprise. Aditivo (no altera las pestañas existentes de Workflow).
"""

import logging

from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from src.gui.catalogo_gestion import _btn, _combo, _dialogo_frameless, _inp
from src.gui.components import (EnterpriseCard, EnterpriseDashboardGrid,
                                EnterpriseTable)
from src.gui.foundation import tokens as T

logger = logging.getLogger("gui.paneles.automatizacion")

# Catálogo cerrado (mismo motor: `services.automatizacion.reglas.CONDICIONES` /
# `services.automatizacion.acciones.CATALOGO`) — la regla nueva combina una condición y una
# acción YA CONECTADAS a IA/Predicción/subsistemas existentes; no se programa lógica nueva.
_CONDICIONES = [
    ("Stock crítico", "stock_critico"), ("Predicción de rotura", "prediccion_rotura"),
    ("Facturas impagadas (≥5, 30d)", "impago_30d"), ("Sin ventas en 120 días", "sin_ventas_120d"),
    ("Contrato caduca en 30 días", "contrato_caduca_30d"), ("Riesgo alto de impago", "riesgo_impago_alto"),
    ("Siempre (sin condición)", "siempre"),
]
_ACCIONES = [
    ("Notificar", "notificar"), ("Crear tarea", "crear_tarea"),
    ("Crear recordatorio", "crear_recordatorio"), ("Crear incidencia", "crear_incidencia"),
    ("Solicitar aprobación (Workflow)", "solicitar_aprobacion"),
    ("Crear propuesta de compra", "crear_propuesta_compra"),
    ("Proponer liquidación", "proponer_liquidacion"), ("Solicitar inventario", "solicitar_inventario"),
    ("Solicitar auditoría", "solicitar_auditoria"), ("Solicitar revisión", "solicitar_revision"),
    ("Enviar correo", "enviar_correo"),
]
_TRIGGERS = [("Programado", "programado"), ("Predicción IA", "prediccion"), ("Evento", "evento")]
_NIVELES = [("Solo informar", "informar"), ("Proponer", "proponer"),
            ("Aprobar (Workflow)", "aprobar"), ("Automático", "auto")]
_PRIORIDADES = [("Crítica", "CRITICA"), ("Alta", "ALTA"), ("Media", "MEDIA"), ("Baja", "BAJA")]


def _emp(id_empresa=None):
    try:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)
    except Exception:
        return id_empresa


class _NuevaReglaDialog(QDialog):
    """Alta de regla: el usuario combina una condición y una acción del catálogo cerrado del
    motor — sin escribir código ni condiciones libres (mismo criterio que el resto de la app)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = _dialogo_frameless(self, "Nueva regla de automatización", ancho=420)
        v.addWidget(QLabel("Código (único, MAYÚSCULAS):"))
        self.inp_codigo = _inp("p. ej. R_MI_REGLA")
        v.addWidget(self.inp_codigo)
        v.addWidget(QLabel("Nombre:"))
        self.inp_nombre = _inp("Nombre descriptivo de la regla")
        v.addWidget(self.inp_nombre)
        v.addWidget(QLabel("Condición (SI):"))
        self.cmb_condicion = _combo(_CONDICIONES)
        v.addWidget(self.cmb_condicion)
        v.addWidget(QLabel("Acción (ENTONCES):"))
        self.cmb_accion = _combo(_ACCIONES)
        v.addWidget(self.cmb_accion)
        v.addWidget(QLabel("Disparador:"))
        self.cmb_trigger = _combo(_TRIGGERS)
        v.addWidget(self.cmb_trigger)
        v.addWidget(QLabel("Nivel de autonomía:"))
        self.cmb_nivel = _combo(_NIVELES)
        v.addWidget(self.cmb_nivel)
        v.addWidget(QLabel("Prioridad:"))
        self.cmb_prioridad = _combo(_PRIORIDADES)
        v.addWidget(self.cmb_prioridad)
        fila = QHBoxLayout(); fila.addStretch()
        fila.addWidget(_btn("Crear regla", self.accept, primary=True))
        v.addLayout(fila)

    def valores(self):
        return {
            "codigo": self.inp_codigo.text().strip(),
            "nombre": self.inp_nombre.text().strip(),
            "condicion": self.cmb_condicion.currentData(),
            "accion": self.cmb_accion.currentData(),
            "trigger_tipo": self.cmb_trigger.currentData(),
            "nivel": self.cmb_nivel.currentData(),
            "prioridad": self.cmb_prioridad.currentData(),
        }


class PanelAutomatizacion(QWidget):
    def __init__(self, usuario=None, id_empresa=None, parent=None):
        super().__init__(parent)
        self.usuario = usuario or {}
        self.id_empresa = _emp(id_empresa)
        self.setStyleSheet(f"background:{T.BG};color:{T.TEXT};")
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        self.grid = EnterpriseDashboardGrid(columnas=4)
        root.addWidget(self.grid)

        # Nueva regla / Activar-Desactivar: justo encima de la tabla a la que afectan (mismo diseño
        # de botón). El propio Actualizar de la tabla va en SU barra, junto a la búsqueda — igual
        # que en "Ejecuciones recientes" — no aquí arriba.
        root.addWidget(QLabel("Reglas de automatización"))
        barra_reglas = QHBoxLayout()
        bt_nueva = QPushButton("+ Nueva regla")
        bt_nueva.clicked.connect(self._nueva_regla)
        bt_nueva.setStyleSheet(T.qss_boton(T.INFO))
        barra_reglas.addWidget(bt_nueva)
        bt = QPushButton("Activar / Desactivar regla")
        bt.clicked.connect(self._toggle_regla)
        bt.setStyleSheet(T.qss_boton(T.INFO))
        barra_reglas.addWidget(bt)
        barra_reglas.addStretch(1)
        root.addLayout(barra_reglas)
        self.t_reglas = EnterpriseTable(["Código", "Nombre", "Disparador", "Acción", "Activa"],
                                        con_busqueda=True, con_actualizar=self._cargar)
        root.addWidget(self.t_reglas)
        self._reglas_cache = []

        root.addWidget(QLabel("Ejecuciones recientes"))
        self.t_ejec = EnterpriseTable(["Regla", "Acción", "Estado", "Creado"], con_busqueda=True,
                                      pagina=15, con_actualizar=self._cargar)
        root.addWidget(self.t_ejec)

        self._cargar()

    def _cargar(self):
        emp = self.id_empresa
        self.grid.limpiar()
        try:
            from src.services import automatizacion
            res = automatizacion.panel.resumen(emp) or {}
            for clave, etiqueta, concepto in (("total", "Ejecuciones", "automatizacion"),
                                              ("pendientes", "Pendientes", "tarea"),
                                              ("propuestas", "Propuestas", "info"),
                                              ("tiempo_ahorrado_min", "Min. ahorrados", "ok")):
                self.grid.add_card(EnterpriseCard(etiqueta, res.get(clave, 0), modo="kpi", concepto=concepto))
        except Exception as e:
            logger.debug("panel automatizacion: %s", e)

        try:
            from src.services.automatizacion.reglas import listar_ejecuciones, listar_reglas
            reglas = listar_reglas(emp)
            ejec = listar_ejecuciones(emp)
        except Exception as e:
            logger.debug("tablas automatizacion: %s", e)
            reglas, ejec = [], []
        self._reglas_cache = reglas
        self.t_reglas.set_datos([{"Código": r.get("codigo"), "Nombre": r.get("nombre"),
                                  "Disparador": r.get("trigger_tipo"), "Acción": r.get("accion"),
                                  "Activa": "Sí" if r.get("activa") else "No"} for r in reglas])
        self.t_ejec.set_datos([{"Regla": e.get("codigo_regla"), "Acción": e.get("accion"),
                                "Estado": e.get("estado"), "Creado": str(e.get("creado"))} for e in ejec])

    def _nueva_regla(self):
        from assets.estilo_global import mostrar_mensaje
        dlg = _NuevaReglaDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        v = dlg.valores()
        if not v["codigo"] or not v["nombre"]:
            mostrar_mensaje(self, "Automatización", "Indica código y nombre de la regla.", "warning")
            return
        from src.services.automatizacion.reglas import crear_regla
        try:
            ok = crear_regla(v["codigo"], v["nombre"], condicion=v["condicion"], accion=v["accion"],
                             trigger_tipo=v["trigger_tipo"], nivel=v["nivel"],
                             prioridad=v["prioridad"], id_empresa=self.id_empresa)
        except ValueError as e:
            mostrar_mensaje(self, "Automatización", str(e), "error")
            return
        if ok:
            mostrar_mensaje(self, "Automatización", f"Regla «{v['nombre']}» creada correctamente.", "success")
            self._cargar()
        else:
            mostrar_mensaje(self, "Automatización",
                            f"Ya existe una regla con el código «{v['codigo']}».", "error")

    def _toggle_regla(self):
        from assets.estilo_global import mostrar_mensaje
        r = self.t_reglas.tabla.currentRow()
        if r < 0 or self.t_reglas.tabla.item(r, 0) is None:
            mostrar_mensaje(self, "Automatización", "Selecciona antes una regla en la tabla.", "warning")
            return
        codigo = self.t_reglas.tabla.item(r, 0).text()
        actual = next((x for x in self._reglas_cache if x.get("codigo") == codigo), None)
        nueva = not bool(actual.get("activa")) if actual else True
        from src.services.automatizacion.reglas import configurar
        if configurar(codigo, self.id_empresa, activa=nueva):
            mostrar_mensaje(self, "Automatización",
                            f"Regla {'activada' if nueva else 'desactivada'} correctamente.", "success")
            self._cargar()
        else:
            mostrar_mensaje(self, "Automatización", "No se pudo cambiar el estado de la regla.", "error")
