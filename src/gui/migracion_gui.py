"""
Migración de datos — asistente Enterprise de 5 pasos (Fase B, GUI). SOLO orquesta
`services.importacion` (sin lógica de negocio, regla del proyecto): stage → validate → simulate → commit
del motor por etapas (Fase A, `services/importacion/motor.py::MigrationEngine`).

Reconciliación de pasos: la especificación de negocio dibujaba 4 pasos en el diagrama del stepper pero
describía 5 en el recorrido detallado (incluyendo "Resumen" como pantalla propia, con sus 3 acciones).
Se usan 5 — "Resumen" es un paso real, no solo el estado final del paso 4:

    [ 1. Origen y Entidad ] → [ 2. Mapeo de Campos ] → [ 3. Simulación y Validaciones ]
        → [ 4. Carga Definitiva ] → [ 5. Resumen ]

Mismo patrón de "chrome custom + contenido Enterprise" que `calculadora_fiscal_wizard.py`: el indicador
de pasos (`_dots`) es la única pieza fuera de `gui/components/`; el CONTENIDO de cada página usa
`EnterpriseCard/Table/InlineBanner/StatusBadge/DashboardGrid` (`gui/components/enterprise.py`).

Convergencia de fuentes (Fichero / Conexión directa BD-ODBC-API): en vez de mantener dos pestañas que
mostrarían el MISMO asistente duplicado, el Paso 1 deja elegir la fuente y de ahí en adelante es un
único flujo — decisión documentada, ver `MigracionDatosWindow._crear_pestanas`.
"""

import csv
import json
import logging
import os

from PyQt6.QtCore import QObject, QSize, Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QInputDialog,
    QLabel, QLineEdit, QProgressBar, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QTextEdit,
    QVBoxLayout, QWidget,
)

from src.gui.components.enterprise import (
    EnterpriseCard, EnterpriseDashboardGrid, EnterpriseInlineBanner, EnterpriseSearch,
    EnterpriseStatusBadge, EnterpriseTable,
)
from src.gui.foundation import tokens as T
from src.gui.foundation.shell import QtEnterpriseWindow
from src.gui.transiciones import StackedActual
from src.services import importacion as _imp
from src.services.importacion import modelo as _modelo

try:
    from assets.estilo_global import mostrar_confirmacion, mostrar_mensaje
except Exception:  # pragma: no cover
    mostrar_mensaje = None
    mostrar_confirmacion = None

logger = logging.getLogger("gui.migracion")

# Centro obligatorio (pedido explícito): mientras el asistente está abierto, el `id_tienda` que
# capturó en su construcción (`_AsistenteMigracion._id_tienda_migracion`) se usa durante TODO el
# flujo (pasos 1-5) — si el usuario pudiera cambiar de centro a mitad de camino, ese valor quedaría
# obsoleto sin que el asistente se enterase. Flag módulo-global (no por instancia): el selector de
# centro vive en `menu_principal.py`, un módulo distinto, sin referencia directa al asistente.
_estado_migracion = {"en_curso": False}


def migracion_en_curso() -> bool:
    """True mientras el asistente de Migrar datos está abierto con un centro ya capturado —
    `gui/menu_principal.py::_abrir_selector_centro` lo consulta para bloquear el cambio de centro."""
    return _estado_migracion["en_curso"]

# Etiqueta visible por campo canónico (los campos de cada entidad los define `modelo.CAMPOS`).
_ETIQUETAS = {"codigo": "Código", "nombre": "Nombre", "descripcion": "Descripción", "precio": "Precio (PVP)",
              "familia": "Familia", "stock": "Stock", "imagen": "Imagen / Foto (ruta o URL)",
              "nif": "NIF / CIF", "email": "Email",
              "telefono": "Teléfono", "direccion": "Dirección", "fecha": "Fecha", "cantidad": "Cantidad",
              "importe": "Importe", "cuenta": "Cuenta contable", "debe": "Debe", "haber": "Haber",
              "saldo": "Saldo", "iban": "IBAN", "titular": "Titular", "bic": "BIC", "banco": "Banco",
              "tipo": "Tipo de cuenta", "naturaleza": "Naturaleza (deudora/acreedora)"}
_ENTIDADES = (("Productos / Catálogo", _imp.PRODUCTOS), ("Clientes", _imp.CLIENTES),
              ("Proveedores", _imp.PROVEEDORES), ("Histórico de ventas", _imp.VENTAS_HIST),
              ("Saldos de apertura", _imp.SALDOS), ("Tesorería (cuentas)", _imp.TESORERIA),
              ("Plan Contable", _imp.PLAN_CONTABLE))
_ENTIDADES_LABEL = {val: etq for etq, val in _ENTIDADES}
_TIPOS_CONECTOR = (("Base de datos (SQLAlchemy)", "bd"), ("ODBC", "odbc"), ("API REST (JSON)", "api"))

# Entidad → v_id del módulo destino (`menu_principal.abrir_ventana_por_id`) donde se ven los registros
# ya importados. PROVEEDORES → "compras": el módulo "Proveedores" real ES la tarjeta v_id "compras"
# (Extranet B2B, ver `compras_gestion.py`) — no existe ya un CRUD de proveedores aparte. VENTAS_HIST →
# "reposicion": es el consumidor real de ese histórico (`informe_reposicion.py`, forecasting Prophet),
# más preciso que "ventas" (que muestra `ventas` de POS, no `ventas_historicas`).
_V_ID_DESTINO = {
    _imp.PRODUCTOS: "catalogo", _imp.CLIENTES: "clientes_crm", _imp.PROVEEDORES: "compras",
    _imp.VENTAS_HIST: "reposicion", _imp.SALDOS: "contabilidad", _imp.TESORERIA: "tesoreria",
    _imp.PLAN_CONTABLE: "contabilidad",
}

_PASOS = ["Origen y Entidad", "Mapeo de Campos", "Simulación y Validaciones", "Carga Definitiva", "Resumen"]


def _combo():
    cb = QComboBox()
    cb.setStyleSheet(f"QComboBox{{background:{T.BG};color:{T.TEXT};border:1px solid {T.BORDE};"
                     "border-radius:8px;padding:5px 10px;min-width:220px;}"
                     "QComboBox::drop-down{border:none;width:22px;background:transparent;}")
    return cb


def _btn(txt, cb, *, primary=False, color=None):
    b = QPushButton(txt); b.setCursor(Qt.CursorShape.PointingHandCursor); b.setFixedHeight(38)
    c = color or T.INFO
    if primary:
        b.setStyleSheet(f"QPushButton{{background:{c};color:{T.BG};border:none;border-radius:10px;"
                        "font-weight:900;padding:6px 18px;}"
                        f"QPushButton:hover{{background:{T.BG};color:{c};border:2px solid {c};}}"
                        f"QPushButton:disabled{{background:{T.BORDE};color:{T.DIM};}}")
    else:
        b.setStyleSheet(f"QPushButton{{background:transparent;color:{c};border:2px solid {c};"
                        "border-radius:10px;font-weight:900;padding:6px 18px;}"
                        f"QPushButton:hover{{background:{c};color:{T.BG};}}"
                        f"QPushButton:disabled{{background:transparent;color:{T.DIM};border-color:{T.BORDE};}}")
    if cb:
        b.clicked.connect(cb)
    return b


def _btn_cargando(txt, cb, *, primary=False, cargando="⏳  Actualizando…"):
    """Como `_btn`, pero al pulsarse muestra un estado de carga y se deshabilita mientras `cb`
    se ejecuta (petición: TODOS los botones «Actualizar» de la app con esta animación)."""
    b = _btn(txt, None, primary=primary)

    def _run():
        orig = b.text()
        b.setText(cargando); b.setEnabled(False)
        try:
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
            cb()
        finally:
            b.setText(orig); b.setEnabled(True)
    b.clicked.connect(_run)
    return b


def _repintar(btn):
    """Fuerza al motor de estilos a re-evaluar los selectores :hover/:disabled tras un
    setEnabled() — sin esto, un botón creado ya deshabilitado puede quedar sin el hover
    swap al volver a habilitarse (limitación de QSS con pseudo-estados)."""
    btn.style().unpolish(btn); btn.style().polish(btn)


def _titulo(txt):
    lb = QLabel(txt); lb.setStyleSheet(f"color:{T.INFO};font-size:16px;font-weight:900;"); return lb


def _inp(ph=""):
    e = QLineEdit(); e.setPlaceholderText(ph); e.setFixedHeight(36)
    e.setStyleSheet(f"QLineEdit{{background:{T.BG};color:{T.TEXT};border:1px solid {T.BORDE};"
                    "border-radius:8px;padding:5px 10px;}"
                    f"QLineEdit:focus{{border-color:{T.INFO};}}")
    return e


def _it(v):
    return QTableWidgetItem("" if v is None else str(v))


