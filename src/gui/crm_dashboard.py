"""
CRM-I — Dashboard CRM. Secciones: Leads, Pipeline, Oportunidades, Actividades, Forecast,
CRM SaaS, KPIs. Reutiliza el estilo global y los servicios CRM. Read-only/operativo ligero.
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QStackedWidget, QTableWidgetItem,
                             QTabWidget, QVBoxLayout, QWidget)

from src.gui.catalogo_gestion import (_BG, _BG2, _CIAN, _DIM, _btn, _btn_cargando, _btn_x, _combo,
                                      _dialogo_frameless, _inp, _lbl, _tabla)
from src.gui.components import EnterpriseKanbanBoard
from src.db import articulos as ART
from src.db import clientes as CLIDB
from src.db import ventas_comercial as VC
from src.services import autorizacion
from src.utils import presupuesto_pdf
from src.utils.i18n import tr

logger = logging.getLogger("gui.crm")

try:
    from assets.estilo_global import mostrar_mensaje
except Exception:  # pragma: no cover
    mostrar_mensaje = None


def _aviso(parent, titulo, msg, nivel="info"):
    if mostrar_mensaje is not None:
        mostrar_mensaje(parent, titulo, msg, nivel=nivel)
    else:  # pragma: no cover
        logger.info("%s: %s", titulo, msg)


def _tabla_c(cols):
    """Igual que _tabla pero con las CABECERAS +2pt (11px → 13px) — duplicado deliberado del
    helper de `contabilidad_gestion.py` (mismo criterio que `soma_tts._con_nombre`): la pestaña
    Presupuestos lo necesita para conservar su aspecto exacto tras migrar aquí, e importarlo desde
    `contabilidad_gestion` crearía una dependencia cruzada innecesaria entre módulos de GUI."""
    t = _tabla(cols)
    t.setStyleSheet(t.styleSheet().replace("font-size:11px", "font-size:13px"))
    return t


def _it(v):
    from PyQt6.QtWidgets import QTableWidgetItem
    return QTableWidgetItem("" if v is None else str(v))


def _empresa():
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return EMPRESA_DEFAULT_ID


class _FormDialog(QDialog):
    """Diálogo de formulario genérico reutilizado por las altas rápidas de CRM (contacto/oportunidad/
    campaña/objetivo/ruta): evita duplicar la misma plantilla de QLineEdit/QComboBox en cada alta.
    `campos`: lista de dicts {key,label,tipo,ph,default,opciones}."""

    def __init__(self, parent, titulo, campos, texto_guardar="Crear"):
        super().__init__(parent)
        v = _dialogo_frameless(self, titulo, ancho=380)
        self._w = {}
        for c in campos:
            v.addWidget(_lbl(c["label"]))
            if c.get("tipo") == "combo":
                w = _combo(c["opciones"], c.get("default"))
            else:
                w = _inp(c.get("ph", ""))
                if c.get("default") is not None:
                    w.setText(str(c["default"]))
            self._w[c["key"]] = (w, c.get("tipo", "text"))
            v.addWidget(w)
        fila = QHBoxLayout(); fila.addStretch()
        fila.addWidget(_btn(texto_guardar, self.accept, primary=True))
        v.addLayout(fila)

    def datos(self):
        return {k: (w.currentData() if tipo == "combo" else w.text().strip())
               for k, (w, tipo) in self._w.items()}


class _ParadasRutaDialog(QDialog):
    """Paradas de una ruta comercial: añadir cliente, marcar visitada. Expone `rutas.añadir_parada`/
    `marcar_visitada`, que hasta ahora no tenían ningún punto de la GUI que los llamara."""

    def __init__(self, parent, id_ruta, usuario):
        super().__init__(parent)
        self._id_ruta = id_ruta
        self._usuario = usuario or {}
        v = _dialogo_frameless(self, "Paradas de la ruta", ancho=480)
        self.tbl = _tabla(["Orden", "Cliente", "Estado", "Notas"])
        self.tbl.setMinimumHeight(260)
        v.addWidget(self.tbl)
        barra = QHBoxLayout()
        barra.addWidget(_btn("➕ Añadir parada", self._anadir, primary=True))
        barra.addWidget(_btn("✅ Marcar visitada", self._marcar_visitada, primary=True))
        v.addLayout(barra)
        self._cache = []
        self._cargar()

    def _cargar(self):
        from src.services.crm import rutas
        self._cache = rutas.paradas(self._id_ruta)
        self.tbl.setRowCount(len(self._cache))
        for i, p in enumerate(self._cache):
            for j, val in enumerate([p.get("orden"), p.get("cliente"), p.get("estado"), p.get("notas")]):
                self.tbl.setItem(i, j, _it(val))

    def _anadir(self):
        from src.gui.factura_window import _SelectorClienteDialog
        sel = _SelectorClienteDialog(self, texto_boton="AÑADIR A LA RUTA")
        if not (sel.exec() and sel.cliente):
            return
        from src.services.crm import rutas
        pid = rutas.añadir_parada(self._id_ruta, sel.cliente.get("id"))
        if pid:
            _aviso(self, "Rutas", "Parada añadida.", "success")
            self._cargar()
        else:
            _aviso(self, "Rutas", "No se pudo añadir la parada.", "error")

    def _marcar_visitada(self):
        r = self.tbl.currentRow()
        if r < 0 or r >= len(self._cache):
            _aviso(self, "Rutas", "Selecciona antes una parada en la tabla.", "warning")
            return
        parada = self._cache[r]
        # `crm_actividades.responsable` es INT (id de usuario), no texto — mismo criterio que
        # inspector/responsable en Calidad/GMAO/SAT (ver CLAUDE.md).
        id_usuario = self._usuario.get("id") if isinstance(self._usuario, dict) else None
        from src.services.crm import rutas
        res = rutas.marcar_visitada(parada["id"], responsable=id_usuario)
        if res.get("ok"):
            _aviso(self, "Rutas", "Parada marcada como visitada.", "success")
            self._cargar()
        else:
            _aviso(self, "Rutas", "No se pudo marcar: " + (res.get("motivo") or ""), "error")


class _GanadaDialog(QDialog):
    """Modal al soltar una tarjeta del Kanban en la columna 'Ganado': ofrece generar un documento a
    partir de la oportunidad (la etapa YA se movió — este diálogo solo decide el documento, nunca
    bloquea ni revierte el cambio de etapa). `accion` queda en None/'pedido'/'factura' tras `exec()`."""

    def __init__(self, parent, titulo_oportunidad):
        super().__init__(parent)
        v = _dialogo_frameless(self, "🎉 Oportunidad ganada", ancho=440)
        v.addWidget(_lbl(f"«{titulo_oportunidad}» se movió a Ganado.\n"
                        "¿Qué documento quieres generar a partir de ella?"))
        self.accion = None
        fila = QHBoxLayout()
        fila.addWidget(_btn("📦 Borrador de Pedido B2B", lambda: self._elegir("pedido"), primary=True))
        fila.addWidget(_btn("🧾 Presupuesto Formal", lambda: self._elegir("factura"), primary=True))
        fila.addWidget(_btn("Ahora no", lambda: self._elegir(None)))
        v.addLayout(fila)

    def _elegir(self, accion):
        self.accion = accion
        self.accept()


class CRMDashboardWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self._main = main
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("CRM Comercial · Cuadro de mando")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        if callback_vuelta:
            cab.addWidget(_btn_x(self._volver))   # X roja (como el resto de ventanas)
        root.addLayout(cab)

        self.lbl = QLabel(""); self.lbl.setStyleSheet(f"color:{_DIM};")
        root.addWidget(self.lbl)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("QTabWidget::pane { border: none; }")
        self.tbl_ops = _tabla(["ID", "Titulo", "Estado", "Valor", "Prob %", "Cierre prev.", "Doc.", "Proy."])
        self.tbl_kpi = _tabla(["KPI", "Valor"])
        # Enriquecimiento CRM (Módulo 1): campañas/marketing, objetivos comerciales y rutas comerciales.
        self.tbl_camp = _tabla(["ID", "Nombre", "Canal", "Segmento", "Estado", "Presupuesto"])
        self.tbl_obj = _tabla(["Responsable", "Tipo", "Objetivo", "Real", "%", "Cumplido"])
        self.tbl_rutas = _tabla(["ID", "Nombre", "Responsable", "Fecha", "Estado"])
        self.tbl_act = _tabla(["ID", "Tipo", "Asunto", "Vinculado a", "Responsable", "Vencimiento", "Estado"])
        # La antigua pestaña "Contactos" (leads) se ha ELIMINADO: su tabla + altas/cambio de
        # estado/conversión a cliente ahora viven dentro de la pestaña "Clientes" (lazy, más abajo),
        # como una segunda vista conmutable "Leads (pre-clientes)" en `ClientesWindow`
        # (`src/gui/clientes_gui.py`) — reutiliza el mismo backend `services/crm/leads.py`, no se
        # duplica lógica. Ver `_construir_tab_clientes`.
        self.tabs.addTab(self._tab_oportunidades(), "Oportunidades")  # idx 0
        self.tabs.addTab(self._tabla_con_actualizar(self.tbl_kpi, self._load_kpis), "KPIs / Previsión")  # idx 1
        self.tabs.addTab(self._tab_campanias(), "Campañas")  # idx 2
        self.tabs.addTab(self._tab_objetivos(), "Objetivos")  # idx 3
        self.tabs.addTab(self._tab_rutas(), "Rutas comerciales")  # idx 4
        self.tabs.addTab(self._tab_actividades(), "Actividades")  # idx 5

        # Lazy loading (init en primer acceso): las 6 pestañas de arriba ya existen como widgets
        # (tablas), pero poblarlas TODAS de golpe (6 consultas a BD seguidas) en __init__ es lo que
        # hacía tardar la apertura. Solo se carga de inmediato la pestaña visible (Oportunidades); el
        # resto carga sus datos la primera vez que el usuario la visita.
        self._load_tab_map = {
            0: self._load_oportunidades, 1: self._load_kpis,
            2: self._load_campanias, 3: self._load_objetivos, 4: self._load_rutas,
            5: self._load_actividades,
        }
        self._datos_cargados = set()
        self.tabs.currentChanged.connect(self._asegurar_datos_tab)
        self._asegurar_datos_tab(self.tabs.currentIndex())

        # Submódulos del dominio CRM (reutilizan las ventanas existentes, sin duplicarlas): gestión de
        # clientes, y Presupuestos para clientes (migrado tal cual desde Contabilidad). Embeben
        # ventanas/vistas completas con su propia carga pesada, así que también se difieren hasta el
        # primer acceso (instalar_pestanas_lazy, añadidas tras las 6 pestañas de datos → índices 6+).
        # (La antigua pestaña "SAT / Postventa" se MIGRÓ a su propio módulo de nivel superior — ver
        # `menu_principal.py`, tarjeta "Posventa"/v_id "sat" — y ya no vive embebida aquí.)
        from src.gui.transiciones import instalar_pestanas_lazy
        _pestanas_lazy = [
            ("Clientes", self._construir_tab_clientes),
            ("Presupuestos", self._page_presupuestos),
        ]
        # Delegación a SOMA — SOLO SUPERADMIN (gate reforzado, no solo el permiso RBAC):
        # autorrelleno de clientes nuevos + generación de presupuestos, las dos delegaciones de
        # este módulo (ver services.soma_delegacion.catalogo, pantalla="crm").
        if str((self.usuario or {}).get("perfil", "")).strip().upper() == "SUPERADMIN":
            def _tab_delegacion_crm():
                from src.gui.soma_delegacion_gui import DelegacionSomaPanel
                return DelegacionSomaPanel(pantalla="crm", usuario=self.usuario)
            _pestanas_lazy.append(("Delegación IA", _tab_delegacion_crm))
        instalar_pestanas_lazy(self.tabs, _pestanas_lazy)

        # Reglas de acceso (Seguridad · Pestañas): con acceso completo al módulo (perfil o
        # concesión en Seguridad · Roles), todas las pestañas se ven por defecto (una regla
        # puntual aún puede DENEGAR una en concreto); sin acceso completo (entró solo por una
        # concesión de pestaña suelta), ninguna se ve por defecto — solo la(s) concedida(s).
        from src.services.seguridad import pestanas_app
        _tiene_completo = pestanas_app.tiene_modulo_completo("clientes_crm", self.usuario, False)
        _slugs = ["oportunidades", "kpis", "campanias", "objetivos", "rutas", "actividades",
                 "clientes", "presupuestos"]
        if str((self.usuario or {}).get("perfil", "")).strip().upper() == "SUPERADMIN":
            _slugs = _slugs + ["delegacion_ia"]
        for _i, _slug in enumerate(_slugs):
            if not pestanas_app.visible(f"clientes_crm.{_slug}", self.usuario, _tiene_completo):
                self.tabs.setTabVisible(_i, False)

        root.addWidget(self.tabs)

    def _tabla_con_actualizar(self, tabla, on_actualizar):
        """Envuelve `tabla` con una barra superior con el botón 'Actualizar' alineado a la
        derecha, justo encima de ella — misma posición en las 6 pestañas de datos propias
        (Contactos/KPIs/Campañas/Objetivos/Rutas; Oportunidades la añade aparte porque ya
        tiene su propia barra inferior). Sustituye al antiguo botón único de la cabecera,
        que quedaba duplicado con el de SAT/Postventa y no dejaba claro qué recargaba."""
        w = QWidget()
        ly = QVBoxLayout(w)
        ly.setContentsMargins(0, 0, 0, 0)
        ly.setSpacing(6)
        barra = QHBoxLayout()
        barra.addStretch()
        barra.addWidget(_btn_cargando("🔄  Actualizar", on_actualizar, primary=True))
        ly.addLayout(barra)
        ly.addWidget(tabla)
        return w

    def _asegurar_datos_tab(self, idx):
        if idx in self._datos_cargados:
            return
        fn = self._load_tab_map.get(idx)
        if fn is None:
            return
        self._datos_cargados.add(idx)
        try:
            fn()
        except Exception as e:
            logger.debug("load CRM pestaña %s: %s", idx, e)

    def _construir_tab_clientes(self):
        try:
            from src.gui.clientes_gui import ClientesWindow
            return ClientesWindow(callback_vuelta=None, usuario=self.usuario, main=self._main)
        except Exception as e:
            logger.debug("tab clientes: %s", e)
            return QWidget()

    # ── Presupuestos de cliente (VTA.6) — migrado tal cual desde Contabilidad ────────────────
    def _page_presupuestos(self):
        """Presupuestos para clientes: lista + generación de PDF profesional (logo + branding
        Smart Manager) + ciclo aprobar/rechazar/convertir a pedido. Backend ya existente en
        `src.db.ventas_comercial` (no se duplica lógica aquí, solo se orquesta)."""
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(10)
        self.stk_presupuestos = QStackedWidget()
        self.stk_presupuestos.addWidget(self._pre_vista_lista())
        self.stk_presupuestos.addWidget(self._pre_vista_nuevo())
        try:
            from src.gui.transiciones import instalar_transicion_stack
            instalar_transicion_stack(self.stk_presupuestos)
        except Exception:
            pass
        ly.addWidget(self.stk_presupuestos, 1)
        self._load_presupuestos()
        return w

    def _pre_vista_lista(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(10)
        t = QLabel("📝  " + tr("contab.pre_titulo", default="Presupuestos para clientes"))
        t.setStyleSheet(f"color:{_CIAN};font-size:17px;font-weight:900;")
        ly.addWidget(t)
        fila = QHBoxLayout()
        self.in_pre_buscar = _inp(tr("contab.pre_buscar_ph", default="Buscar por cliente…"))
        self.in_pre_buscar.returnPressed.connect(self._load_presupuestos)
        fila.addWidget(self.in_pre_buscar, 1)
        self.cmb_pre_estado = _combo([
            (tr("contab.pre_todos", default="Todos"), None),
            (tr("contab.pre_borrador", default="Borrador"), "borrador"),
            (tr("contab.pre_aprobado", default="Aprobado"), "aprobado"),
            (tr("contab.pre_rechazado", default="Rechazado"), "rechazado"),
            (tr("contab.pre_convertido", default="Convertido"), "convertido"),
            (tr("contab.pre_cancelado", default="Cancelado"), "cancelado"),
        ])
        self.cmb_pre_estado.setMinimumWidth(160)
        self.cmb_pre_estado.currentIndexChanged.connect(self._load_presupuestos)
        fila.addWidget(self.cmb_pre_estado)
        fila.addWidget(_btn(tr("contab.pre_actualizar", default="🔄  ACTUALIZAR"),
                           self._load_presupuestos, primary=True))
        fila.addWidget(_btn(tr("contab.pre_nuevo", default="➕  NUEVO PRESUPUESTO"), self._pre_nuevo, primary=True))
        ly.addLayout(fila)
        self.tbl_presupuestos = _tabla_c(["Nº", "Fecha", "Cliente", "Total", "Estado"])
        ly.addWidget(self.tbl_presupuestos, 1)
        # Esquina inferior izquierda: Generar PDF + Convertir a Pedido. Esquina inferior derecha:
        # Aprobar + Rechazar (antes se solapaban con el botón flotante del Asistente SOMA).
        acc = QHBoxLayout()
        self.btn_pre_pdf = _btn(tr("contab.pre_pdf", default="GENERAR PDF"), self._pre_generar_pdf, primary=True)
        self.btn_pre_convertir = _btn(tr("contab.pre_convertir", default="CONVERTIR A PEDIDO"),
                                      self._pre_convertir, primary=True)
        self.btn_pre_aprobar = _btn(tr("contab.pre_aprobar", default="✅  Aprobar"), self._pre_aprobar)
        # Mismo diseño estructural que "danger" (contorno + relleno al hover) pero en verde de éxito
        # (#1ED760, el mismo que usan los avisos nivel="success" en assets/estilo_global.py) — _btn
        # no trae una variante "success", así que se calca su CSS con ese color en vez del rojo.
        self.btn_pre_aprobar.setStyleSheet(
            f"QPushButton{{background:{_BG2};color:#1ED760;border:2px solid #1ED760;border-radius:8px;"
            f"font-weight:900;font-size:12px;padding:0 14px;font-family:'Segoe UI';}}"
            f"QPushButton:hover{{background:#1ED760;color:{_BG};border-color:#1ED760;}}")
        self.btn_pre_rechazar = _btn(tr("contab.pre_rechazar", default="❌  RECHAZAR"), self._pre_rechazar, danger=True)
        # Delegación a SOMA (SUPERADMIN): borrador de presupuesto generado por IA a partir de una
        # breve descripción — siempre en estado 'borrador', nunca se compromete sin tu aprobación.
        btn_pre_soma = _btn("✨  GENERAR CON SOMA", self._pre_generar_con_soma, primary=True)
        acc.addWidget(self.btn_pre_pdf)
        acc.addWidget(self.btn_pre_convertir)
        acc.addWidget(btn_pre_soma)
        acc.addStretch(1)
        acc.addWidget(self.btn_pre_aprobar)
        acc.addWidget(self.btn_pre_rechazar)
        # Sin "gateado" ni setEnabled: los 4 botones se ven SIEMPRE con su color propio y su hover
        # normal, seleccione o no una fila — pulsar uno sin fila válida ya muestra el aviso
        # correspondiente (cada manejador valida la fila/estado antes de actuar). Más simple y sin
        # el problema de Qt donde un widget deshabilitado deja de recibir eventos de hover.
        ly.addLayout(acc)
        self._pre_cache = []
        return w

    def _pre_vista_nuevo(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(10)
        cab = QHBoxLayout()
        t = QLabel("🧾  " + tr("contab.pre_nuevo_titulo", default="Nuevo presupuesto"))
        t.setStyleSheet(f"color:{_CIAN};font-size:17px;font-weight:900;")
        cab.addWidget(t); cab.addStretch(1)
        btn_volver = _btn("←", self._pre_volver_lista, primary=True)
        # Nudge fino: el glifo "←" de Segoe UI no cae justo en el centro geométrico de la caja
        # 34x34 de `_btn` (tinta desplazada arriba-izquierda) — se compensa con un pelín de padding
        # en vez de un overlay (que ya rompió el hover una vez, ver commits previos).
        btn_volver.setStyleSheet(btn_volver.styleSheet() + "QPushButton{padding-bottom:3px;padding-left:3px;}")
        cab.addWidget(btn_volver)
        ly.addLayout(cab)

        fila_cli = QHBoxLayout()
        fila_cli.addWidget(_btn(tr("contab.pre_elegir_cliente", default="👤  SELECCIONAR CLIENTE"),
                                self._pre_elegir_cliente, primary=True))
        self.lbl_pre_cliente = QLabel(tr("contab.pre_sin_cliente", default="Cliente: (ninguno seleccionado)"))
        self.lbl_pre_cliente.setStyleSheet(f"color:{_DIM};font-weight:700;")
        fila_cli.addWidget(self.lbl_pre_cliente, 1)
        ly.addLayout(fila_cli)

        self.tbl_pre_lineas = _tabla_c(["Código", "Descripción", "Cantidad", "Precio Unit.", "Subtotal"])
        from PyQt6.QtWidgets import QAbstractItemView
        self.tbl_pre_lineas.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked |
                                            QAbstractItemView.EditTrigger.EditKeyPressed)
        # El editor de celda (QLineEdit interno) hereda el borde/padding neón GLOBAL de la app y,
        # dentro de una celda de tabla, ese borde+padding deja poco sitio real para el texto
        # tecleado (se ve cortado). Se retira el borde/relleno del editor y del recuadro de
        # selección — con el cursor parpadeando basta para ver qué celda está activa.
        self.tbl_pre_lineas.setStyleSheet(
            self.tbl_pre_lineas.styleSheet()
            + "QTableWidget::item:selected{background:transparent;color:white;}"
              f"QTableWidget QLineEdit{{border:none;background:{_BG};color:white;padding:0 2px;"
              # `selection-color` (primer plano del texto resaltado) explícito: al entrar en modo
              # edición, Qt selecciona todo el texto existente por defecto — sin fijar este color,
              # el texto seleccionado hereda un gris oscuro por defecto casi invisible sobre el
              # resaltado semitransparente, pareciendo "vacío" hasta que se empieza a escribir.
              "margin:0;selection-background-color:#00FFC655;selection-color:white;}")
        self.tbl_pre_lineas.itemChanged.connect(self._pre_linea_cambiada)
        ly.addWidget(self.tbl_pre_lineas, 1)

        acc_lin = QHBoxLayout()
        acc_lin.addWidget(_btn(tr("contab.pre_add_linea", default="➕  AÑADIR LÍNEA"),
                              self._pre_anadir_linea, primary=True))
        acc_lin.addWidget(_btn(tr("contab.pre_del_linea", default="🗑  QUITAR LÍNEA"),
                               self._pre_quitar_linea, danger=True))
        acc_lin.addStretch(1)
        self.lbl_pre_total = QLabel("TOTAL: 0.00 €")
        self.lbl_pre_total.setStyleSheet(f"color:{_CIAN};font-weight:900;font-size:15px;")
        acc_lin.addWidget(self.lbl_pre_total)
        ly.addLayout(acc_lin)

        f2 = QHBoxLayout()
        self.in_pre_obs = _inp(tr("contab.pre_obs_ph", default="Observaciones (opcional)"))
        f2.addWidget(self.in_pre_obs, 1)
        lbl_val = QLabel(tr("contab.pre_validez", default="Validez de la oferta (días):"))
        lbl_val.setStyleSheet(f"color:{_DIM};")
        f2.addWidget(lbl_val)
        self.in_pre_validez = _inp("30"); self.in_pre_validez.setFixedWidth(60); self.in_pre_validez.setText("30")
        f2.addWidget(self.in_pre_validez)
        ly.addLayout(f2)

        acc3 = QHBoxLayout(); acc3.addStretch(1)
        acc3.addWidget(_btn(tr("contab.pre_guardar", default="💾  GUARDAR PRESUPUESTO"),
                            self._guardar_presupuesto, primary=True))
        ly.addLayout(acc3)
        return w

    # -- lista: carga / acciones --------------------------------------------
    def _load_presupuestos(self):
        estado = self.cmb_pre_estado.currentData()
        filas = VC.listar("presupuestos", estado=estado)
        texto = (self.in_pre_buscar.text() or "").strip().lower()
        self._pre_cache = []
        self.tbl_presupuestos.setRowCount(0)
        for f in filas:
            cli = CLIDB.obtener_cliente(f.get("id_cliente")) or {}
            nombre_cli = cli.get("nombre") or ""
            if texto and texto not in nombre_cli.lower():
                continue
            self._pre_cache.append(f)
            r = self.tbl_presupuestos.rowCount(); self.tbl_presupuestos.insertRow(r)
            vals = [f.get("numero"), f.get("fecha"), nombre_cli, f.get("total"), f.get("estado")]
            for c, v in enumerate(vals):
                self.tbl_presupuestos.setItem(r, c, QTableWidgetItem("" if v is None else str(v)))

    def _pre_fila_actual(self):
        r = self.tbl_presupuestos.currentRow()
        if r < 0 or r >= len(self._pre_cache):
            _aviso(self, "Presupuestos", tr("contab.pre_selecc",
                                            default="Selecciona un presupuesto en la tabla."), "warning")
            return None
        return self._pre_cache[r]

    def _generar_pdf_presupuesto_id(self, did, *, validez_dias=30):
        pre = VC.obtener_presupuesto(did)
        if not pre:
            _aviso(self, "Presupuestos", tr("contab.pre_error_leer",
                                            default="No se pudo leer el presupuesto."), "error")
            return
        cli = CLIDB.obtener_cliente(pre.get("id_cliente")) or {}
        ruta = presupuesto_pdf.generar_y_registrar_presupuesto(pre, cli, validez_dias=validez_dias)
        if not ruta:
            _aviso(self, "Presupuestos", tr("contab.pre_error_pdf",
                                            default="No se pudo generar el PDF."), "error")
            return
        try:
            from src.utils import plataforma
            plataforma.abrir_archivo(ruta)
        except Exception as ex:
            logger.error("abrir pdf presupuesto: %s", ex)
        _aviso(self, "Presupuestos", tr("contab.pre_pdf_ok", default="PDF generado y abierto correctamente."),
              "success")
        self._load_presupuestos()

    def _pre_generar_pdf(self):
        f = self._pre_fila_actual()
        if f:
            self._generar_pdf_presupuesto_id(f["id"])

    def _pre_aprobar(self):
        f = self._pre_fila_actual()
        if not f:
            return
        if not autorizacion.puede(self.usuario, "ventas.presupuestos.aprobar"):
            _aviso(self, "Presupuestos", tr("contab.pre_sin_permiso_aprobar",
                                            default="No tiene permiso para aprobar/rechazar presupuestos."), "warning")
            return
        if f.get("estado") != "borrador":
            _aviso(self, "Presupuestos", tr("contab.pre_no_aprobable",
                                            default="Solo se pueden aprobar presupuestos en borrador."), "warning")
            return
        if VC.aprobar_presupuesto(f["id"]):
            _aviso(self, "Presupuestos", tr("contab.pre_aprobado_ok", default="Presupuesto aprobado."), "success")
            self._load_presupuestos()
        else:
            _aviso(self, "Presupuestos", tr("contab.pre_error_aprobar", default="No se pudo aprobar."), "error")

    def _pre_rechazar(self):
        f = self._pre_fila_actual()
        if not f:
            return
        if not autorizacion.puede(self.usuario, "ventas.presupuestos.aprobar"):
            _aviso(self, "Presupuestos", tr("contab.pre_sin_permiso_aprobar",
                                            default="No tiene permiso para aprobar/rechazar presupuestos."), "warning")
            return
        if f.get("estado") != "borrador":
            _aviso(self, "Presupuestos", tr("contab.pre_no_rechazable",
                                            default="Solo se pueden rechazar presupuestos en borrador."), "warning")
            return
        if VC.rechazar_presupuesto(f["id"]):
            _aviso(self, "Presupuestos", tr("contab.pre_rechazado_ok", default="Presupuesto rechazado."), "success")
            self._load_presupuestos()
        else:
            _aviso(self, "Presupuestos", tr("contab.pre_error_rechazar", default="No se pudo rechazar."), "error")

    def _pre_convertir(self):
        f = self._pre_fila_actual()
        if not f:
            return
        if not autorizacion.puede(self.usuario, "ventas.presupuestos.convertir"):
            _aviso(self, "Presupuestos", tr("contab.pre_sin_permiso_convertir",
                                            default="No tiene permiso para convertir presupuestos a pedido."), "warning")
            return
        if f.get("estado") not in ("aprobado", "borrador"):
            _aviso(self, "Presupuestos", tr("contab.pre_no_convertible",
                                            default="Solo se pueden convertir presupuestos aprobados."), "warning")
            return
        usuario_nombre = (self.usuario or {}).get("nombre") if isinstance(self.usuario, dict) else None
        ped = VC.convertir_a_pedido(f["id"], usuario=usuario_nombre)
        if ped:
            _aviso(self, "Presupuestos",
                   tr("contab.pre_convertido_ok", default="Convertido a pedido de cliente correctamente."),
                   "success")
            self._load_presupuestos()
        else:
            _aviso(self, "Presupuestos", tr("contab.pre_error_convertir", default="No se pudo convertir."), "error")

    # -- nuevo presupuesto: líneas editables ---------------------------------
    def _pre_nuevo(self):
        if not autorizacion.puede(self.usuario, "ventas.presupuestos.crear"):
            _aviso(self, "Presupuestos", tr("contab.pre_sin_permiso_crear",
                                            default="No tiene permiso para crear presupuestos."), "warning")
            return
        self._pre_cliente = None
        self.lbl_pre_cliente.setText(tr("contab.pre_sin_cliente", default="Cliente: (ninguno seleccionado)"))
        self.tbl_pre_lineas.setRowCount(0)
        self.in_pre_obs.clear()
        self.in_pre_validez.setText("30")
        self.lbl_pre_total.setText("TOTAL: 0.00 €")
        self._pre_anadir_linea()
        self.stk_presupuestos.setCurrentIndex(1)

    def _pre_volver_lista(self):
        self.stk_presupuestos.setCurrentIndex(0)
        self._load_presupuestos()

    def _pre_elegir_cliente(self):
        from src.gui.factura_window import _SelectorClienteDialog
        dlg = _SelectorClienteDialog(self, texto_boton=tr("contab.pre_asignar_cliente", default="ASIGNAR CLIENTE"))
        if dlg.exec() and dlg.cliente:
            self._pre_cliente = dlg.cliente
            self.lbl_pre_cliente.setText(
                tr("contab.pre_cliente_lbl", default="Cliente:") + f" {dlg.cliente.get('nombre') or ''}")

    def _pre_generar_con_soma(self):
        """Delegación a SOMA (ver `services.soma_delegacion`): genera un BORRADOR de presupuesto
        a partir de una breve descripción, siguiendo las instrucciones que el SUPERADMIN haya
        dejado configuradas en «Delegación a SOMA». Si no hay ninguna regla activa para esta
        tarea, no inventa nada — remite a esa pantalla para configurarla primero (el encargo
        exige que SIEMPRE haya instrucciones explícitas antes de poder delegar)."""
        from src.services.soma_delegacion import reglas as _sd_reglas
        if not _sd_reglas.listar_reglas(id_empresa=_empresa(), tipo="crm.generar_presupuesto",
                                        solo_activas=True):
            _aviso(self, "Generar con SOMA",
                  "Todavía no has delegado esta tarea a SOMA. Actívala desde «Delegación a SOMA» "
                  "(solo SUPERADMIN) indicando cómo debe generar los presupuestos.", "warning")
            return
        from src.gui.factura_window import _SelectorClienteDialog
        dlg_cli = _SelectorClienteDialog(self, texto_boton=tr("contab.pre_asignar_cliente",
                                                              default="ASIGNAR CLIENTE"))
        if not (dlg_cli.exec() and dlg_cli.cliente):
            return
        from PyQt6.QtWidgets import QInputDialog
        brief, ok = QInputDialog.getMultiLineText(
            self, "Generar presupuesto con SOMA",
            f"¿Qué pide {dlg_cli.cliente.get('nombre') or 'el cliente'}?")
        if not ok or not brief.strip():
            return
        from src.services.soma_delegacion import motor as _sd_motor
        contexto = {"id_cliente": dlg_cli.cliente.get("id"), "brief": brief.strip()}
        resultados = _sd_motor.procesar_evento("crm.generar_presupuesto", contexto,
                                               id_empresa=_empresa(), usuario=self.usuario)
        if not resultados:
            _aviso(self, "Generar con SOMA", "No se pudo evaluar la delegación.", "error")
            return
        r = resultados[0]
        nivel = "success" if r.get("estado") == "aplicado" else (
            "warning" if r.get("estado") == "descartado" else "error")
        _aviso(self, "Generar con SOMA", r.get("detalle") or "Proceso completado.", nivel)
        self._load_presupuestos()

    def _pre_anadir_linea(self):
        tbl = self.tbl_pre_lineas
        r = tbl.rowCount(); tbl.insertRow(r)
        tbl.blockSignals(True)
        try:
            tbl.setItem(r, 0, QTableWidgetItem(""))
            tbl.setItem(r, 1, QTableWidgetItem(""))
            tbl.setItem(r, 2, QTableWidgetItem("1"))
            tbl.setItem(r, 3, QTableWidgetItem("0.00"))
            sub_item = QTableWidgetItem("0.00")
            sub_item.setFlags(sub_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            tbl.setItem(r, 4, sub_item)
        finally:
            tbl.blockSignals(False)

    def _pre_quitar_linea(self):
        r = self.tbl_pre_lineas.currentRow()
        if r >= 0:
            self.tbl_pre_lineas.removeRow(r)
            self._pre_recalcular_total()

    def _pre_linea_cambiada(self, item):
        tbl = self.tbl_pre_lineas
        row, col = item.row(), item.column()
        tbl.blockSignals(True)
        try:
            if col == 0:   # código: autocompletar descripción/precio desde el catálogo si están vacíos
                codigo = (item.text() or "").strip()
                if codigo:
                    encontrado = ART.buscar_uno(codigo)
                    if encontrado:
                        cod, nombre, precio = encontrado
                        desc_item = tbl.item(row, 1)
                        if desc_item is not None and not (desc_item.text() or "").strip():
                            desc_item.setText(nombre or "")
                        precio_item = tbl.item(row, 3)
                        if precio_item is not None and not (precio_item.text() or "").strip():
                            precio_item.setText(f"{float(precio or 0):.2f}")

            def _num(c):
                it = tbl.item(row, c)
                try:
                    return float((it.text() if it else "0").replace(",", ".") or 0)
                except ValueError:
                    return 0.0

            sub = round(_num(2) * _num(3), 2)
            sub_item = tbl.item(row, 4)
            if sub_item is None:
                sub_item = QTableWidgetItem()
                sub_item.setFlags(sub_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                tbl.setItem(row, 4, sub_item)
            sub_item.setText(f"{sub:.2f}")
        finally:
            tbl.blockSignals(False)
        self._pre_recalcular_total()

    def _pre_recalcular_total(self):
        tbl = self.tbl_pre_lineas
        total = 0.0
        for r in range(tbl.rowCount()):
            it = tbl.item(r, 4)
            try:
                total += float((it.text() if it else "0") or 0)
            except ValueError:
                pass
        self.lbl_pre_total.setText(f"TOTAL: {total:.2f} €")

    def _guardar_presupuesto(self):
        if not autorizacion.puede(self.usuario, "ventas.presupuestos.crear"):
            _aviso(self, "Presupuestos", tr("contab.pre_sin_permiso_crear",
                                            default="No tiene permiso para crear presupuestos."), "warning")
            return
        cli = getattr(self, "_pre_cliente", None)
        if not cli:
            _aviso(self, "Presupuestos", tr("contab.pre_sin_cliente_aviso",
                                            default="Seleccione un cliente antes de guardar."), "warning")
            return
        tbl = self.tbl_pre_lineas
        lineas = []
        for r in range(tbl.rowCount()):
            cod = (tbl.item(r, 0).text() if tbl.item(r, 0) else "").strip()
            desc = (tbl.item(r, 1).text() if tbl.item(r, 1) else "").strip()
            try:
                cant = int(float((tbl.item(r, 2).text() if tbl.item(r, 2) else "0").replace(",", ".") or 0))
            except ValueError:
                cant = 0
            try:
                precio = float((tbl.item(r, 3).text() if tbl.item(r, 3) else "0").replace(",", ".") or 0)
            except ValueError:
                precio = 0.0
            if cod and cant > 0:
                lineas.append({"codigo": cod, "descripcion": desc, "cantidad": cant, "precio_unitario": precio})
        if not lineas:
            _aviso(self, "Presupuestos", tr("contab.pre_sin_lineas",
                                            default="Añada al menos una línea válida (código y cantidad > 0)."),
                   "warning")
            return
        obs = (self.in_pre_obs.text() or "").strip() or None
        try:
            validez = int((self.in_pre_validez.text() or "30").strip() or 30)
        except ValueError:
            validez = 30
        usuario_nombre = (self.usuario or {}).get("nombre") if isinstance(self.usuario, dict) else None
        did = VC.crear_presupuesto(id_cliente=cli.get("id"), lineas=lineas, observaciones=obs,
                                   usuario=usuario_nombre)
        if not did:
            _aviso(self, "Presupuestos", tr("contab.pre_error_guardar",
                                            default="No se pudo guardar el presupuesto."), "error")
            return
        _aviso(self, "Presupuestos", tr("contab.pre_guardado_ok", default="Presupuesto guardado correctamente."),
              "success")
        # Automatización: generar y abrir el PDF profesional inmediatamente tras guardar.
        self._generar_pdf_presupuesto_id(did, validez_dias=validez)
        self._pre_volver_lista()

    def _tab_oportunidades(self):
        """Pestaña Oportunidades = tabla/Kanban (conmutable) + alta + mover de etapa + cierre +
        'Convertir a factura/proyecto'. El Kanban (`EnterpriseKanbanBoard`) es una vista ALTERNATIVA
        a la tabla, no la sustituye: la tabla sigue siendo el fallback de bajo riesgo."""
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 16, 0, 0); ly.setSpacing(14)
        barra = QHBoxLayout()
        self.btn_vista_oportunidades = _btn("🗂️ Vista Kanban", self._alternar_vista_oportunidades,
                                            primary=True)
        barra.addWidget(self.btn_vista_oportunidades)
        barra.addStretch()
        barra.addWidget(_btn("➕ Nueva oportunidad", self._nueva_oportunidad, primary=True))
        barra.addWidget(_btn("➡️ Mover etapa", self._mover_etapa_oportunidad, primary=True))
        barra.addWidget(_btn("✅ Marcar ganada", self._cerrar_oportunidad_ganada, primary=True))
        barra.addWidget(_btn("❌ Marcar perdida", self._cerrar_oportunidad_perdida, danger=True))
        self._btn_conv = _btn("🧾 Convertir a factura", self._convertir_factura, primary=True)
        self._btn_proy = _btn("📁 Convertir a proyecto", self._convertir_proyecto, primary=True)
        try:
            from src.services.autorizacion import puede
            self._btn_conv.setEnabled(puede(self.usuario, "ventas.facturar"))
            self._btn_proy.setEnabled(puede(self.usuario, "proyectos.gestionar"))
        except Exception:
            pass
        barra.addWidget(self._btn_conv)
        barra.addWidget(self._btn_proy)
        barra.addWidget(_btn_cargando("🔄  Actualizar", self._load_oportunidades, primary=True))
        ly.addLayout(barra)

        self.stk_oportunidades = QStackedWidget()
        self.stk_oportunidades.addWidget(self.tbl_ops)          # idx 0: tabla (fallback)
        self.kanban_oportunidades = EnterpriseKanbanBoard([])   # idx 1: Kanban (columnas en _load_kanban)
        self.kanban_oportunidades.cartaMovida.connect(self._kanban_carta_movida)
        self.stk_oportunidades.addWidget(self.kanban_oportunidades)
        ly.addWidget(self.stk_oportunidades, 1)
        self._kanban_cache = {}      # id_oportunidad -> fila cruda (para el diálogo de Ganado)
        self._kanban_etapas = []     # lista de etapas vigentes (para traducir id_etapa -> codigo)
        self._cache_clientes_kanban = {}
        return w

    def _alternar_vista_oportunidades(self):
        nuevo = 1 - self.stk_oportunidades.currentIndex()
        self.stk_oportunidades.setCurrentIndex(nuevo)
        self.btn_vista_oportunidades.setText("📊 Vista Tabla" if nuevo == 1 else "🗂️ Vista Kanban")
        if nuevo == 1:
            self._load_kanban()

    def _oportunidad_seleccionada(self):
        r = self.tbl_ops.currentRow()
        if r < 0 or self.tbl_ops.item(r, 0) is None:
            _aviso(self, "Oportunidades", "Selecciona antes una oportunidad en la tabla.", "warning")
            return None
        try:
            return int(self.tbl_ops.item(r, 0).text())
        except (TypeError, ValueError):
            return None

    def _nueva_oportunidad(self):
        if not autorizacion.puede(self.usuario, "crm.oportunidades"):
            _aviso(self, "Oportunidades", "No tiene permiso para crear oportunidades.", "warning")
            return
        dlg = _FormDialog(self, "Nueva oportunidad", [
            {"key": "titulo", "label": "Título *", "ph": "Título de la oportunidad"},
            {"key": "valor", "label": "Valor (€)", "ph": "0", "default": "0"},
            {"key": "fecha_cierre_prevista", "label": "Cierre previsto (AAAA-MM-DD, opcional)",
             "ph": "2026-12-31"},
        ])
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        d = dlg.datos()
        if not d["titulo"]:
            _aviso(self, "Oportunidades", "El título es obligatorio.", "warning")
            return
        try:
            valor = float((d["valor"] or "0").replace(",", ".") or 0)
        except ValueError:
            valor = 0
        from src.gui.factura_window import _SelectorClienteDialog
        sel = _SelectorClienteDialog(self, texto_boton="ASIGNAR CLIENTE")
        cid = sel.cliente.get("id") if sel.exec() and sel.cliente else None
        from src.services.crm import oportunidades
        oid = oportunidades.crear_oportunidad(d["titulo"], valor=valor, id_cliente=cid,
                                              fecha_cierre_prevista=d["fecha_cierre_prevista"] or None,
                                              id_empresa=_empresa())
        if oid:
            _aviso(self, "Oportunidades", "Oportunidad creada correctamente.", "success")
            self._load_oportunidades()
        else:
            _aviso(self, "Oportunidades", "No se pudo crear la oportunidad.", "error")

    def _mover_etapa_oportunidad(self):
        oid = self._oportunidad_seleccionada()
        if not oid:
            return
        if not autorizacion.puede(self.usuario, "crm.pipeline"):
            _aviso(self, "Oportunidades", "No tiene permiso para mover oportunidades de etapa.", "warning")
            return
        from src.services.crm import pipeline
        etapas = pipeline.listar_etapas(id_empresa=_empresa())
        opciones = [(e.get("nombre"), e.get("codigo")) for e in etapas] or [
            ("Lead", "lead"), ("Contacto", "contacto"), ("Propuesta", "propuesta"),
            ("Negociación", "negociacion"), ("Pendiente", "pendiente"),
            ("Ganado", "ganado"), ("Perdido", "perdido")]
        dlg = _FormDialog(self, "Mover a etapa", [
            {"key": "etapa", "label": "Nueva etapa", "tipo": "combo", "opciones": opciones},
        ], texto_guardar="Mover")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        from src.services.crm import oportunidades
        r = oportunidades.mover_etapa(oid, dlg.datos()["etapa"], id_empresa=_empresa())
        if r.get("ok"):
            _aviso(self, "Oportunidades", "Etapa actualizada.", "success")
            self._load_oportunidades()
        else:
            _aviso(self, "Oportunidades", "No se pudo mover de etapa: " + (r.get("error") or ""), "error")

    def _cerrar_oportunidad(self, ganada):
        oid = self._oportunidad_seleccionada()
        if not oid:
            return
        if not autorizacion.puede(self.usuario, "crm.oportunidades"):
            _aviso(self, "Oportunidades", "No tiene permiso para cerrar oportunidades.", "warning")
            return
        from src.services.crm import oportunidades
        r = oportunidades.cerrar(oid, ganada)
        if r.get("ok"):
            _aviso(self, "Oportunidades",
                  f"Oportunidad marcada como {'ganada' if ganada else 'perdida'}.", "success")
            self._load_oportunidades()
        else:
            _aviso(self, "Oportunidades", "No se pudo cerrar: " + (r.get("error") or ""), "error")

    def _cerrar_oportunidad_ganada(self):
        self._cerrar_oportunidad(True)

    def _cerrar_oportunidad_perdida(self):
        self._cerrar_oportunidad(False)

    def _tab_campanias(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 16, 0, 0); ly.setSpacing(14)
        barra = QHBoxLayout()
        barra.addStretch()
        barra.addWidget(_btn("➕ Nueva campaña", self._nueva_campania, primary=True))
        barra.addWidget(_btn("▶️ Activar", self._activar_campania, primary=True))
        barra.addWidget(_btn_cargando("🔄  Actualizar", self._load_campanias, primary=True))
        ly.addLayout(barra)
        ly.addWidget(self.tbl_camp)
        return w

    def _nueva_campania(self):
        if not autorizacion.puede(self.usuario, "crm.admin"):
            _aviso(self, "Campañas", "No tiene permiso para crear campañas.", "warning")
            return
        dlg = _FormDialog(self, "Nueva campaña", [
            {"key": "nombre", "label": "Nombre *", "ph": "Nombre de la campaña"},
            {"key": "canal", "label": "Canal", "tipo": "combo",
             "opciones": [("Email", "email"), ("SMS", "sms"), ("WhatsApp", "whatsapp"), ("Otro", "otro")],
             "default": "email"},
            {"key": "segmento_objetivo", "label": "Segmento (opcional)", "ph": "Ej: mayoristas"},
            {"key": "presupuesto", "label": "Presupuesto (€)", "ph": "0", "default": "0"},
        ])
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        d = dlg.datos()
        if not d["nombre"]:
            _aviso(self, "Campañas", "El nombre es obligatorio.", "warning")
            return
        try:
            presupuesto = float((d["presupuesto"] or "0").replace(",", ".") or 0)
        except ValueError:
            presupuesto = 0
        from src.services.crm import campanias
        cid = campanias.crear_campania(d["nombre"], canal=d["canal"],
                                       segmento_objetivo=d["segmento_objetivo"] or None,
                                       presupuesto=presupuesto, id_empresa=_empresa())
        if cid:
            _aviso(self, "Campañas", "Campaña creada correctamente.", "success")
            self._load_campanias()
        else:
            _aviso(self, "Campañas", "No se pudo crear la campaña.", "error")

    def _activar_campania(self):
        r = self.tbl_camp.currentRow()
        if r < 0 or self.tbl_camp.item(r, 0) is None:
            _aviso(self, "Campañas", "Selecciona antes una campaña en la tabla.", "warning")
            return
        if not autorizacion.puede(self.usuario, "crm.admin"):
            _aviso(self, "Campañas", "No tiene permiso para activar campañas.", "warning")
            return
        try:
            cid = int(self.tbl_camp.item(r, 0).text())
        except (TypeError, ValueError):
            return
        from src.services.crm import campanias
        res = campanias.activar(cid, id_empresa=_empresa())
        if res.get("ok"):
            _aviso(self, "Campañas", "Campaña activada.", "success")
            self._load_campanias()
        else:
            _aviso(self, "Campañas", "No se pudo activar: " + (res.get("motivo") or ""), "error")

    def _tab_objetivos(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 16, 0, 0); ly.setSpacing(14)
        barra = QHBoxLayout()
        barra.addStretch()
        barra.addWidget(_btn("➕ Nuevo objetivo", self._nuevo_objetivo, primary=True))
        barra.addWidget(_btn_cargando("🔄  Actualizar", self._load_objetivos, primary=True))
        ly.addLayout(barra)
        ly.addWidget(self.tbl_obj)
        return w

    def _nuevo_objetivo(self):
        if not autorizacion.puede(self.usuario, "crm.admin"):
            _aviso(self, "Objetivos", "No tiene permiso para crear objetivos.", "warning")
            return
        dlg = _FormDialog(self, "Nuevo objetivo", [
            {"key": "responsable", "label": "Responsable *", "ph": "Nombre del responsable"},
            {"key": "tipo", "label": "Tipo", "tipo": "combo",
             "opciones": [("Ventas", "ventas"), ("Oportunidades", "oportunidades"), ("Visitas", "visitas")],
             "default": "ventas"},
            {"key": "objetivo_valor", "label": "Objetivo (importe o cantidad)", "ph": "0", "default": "0"},
            {"key": "periodo", "label": "Periodo (opcional)", "ph": "Ej: 2026-Q1"},
            {"key": "fecha_inicio", "label": "Fecha inicio (AAAA-MM-DD, opcional)", "ph": "2026-01-01"},
            {"key": "fecha_fin", "label": "Fecha fin (AAAA-MM-DD, opcional)", "ph": "2026-03-31"},
        ])
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        d = dlg.datos()
        if not d["responsable"]:
            _aviso(self, "Objetivos", "El responsable es obligatorio.", "warning")
            return
        try:
            valor = float((d["objetivo_valor"] or "0").replace(",", ".") or 0)
        except ValueError:
            valor = 0
        from src.services.crm import objetivos
        try:
            oid = objetivos.crear_objetivo(d["responsable"], valor, tipo=d["tipo"],
                                           periodo=d["periodo"] or None,
                                           fecha_inicio=d["fecha_inicio"] or None,
                                           fecha_fin=d["fecha_fin"] or None, id_empresa=_empresa())
        except ValueError as e:
            _aviso(self, "Objetivos", str(e), "warning")
            return
        if oid:
            _aviso(self, "Objetivos", "Objetivo creado correctamente.", "success")
            self._load_objetivos()
        else:
            _aviso(self, "Objetivos", "No se pudo crear el objetivo.", "error")

    def _tab_rutas(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 16, 0, 0); ly.setSpacing(14)
        barra = QHBoxLayout()
        barra.addStretch()
        barra.addWidget(_btn("➕ Nueva ruta", self._nueva_ruta, primary=True))
        barra.addWidget(_btn("📍 Gestionar paradas", self._gestionar_paradas_ruta, primary=True))
        barra.addWidget(_btn("🧭 Optimizar", self._optimizar_ruta, primary=True))
        barra.addWidget(_btn_cargando("🔄  Actualizar", self._load_rutas, primary=True))
        ly.addLayout(barra)
        ly.addWidget(self.tbl_rutas)
        return w

    def _ruta_seleccionada(self):
        r = self.tbl_rutas.currentRow()
        if r < 0 or self.tbl_rutas.item(r, 0) is None:
            _aviso(self, "Rutas", "Selecciona antes una ruta en la tabla.", "warning")
            return None
        try:
            return int(self.tbl_rutas.item(r, 0).text())
        except (TypeError, ValueError):
            return None

    def _nueva_ruta(self):
        if not autorizacion.puede(self.usuario, "crm.admin"):
            _aviso(self, "Rutas", "No tiene permiso para crear rutas.", "warning")
            return
        dlg = _FormDialog(self, "Nueva ruta", [
            {"key": "nombre", "label": "Nombre *", "ph": "Nombre de la ruta"},
            {"key": "responsable", "label": "Responsable (opcional)", "ph": "Comercial asignado"},
            {"key": "fecha", "label": "Fecha (AAAA-MM-DD, opcional)", "ph": "2026-09-10"},
        ])
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        d = dlg.datos()
        if not d["nombre"]:
            _aviso(self, "Rutas", "El nombre es obligatorio.", "warning")
            return
        from src.services.crm import rutas
        rid = rutas.crear_ruta(d["nombre"], responsable=d["responsable"] or None,
                               fecha=d["fecha"] or None, id_empresa=_empresa())
        if rid:
            _aviso(self, "Rutas", "Ruta creada correctamente.", "success")
            self._load_rutas()
        else:
            _aviso(self, "Rutas", "No se pudo crear la ruta.", "error")

    def _optimizar_ruta(self):
        rid = self._ruta_seleccionada()
        if not rid:
            return
        if not autorizacion.puede(self.usuario, "crm.admin"):
            _aviso(self, "Rutas", "No tiene permiso para optimizar rutas.", "warning")
            return
        from src.services.crm import rutas
        r = rutas.optimizar(rid, id_empresa=_empresa())
        if r.get("ok"):
            _aviso(self, "Rutas",
                  f"Ruta optimizada: {r['paradas']} paradas ({r['geolocalizadas']} geolocalizadas).",
                  "success")
        else:
            _aviso(self, "Rutas", "No se pudo optimizar: " + (r.get("motivo") or ""), "error")

    def _gestionar_paradas_ruta(self):
        rid = self._ruta_seleccionada()
        if not rid:
            return
        if not autorizacion.puede(self.usuario, "crm.admin"):
            _aviso(self, "Rutas", "No tiene permiso para gestionar paradas.", "warning")
            return
        _ParadasRutaDialog(self, rid, self.usuario).exec()
        self._load_rutas()

    def _tab_actividades(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 16, 0, 0); ly.setSpacing(14)
        barra = QHBoxLayout()
        barra.addStretch()
        barra.addWidget(_btn("➕ Nueva actividad", self._nueva_actividad, primary=True))
        barra.addWidget(_btn("Completar", self._completar_actividad, primary=True))
        barra.addWidget(_btn_cargando("🔄  Actualizar", self._load_actividades, primary=True))
        ly.addLayout(barra)
        ly.addWidget(self.tbl_act)
        return w

    def _actividad_seleccionada(self):
        r = self.tbl_act.currentRow()
        if r < 0 or self.tbl_act.item(r, 0) is None:
            _aviso(self, "Actividades", "Selecciona antes una actividad en la tabla.", "warning")
            return None
        try:
            return int(self.tbl_act.item(r, 0).text())
        except (TypeError, ValueError):
            return None

    def _nueva_actividad(self):
        if not autorizacion.puede(self.usuario, "crm.actividades"):
            _aviso(self, "Actividades", "No tiene permiso para crear actividades.", "warning")
            return
        eid = _empresa()
        from src.services.crm import leads, oportunidades, actividades
        op_leads = [("— Ninguno —", None)] + [(l.get("nombre"), l.get("id"))
                                              for l in leads.listar_leads(id_empresa=eid)]
        op_ops = [("— Ninguno —", None)] + [(o.get("titulo"), o.get("id"))
                                            for o in oportunidades.listar(id_empresa=eid)]
        dlg = _FormDialog(self, "Nueva actividad", [
            {"key": "tipo", "label": "Tipo", "tipo": "combo",
             "opciones": [(t.capitalize(), t) for t in actividades.TIPOS], "default": "llamada"},
            {"key": "asunto", "label": "Asunto *", "ph": "Asunto de la actividad"},
            {"key": "responsable", "label": "Responsable (ID de usuario, opcional)", "ph": "ID usuario"},
            {"key": "vencimiento", "label": "Vencimiento (AAAA-MM-DD, opcional)", "ph": "2026-09-30"},
            {"key": "lead", "label": "Lead vinculado", "tipo": "combo", "opciones": op_leads},
            {"key": "oportunidad", "label": "Oportunidad vinculada", "tipo": "combo", "opciones": op_ops},
            {"key": "notas", "label": "Notas (opcional)", "ph": "Notas"},
        ])
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        d = dlg.datos()
        if not d["asunto"]:
            _aviso(self, "Actividades", "El asunto es obligatorio.", "warning")
            return
        try:
            responsable = int(d["responsable"]) if d["responsable"] else None
        except ValueError:
            responsable = None
        aid = actividades.crear_actividad(d["tipo"], d["asunto"], id_lead=d["lead"], id_oportunidad=d["oportunidad"],
                                          responsable=responsable, vencimiento=d["vencimiento"] or None,
                                          notas=d["notas"] or None, id_empresa=eid)
        if aid:
            _aviso(self, "Actividades", "Actividad creada correctamente.", "success")
            self._load_actividades()
        else:
            _aviso(self, "Actividades", "No se pudo crear la actividad.", "error")

    def _completar_actividad(self):
        aid = self._actividad_seleccionada()
        if not aid:
            return
        if not autorizacion.puede(self.usuario, "crm.actividades"):
            _aviso(self, "Actividades", "No tiene permiso para completar actividades.", "warning")
            return
        from src.services.crm import actividades
        if actividades.completar(aid, id_empresa=_empresa()):
            _aviso(self, "Actividades", "Actividad marcada como completada.", "success")
            self._load_actividades()
        else:
            _aviso(self, "Actividades", "No se pudo completar la actividad.", "error")

    def _msg(self, titulo, texto, nivel="info"):
        try:
            from assets.estilo_global import mostrar_mensaje
            mostrar_mensaje(self, titulo, texto, nivel=nivel)
        except Exception:
            self.lbl.setText(texto)

    def _convertir_factura(self):
        row = self.tbl_ops.currentRow()
        if row < 0 or self.tbl_ops.item(row, 0) is None:
            self._msg("Convertir a factura", "Selecciona antes una oportunidad de la tabla.")
            return
        try:
            oid = int(self.tbl_ops.item(row, 0).text())
        except (TypeError, ValueError):
            return
        self._hacer_convertir_factura(oid)

    def _hacer_convertir_factura(self, oid):
        """Lógica de 'Convertir a factura' por id de oportunidad — extraída de `_convertir_factura`
        para que la pueda disparar también el diálogo de 'Oportunidad ganada' del Kanban."""
        from src.services.crm import conversion
        r = conversion.convertir_a_factura(oid)
        if r.get("ok"):
            if r.get("existente"):
                self._msg("Convertir a factura", f"La oportunidad ya tenía el documento #{r['id_factura']}.")
            else:
                self._msg("Convertir a factura",
                          f"Proforma #{r['id_factura']} generada a partir de la oportunidad.\n"
                          "Puedes convertirla en factura desde Facturación.", "success")
        else:
            self._msg("Convertir a factura", "No se pudo convertir: " + r.get("error", ""), "warning")
        self._load()

    def _convertir_proyecto(self):
        row = self.tbl_ops.currentRow()
        if row < 0 or self.tbl_ops.item(row, 0) is None:
            self._msg("Convertir a proyecto", "Selecciona antes una oportunidad de la tabla.")
            return
        try:
            oid = int(self.tbl_ops.item(row, 0).text())
        except (TypeError, ValueError):
            return
        from src.services.crm import conversion
        r = conversion.convertir_a_proyecto(oid)
        if r.get("ok"):
            if r.get("existente"):
                self._msg("Convertir a proyecto", f"La oportunidad ya tenía el proyecto #{r['id_proyecto']}.")
            else:
                self._msg("Convertir a proyecto",
                          f"Proyecto #{r['id_proyecto']} creado a partir de la oportunidad "
                          "(presupuesto = valor de la oportunidad).", "success")
        else:
            self._msg("Convertir a proyecto", "No se pudo convertir: " + r.get("error", ""), "warning")
        self._load()

    # ── Kanban de Oportunidades (vista alternativa a la tabla) ──────────────────────────────
    def _kanban_carta_movida(self, id_oportunidad, columna_origen, columna_destino):
        """Señal `cartaMovida` del `EnterpriseKanbanBoard`: una tarjeta se soltó en otra columna.
        Llama DIRECTAMENTE a `oportunidades.mover_etapa` (ya audita/actualiza probabilidad/estado) —
        no se reimplementa nada de esa lógica aquí, la GUI solo orquesta."""
        if columna_origen == columna_destino:
            return
        if not autorizacion.puede(self.usuario, "crm.pipeline"):
            _aviso(self, "Oportunidades", "No tiene permiso para mover oportunidades de etapa.", "warning")
            self._load_kanban()  # revierte la vista a lo que de verdad hay en BD
            return
        from src.services.crm import oportunidades
        r = oportunidades.mover_etapa(id_oportunidad, columna_destino, id_empresa=_empresa())
        if not r.get("ok"):
            _aviso(self, "Oportunidades", "No se pudo mover de etapa: " + (r.get("error") or ""), "error")
            self._load_kanban()
            return
        self._load_oportunidades()  # mantiene sincronizada la vista de tabla y recarga el Kanban
        if columna_destino == "ganado":
            self._ofrecer_conversion_ganada(id_oportunidad)

    def _ofrecer_conversion_ganada(self, id_oportunidad):
        op = self._kanban_cache.get(id_oportunidad) or {}
        dlg = _GanadaDialog(self, op.get("titulo") or f"Oportunidad {id_oportunidad}")
        dlg.exec()
        if dlg.accion == "pedido":
            self._generar_pedido_borrador(id_oportunidad)
        elif dlg.accion == "factura":
            self._hacer_convertir_factura(id_oportunidad)

    def _generar_pedido_borrador(self, id_oportunidad):
        """'Generar Borrador de Pedido B2B' del diálogo de Ganado: crea un PEDIDO DE CLIENTE en
        borrador (`ventas_comercial.crear_pedido_cliente`, vía `conversion.convertir_a_pedido_borrador`
        — ver ese módulo para la limitación documentada de línea única/sin itemizar)."""
        if not autorizacion.puede(self.usuario, "crm.oportunidades"):
            _aviso(self, "Oportunidades", "No tiene permiso para generar pedidos.", "warning")
            return
        from src.services.crm import conversion
        usuario_nombre = (self.usuario or {}).get("nombre") if isinstance(self.usuario, dict) else None
        r = conversion.convertir_a_pedido_borrador(id_oportunidad, id_empresa=_empresa(),
                                                    usuario=usuario_nombre)
        if r.get("ok"):
            if r.get("existente"):
                _aviso(self, "Pedido B2B",
                      f"La oportunidad ya tenía el borrador de pedido #{r['id_pedido']}.", "info")
            else:
                _aviso(self, "Pedido B2B",
                      f"Borrador de pedido #{r['id_pedido']} creado a partir de la oportunidad "
                      "(revísalo en Presupuestos → Pedidos de cliente).", "success")
        else:
            _aviso(self, "Pedido B2B", "No se pudo generar el borrador: " + (r.get("error") or ""), "warning")
        self._load()

    def _etapa_de_id(self, id_etapa):
        for e in self._kanban_etapas:
            if e.get("id") == id_etapa:
                return e.get("codigo")
        return None

    def _nombre_cliente_kanban(self, id_cliente):
        if not id_cliente:
            return None
        if id_cliente in self._cache_clientes_kanban:
            return self._cache_clientes_kanban[id_cliente]
        try:
            cli = CLIDB.obtener_cliente(id_cliente)
            nombre = (cli or {}).get("nombre")
        except Exception:
            nombre = None
        self._cache_clientes_kanban[id_cliente] = nombre
        return nombre

    def _proxima_actividad_kanban(self, id_oportunidad, eid):
        try:
            from src.services.crm import actividades
            acts = actividades.listar(id_oportunidad=id_oportunidad, id_empresa=eid, limite=20)
        except Exception:
            return None
        pendientes = [a for a in acts if a.get("estado") != "completada" and a.get("vencimiento")]
        pendientes.sort(key=lambda a: a["vencimiento"])
        act = pendientes[0] if pendientes else (acts[0] if acts else None)
        if not act:
            return None
        asunto = act.get("asunto") or act.get("tipo") or ""
        venc = act.get("vencimiento")
        return f"{asunto} ({venc})" if venc else asunto

    def _load_kanban(self):
        """Repuebla el Kanban desde la BD real (columnas = etapas vigentes del pipeline, una tarjeta
        por oportunidad). Llamado al activar la vista Kanban y tras cualquier recarga de Oportunidades
        (`_load_oportunidades`) para que tabla y Kanban nunca queden desincronizados."""
        if not hasattr(self, "kanban_oportunidades"):
            return
        eid = _empresa()
        from src.services.crm import pipeline, oportunidades
        self._kanban_etapas = pipeline.listar_etapas(id_empresa=eid)
        columnas = [{"codigo": e.get("codigo"), "titulo": e.get("nombre"), "color": e.get("color")}
                   for e in self._kanban_etapas]
        self.kanban_oportunidades.establecer_columnas(columnas)
        ops = oportunidades.listar(id_empresa=eid)
        self._kanban_cache = {o["id"]: o for o in ops}
        self._cache_clientes_kanban = {}
        tarjetas = []
        for o in ops:
            codigo = self._etapa_de_id(o.get("id_etapa"))
            if codigo is None:
                continue
            tarjetas.append({
                "id": o["id"], "columna": codigo,
                "titulo": o.get("titulo") or f"Oportunidad {o['id']}",
                "cliente": self._nombre_cliente_kanban(o.get("id_cliente")),
                "valor": o.get("valor"), "probabilidad": o.get("probabilidad"),
                "responsable": o.get("responsable"),
                "proxima_actividad": self._proxima_actividad_kanban(o["id"], eid),
            })
        self.kanban_oportunidades.establecer_tarjetas(tarjetas)

    def _load(self):
        """Recarga TODAS las pestañas de datos (botón «Actualizar»), sin importar cuáles se hayan
        visitado ya — a diferencia de `_asegurar_datos_tab`, que solo carga una vez por pestaña."""
        for idx, fn in self._load_tab_map.items():
            self._datos_cargados.add(idx)
            try:
                fn()
            except Exception as e:
                logger.debug("load CRM pestaña %s: %s", idx, e)

    def _load_oportunidades(self):
        eid = _empresa()
        from src.services.crm import oportunidades
        ops = oportunidades.listar(id_empresa=eid)
        self.tbl_ops.setRowCount(len(ops))
        for i, o in enumerate(ops):
            doc = o.get("id_factura")
            proy = o.get("id_proyecto")
            for j, v in enumerate([o.get("id"), o.get("titulo"), o.get("estado"), o.get("valor"),
                                   o.get("probabilidad"), o.get("fecha_cierre_prevista"),
                                   f"#{doc}" if doc else "—", f"#{proy}" if proy else "—"]):
                self.tbl_ops.setItem(i, j, _it(v))
        # Mantiene el Kanban (vista alternativa) sincronizado con cualquier recarga de la tabla.
        try:
            self._load_kanban()
        except Exception as e:
            logger.debug("sincronizar kanban tras _load_oportunidades: %s", e)

    def _load_kpis(self):
        eid = _empresa()
        from src.services.crm import analitica
        # `registrar_en_bi` calcula los mismos KPIs que `kpis()` y además los sincroniza con BI (mismo
        # patrón que MRP/SAT/Calidad/GMAO/Finanzas — antes CRM lo tenía definido pero sin caller real).
        k = analitica.registrar_en_bi(id_empresa=eid)
        self.tbl_kpi.setRowCount(len(k))
        for i, (nombre, val) in enumerate(k.items()):
            self.tbl_kpi.setItem(i, 0, _it(nombre)); self.tbl_kpi.setItem(i, 1, _it(val))
        self.lbl.setText(f"Forecast ponderado: {k.get('forecast', 0)} € · Conversión: {k.get('conversion_pct', 0)}%")

    # Enriquecimiento CRM (Módulo 1): campañas · objetivos · rutas.
    def _load_campanias(self):
        eid = _empresa()
        from src.services.crm import campanias
        cps = campanias.listar(id_empresa=eid)
        self.tbl_camp.setRowCount(len(cps))
        for i, cp in enumerate(cps):
            for j, v in enumerate([cp.get("id"), cp.get("nombre"), cp.get("canal"),
                                   cp.get("segmento_objetivo"), cp.get("estado"), cp.get("presupuesto")]):
                self.tbl_camp.setItem(i, j, _it(v))

    def _load_objetivos(self):
        eid = _empresa()
        from src.services.crm import objetivos
        obs = objetivos.progreso(id_empresa=eid)
        self.tbl_obj.setRowCount(len(obs))
        for i, o in enumerate(obs):
            for j, v in enumerate([o.get("responsable"), o.get("tipo"), o.get("objetivo_valor"),
                                   o.get("real"), o.get("pct"), "Sí" if o.get("cumplido") else "No"]):
                self.tbl_obj.setItem(i, j, _it(v))

    def _load_rutas(self):
        eid = _empresa()
        from src.services.crm import rutas
        rts = rutas.listar_rutas(id_empresa=eid)
        self.tbl_rutas.setRowCount(len(rts))
        for i, rt in enumerate(rts):
            for j, v in enumerate([rt.get("id"), rt.get("nombre"), rt.get("responsable"),
                                   rt.get("fecha"), rt.get("estado")]):
                self.tbl_rutas.setItem(i, j, _it(v))

    def _load_actividades(self):
        eid = _empresa()
        from src.services.crm import actividades
        filas = actividades.listar(id_empresa=eid)
        self.tbl_act.setRowCount(len(filas))
        for i, f in enumerate(filas):
            if f.get("id_lead"):
                vinculado = f"Lead #{f['id_lead']}"
            elif f.get("id_oportunidad"):
                vinculado = f"Oportunidad #{f['id_oportunidad']}"
            elif f.get("id_cliente"):
                vinculado = f"Cliente #{f['id_cliente']}"
            else:
                vinculado = "—"
            for j, v in enumerate([f.get("id"), f.get("tipo"), f.get("asunto"), vinculado,
                                   f.get("responsable"), f.get("vencimiento"), f.get("estado")]):
                self.tbl_act.setItem(i, j, _it(v))
