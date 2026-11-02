"""
GUIs MRP / Fabricación (BLOQUE 3) — AHORA OPERATIVAS.

  · MRPDashboardWindow  — cuadro de mando + BARRA DE ACCIONES sobre Órdenes de Fabricación
                          (nueva OF, planificar, liberar, iniciar, pausar, consumir, producir,
                          finalizar, cancelar) + pestaña BOM. Se embebe en Almacenes · Operaciones
                          (pestaña "MRP / Fabricación").
  · BOMWindow           — listado + ALTA de listas de materiales (BOM); pestaña de MRPDashboardWindow.
  · OrdenesFabricacionWindow / FabricacionWindow — alias de compatibilidad.

Reutiliza ÍNTEGRAMENTE los servicios MRP existentes (`services.mrp.bom/ordenes/costes/analitica/
planificador`). El consumo de componentes y el alta de producto terminado pasan por el MOTOR OFICIAL de
stock/kardex a través de `ordenes.consumir_materiales` / `ordenes.registrar_produccion` (NO hay motor de
stock paralelo). La auditoría (`FAB_*`) la emite el backend. RBAC único vía `services.autorizacion`.
"""

import logging

from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.gui.catalogo_gestion import (_BG, _CIAN, _DIM, _btn as _btn_base, _btn_cargando as _btn_cargando_base, _btn_x,
                                      _dialogo_frameless, _tabla)
from src.gui.components.completer_articulos import instalar_sugerencias_articulo
from src.gui.components.completer_centros import instalar_sugerencias_centro, resolver_id_centro

logger = logging.getLogger("gui.mrp")


def _btn(txt, slot=None, primary=False, danger=False):
    """Diseño global: los botones secundarios (antes grises) usan el estilo turquesa (contorno azul
    turquesa, fondo azul oscuro, texto turquesa, hover swap) — igual que 'Actualizar'. Los 'danger'
    (rojo) se conservan. Reutiliza el `_btn` compartido sin modificarlo (solo local a este módulo)."""
    return _btn_base(txt, slot, primary=(primary or not danger), danger=danger)


def _btn_cargando(txt, slot=None, primary=False, danger=False):
    return _btn_cargando_base(txt, slot, primary=(primary or not danger), danger=danger)


def _it(v):
    from PyQt6.QtWidgets import QTableWidgetItem
    return QTableWidgetItem("" if v is None else str(v))


class _PedirTextoDialog(QDialog):
    """Reemplazo de `QInputDialog.getText/getInt/getDouble` (sin barra de Windows, esquinas
    redondeadas, botones con texto visible) — mismo criterio ya aplicado en `tesoreria_gui.py`/
    `rrhh_gestion.py`. `validador`, si se indica, se aplica al campo (QIntValidator/QDoubleValidator)."""

    def __init__(self, titulo, prompt, texto="", parent=None, validador=None):
        super().__init__(parent)
        v = _dialogo_frameless(self, titulo, ancho=380)
        lbl = QLabel(prompt); lbl.setStyleSheet(f"color:{_CIAN};font-weight:700;")
        v.addWidget(lbl)
        self.inp = QLineEdit(str(texto)); self.inp.setFixedHeight(36)
        self.inp.setStyleSheet(f"QLineEdit{{background:{_BG};color:{_CIAN};border:2px solid {_CIAN};"
                               "border-radius:8px;padding:0 10px;}")
        if validador is not None:
            self.inp.setValidator(validador)
        self.inp.returnPressed.connect(self.accept)
        v.addWidget(self.inp)
        fila = QHBoxLayout(); fila.addStretch()
        fila.addWidget(_btn("Aceptar", self.accept, primary=True))
        v.addLayout(fila)
        self.inp.setFocus()

    def valor(self):
        return self.inp.text()


