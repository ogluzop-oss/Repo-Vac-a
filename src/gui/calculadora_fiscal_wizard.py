"""
Calculadora Fiscal (Contabilidad) — asistente guiado de 5 pasos ("Smart Accounting", Fase D):
Perfil y Epígrafe → Importación Inteligente → Revisión de Gastos → Simulación → Generación.
Sustituye el antiguo asistente de 4 páginas + resultado (solo Impuesto de Sociedades) y fusiona
también el flujo de "Generar" de `gui/aeat_gui.py` para los modelos 130/303/111.

La GUI SOLO orquesta: toda la lógica vive en `services.contabilidad.calculadora_fiscal`
(Impuesto de Sociedades), `services.contabilidad.fiscal_perfil`/`fiscal_deducciones` (Fase A),
`services.contabilidad.posting.listar_gastos_completo` (Fase B, Libro de Gastos completo),
`services.contabilidad.factura_ocr_ia` (Fase D, lectura de facturas por IA) y
`services.aeat.modelo_130/303/111` + `services.aeat.base/estados` (Fase B). Mismo patrón de
navegación que `gui/onboarding_wizard.py` (QStackedWidget + barra Atrás/Siguiente), embebido
como una pestaña más de `contabilidad_gestion.py`.

**Cómo se preservaron los datos del antiguo asistente de Impuesto de Sociedades**: las 3
páginas antiguas "Operaciones"/"Empleados"/"Inversiones" (con sus campos ingresos/gastos/
plantilla/contrataciones/inversión I+D-Digitalización) NO se han eliminado — sus métodos
constructores (`_page_operaciones`/`_page_empleados`/`_page_inversiones`, sin cambios) ahora
se instancian DENTRO del nuevo Paso 4 ("Simulación"), en una sección plegable "Datos
adicionales para Impuesto de Sociedades" (oculta por defecto, con un botón para desplegarla).
`_entrada_actual()`/`_cargar_entrada()`/`_precargar_datos_reales()`/`_calcular()` siguen
operando exactamente igual sobre esos mismos widgets (`self.inp_ingresos`, etc.) — el cálculo
de Impuesto de Sociedades no ha perdido ninguna capacidad, solo ha cambiado de ubicación visual.

El indicador de pasos (1-5) es la única pieza de "chrome" fuera de `gui/components/` —
navegación del asistente, no una tabla/tarjeta/toolbar/badge (esas sí usan la librería
Enterprise en todas las páginas).
"""

import datetime as _dt
import logging

from PyQt6.QtCore import QStringListModel, QSize, Qt
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QCompleter, QDialog, QFileDialog, QHBoxLayout,
                             QInputDialog, QLabel, QScrollArea, QVBoxLayout, QWidget)

from src.gui.catalogo_gestion import _BG, _BG2, _BORDE, _CIAN, _DIM, _TEXT, _btn, _combo, _inp
from src.gui.components.enterprise import (EnterpriseCard, EnterpriseDashboardGrid,
                                           EnterpriseHelpTooltip, EnterpriseInlineBanner,
                                           EnterpriseTable)
from src.gui.transiciones import StackedActual

logger = logging.getLogger("gui.calculadora_fiscal_wizard")

try:
    from assets.estilo_global import estilizar_completer as _estilizar_completer
except Exception:  # pragma: no cover
    _estilizar_completer = None

try:
    from assets.estilo_global import mostrar_mensaje
except Exception:  # pragma: no cover
    mostrar_mensaje = None

try:
    from assets.estilo_global import mostrar_confirmacion
except Exception:  # pragma: no cover
    mostrar_confirmacion = None

_OK = "#3FB950"
_ADVERTENCIA = "#FFB020"


class _SinAnchoMinimo(QWidget):
    """QWidget cuyo ANCHO mínimo NUNCA refleja el de su layout — para contenedores puramente
    decorativos (p. ej. la barra de pasos del wizard) que no deben forzar un ancho mínimo en el
    padre solo por llevar varios widgets uno al lado de otro. El ALTO mínimo SÍ se conserva (el
    real, calculado por el propio layout): devolver (0, 0) en las dos dimensiones (versión
    anterior) colapsaba esta fila a 0px de alto en cuanto la ventana tenía poco espacio vertical
    (p. ej. embebido como pestaña de Contabilidad, compitiendo por alto con el resto del chrome
    del módulo) — Qt no recorta un contenedor por debajo de lo que sus hijos necesitan, así que
    con el contenedor a 0px los propios widgets (botones/"dots") se superponían con el paso
    siguiente del stack en vez de simplemente reservar menos ancho. Bug real reproducido de forma
    headless: a 1366×550 (y por debajo) `cab`/`_wrap_progreso` caían a `height()==0` con esta
    clase devolviendo (0, 0); con (0, alto-real) mantienen su alto y solo liberan el ancho."""

    def minimumSizeHint(self):
        return QSize(0, super().minimumSizeHint().height())


def _vaciar_layout(layout):
    """Elimina todos los widgets/sub-layouts de un layout SIN destruir el propio layout — para
    refrescar contenido dinámico (sugerencias de deducciones, filas de modelos AEAT) cada vez
    que se reentra en un paso, sin ir acumulando filas duplicadas."""
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.deleteLater()
            continue
        sub = item.layout()
        if sub is not None:
            _vaciar_layout(sub)


_PASOS = ["Perfil y Epígrafe", "Importación Inteligente", "Revisión de Gastos", "Simulación",
         "Generación"]

_TIPOS_ENTIDAD = [("Sociedad Limitada (SL)", "SL"), ("Sociedad Anónima (SA)", "SA"),
                  ("Autónomo", "AUTONOMO")]

_CCAA = [(n, n) for n in (
    "Andalucía", "Aragón", "Asturias", "Islas Baleares", "Canarias", "Cantabria",
    "Castilla-La Mancha", "Castilla y León", "Cataluña", "Extremadura", "Galicia",
    "Comunidad de Madrid", "Región de Murcia", "Comunidad Foral de Navarra", "País Vasco",
    "La Rioja", "Comunidad Valenciana", "Ceuta", "Melilla",
)]
_CCAA_CON_VACIO = [("(Cualquiera / regla nacional)", "")] + _CCAA
_TIPOS_ENTIDAD_CON_VACIO = [("(Cualquiera)", "")] + _TIPOS_ENTIDAD

_CONCEPTOS = [("tipo_general", "Tipo general (IS)"), ("empleo_indefinido", "Deducción empleo indefinido"),
             ("empleo_bonificado", "Deducción empleo bonificado"), ("id", "Deducción I+D"),
             ("digitalizacion", "Deducción digitalización")]
_CONCEPTOS_TXT = dict(_CONCEPTOS)
_UNIDADES = [("Porcentaje (%)", "pct"), ("Importe fijo (€)", "eur")]

# Paso 3 (Revisión de gastos): palabras clave usadas para decidir, de forma puramente textual y
# heurística, si una deducción sectorial "parece" ya reflejada en el gasto registrado. NO es una
# verificación contable rigurosa (no sabe si el importe/proporción deducida es correcta, solo si
# el concepto aparece mencionado) — ver honestidad documentada en `_cargar_revision_gastos`.
_PALABRAS_DEDUCCION = {
    "suministros_hogar": ["suministro", "luz", "electricidad", "gas", "agua", "internet", "telefono", "teléfono"],
    "dietas_manutencion": ["dieta", "manutenci", "restaurante", "comida", "menu", "menú"],
    "vehiculo": ["vehiculo", "vehículo", "combustible", "gasolina", "gasóleo", "kilometraje", " km"],
}

# Paso 4/5: explicación en lenguaje claro de cada modelo trimestral, reutilizada tanto en la
# fila de ayuda de la Simulación como en la Generación (mismo texto, un solo sitio de verdad).
_AYUDA_MODELOS = {
    "130": ("Modelo 130", "Un «pago fraccionado» es un anticipo trimestral de lo que "
           "probablemente te tocará pagar en tu declaración anual de la Renta — se descuenta "
           "luego de la cuota final, no es un impuesto aparte."),
    "303": ("Modelo 303", "Es la liquidación trimestral del IVA: lo que has cobrado de IVA a "
           "tus clientes menos lo que tú has pagado de IVA a tus proveedores."),
    "111": ("Modelo 111", "Son las retenciones de IRPF que ya le has descontado a tus "
           "empleados o a otros profesionales al pagarles — este modelo es solo para "
           "ingresarlas en Hacienda, no genera un gasto nuevo."),
}


def _num(txt):
    """Tolera coma decimal; nunca negativo (no tiene sentido un ingreso/gasto/nº de contrataciones
    negativo en este formulario)."""
    try:
        v = float(str(txt).strip().replace(".", "").replace(",", ".")) if "," in str(txt) \
            else float(str(txt).strip() or 0)
    except Exception:
        v = 0.0
    return max(0.0, v)


def _entero(txt):
    return int(_num(txt))


def _fmt_eur(v):
    return f"{v:,.2f} €".replace(",", "␟").replace(".", ",").replace("␟", ".")


def _aviso(parent, titulo, msg, nivel="info"):
    if mostrar_mensaje is not None:
        mostrar_mensaje(parent, titulo, msg, nivel=nivel)


def _lbl_seccion(txt):
    lb = QLabel(txt)
    lb.setStyleSheet(f"color:{_CIAN};font-size:16px;font-weight:900;font-family:'Segoe UI';"
                     "background:transparent;border:none;")
    return lb


def _agrandar(widget, delta=2, base=12):
    """Sube `delta` puntos el font-size de un `_inp`/`_combo` (parte del font-size base conocido de
    esos helpers, 12px) sin tocar el resto de su estilo ni el helper compartido con otros módulos."""
    widget.setStyleSheet(widget.styleSheet().replace(f"font-size:{base}px", f"font-size:{base + delta}px"))
    return widget


def _lbl_campo(txt, tooltip=None):
    lb = QLabel(txt)
    lb.setStyleSheet(f"color:{_TEXT};font-size:14px;font-weight:900;font-family:'Segoe UI';"
                     "background:transparent;border:none;")
    if tooltip:
        lb.setToolTip(tooltip)
    return lb


def _lbl_nota(txt, color=None):
    lb = QLabel(txt)
    lb.setWordWrap(True)
    lb.setStyleSheet(f"color:{color or _DIM};font-size:11px;background:transparent;border:none;")
    return lb


def _tam_pantalla_completa(parent):
    """Tamaño para que un diálogo de lista/tabla (Parámetros fiscales, Historial) ocupe toda la
    ventana — el contenido de una tabla necesita más espacio que un formulario pequeño. Usa el
    tamaño de la ventana anfitriona; si no hay parent, el de la pantalla principal."""
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
    from PyQt6.QtCore import QSize
    return QSize(1200, 800)


def _marco_dialogo(cont, *, bg, nombre):
    """Fondo+contorno del "cartón" de un diálogo frameless, SIEMPRE con un `#objectName` — un
    stylesheet sin selector cascada el borde/fondo a TODOS los descendientes (tablas, labels,
    botones incluidos), un problema real ya documentado en `contabilidad_gestion.py::_sidebar`."""
    cont.setObjectName(nombre)
    cont.setStyleSheet(f"#{nombre}{{background:{bg};border:2px solid {_CIAN};border-radius:15px;}}")