def _qss_progressbar():
    return (f"QProgressBar{{background:{T.BG2};border:2px solid {T.BORDE};border-radius:8px;"
            f"text-align:center;color:{T.TEXT};font-weight:800;height:26px;}}"
            f"QProgressBar::chunk{{background:{T.INFO};border-radius:6px;}}")


def _qss_toggle(activo):
    if activo:
        return (f"QPushButton{{background:{T.INFO};color:{T.BG};border:none;border-radius:10px;"
                f"font-weight:900;padding:6px 18px;}}")
    return (f"QPushButton{{background:transparent;color:{T.INFO};border:2px solid {T.INFO};"
            f"border-radius:10px;font-weight:900;padding:6px 18px;}}"
            f"QPushButton:hover{{background:{T.INFO};color:{T.BG};}}")


def _qss_dot(activo, completado):
    color = T.INFO if activo else (T.OK if completado else T.DIM)
    borde = T.INFO if activo else T.BORDE
    return (f"QLabel{{color:{color};background:{T.BG2};border:2px solid {borde};"
            f"border-radius:9px;padding:4px 12px;font-weight:800;font-size:13px;}}")


class _SinAnchoMinimo(QWidget):
    """QWidget cuyo ANCHO mínimo NUNCA refleja el de su layout — para la barra de pasos (decorativa)
    y la barra de navegación, que no deben forzar un ancho mínimo en el padre. El ALTO mínimo SÍ se
    conserva (mismo problema/arreglo documentado en `calculadora_fiscal_wizard.py::_SinAnchoMinimo`:
    devolver (0, 0) en las dos dimensiones colapsaba esta fila a 0px de alto con poco espacio
    vertical, dejando que sus widgets internos se superpusieran con el contenido de al lado)."""

    def minimumSizeHint(self):
        return QSize(0, super().minimumSizeHint().height())


# ── Combos de mapeo compartidos (usados por el Paso 2 del asistente) ────────────────────────────────
def _pintar_combos(combos, columnas, mapeo_sugerido):
    for campo, cb in combos.items():
        cb.blockSignals(True); cb.clear(); cb.addItem("— (ninguna)", None)
        for col in columnas:
            cb.addItem(str(col), col)
        sel = (mapeo_sugerido or {}).get(campo)
        idx = cb.findData(sel) if sel else 0
        cb.setCurrentIndex(idx if idx >= 0 else 0)
        cb.blockSignals(False)


def _leer_mapeo(combos):
    m = {}
    for campo, cb in combos.items():
        v = cb.currentData()
        if v:
            m[campo] = v
    return m


def _tam_pantalla_completa(parent):
    """Tamaño para que un diálogo de detalle ocupe toda la ventana (mismo helper que
    `calculadora_fiscal_wizard.py::_tam_pantalla_completa`)."""
    try:
        geo = parent.window().geometry()
        if not geo.isEmpty():
            return geo.size()
    except Exception:
        pass
    try:
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen:
            return screen.availableGeometry().size()
    except Exception:
        pass
    return QSize(1200, 800)


def _marco_dialogo(cont, *, bg, nombre):
    cont.setObjectName(nombre)
    cont.setStyleSheet(f"#{nombre}{{background:{bg};border:2px solid {T.INFO};border-radius:15px;}}")


def _exportar_informe(parent, filas_errores, resumen, nombre_base):
    """Exporta un informe (CSV o JSON, a elección del usuario) con el resumen de una importación + el
    detalle fila a fila de `import_trabajos_errores` (`services.importacion.errores_trabajo`). No existe
    un exportador CSV/JSON compartido en `gui/foundation/export.py` (solo `exportar_excel`, para Excel) —
    se implementa aquí en el mismo espíritu: mismo registro en Documentos vía
    `db.documentos.registrar_documento` que ya usa `exportar_excel`, best-effort, nunca lanza."""
    ruta, _filtro = QFileDialog.getSaveFileName(
        parent, "Descargar informe", f"{nombre_base}.csv", "CSV (*.csv);;JSON (*.json)")
    if not ruta:
        return
    try:
        if ruta.lower().endswith(".json"):
            with open(ruta, "w", encoding="utf-8") as fh:
                json.dump({"resumen": resumen, "errores": filas_errores}, fh, ensure_ascii=False,
                          indent=2, default=str)
        else:
            with open(ruta, "w", encoding="utf-8", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["=== RESUMEN ==="])
                for k, v in (resumen or {}).items():
                    w.writerow([k, v])
                w.writerow([])
                w.writerow(["=== ERRORES / ADVERTENCIAS ==="])
                w.writerow(["numero_fila", "campo", "valor_original", "severidad", "motivo"])
                for e in (filas_errores or []):
                    w.writerow([e.get("numero_fila"), e.get("campo"), e.get("valor_original"),
                               e.get("severidad"), e.get("motivo")])
        try:
            from src.db.documentos import registrar_documento
            registrar_documento(ruta, tipo="exportacion", nombre=os.path.basename(ruta),
                                referencia=nombre_base)
        except Exception as e:
            logger.debug("registrar_documento informe: %s", e)
        if mostrar_mensaje:
            mostrar_mensaje(parent, "Descargar informe", "Informe generado correctamente.", "info")
    except Exception as e:
        logger.error("_exportar_informe: %s", e)
        if mostrar_mensaje:
            mostrar_mensaje(parent, "Descargar informe", f"No se pudo generar el informe: {e}", "error")


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# Workers en segundo plano (QObject + moveToThread — patrón `rfid_worker.py`/`dr_dashboard_gui.py`:
# nunca tocar widgets desde el hilo secundario, solo emitir señales).
# ══════════════════════════════════════════════════════════════════════════════════════════════════
class _TareaWorker(QObject):
    """Ejecuta una función SIN ARGUMENTOS en un QThread aparte. `stage()+validate()+simulate()` suelen
    ser rápidos, pero se mantienen fuera del hilo de UI por consistencia con el resto de la app (nunca
    bloquear la ventana ante I/O de BD/conector externo)."""
    terminado = pyqtSignal(object)
    fallo = pyqtSignal(str)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            r = self._fn()
        except Exception as e:
            self.fallo.emit(str(e))
            return
        self.terminado.emit(r)


class _CommitWorker(QObject):
    """Ejecuta `MigrationEngine.commit()` en un QThread aparte, retransmitiendo su progreso por tandas
    como señal Qt (`progreso(hecho, total)`) — `commit()` en sí es framework-agnóstico (no depende de
    Qt); este worker es el único punto que traduce sus callbacks `on_progreso`/`debe_continuar` (Fase A,
    parámetros aditivos) a señales/slots. `cancelar()` solo detiene el inicio de tandas NUEVAS: las ya
    confirmadas se quedan confirmadas (ver docstring de `commit()` — es la semántica honesta que pide
    la especificación, no un rollback total)."""
    progreso = pyqtSignal(int, int)
    terminado = pyqtSignal(object)
    fallo = pyqtSignal(str)

    def __init__(self, id_lote_staging, tamano_lote=300, id_tienda=None):
        super().__init__()
        self._id_lote = id_lote_staging
        self._tamano_lote = tamano_lote
        self._id_tienda = id_tienda
        self._cancelado = False

    def cancelar(self):
        self._cancelado = True

    def run(self):
        try:
            r = _imp.commit(self._id_lote, tamano_lote=self._tamano_lote, id_tienda=self._id_tienda,
                            on_progreso=lambda hecho, total: self.progreso.emit(hecho, total),
                            debe_continuar=lambda: not self._cancelado)
        except Exception as e:
            self.fallo.emit(str(e))
            return
        self.terminado.emit(r)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# Asistente de 5 pasos — pantalla principal de "Importar / Migrar datos".