class _PedirCentroDialog(QDialog):
    """Selector de centro destino con BÚSQUEDA EN TIEMPO REAL (petición explícita, flujo
    Producción -> Logística): cualquier centro REGISTRADO de la empresa (tienda/almacén/fábrica/
    oficina/otro — `db.centros`, no solo almacenes de producción). "Omitir" conserva el
    comportamiento previo (producción sin generar ningún documento logístico automático)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = _dialogo_frameless(self, "Centro destino de la producción", ancho=420)
        lbl = QLabel("Busca y elige el centro al que se dirige esta producción (opcional):")
        lbl.setStyleSheet(f"color:{_CIAN};font-weight:700;")
        lbl.setWordWrap(True)
        v.addWidget(lbl)
        self.inp = QLineEdit()
        self.inp.setPlaceholderText("Escribe para buscar un centro…")
        self.inp.setFixedHeight(36)
        self.inp.setStyleSheet(f"QLineEdit{{background:{_BG};color:{_CIAN};border:2px solid {_CIAN};"
                               "border-radius:8px;padding:0 10px;}")
        instalar_sugerencias_centro(self.inp)
        self.inp.returnPressed.connect(self.accept)
        v.addWidget(self.inp)
        fila = QHBoxLayout(); fila.addStretch()
        fila.addWidget(_btn("Omitir", self.reject))
        fila.addWidget(_btn("Aceptar", self.accept, primary=True))
        v.addLayout(fila)
        self.inp.setFocus()

    def id_centro(self):
        return resolver_id_centro(self.inp.text())


def _pedir_texto(parent, titulo, prompt, texto=""):
    d = _PedirTextoDialog(titulo, prompt, texto, parent)
    ok = d.exec() == QDialog.DialogCode.Accepted
    return d.valor(), ok


def _pedir_entero(parent, titulo, prompt, valor=0, minimo=0, maximo=1_000_000_000):
    from PyQt6.QtGui import QIntValidator
    d = _PedirTextoDialog(titulo, prompt, valor, parent, validador=QIntValidator(minimo, maximo))
    ok = d.exec() == QDialog.DialogCode.Accepted
    try:
        return int(d.valor() or 0), ok
    except ValueError:
        return 0, False


def _pedir_decimal(parent, titulo, prompt, valor=0.0, minimo=0.0, maximo=1e9, decimales=2):
    from PyQt6.QtGui import QDoubleValidator
    val = QDoubleValidator(minimo, maximo, decimales)
    val.setNotation(QDoubleValidator.Notation.StandardNotation)
    d = _PedirTextoDialog(titulo, prompt, valor, parent, validador=val)
    ok = d.exec() == QDialog.DialogCode.Accepted
    try:
        return float((d.valor() or "0").replace(",", ".")), ok
    except ValueError:
        return 0.0, False


def _empresa():
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return EMPRESA_DEFAULT_ID


def _usuario_sesion(fallback=None):
    try:
        from src.db.usuario import sesion_global
        return sesion_global.usuario_actual or fallback or {}
    except Exception:
        return fallback or {}


def _nombre(usuario) -> str:
    u = usuario or {}
    return u.get("nombre") or u.get("usuario") or "sistema"


def _puede(usuario, permiso) -> bool:
    """RBAC ÚNICO (services.autorizacion). Degradable a True SOLO si el subsistema no está disponible
    (la ventana ya está restringida por rol en el menú)."""
    try:
        from src.services import autorizacion
        return autorizacion.puede(usuario or {}, permiso, id_empresa=_empresa())
    except Exception:
        return True


class MRPDashboardWindow(QWidget):
    """Cuadro de mando de fabricación + acciones OPERATIVAS sobre Órdenes de Fabricación."""

    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or _usuario_sesion()
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("MRP / Producción · Cuadro de mando")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        if callback_vuelta:
            cab.addWidget(_btn_x(self._volver))
        root.addLayout(cab)
        self.lbl = QLabel(""); self.lbl.setStyleSheet(f"color:{_DIM};")
        root.addWidget(self.lbl)
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("QTabWidget::pane{border:none;}")

        # ── Órdenes de Fabricación: barra de acciones OPERATIVAS + tabla ──
        of_page = QWidget(); of_l = QVBoxLayout(of_page)
        bar = QHBoxLayout()
        bar.addWidget(_btn("➕  Nueva OP", self._nueva_of, primary=True))
        for txt, fn in (("Planificar", lambda: self._accion("planificar")),
                        ("Liberar", lambda: self._accion("liberar")),
                        ("Iniciar", lambda: self._accion("iniciar")),
                        ("Pausar", lambda: self._accion("pausar")),
                        ("Consumir materiales", self._consumir),
                        ("Registrar producción", self._producir),
                        ("Finalizar", self._finalizar),
                        ("Cancelar", lambda: self._accion("cancelar"))):
            bar.addWidget(_btn(txt, fn))
        bar.addStretch()
        bar.addWidget(_btn_cargando("🔄  Actualizar", self._load, primary=True))
        of_l.addLayout(bar)
        self.tbl_of = _tabla(["ID", "Código", "Artículo", "Cant", "Producido", "Estado"])
        of_l.addWidget(self.tbl_of)

        # Sugerencias MRP: trigger manual (planificador.generar_sugerencias/calcular_necesidades no
        # tenían ningún botón — la tabla estaba siempre vacía salvo inserción externa).
        sug_page = QWidget(); sug_l = QVBoxLayout(sug_page); sug_l.setContentsMargins(0, 12, 0, 0)
        bar_sug = QHBoxLayout()
        btn_generar_sug = _btn("⚙  Generar sugerencias", self._generar_sugerencias, primary=True)
        btn_generar_sug.setMinimumWidth(btn_generar_sug.sizeHint().width() + 36)
        bar_sug.addWidget(btn_generar_sug)
        bar_sug.addStretch()
        sug_l.addLayout(bar_sug)
        self.tbl_sug = _tabla(["Tipo", "Artículo", "Cantidad", "Estado"])
        sug_l.addWidget(self.tbl_sug)

        self.tbl_kpi = _tabla(["KPI", "Valor"])
        kpi_page = QWidget(); kpi_l = QVBoxLayout(kpi_page); kpi_l.setContentsMargins(0, 12, 0, 0)
        bar_kpi = QHBoxLayout()
        btn_prevision = _btn("📈  Previsión de producción", self._prevision_produccion)
        btn_prevision.setMinimumWidth(btn_prevision.sizeHint().width() + 36)
        bar_kpi.addWidget(btn_prevision)
        bar_kpi.addStretch()
        kpi_l.addLayout(bar_kpi)
        kpi_l.addWidget(self.tbl_kpi)

        self.tabs.addTab(of_page, "Órdenes de Producción")
        self.tabs.addTab(sug_page, "Sugerencias MRP")
        self.tabs.addTab(kpi_page, "KPIs")
        # BOM (alta/listado de listas de materiales): integrado como pestaña del cuadro de mando para que
        # esté disponible allá donde se use MRPDashboardWindow (p. ej. Almacenes · Operaciones → MRP).
        self.bom_win = BOMWindow(usuario=self.usuario, main=main)
        self.tabs.addTab(self.bom_win, "Lista de materiales")
        self.tabs.addTab(self._tab_mps(), "Plan Maestro (MPS)")
        self.tabs.addTab(self._tab_centros(), "Centros de trabajo")
        self.tabs.addTab(self._tab_planta(), "Control de planta")
        root.addWidget(self.tabs)
        self._load()

    def _envolver_tabla(self, tabla):
        """Envuelve una tabla que es TODA la pestaña con un margen superior — pegada directamente
        al borde de la pestaña, su contorno se veía más fino por arriba que por los otros lados."""
        w = QWidget(); ly = QVBoxLayout(w)
        ly.setContentsMargins(0, 12, 0, 0)
        ly.addWidget(tabla)
        return w

    # ── carga (solo lectura) ──────────────────────────────────────────────────
    def _load(self):
        eid = _empresa()
        try:
            from src.services.mrp import analitica, ordenes, planificador
            ofs = ordenes.listar(id_empresa=eid)
            self.tbl_of.setRowCount(len(ofs))
            for i, o in enumerate(ofs):
                for j, v in enumerate([o.get("id"), o.get("codigo"), o.get("articulo_final"),
                                       o.get("cantidad"), o.get("cantidad_producida"), o.get("estado")]):
                    self.tbl_of.setItem(i, j, _it(v))
            sug = planificador.listar_sugerencias(id_empresa=eid)
            self.tbl_sug.setRowCount(len(sug))
            for i, s in enumerate(sug):
                for j, v in enumerate([s.get("tipo"), s.get("articulo"), s.get("cantidad"), s.get("estado")]):
                    self.tbl_sug.setItem(i, j, _it(v))
            # `registrar_en_bi` calcula los mismos KPIs que `kpis()` y además los sincroniza con BI
            # (mismo patrón que `finanzas.dashboard` — único módulo que ya lo hacía; el resto de
            # analíticas PRO de esta auditoría lo tenían definido pero sin ningún caller real).
            k = analitica.registrar_en_bi(id_empresa=eid)
            self.tbl_kpi.setRowCount(len(k))
            for i, (nombre, val) in enumerate(k.items()):
                self.tbl_kpi.setItem(i, 0, _it(nombre)); self.tbl_kpi.setItem(i, 1, _it(val))
            self.lbl.setText(f"OP en curso: {k.get('of_en_curso', 0)} · Eficiencia: {k.get('eficiencia_pct', 0)}%")
        except Exception as e:
            logger.error("load MRP: %s", e)
            self.lbl.setText(f"Error: {e}")

    # ── acciones operativas ───────────────────────────────────────────────────
    def _set(self, msg, nivel="info"):
        try:
            from assets.estilo_global import mostrar_mensaje
            mostrar_mensaje(self, "MRP / Producción", msg, nivel=nivel)
        except Exception:
            pass

    def _of_sel(self):
        row = self.tbl_of.currentRow()
        if row < 0:
            return None
        it = self.tbl_of.item(row, 0)
        try:
            return int(it.text()) if it and it.text() else None
        except ValueError:
            return None

    def _accion(self, accion):
        # planificar exige mrp.planificar; el resto de transiciones (liberar/iniciar/pausar/cancelar)
        # exigen mrp.admin (gestión). RBAC único, sin sistema paralelo.
        perm = "mrp.planificar" if accion == "planificar" else "mrp.admin"
        if not _puede(self.usuario, perm):
            self._set(f"Permiso requerido: {perm}", nivel="warning"); return
        oid = self._of_sel()
        if not oid:
            self._set("Selecciona una OP en la tabla.", nivel="warning"); return
        from src.services.mrp import ordenes
        try:
            r = getattr(ordenes, accion)(oid, id_empresa=_empresa())
        except Exception as e:
            self._set(f"Error: {e}", nivel="error"); return
        self._set(f"OP {oid} → {r.get('estado')}" if r.get("ok") else f"OP {oid}: {r.get('error')}",
                 nivel="success" if r.get("ok") else "error")
        self._load()

    def _consumir(self):
        if not _puede(self.usuario, "mrp.admin"):
            self._set("Permiso requerido: mrp.admin", nivel="warning"); return
        oid = self._of_sel()
        if not oid:
            self._set("Selecciona una OP.", nivel="warning"); return
        from src.services.mrp import ordenes
        r = ordenes.consumir_materiales(oid, id_empresa=_empresa(), usuario=_nombre(self.usuario))
        if not r.get("ok"):
            self._set(f"OP {oid}: {r.get('error')}", nivel="error")
        elif r.get("faltantes"):
            self._set(f"OP {oid}: consumido con ROTURAS → {r['faltantes']}", nivel="warning")
        else:
            self._set(f"OP {oid}: materiales consumidos ({len(r.get('consumidos', []))} componentes) "
                      "vía kardex oficial.", nivel="success")
        self._load()

    def _producir(self):
        if not _puede(self.usuario, "mrp.admin"):
            self._set("Permiso requerido: mrp.admin", nivel="warning"); return
        oid = self._of_sel()
        if not oid:
            self._set("Selecciona una OP.", nivel="warning"); return
        cant, ok = _pedir_entero(self, "Registrar producción",
                                 "Cantidad de producto terminado a dar de alta:", 1, 1, 100000000)
        if not ok:
            return
        dlg_centro = _PedirCentroDialog(self)
        id_centro_destino = dlg_centro.id_centro() if dlg_centro.exec() == QDialog.DialogCode.Accepted else None
        from src.services.mrp import ordenes
        r = ordenes.registrar_produccion(oid, cant, id_empresa=_empresa(), usuario=_nombre(self.usuario),
                                         id_centro_destino=id_centro_destino)
        if not r.get("ok"):
            self._set(f"OP {oid}: {r.get('error')}", nivel="error")
        else:
            msg = f"OP {oid}: producidas {cant} uds (lote {r.get('lote')}) → entrada de stock oficial."
            log = (r.get("logistica") or {})
            if log.get("ok") and not log.get("ya_existia"):
                xd = (log.get("cross_docking") or {})
                if xd.get("cross_dockeado"):
                    ruta = xd.get("ruta") or {}
                    msg += (f" Cross-docking automático → ruta #{ruta.get('id_ruta')} "
                           f"({ruta.get('fecha') or '—'}), sin pasar por almacén.")
                else:
                    msg += " Mercancía registrada en Logística, pendiente de ruta disponible."
            self._set(msg, nivel="success")
        self._load()

    def _finalizar(self):
        if not _puede(self.usuario, "mrp.admin"):
            self._set("Permiso requerido: mrp.admin", nivel="warning"); return
        oid = self._of_sel()
        if not oid:
            self._set("Selecciona una OP.", nivel="warning"); return
        from src.services.mrp import ordenes
        r = ordenes.finalizar(oid, id_empresa=_empresa(), usuario=_nombre(self.usuario))
        if r.get("ok"):
            c = r.get("costes") or {}
            self._set(f"OP {oid} FINALIZADA. Coste real: {c.get('coste_real', '—')} "
                     f"(estimado {c.get('coste_estimado', '—')}, desviación {c.get('desviacion', '—')})",
                     nivel="success")
        else:
            self._set(f"OP {oid}: {r.get('error')}", nivel="error")
        self._load()

    def _nueva_of(self):
        if not _puede(self.usuario, "mrp.admin"):
            self._set("Permiso requerido: mrp.admin", nivel="warning"); return
        dlg = _NuevaOFDialog(self)
        if dlg.exec() and dlg.resultado:
            art, cant, alm = dlg.resultado
            from src.services.mrp import ordenes
            # `ordenes_fabricacion.responsable` es INT (id de usuario), no el nombre — a diferencia de
            # `partes_trabajo_prod.operario` (VARCHAR), que sí usa `_nombre(...)`. Pasar el nombre aquí
            # hacía fallar SIEMPRE la creación de la OP con un error de tipo en MariaDB (bug real
            # descubierto al verificar esta pestaña contra la BD, no solo un hueco de auditoría).
            oid = ordenes.crear_orden(art, cant, id_almacen=alm, id_empresa=_empresa(),
                                      responsable=self.usuario.get("id"))
            self._set(f"OP creada: {oid} ({art} x{cant})" if oid
                      else "No se pudo crear la OP (¿existe BOM activa del artículo?).",
                     nivel="success" if oid else "error")
            self._load()

    # ── Sugerencias MRP: trigger manual (services.mrp.planificador) ────────────
    def _generar_sugerencias(self):
        if not _puede(self.usuario, "mrp.planificar"):
            self._set("Permiso requerido: mrp.planificar", nivel="warning"); return
        dlg = _DemandaDialog(self)
        if dlg.exec() and dlg.resultado:
            art, cant = dlg.resultado
            from src.services.mrp import planificador
            try:
                r = planificador.generar_sugerencias({art: cant}, id_empresa=_empresa())
            except Exception as e:
                self._set(f"No se pudieron generar las sugerencias: {e}", nivel="error"); return
            self._set(f"Sugerencias generadas: {len(r.get('compras', []))} de compra, "
                     f"{len(r.get('fabricacion', []))} de producción.", nivel="success")
            self._load()

    # ── KPIs: previsión de producción (services.mrp.analitica) ─────────────────
    def _prevision_produccion(self):
        art, ok = _pedir_texto(self, "Previsión de producción", "Código del artículo final:")
        if not ok:
            return
        if not art.strip():
            self._set("Indica el código del artículo final.", nivel="warning"); return
        from src.services.mrp import analitica
        try:
            r = analitica.prevision_produccion(art.strip(), id_empresa=_empresa())
        except Exception as e:
            self._set(f"No se pudo calcular la previsión: {e}", nivel="error"); return
        prev = ", ".join(str(v) for v in r.get("prevision", []))
        self._set(f"Previsión ({r.get('metodo')}, {r.get('puntos_historicos', 0)} punto(s) históricos): "
                 f"{prev}", nivel="info")

    # ── Plan Maestro (MPS) ───────────────────────────────────────────────────────
    def _tab_mps(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 12, 0, 0)
        fila = QHBoxLayout()
        self.in_mps_periodo = QLineEdit(); self.in_mps_periodo.setPlaceholderText("Periodo AAAA-MM")
        fila.addWidget(QLabel("Periodo:")); fila.addWidget(self.in_mps_periodo)
        fila.addWidget(_btn("Cargar", self._mps_cargar, primary=True))
        fila.addWidget(_btn("Confirmar periodo", self._mps_confirmar))
        fila.addWidget(_btn("🚀 Lanzar MRP", self._mps_lanzar, primary=True))
        fila.addStretch()
        ly.addLayout(fila)
        self.tbl_mps = _tabla(["Artículo", "Demanda pedidos", "Demanda previsión", "Demanda total",
                               "Plan producción", "Estado"])
        ly.addWidget(self.tbl_mps)
        fila2 = QHBoxLayout()
        self.in_mps_art = QLineEdit(); self.in_mps_art.setPlaceholderText("Artículo")
        instalar_sugerencias_articulo(self.in_mps_art)
        self.in_mps_dp = QLineEdit("0"); self.in_mps_dp.setPlaceholderText("Demanda pedidos")
        self.in_mps_dpv = QLineEdit("0"); self.in_mps_dpv.setPlaceholderText("Demanda previsión")
        self.in_mps_plan = QLineEdit(); self.in_mps_plan.setPlaceholderText("Plan producción (opcional)")
        for wd in (self.in_mps_art, self.in_mps_dp, self.in_mps_dpv, self.in_mps_plan):
            fila2.addWidget(wd)
        fila2.addWidget(_btn("＋ Fijar línea", self._mps_fijar_linea, primary=True))
        ly.addLayout(fila2)
        return w

    def _mps_periodo(self):
        p = self.in_mps_periodo.text().strip()
        if not p:
            self._set("Indica el periodo (AAAA-MM).", nivel="warning")
            return None
        return p

    def _mps_cargar(self):
        p = self._mps_periodo()
        if not p:
            return
        from src.services.mrp import mps
        filas = mps.plan_maestro(p, id_empresa=_empresa())
        self.tbl_mps.setRowCount(len(filas))
        for i, r in enumerate(filas):
            for j, v in enumerate([r.get("articulo"), r.get("demanda_pedidos"), r.get("demanda_prevision"),
                                   r.get("demanda_total"), r.get("plan_produccion"), r.get("estado")]):
                self.tbl_mps.setItem(i, j, _it(v))

    def _mps_fijar_linea(self):
        p = self._mps_periodo()
        if not p:
            return   # _mps_periodo() ya ha mostrado el aviso correspondiente
        art = self.in_mps_art.text().strip()
        if "–" in art:  # viene del autocompletado "CÓDIGO – NOMBRE"
            art = art.split("–")[0].strip()
        if not art:
            self._set("Indica el artículo.", nivel="warning"); return
        try:
            dp = float(self.in_mps_dp.text().strip().replace(",", ".") or 0)
            dpv = float(self.in_mps_dpv.text().strip().replace(",", ".") or 0)
            plan_txt = self.in_mps_plan.text().strip()
            plan = float(plan_txt.replace(",", ".")) if plan_txt else None
        except ValueError:
            self._set("Las cantidades deben ser numéricas.", nivel="error"); return
        from src.services.mrp import mps
        mid = mps.fijar_linea_mps(p, art, demanda_pedidos=dp, demanda_prevision=dpv,
                                  plan_produccion=plan, id_empresa=_empresa())
        self._set(f"Línea MPS {art}/{p} fijada." if mid else "No se pudo fijar la línea.",
                 nivel="success" if mid else "error")
        if mid:
            self.in_mps_art.clear(); self.in_mps_dp.setText("0"); self.in_mps_dpv.setText("0")
            self.in_mps_plan.clear()
            self._mps_cargar()

    def _mps_confirmar(self):
        p = self._mps_periodo()
        if not p:
            return
        from src.services.mrp import mps
        r = mps.confirmar_periodo(p, id_empresa=_empresa())
        self._set(f"Periodo {p} confirmado." if r.get("ok") else r.get("motivo", "No se pudo confirmar."),
                 nivel="success" if r.get("ok") else "error")
        self._mps_cargar()

    def _mps_lanzar(self):
        p = self._mps_periodo()
        if not p:
            return
        from src.services.mrp import mps
        r = mps.lanzar_mrp(p, id_empresa=_empresa())
        if r.get("ok"):
            self._set(f"MRP lanzado sobre {len(r.get('demanda', {}))} artículo(s): "
                     f"{len(r.get('compras', []))} sugerencia(s) de compra, "
                     f"{len(r.get('fabricacion', []))} de producción.", nivel="success")
            self._load()
        else:
            self._set(r.get("motivo", "No se pudo lanzar el MRP."), nivel="error")

    # ── Centros de trabajo ────────────────────────────────────────────────────────
    def _tab_centros(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 12, 0, 0)
        fila = QHBoxLayout()
        btn_centro = _btn("➕ Nuevo centro", self._nuevo_centro, primary=True)
        btn_ruta = _btn("🧭 Nueva ruta", self._nueva_ruta)
        btn_cal = _btn("📅 Fijar calendario", self._fijar_calendario)
        # Con el hover (fuente ligeramente más ancha para el emoji) el texto se veía cortado —
        # se fija un ancho mínimo con margen, mismo criterio que el resto de botones con emoji.
        for _b in (btn_centro, btn_ruta, btn_cal):
            _b.setMinimumWidth(_b.sizeHint().width() + 36)
        fila.addWidget(btn_centro)
        fila.addWidget(btn_ruta)
        fila.addWidget(btn_cal)
        fila.addStretch()
        fila.addWidget(_btn_cargando("🔄  Actualizar", self._cargar_centros, primary=True))
        ly.addLayout(fila)
        self.tbl_centros = _tabla(["ID", "Código", "Nombre", "Tipo", "Coste/hora"])
        ly.addWidget(self.tbl_centros)
        self._cargar_centros()
        return w

    def _cargar_centros(self):
        from src.services.mrp import centros
        filas = centros.listar_centros(id_empresa=_empresa())
        self.tbl_centros.setRowCount(len(filas))
        for i, c in enumerate(filas):
            for j, v in enumerate([c.get("id"), c.get("codigo"), c.get("nombre"), c.get("tipo"),
                                   c.get("coste_hora")]):
                self.tbl_centros.setItem(i, j, _it(v))

    def _nuevo_centro(self):
        if not _puede(self.usuario, "mrp.admin"):
            self._set("Permiso requerido: mrp.admin", nivel="warning"); return
        dlg = _NuevoCentroDialog(self)
        if dlg.exec() and dlg.resultado:
            from src.services.mrp import centros
            cid = centros.crear_centro(**dlg.resultado, id_empresa=_empresa())
            self._set(f"Centro creado: {cid}" if cid else "No se pudo crear el centro.",
                     nivel="success" if cid else "error")
            self._cargar_centros()

    def _nueva_ruta(self):
        if not _puede(self.usuario, "mrp.admin"):
            self._set("Permiso requerido: mrp.admin", nivel="warning"); return
        dlg = _NuevaRutaDialog(self)
        if dlg.exec() and dlg.resultado:
            art, cod, nombre, ops = dlg.resultado
            from src.services.mrp import centros
            rid = centros.crear_ruta(art, cod, nombre=nombre or None, operaciones=ops, id_empresa=_empresa())
            self._set(f"Ruta creada: {rid} ({len(ops)} operación/es)" if rid else "No se pudo crear la ruta.",
                     nivel="success" if rid else "error")

    def _fijar_calendario(self):
        if not _puede(self.usuario, "mrp.admin"):
            self._set("Permiso requerido: mrp.admin", nivel="warning"); return
        row = self.tbl_centros.currentRow()
        if row < 0:
            self._set("Selecciona un centro en la tabla.", nivel="warning"); return
        cid = int(self.tbl_centros.item(row, 0).text())
        fecha, ok = _pedir_texto(self, "Fijar calendario", "Fecha (AAAA-MM-DD):")
        if not ok or not fecha.strip():
            return
        horas, ok = _pedir_decimal(self, "Fijar calendario", "Horas disponibles:", 8.0, 0.0, 24.0)
        if not ok:
            return
        from src.services.mrp import centros
        r = centros.fijar_calendario(cid, fecha.strip(), horas=horas, id_empresa=_empresa())
        self._set(f"Calendario del centro {cid} fijado ({fecha.strip()}, {horas}h)." if r
                 else "No se pudo fijar el calendario.", nivel="success" if r else "error")

    # ── Control de planta (produccion_pro: partes de trabajo + CRP) ─────────────
    def _tab_planta(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 12, 0, 0)
        desc = QLabel("Partes de trabajo (operaciones ejecutadas) y carga de centros (CRP) — "
                     "services.mrp.produccion_pro, sin frontend hasta esta auditoría.")
        desc.setStyleSheet(f"color:{_DIM};"); desc.setWordWrap(True)
        ly.addWidget(desc)
        fila = QHBoxLayout()
        self.in_planta_of = QLineEdit(); self.in_planta_of.setPlaceholderText("ID de la OP")
        self.in_planta_centro = QLineEdit(); self.in_planta_centro.setPlaceholderText("ID centro (opcional)")
        self.in_planta_cant = QLineEdit("0"); self.in_planta_cant.setPlaceholderText("Cantidad")
        self.in_planta_tiempo = QLineEdit("0"); self.in_planta_tiempo.setPlaceholderText("Tiempo (min)")
        for wd in (self.in_planta_of, self.in_planta_centro, self.in_planta_cant, self.in_planta_tiempo):
            fila.addWidget(wd)
        fila.addWidget(_btn("＋ Registrar parte", self._registrar_parte, primary=True))
        ly.addLayout(fila)
        fila2 = QHBoxLayout()
        fila2.addWidget(_btn("📊 Ver avance de la OP", self._ver_avance))
        fila2.addWidget(_btn("🏭 Ver carga de un centro (CRP)", self._ver_carga_centro))
        fila2.addStretch()
        ly.addLayout(fila2)
        self.tbl_partes = _tabla(["ID", "OP", "Centro", "Cantidad", "Tiempo (min)", "Operario", "Fecha"])
        ly.addWidget(self.tbl_partes)
        return w

    def _registrar_parte(self):
        if not _puede(self.usuario, "mrp.admin"):
            self._set("Permiso requerido: mrp.admin", nivel="warning"); return
        try:
            oid = int(self.in_planta_of.text().strip())
        except ValueError:
            self._set("Indica el ID de la OP.", nivel="warning"); return
        centro_txt = self.in_planta_centro.text().strip()
        try:
            cantidad = float(self.in_planta_cant.text().strip().replace(",", ".") or 0)
            tiempo = float(self.in_planta_tiempo.text().strip().replace(",", ".") or 0)
        except ValueError:
            self._set("Cantidad/tiempo deben ser numéricos.", nivel="error"); return
        from src.services.mrp import produccion_pro as PP
        try:
            pid = PP.registrar_parte(oid, id_centro=(int(centro_txt) if centro_txt else None), cantidad=cantidad,
                                     tiempo_min=tiempo, operario=_nombre(self.usuario), id_empresa=_empresa())
        except Exception as e:
            self._set(f"No se pudo registrar el parte: {e}", nivel="error"); return
        if pid:
            self._set(f"Parte {pid} registrado en OP {oid}.", nivel="success")
            self._cargar_partes(oid)
        else:
            self._set("No se pudo registrar el parte.", nivel="error")

    def _cargar_partes(self, oid):
        from src.services.mrp import produccion_pro as PP
        filas = PP.partes_de_orden(oid, id_empresa=_empresa())
        self.tbl_partes.setRowCount(len(filas))
        for i, p in enumerate(filas):
            for j, v in enumerate([p.get("id"), p.get("id_orden"), p.get("id_centro"), p.get("cantidad"),
                                   p.get("tiempo_min"), p.get("operario"), p.get("fecha")]):
                self.tbl_partes.setItem(i, j, _it(v))

    def _ver_avance(self):
        try:
            oid = int(self.in_planta_of.text().strip())
        except ValueError:
            self._set("Indica el ID de la OP.", nivel="warning"); return
        from src.services.mrp import produccion_pro as PP
        try:
            r = PP.avance_orden(oid, id_empresa=_empresa())
        except Exception as e:
            self._set(f"No se pudo obtener el avance de la OP: {e}", nivel="error"); return
        self._cargar_partes(oid)
        self._set(f"OP {oid}: {r.get('operaciones_con_parte', 0)}/{r.get('operaciones_ruta') or '—'} "
                 f"operación(es) ({r.get('avance_pct', '—')}%), {r.get('cantidad_reportada', 0)} uds "
                 f"reportadas, {r.get('tiempo_total_min', 0)} min.", nivel="info")

    def _ver_carga_centro(self):
        centro_txt, ok = _pedir_texto(self, "Carga de centro (CRP)", "ID del centro:")
        if not ok or not centro_txt.strip():
            return
        try:
            cid = int(centro_txt.strip())
        except ValueError:
            self._set("El ID del centro debe ser numérico.", nivel="error"); return
        from src.services.mrp import produccion_pro as PP
        r = PP.carga_centro(cid, id_empresa=_empresa())
        if not r:
            self._set(f"Centro {cid}: sin datos de carga.", nivel="warning"); return
        nivel = "warning" if r.get("sobrecarga") else "info"
        self._set(f"Centro {cid}: carga {r.get('carga_horas')}h / capacidad {r.get('capacidad_horas')}h "
                 f"({r.get('ocupacion_pct', '—')}% ocupación)"
                 + (" — ⚠️ SOBRECARGA" if r.get("sobrecarga") else ""), nivel=nivel)


class _DemandaDialog(QDialog):
    """Demanda ad-hoc (artículo + cantidad) para `planificador.generar_sugerencias`/`calcular_necesidades`."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.resultado = None
        self.setWindowTitle("Generar sugerencias MRP")
        body = _dialogo_frameless(self, "Generar sugerencias MRP")
        f = QFormLayout(); body.addLayout(f)
        self.in_art = QLineEdit(); self.in_art.setPlaceholderText("Código del artículo final")
        instalar_sugerencias_articulo(self.in_art)
        from PyQt6.QtGui import QDoubleValidator
        self.in_cant = QLineEdit("1")
        val = QDoubleValidator(0.001, 1e9, 3, self.in_cant)
        val.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.in_cant.setValidator(val)
        f.addRow("Artículo:", self.in_art)
        f.addRow("Cantidad (demanda):", self.in_cant)
        row = QHBoxLayout()
        row.addWidget(_btn("Generar", self._ok, primary=True))
        body.addLayout(row)

    def _ok(self):
        art = self.in_art.text().strip()
        if "–" in art:  # viene del autocompletado "CÓDIGO – NOMBRE"
            art = art.split("–")[0].strip()
        if not art:
            return
        try:
            cant = float((self.in_cant.text() or "0").replace(",", "."))
        except ValueError:
            cant = 0.0
        if cant <= 0:
            return
        self.resultado = (art, cant)
        self.accept()


