"""
App Store · Plugins y Extensiones — GUI (Fase IV · Bloque 2).

@deprecated: retirada del menú principal del escritorio (decisión de producto informada, tras
confirmar que ninguna capacidad esencial dependía de "instalar" nada desde aquí — pasarelas de pago,
conectores de e-commerce y Canal Web ya son módulos núcleo autónomos con su propia pantalla de
configuración: `_PasarelaConfigDialog` en TPV, `services/tpv/ecommerce/`, Canal Web). Sin llamadores
en `src/gui/` desde ese cambio. Se conserva un ciclo (no se elimina de inmediato, per CLAUDE.md
"Deprecación") por si algo externo aún la referencia; el servicio `src.services.marketplace` sigue
vivo y en uso (Cloud Manager, observabilidad, SDK de plugins), solo esta pantalla queda huérfana.

App Store OFICIAL del ERP: instala y administra PLUGINS, EXTENSIONES y conectores oficiales que
AMPLÍAN las capacidades del sistema. NO es un canal de comercio electrónico ni un canal de venta: los
marketplaces de e-commerce (Amazon/WooCommerce/…) son CANALES de Comercio Digital, no este módulo.
El módulo solo INSTALA/ADMINISTRA; la EJECUCIÓN de los conectores pertenece a los módulos consumidores
(p. ej. Canal Web). (Rearquitectura Comercio Digital · Fase 3.)

Pantalla profesional para navegar el catálogo de plugins: categorías, búsqueda, instalar,
desinstalar, actualizar, ver detalles, dependencias e historial. Consume ÚNICAMENTE el servicio
`src.services.marketplace` (nunca BD directa). Feedback 100% INLINE (sin QMessageBox/QDialog: en
esta app los modales pueden aflorar la corrupción de heap del stack de audio de SOMA — se usa una
etiqueta en la propia pantalla). Aislamiento por empresa (empresa activa).
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QTableWidgetItem, QTabWidget,
                             QVBoxLayout, QWidget)

from src.gui.catalogo_gestion import (_BG, _CIAN, _DIM, _SIDEBAR, _TEXT,
                                      _btn as _btn_base, _btn_cargando as _btn_cargando_base, _btn_x, _combo, _inp, _tabla)
from src.services import marketplace as mk

logger = logging.getLogger("marketplace.gui")


def _btn(txt, slot=None, primary=False, danger=False):
    # Estilo global: los botones secundarios (grises) se muestran turquesa (contorno/texto
    # turquesa, fondo azul oscuro, hover swap), como el resto de la app. Instalar (primary) y
    # Desinstalar (danger) conservan su color propio.
    return _btn_base(txt, slot, primary=(primary or not danger), danger=danger)


def _btn_cargando(txt, slot=None, primary=False, danger=False):
    return _btn_cargando_base(txt, slot, primary=(primary or not danger), danger=danger)


def _it(v):
    return QTableWidgetItem("" if v is None else str(v))


_NIVEL_POR_COLOR = {"#F85149": "error", "#F0A020": "warning", _CIAN: "success"}


def _popup(parent, msg, color=_CIAN):
    """Aviso emergente centrado (mismo diseño que el resto de la app): la etiqueta inline (abajo
    a la izquierda) se conserva como contexto persistente, pero el propio mensaje de éxito/error/
    informativo se muestra siempre con el diálogo propio de `mostrar_mensaje`."""
    try:
        from assets.estilo_global import mostrar_mensaje
        mostrar_mensaje(parent, "App Store", msg, _NIVEL_POR_COLOR.get(color, "info"))
    except Exception:
        pass


class MarketplaceWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.main = main
        self._items = []
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)

        cab = QHBoxLayout()
        t = QLabel("🧩 App Store · Plugins y Extensiones")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        if callback_vuelta:
            cab.addWidget(_btn_x(self._volver))
        root.addLayout(cab)

        # Subtítulo aclaratorio: elimina la ambigüedad con el comercio electrónico (Fase 3).
        sub = QLabel("Instala y administra plugins, extensiones y conectores oficiales que amplían el "
                     "ERP. No es un canal de venta.")
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color:{_DIM};font-size:12px;")
        root.addWidget(sub)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"QTabBar::tab{{background:{_SIDEBAR};color:{_DIM};padding:8px 14px;}}"
                                f"QTabBar::tab:selected{{color:{_CIAN};}}"
                                f"QTabWidget::pane{{border:none;}}")
        page_cat = QWidget(); root_cat = QVBoxLayout(page_cat); root_cat.setContentsMargins(0, 8, 0, 0)
        self.tabs.addTab(page_cat, "Catálogo")
        self.tabs.addTab(self._page_repositorios(), "Repositorios")
        self.tabs.addTab(self._page_licencias(), "Licencias")
        root.addWidget(self.tabs)
        root = root_cat

        # Barra: buscar + categoría + política + refrescar.
        barra = QHBoxLayout()
        self.in_buscar = _inp("🔍 Buscar plugin…"); self.in_buscar.setFixedWidth(220)
        self.in_buscar.textChanged.connect(self._recargar)
        self.in_buscar.returnPressed.connect(self._recargar)
        self.cmb_categoria = _combo([("(todas)", None)])
        self.cmb_categoria.setMinimumWidth(150)   # evita texto cortado en el desplegable
        self.cmb_categoria.currentIndexChanged.connect(self._recargar)
        self.cmb_politica = _combo([(p, p) for p in mk.POLITICAS])
        self.cmb_politica.setMinimumWidth(150)    # evita texto cortado (oficiales/firmados/internos)
        self.cmb_politica.currentIndexChanged.connect(self._cambiar_politica)
        # "Mostrar": el catálogo lista TODOS los plugins disponibles (estén o no instalados) — al
        # desinstalar uno, sigue existiendo como entrada del catálogo (solo cambia su columna
        # "Instalado" a "—"), igual que una tienda de apps no borra la app de la tienda al
        # desinstalarla de tu dispositivo. Por defecto se muestran solo los instalados, así que
        # desinstalar uno lo retira de la vista por defecto sin tocar el catálogo real; "Todos"
        # sigue disponible para volver a instalarlo o descubrir otros.
        self.cmb_mostrar = _combo([("Instalados", "instalados"), ("Todos", "todos")])
        self.cmb_mostrar.setMinimumWidth(130)
        self.cmb_mostrar.currentIndexChanged.connect(self._recargar)
        barra.addWidget(QLabel("Buscar:")); barra.addWidget(self.in_buscar)
        barra.addWidget(_btn("🔍", self._recargar, primary=True))
        barra.addWidget(QLabel("Categoría:")); barra.addWidget(self.cmb_categoria)
        barra.addWidget(QLabel("Mostrar:")); barra.addWidget(self.cmb_mostrar)
        barra.addStretch()
        barra.addWidget(QLabel("Política:")); barra.addWidget(self.cmb_politica)
        barra.addWidget(_btn_cargando("🔄 Actualizar catálogo", self._recargar))
        root.addLayout(barra)

        self.tabla = _tabla(["Plugin", "Versión", "Categoría", "Autor", "Firma", "Instalado"])
        self.tabla.itemSelectionChanged.connect(self._on_sel)
        root.addWidget(self.tabla)

        # Acciones (inline, sin modales).
        acc = QHBoxLayout()
        acc.addWidget(_btn("Instalar", self._instalar, primary=True))
        acc.addWidget(_btn("Reinstalar", self._reinstalar))
        acc.addWidget(_btn("Actualizar", self._actualizar))
        acc.addWidget(_btn("Verificar", self._verificar))
        acc.addWidget(_btn("Historial", self._historial))
        acc.addWidget(_btn("Rollback", self._rollback))
        acc.addStretch()
        acc.addWidget(_btn("Desinstalar", self._desinstalar, danger=True))
        root.addLayout(acc)

        # Detalle del plugin seleccionado: fondo TRANSPARENTE (antes _BG2, que dibujaba una barra gris a
        # todo lo ancho de la ventana incluso vacío). Ahora se integra con el fondo del resto de la vista.
        self.lbl_detalle = QLabel("")
        self.lbl_detalle.setWordWrap(True)
        self.lbl_detalle.setStyleSheet(f"color:{_TEXT};font-size:12px;background:transparent;padding:4px;")
        root.addWidget(self.lbl_detalle)

        self._sincronizar_politica()
        self._cargar_categorias()
        self._recargar()

    # ── Repositorios (services.marketplace.repositorios — sin frontend hasta esta auditoría) ──
    def _page_repositorios(self):
        w = QWidget(); ly = QVBoxLayout(w)
        desc = QLabel("Orígenes de plugins: además del repositorio oficial integrado, registra "
                      "repositorios privados/Git/ZIP/locales adicionales.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color:{_DIM};font-size:12px;")
        ly.addWidget(desc)
        self.tbl_repos = _tabla(["Nombre", "Tipo", "URL", "Prioridad", "Activo"])
        ly.addWidget(self.tbl_repos)
        f = QHBoxLayout()
        self.in_repo_nombre = _inp("Nombre"); self.in_repo_nombre.setFixedWidth(160)
        self.cmb_repo_tipo = _combo([(t, t) for t in mk.repositorios.TIPOS])
        self.cmb_repo_tipo.setMinimumWidth(150)   # evita texto cortado en el desplegable
        self.in_repo_url = _inp("URL / ruta"); self.in_repo_url.setMaximumWidth(260)
        self.in_repo_prioridad = _inp("Prioridad (100)"); self.in_repo_prioridad.setFixedWidth(150)
        f.addWidget(self.in_repo_nombre); f.addWidget(self.cmb_repo_tipo)
        f.addWidget(self.in_repo_url); f.addWidget(self.in_repo_prioridad)
        f.addWidget(_btn("＋ Registrar repositorio", self._registrar_repositorio, primary=True))
        ly.addLayout(f)
        self._cargar_repositorios()
        return w

    def _cargar_repositorios(self):
        repos = mk.repositorios.listar_repositorios(self._id_empresa())
        self.tbl_repos.setRowCount(len(repos))
        for i, r in enumerate(repos):
            fila = [r.get("nombre"), r.get("tipo"), r.get("url"), r.get("prioridad"),
                    "Sí" if r.get("activo") else "—"]
            for j, v in enumerate(fila):
                self.tbl_repos.setItem(i, j, _it(v))

    def _feedback_repos(self, msg, color=_CIAN):
        _popup(self, msg, color)

    def _registrar_repositorio(self):
        nombre = self.in_repo_nombre.text().strip()
        if not nombre:
            self._feedback_repos("Indica un nombre de repositorio.", "#F0A020")
            return
        try:
            prioridad = int(self.in_repo_prioridad.text().strip() or 100)
        except ValueError:
            prioridad = 100
        ok = mk.repositorios.registrar_repositorio(
            nombre, self.cmb_repo_tipo.currentData(), url=self.in_repo_url.text().strip() or None,
            id_empresa=self._id_empresa(), prioridad=prioridad)
        if ok:
            self._feedback_repos(f"✅ Repositorio «{nombre}» registrado.", _CIAN)
            self.in_repo_nombre.clear(); self.in_repo_url.clear(); self.in_repo_prioridad.clear()
            self._cargar_repositorios()
        else:
            self._feedback_repos("⚠️ No se pudo registrar el repositorio.", "#F0A020")

    # ── Licencias (services.marketplace.licencias — sin frontend hasta esta auditoría) ──
    def _page_licencias(self):
        w = QWidget(); ly = QVBoxLayout(w)
        desc = QLabel("Licencias por plugin: empresa/tienda/usuario/temporal/enterprise. Sin cobro — "
                      "solo arquitectura de licenciamiento; gate opcional de instalación/uso.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color:{_DIM};font-size:12px;")
        ly.addWidget(desc)
        self.tbl_licencias = _tabla(["Plugin", "Tipo", "Alcance", "Válido hasta", "Estado"])
        ly.addWidget(self.tbl_licencias)
        f = QHBoxLayout()
        self.in_lic_clave = _inp("Clave del plugin"); self.in_lic_clave.setFixedWidth(160)
        self.cmb_lic_tipo = _combo([(t, t) for t in mk.licencias.TIPOS])
        self.in_lic_alcance = _inp("Alcance (id tienda/usuario, opcional)")
        self.in_lic_hasta = _inp("Válido hasta AAAA-MM-DD (opcional)")
        f.addWidget(self.in_lic_clave); f.addWidget(self.cmb_lic_tipo)
        f.addWidget(self.in_lic_alcance); f.addWidget(self.in_lic_hasta)
        ly.addLayout(f)
        b = QHBoxLayout()
        b.addWidget(_btn("Conceder licencia", self._conceder_licencia, primary=True))
        b.addWidget(_btn("Revocar licencia", self._revocar_licencia, danger=True))
        b.addStretch()
        ly.addLayout(b)
        self._licencias_data = []
        self._cargar_licencias()
        return w

    def _cargar_licencias(self):
        self._licencias_data = mk.licencias.listar(self._id_empresa())
        self.tbl_licencias.setRowCount(len(self._licencias_data))
        for i, lic in enumerate(self._licencias_data):
            fila = [lic.get("clave_plugin"), lic.get("tipo"), lic.get("alcance_id") or "—",
                    lic.get("valido_hasta") or "—", lic.get("estado")]
            for j, v in enumerate(fila):
                self.tbl_licencias.setItem(i, j, _it(v))

    def _feedback_lic(self, msg, color=_CIAN):
        _popup(self, msg, color)

    def _conceder_licencia(self):
        clave = self.in_lic_clave.text().strip()
        if not clave:
            self._feedback_lic("Indica la clave del plugin.", "#F0A020")
            return
        ok = mk.licencias.conceder(
            clave, id_empresa=self._id_empresa(), tipo=self.cmb_lic_tipo.currentData(),
            alcance_id=self.in_lic_alcance.text().strip() or None,
            valido_hasta=self.in_lic_hasta.text().strip() or None)
        if ok:
            self._feedback_lic(f"✅ Licencia de «{clave}» concedida.", _CIAN)
            self.in_lic_clave.clear(); self.in_lic_alcance.clear(); self.in_lic_hasta.clear()
            self._cargar_licencias()
        else:
            self._feedback_lic("⚠️ No se pudo conceder la licencia.", "#F0A020")

    def _revocar_licencia(self):
        fila = self.tbl_licencias.currentRow()
        if fila < 0 or fila >= len(self._licencias_data):
            self._feedback_lic("Selecciona una licencia en la tabla.", "#F0A020")
            return
        lic = self._licencias_data[fila]
        ok = mk.licencias.revocar(lic["clave_plugin"], id_empresa=self._id_empresa())
        if ok:
            self._feedback_lic(f"🗑 Licencia de «{lic['clave_plugin']}» revocada.", _CIAN)
            self._cargar_licencias()
        else:
            self._feedback_lic("⚠️ No se pudo revocar la licencia.", "#F0A020")

    # ── helpers ────────────────────────────────────────────────────────────────
    def _id_empresa(self):
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return None

    def _usuario(self):
        return (self.usuario or {}).get("nombre")

    def _feedback(self, msg, color=_CIAN):
        _popup(self, msg, color)

    def _clave_sel(self):
        fila = self.tabla.currentRow()
        if fila < 0 or fila >= len(self._items):
            return None
        return self._items[fila].get("clave")

    def _sincronizar_politica(self):
        pol = mk.politica(self._id_empresa())
        i = self.cmb_politica.findData(pol)
        if i >= 0:
            self.cmb_politica.blockSignals(True); self.cmb_politica.setCurrentIndex(i)
            self.cmb_politica.blockSignals(False)

    def _cargar_categorias(self):
        self.cmb_categoria.blockSignals(True)
        self.cmb_categoria.clear(); self.cmb_categoria.addItem("(todas)", None)
        for c in mk.categorias(self._id_empresa()):
            self.cmb_categoria.addItem(c, c)
        self.cmb_categoria.blockSignals(False)

    # ── datos ────────────────────────────────────────────────────────────────
    def _recargar(self, *_):
        emp = self._id_empresa()
        items = mk.catalogo(emp, categoria=self.cmb_categoria.currentData(),
                            texto=self.in_buscar.text().strip())
        if self.cmb_mostrar.currentData() == "instalados":
            items = [it for it in items if it.get("instalado")]
        self._items = items
        self.tabla.setRowCount(len(self._items))
        for i, it in enumerate(self._items):
            fila = [it.get("clave"), it.get("version"), it.get("categoria"), it.get("autor"),
                    it.get("firma"), "Sí" if it.get("instalado") else "—"]
            for j, v in enumerate(fila):
                self.tabla.setItem(i, j, _it(v))

    def _on_sel(self):
        it = None
        fila = self.tabla.currentRow()
        if 0 <= fila < len(self._items):
            it = self._items[fila]
        if not it:
            self.lbl_detalle.setText(""); return
        det = mk.detalle(it["clave"], self._id_empresa()) or it
        deps = ", ".join(det.get("dependencias") or []) or "ninguna"
        self.lbl_detalle.setText(
            f"<b>{det.get('nombre')}</b> v{det.get('version')} · {det.get('categoria')} · "
            f"autor: {det.get('autor') or '—'}<br>{det.get('descripcion') or ''}<br>"
            f"Firma: {det.get('firma')} · Licencia: {det.get('licencia') or '—'} · "
            f"Dependencias: {deps} · Repo: {det.get('repo')}")

    # ── acciones (inline) ──────────────────────────────────────────────────────
    def _cambiar_politica(self):
        pol = self.cmb_politica.currentData()
        if mk.fijar_politica(pol, id_empresa=self._id_empresa()):
            self._feedback(f"Política del marketplace fijada a «{pol}».")
        self._recargar()

    def _accion(self, fn, ok_msg):
        clave = self._clave_sel()
        if not clave:
            self._feedback("Selecciona un plugin en la lista.", "#F0A020"); return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            res = fn(clave)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self._feedback(f"❌ Error: {e}", "#F85149"); return
        QApplication.restoreOverrideCursor()
        if isinstance(res, dict) and res.get("ok"):
            self._feedback(ok_msg(res), _CIAN)
            self._cargar_categorias(); self._recargar()
        else:
            err = (res or {}).get("errores") if isinstance(res, dict) else None
            self._feedback(f"⚠️ No se pudo completar: {err or res}", "#F0A020")

    def _instalar(self):
        self._accion(lambda c: mk.instalar(c, id_empresa=self._id_empresa(), usuario=self._usuario()),
                     lambda r: f"✅ Instalado «{r['clave']}» ({', '.join(r.get('instalados', []))}).")

    def _reinstalar(self):
        self._accion(lambda c: mk.reinstalar(c, id_empresa=self._id_empresa(), usuario=self._usuario()),
                     lambda r: f"✅ Reinstalado «{r['clave']}».")

    def _desinstalar(self):
        self._accion(lambda c: mk.desinstalar(c, id_empresa=self._id_empresa(), usuario=self._usuario()),
                     lambda r: f"🗑 Desinstalado «{r['clave']}».")

    def _actualizar(self):
        self._accion(lambda c: mk.actualizar(c, id_empresa=self._id_empresa(), usuario=self._usuario()),
                     lambda r: f"⬆ Actualizado «{r['clave']}» {r.get('desde')}→{r.get('hasta')}.")

    def _rollback(self):
        self._accion(lambda c: mk.rollback(c, id_empresa=self._id_empresa(), usuario=self._usuario()),
                     lambda r: f"↩ Rollback de «{r['clave']}» a v{r.get('version')}.")

    def _verificar(self):
        clave = self._clave_sel()
        if not clave:
            self._feedback("Selecciona un plugin.", "#F0A020"); return
        try:
            r = mk.verificar_integridad(clave, id_empresa=self._id_empresa())
        except Exception as e:
            self._feedback(f"❌ Error al verificar: {e}", "#F85149"); return
        ok = r.get("ok")
        self._feedback(f"{'✅' if ok else '⚠️'} Integridad de «{clave}»: firma={r.get('firma')} · "
                       f"hash instalado={str(r.get('hash_instalado'))[:12]}…",
                       _CIAN if ok else "#F0A020")

    def _historial(self):
        clave = self._clave_sel()
        if not clave:
            self._feedback("Selecciona un plugin.", "#F0A020"); return
        try:
            hist = mk.historial(clave, self._id_empresa())
        except Exception as e:
            self._feedback(f"❌ Error al obtener el historial: {e}", "#F85149"); return
        if not hist:
            self._feedback(f"Sin historial para «{clave}».", _DIM); return
        lineas = " · ".join(f"{h.get('accion')} v{h.get('version') or '?'}" for h in hist[:8])
        self._feedback(f"Historial de «{clave}»: {lineas}", _TEXT)