class CalculadoraFiscalWizard(QWidget):
    """Asistente de 5 pasos: Perfil y Epígrafe · Importación Inteligente · Revisión de Gastos ·
    Simulación · Generación. `usuario` opcional (solo para contexto de sesión, la empresa activa
    se resuelve igual que en el resto de Contabilidad)."""

    def __init__(self, usuario=None, parent=None):
        super().__init__(parent)
        self.usuario = usuario or {}
        self._ultimo_resultado = None
        self._deducciones_aceptadas = {}
        self._ruta_ocr = None
        self._periodo_modelos = None
        self._build()
        self._precargar_datos_reales()

    # ── construcción ──────────────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(14)

        cab = QHBoxLayout()
        t = QLabel("🧮  Calculadora Fiscal")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:900;background:transparent;")
        cab.addWidget(t)
        cab.addStretch(1)
        cab.addWidget(_btn("⚙️ Parámetros fiscales", self._abrir_parametros_fiscales, primary=True))
        cab.addWidget(_btn("🕑 Historial", self._abrir_historial, primary=True))
        # Igual que la barra de pasos: título + 2 botones medían 896px de ancho mínimo por sí
        # solos — envuelto en _SinAnchoMinimo para que no fuerce el ancho mínimo del wizard.
        _wrap_cab = _SinAnchoMinimo()
        _wrap_cab.setLayout(cab)
        root.addWidget(_wrap_cab)

        self._progreso = QHBoxLayout()
        self._progreso.setSpacing(8)
        self._dots = []
        for i, nombre in enumerate(_PASOS):
            d = QLabel(f"{i + 1}. {nombre}")
            d.setStyleSheet(self._qss_dot(False, False))
            self._dots.append(d)
            self._progreso.addWidget(d)
        self._progreso.addStretch(1)
        # La barra de pasos (5 "dots" con borde+padding) medía un ancho MÍNIMO alto ella sola —
        # es indicador visual, no contenido funcional, y era la mayor responsable de que
        # Contabilidad pidiera una ventana más ancha que la pantalla real del usuario (1366×768,
        # con la barra de tareas reduce el área útil) y Windows respondiera con una geometría
        # recortada (bug real confirmado por el log de eventos: contenido cortado a la derecha
        # SOLO tras visitar esta pestaña — mismo mecanismo ya identificado y corregido en el
        # sidebar de RRHH). `QLayout.SizeConstraint.SetNoConstraint` NO basta (solo afecta al
        # auto-resize en caliente, no a minimumSizeHint()) — hay que anular minimumSizeHint()
        # directamente en el contenedor.
        self._wrap_progreso = _SinAnchoMinimo()
        self._wrap_progreso.setLayout(self._progreso)
        root.addWidget(self._wrap_progreso)

        # StackedActual: el ancho del wizard depende SOLO del paso visible, no del máximo de
        # los 5 (evita que, p. ej., la tabla de Revisión de Gastos deje abultado el ancho mínimo
        # del paso de Perfil, recortando contenido — bug reportado como "se corta a la derecha").
        self._stack = StackedActual()
        root.addWidget(self._stack, 1)
        self._stack.addWidget(self._page_perfil())           # 0 — Paso 1 (Fase A, sin cambios)
        self._stack.addWidget(self._page_importacion())      # 1 — Paso 2 (nuevo, Fase D)
        self._stack.addWidget(self._page_revision_gastos())  # 2 — Paso 3 (nuevo, Fase D)
        self._stack.addWidget(self._page_simulacion())        # 3 — Paso 4 (nuevo, pliega el
                                                               #     antiguo Operaciones/Empleados/
                                                               #     Inversiones + resultado IS)
        self._stack.addWidget(self._page_generacion())        # 4 — Paso 5 (nuevo)

        # Animación de deslizamiento al cambiar de paso (mismo mecanismo que el resto de la app,
        # `gui/transiciones.py`) — el wizard construye sus 5 páginas de golpe (no son lazy), así que
        # basta instalarla una vez aquí, sin necesidad del re-barrido que sí hace falta con pestañas
        # perezosas (ver `instalar_pestanas_lazy`).
        try:
            from src.gui.transiciones import instalar_transicion_stack
            instalar_transicion_stack(self._stack)
        except Exception:
            pass

        nav = QHBoxLayout()
        self._btn_atras = _btn("←  Atrás", self._atras)
        self._btn_sig = _btn("Siguiente →", self._siguiente, primary=True)
        nav.addWidget(self._btn_atras)
        nav.addStretch(1)
        nav.addWidget(self._btn_sig)
        root.addLayout(nav)
        self._nav = nav

        self._ir(0)

    def _qss_dot(self, activo, completado):
        color = _CIAN if activo else (_OK if completado else _DIM)
        borde = _CIAN if activo else _BORDE
        return (f"QLabel{{color:{color};background:{_BG2};border:2px solid {borde};"
                f"border-radius:9px;padding:4px 12px;font-weight:800;font-size:14px;}}")

    # ── página: Paso 1 Perfil y Epígrafe (Fase A — SIN CAMBIOS) ────────────
    def _page_perfil(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(10)
        v.addWidget(_lbl_seccion("1. Perfil de la empresa"))
        v.addWidget(_lbl_campo("Tipo de entidad"))
        self.cmb_tipo_entidad = _agrandar(_combo(_TIPOS_ENTIDAD))
        v.addWidget(self.cmb_tipo_entidad)
        v.addWidget(_lbl_campo("Comunidad Autónoma"))
        self.cmb_ccaa = _agrandar(_combo(_CCAA_CON_VACIO))
        self.cmb_ccaa.currentIndexChanged.connect(self._actualizar_aviso_foral)
        v.addWidget(self.cmb_ccaa)
        nota = QLabel("El tipo de entidad y la Comunidad Autónoma se usan para elegir la regla fiscal "
                      "más específica (Parámetros fiscales). Si no hay ninguna regla propia de esa "
                      "CCAA/tipo de entidad, se usa la regla nacional.")
        nota.setWordWrap(True)
        nota.setStyleSheet(f"color:{_DIM};font-size:11px;background:transparent;border:none;")
        v.addWidget(nota)
        self.lbl_aviso_foral = QLabel(
            "⚠️ País Vasco y Navarra tienen normativa FORAL propia (Concierto/Convenio Económico), "
            "distinta de la general — este cálculo solo usará una regla foral si tú mismo la has dado "
            "de alta en «Parámetros fiscales» con esa Comunidad Autónoma.")
        self.lbl_aviso_foral.setWordWrap(True)
        self.lbl_aviso_foral.setStyleSheet(f"color:{_ADVERTENCIA};font-size:11px;font-weight:700;"
                                           "background:transparent;border:none;")
        self.lbl_aviso_foral.setVisible(False)
        v.addWidget(self.lbl_aviso_foral)

        v.addWidget(_lbl_campo("Epígrafe IAE (actividad económica)"))
        self.cmb_epigrafe = self._crear_combo_epigrafes()
        v.addWidget(_agrandar(self.cmb_epigrafe))
        nota_epi = QLabel("Busca por código o por nombre de tu actividad (p. ej. «pan», «abogado», "
                          "«transporte»). Al elegir uno, régimen de IRPF y modelos obligatorios de "
                          "abajo se rellenan solos.")
        nota_epi.setWordWrap(True)
        nota_epi.setStyleSheet(f"color:{_DIM};font-size:11px;background:transparent;border:none;")
        v.addWidget(nota_epi)

        v.addWidget(self._bloque_derivados_perfil())
        v.addStretch(1)
        return w

    def _crear_combo_epigrafes(self):
        """Combo editable con autocompletado (mismo patrón que `_combo_buscable` de
        `seguridad_gui.py`): el catálogo de epígrafes es pequeño (subconjunto representativo, no el
        listado oficial completo), así que se carga entero de golpe y se filtra en el propio cliente
        con un `QCompleter` (`MatchContains`) en vez de una consulta a la BD por cada pulsación."""
        from src.services.contabilidad import fiscal_perfil as FP
        try:
            catalogo = FP.buscar_epigrafes("")
        except Exception:
            catalogo = []
        opciones = [(f"{e['codigo']} — {e['descripcion']}", e["id"]) for e in catalogo]
        cb = _combo(opciones)
        cb.setEditable(True)
        cb.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        modelo = QStringListModel([etq for etq, _v in opciones])
        completer = QCompleter(modelo, cb)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        cb.setCompleter(completer)
        if _estilizar_completer is not None:
            try:
                _estilizar_completer(completer)
            except Exception:
                pass
        cb.setCurrentIndex(-1)
        cb.lineEdit().setPlaceholderText("Buscar epígrafe…")
        # `activated` (no `currentIndexChanged`/`currentTextChanged`): solo se dispara al ELEGIR de
        # verdad una opción de la lista (clic o Intro sobre una sugerencia), nunca en cada pulsación
        # de tecla mientras se escribe/filtra — evita reasignar el epígrafe letra a letra.
        cb.activated.connect(self._al_elegir_epigrafe)
        return cb

    def _bloque_derivados_perfil(self):
        """Campos derivados del epígrafe (régimen de IRPF + modelos 130/303/111 obligatorios):
        SOLO LECTURA por defecto (autorrellenados), editables si el usuario discrepa mediante el
        botón «✏️ Editar» — mismo criterio de "auto + override manual" que el campo de IVA automático
        de `gestion_usuarios.py` (país fiscal → IVA), aquí con un toggle explícito en vez de un campo
        maestro distinto."""
        cont = QWidget()
        v = QVBoxLayout(cont)
        v.setContentsMargins(0, 6, 0, 0)
        v.setSpacing(8)

        cab = QHBoxLayout()
        cab.addWidget(_lbl_campo("Régimen de IRPF y modelos obligatorios (autorrellenado)"))
        cab.addStretch(1)
        self.btn_editar_derivados = _btn("✏️ Editar", self._alternar_edicion_derivados)
        cab.addWidget(self.btn_editar_derivados)
        v.addLayout(cab)

        fila_regimen = QHBoxLayout()
        self.inp_regimen_irpf = _inp("(elige un epígrafe)")
        self.inp_regimen_irpf.setReadOnly(True)
        fila_regimen.addWidget(self.inp_regimen_irpf, 1)
        self.help_regimen = EnterpriseHelpTooltip(
            "Elige tu epígrafe para ver aquí el régimen de IRPF.", titulo="Régimen de IRPF")
        fila_regimen.addWidget(self.help_regimen)
        v.addLayout(fila_regimen)

        fila_modelos = QHBoxLayout()

        def _bloque_modelo(nombre, tooltip_inicial):
            col = QVBoxLayout()
            fila = QHBoxLayout()
            chk = QCheckBox(nombre)
            chk.setEnabled(False)
            chk.setStyleSheet(f"color:{_TEXT};font-weight:700;")
            fila.addWidget(chk)
            help_ = EnterpriseHelpTooltip(tooltip_inicial, titulo=nombre)
            fila.addWidget(help_)
            fila.addStretch(1)
            col.addLayout(fila)
            return col, chk, help_

        col130, self.chk_modelo_130, self.help_modelo_130 = _bloque_modelo(
            "Modelo 130", "Pago fraccionado de IRPF para autónomos en Estimación Directa.")
        col303, self.chk_modelo_303, self.help_modelo_303 = _bloque_modelo(
            "Modelo 303", "Declaración trimestral de IVA.")
        col111, self.chk_modelo_111, self.help_modelo_111 = _bloque_modelo(
            "Modelo 111", "Retenciones de IRPF si tienes personal contratado o pagas a otros "
            "profesionales reteniéndoles.")
        fila_modelos.addLayout(col130)
        fila_modelos.addLayout(col303)
        fila_modelos.addLayout(col111)
        v.addLayout(fila_modelos)

        self.lbl_sin_epigrafe = QLabel(
            "Sin epígrafe asignado todavía: elige uno arriba para autorrellenar esta sección.")
        self.lbl_sin_epigrafe.setWordWrap(True)
        self.lbl_sin_epigrafe.setStyleSheet(f"color:{_DIM};font-size:11px;background:transparent;"
                                            "border:none;")
        v.addWidget(self.lbl_sin_epigrafe)

        return cont

    def _alternar_edicion_derivados(self):
        editable = self.inp_regimen_irpf.isReadOnly()  # pasa de solo-lectura a editable
        self.inp_regimen_irpf.setReadOnly(not editable)
        for chk in (self.chk_modelo_130, self.chk_modelo_303, self.chk_modelo_111):
            chk.setEnabled(editable)
        self.btn_editar_derivados.setText("🔒 Bloquear" if editable else "✏️ Editar")

    def _al_elegir_epigrafe(self, _indice):
        from src.db.empresa import empresa_actual_id
        from src.services.contabilidad import fiscal_perfil as FP
        id_epigrafe = self.cmb_epigrafe.currentData()
        if id_epigrafe is None:
            return
        try:
            id_empresa = empresa_actual_id()
            FP.asignar_epigrafe(id_empresa, id_epigrafe)
            perfil = FP.perfil_fiscal_empresa(id_empresa)
        except Exception as e:
            _aviso(self, "Epígrafe IAE", f"No se pudo asignar el epígrafe: {e}", nivel="error")
            return
        self._poblar_derivados_perfil(perfil)

    _TXT_REGIMEN = {
        "estimacion_directa_simplificada": (
            "Estimación Directa Simplificada",
            "Llevas tus ingresos y gastos reales, sin estimaciones — el régimen más habitual hoy en "
            "día para autónomos. Tu impuesto se calcula sobre el beneficio real (ingresos menos "
            "gastos deducibles), no sobre una tabla de módulos."),
        "estimacion_directa_normal": (
            "Estimación Directa Normal",
            "Igual que la Simplificada (tributas por tu beneficio real), pero con obligaciones "
            "contables más completas — se aplica a partir de cierto volumen de facturación anual."),
        "modulos": (
            "Estimación Objetiva (Módulos)",
            "No tributas por tu beneficio real, sino por unos «módulos» (signos, índices o "
            "módulos: nº de empleados, superficie del local, potencia eléctrica…) fijados por "
            "Hacienda para tu actividad. Solo un catálogo reducido de actividades (comercio "
            "minorista de alimentación, hostelería, transporte, peluquerías…) puede acogerse a él "
            "hoy en día."),
    }

    def _poblar_derivados_perfil(self, perfil):
        if not perfil or perfil.get("sin_epigrafe"):
            self.inp_regimen_irpf.setText("")
            self.chk_modelo_130.setChecked(False)
            self.chk_modelo_303.setChecked(False)
            self.chk_modelo_111.setChecked(False)
            self.lbl_sin_epigrafe.setVisible(True)
            return
        self.lbl_sin_epigrafe.setVisible(False)

        regimen = perfil.get("regimen_irpf")
        nombre_regimen, texto_regimen = self._TXT_REGIMEN.get(regimen, (regimen or "—", ""))
        self.inp_regimen_irpf.setText(nombre_regimen)
        if texto_regimen:
            self.help_regimen.set_texto(texto_regimen)

        epigrafes_txt = ", ".join(f"{e['codigo']} ({e['descripcion']})" for e in perfil.get("epigrafes", []))

        self.chk_modelo_130.setChecked(bool(perfil.get("modelo_130")))
        self.help_modelo_130.set_texto({
            "resumen": "Pago fraccionado de IRPF para autónomos en Estimación Directa (Simplificada "
            "o Normal): un anticipo trimestral de lo que se calcula que tocará pagar en la "
            "declaración anual de la Renta.",
            "por_que": ("es obligatorio para tu actividad." if perfil.get("modelo_130")
                       else "no es obligatorio para tu actividad concreta."),
            "datos": {"Epígrafe(s)": epigrafes_txt} if epigrafes_txt else None,
            "consecuencias": "En régimen de Módulos este pago fraccionado se declara en el Modelo "
            "131, no en el 130." if regimen == "modulos" else "",
        })

        self.chk_modelo_303.setChecked(bool(perfil.get("modelo_303")))
        self.help_modelo_303.set_texto({
            "resumen": "Declaración trimestral del IVA repercutido en tus ventas menos el soportado "
            "en tus compras.",
            "por_que": ("tu actividad está sujeta a IVA." if perfil.get("modelo_303") else
                       "tu actividad está EXENTA de IVA (art. 20 de la Ley del IVA — sanidad, "
                       "enseñanza reglada, servicios financieros o seguros)."),
            "datos": {"Epígrafe(s)": epigrafes_txt} if epigrafes_txt else None,
        })

        self.chk_modelo_111.setChecked(bool(perfil.get("modelo_111")))
        self.help_modelo_111.set_texto({
            "resumen": "Retenciones de IRPF practicadas a tus empleados (nóminas) o a otros "
            "profesionales a los que pagas facturas con retención.",
            "por_que": "solo se presenta SI tienes personal contratado o retienes a algún "
            "profesional — no depende únicamente del epígrafe.",
            "datos": {"Epígrafe(s)": epigrafes_txt} if epigrafes_txt else None,
        })

    def _actualizar_aviso_foral(self):
        ccaa = self.cmb_ccaa.currentData()
        self.lbl_aviso_foral.setVisible(bool(ccaa) and ccaa in ("País Vasco", "Comunidad Foral de Navarra"))

    # ── página: Paso 2 Importación inteligente (NUEVO, Fase D) ─────────────
    def _page_importacion(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(10)
        v.addWidget(_lbl_seccion("2. Importación inteligente de documentos"))
        v.addWidget(_lbl_nota(
            "Sube una imagen o PDF de una factura de proveedor: la IA de Claude (si está "
            "configurada en este equipo) extrae proveedor/NIF/fecha/base/cuota de IVA/total como "
            "un BORRADOR editable. Revísalo y corrígelo si hace falta — NUNCA se crea ninguna "
            "factura de compra real sin que tú lo confirmes explícitamente abajo."))

        self.lbl_aviso_ia_ocr = QLabel("")
        self.lbl_aviso_ia_ocr.setWordWrap(True)
        self.lbl_aviso_ia_ocr.setStyleSheet(f"color:{_ADVERTENCIA};font-size:11px;font-weight:700;"
                                            "background:transparent;border:none;")
        self.lbl_aviso_ia_ocr.setVisible(False)
        v.addWidget(self.lbl_aviso_ia_ocr)

        fila_archivo = QHBoxLayout()
        self.lbl_archivo_ocr = QLabel("(ningún archivo seleccionado)")
        self.lbl_archivo_ocr.setStyleSheet(f"color:{_TEXT};font-size:12px;background:transparent;"
                                           "border:none;")
        fila_archivo.addWidget(self.lbl_archivo_ocr, 1)
        fila_archivo.addWidget(_btn("📎 Seleccionar factura", self._elegir_archivo_ocr, primary=True))
        self.btn_extraer_ocr = _btn("🔎 Extraer con IA", self._extraer_factura_ocr, primary=True)
        fila_archivo.addWidget(self.btn_extraer_ocr)
        v.addLayout(fila_archivo)

        v.addWidget(_lbl_campo("Borrador de factura (editable antes de confirmar)"))
        fila1 = QHBoxLayout()
        self.inp_ocr_nif = _inp("NIF/CIF del proveedor")
        self.inp_ocr_proveedor = _inp("Razón social del proveedor")
        fila1.addWidget(self.inp_ocr_nif)
        fila1.addWidget(self.inp_ocr_proveedor, 1)
        v.addLayout(fila1)
        fila2 = QHBoxLayout()
        self.inp_ocr_numero = _inp("Nº de factura")
        self.inp_ocr_fecha = _inp("Fecha (AAAA-MM-DD)")
        fila2.addWidget(self.inp_ocr_numero)
        fila2.addWidget(self.inp_ocr_fecha)
        v.addLayout(fila2)
        fila3 = QHBoxLayout()
        self.inp_ocr_base = _inp("Base imponible (€)")
        self.inp_ocr_cuota = _inp("Cuota de IVA (€)")
        self.inp_ocr_total = _inp("Total (€, informativo)")
        fila3.addWidget(self.inp_ocr_base)
        fila3.addWidget(self.inp_ocr_cuota)
        fila3.addWidget(self.inp_ocr_total)
        v.addLayout(fila3)

        self.lbl_estado_ocr = QLabel("")
        self.lbl_estado_ocr.setWordWrap(True)
        self.lbl_estado_ocr.setStyleSheet(f"color:{_DIM};font-size:11px;background:transparent;"
                                          "border:none;")
        v.addWidget(self.lbl_estado_ocr)

        v.addWidget(_btn("✅ Confirmar y crear factura de compra", self._confirmar_factura_ocr,
                        primary=True))
        v.addStretch(1)
        return w

    def _actualizar_aviso_ia_ocr(self):
        try:
            from src.services.contabilidad import factura_ocr_ia as OCR
            disponible = OCR.disponible()
        except Exception:
            disponible = False
        if disponible:
            self.lbl_aviso_ia_ocr.setVisible(False)
            self.btn_extraer_ocr.setEnabled(True)
        else:
            self.lbl_aviso_ia_ocr.setText(
                "⚠️ IA no disponible en este equipo (falta el paquete «anthropic» o la variable de "
                "entorno ANTHROPIC_API_KEY): puedes seguir usando este paso — solo tendrás que "
                "rellenar el borrador de la factura a mano en vez de que la IA lo proponga.")
            self.lbl_aviso_ia_ocr.setVisible(True)
            self.btn_extraer_ocr.setEnabled(False)

    def _elegir_archivo_ocr(self):
        ruta, _f = QFileDialog.getOpenFileName(
            self, "Seleccionar factura", "",
            "Imágenes/PDF (*.png *.jpg *.jpeg *.gif *.webp *.pdf)")
        if ruta:
            self._ruta_ocr = ruta
            self.lbl_archivo_ocr.setText(ruta.replace("\\", "/").rsplit("/", 1)[-1])

    def _extraer_factura_ocr(self):
        from src.services.contabilidad import factura_ocr_ia as OCR
        if not self._ruta_ocr:
            _aviso(self, "Importación inteligente", "Selecciona primero un archivo.", nivel="advertencia")
            return
        r = OCR.extraer_factura(self._ruta_ocr)
        if not r.get("ok"):
            _aviso(self, "Importación inteligente", f"No se pudo extraer: {r.get('error')}", nivel="error")
            return
        d = r.get("datos") or {}
        self.inp_ocr_nif.setText(str(d.get("nif") or ""))
        self.inp_ocr_proveedor.setText(str(d.get("proveedor") or ""))
        self.inp_ocr_numero.setText(str(d.get("numero_factura") or ""))
        self.inp_ocr_fecha.setText(str(d.get("fecha") or ""))
        self.inp_ocr_base.setText(str(d.get("base") or ""))
        self.inp_ocr_cuota.setText(str(d.get("cuota_iva") or ""))
        self.inp_ocr_total.setText(str(d.get("total") or ""))
        self.lbl_estado_ocr.setText("Borrador extraído por IA — revisa y corrige los campos antes "
                                    "de confirmar.")

    def _confirmar_factura_ocr(self):
        nif = self.inp_ocr_nif.text().strip()
        razon = self.inp_ocr_proveedor.text().strip()
        if not (nif or razon):
            _aviso(self, "Importación inteligente",
                  "Indica al menos el NIF o la razón social del proveedor.", nivel="advertencia")
            return
        base = _num(self.inp_ocr_base.text())
        cuota = _num(self.inp_ocr_cuota.text())
        fecha = self.inp_ocr_fecha.text().strip() or None
        numero = self.inp_ocr_numero.text().strip() or None
        if mostrar_confirmacion and not mostrar_confirmacion(
                self, "Confirmar factura de compra",
                f"¿Crear la factura de compra de «{razon or nif}» por {_fmt_eur(base + cuota)} "
                "(base + cuota de IVA)? Esto SÍ escribe un registro real en Compras, contabiliza "
                "el gasto y queda sujeto al motor de exención/ISP si el proveedor es "
                "intracomunitario/extracomunitario."):
            return
        try:
            from src.db.empresa import empresa_actual_id
            from src.db import compras as _C
            from src.services.contabilidad import factura_ocr_ia as OCR
            id_empresa = empresa_actual_id()
            id_proveedor, creado = OCR.resolver_o_crear_proveedor(nif, razon, id_empresa=id_empresa)
            if not id_proveedor:
                _aviso(self, "Importación inteligente", "No se pudo resolver el proveedor.", nivel="error")
                return
            fid = _C.registrar_factura(
                id_proveedor=id_proveedor, numero_factura=numero, fecha_factura=fecha,
                base=base, iva=cuota,
                observaciones="Importada por IA (Calculadora Fiscal, Paso 2 — Importación Inteligente)",
                id_empresa=id_empresa)
        except Exception as e:
            _aviso(self, "Importación inteligente", f"No se pudo crear la factura: {e}", nivel="error")
            return
        if not fid:
            _aviso(self, "Importación inteligente", "No se pudo crear la factura.", nivel="error")
            return
        extra = " (proveedor nuevo dado de alta)" if creado else ""
        _aviso(self, "Importación inteligente", f"Factura de compra creada correctamente{extra}.",
              nivel="success")
        self.lbl_estado_ocr.setText(
            f"Última factura creada: proveedor «{razon or nif}», {_fmt_eur(base + cuota)}.")
        for inp in (self.inp_ocr_nif, self.inp_ocr_proveedor, self.inp_ocr_numero, self.inp_ocr_fecha,
                   self.inp_ocr_base, self.inp_ocr_cuota, self.inp_ocr_total):
            inp.clear()
        self._ruta_ocr = None
        self.lbl_archivo_ocr.setText("(ningún archivo seleccionado)")

    # ── página: Paso 3 Revisión de gastos (NUEVO, Fase D) ──────────────────
    def _page_revision_gastos(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(10)
        v.addWidget(_lbl_seccion("3. Revisión de gastos y maximización de deducciones"))
        v.addWidget(_lbl_nota(
            "Libro de Gastos COMPLETO del ejercicio (altas manuales + facturas reales de "
            "proveedor) y sugerencias de deducciones sectoriales de tu epígrafe que no parecen "
            "reflejadas todavía en tus gastos registrados."))

        self.tabla_gastos = EnterpriseTable(["Fecha", "Concepto", "Importe", "Origen"])
        v.addWidget(self.tabla_gastos, 1)

        v.addWidget(_lbl_campo("Sugerencias de deducciones"))
        self.cont_sugerencias = QWidget()
        self._layout_sugerencias = QVBoxLayout(self.cont_sugerencias)
        self._layout_sugerencias.setSpacing(8)
        scroll_sug = QScrollArea()
        scroll_sug.setWidgetResizable(True)
        scroll_sug.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        scroll_sug.setWidget(self.cont_sugerencias)
        scroll_sug.setMaximumHeight(220)
        v.addWidget(scroll_sug)

        self.lbl_sin_sugerencias = QLabel("Sin sugerencias pendientes en este momento.")
        self.lbl_sin_sugerencias.setStyleSheet(f"color:{_DIM};font-size:11px;background:transparent;"
                                               "border:none;")
        v.addWidget(self.lbl_sin_sugerencias)

        v.addWidget(_lbl_nota(
            "ℹ️ Aceptar una sugerencia te pedirá el importe/base o los días sobre los que se aplica "
            "y, a partir de ahí, se APLICA de verdad al cálculo del Paso 4 (Simulación) y del Modelo "
            "130 y del Impuesto de Sociedades que se generen en el Paso 5 — no es solo un "
            "recordatorio. Sigue siendo tu responsabilidad dar de alta el gasto real correspondiente "
            "en Contabilidad si procede (esto no crea ningún asiento nuevo).", color=_ADVERTENCIA))
        return w

    def _cargar_revision_gastos(self):
        from src.db.empresa import empresa_actual_id
        from src.services.contabilidad import fiscal_deducciones as FD
        from src.services.contabilidad import fiscal_perfil as FP
        from src.services.contabilidad import posting as _POST
        id_empresa = empresa_actual_id()
        anio = _dt.date.today().year
        gastos = _POST.listar_gastos_completo(anio=anio, id_empresa=id_empresa)
        datos = [[str(g.get("fecha") or ""), str(g.get("concepto") or ""),
                 _fmt_eur(float(g.get("importe") or 0)),
                 "Factura de compra" if g.get("origen") == "compra" else "Alta manual"]
                for g in gastos]
        self.tabla_gastos.set_datos(datos)

        _vaciar_layout(self._layout_sugerencias)
        perfil = FP.perfil_fiscal_empresa(id_empresa)
        conceptos_texto = " ".join((g.get("concepto") or "").lower() for g in gastos)
        vistos = set()
        sugerencias = []
        for epi in perfil.get("epigrafes", []):
            try:
                reglas = FD.resolver_deducciones(id_epigrafe=epi["id"], id_empresa=id_empresa)
            except Exception as e:
                logger.error("resolver_deducciones(%s): %s", epi.get("id"), e)
                continue
            for regla in reglas:
                if regla["concepto"] in vistos:
                    continue
                vistos.add(regla["concepto"])
                palabras = _PALABRAS_DEDUCCION.get(
                    regla["concepto"], [regla["concepto"].replace("_", " ")])
                aplicada = any(p in conceptos_texto for p in palabras)
                if not aplicada:
                    sugerencias.append(regla)
        self.lbl_sin_sugerencias.setVisible(not sugerencias)
        for regla in sugerencias:
            self._agregar_fila_sugerencia(regla)

    def _agregar_fila_sugerencia(self, regla):
        if regla.get("porcentaje") is not None:
            valor = f"{float(regla['porcentaje']):g}%"
        else:
            valor = _fmt_eur(float(regla.get("importe_fijo") or 0))
        nombre_concepto = regla["concepto"].replace("_", " ").capitalize()
        msg = (f"Posible deducción sectorial no aplicada: «{nombre_concepto}» ({valor}). No se han "
              "encontrado gastos registrados que mencionen este concepto.")
        cont = QWidget()
        lay = QHBoxLayout(cont)
        lay.setContentsMargins(0, 0, 0, 0)
        banner = EnterpriseInlineBanner(msg, rol="advertencia", texto_accion="✅ Aceptar y aplicar")
        banner.accion_pulsada.connect(lambda r=regla, c=cont: self._aceptar_sugerencia(r, c))
        lay.addWidget(banner, 1)
        lay.addWidget(_btn("✕ Descartar", lambda c=cont: c.setVisible(False)))
        self._layout_sugerencias.addWidget(cont)

    def _aceptar_sugerencia(self, regla, cont):
        """Convierte la regla (porcentaje o importe_fijo/día, sin ningún importe en euros todavía) en
        una deducción ACEPTADA con un `importe` concreto — pidiendo al usuario el dato que falta
        (base en euros para las de porcentaje, nº de días para las de importe_fijo/día). Nunca se
        inventa el importe: si el usuario cancela el diálogo, no se acepta nada."""
        from src.services.contabilidad import fiscal_deducciones as FD
        concepto = regla["concepto"]
        nombre = concepto.replace("_", " ").capitalize()
        if regla.get("porcentaje") is not None:
            pct = float(regla["porcentaje"])
            base, ok = QInputDialog.getDouble(
                self, "Aceptar deducción",
                f"«{nombre}» ({pct:g}%): indica el importe (€) acumulado del ejercicio sobre el que "
                "se aplica este porcentaje (p. ej., el total de gastos de suministros del hogar o de "
                "vehículo ya declarados hasta este trimestre).",
                0.0, 0.0, 10_000_000.0, 2)
            if not ok:
                return
            importe = round(base * pct / 100.0, 2)
        else:
            tarifa = float(regla.get("importe_fijo") or 0)
            dias, ok = QInputDialog.getInt(
                self, "Aceptar deducción",
                f"«{nombre}» ({_fmt_eur(tarifa)}/día): indica el número de días acumulados del "
                "ejercicio a los que corresponde.",
                0, 0, 366)
            if not ok:
                return
            importe = round(dias * tarifa, 2)
        self._deducciones_aceptadas[concepto] = {
            "concepto": concepto, "tipo": FD.tipo_deduccion(concepto), "importe": importe,
            "regla": regla,
        }
        cont.setVisible(False)
        _aviso(self, "Deducción aceptada",
              f"«{nombre}»: {_fmt_eur(importe)} aplicados como gasto deducible adicional. Se "
              "reflejará en el Paso 4 (Simulación) y en el Paso 5 (Generación).", nivel="success")

    def _deducciones_aceptadas_lista(self) -> list:
        """Transforma `self._deducciones_aceptadas` (dict vivo `concepto -> aceptación`, mutado en el
        Paso 3) en la lista plana que esperan `Modelo130`/`calculadora_fiscal.simular`. SIEMPRE lee
        el atributo en vivo (nunca cachea una copia) para que ir atrás al Paso 3, cambiar una
        aceptación y volver a avanzar al Paso 4/5 recalcule con el set actualizado, sin drift entre
        la vista previa y la generación final."""
        return [
            {"concepto": c, "tipo": d.get("tipo", "gasto"), "importe": float(d.get("importe") or 0)}
            for c, d in self._deducciones_aceptadas.items()
        ]

    # ── página: Paso 4 Simulación (NUEVO — pliega Operaciones/Empleados/ ──
    # ── Inversiones del antiguo asistente + resultado IS + modelos 130/303/111) ─
    def _page_simulacion(self):
        w = QWidget()
        v_outer = QVBoxLayout(w)
        v_outer.setContentsMargins(0, 0, 0, 0)
        v_outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        cont = QWidget()
        v = QVBoxLayout(cont)
        v.setSpacing(14)

        v.addWidget(_lbl_seccion("4. Pre-cálculo y simulación"))
        v.addWidget(_lbl_nota(
            "Cálculo EN VIVO con los motores REALES ya existentes (Impuesto de Sociedades + "
            "Modelo 130/303/111 si tu perfil los exige) — nada se genera ni se presenta todavía, "
            "esto es solo una vista previa antes del Paso 5."))

        # Sección plegable: los 3 antiguos pasos de datos de entrada del Impuesto de Sociedades
        # (Operaciones/Empleados/Inversiones) — mismos widgets/métodos que antes, solo reubicados.
        self.btn_toggle_datos_is = _btn(
            "▸ Datos adicionales para Impuesto de Sociedades (Operaciones/Empleados/Inversiones)",
            self._alternar_datos_is, primary=True)
        v.addWidget(self.btn_toggle_datos_is)
        self.cont_datos_is = QWidget()
        cl = QVBoxLayout(self.cont_datos_is)
        cl.setContentsMargins(0, 6, 0, 0)
        cl.setSpacing(16)
        cl.addWidget(self._page_operaciones())
        cl.addWidget(self._page_empleados())
        cl.addWidget(self._page_inversiones())
        self.cont_datos_is.setVisible(False)
        v.addWidget(self.cont_datos_is)

        cab_calc = QHBoxLayout()
        cab_calc.addWidget(_lbl_seccion("Resultado: Impuesto de Sociedades"))
        cab_calc.addStretch(1)
        cab_calc.addWidget(_btn("🔄 Recalcular", self._calcular_todo, primary=True))
        v.addLayout(cab_calc)

        self.lbl_aviso_faltantes = QLabel("")
        self.lbl_aviso_faltantes.setWordWrap(True)
        self.lbl_aviso_faltantes.setStyleSheet(f"color:{_ADVERTENCIA};font-size:12px;font-weight:700;"
                                               "background:transparent;border:none;")
        self.lbl_aviso_faltantes.setVisible(False)
        v.addWidget(self.lbl_aviso_faltantes)

        self.grid_resultado = EnterpriseDashboardGrid(columnas=4)
        v.addWidget(self.grid_resultado)

        self.lbl_deducciones_aceptadas = QLabel("")
        self.lbl_deducciones_aceptadas.setWordWrap(True)
        self.lbl_deducciones_aceptadas.setStyleSheet(
            f"color:{_DIM};font-size:11px;font-style:italic;background:transparent;border:none;")
        self.lbl_deducciones_aceptadas.setVisible(False)
        v.addWidget(self.lbl_deducciones_aceptadas)

        self.lbl_disclaimer = QLabel("")
        self.lbl_disclaimer.setWordWrap(True)
        self.lbl_disclaimer.setStyleSheet(f"color:{_DIM};font-size:10px;background:transparent;border:none;")
        v.addWidget(self.lbl_disclaimer)

        v.addWidget(_lbl_seccion("Resultado: modelos trimestrales (130/303/111)"))
        self.lbl_sin_epigrafe_modelos = QLabel(
            "Sin epígrafe asignado: vuelve al Paso 1 para saber qué modelos trimestrales aplican.")
        self.lbl_sin_epigrafe_modelos.setWordWrap(True)
        self.lbl_sin_epigrafe_modelos.setStyleSheet(f"color:{_DIM};font-size:11px;background:transparent;"
                                                    "border:none;")
        self.lbl_sin_epigrafe_modelos.setVisible(False)
        v.addWidget(self.lbl_sin_epigrafe_modelos)

        self._layout_ayuda_modelos = QVBoxLayout()
        self._layout_ayuda_modelos.setSpacing(4)
        v.addLayout(self._layout_ayuda_modelos)

        self.grid_modelos = EnterpriseDashboardGrid(columnas=3)
        v.addWidget(self.grid_modelos)

        v.addStretch(1)
        scroll.setWidget(cont)
        v_outer.addWidget(scroll, 1)
        return w

    def _alternar_datos_is(self):
        visible = not self.cont_datos_is.isVisible()
        self.cont_datos_is.setVisible(visible)
        flecha = "▾" if visible else "▸"
        self.btn_toggle_datos_is.setText(
            f"{flecha} Datos adicionales para Impuesto de Sociedades (Operaciones/Empleados/Inversiones)")

    def _calcular_todo(self):
        self._calcular()
        self._calcular_modelos_periodo()
        if self._deducciones_aceptadas:
            nombres = ", ".join(c.replace("_", " ") for c in self._deducciones_aceptadas)
            self.lbl_deducciones_aceptadas.setText(
                f"📌 Deducciones sectoriales aceptadas en «Revisión de gastos» YA aplicadas a los "
                f"cálculos de esta pantalla (Impuesto de Sociedades y Modelo 130): {nombres}. Vuelve "
                "al Paso 3 para revisarlas o quitarlas.")
            self.lbl_deducciones_aceptadas.setVisible(True)
        else:
            self.lbl_deducciones_aceptadas.setVisible(False)

    def _calcular_modelos_periodo(self):
        from src.db.empresa import empresa_actual_id
        from src.services.contabilidad import fiscal_perfil as FP
        id_empresa = empresa_actual_id()
        perfil = FP.perfil_fiscal_empresa(id_empresa)
        self.grid_modelos.limpiar()
        _vaciar_layout(self._layout_ayuda_modelos)
        self.lbl_sin_epigrafe_modelos.setVisible(bool(perfil.get("sin_epigrafe")))
        if perfil.get("sin_epigrafe"):
            self._periodo_modelos = None
            return
        hoy = _dt.date.today()
        ejercicio = hoy.year
        periodo = f"{(hoy.month - 1) // 3 + 1}T"
        self._periodo_modelos = (ejercicio, periodo)

        def _fila_ayuda(clave):
            nombre, texto = _AYUDA_MODELOS[clave]
            fila = QHBoxLayout()
            fila.addWidget(_lbl_campo(nombre))
            fila.addWidget(EnterpriseHelpTooltip(texto, titulo=nombre))
            fila.addStretch(1)
            self._layout_ayuda_modelos.addLayout(fila)

        if perfil.get("modelo_130"):
            _fila_ayuda("130")
            try:
                from src.services.aeat.modelo_130 import Modelo130
                m = Modelo130(ejercicio, periodo, id_empresa,
                              deducciones_aceptadas=self._deducciones_aceptadas_lista())
                self.grid_modelos.add_card(EnterpriseCard(
                    f"Modelo 130 ({periodo} {ejercicio})", _fmt_eur(m.resultado),
                    modo="kpi", subtitulo=m.sentido.capitalize()))
            except Exception as e:
                logger.error("Modelo130 en wizard: %s", e)
                self.grid_modelos.add_card(EnterpriseCard(
                    "Modelo 130", "—", subtitulo=f"No se pudo calcular: {e}"))
        if perfil.get("modelo_303"):
            _fila_ayuda("303")
            try:
                from src.services.aeat.modelo_303 import Modelo303
                m = Modelo303(ejercicio, periodo, id_empresa)
                self.grid_modelos.add_card(EnterpriseCard(
                    f"Modelo 303 ({periodo} {ejercicio})", _fmt_eur(m.resultado),
                    modo="kpi", subtitulo=m.sentido.capitalize()))
            except Exception as e:
                logger.error("Modelo303 en wizard: %s", e)
                self.grid_modelos.add_card(EnterpriseCard(
                    "Modelo 303", "—", subtitulo=f"No se pudo calcular: {e}"))
        if perfil.get("modelo_111"):
            _fila_ayuda("111")
            try:
                from src.services.aeat.modelo_111 import Modelo111
                m = Modelo111(ejercicio, periodo, id_empresa)
                self.grid_modelos.add_card(EnterpriseCard(
                    f"Modelo 111 ({periodo} {ejercicio})", _fmt_eur(m.resultado),
                    modo="kpi", subtitulo=m.sentido.capitalize()))
            except Exception as e:
                logger.error("Modelo111 en wizard: %s", e)
                self.grid_modelos.add_card(EnterpriseCard(
                    "Modelo 111", "—", subtitulo=f"No se pudo calcular: {e}"))

    # ── página: Paso 2 Operaciones (ANTIGUA — sin cambios, ahora embebida) ──
    def _page_operaciones(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(10)
        v.addWidget(_lbl_seccion("Operaciones del ejercicio"))
        v.addWidget(_lbl_campo("Ingresos Brutos (€)"))
        self.inp_ingresos = _agrandar(_inp("0,00"))
        v.addWidget(self.inp_ingresos)
        fila_gastos = QHBoxLayout()
        self.inp_gastos = _agrandar(_inp("0,00"))
        fila_gastos.addWidget(self.inp_gastos, 1)
        fila_gastos.addWidget(_btn("📥 Importar gastos B2B", self._importar_gastos_b2b, primary=True))
        v.addWidget(_lbl_campo("Gastos Operativos (€)"))
        v.addLayout(fila_gastos)
        self.lbl_prefill_op = QLabel("")
        self.lbl_prefill_op.setWordWrap(True)
        self.lbl_prefill_op.setStyleSheet(f"color:{_DIM};font-size:11px;background:transparent;border:none;")
        v.addWidget(self.lbl_prefill_op)
        return w

    def _importar_gastos_b2b(self):
        from src.services.contabilidad import calculadora_fiscal as CF
        d = CF.desglose_b2b()
        if not d:
            _aviso(self, "Gastos B2B", "No se pudo consultar el gasto B2B en este momento.", nivel="advertencia")
            return
        _aviso(self, "Gastos B2B del mes en curso",
              f"De tus gastos operativos, {_fmt_eur(d['gasto_b2b_mes'])} corresponden a compras B2B "
              "ya facturadas este mes. Esta cifra es informativa: las compras B2B facturadas ya están "
              "incluidas en el total de Gastos Operativos (no se suman aparte, para no duplicarlas).",
              nivel="info")

    # ── página: Factor Empleados (ANTIGUA — sin cambios, ahora embebida) ────
    def _page_empleados(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(10)
        v.addWidget(_lbl_seccion("Factor Empleados"))
        v.addWidget(_lbl_campo("Número total de empleados",
                               "Plantilla actual de la empresa. Se usa como contexto de la simulación."))
        self.inp_num_empleados = _agrandar(_inp("0"))
        v.addWidget(self.inp_num_empleados)
        v.addWidget(_lbl_campo("Nuevas contrataciones indefinidas",
                               "Cada nueva contratación indefinida genera una deducción fiscal "
                               "automática por creación de empleo."))
        self.inp_nuevas_indefinidas = _agrandar(_inp("0"))
        v.addWidget(self.inp_nuevas_indefinidas)
        v.addWidget(_lbl_campo("Contrataciones con bonificación",
                               "Contrataciones con bonificación especial (p. ej. menores de 30 años o "
                               "personas con discapacidad): generan una deducción mayor que una "
                               "contratación indefinida ordinaria."))
        self.inp_bonificadas = _agrandar(_inp("0"))
        v.addWidget(self.inp_bonificadas)
        self.lbl_prefill_emp = QLabel("")
        self.lbl_prefill_emp.setWordWrap(True)
        self.lbl_prefill_emp.setStyleSheet(f"color:{_DIM};font-size:11px;background:transparent;border:none;")
        v.addWidget(self.lbl_prefill_emp)
        return w

    # ── página: Inversiones especiales (ANTIGUA — sin cambios, ahora embebida) ─
    def _page_inversiones(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(10)
        v.addWidget(_lbl_seccion("Inversiones especiales"))
        v.addWidget(_lbl_campo("Inversión en I+D (€)",
                               "La inversión en investigación y desarrollo es altamente deducible."))
        self.inp_inversion_id = _agrandar(_inp("0,00"))
        v.addWidget(self.inp_inversion_id)
        v.addWidget(_lbl_campo("Inversión en Digitalización (€)",
                               "La inversión en digitalización del negocio también genera deducción."))
        self.inp_inversion_dig = _agrandar(_inp("0,00"))
        v.addWidget(self.inp_inversion_dig)
        return w

    # ── página: Paso 5 Generación (NUEVO, Fase D) ───────────────────────────
    def _page_generacion(self):
        w = QWidget()
        v_outer = QVBoxLayout(w)
        v_outer.setContentsMargins(0, 0, 0, 0)
        v_outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        cont = QWidget()
        v = QVBoxLayout(cont)
        v.setSpacing(14)

        v.addWidget(_lbl_seccion("5. Generación"))
        v.addWidget(_lbl_nota(
            "Genera el PDF/fichero borrador de cada modelo aplicable y, cuando ya lo hayas "
            "presentado tú mismo en la Sede Electrónica de la AEAT, márcalo como presentado aquí. "
            "Smart Manager NUNCA presenta nada de forma telemática por su cuenta."))

        fila_is = QHBoxLayout()
        fila_is.addWidget(_lbl_campo("Impuesto de Sociedades"))
        fila_is.addWidget(EnterpriseHelpTooltip(
            "El PDF de Sociedades es un documento de apoyo con la estimación de este asistente — "
            "a diferencia de los modelos 130/303/111 (que sí tienen aquí un fichero en su formato "
            "oficial de declaración), este no sustituye a la presentación real del Impuesto de "
            "Sociedades ante la AEAT.", titulo="Impuesto de Sociedades"))
        fila_is.addStretch(1)
        fila_is.addWidget(_btn("📄 Exportar PDF Sociedades", self._exportar_pdf, primary=True))
        v.addLayout(fila_is)

        self.cont_modelos_generacion = QWidget()
        self._layout_modelos_generacion = QVBoxLayout(self.cont_modelos_generacion)
        self._layout_modelos_generacion.setSpacing(10)
        v.addWidget(self.cont_modelos_generacion)

        self.lbl_sin_epigrafe_generacion = QLabel(
            "Sin epígrafe asignado: vuelve al Paso 1 para saber qué modelos trimestrales aplican.")
        self.lbl_sin_epigrafe_generacion.setWordWrap(True)
        self.lbl_sin_epigrafe_generacion.setStyleSheet(
            f"color:{_DIM};font-size:11px;background:transparent;border:none;")
        self.lbl_sin_epigrafe_generacion.setVisible(False)
        v.addWidget(self.lbl_sin_epigrafe_generacion)

        v.addStretch(1)
        scroll.setWidget(cont)
        v_outer.addWidget(scroll, 1)
        return w

    def _refrescar_generacion(self):
        from src.db.empresa import empresa_actual_id
        from src.services.contabilidad import fiscal_perfil as FP
        id_empresa = empresa_actual_id()
        perfil = FP.perfil_fiscal_empresa(id_empresa)
        _vaciar_layout(self._layout_modelos_generacion)
        self.lbl_sin_epigrafe_generacion.setVisible(bool(perfil.get("sin_epigrafe")))
        if perfil.get("sin_epigrafe"):
            return
        ejercicio, periodo = self._periodo_modelos or (
            _dt.date.today().year, f"{(_dt.date.today().month - 1) // 3 + 1}T")
        for clave in ("130", "303", "111"):
            if perfil.get(f"modelo_{clave}"):
                self._agregar_fila_generacion(clave, ejercicio, periodo, id_empresa)

    def _declaracion_periodo(self, clave, ejercicio, periodo, id_empresa):
        from src.services.aeat import base as _B
        decls = [d for d in _B.listar_declaraciones(modelo=clave, ejercicio=ejercicio, id_empresa=id_empresa)
                if d.get("periodo") == periodo]
        return decls[0] if decls else None

    def _agregar_fila_generacion(self, clave, ejercicio, periodo, id_empresa):
        from src.services.aeat import estados as _E
        nombre, ayuda = _AYUDA_MODELOS[clave]
        decl = self._declaracion_periodo(clave, ejercicio, periodo, id_empresa)
        estado = decl.get("estado") if decl else None

        cont = QWidget()
        v = QVBoxLayout(cont)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        cab = QHBoxLayout()
        cab.addWidget(_lbl_campo(f"{nombre} — {periodo} {ejercicio}"))
        cab.addWidget(EnterpriseHelpTooltip(ayuda, titulo=nombre))
        cab.addStretch(1)
        color_estado = _OK if estado == _E.PRESENTADO else (_CIAN if estado == _E.GENERADO else _DIM)
        lbl_estado = QLabel(estado or "sin generar")
        lbl_estado.setStyleSheet(f"color:{color_estado};font-weight:800;background:transparent;border:none;")
        cab.addWidget(lbl_estado)
        v.addLayout(cab)

        fila_btn = QHBoxLayout()
        fila_btn.addWidget(_btn("⚙️ Generar", lambda c=clave: self._generar_modelo(c, ejercicio, periodo, id_empresa),
                               primary=True))
        btn_presentado = _btn(
            "✅ Marcar como presentado",
            lambda c=clave: self._marcar_presentado_modelo(c, ejercicio, periodo, id_empresa))
        btn_presentado.setVisible(estado == _E.GENERADO)
        fila_btn.addWidget(btn_presentado)
        fila_btn.addStretch(1)
        v.addLayout(fila_btn)

        self._layout_modelos_generacion.addWidget(cont)

    def _generar_modelo(self, clave, ejercicio, periodo, id_empresa):
        import importlib
        try:
            modulo = importlib.import_module(f"src.services.aeat.modelo_{clave}")
            kwargs = {"id_empresa": id_empresa, "usuario": (self.usuario or {}).get("nombre")}
            if clave == "130":
                # Mismo set de deducciones aceptadas que ya vio el usuario en la vista previa del
                # Paso 4 (`_calcular_modelos_periodo`) — sin esto habría drift entre lo previsualizado
                # y lo generado. Solo el 130 las admite (303/111 no tienen ningún concepto sectorial
                # de IRPF que aplicarles).
                kwargs["deducciones_aceptadas"] = self._deducciones_aceptadas_lista()
            r = modulo.generar(ejercicio, periodo, **kwargs)
        except Exception as e:
            _aviso(self, "Generación", f"No se pudo generar el Modelo {clave}: {e}", nivel="error")
            return
        if not r.get("ok"):
            _aviso(self, "Generación", str(r.get("errores") or "No se pudo generar."), nivel="advertencia")
            return
        _aviso(self, "Generación",
              f"Modelo {clave} generado correctamente ({r.get('sentido')}, {_fmt_eur(r.get('resultado', 0))}).",
              nivel="success")
        self._refrescar_generacion()

    def _marcar_presentado_modelo(self, clave, ejercicio, periodo, id_empresa):
        """Misma lógica EXACTA (mismo permiso, misma redacción honesta) que el botón "Marcar como
        presentado" de `gui/aeat_gui.py::AEATWindow._marcar_presentado` — reutilizado aquí en vez
        de reimplementado, para que el mensaje no pueda divergir entre ambas pantallas."""
        from src.services.aeat import base as _B
        from src.services.aeat import estados as _E
        decl = self._declaracion_periodo(clave, ejercicio, periodo, id_empresa)
        if not decl or decl.get("estado") != _E.GENERADO:
            _aviso(self, "AEAT", "Solo se puede marcar como presentada una declaración GENERADA "
                  "(ni un borrador ni una ya presentada/anulada).", nivel="info")
            return
        try:
            from src.services import autorizacion
            if not autorizacion.puede(self.usuario or {}, "aeat.presentar", id_empresa=id_empresa):
                _aviso(self, "AEAT", "Permiso requerido: aeat.presentar", nivel="advertencia")
                return
        except Exception:
            pass
        if not (mostrar_confirmacion and mostrar_confirmacion(
                self, "Marcar como presentado",
                "Esta acción NO envía nada a la AEAT: Smart Manager no presenta modelos "
                "trimestrales/anuales de forma telemática. Al confirmar, estás CERTIFICANDO que "
                "YA has presentado tú mismo (o tu asesoría) este modelo en la Sede Electrónica de "
                "la AEAT, por tu cuenta.\n\n¿Confirmas que ya lo has presentado?")):
            return
        try:
            ok = _B.cambiar_estado(decl["id"], _E.PRESENTADO, usuario=(self.usuario or {}).get("nombre"),
                                   id_empresa=id_empresa)
        except Exception as e:
            _aviso(self, "AEAT", str(e), nivel="error")
            return
        if ok:
            _aviso(self, "AEAT", "Declaración marcada como PRESENTADA (autocertificación del "
                  "usuario; no se ha enviado nada a la AEAT).", nivel="success")
            self._refrescar_generacion()
        else:
            _aviso(self, "AEAT", "No se pudo actualizar el estado.", nivel="error")

    # ── prellenado con datos reales ──────────────────────────────────────
    def _precargar_datos_reales(self):
        try:
            from src.services.contabilidad import calculadora_fiscal as CF
            d = CF.datos_reales_sugeridos()
        except Exception:
            d = {}
        partes = []
        if d.get("ingresos_brutos") is not None:
            self.inp_ingresos.setText(f"{d['ingresos_brutos']:.2f}".replace(".", ","))
            partes.append(f"Ingresos reales del ejercicio: {_fmt_eur(d['ingresos_brutos'])}")
        if d.get("gastos_operativos") is not None:
            self.inp_gastos.setText(f"{d['gastos_operativos']:.2f}".replace(".", ","))
            partes.append(f"Gastos reales del ejercicio: {_fmt_eur(d['gastos_operativos'])}")
        if partes:
            self.lbl_prefill_op.setText("Prellenado con datos reales de Contabilidad — " +
                                        " · ".join(partes) + ". Puedes editarlos.")
        if d.get("num_empleados_total") is not None:
            self.inp_num_empleados.setText(str(d["num_empleados_total"]))
        if d.get("nuevas_contrataciones_indefinidas") is not None:
            self.inp_nuevas_indefinidas.setText(str(d["nuevas_contrataciones_indefinidas"]))
        if d.get("contrataciones_bonificadas") is not None:
            self.inp_bonificadas.setText(str(d["contrataciones_bonificadas"]))
        if d.get("nuevas_contrataciones_indefinidas") is not None:
            self.lbl_prefill_emp.setText(
                "Prellenado con altas indefinidas reales de RRHH de este año "
                f"({d['nuevas_contrataciones_indefinidas']} altas, {d['contrataciones_bonificadas']} "
                "bonificadas por edad<30 o discapacidad≥33%). Puedes corregirlo.")

    # ── navegación ────────────────────────────────────────────────────────
    def _ir(self, idx):
        self._stack.setCurrentIndex(idx)
        for i, d in enumerate(self._dots):
            d.setStyleSheet(self._qss_dot(i == idx, i < idx))
        self._btn_atras.setVisible(idx > 0)
        ultimo = len(_PASOS) - 1
        self._btn_sig.setText("🔄 Nueva simulación" if idx == ultimo else "Siguiente →")
        if idx == 1:
            self._actualizar_aviso_ia_ocr()
        elif idx == 2:
            self._cargar_revision_gastos()
        elif idx == 3:
            self._calcular_todo()
        elif idx == 4:
            self._refrescar_generacion()

    def _atras(self):
        idx = self._stack.currentIndex()
        if idx > 0:
            self._ir(idx - 1)

    def _siguiente(self):
        idx = self._stack.currentIndex()
        ultimo = len(_PASOS) - 1
        if idx == ultimo:
            self._ir(0)
            return
        self._ir(idx + 1)

    # ── cálculo (Impuesto de Sociedades — SIN CAMBIOS) ─────────────────────
    def _entrada_actual(self):
        return {
            "anio": _dt.date.today().year,
            "tipo_entidad": self.cmb_tipo_entidad.currentData(),
            "ccaa": self.cmb_ccaa.currentData() or None,
            "ingresos_brutos": _num(self.inp_ingresos.text()),
            "gastos_operativos": _num(self.inp_gastos.text()),
            "num_empleados_total": _entero(self.inp_num_empleados.text()),
            "nuevas_contrataciones_indefinidas": _entero(self.inp_nuevas_indefinidas.text()),
            "contrataciones_bonificadas": _entero(self.inp_bonificadas.text()),
            "inversion_id": _num(self.inp_inversion_id.text()),
            "inversion_digitalizacion": _num(self.inp_inversion_dig.text()),
        }

    def _cargar_entrada(self, entrada):
        entrada = entrada or {}
        i = self.cmb_tipo_entidad.findData(entrada.get("tipo_entidad"))
        if i >= 0:
            self.cmb_tipo_entidad.setCurrentIndex(i)
        i = self.cmb_ccaa.findData(entrada.get("ccaa") or "")
        if i >= 0:
            self.cmb_ccaa.setCurrentIndex(i)
        self.inp_ingresos.setText(str(entrada.get("ingresos_brutos", "")).replace(".", ","))
        self.inp_gastos.setText(str(entrada.get("gastos_operativos", "")).replace(".", ","))
        self.inp_num_empleados.setText(str(entrada.get("num_empleados_total", "")))
        self.inp_nuevas_indefinidas.setText(str(entrada.get("nuevas_contrataciones_indefinidas", "")))
        self.inp_bonificadas.setText(str(entrada.get("contrataciones_bonificadas", "")))
        self.inp_inversion_id.setText(str(entrada.get("inversion_id", "")).replace(".", ","))
        self.inp_inversion_dig.setText(str(entrada.get("inversion_digitalizacion", "")).replace(".", ","))

    def _calcular(self):
        from src.services.contabilidad import calculadora_fiscal as CF
        entrada = self._entrada_actual()
        r = CF.simular(
            ingresos_brutos=entrada["ingresos_brutos"],
            gastos_operativos=entrada["gastos_operativos"],
            num_empleados_total=entrada["num_empleados_total"],
            nuevas_contrataciones_indefinidas=entrada["nuevas_contrataciones_indefinidas"],
            contrataciones_bonificadas=entrada["contrataciones_bonificadas"],
            inversion_id=entrada["inversion_id"],
            inversion_digitalizacion=entrada["inversion_digitalizacion"],
            ccaa=entrada["ccaa"], tipo_entidad=entrada["tipo_entidad"],
            deducciones_aceptadas=self._deducciones_aceptadas_lista(),
        )
        self._ultimo_resultado = r
        self._ultima_entrada = entrada

        if r["reglas_faltantes"]:
            nombres = ", ".join(_CONCEPTOS_TXT.get(c, c) for c in r["reglas_faltantes"])
            self.lbl_aviso_faltantes.setText(
                f"⚠️ No hay ninguna regla fiscal aplicable para: {nombres}. Se ha usado 0 para ese "
                "concepto — da de alta la regla que falte en «Parámetros fiscales».")
            self.lbl_aviso_faltantes.setVisible(True)
        else:
            self.lbl_aviso_faltantes.setVisible(False)

        try:
            from src.services.contabilidad import calculadora_fiscal_historial as H
            H.guardar(entrada, r, usuario=(self.usuario or {}).get("nombre"))
        except Exception:
            pass

        self.grid_resultado.limpiar()
        self.grid_resultado.add_card(EnterpriseCard(
            "Base Imponible", _fmt_eur(r["base_imponible"]), modo="kpi",
            subtitulo=f"Cuota íntegra ({r['tipo_general_pct']:.0f}%): {_fmt_eur(r['cuota_integra'])}"))
        desglose = (f"Empleo: {_fmt_eur(r['deduccion_empleo'])} · "
                   f"I+D: {_fmt_eur(r['deduccion_id'])} · "
                   f"Digitalización: {_fmt_eur(r['deduccion_digitalizacion'])}")
        if r["topado"]:
            desglose += " (topadas a la cuota íntegra)"
        self.grid_resultado.add_card(EnterpriseCard(
            "Total Deducciones Aplicadas", _fmt_eur(r["total_deducciones"]), modo="kpi",
            subtitulo=desglose))
        self.grid_resultado.add_card(EnterpriseCard(
            "Ahorro Fiscal Estimado", _fmt_eur(r["ahorro_fiscal_estimado"]), modo="accion"))
        self.grid_resultado.add_card(EnterpriseCard(
            "Impuesto Final Estimado", _fmt_eur(r["impuesto_final"]), modo="kpi"))
        self.lbl_disclaimer.setText(
            "⚠️ " + r.get("nota_legal", "Estimación orientativa, sujeta a validación contable."))

    # ── exportar a PDF (Impuesto de Sociedades — SIN CAMBIOS) ──────────────
    def _exportar_pdf(self):
        if not self._ultimo_resultado:
            _aviso(self, "Exportar a PDF", "Calcula primero una simulación.", nivel="advertencia")
            return
        try:
            from src.services.contabilidad import calculadora_fiscal_pdf as PDF
            from src.db.empresa import empresa_actual_id
            entrada = getattr(self, "_ultima_entrada", {}) or {}
            ruta = PDF.generar_pdf(self._ultimo_resultado, {
                "empresa": empresa_actual_id(), "tipo_entidad": entrada.get("tipo_entidad"),
                "ccaa": entrada.get("ccaa"), "anio": entrada.get("anio")})
        except Exception as e:
            _aviso(self, "Exportar a PDF", f"No se pudo generar el PDF: {e}", nivel="error")
            return
        _aviso(self, "Exportar a PDF", "PDF generado correctamente.", nivel="success")
        try:
            from src.utils import plataforma
            plataforma.abrir_carpeta(ruta.replace("\\", "/").rsplit("/", 1)[0])
        except Exception:
            pass

    # ── parámetros fiscales (reglas) ─────────────────────────────────────
    def _abrir_parametros_fiscales(self):
        from src.gui.transiciones import abrir_dialogo_deslizante
        dlg = _ParametrosFiscalesDialog(self)
        abrir_dialogo_deslizante(dlg, self)

    # ── historial de simulaciones ────────────────────────────────────────
    def _abrir_historial(self):
        from src.gui.transiciones import abrir_dialogo_deslizante
        dlg = _HistorialDialog(self)
        if abrir_dialogo_deslizante(dlg, self) == QDialog.DialogCode.Accepted and dlg.entrada_elegida is not None:
            self._cargar_entrada(dlg.entrada_elegida)
            self._ir(0)


class _ReglaFiscalDialog(QDialog):
    """Alta/edición de una regla del Impuesto de Sociedades — clon del patrón de
    `gui/etiquetas_precios.py::_ReglaPrecioDialog` sobre `fiscal_is_reglas`."""

    def __init__(self, parent=None, regla=None):
        super().__init__(parent)
        regla = regla or {}
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(460)

        main = QVBoxLayout(self)
        cont = QWidget()
        _marco_dialogo(cont, bg=_BG2, nombre="marco_regla_fiscal")
        main.addWidget(cont)
        ly = QVBoxLayout(cont)
        ly.setContentsMargins(24, 22, 24, 22)
        ly.setSpacing(9)

        ly.addWidget(_lbl_seccion("Editar regla" if regla else "Nueva regla"))

        ly.addWidget(_lbl_campo("Concepto"))
        self.cmb_concepto = _combo(_CONCEPTOS, regla.get("concepto"))
        ly.addWidget(self.cmb_concepto)

        ly.addWidget(_lbl_campo("Comunidad Autónoma (vacío = regla nacional)"))
        self.cmb_ccaa = _combo(_CCAA_CON_VACIO, regla.get("ccaa") or "")
        ly.addWidget(self.cmb_ccaa)

        ly.addWidget(_lbl_campo("Tipo de entidad (vacío = cualquiera)"))
        self.cmb_tipo = _combo(_TIPOS_ENTIDAD_CON_VACIO, regla.get("tipo_entidad") or "")
        ly.addWidget(self.cmb_tipo)

        fila_base = QHBoxLayout()
        self.inp_base_desde = _inp("Base desde (€, opc.)")
        self.inp_base_desde.setText(str(regla.get("base_desde")) if regla.get("base_desde") is not None else "")
        self.inp_base_hasta = _inp("Base hasta (€, opc.)")
        self.inp_base_hasta.setText(str(regla.get("base_hasta")) if regla.get("base_hasta") is not None else "")
        fila_base.addWidget(self.inp_base_desde)
        fila_base.addWidget(self.inp_base_hasta)
        ly.addWidget(_lbl_campo("Tramo de base imponible (opcional)"))
        ly.addLayout(fila_base)

        fila_valor = QHBoxLayout()
        self.cmb_unidad = _combo(_UNIDADES, regla.get("unidad") or "pct")
        self.inp_valor = _inp("Valor")
        self.inp_valor.setText(str(regla.get("valor")) if regla.get("valor") is not None else "")
        fila_valor.addWidget(self.cmb_unidad)
        fila_valor.addWidget(self.inp_valor, 1)
        ly.addWidget(_lbl_campo("Valor"))
        ly.addLayout(fila_valor)

        fila_vig = QHBoxLayout()
        self.inp_vig_desde = _inp("Vigente desde AAAA-MM-DD (opc.)")
        self.inp_vig_desde.setText(str(regla.get("vigente_desde") or ""))
        self.inp_vig_hasta = _inp("Vigente hasta AAAA-MM-DD (opc.)")
        self.inp_vig_hasta.setText(str(regla.get("vigente_hasta") or ""))
        fila_vig.addWidget(self.inp_vig_desde)
        fila_vig.addWidget(self.inp_vig_hasta)
        ly.addWidget(_lbl_campo("Vigencia (opcional — condiciones del ejercicio)"))
        ly.addLayout(fila_vig)

        self.chk_activo = QCheckBox("Regla activa")
        self.chk_activo.setStyleSheet(f"color:{_TEXT};")
        self.chk_activo.setChecked(bool(regla.get("activo", 1)))
        ly.addWidget(self.chk_activo)

        botones = QHBoxLayout()
        botones.addWidget(_btn("Guardar", self.accept, primary=True))
        botones.addWidget(_btn("Cancelar", self.reject))
        ly.addLayout(botones)

    def datos(self):
        def _f_opt(txt):
            txt = txt.strip()
            if not txt:
                return None
            try:
                return float(txt.replace(",", "."))
            except ValueError:
                return None
        return {
            "concepto": self.cmb_concepto.currentData(),
            "ccaa": self.cmb_ccaa.currentData() or None,
            "tipo_entidad": self.cmb_tipo.currentData() or None,
            "base_desde": _f_opt(self.inp_base_desde.text()),
            "base_hasta": _f_opt(self.inp_base_hasta.text()),
            "unidad": self.cmb_unidad.currentData(),
            "valor": _f_opt(self.inp_valor.text()) or 0.0,
            "vigente_desde": self.inp_vig_desde.text().strip() or None,
            "vigente_hasta": self.inp_vig_hasta.text().strip() or None,
            "activo": 1 if self.chk_activo.isChecked() else 0,
        }


class _ParametrosFiscalesDialog(QDialog):
    """Lista + CRUD de las reglas fiscales de la empresa (tabla `fiscal_is_reglas`)."""

    _COLS = ["Concepto", "CCAA", "Tipo entidad", "Tramo base", "Valor", "Vigencia", "Activa"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._filas = []
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(_tam_pantalla_completa(parent))
        # Sin el contorno neón cian global (`QDialog{border:2px solid CIAN}`, estilo_global.py):
        # esta ventana ocupa toda la ventana anfitriona (ver `_tam_pantalla_completa`).
        self.setObjectName("dlg_parametros_fiscales")
        self.setStyleSheet("#dlg_parametros_fiscales { border: none; }")

        main = QVBoxLayout(self)
        cont = QWidget()
        _marco_dialogo(cont, bg=_BG, nombre="marco_parametros_fiscales")
        main.addWidget(cont)
        ly = QVBoxLayout(cont)
        ly.setContentsMargins(30, 26, 30, 26)
        ly.setSpacing(16)

        cab = QHBoxLayout()
        cab.addWidget(_lbl_seccion("⚙️ Parámetros fiscales (Impuesto de Sociedades)"))
        cab.addStretch(1)
        cab.addWidget(_btn("X", self.accept, danger=True))
        ly.addLayout(cab)

        nota = QLabel("Tipo general y deducciones editables. Añade una fila por CCAA/tipo de entidad/"
                      "tramo de base para modelar condiciones específicas del ejercicio — la regla más "
                      "específica gana sobre la nacional.")
        nota.setWordWrap(True)
        nota.setStyleSheet(f"color:{_DIM};font-size:11px;background:transparent;border:none;")
        ly.addWidget(nota)

        self.tabla = EnterpriseTable(self._COLS)
        ly.addWidget(self.tabla, 1)

        botones = QHBoxLayout()
        botones.addWidget(_btn("➕ Nueva", self._nueva, primary=True))
        botones.addWidget(_btn("✏️ Editar", self._editar, primary=True))
        botones.addWidget(_btn("🗑️ Eliminar", self._eliminar, danger=True))
        botones.addStretch(1)
        ly.addLayout(botones)

        self._cargar()

    def _cargar(self):
        from src.services.contabilidad import fiscal_is_reglas as R
        self._filas = R.listar_reglas()
        datos = []
        for r in self._filas:
            tramo = "—"
            if r.get("base_desde") is not None or r.get("base_hasta") is not None:
                tramo = f"{r.get('base_desde') or 0:g} - {r.get('base_hasta') if r.get('base_hasta') is not None else '∞'}"
            vig = "—"
            if r.get("vigente_desde") or r.get("vigente_hasta"):
                vig = f"{r.get('vigente_desde') or ''} → {r.get('vigente_hasta') or ''}"
            valor = f"{r['valor']:g}{'%' if r['unidad'] == 'pct' else ' €'}"
            datos.append([_CONCEPTOS_TXT.get(r["concepto"], r["concepto"]), r.get("ccaa") or "(nacional)",
                         r.get("tipo_entidad") or "(cualquiera)", tramo, valor, vig,
                         "✓" if r.get("activo") else "—"])
        self.tabla.set_datos(datos)

    def _sel(self):
        fila = self.tabla.tabla.currentRow()
        if fila < 0 or fila >= len(self._filas):
            return None
        return self._filas[fila]

    def _nueva(self):
        from src.services.contabilidad import fiscal_is_reglas as R
        dlg = _ReglaFiscalDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        d = dlg.datos()
        R.crear_regla(d["concepto"], ccaa=d["ccaa"], tipo_entidad=d["tipo_entidad"],
                      base_desde=d["base_desde"], base_hasta=d["base_hasta"], unidad=d["unidad"],
                      valor=d["valor"], vigente_desde=d["vigente_desde"], vigente_hasta=d["vigente_hasta"],
                      activo=d["activo"])
        self._cargar()

    def _editar(self):
        from src.services.contabilidad import fiscal_is_reglas as R
        reg = self._sel()
        if reg is None:
            _aviso(self, "Editar regla", "Selecciona antes una regla de la tabla.", nivel="info")
            return
        dlg = _ReglaFiscalDialog(self, regla=reg)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        d = dlg.datos()
        R.actualizar_regla(reg["id"], **d)
        self._cargar()

    def _eliminar(self):
        from src.services.contabilidad import fiscal_is_reglas as R
        reg = self._sel()
        if reg is None:
            _aviso(self, "Eliminar regla", "Selecciona antes una regla de la tabla.", nivel="info")
            return
        if mostrar_confirmacion and not mostrar_confirmacion(
                self, "Eliminar regla", f"¿Eliminar la regla de «{_CONCEPTOS_TXT.get(reg['concepto'], reg['concepto'])}»?"):
            return
        R.eliminar_regla(reg["id"])
        self._cargar()


class _HistorialDialog(QDialog):
    """Historial de simulaciones guardadas (tabla `fiscal_is_simulaciones`). Doble clic / botón
    "Cargar" recupera esos datos de entrada en el asistente."""

    _COLS = ["Fecha", "Entidad", "CCAA", "Impuesto final", "Ahorro fiscal"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._filas = []
        self.entrada_elegida = None
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(_tam_pantalla_completa(parent))
        # Sin el contorno neón cian global (`QDialog{border:2px solid CIAN}`, estilo_global.py):
        # esta ventana ocupa toda la ventana anfitriona (ver `_tam_pantalla_completa`).
        self.setObjectName("dlg_historial_fiscal")
        self.setStyleSheet("#dlg_historial_fiscal { border: none; }")

        main = QVBoxLayout(self)
        cont = QWidget()
        _marco_dialogo(cont, bg=_BG, nombre="marco_historial_fiscal")
        main.addWidget(cont)
        ly = QVBoxLayout(cont)
        ly.setContentsMargins(30, 26, 30, 26)
        ly.setSpacing(16)

        cab = QHBoxLayout()
        cab.addWidget(_lbl_seccion("🕑 Historial de cálculos"))
        cab.addStretch(1)
        cab.addWidget(_btn("X", self.reject, danger=True))
        ly.addLayout(cab)

        self.tabla = EnterpriseTable(self._COLS)
        self.tabla.tabla.cellDoubleClicked.connect(lambda *_: self._cargar_seleccion())
        ly.addWidget(self.tabla, 1)

        botones = QHBoxLayout()
        botones.addWidget(_btn("📂 Cargar en el asistente", self._cargar_seleccion, primary=True))
        botones.addWidget(_btn("🗑️ Eliminar", self._eliminar, danger=True))
        botones.addStretch(1)
        ly.addLayout(botones)

        self._cargar()

    def _cargar(self):
        from src.services.contabilidad import calculadora_fiscal_historial as H
        self._filas = H.listar()
        datos = []
        for f in self._filas:
            r = f.get("resultado") or {}
            datos.append([str(f.get("creado") or ""), f.get("tipo_entidad") or "—", f.get("ccaa") or "—",
                         _fmt_eur(r.get("impuesto_final", 0)), _fmt_eur(r.get("ahorro_fiscal_estimado", 0))])
        self.tabla.set_datos(datos)

    def _sel(self):
        fila = self.tabla.tabla.currentRow()
        if fila < 0 or fila >= len(self._filas):
            return None
        return self._filas[fila]

    def _cargar_seleccion(self):
        from src.services.contabilidad import calculadora_fiscal_historial as H
        fila = self._sel()
        if fila is None:
            _aviso(self, "Historial", "Selecciona antes una simulación de la tabla.", nivel="info")
            return
        detalle = H.obtener(fila["id"])
        if not detalle:
            _aviso(self, "Historial", "No se pudo recuperar esa simulación.", nivel="advertencia")
            return
        self.entrada_elegida = detalle.get("entrada") or {}
        self.accept()

    def _eliminar(self):
        from src.services.contabilidad import calculadora_fiscal_historial as H
        fila = self._sel()
        if fila is None:
            _aviso(self, "Historial", "Selecciona antes una simulación de la tabla.", nivel="info")
            return
        if mostrar_confirmacion and not mostrar_confirmacion(
                self, "Eliminar simulación", "¿Eliminar esta simulación del historial?"):
            return
        H.eliminar(fila["id"])
        self._cargar()