class _NuevoCentroDialog(QDialog):
    """Alta de centro de trabajo (reutiliza centros.crear_centro)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.resultado = None
        self.setWindowTitle("Nuevo centro de trabajo")
        body = _dialogo_frameless(self, "Nuevo centro de trabajo")
        f = QFormLayout(); body.addLayout(f)
        self.in_cod = QLineEdit(); self.in_cod.setPlaceholderText("Código")
        self.in_nom = QLineEdit(); self.in_nom.setPlaceholderText("Nombre")
        from PyQt6.QtWidgets import QComboBox
        self.cb_tipo = QComboBox()
        for t in ("linea", "maquina", "operario", "celula"):
            self.cb_tipo.addItem(t, t)
        self.in_coste = QLineEdit("0")
        self.in_horas = QLineEdit("8")
        self.in_uds = QLineEdit("0")
        f.addRow("Código:", self.in_cod)
        f.addRow("Nombre:", self.in_nom)
        f.addRow("Tipo:", self.cb_tipo)
        f.addRow("Coste/hora:", self.in_coste)
        f.addRow("Horas/día:", self.in_horas)
        f.addRow("Unidades/hora:", self.in_uds)
        row = QHBoxLayout()
        row.addWidget(_btn("Crear", self._ok, primary=True))
        body.addLayout(row)

    def _ok(self):
        cod = self.in_cod.text().strip(); nom = self.in_nom.text().strip()
        if not cod or not nom:
            return
        def _f(le, d=0.0):
            try:
                return float((le.text() or "0").replace(",", "."))
            except ValueError:
                return d
        self.resultado = {"codigo": cod, "nombre": nom, "tipo": self.cb_tipo.currentData(),
                          "coste_hora": _f(self.in_coste), "horas_dia": _f(self.in_horas, 8),
                          "unidades_hora": _f(self.in_uds)}
        self.accept()


class _NuevaRutaDialog(QDialog):
    """Alta de ruta de fabricación con sus operaciones (reutiliza centros.crear_ruta)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.resultado = None
        self.setWindowTitle("Nueva ruta de producción")
        v = _dialogo_frameless(self, "Nueva ruta de producción", ancho=560)
        f = QFormLayout()
        self.in_art = QLineEdit(); self.in_art.setPlaceholderText("Artículo final")
        instalar_sugerencias_articulo(self.in_art)
        self.in_cod = QLineEdit(); self.in_cod.setPlaceholderText("Código de ruta")
        self.in_nom = QLineEdit(); self.in_nom.setPlaceholderText("Nombre (opcional)")
        f.addRow("Artículo final:", self.in_art)
        f.addRow("Código:", self.in_cod)
        f.addRow("Nombre:", self.in_nom)
        v.addLayout(f)
        v.addWidget(QLabel("Operaciones (nombre / ID centro opcional / tiempo estándar min):"))
        self.tbl = _tabla(["Nombre", "ID centro", "Tiempo (min)"])
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.AllEditTriggers)
        # El rectángulo turquesa de selección de `_tabla` (pensado para tablas de SOLO LECTURA)
        # tapaba el texto mientras se edita una celda — mismo fix ya aplicado en
        # `crm_dashboard.py::_page_presupuestos` para su tabla de líneas editable: selección
        # transparente + editor (QLineEdit interno) con su propio fondo/selección legibles.
        self.tbl.setStyleSheet(
            self.tbl.styleSheet()
            + "QTableWidget::item:selected{background:transparent;color:white;}"
              f"QTableWidget QLineEdit{{border:none;background:{_BG};color:white;padding:0 2px;"
              "margin:0;selection-background-color:#00FFC655;selection-color:white;}")
        self.tbl.setRowCount(4)
        for r in range(self.tbl.rowCount()):
            for c in range(3):
                self.tbl.setItem(r, c, _it(""))
        v.addWidget(self.tbl)
        row = QHBoxLayout()
        row.addWidget(_btn("Añadir fila", self._add_row))
        row.addStretch()
        row.addWidget(_btn("Crear ruta", self._ok, primary=True))
        v.addLayout(row)

    def _add_row(self):
        r = self.tbl.rowCount()
        self.tbl.insertRow(r)
        for c in range(3):
            self.tbl.setItem(r, c, _it(""))

    def _ok(self):
        art = self.in_art.text().strip()
        if "–" in art:  # viene del autocompletado "CÓDIGO – NOMBRE"
            art = art.split("–")[0].strip()
        cod = self.in_cod.text().strip()
        if not art or not cod:
            return
        ops = []
        for r in range(self.tbl.rowCount()):
            it0 = self.tbl.item(r, 0)
            nombre = it0.text().strip() if it0 else ""
            if not nombre:
                continue
            it1 = self.tbl.item(r, 1); it2 = self.tbl.item(r, 2)
            centro_txt = it1.text().strip() if it1 else ""
            try:
                tiempo = float(it2.text()) if it2 and it2.text().strip() else 0
            except ValueError:
                tiempo = 0
            ops.append({"nombre": nombre, "id_centro": int(centro_txt) if centro_txt.isdigit() else None,
                       "tiempo_estandar_min": tiempo})
        if not ops:
            return
        self.resultado = (art, cod, self.in_nom.text().strip(), ops)
        self.accept()