# ══════════════════════════════════════════════════════════════════════════════════════════════════
class _AsistenteMigracion(QWidget):
    """Asistente guiado de 5 pasos sobre `MigrationEngine` (stage → validate → simulate → commit).
    `cargar_fichero(ruta)`/`_cargar_fuente_conector()` permiten ejercer el flujo sin diálogos nativos
    (pruebas/automatización). `main` (opcional) es la instancia de `MenuPrincipal` — se usa SOLO para
    navegar al módulo destino en el Paso 5 (`main.abrir_ventana_por_id`), nunca para lógica de negocio."""

    def __init__(self, usuario=None, main=None):
        super().__init__()
        # Fondo opaco explícito — mismo motivo documentado en el `_Asistente` original: sin esto, el
        # deslizamiento de entrada al módulo podía dejar restos visibles del menú anterior.
        self.setStyleSheet(f"background:{T.BG};")
        self.usuario = usuario or {}
        self.main = main
        self._thread = None
        self._worker = None
        self._commit_thread = None
        self._commit_worker = None

        # Guardia OBLIGATORIA (pedido explícito): la migración debe ir siempre al centro/tienda al
        # que está conectado el usuario — nunca "a todos los centros" ni a un centro por defecto
        # arbitrario (antes `commit()` caía silenciosamente en `tienda_por_defecto`, la tienda de
        # id más bajo de la empresa, ignorando con quién estaba conectado el usuario). Sin contexto
        # operativo activo (`tienda_actual_id()` None — el caso típico de SUPERADMIN antes de elegir
        # centro, ver `gui.selector_tienda`), el asistente ni siquiera se construye: se corta aquí
        # con un aviso, mismo patrón que `gui/registro_temperatura_gui.py` para la misma precondición
        # ("sin tienda asignada, no se puede continuar").
        from src.db.empresa import tienda_actual_id
        self._id_tienda_migracion = tienda_actual_id()
        if not self._id_tienda_migracion:
            ly = QVBoxLayout(self)
            ly.setContentsMargins(24, 24, 24, 24)
            ly.setSpacing(12)
            ly.addWidget(EnterpriseInlineBanner(
                "Debes conectarte a un centro antes de poder migrar datos. Usa «Cambiar de "
                "Centro» (menú principal) y vuelve a abrir Migrar datos.",
                rol="advertencia"))
            ly.addStretch(1)
            return

        # Bloquea el cambio de centro mientras este asistente exista — `self._id_tienda_migracion`
        # (capturado arriba) se usa durante TODO el flujo (pasos 1-5); cambiar de centro a mitad de
        # camino lo dejaría obsoleto. `destroyed` cubre cualquier vía de cierre (✕, navegación,
        # error) sin depender de un `closeEvent` propio.
        _estado_migracion["en_curso"] = True
        self.destroyed.connect(lambda: _estado_migracion.update(en_curso=False))

        self._reset_estado()

        ly = QVBoxLayout(self); ly.setContentsMargins(4, 4, 4, 4); ly.setSpacing(12)

        self._progreso = QHBoxLayout(); self._progreso.setSpacing(8)
        self._dots = []
        for i, nombre in enumerate(_PASOS):
            d = QLabel(f"{i + 1}. {nombre}")
            d.setStyleSheet(_qss_dot(False, False))
            self._dots.append(d)
            self._progreso.addWidget(d)
        self._progreso.addStretch(1)
        self._wrap_progreso = _SinAnchoMinimo(); self._wrap_progreso.setLayout(self._progreso)
        ly.addWidget(self._wrap_progreso)

        # StackedActual: el ancho del asistente depende SOLO del paso visible (mismo motivo que
        # `calculadora_fiscal_wizard.py` — evita que un paso ancho deje abultado el ancho mínimo de
        # los demás).
        self._stack = StackedActual()
        ly.addWidget(self._stack, 1)
        self._stack.addWidget(self._paso_origen())      # 0
        self._stack.addWidget(self._paso_mapeo())        # 1
        self._stack.addWidget(self._paso_simulacion())   # 2
        self._stack.addWidget(self._paso_carga())        # 3
        self._stack.addWidget(self._paso_resumen())      # 4
        try:
            from src.gui.transiciones import instalar_transicion_stack
            instalar_transicion_stack(self._stack)
        except Exception:
            pass

        nav = QHBoxLayout()
        self._btn_atras = _btn("←  Atrás", self._atras)
        self._btn_sig = _btn("Siguiente →", self._siguiente, primary=True)
        nav.addWidget(self._btn_atras); nav.addStretch(1); nav.addWidget(self._btn_sig)
        self._wrap_nav = _SinAnchoMinimo(); self._wrap_nav.setLayout(nav)
        ly.addWidget(self._wrap_nav)

        self._cambiar_modo_origen(0)
        self._ir(0)

    def _reset_estado(self):
        self._entidad = _imp.PRODUCTOS
        self._ruta_origen = None
        self._origen_nombre = None
        self._formato = None
        self._filas = []
        self._columnas = []
        self._muestra = []
        self._mapeo_sugerido = {}
        self._campos_ia = set()
        self._combos = {}
        self._id_lote = None
        self._val_resumen = None
        self._ultimo_sim = None
        self._diag_meta = []
        self._diagnostico_en_curso = False
        self._commit_resultado = None

    # ── contexto (empresa/usuario) ──────────────────────────────────────────
    def _id_empresa(self):
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return None

    def _usuario_nombre(self):
        return self.usuario.get("nombre") or self.usuario.get("usuario")

    def _aviso(self, msg, tipo="warning"):
        if mostrar_mensaje:
            mostrar_mensaje(self, "Migración de datos", msg, tipo)
        else:  # pragma: no cover
            logger.info("migracion: %s", msg)

    # ══════════════════════════════════════════════════════════════════════
    # Paso 1 — Origen y Entidad
    # ══════════════════════════════════════════════════════════════════════
    def _paso_origen(self):
        w = QWidget(); v = QVBoxLayout(w); v.setSpacing(12)
        v.addWidget(_titulo("1 · Origen y entidad"))

        self._banner_orden = EnterpriseInlineBanner(
            "Orden recomendado de importación: 1º Configuración Base (Plan Contable) · 2º Datos "
            "Maestros (Clientes / Proveedores / Productos) · 3º Saldos e Inventario Inicial · "
            "4º Documentos e Histórico.", rol="info")
        v.addWidget(self._banner_orden)

        self._banner_contextual = EnterpriseInlineBanner("", rol="advertencia")
        self._banner_contextual.setVisible(False)
        v.addWidget(self._banner_contextual)

        lbl_entidad = QLabel("¿Qué vas a importar?")
        lbl_entidad.setStyleSheet(f"color:{T.TEXT};font-weight:700;")
        v.addWidget(lbl_entidad)
        self.cb_entidad = _combo()
        for etq, val in _ENTIDADES:
            self.cb_entidad.addItem(etq, val)
        self.cb_entidad.currentIndexChanged.connect(self._al_cambiar_entidad)
        v.addWidget(self.cb_entidad)

        fila_modo = QHBoxLayout()
        self._btn_modo_fichero = _btn("📂 Fichero", lambda: self._cambiar_modo_origen(0))
        self._btn_modo_conector = _btn("🔌 Conexión directa (BD / ODBC / API)",
                                       lambda: self._cambiar_modo_origen(1))
        fila_modo.addWidget(self._btn_modo_fichero); fila_modo.addWidget(self._btn_modo_conector)
        fila_modo.addStretch()
        v.addLayout(fila_modo)

        self._sub_stack_origen = StackedActual()
        self._sub_stack_origen.addWidget(self._paso_origen_fichero())
        self._sub_stack_origen.addWidget(self._paso_origen_conector())
        v.addWidget(self._sub_stack_origen)

        fila_ia = QHBoxLayout()
        self.chk_ia = QCheckBox("Sugerir el mapeo con IA (si está disponible)")
        self.chk_ia.setStyleSheet(f"color:{T.TEXT};")
        self.chk_ia.stateChanged.connect(self._al_cambiar_ia)
        fila_ia.addWidget(self.chk_ia)
        disponible = _imp.ia_disponible()
        lbl_ia_estado = QLabel("✅ IA disponible." if disponible else
                               "⚠️ IA no disponible (sin API configurada): se usará la sugerencia heurística.")
        lbl_ia_estado.setStyleSheet(f"color:{T.DIM if disponible else T.ADVERTENCIA};font-size:11px;")
        fila_ia.addWidget(lbl_ia_estado); fila_ia.addStretch()
        v.addLayout(fila_ia)

        self.lbl_estado_fuente = QLabel("")
        self.lbl_estado_fuente.setStyleSheet(f"color:{T.TEXT};font-weight:700;")
        self.lbl_estado_fuente.setWordWrap(True)
        v.addWidget(self.lbl_estado_fuente)

        v.addStretch()
        return w

    def _paso_origen_fichero(self):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(8)
        sub = QLabel("Formatos: CSV, TSV, TXT, Excel, JSON/JSONL, Parquet, XML (BMEcat), EDIFACT y "
                    "volcados .sql. Se cargan en los módulos reales sin recrear nada a mano.")
        sub.setStyleSheet(f"color:{T.DIM};"); sub.setWordWrap(True)
        v.addWidget(sub)
        fila = QHBoxLayout()
        fila.addWidget(_btn("📂  Seleccionar fichero", self._seleccionar_fichero, primary=True))
        fila.addStretch()
        v.addLayout(fila)
        self.lbl_ruta = QLabel("Ningún fichero seleccionado.")
        self.lbl_ruta.setStyleSheet(f"color:{T.TEXT};")
        v.addWidget(self.lbl_ruta)
        return w

    def _paso_origen_conector(self):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(8)
        sub = QLabel("Importa directamente desde la base de datos, un origen ODBC o una API REST del "
                    "sistema de origen, sin pasar por fichero. Requiere plan PRO o superior.")
        sub.setStyleSheet(f"color:{T.DIM};"); sub.setWordWrap(True)
        v.addWidget(sub)
        self.cb_tipo_conector = _combo()
        for etq, val in _TIPOS_CONECTOR:
            self.cb_tipo_conector.addItem(etq, val)
        self.cb_tipo_conector.currentIndexChanged.connect(self._actualizar_campos_conector)
        v.addWidget(self.cb_tipo_conector)
        self.in_url = _inp("URL SQLAlchemy (mysql+pymysql://…) o DSN ODBC")
        self.in_query = _inp("Consulta SQL (SELECT …)")
        self.in_api = _inp("URL de la API (https://…)")
        v.addWidget(self.in_url); v.addWidget(self.in_query); v.addWidget(self.in_api)
        fila = QHBoxLayout()
        fila.addWidget(_btn("🔎  Cargar datos", self._cargar_fuente_conector, primary=True))
        fila.addStretch()
        v.addLayout(fila)
        self._actualizar_campos_conector()
        return w

    def _actualizar_campos_conector(self):
        tipo = self.cb_tipo_conector.currentData()
        self.in_url.setVisible(tipo in ("bd", "odbc"))
        self.in_url.setPlaceholderText("DSN ODBC" if tipo == "odbc" else "URL SQLAlchemy (mysql+pymysql://…)")
        self.in_query.setVisible(tipo in ("bd", "odbc"))
        self.in_api.setVisible(tipo == "api")

    def _cambiar_modo_origen(self, idx):
        self._sub_stack_origen.setCurrentIndex(idx)
        self._btn_modo_fichero.setStyleSheet(_qss_toggle(idx == 0))
        self._btn_modo_conector.setStyleSheet(_qss_toggle(idx == 1))

    def _al_cambiar_entidad(self):
        self._actualizar_banner_contextual()
        if self._filas:
            self._aplicar_filas_cargadas(self._filas, origen_nombre=self._origen_nombre or "—",
                                         formato=self._formato)

    def _al_cambiar_ia(self):
        if self._filas:
            self._aplicar_filas_cargadas(self._filas, origen_nombre=self._origen_nombre or "—",
                                         formato=self._formato)

    def _actualizar_banner_contextual(self):
        entidad = self.cb_entidad.currentData()
        if entidad == _imp.SALDOS:
            try:
                from src.services.contabilidad.cuentas import listar_cuentas
                hay_cuentas = bool(listar_cuentas(self._id_empresa()))
            except Exception:
                hay_cuentas = True  # best-effort: si falla la comprobación, no bloquear con un aviso falso
            if not hay_cuentas:
                self._banner_contextual.set_mensaje(
                    "Todavía no hay cuentas en el Plan Contable de esta empresa. Los saldos necesitan "
                    "que la cuenta YA exista — importa primero «Plan Contable» (Configuración Base).")
                self._banner_contextual.setVisible(True)
                return
        self._banner_contextual.setVisible(False)

    def _seleccionar_fichero(self):
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Selecciona el fichero", "",
            "Datos (*.csv *.tsv *.txt *.xlsx *.json *.jsonl);;Todos los archivos (*)")
        if ruta:
            self.cargar_fichero(ruta)

    def cargar_fichero(self, ruta):
        """Punto de entrada testable/automatizable (sin diálogo nativo)."""
        self._ruta_origen = ruta
        self.lbl_ruta.setText(os.path.basename(ruta))
        try:
            filas, _meta = _imp.leer(ruta)
        except Exception as e:
            self._aviso(f"No se pudo leer el fichero: {e}", "error")
            return
        if not filas:
            self._aviso("El fichero no contiene filas.", "advertencia")
            return
        self._aplicar_filas_cargadas(filas, origen_nombre=os.path.basename(ruta),
                                     formato=_imp.detectar_formato(ruta))

    def _cargar_fuente_conector(self):
        tipo = self.cb_tipo_conector.currentData()
        try:
            if tipo == "bd":
                filas = _imp.leer_consulta(self.in_query.text().strip(), url=self.in_url.text().strip())
            elif tipo == "odbc":
                filas = _imp.leer_odbc(self.in_url.text().strip(), self.in_query.text().strip())
            else:
                filas = _imp.leer_api(self.in_api.text().strip())
        except Exception as e:
            self._aviso(f"No se pudo conectar: {e}", "error")
            return
        if not filas:
            self._aviso("La consulta no devolvió ninguna fila.", "advertencia")
            return
        self._aplicar_filas_cargadas(filas, origen_nombre=f"conector:{tipo}", formato=tipo)

    def _aplicar_filas_cargadas(self, filas, *, origen_nombre, formato):
        self._filas = filas
        self._origen_nombre = origen_nombre
        self._formato = formato
        self._entidad = self.cb_entidad.currentData() or _imp.PRODUCTOS
        usar_ia = self.chk_ia.isChecked()
        plan = _imp.analizar_filas(filas, self._entidad, usar_ia=usar_ia)
        self._columnas = plan.get("columnas", [])
        self._muestra = plan.get("muestra", [])
        self._mapeo_sugerido = plan.get("mapeo_sugerido", {})
        if usar_ia and _imp.ia_disponible():
            heur = _imp.sugerir_mapeo(self._columnas, self._entidad)
            self._campos_ia = {c for c, val in self._mapeo_sugerido.items() if val and heur.get(c) != val}
        else:
            self._campos_ia = set()
        self.lbl_estado_fuente.setText(
            f"✅ {len(filas)} fila(s) · {len(self._columnas)} columna(s) detectadas de «{origen_nombre}».")
        self._actualizar_estado_boton_siguiente()

    # ══════════════════════════════════════════════════════════════════════
    # Paso 2 — Mapeo de Campos
    # ══════════════════════════════════════════════════════════════════════
    def _paso_mapeo(self):
        w = QWidget(); v = QVBoxLayout(w); v.setSpacing(10)
        v.addWidget(_titulo("2 · Mapeo de campos"))
        cols = QHBoxLayout(); cols.setSpacing(16)

        izq = QWidget(); izq_l = QVBoxLayout(izq); izq_l.setContentsMargins(0, 0, 0, 0); izq_l.setSpacing(6)
        lbl_izq = QLabel("Columnas detectadas en el origen (con 2 filas de ejemplo):")
        lbl_izq.setStyleSheet(f"color:{T.TEXT};font-weight:700;")
        izq_l.addWidget(lbl_izq)
        self._tabla_muestra = EnterpriseTable(["Columna origen", "Ejemplo 1", "Ejemplo 2"], con_busqueda=False)
        izq_l.addWidget(self._tabla_muestra, 1)
        cols.addWidget(izq, 1)

        der = QWidget(); der_l = QVBoxLayout(der); der_l.setContentsMargins(0, 0, 0, 0); der_l.setSpacing(6)
        lbl_der = QLabel("Asigna cada campo canónico de destino (los marcados con * son obligatorios):")
        lbl_der.setStyleSheet(f"color:{T.TEXT};font-weight:700;")
        der_l.addWidget(lbl_der)
        self._banner_mapeo_incompleto = EnterpriseInlineBanner("", rol="advertencia")
        self._banner_mapeo_incompleto.setVisible(False)
        der_l.addWidget(self._banner_mapeo_incompleto)
        scroll_map = QScrollArea(); scroll_map.setWidgetResizable(True)
        scroll_map.setStyleSheet("QScrollArea{background:transparent;border:none;}" + T.qss_scrollbar())
        self._form_cont = QWidget()
        self.form_map = QFormLayout(self._form_cont); self.form_map.setSpacing(10)
        scroll_map.setWidget(self._form_cont)
        der_l.addWidget(scroll_map, 1)
        fila_plantillas = QHBoxLayout()
        fila_plantillas.addWidget(_btn("💾 Guardar esta plantilla de mapeo", self._guardar_plantilla))
        fila_plantillas.addWidget(_btn("📂 Cargar plantilla previa", self._cargar_plantilla))
        fila_plantillas.addStretch()
        der_l.addLayout(fila_plantillas)
        cols.addWidget(der, 1)

        v.addLayout(cols, 1)
        return w

    def _construir_mapeo_paso2(self):
        while self.form_map.rowCount():
            self.form_map.removeRow(0)
        self._combos = {}
        campos = _modelo.CAMPOS.get(self._entidad, {})
        for campo, (req, _syn) in campos.items():
            lbl_widget = QWidget()
            lw = QHBoxLayout(lbl_widget); lw.setContentsMargins(0, 0, 0, 0); lw.setSpacing(6)
            lbl = QLabel(_ETIQUETAS.get(campo, campo) + (" *" if req else ""))
            lbl.setStyleSheet(f"color:{T.CRITICO if req else T.TEXT};font-weight:700;")
            lw.addWidget(lbl)
            if campo in self._campos_ia:
                lw.addWidget(EnterpriseStatusBadge("🤖 Auto-mapeado con IA", rol="info"))
            lw.addStretch()
            cb = _combo()
            self._combos[campo] = cb
            self.form_map.addRow(lbl_widget, cb)
        _pintar_combos(self._combos, self._columnas, self._mapeo_sugerido)
        for cb in self._combos.values():
            cb.currentIndexChanged.connect(self._actualizar_estado_boton_siguiente)
        self._actualizar_estado_boton_siguiente()

    def _pintar_tabla_muestra(self):
        datos = []
        for col in self._columnas:
            e1 = self._muestra[0].get(col, "") if len(self._muestra) > 0 else ""
            e2 = self._muestra[1].get(col, "") if len(self._muestra) > 1 else ""
            datos.append([col, e1, e2])
        self._tabla_muestra.set_datos(datos)

    def _guardar_plantilla(self):
        mapeo = _leer_mapeo(self._combos)
        if not mapeo:
            self._aviso("No hay ningún campo mapeado todavía.", "info")
            return
        nombre, ok = QInputDialog.getText(self, "Guardar plantilla de mapeo", "Nombre de la plantilla:")
        nombre = (nombre or "").strip()
        if not ok or not nombre:
            return
        idp = _imp.guardar_plantilla_mapeo(nombre, self._entidad, self._origen_nombre or "—", mapeo,
                                           self._id_empresa())
        self._aviso("Plantilla guardada correctamente." if idp else "No se pudo guardar la plantilla.",
                    "info" if idp else "error")

    def _cargar_plantilla(self):
        plantillas = _imp.listar_plantillas_mapeo(self._entidad, self._id_empresa())
        if not plantillas:
            self._aviso("No hay ninguna plantilla guardada para esta entidad.", "info")
            return
        nombres = [p["nombre"] for p in plantillas]
        elegido, ok = QInputDialog.getItem(self, "Cargar plantilla de mapeo", "Plantilla:", nombres, 0, False)
        if not ok or not elegido:
            return
        p = next((p for p in plantillas if p["nombre"] == elegido), None)
        if not p:
            return
        detalle = _imp.obtener_plantilla_mapeo(p["id"])
        if not detalle:
            self._aviso("No se pudo cargar la plantilla.", "error")
            return
        self._mapeo_sugerido = detalle.get("mapeo") or {}
        self._campos_ia = set()
        _pintar_combos(self._combos, self._columnas, self._mapeo_sugerido)
        self._actualizar_estado_boton_siguiente()

    # ══════════════════════════════════════════════════════════════════════
    # Paso 3 — Simulación y Validaciones
    # ══════════════════════════════════════════════════════════════════════
    def _paso_simulacion(self):
        w = QWidget(); v = QVBoxLayout(w); v.setSpacing(10)
        v.addWidget(_titulo("3 · Simulación y validaciones"))
        self._lbl_carga_diag = QLabel("⏳ Analizando y validando los datos…")
        self._lbl_carga_diag.setStyleSheet(f"color:{T.INFO};font-weight:700;")
        v.addWidget(self._lbl_carga_diag)
        self._progress_diag = QProgressBar(); self._progress_diag.setRange(0, 0)
        self._progress_diag.setStyleSheet(_qss_progressbar())
        v.addWidget(self._progress_diag)

        self._grid_diag = EnterpriseDashboardGrid(columnas=3)
        v.addWidget(self._grid_diag)

        self._banner_sim = EnterpriseInlineBanner("", rol="analisis")
        self._banner_sim.setVisible(False)
        v.addWidget(self._banner_sim)

        self._cont_tabla_diag = self._construir_tabla_diagnostico()
        v.addWidget(self._cont_tabla_diag, 1)
        return w

    def _construir_tabla_diagnostico(self):
        cont = QWidget(); v = QVBoxLayout(cont); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(6)
        lbl = QLabel("Filas con advertencia o error (doble clic en «Valor original» para editar en línea):")
        lbl.setStyleSheet(f"color:{T.TEXT};font-weight:700;"); lbl.setWordWrap(True)
        v.addWidget(lbl)
        self._buscar_diag = EnterpriseSearch("Filtrar por fila, campo o motivo…")
        self._buscar_diag.textChanged.connect(self._filtrar_tabla_diagnostico)
        v.addWidget(self._buscar_diag)
        self._tw_diag = QTableWidget(0, 4)
        self._tw_diag.setHorizontalHeaderLabels(["Fila", "Campo", "Valor original", "Motivo"])
        self._tw_diag.verticalHeader().setVisible(False)
        self._tw_diag.setStyleSheet(T.qss_tabla())
        hh = self._tw_diag.horizontalHeader()
        for c in range(4):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Stretch)
        hh.setHighlightSections(False)
        self._tw_diag.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tw_diag.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._tw_diag.cellDoubleClicked.connect(self._editar_celda_diagnostico)
        v.addWidget(self._tw_diag, 1)
        return cont

    def _iniciar_diagnostico(self):
        if self._diagnostico_en_curso:
            return
        self._diagnostico_en_curso = True
        self._mostrar_carga_diagnostico(True)
        mapeo = _leer_mapeo(self._combos)
        filas = self._filas
        entidad = self._entidad
        id_empresa = self._id_empresa()
        usuario = self._usuario_nombre()

        def _trabajo():
            id_lote = _imp.stage(filas, entidad, id_empresa, usuario, mapeo)
            if not id_lote:
                raise RuntimeError("No se pudo preparar el lote de staging (revisa la conexión a la base "
                                   "de datos).")
            val = _imp.validate(id_lote)
            sim = _imp.simulate(id_lote)
            return {"id_lote": id_lote, "validate": val, "simulate": sim}

        self._thread = QThread()
        self._worker = _TareaWorker(_trabajo)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.terminado.connect(self._diagnostico_ok)
        self._worker.fallo.connect(self._diagnostico_error)
        self._worker.terminado.connect(self._thread.quit)
        self._worker.fallo.connect(self._thread.quit)
        # Mismo motivo que en `_iniciar_commit`: `.wait()` antes de `deleteLater()` evita la
        # ventana de colgado intermitente ligada a GC generacional durante un hilo en vuelo.
        hilo = self._thread
        hilo.finished.connect(lambda hilo=hilo: (hilo.wait(), hilo.deleteLater()))
        self._thread.start()

    def _mostrar_carga_diagnostico(self, cargando):
        self._lbl_carga_diag.setVisible(cargando)
        self._progress_diag.setVisible(cargando)
        self._grid_diag.setVisible(not cargando)
        self._cont_tabla_diag.setVisible(not cargando)
        if cargando:
            self._banner_sim.setVisible(False)

    def _diagnostico_ok(self, r):
        self._diagnostico_en_curso = False
        self._mostrar_carga_diagnostico(False)
        val = r.get("validate") or {}
        if not val.get("ok"):
            self._aviso(val.get("error", "No se pudo validar el lote."), "error")
            self._actualizar_estado_boton_siguiente()
            return
        self._id_lote = r.get("id_lote")
        self._val_resumen = val
        self._render_diagnostico(val, r.get("simulate") or {})
        self._actualizar_estado_boton_siguiente()

    def _diagnostico_error(self, msg):
        self._diagnostico_en_curso = False
        self._mostrar_carga_diagnostico(False)
        self._aviso(f"No se pudo preparar el diagnóstico: {msg}", "error")
        self._actualizar_estado_boton_siguiente()

    def _render_diagnostico(self, val, sim):
        self._ultimo_sim = sim
        self._grid_diag.limpiar()
        self._grid_diag.add_card(EnterpriseCard("Válidos", str(val.get("validos", 0)), modo="riesgo",
                                                riesgo="OK", subtitulo="Listos para importar."))
        self._grid_diag.add_card(EnterpriseCard("Advertencias", str(val.get("advertencias", 0)),
                                                modo="riesgo", riesgo="ADVERTENCIA",
                                                subtitulo="Se importarán con aviso."))
        self._grid_diag.add_card(EnterpriseCard("Errores", str(val.get("errores", 0)), modo="riesgo",
                                                riesgo="CRITICO", subtitulo="Se omitirán al importar."))
        self._pintar_tabla_diagnostico(val.get("detalle", []))
        if sim:
            nota = ""
            detalle_sim = sim.get("detalle")
            if isinstance(detalle_sim, dict) and detalle_sim.get("nota"):
                nota = " " + str(detalle_sim["nota"])
            self._banner_sim.set_mensaje(
                f"Simulación (dry-run real, sin dejar rastro en producción): {sim.get('simulados', 0)} "
                f"registro(s) probados con éxito, {sim.get('fallidos', 0)} fallarían.{nota}")
            self._banner_sim.setVisible(True)
        else:
            self._banner_sim.setVisible(False)

    def _pintar_tabla_diagnostico(self, detalle):
        meta = []
        for item in (detalle or []):
            for h in item.get("hallazgos") or []:
                meta.append({"id_fila": item.get("id_fila"), "fila": item.get("fila"),
                            "campo": h.get("campo"), "valor": h.get("valor"),
                            "motivo": h.get("motivo"), "severidad": h.get("severidad")})
        self._diag_meta = meta
        tw = self._tw_diag
        tw.setRowCount(len(meta))
        for i, m in enumerate(meta):
            tw.setItem(i, 0, _it(m["fila"]))
            tw.setItem(i, 1, _it(m["campo"] or "—"))
            tw.setItem(i, 2, _it(m["valor"]))
            tw.setItem(i, 3, _it(m["motivo"]))
        self._filtrar_tabla_diagnostico()

    def _filtrar_tabla_diagnostico(self):
        txt = self._buscar_diag.text().strip().lower()
        tw = self._tw_diag
        for i in range(tw.rowCount()):
            if not txt:
                tw.setRowHidden(i, False)
                continue
            partes = [tw.item(i, c).text() if tw.item(i, c) else "" for c in range(4)]
            tw.setRowHidden(i, txt not in " ".join(partes).lower())

    def _editar_celda_diagnostico(self, row, col):
        if col != 2 or row < 0 or row >= len(self._diag_meta):
            return
        m = self._diag_meta[row]
        if not m.get("id_fila") or not m.get("campo"):
            self._aviso("Esta fila no tiene un campo asociado editable.", "info")
            return
        actual = self._tw_diag.item(row, 2).text() if self._tw_diag.item(row, 2) else ""
        nuevo, ok = QInputDialog.getText(
            self, "Editar valor",
            f"Nuevo valor para «{_ETIQUETAS.get(m['campo'], m['campo'])}» (fila {m['fila']}):", text=actual)
        if not ok:
            return
        r = _imp.actualizar_fila_staging(m["id_fila"], m["campo"], nuevo)
        if r is None:
            self._aviso("No se pudo actualizar esta fila.", "error")
            return
        # Re-valida el LOTE completo (recuento consistente) — la edición en sí ya fue "scoped to that
        # row" (`actualizar_fila_staging`); esto solo refresca contadores/tabla tras ese cambio puntual.
        val = _imp.validate(self._id_lote)
        if val.get("ok"):
            self._val_resumen = val
            self._render_diagnostico(val, self._ultimo_sim)
            self._actualizar_estado_boton_siguiente()

    def _registros_a_importar(self):
        if not self._val_resumen:
            return 0
        return int(self._val_resumen.get("validos", 0)) + int(self._val_resumen.get("advertencias", 0))

    # ══════════════════════════════════════════════════════════════════════
    # Paso 4 — Carga Definitiva
    # ══════════════════════════════════════════════════════════════════════
    def _paso_carga(self):
        w = QWidget(); v = QVBoxLayout(w); v.setSpacing(14)
        v.addWidget(_titulo("4 · Carga definitiva"))
        self._lbl_carga_estado = QLabel("Preparando…")
        self._lbl_carga_estado.setStyleSheet(f"color:{T.TEXT};font-size:13px;font-weight:700;")
        v.addWidget(self._lbl_carga_estado)
        self._barra_progreso = QProgressBar()
        self._barra_progreso.setRange(0, 100)
        self._barra_progreso.setStyleSheet(_qss_progressbar())
        v.addWidget(self._barra_progreso)
        fila = QHBoxLayout(); fila.addStretch()
        self._btn_cancelar_carga = _btn("✖ Cancelar procesamiento", self._cancelar_commit, color=T.CRITICO)
        fila.addWidget(self._btn_cancelar_carga)
        v.addLayout(fila)
        self._banner_carga_info = EnterpriseInlineBanner("", rol="critico")
        self._banner_carga_info.setVisible(False)
        v.addWidget(self._banner_carga_info)
        nota = QLabel("«Cancelar» detiene el inicio de tandas NUEVAS — las tandas ya confirmadas antes de "
                     "cancelar NO se deshacen (garantía de rollback parcial del motor: cada fila "
                     "confirmada es su propia unidad atómica; deshacerla violaría esa misma garantía).")
        nota.setWordWrap(True)
        nota.setStyleSheet(f"color:{T.DIM};font-size:11px;")
        v.addWidget(nota)
        v.addStretch()
        return w

    def _iniciar_commit(self):
        self._barra_progreso.setRange(0, 100); self._barra_progreso.setValue(0)
        self._lbl_carga_estado.setText("Iniciando…")
        self._btn_cancelar_carga.setEnabled(True)
        self._btn_cancelar_carga.setText("✖ Cancelar procesamiento")
        self._banner_carga_info.setVisible(False)
        self._commit_thread = QThread()
        self._commit_worker = _CommitWorker(self._id_lote, tamano_lote=300,
                                            id_tienda=self._id_tienda_migracion)
        self._commit_worker.moveToThread(self._commit_thread)
        self._commit_thread.started.connect(self._commit_worker.run)
        self._commit_worker.progreso.connect(self._commit_progreso)
        self._commit_worker.terminado.connect(self._commit_ok)
        self._commit_worker.fallo.connect(self._commit_error)
        self._commit_worker.terminado.connect(self._commit_thread.quit)
        self._commit_worker.fallo.connect(self._commit_thread.quit)
        # `finished` se emite cuando el bucle de eventos del hilo acaba de parar, pero
        # `.quit()` NO espera a que el hilo del SO termine realmente de desenrollarse — solo
        # `.wait()` lo confirma de forma síncrona. Sin esto, `deleteLater()` puede dejar el
        # wrapper SIP/Qt del hilo en un estado a medio cerrar durante una ventana muy breve;
        # si un ciclo del recolector GENERACIONAL de Python (no el simple refcounting) cae
        # justo ahí mientras visita objetos rastreados, puede colgarse de forma intermitente
        # — visto realmente en los tests de este asistente. `hilo=` por valor (no `self.
        # _commit_thread`, que podría cambiar) deja el `wait()` siempre sobre el hilo correcto.
        hilo = self._commit_thread
        hilo.finished.connect(lambda hilo=hilo: (hilo.wait(), hilo.deleteLater()))
        self._commit_thread.start()

    def _commit_progreso(self, hecho, total):
        total_seguro = max(1, total)
        pct = max(0, min(100, int(hecho * 100 / total_seguro)))
        self._barra_progreso.setValue(pct)
        tamano_lote = 300
        n_lote = max(1, -(-hecho // tamano_lote)) if hecho else 1
        total_lotes = max(1, -(-total // tamano_lote))
        self._lbl_carga_estado.setText(
            f"Procesando lote {min(n_lote, total_lotes)}/{total_lotes} ({hecho} de {total} registros)…")

    def _cancelar_commit(self):
        if self._commit_worker is not None:
            self._commit_worker.cancelar()
        self._btn_cancelar_carga.setEnabled(False)
        self._btn_cancelar_carga.setText("Cancelando… (los lotes ya confirmados no se deshacen)")

    def _commit_ok(self, r):
        self._commit_resultado = r
        self._barra_progreso.setValue(100)
        self._lbl_carga_estado.setText(
            "Procesamiento cancelado por el usuario." if r.get("cancelado") else "Carga completada.")
        self._render_resumen(r)
        self._ir(4)

    def _commit_error(self, msg):
        self._banner_carga_info.set_mensaje(f"No se pudo completar la carga: {msg}")
        self._banner_carga_info.setVisible(True)
        self._btn_cancelar_carga.setEnabled(False)
        self._btn_cancelar_carga.setText("✖ Cancelar procesamiento")

    def _confirmar_y_ejecutar(self):
        n = self._registros_a_importar()
        if n <= 0:
            self._aviso("No hay registros válidos ni con advertencia para importar.", "advertencia")
            return
        etiqueta = _ENTIDADES_LABEL.get(self._entidad, self._entidad)
        msg = (f"Vas a importar {n} registro(s) de «{etiqueta}». Las filas con error se omitirán "
              "automáticamente. ¿Deseas continuar?")
        if mostrar_confirmacion is not None and not mostrar_confirmacion(self, "Migración de datos", msg):
            return
        self._ir(3)
        self._iniciar_commit()

    # ══════════════════════════════════════════════════════════════════════
    # Paso 5 — Resumen
    # ══════════════════════════════════════════════════════════════════════
    def _paso_resumen(self):
        w = QWidget(); v = QVBoxLayout(w); v.setSpacing(14)
        v.addWidget(_titulo("5 · Resumen"))
        self._banner_resumen = EnterpriseInlineBanner("", rol="advertencia")
        self._banner_resumen.setVisible(False)
        v.addWidget(self._banner_resumen)
        self._grid_resumen = EnterpriseDashboardGrid(columnas=3)
        v.addWidget(self._grid_resumen)
        fila = QHBoxLayout()
        fila.addWidget(_btn("👁 Ver registros en el módulo destino", self._ver_modulo_destino, primary=True))
        fila.addWidget(_btn("⬇ Descargar reporte completo (CSV/JSON)", self._descargar_reporte))
        fila.addWidget(_btn("🔄 Realizar otra importación", self._reiniciar_asistente))
        fila.addStretch()
        v.addLayout(fila)
        v.addStretch()
        return w

    def _render_resumen(self, r):
        self._grid_resumen.limpiar()
        self._grid_resumen.add_card(EnterpriseCard("Total del lote", str(r.get("total", 0)), modo="kpi"))
        self._grid_resumen.add_card(EnterpriseCard("Confirmados", str(r.get("confirmados", 0)),
                                                   modo="riesgo", riesgo="OK"))
        self._grid_resumen.add_card(EnterpriseCard("Fallidos", str(r.get("fallidos", 0)), modo="riesgo",
                                                   riesgo=("CRITICO" if r.get("fallidos") else "OK")))
        if r.get("cancelado"):
            self._banner_resumen.set_mensaje(
                "Se canceló el procesamiento antes de terminar el lote entero: los registros YA "
                "confirmados antes de cancelar SE MANTIENEN (no se deshacen); el resto se quedó sin "
                "procesar — puedes reintentarlo con una nueva importación.")
            self._banner_resumen.setVisible(True)
        else:
            self._banner_resumen.setVisible(False)

    def _ver_modulo_destino(self):
        v_id = _V_ID_DESTINO.get(self._entidad)
        if not v_id or self.main is None or not hasattr(self.main, "abrir_ventana_por_id"):
            self._aviso("No hay un módulo destino disponible para navegar automáticamente desde aquí.",
                        "info")
            return
        try:
            self.main.abrir_ventana_por_id(v_id)
        except Exception as e:
            self._aviso(f"No se pudo abrir el módulo destino: {e}", "advertencia")

    def _descargar_reporte(self):
        r = self._commit_resultado or {}
        id_trabajo = r.get("id_trabajo")
        errores = _imp.errores_trabajo(id_trabajo) if id_trabajo else []
        resumen = {"entidad": self._entidad, "origen": self._origen_nombre, "id_trabajo": id_trabajo,
                  "total": r.get("total"), "confirmados": r.get("confirmados"),
                  "fallidos": r.get("fallidos"), "cancelado": r.get("cancelado")}
        _exportar_informe(self, errores, resumen, f"migracion_{self._entidad}")

    def _reiniciar_asistente(self):
        self._reset_estado()
        self.cb_entidad.setCurrentIndex(0)
        self.lbl_ruta.setText("Ningún fichero seleccionado.")
        self.in_url.clear(); self.in_query.clear(); self.in_api.clear()
        self.lbl_estado_fuente.setText("")
        self._banner_contextual.setVisible(False)
        self._cambiar_modo_origen(0)
        self._ir(0)

    # ══════════════════════════════════════════════════════════════════════
    # Navegación del asistente
    # ══════════════════════════════════════════════════════════════════════
    def _ir(self, idx):
        self._stack.setCurrentIndex(idx)
        for i, d in enumerate(self._dots):
            d.setStyleSheet(_qss_dot(i == idx, i < idx))
        ocultar_nav = idx >= 3   # Carga Definitiva y Resumen llevan sus propios controles
        self._wrap_nav.setVisible(not ocultar_nav)
        if not ocultar_nav:
            self._btn_atras.setVisible(idx > 0)
            if idx == 0:
                self._btn_sig.setText("Siguiente →")
            elif idx == 1:
                self._btn_sig.setText("Simular y Validar ▶")
            elif idx == 2:
                self._btn_sig.setText(f"Ejecutar Importación Real ({self._registros_a_importar()} "
                                      "Registros) 🚀")
            self._actualizar_estado_boton_siguiente()
        if idx == 2:
            self._iniciar_diagnostico()

    def _atras(self):
        idx = self._stack.currentIndex()
        if idx > 0:
            self._ir(idx - 1)

    def _siguiente(self):
        idx = self._stack.currentIndex()
        if idx == 0:
            if not self._filas:
                self._aviso("Carga primero un origen de datos válido.", "advertencia")
                return
            self._construir_mapeo_paso2()
            self._pintar_tabla_muestra()
            self._ir(1)
        elif idx == 1:
            mapeo = _leer_mapeo(self._combos)
            faltan = [_ETIQUETAS.get(c, c) for c, (req, _s) in _modelo.CAMPOS.get(self._entidad, {}).items()
                     if req and c not in mapeo]
            if faltan:
                self._aviso("Debes asignar la(s) columna(s) obligatoria(s): " + ", ".join(faltan) + ".",
                            "advertencia")
                return
            self._ir(2)
        elif idx == 2:
            self._confirmar_y_ejecutar()

    def _actualizar_estado_boton_siguiente(self):
        idx = self._stack.currentIndex()
        if idx == 0:
            self._btn_sig.setEnabled(bool(self._filas))
        elif idx == 1:
            mapeo = _leer_mapeo(self._combos) if self._combos else {}
            faltan = [c for c, (req, _s) in _modelo.CAMPOS.get(self._entidad, {}).items()
                     if req and c not in mapeo]
            if faltan:
                etiquetas = [_ETIQUETAS.get(c, c) for c in faltan]
                self._banner_mapeo_incompleto.set_mensaje(
                    "Faltan campos obligatorios por asignar: " + ", ".join(etiquetas) + ".")
            self._banner_mapeo_incompleto.setVisible(bool(faltan))
            self._btn_sig.setEnabled(not faltan)
        elif idx == 2:
            self._btn_sig.setEnabled((not self._diagnostico_en_curso) and self._registros_a_importar() > 0)
            self._btn_sig.setText(f"Ejecutar Importación Real ({self._registros_a_importar()} Registros) 🚀")


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# "Documentos" — SIN TOCAR (ya correctamente arquitecturado/enrutado a dominio, fuera de alcance).
# ══════════════════════════════════════════════════════════════════════════════════════════════════
class _ImportarDocumentos(QWidget):
    """Importación masiva de documentos históricos (`services.importacion.importar_documentos` →
    `db.documentos.registrar_documento`, sin ninguna superficie hasta esta auditoría)."""

    def __init__(self, usuario=None):
        super().__init__()
        self.setStyleSheet(f"background:{T.BG};")
        self.usuario = usuario or {}
        self._rutas = []
        ly = QVBoxLayout(self); ly.setSpacing(10)
        sub = QLabel("Registra en el centro documental ficheros ya existentes (facturas, contratos, "
                    "albaranes… escaneados o exportados de otro sistema) como adjuntos de solo lectura.")
        sub.setStyleSheet(f"color:{T.DIM};"); sub.setWordWrap(True)
        ly.addWidget(_titulo("Importar documentos históricos"))
        ly.addWidget(sub)

        from src.db.documentos import TIPOS as _TIPOS_DOC
        self.cb_tipo = QComboBox()
        self.cb_tipo.setStyleSheet(f"QComboBox{{background:{T.BG};color:{T.TEXT};border:1px solid "
                                   f"{T.INFO};border-radius:8px;padding:5px 10px;min-width:220px;}}"
                                   f"QComboBox::drop-down{{border:none;width:22px;background:transparent;}}")
        for tipo in _TIPOS_DOC:
            self.cb_tipo.addItem(tipo.replace("_", " ").capitalize(), tipo)
        fila = QHBoxLayout()
        btn_seleccionar_doc = _btn("📂 Seleccionar documentos", self._seleccionar)
        btn_seleccionar_doc.setMinimumWidth(btn_seleccionar_doc.sizeHint().width() + 16)
        fila.addWidget(btn_seleccionar_doc)
        fila.addWidget(QLabel("Tipo:")); fila.addWidget(self.cb_tipo)
        fila.addStretch()
        btn_importar_doc = _btn("✅ Importar documentos", self._importar)
        btn_importar_doc.setMinimumWidth(btn_importar_doc.sizeHint().width() + 16)
        fila.addWidget(btn_importar_doc)
        ly.addLayout(fila)
        self.lbl_rutas = QLabel("Ningún documento seleccionado."); self.lbl_rutas.setWordWrap(True)
        self.lbl_rutas.setStyleSheet(f"color:{T.TEXT};")
        ly.addWidget(self.lbl_rutas)
        self.txt_resultado = QTextEdit(); self.txt_resultado.setReadOnly(True)
        self.txt_resultado.setStyleSheet(f"QTextEdit{{background:{T.BG};color:{T.TEXT};border:1px solid "
                                         f"{T.INFO};border-radius:8px;padding:8px;}}")
        ly.addWidget(self.txt_resultado, 1)

    def _emp(self):
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return None

    def _seleccionar(self):
        rutas, _ = QFileDialog.getOpenFileNames(self, "Selecciona los documentos")
        if rutas:
            self._rutas = rutas
            self.lbl_rutas.setText(f"{len(rutas)} documento(s) seleccionado(s).")

    def _importar(self):
        if not self._rutas:
            self._aviso("Selecciona al menos un documento.", "warning")
            return
        # `importar_documentos` reenvía `usuario` como `id_usuario` (INT) a `registrar_documento` —
        # a diferencia de `_imp.ejecutar`/`importar_desde_bd`, que lo guardan como etiqueta de texto.
        res = _imp.importar_documentos(self._rutas, tipo=self.cb_tipo.currentData(), id_empresa=self._emp(),
                                       usuario=self.usuario.get("id"))
        txt = f"Registrados: {res.get('registrados', 0)} de {len(self._rutas)}."
        if res.get("errores"):
            txt += "\n\nErrores:\n" + "\n".join(f"  · {e['ruta']}: {e['motivo']}" for e in res["errores"][:20])
        self.txt_resultado.setPlainText(txt)
        self._aviso(f"Importación completada: {res.get('registrados', 0)} documento(s).", "info")
        self._rutas = []
        self.lbl_rutas.setText("Ningún documento seleccionado.")

    def _aviso(self, msg, tipo="warning"):
        if mostrar_mensaje:
            mostrar_mensaje(self, "Migración de datos", msg, tipo)
        else:  # pragma: no cover
            logger.info("migracion: %s", msg)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# Historial — drill-down por trabajo + exportación del informe de errores (Fase B).
# ══════════════════════════════════════════════════════════════════════════════════════════════════
class _DetalleTrabajoDialog(QDialog):
    """Detalle fila a fila de UNA importación ya ejecutada (`import_trabajos_errores`, vía
    `services.importacion.errores_trabajo`)."""

    def __init__(self, parent, trabajo):
        super().__init__(parent)
        self._trabajo = trabajo or {}
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(_tam_pantalla_completa(parent))
        # Sin el contorno neón cian global (`QDialog{border:2px solid CIAN}`, estilo_global.py):
        # esta ventana ocupa toda la ventana anfitriona (ver `_tam_pantalla_completa`).
        self.setObjectName("dlg_detalle_trabajo")
        self.setStyleSheet("#dlg_detalle_trabajo { border: none; }")

        main = QVBoxLayout(self)
        cont = QWidget(); _marco_dialogo(cont, bg=T.BG, nombre="marco_detalle_trabajo")
        main.addWidget(cont)
        ly = QVBoxLayout(cont); ly.setContentsMargins(24, 20, 24, 20); ly.setSpacing(12)

        cab = QHBoxLayout()
        t = QLabel(f"Detalle · {self._trabajo.get('fichero') or self._trabajo.get('entidad') or '—'}")
        t.setStyleSheet(f"color:{T.INFO};font-size:16px;font-weight:900;")
        cab.addWidget(t); cab.addStretch()
        cab.addWidget(_btn("✕", self.accept, color=T.CRITICO))
        ly.addLayout(cab)

        resumen = QLabel(
            f"Entidad: {self._trabajo.get('entidad')} · Total: {self._trabajo.get('filas_total')} · "
            f"OK: {self._trabajo.get('filas_ok')} · Error: {self._trabajo.get('filas_error')} · "
            f"Estado: {self._trabajo.get('estado')} · Usuario: {self._trabajo.get('usuario') or '—'}")
        resumen.setStyleSheet(f"color:{T.TEXT};font-size:12px;")
        resumen.setWordWrap(True)
        ly.addWidget(resumen)

        self._errores = _imp.errores_trabajo(self._trabajo.get("id"))
        self.tabla = EnterpriseTable(["Fila", "Campo", "Valor", "Severidad", "Motivo"])
        self.tabla.set_datos([[e.get("numero_fila"), e.get("campo") or "—", e.get("valor_original") or "—",
                              e.get("severidad"), e.get("motivo")] for e in self._errores])
        ly.addWidget(self.tabla, 1)
        if not self._errores:
            aviso = QLabel("Esta importación no tiene detalle de errores registrado (ninguna fila con "
                          "error/advertencia, o es de una versión anterior del motor).")
            aviso.setStyleSheet(f"color:{T.DIM};font-size:11px;")
            aviso.setWordWrap(True)
            ly.addWidget(aviso)

        botones = QHBoxLayout()
        botones.addWidget(_btn("⬇ Descargar informe de errores (CSV/JSON)", self._descargar, primary=True))
        botones.addStretch()
        ly.addLayout(botones)

    def _descargar(self):
        resumen = {k: self._trabajo.get(k) for k in
                  ("fichero", "entidad", "formato", "filas_total", "filas_ok", "filas_error", "estado",
                   "usuario")}
        _exportar_informe(self, self._errores, resumen, f"historial_{self._trabajo.get('id')}")


class _Historial(QWidget):
    """Historial de trabajos de importación (`services.importacion.trabajos_recientes`). Doble clic en
    una fila abre el drill-down por trabajo (`_DetalleTrabajoDialog`)."""

    def __init__(self, usuario=None):
        super().__init__()
        self.setStyleSheet(f"background:{T.BG};")
        self.usuario = usuario or {}
        self._trabajos = []
        ly = QVBoxLayout(self); ly.setSpacing(10)
        fila = QHBoxLayout()
        fila.addWidget(_titulo("Historial de importaciones"))
        fila.addStretch()
        fila.addWidget(_btn_cargando("🔄 Actualizar", self._cargar))
        ly.addLayout(fila)
        nota = QLabel("Doble clic en una fila para ver el detalle (errores/advertencias por fila) de esa "
                     "importación.")
        nota.setStyleSheet(f"color:{T.DIM};font-size:11px;")
        ly.addWidget(nota)
        self.tabla = EnterpriseTable(["Fichero/origen", "Entidad", "Formato", "Total", "OK", "Error",
                                      "Estado", "Usuario"])
        self.tabla.tabla.cellDoubleClicked.connect(lambda *_: self._abrir_detalle())
        ly.addWidget(self.tabla, 1)
        fila2 = QHBoxLayout()
        fila2.addWidget(_btn("⬇ Descargar informe de errores (fila seleccionada)", self._descargar_seleccion))
        fila2.addStretch()
        ly.addLayout(fila2)
        self._cargar()

    def _emp(self):
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return None

    def _cargar(self):
        self._trabajos = _imp.trabajos_recientes(self._emp())
        datos = []
        for t in self._trabajos:
            datos.append([t.get("fichero"), t.get("entidad"), t.get("formato"), t.get("filas_total"),
                         t.get("filas_ok"), t.get("filas_error"), t.get("estado"), t.get("usuario")])
        self.tabla.set_datos(datos)

    def _sel(self):
        fila = self.tabla.tabla.currentRow()
        if fila < 0 or fila >= len(self._trabajos):
            return None
        return self._trabajos[fila]

    def _abrir_detalle(self):
        t = self._sel()
        if t is None:
            return
        from src.gui.transiciones import abrir_dialogo_deslizante
        dlg = _DetalleTrabajoDialog(self, t)
        abrir_dialogo_deslizante(dlg, self)

    def _descargar_seleccion(self):
        t = self._sel()
        if t is None:
            self._aviso("Selecciona una importación de la tabla.", "info")
            return
        if not (t.get("filas_error") or 0):
            self._aviso("Esta importación no tiene filas con error.", "info")
            return
        errores = _imp.errores_trabajo(t.get("id"))
        resumen = {k: t.get(k) for k in
                  ("fichero", "entidad", "formato", "filas_total", "filas_ok", "filas_error", "estado",
                   "usuario")}
        _exportar_informe(self, errores, resumen, f"historial_{t.get('id')}")

    def _aviso(self, msg, tipo="warning"):
        if mostrar_mensaje:
            mostrar_mensaje(self, "Migración de datos", msg, tipo)
        else:  # pragma: no cover
            logger.info("migracion: %s", msg)


class MigracionDatosWindow(QtEnterpriseWindow):
    """Ventana Enterprise 'Migración de datos' (v_id 'migracion'). Aloja el asistente de 5 pasos."""

    titulo_ventana = "Migración de datos"
    concepto = None

    def closeEvent(self, event):
        # Libera el bloqueo de "cambiar de centro" al cerrar — `destroyed` del widget embebido NO es
        # fiable aquí (un `QWidget` hijo no recibe su propio cierre cuando cierra la ventana
        # contenedora; verificado: `deleteLater()` + bombeo del bucle de eventos no garantiza que
        # `destroyed` llegue a disparar en una ventana de nivel superior). `closeEvent` de la propia
        # ventana SÍ es el punto determinista de "esto se ha cerrado de verdad".
        _estado_migracion["en_curso"] = False
        super().closeEvent(event)

    def _crear_pestanas(self):
        # "Importar catálogo" y "Conexión directa" CONVERGEN en el mismo asistente de 5 pasos (Paso 1
        # deja elegir fichero O conexión directa) — una única pestaña en vez de dos que mostrarían el
        # mismo wizard duplicado; decisión documentada en el docstring del módulo.
        self.registrar_pestana("Importar / Migrar datos", self._tab_importar, destacada=True)
        self.registrar_pestana("Documentos", self._tab_documentos)
        self.registrar_pestana("Historial", self._tab_historial)

    def _tab_importar(self):
        self.asistente = _AsistenteMigracion(usuario=self.usuario, main=self.main)
        return self.asistente

    def _tab_documentos(self):
        return _ImportarDocumentos(self.usuario)

    def _tab_historial(self):
        return _Historial(self.usuario)