class _NuevaOFDialog(QDialog):
    """Alta de una Orden de Fabricación (reutiliza ordenes.crear_orden: explosiona la BOM activa)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.resultado = None
        self.setWindowTitle("Nueva Orden de Producción")
        body = _dialogo_frameless(self, "Nueva Orden de Producción")
        f = QFormLayout(); body.addLayout(f)
        self.in_art = QLineEdit(); self.in_art.setPlaceholderText("Código del artículo a fabricar")
        instalar_sugerencias_articulo(self.in_art)
        # QLineEdit + validador en vez de QDoubleSpinBox: la app oculta sus flechas arriba/abajo vía
        # QSS y eso rompía su foco/clic en varios diálogos (confirmado por el usuario) — mismo
        # criterio ya aplicado en `sat_dashboard._FormDialog`.
        from PyQt6.QtGui import QDoubleValidator
        self.in_cant = QLineEdit("1.000")
        val_cant = QDoubleValidator(0.001, 1e9, 3, self.in_cant)
        val_cant.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.in_cant.setValidator(val_cant)
        self.in_alm = QLineEdit(); self.in_alm.setPlaceholderText("(opcional) ID de almacén")
        f.addRow("Artículo final:", self.in_art)
        f.addRow("Cantidad:", self.in_cant)
        f.addRow("Almacén:", self.in_alm)
        row = QHBoxLayout()
        row.addWidget(_btn("Crear", self._ok, primary=True))
        body.addLayout(row)

    def _ok(self):
        art = self.in_art.text().strip()
        if "–" in art:  # viene del autocompletado "CÓDIGO – NOMBRE"
            art = art.split("–")[0].strip()
        if not art:
            return
        alm = self.in_alm.text().strip()
        try:
            cant = float((self.in_cant.text() or "0").replace(",", "."))
        except ValueError:
            cant = 0.0
        self.resultado = (art, cant, alm or None)
        self.accept()


class _NuevaBOMDialog(QDialog):
    """Alta de una lista de materiales (reutiliza bom.crear_bom)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.resultado = None
        self.setWindowTitle("Nueva Lista de Materiales (BOM)")
        v = _dialogo_frameless(self, "Nueva Lista de Materiales (BOM)", ancho=560)
        f = QFormLayout()
        self.in_art = QLineEdit(); self.in_art.setPlaceholderText("Artículo final (producto fabricable)")
        instalar_sugerencias_articulo(self.in_art)
        self.in_ver = QLineEdit("1")
        from PyQt6.QtGui import QDoubleValidator
        self.in_base = QLineEdit("1.000")
        val_base = QDoubleValidator(0.001, 1e9, 3, self.in_base)
        val_base.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.in_base.setValidator(val_base)
        f.addRow("Artículo final:", self.in_art)
        f.addRow("Versión:", self.in_ver)
        f.addRow("Cantidad base:", self.in_base)
        v.addLayout(f)
        v.addWidget(QLabel("Componentes:"))
        self.tbl = _tabla(["Componente", "Cantidad", "Merma %"])
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.AllEditTriggers)
        self.tbl.setRowCount(6)
        for r in range(self.tbl.rowCount()):
            for c in range(3):
                self.tbl.setItem(r, c, _it(""))
        v.addWidget(self.tbl)
        row = QHBoxLayout()
        row.addWidget(_btn("Añadir fila", self._add_row))
        row.addStretch()
        row.addWidget(_btn("Crear BOM", self._ok, primary=True))
        v.addLayout(row)

    def _add_row(self):
        r = self.tbl.rowCount()
        self.tbl.insertRow(r)
        for c in range(3):
            self.tbl.setItem(r, c, _it(""))

    def _ok(self):
        art = self.in_art.text().strip()
        if "–" in art:  # viene del autocompletado "CÓDIGO – NOMBRE"
            art = art.split("–")[0].strip()
        if not art:
            return
        lineas = []
        for r in range(self.tbl.rowCount()):
            it0 = self.tbl.item(r, 0)
            comp = it0.text().strip() if it0 else ""
            if not comp:
                continue

            def _num(c, d=0.0):
                it = self.tbl.item(r, c)
                try:
                    return float(it.text()) if it and it.text().strip() else d
                except ValueError:
                    return d
            lineas.append({"componente": comp, "cantidad": _num(1, 1), "merma_pct": _num(2, 0)})
        if not lineas:
            return
        try:
            base = float((self.in_base.text() or "0").replace(",", "."))
        except ValueError:
            base = 0.0
        self.resultado = (art, self.in_ver.text().strip() or "1", base, lineas)
        self.accept()


class BOMWindow(QWidget):
    """Listado + ALTA de listas de materiales (BOM) por empresa."""

    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or _usuario_sesion()
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("Listas de materiales (BOM)")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        cab.addWidget(_btn("➕  Nueva BOM", self._nueva, primary=True))
        cab.addWidget(_btn("💲  Fijar coste estándar", self._fijar_coste_estandar))
        cab.addWidget(_btn_cargando("🔄  Actualizar", self._load, primary=True))
        if callback_vuelta:
            cab.addWidget(_btn_x(self._volver))
        root.addLayout(cab)
        self.tbl = _tabla(["ID", "Artículo final", "Versión", "Estado"])
        root.addWidget(self.tbl)
        self._load()

    def _set(self, msg, nivel="info"):
        try:
            from assets.estilo_global import mostrar_mensaje
            mostrar_mensaje(self, "MRP / Producción", msg, nivel=nivel)
        except Exception:
            pass

    def _nueva(self):
        if not _puede(self.usuario, "mrp.bom"):
            self._set("Permiso requerido: mrp.bom", nivel="warning"); return
        dlg = _NuevaBOMDialog(self)
        if dlg.exec() and dlg.resultado:
            art, ver, base, lineas = dlg.resultado
            from src.services.mrp import bom
            bid = bom.crear_bom(art, version=ver, cantidad_base=base, lineas=lineas, id_empresa=_empresa())
            self._set(f"BOM creada: {bid} ({art} v{ver}, {len(lineas)} componentes)"
                      if bid else "No se pudo crear la BOM.", nivel="success" if bid else "error")
            self._load()

    def _fijar_coste_estandar(self):
        if not _puede(self.usuario, "mrp.bom"):
            self._set("Permiso requerido: mrp.bom", nivel="warning"); return
        row = self.tbl.currentRow()
        if row < 0:
            self._set("Selecciona una BOM en la tabla.", nivel="warning"); return
        art = self.tbl.item(row, 1).text()
        from src.services.mrp import costes
        try:
            c = costes.guardar_coste_estandar(art, id_empresa=_empresa())
        except Exception as e:
            self._set(f"No se pudo fijar el coste estándar: {e}", nivel="error"); return
        self._set(f"Coste estándar de «{art}» fijado: materiales {c.get('materiales', 0)} + "
                 f"mano de obra {c.get('mano_obra', 0)} + máquina {c.get('maquina', 0)} + "
                 f"indirecto {c.get('indirecto', 0)} = {c.get('total', 0)}.", nivel="success")

    def _load(self):
        try:
            # Cliente fino (Fase 3): datos desde services/mrp; la GUI solo orquesta.
            from src.services.mrp.bom import listar as listar_bom
            filas = listar_bom(_empresa())
            self.tbl.setRowCount(len(filas))
            for i, r in enumerate(filas):
                r = list(r.values()) if isinstance(r, dict) else r
                for j, v in enumerate(r):
                    self.tbl.setItem(i, j, _it(v))
        except Exception as e:
            logger.error("load BOM: %s", e)


class OrdenesFabricacionWindow(MRPDashboardWindow):
    """Vista centrada en órdenes de fabricación (reutiliza el cuadro de mando operativo)."""


class FabricacionWindow(MRPDashboardWindow):
    """Alias operativo de fabricación (reutiliza el cuadro de mando operativo)."""
