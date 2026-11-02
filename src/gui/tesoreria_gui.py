"""
Tesorería — interfaz unificada (rama Tesorería, FASE 12).

Pantalla NUEVA (no modifica las existentes) con 8 paneles en pestañas, coherentes con el
estilo del ERP (dark + cian): Posición, Cuentas, Movimientos, Vencimientos, Conciliación,
Remesas SEPA, Cash Flow y Previsión. Siempre acotada a la empresa activa. Reutiliza los
servicios de las FASES 1-11. Las consultas son best-effort: un fallo de datos no rompe la UI.
"""

import datetime as _dt
import logging

from PyQt6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel,
                             QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from src.db import tesoreria as _T
from src.db import vencimientos as _V
from src.db import sepa as _S
from src.gui.catalogo_gestion import (_BG, _CIAN, _DIM, _btn, _btn_cargando, _btn_x, _combo,
                                      _dialogo_frameless, _inp, _lbl, _tabla)
from src.gui.foundation import tokens as T
from src.services.tesoreria import cashflow as _CF
from src.services.tesoreria import conciliacion as _CC
from src.services.tesoreria import posicion as _POS
from src.services.tesoreria import prevision_financiera as _PF
from src.services.tesoreria import sepa as _SEPA

logger = logging.getLogger("tesoreria.gui")


def _it(v):
    return QTableWidgetItem("" if v is None else str(v))


# `QMessageBox`/`QInputDialog` nativos se sustituyen por el patrón propio de la app: sobre la
# ventana anfitriona FRAMELESS de todo Smart Manager pueden quedar sin handle correcto (barra de
# Windows visible, botones sin texto legible, sin esquinas redondeadas) — mismo criterio ya
# aplicado en `rrhh_gestion.py`/`catalogo_gestion._InfoDialog`.
def _info_msg(parent, titulo, mensaje):
    try:
        from assets.estilo_global import mostrar_mensaje
        mostrar_mensaje(parent, titulo, mensaje, "info")
    except Exception:
        logger.info("%s: %s", titulo, mensaje)


def _error_msg(parent, titulo, mensaje):
    try:
        from assets.estilo_global import mostrar_mensaje
        mostrar_mensaje(parent, titulo, mensaje, "error")
    except Exception:
        logger.warning("%s: %s", titulo, mensaje)


class _PedirTextoDialog(QDialog):
    """Reemplazo de `QInputDialog.getText` (sin barra de Windows, esquinas redondeadas, botones
    con texto visible), usando el mismo `_dialogo_frameless` que el resto de diálogos del módulo."""

    def __init__(self, titulo, prompt, texto="", parent=None):
        super().__init__(parent)
        v = _dialogo_frameless(self, titulo, ancho=380)
        v.addWidget(_lbl(prompt, dim=False))
        from PyQt6.QtWidgets import QLineEdit
        self.inp = QLineEdit(texto); self.inp.setFixedHeight(36)
        self.inp.setStyleSheet(f"QLineEdit{{background:{_BG};color:{_CIAN};border:2px solid {_CIAN};"
                               "border-radius:8px;padding:0 10px;}")
        self.inp.returnPressed.connect(self.accept)
        v.addWidget(self.inp)
        fila = QHBoxLayout(); fila.addStretch()
        fila.addWidget(_btn("Aceptar", self.accept, primary=True))
        v.addLayout(fila)
        self.inp.setFocus()

    def valor(self):
        return self.inp.text()


def _pedir_texto(parent, titulo, prompt, texto=""):
    d = _PedirTextoDialog(titulo, prompt, texto, parent)
    ok = d.exec() == QDialog.DialogCode.Accepted
    return d.valor(), ok


class _PedirOpcionDialog(QDialog):
    """Reemplazo de `QInputDialog.getItem` con el mismo estilo (sin barra de Windows)."""

    def __init__(self, titulo, prompt, opciones, parent=None):
        super().__init__(parent)
        v = _dialogo_frameless(self, titulo, ancho=420)
        v.addWidget(_lbl(prompt, dim=False))
        self.cmb = _combo([(o, o) for o in opciones])
        v.addWidget(self.cmb)
        fila = QHBoxLayout(); fila.addStretch()
        fila.addWidget(_btn("Aceptar", self.accept, primary=True))
        v.addLayout(fila)

    def valor(self):
        return self.cmb.currentText()


def _pedir_opcion(parent, titulo, prompt, opciones):
    d = _PedirOpcionDialog(titulo, prompt, opciones, parent)
    ok = d.exec() == QDialog.DialogCode.Accepted
    return d.valor(), ok


def _empresa():
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return EMPRESA_DEFAULT_ID


class _ImportarExtractoDialog(QDialog):
    """Selecciona un fichero de extracto bancario (CSV/N43/CAMT.053) + formato + cuenta opcional.
    `contenido`/`formato`/`id_cuenta` quedan listos para `conciliacion.importar_extracto` tras
    aceptar. Sin este diálogo la pestaña Conciliación era inutilizable: no había forma de crear
    un extracto nuevo, solo de teclear a mano el ID de uno ya existente (huella crítica de la
    auditoría app-wide)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.contenido = None
        self.ruta = None
        v = _dialogo_frameless(self, "Importar extracto bancario", ancho=420)
        v.addWidget(_lbl("Fichero"))
        fila = QHBoxLayout()
        self.lbl_ruta = QLabel("(ningún fichero seleccionado)")
        self.lbl_ruta.setStyleSheet(f"color:{_DIM};")
        self.lbl_ruta.setWordWrap(True)
        fila.addWidget(self.lbl_ruta, 1)
        fila.addWidget(_btn("Elegir…", self._elegir, primary=True))
        v.addLayout(fila)
        v.addWidget(_lbl("Formato"))
        self.cmb_formato = _combo([("CSV", "CSV"), ("N43 (Cuaderno 43)", "N43"), ("CAMT.053 (XML)", "CAMT")])
        v.addWidget(self.cmb_formato)
        v.addWidget(_lbl("ID de cuenta (opcional)"))
        self.in_cuenta = _inp("ID de cuenta bancaria")
        v.addWidget(self.in_cuenta)
        fila2 = QHBoxLayout(); fila2.addStretch()
        self.btn_ok = _btn("Importar", self._ok, primary=True)
        self.btn_ok.setEnabled(False)
        fila2.addWidget(self.btn_ok)
        v.addLayout(fila2)

    def _elegir(self):
        ruta, _f = QFileDialog.getOpenFileName(
            self, "Seleccionar extracto bancario", "",
            "Extractos (*.csv *.txt *.n43 *.xml);;Todos los ficheros (*)")
        if not ruta:
            return
        self.ruta = ruta
        self.lbl_ruta.setText(ruta)
        self.lbl_ruta.setStyleSheet(f"color:{_CIAN};")
        self.btn_ok.setEnabled(True)
        ext = ruta.rsplit(".", 1)[-1].lower() if "." in ruta else ""
        if ext == "xml":
            self.cmb_formato.setCurrentIndex(self.cmb_formato.findData("CAMT"))
        elif ext in ("n43", "txt"):
            self.cmb_formato.setCurrentIndex(self.cmb_formato.findData("N43"))
        else:
            self.cmb_formato.setCurrentIndex(self.cmb_formato.findData("CSV"))

    def _ok(self):
        if not self.ruta:
            return
        try:
            with open(self.ruta, encoding="utf-8-sig", errors="replace") as f:
                self.contenido = f.read()
        except OSError as e:
            _error_msg(self, "Importar extracto", f"No se pudo leer el fichero: {e}")
            return
        self.formato = self.cmb_formato.currentData()
        cta = self.in_cuenta.text().strip()
        try:
            self.id_cuenta = int(cta) if cta else None
        except ValueError:
            self.id_cuenta = None
        self.accept()


class TesoreriaWindow(QWidget):
    # Badges por pestaña (Centro de Actividad, fina granularidad): subtab (mapeo.TIPO_A_SUBTAB,
    # por ahora solo "cobros" ← COBRO_REGISTRADO) → índice REAL de pestaña (orden de `addTab` en
    # __init__: posicion=0, cuentas=1, movimientos=2, vencimientos=3, recordatorios=4, ...).
    _SUBTAB_A_INDICE = {"cobros": 4}   # "cobros" → _tab_recordatorios ("Recordatorios de cobro")

    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)

        cab = QHBoxLayout()
        t = QLabel("Tesorería · Bancos · SEPA")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        # (El botón Actualizar de la cabecera se retira: cada pestaña tiene su propio Actualizar
        #  en la esquina superior derecha de su tabla.)
        if callback_vuelta:
            cab.addWidget(_btn_x(self._volver))
        root.addLayout(cab)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(T.qss_tabs())   # mismo diseño de pestañas que el Centro de Inteligencia
        root.addWidget(self.tabs)

        self._tab_posicion()
        self._tab_cuentas()
        self._tab_movimientos()
        self._tab_vencimientos()
        self._tab_recordatorios()
        self._tab_conciliacion()
        self._tab_banca()
        self._tab_remesas()
        self._tab_cashflow()
        self._tab_prevision()
        self._tab_finanzas_avanzadas()   # dominio financiero: Finanzas Avanzadas (dashboard embebido)

        # Reglas de acceso (Seguridad · Pestañas): con acceso completo al módulo, todas visibles
        # por defecto (una regla puntual aún puede DENEGAR una en concreto); sin acceso completo
        # (entró solo por una concesión de pestaña suelta), ninguna se ve por defecto — solo la(s)
        # concedida(s). El orden de esta lista es el orden real de `addTab` de las llamadas arriba.
        from src.services.seguridad import pestanas_app
        _tiene_completo = pestanas_app.tiene_modulo_completo("tesoreria", self.usuario, False)
        _slugs = ["posicion", "cuentas", "movimientos", "vencimientos", "recordatorios",
                 "conciliacion", "banca", "remesas", "cashflow", "prevision", "finanzas_avanzadas"]
        for _i, _slug in enumerate(_slugs):
            if not pestanas_app.visible(f"tesoreria.{_slug}", self.usuario, _tiene_completo):
                self.tabs.setTabVisible(_i, False)

        # Badges de actividad por pestaña (círculo rojo + nº blanco) — mismo mecanismo reutilizable
        # que `menu_principal.py` usa para las tarjetas del menú (Centro de Actividad, Fase 3), ahora
        # a nivel de pestaña vía `tab_badges.instalar_badges` + `services.actividad.badges`. Refresco
        # inicial diferido + periódico cada 60s (mismo patrón que `menu_principal._timer_badges`).
        from PyQt6.QtCore import QTimer as _QTimer
        from src.gui.foundation.tab_badges import instalar_badges
        self._gestor_badges = instalar_badges(self.tabs, self._contar_badges_pestanas,
                                              self._al_entrar_pestana_badge)
        self._timer_badges = _QTimer(self)
        self._timer_badges.timeout.connect(self._refrescar_badges_pestanas)
        self._timer_badges.start(60000)

    def _contar_badges_pestanas(self):
        """{índice_pestaña: nº} para `GestorBadgesPestanas` — traduce los subtabs devueltos por
        `actividad.badges.contar_subtabs('tesoreria', ...)` a índices reales vía `_SUBTAB_A_INDICE`.
        Best-effort: ante cualquier fallo, sin badges (nunca rompe la ventana)."""
        try:
            from src.services.actividad import badges as actividad_badges
            counts = actividad_badges.contar_subtabs("tesoreria", usuario=self.usuario,
                                                      id_empresa=_empresa())
        except Exception:
            logger.debug("contar_badges_pestanas: fallo best-effort", exc_info=True)
            counts = {}
        out = {}
        for slug, idx in self._SUBTAB_A_INDICE.items():
            n = counts.get(slug, 0)
            if n:
                out[idx] = n
        return out

    def _al_entrar_pestana_badge(self, indice):
        """Al cambiar a una pestaña con subtab mapeado, marca ese subtab como visto (watermark del
        usuario) y repinta los badges."""
        slug = next((s for s, i in self._SUBTAB_A_INDICE.items() if i == indice), None)
        if slug:
            try:
                from src.services.actividad import badges as actividad_badges
                actividad_badges.marcar_visto(f"tesoreria.{slug}", usuario=self.usuario,
                                              id_empresa=_empresa())
            except Exception:
                logger.debug("marcar_visto(tesoreria.%s): fallo best-effort", slug, exc_info=True)
        if getattr(self, "_gestor_badges", None):
            self._gestor_badges.refrescar()

    def _refrescar_badges_pestanas(self):
        if getattr(self, "_gestor_badges", None):
            self._gestor_badges.refrescar()

    def _tab_finanzas_avanzadas(self):
        """Integra el Dashboard de Finanzas Avanzadas (ratios/financiación/crédito/IA) como pestaña
        del dominio financiero, reutilizando la ventana existente sin duplicarla."""
        try:
            from src.gui.finanzas_dashboard import FinanzasDashboardWindow
            w = FinanzasDashboardWindow(callback_vuelta=None, usuario=self.usuario)
            self.tabs.addTab(w, "Finanzas Avanzadas")
        except Exception as e:
            logger.debug("tab finanzas avanzadas: %s", e)

    def showEvent(self, e):
        # Garantiza que la ventana se abre maximizada (a pantalla completa) en el primer mostrado.
        # Se reintenta con varios retardos para vencer una posible carrera con el gestor de ventanas
        # (mismo patrón que otras rutinas diferidas de la app).
        super().showEvent(e)
        if not getattr(self, "_max_once", False):
            self._max_once = True
            from PyQt6.QtCore import QTimer
            for _d in (0, 80, 250, 500):
                QTimer.singleShot(_d, self._forzar_maximizar)

    def _forzar_maximizar(self):
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QApplication
        try:
            self.setWindowState(Qt.WindowState.WindowMaximized)
            self.showMaximized()
            # El flag isMaximized() puede DESINCRONIZARSE del gestor de ventanas (Qt cree que está
            # maximizada pero se ve como ventana normal). Por eso comprobamos el TAMAÑO REAL: si no
            # cubre casi toda la pantalla, forzamos la geometría a la pantalla completa disponible.
            scr = self.screen() or QApplication.primaryScreen()
            if scr is not None:
                avail = scr.availableGeometry()
                if self.width() < avail.width() - 40 or self.height() < avail.height() - 40:
                    self.setGeometry(avail)
        except Exception:
            pass

    def _btn_actualizar(self, loader):
        """Botón Actualizar (emoji) para la esquina superior derecha de la tabla de una pestaña."""
        return _btn_cargando("🔄 Actualizar", loader, primary=True)

    # ── Posición ──────────────────────────────────────────────────────────────
    def _tab_posicion(self):
        w = QWidget(); w.setStyleSheet(f"background:{_BG};"); lay = QVBoxLayout(w)
        top = QHBoxLayout()
        self.lbl_pos = QLabel(""); self.lbl_pos.setStyleSheet(f"color:{_CIAN};font-size:15px;")
        top.addWidget(self.lbl_pos); top.addStretch(1)
        top.addWidget(self._btn_actualizar(self._load_posicion))
        lay.addLayout(top)
        self.tbl_pos = _tabla(["Cuenta", "Tienda", "Moneda", "Saldo"])
        lay.addWidget(self.tbl_pos)
        self.tabs.addTab(w, "Posición")
        self._load_posicion()

    def _load_posicion(self):
        try:
            p = _POS.posicion(_empresa(), horizonte_dias=90)
            self.lbl_pos.setText(
                f"Disponible: {p['disponible']:.2f} €   |   Por cobrar: {p['por_cobrar']:.2f} €   "
                f"|   Comprometido: {p['comprometido']:.2f} €   |   Previsto: {p['previsto']:.2f} €   "
                f"|   Futuro 90d: {p.get('futuro', 0):.2f} €")
            cuentas = p.get("por_cuenta", [])
            self.tbl_pos.setRowCount(len(cuentas))
            for i, c in enumerate(cuentas):
                for j, v in enumerate([c["nombre_cuenta"], c.get("id_tienda"), c.get("moneda"),
                                       f"{c['saldo']:.2f}"]):
                    self.tbl_pos.setItem(i, j, _it(v))
        except Exception as e:
            logger.error("posicion: %s", e)

    # ── Cuentas ───────────────────────────────────────────────────────────────
    def _tab_cuentas(self):
        w = QWidget(); w.setStyleSheet(f"background:{_BG};"); lay = QVBoxLayout(w)
        bar = QHBoxLayout()
        bar.addWidget(_btn("Nueva cuenta", self._nueva_cuenta, primary=True))
        bar.addStretch(); bar.addWidget(self._btn_actualizar(self._load_cuentas)); lay.addLayout(bar)
        self.tbl_cuentas = _tabla(["ID", "Cuenta", "Titular", "IBAN", "BIC", "Entidad", "Moneda", "Saldo"])
        lay.addWidget(self.tbl_cuentas)
        self.tabs.addTab(w, "Cuentas")
        self._load_cuentas()

    def _load_cuentas(self):
        try:
            filas = _T.listar_cuentas(id_empresa=_empresa())
            self.tbl_cuentas.setRowCount(len(filas))
            for i, c in enumerate(filas):
                vals = [c["id"], c["nombre_cuenta"], c.get("titular"), c.get("iban"),
                        c.get("bic"), c.get("entidad"), c.get("moneda"),
                        f"{_T.saldo_cuenta(c['id'], _empresa()):.2f}"]
                for j, v in enumerate(vals):
                    self.tbl_cuentas.setItem(i, j, _it(v))
        except Exception as e:
            logger.error("cuentas: %s", e)

    def _nueva_cuenta(self):
        nombre, ok = _pedir_texto(self, "Nueva cuenta", "Nombre de la cuenta:")
        if not ok or not nombre:
            return
        iban, ok = _pedir_texto(self, "Nueva cuenta", "IBAN:")
        if not ok:
            return
        try:
            _T.crear_cuenta(nombre, iban, usuario=self.usuario.get("nombre"), id_empresa=_empresa())
            self._load_cuentas(); self._load_posicion()
            _info_msg(self, "Cuentas", f"Cuenta «{nombre}» creada correctamente.")
        except Exception as e:
            _error_msg(self, "Error", str(e))

    # ── Movimientos ───────────────────────────────────────────────────────────
    def _tab_movimientos(self):
        w = QWidget(); w.setStyleSheet(f"background:{_BG};"); lay = QVBoxLayout(w)
        top = QHBoxLayout(); top.addStretch(1); top.addWidget(self._btn_actualizar(self._load_movimientos))
        lay.addLayout(top)
        self.tbl_mov = _tabla(["Fecha", "Tipo", "Concepto", "Importe", "Saldo", "Origen", "Doc."])
        lay.addWidget(self.tbl_mov)
        self.tabs.addTab(w, "Movimientos")
        self._load_movimientos()

    def _load_movimientos(self):
        try:
            filas = _T.listar_movimientos(id_empresa=_empresa(), limite=500)
            self.tbl_mov.setRowCount(len(filas))
            for i, m in enumerate(filas):
                vals = [m["fecha"], m["tipo"], m.get("concepto"), f"{float(m['importe']):.2f}",
                        ("" if m.get("saldo_resultante") is None else f"{float(m['saldo_resultante']):.2f}"),
                        m.get("origen"), m.get("id_documento")]
                for j, v in enumerate(vals):
                    self.tbl_mov.setItem(i, j, _it(v))
        except Exception as e:
            logger.error("movimientos: %s", e)

    # ── Vencimientos ──────────────────────────────────────────────────────────
    def _tab_vencimientos(self):
        w = QWidget(); w.setStyleSheet(f"background:{_BG};"); lay = QVBoxLayout(w)
        bar = QHBoxLayout()
        bar.addWidget(_btn("Marcar vencidos", self._marcar_vencidos, primary=True))
        bar.addWidget(_btn("Anular", self._anular_vencimiento, danger=True))
        bar.addStretch(); bar.addWidget(self._btn_actualizar(self._load_vencimientos)); lay.addLayout(bar)
        self.tbl_venc = _tabla(["ID", "Tipo", "Vence", "Importe", "Pendiente", "Estado", "Tercero", "Origen"])
        lay.addWidget(self.tbl_venc)
        self.tabs.addTab(w, "Vencimientos")
        self._load_vencimientos()

    def _load_vencimientos(self):
        try:
            filas = _V.listar_vencimientos(id_empresa=_empresa())
            self.tbl_venc.setRowCount(len(filas))
            for i, v in enumerate(filas):
                vals = [v["id"], v["tipo"], v["fecha_vencimiento"], f"{float(v['importe']):.2f}",
                        f"{float(v['pendiente']):.2f}", v["estado"], v.get("tercero"), v.get("origen")]
                for j, val in enumerate(vals):
                    self.tbl_venc.setItem(i, j, _it(val))
        except Exception as e:
            logger.error("vencimientos: %s", e)

    def _marcar_vencidos(self):
        try:
            n = _V.marcar_vencidos(_empresa())
            _info_msg(self, "Vencimientos", f"{n} vencimiento(s) marcados como VENCIDO.")
            self._load_vencimientos()
        except Exception as e:
            _error_msg(self, "Error", str(e))

    def _anular_vencimiento(self):
        r = self.tbl_venc.currentRow()
        if r < 0 or self.tbl_venc.item(r, 0) is None:
            _info_msg(self, "Vencimientos", "Selecciona antes un vencimiento en la tabla.")
            return
        try:
            id_venc = int(self.tbl_venc.item(r, 0).text())
        except (TypeError, ValueError):
            return
        try:
            from assets.estilo_global import mostrar_confirmacion
            ok_conf = mostrar_confirmacion(self, "Anular vencimiento",
                                           f"¿Anular el vencimiento #{id_venc}? Esta acción no revierte "
                                           "cobros/pagos ya registrados, solo marca el vencimiento como "
                                           "ANULADO.")
        except Exception:
            ok_conf = True
        if not ok_conf:
            return
        nombre = self.usuario.get("nombre") if isinstance(self.usuario, dict) else None
        if _V.anular_vencimiento(id_venc, usuario=nombre, id_empresa=_empresa()):
            _info_msg(self, "Vencimientos", f"Vencimiento #{id_venc} anulado.")
            self._load_vencimientos()
        else:
            _error_msg(self, "Vencimientos", "No se pudo anular el vencimiento.")

    # ── Recordatorios de cobro (dunning) ──────────────────────────────────────
    def _tab_recordatorios(self):
        w = QWidget(); w.setStyleSheet(f"background:{_BG};"); lay = QVBoxLayout(w)
        bar = QHBoxLayout()
        bar.addWidget(_btn("👁 Previsualizar", self._prev_recordatorios, primary=True))
        bar.addWidget(_btn("Enviar recordatorios ahora", self._enviar_recordatorios, primary=True))
        bar.addStretch(); bar.addWidget(self._btn_actualizar(self._load_recordatorios)); lay.addLayout(bar)
        self.tbl_rec = _tabla(["Factura", "Cliente", "Vence", "Pendiente", "Días", "Nivel a enviar",
                               "Últ. nivel"])
        lay.addWidget(self.tbl_rec)
        self.tabs.addTab(w, "Recordatorios de cobro")
        self._load_recordatorios()

    def _load_recordatorios(self):
        try:
            from src.services.facturacion import recordatorios as REC
            filas = REC.resumen(_empresa())
            self.tbl_rec.setRowCount(len(filas))
            for i, f in enumerate(filas):
                nivel = f["nivel_actual"] if f["pendiente_envio"] else "—"
                ult = f["ultimo_nivel"] if f["ultimo_nivel"] >= 0 else "—"
                vals = [f["ref"], f["cliente"], f["vence"], f"{f['pendiente']:.2f}", f["dias"], nivel, ult]
                for j, v in enumerate(vals):
                    self.tbl_rec.setItem(i, j, _it(v))
        except Exception as e:
            logger.error("recordatorios: %s", e)

    def _prev_recordatorios(self):
        try:
            from src.services.facturacion import recordatorios as REC
            r = REC.procesar(_empresa(), enviar=False)
            _info_msg(self, "Previsualización de recordatorios",
                                    f"Se enviarían {r['enviados']} recordatorio(s) de {r['evaluadas']} "
                                    f"factura(s) pendientes de cobro.")
        except Exception as e:
            _error_msg(self, "Error", str(e))

    def _enviar_recordatorios(self):
        try:
            from src.services.facturacion import recordatorios as REC
            r = REC.procesar(_empresa())
            _info_msg(self, "Recordatorios de cobro",
                                    f"Enviados: {r['enviados']}   ·   Evaluadas: {r['evaluadas']}   ·   "
                                    f"Errores: {r['errores']}")
            self._load_recordatorios()
        except Exception as e:
            _error_msg(self, "Error", str(e))

    # ── Banca online (open banking / PSD2) ────────────────────────────────────
    def _tab_banca(self):
        w = QWidget(); w.setStyleSheet(f"background:{_BG};"); lay = QVBoxLayout(w)
        bar = QHBoxLayout()
        self.cmb_banca = _combo([]); self.cmb_banca.setMinimumWidth(240)
        self.cmb_banca.currentIndexChanged.connect(self._banca_estado)
        bar.addWidget(QLabel("Cuenta:")); bar.addWidget(self.cmb_banca)
        bar.addWidget(_btn("⚙ Configurar conexión", self._banca_config, primary=True))
        bar.addWidget(_btn("🔄 Sincronizar banco", self._banca_sync, primary=True))
        bar.addStretch(); lay.addLayout(bar)
        self.lbl_banca = QLabel(""); self.lbl_banca.setStyleSheet(f"color:{_DIM};font-weight:bold;")
        lay.addWidget(self.lbl_banca)
        ayuda = QLabel("La conexión descarga los movimientos reales del banco y los concilia "
                       "automáticamente con las facturas/movimientos. Sin credenciales de un agregador "
                       "PSD2 opera en modo simulado (no descarga nada).")
        ayuda.setWordWrap(True); ayuda.setStyleSheet(f"color:{_DIM};")
        lay.addWidget(ayuda); lay.addStretch()
        self.tabs.addTab(w, "Banca en línea")
        self._banca_cargar_cuentas()

    def _banca_cargar_cuentas(self):
        self.cmb_banca.blockSignals(True); self.cmb_banca.clear()
        for c in _T.listar_cuentas(id_empresa=_empresa()):
            et = c.get("nombre") or c.get("alias") or c.get("iban") or f"Cuenta {c['id']}"
            self.cmb_banca.addItem(str(et), c["id"])
        self.cmb_banca.blockSignals(False)
        self._banca_estado()

    def _banca_cuenta(self):
        return self.cmb_banca.currentData()

    def _banca_estado(self):
        cta = self._banca_cuenta()
        if not cta:
            self.lbl_banca.setText("No hay cuentas bancarias. Crea una en la pestaña «Cuentas».")
            return
        from src.services.banca_online import config as CFG
        cfg = CFG.obtener_config(cta, id_empresa=_empresa())
        if not cfg:
            self.lbl_banca.setText("● Sin conexión configurada (modo simulado)")
        else:
            modo = "simulado" if cfg.get("modo_simulado", 1) else f"REAL · {cfg.get('proveedor')}"
            self.lbl_banca.setText(f"● Conexión: {modo}   ·   Última sincronización: "
                                   f"{cfg.get('ultima_sync') or 'nunca'}")

    def _banca_config(self):
        cta = self._banca_cuenta()
        if not cta:
            _info_msg(self, "Conexión bancaria", "No hay cuentas bancarias. Crea una en la pestaña «Cuentas».")
            return
        from src.gui.proyectos_gui import _FormDialog
        from src.services.banca_online import config as CFG
        cfg = CFG.obtener_config(cta, id_empresa=_empresa()) or {}
        d = _FormDialog(self, "Conexión bancaria (open banking / PSD2)", [
            {"key": "proveedor", "label": "Proveedor:", "tipo": "combo",
             "opciones": [("Simulado", "simulado"), ("PSD2 genérico", "psd2_generico")],
             "default": cfg.get("proveedor", "simulado")},
            {"key": "endpoint", "label": "Endpoint (API del agregador):", "default": cfg.get("endpoint")},
            {"key": "account_id", "label": "ID de cuenta en el proveedor:", "default": cfg.get("account_id")},
            {"key": "credencial", "label": "Token / API key (vacío = conservar la actual):"},
            {"key": "modo_simulado", "label": "Modo:", "tipo": "combo",
             "opciones": [("Simulado", "1"), ("Real", "0")],
             "default": "1" if cfg.get("modo_simulado", 1) else "0"},
        ])
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        v = d.datos()
        try:
            CFG.guardar_conexion(cta, proveedor=v["proveedor"], endpoint=v["endpoint"] or None,
                                 account_id=v["account_id"] or None, credencial=v["credencial"] or None,
                                 modo_simulado=(v["modo_simulado"] == "1"), id_empresa=_empresa())
            _info_msg(self, "Conexión bancaria", "Conexión guardada correctamente.")
        except Exception as e:
            _error_msg(self, "Conexión bancaria", str(e))
            return
        self._banca_estado()

    def _banca_sync(self):
        cta = self._banca_cuenta()
        if not cta:
            _info_msg(self, "Sincronización bancaria", "No hay cuentas bancarias. Crea una en la pestaña «Cuentas».")
            return
        try:
            from src.services.banca_online import sync as SYNC
            r = SYNC.sincronizar(cta, id_empresa=_empresa())
            if r.get("ok"):
                extra = ("\n\n(Modo simulado: sin conexión real no se descargan movimientos.)"
                         if r["importados"] == 0 else "")
                _info_msg(self, "Sincronización bancaria",
                                        f"Movimientos importados: {r['importados']}   ·   "
                                        f"Conciliados: {r.get('conciliados', 0)}" + extra)
            else:
                _error_msg(self, "Error", r.get("error", ""))
            self._banca_estado()
        except Exception as e:
            _error_msg(self, "Error", str(e))

    # ── Conciliación ──────────────────────────────────────────────────────────
    def _tab_conciliacion(self):
        w = QWidget(); w.setStyleSheet(f"background:{_BG};"); lay = QVBoxLayout(w)
        bar = QHBoxLayout()
        self.in_extracto = _inp("ID extracto"); self.in_extracto.setFixedWidth(120)
        bar.addWidget(QLabel("Extracto:")); bar.addWidget(self.in_extracto)
        bar.addWidget(_btn("📥 Importar extracto", self._importar_extracto, primary=True))
        bar.addWidget(_btn("Conciliar automático", self._conciliar_auto, primary=True))
        bar.addWidget(_btn("✅ Aprobar Conciliación", self._aprobar_conciliacion, primary=True))
        bar.addWidget(_btn("Conciliar manualmente", self._conciliar_manual, primary=True))
        bar.addStretch(); bar.addWidget(self._btn_actualizar(self._conciliar_auto)); lay.addLayout(bar)
        self.lbl_conc = QLabel(""); self.lbl_conc.setStyleSheet(f"color:{_DIM};")
        lay.addWidget(self.lbl_conc)
        ayuda_conc = QLabel("«Aprobar Conciliación» confirma directamente la sugerencia de mayor "
                            "puntuación de la línea seleccionada (movimiento de tesorería o factura "
                            "pendiente de cliente/proveedor). «Conciliar manualmente» permite elegir "
                            "entre todos los candidatos.")
        ayuda_conc.setWordWrap(True); ayuda_conc.setStyleSheet(f"color:{_DIM};")
        lay.addWidget(ayuda_conc)
        self.tbl_conc = _tabla(["Línea", "Fecha", "Importe", "Concepto", "Conciliado", "Sugerencia"])
        lay.addWidget(self.tbl_conc)
        self.tabs.addTab(w, "Conciliación")

    def _sugerencia_top(self, id_linea):
        """Mejor candidato (score%, etiqueta) para una línea, o (None, texto) si no hay."""
        try:
            cand = _CC.sugerir(id_linea, id_empresa=_empresa())
        except Exception as e:
            logger.debug("sugerir(%s): %s", id_linea, e)
            return None, "—"
        if not cand:
            return None, "Sin candidatos"
        top = cand[0]
        return top, f"{top['score']:.0f}% Coincidencia · {top.get('etiqueta', '')}"

    def _importar_extracto(self):
        dlg = _ImportarExtractoDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.contenido:
            return
        try:
            r = _CC.importar_extracto(dlg.contenido, dlg.formato, id_cuenta=dlg.id_cuenta,
                                      nombre_fichero=dlg.ruta.rsplit("/", 1)[-1].rsplit("\\", 1)[-1],
                                      id_empresa=_empresa())
        except Exception as e:
            _error_msg(self, "Importar extracto", f"No se pudo importar: {e}")
            return
        self.in_extracto.setText(str(r["id_extracto"]))
        _info_msg(
            self, "Importar extracto",
            f"Extracto #{r['id_extracto']} importado ({r['formato']}, {r['num_lineas']} líneas).")
        self._conciliar_auto()

    def _conciliar_auto(self):
        try:
            eid = int(self.in_extracto.text() or 0)
        except ValueError:
            _info_msg(self, "Conciliación", "Indica antes un ID de extracto válido.")
            return
        if not eid:
            _info_msg(self, "Conciliación", "Indica antes un ID de extracto válido.")
            return
        try:
            r = _CC.conciliar_automatico(eid, id_empresa=_empresa())
            self.lbl_conc.setText(f"Conciliadas: {r['conciliadas']}  Ambiguas: {r['ambiguas']}  "
                                  f"Sin match: {r['sin_match']}")
            difs = _CC.diferencias(eid, id_empresa=_empresa())
            self.tbl_conc.setRowCount(len(difs))
            for i, d in enumerate(difs):
                _, texto_sug = self._sugerencia_top(d["id"])
                for j, v in enumerate([d["id"], d["fecha"], f"{float(d['importe']):.2f}",
                                       d.get("concepto"), "No", texto_sug]):
                    self.tbl_conc.setItem(i, j, _it(v))
            _info_msg(self, "Conciliación",
                     f"Conciliadas: {r['conciliadas']} · Ambiguas: {r['ambiguas']} · "
                     f"Sin match: {r['sin_match']}")
        except Exception as e:
            _error_msg(self, "Error", str(e))

    def _fila_conc_seleccionada(self):
        r = self.tbl_conc.currentRow()
        if r < 0 or self.tbl_conc.item(r, 0) is None:
            return None
        try:
            return int(self.tbl_conc.item(r, 0).text())
        except (TypeError, ValueError):
            return None

    def _aprobar_conciliacion(self):
        """Confirma de un clic la sugerencia de MAYOR puntuación para la línea seleccionada
        (movimiento de tesorería o factura pendiente de cliente/proveedor)."""
        id_linea = self._fila_conc_seleccionada()
        if id_linea is None:
            _info_msg(self, "Aprobar Conciliación",
                     "Selecciona antes una línea (diferencia) en la tabla.")
            return
        top, _texto = self._sugerencia_top(id_linea)
        if top is None:
            _info_msg(self, "Aprobar Conciliación",
                     "No hay ningún candidato para esta línea. Usa «Conciliar manualmente» "
                     "para emparejarla a mano.")
            return
        id_mov = _CC.confirmar_candidato(id_linea, top, tipo="manual", id_empresa=_empresa())
        if id_mov is not None:
            _info_msg(self, "Aprobar Conciliación",
                     f"Línea #{id_linea} conciliada ({top['score']:.0f}% de confianza) con: "
                     f"{top.get('etiqueta', '')}.")
            self._conciliar_auto()
        else:
            _error_msg(self, "Aprobar Conciliación",
                      "No se pudo conciliar la línea (puede que el candidato ya se haya usado "
                      "en otra línea). Refresca y vuelve a intentarlo.")

    def _conciliar_manual(self):
        """Emparejamiento manual: lista TODOS los candidatos (movimientos de tesorería Y facturas
        pendientes de cliente/proveedor) con su puntuación de confianza real, como alternativa
        cuando la sugerencia automática no es de fiar o para líneas de baja confianza/sin match."""
        id_linea = self._fila_conc_seleccionada()
        if id_linea is None:
            _info_msg(self, "Conciliar manualmente",
                                    "Selecciona antes una línea (diferencia) en la tabla.")
            return
        candidatos = _CC.sugerir(id_linea, id_empresa=_empresa())
        if not candidatos:
            _info_msg(self, "Conciliar manualmente",
                                    "No hay movimientos ni facturas pendientes candidatos para esta "
                                    "línea (mismo importe aproximado, fecha próxima).")
            return
        etiquetas = [f"{c['score']:.0f}% · {c.get('etiqueta', '')}" for c in candidatos]
        elegido, ok = _pedir_opcion(self, "Conciliar manualmente",
                                    "Candidato con el que emparejar la línea (puntuación de confianza):",
                                    etiquetas)
        if not ok or not elegido:
            return
        candidato = candidatos[etiquetas.index(elegido)]
        id_mov = _CC.confirmar_candidato(id_linea, candidato, tipo="manual", id_empresa=_empresa())
        if id_mov is not None:
            _info_msg(self, "Conciliar manualmente",
                                    f"Línea #{id_linea} conciliada con: {candidato.get('etiqueta', '')}.")
            self._conciliar_auto()
        else:
            _error_msg(self, "Conciliar manualmente", "No se pudo conciliar la línea.")

    # ── Remesas SEPA ──────────────────────────────────────────────────────────
    def _tab_remesas(self):
        w = QWidget(); w.setStyleSheet(f"background:{_BG};"); lay = QVBoxLayout(w)
        bar = QHBoxLayout()
        self.in_remesa = _inp("ID remesa"); self.in_remesa.setFixedWidth(120)
        bar.addWidget(QLabel("Remesa:")); bar.addWidget(self.in_remesa)
        bar.addWidget(_btn("Nueva remesa", self._nueva_remesa, primary=True))
        bar.addWidget(_btn("Añadir operación", self._anadir_operacion_remesa, primary=True))
        bar.addWidget(_btn("Generar XML", self._generar_remesa, primary=True))
        bar.addStretch(); bar.addWidget(self._btn_actualizar(self._load_remesas)); lay.addLayout(bar)
        self.tbl_rem = _tabla(["ID", "Tipo", "Estado", "Operaciones", "Importe", "Mensaje"])
        lay.addWidget(self.tbl_rem)

        bar_mand = QHBoxLayout()
        bar_mand.addWidget(QLabel("Mandatos SEPA"))
        bar_mand.addWidget(_btn("Nuevo mandato", self._nuevo_mandato, primary=True))
        bar_mand.addStretch()
        lay.addLayout(bar_mand)
        self.tbl_mand = _tabla(["ID", "Referencia", "Tipo", "Deudor", "IBAN", "Estado"])
        lay.addWidget(self.tbl_mand)

        self.tabs.addTab(w, "Remesas SEPA")
        self._load_remesas()
        self._load_mandatos()

    def _load_remesas(self):
        try:
            # Cliente fino (Strangler, Fase 3): los datos vienen de la capa de datos; la GUI orquesta.
            from src.db.sepa import listar_remesas
            filas = listar_remesas(id_empresa=_empresa())
            self.tbl_rem.setRowCount(len(filas))
            for i, r in enumerate(filas):
                vals = [r["id"], r["tipo"], r["estado"], r["num_operaciones"],
                        f"{float(r['importe_total']):.2f}", r.get("mensaje_id")]
                for j, v in enumerate(vals):
                    self.tbl_rem.setItem(i, j, _it(v))
        except Exception as e:
            logger.error("remesas: %s", e)

    def _load_mandatos(self):
        try:
            filas = _S.listar_mandatos(solo_activos=False, id_empresa=_empresa())
            self.tbl_mand.setRowCount(len(filas))
            for i, m in enumerate(filas):
                vals = [m["id"], m.get("referencia_mandato"), m.get("tipo"), m.get("nombre_deudor"),
                        m.get("iban_deudor"), m.get("estado")]
                for j, v in enumerate(vals):
                    self.tbl_mand.setItem(i, j, _it(v))
        except Exception as e:
            logger.error("mandatos: %s", e)

    def _nueva_remesa(self):
        from src.gui.proyectos_gui import _FormDialog
        d = _FormDialog(self, "Nueva remesa SEPA", [
            {"key": "tipo", "label": "Tipo:", "tipo": "combo",
             "opciones": [("Transferencia", "TRANSFER"), ("Adeudo domiciliado", "ADEUDO")]},
        ])
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        v = d.datos()
        try:
            rid = _S.crear_remesa(v["tipo"], id_empresa=_empresa())
            if rid is None:
                raise RuntimeError("No se pudo crear la remesa.")
            self.in_remesa.setText(str(rid))
            self._load_remesas()
            _info_msg(self, "Remesas SEPA", f"Remesa #{rid} creada en borrador.")
        except Exception as e:
            _error_msg(self, "Remesas SEPA", str(e))

    def _anadir_operacion_remesa(self):
        try:
            rid = int(self.in_remesa.text() or 0)
        except ValueError:
            rid = 0
        if not rid:
            _info_msg(self, "Remesas SEPA", "Indica antes el ID de una remesa en borrador.")
            return
        mandatos = _S.listar_mandatos(id_empresa=_empresa())
        opciones_mandato = [("(sin mandato)", None)] + [
            (f"#{m['id']} · {m.get('referencia_mandato')} · {m.get('nombre_deudor')}", m["id"])
            for m in mandatos]
        from src.gui.proyectos_gui import _FormDialog
        d = _FormDialog(self, f"Añadir operación a remesa #{rid}", [
            {"key": "nombre_tercero", "label": "Nombre del tercero:"},
            {"key": "iban", "label": "IBAN:"},
            {"key": "importe", "label": "Importe (€):"},
            {"key": "concepto", "label": "Concepto (opcional):"},
            {"key": "id_mandato", "label": "Mandato (solo adeudos):", "tipo": "combo",
             "opciones": opciones_mandato},
        ])
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        v = d.datos()
        try:
            importe = float((v.get("importe") or "0").replace(",", "."))
        except ValueError:
            _error_msg(self, "Remesas SEPA", "El importe debe ser un número válido.")
            return
        try:
            lid = _S.anadir_operacion(rid, v["nombre_tercero"], v["iban"], importe,
                                      concepto=v.get("concepto") or None,
                                      id_mandato=v.get("id_mandato"), id_empresa=_empresa())
            if lid is None:
                raise RuntimeError("No se pudo añadir la operación.")
            self._load_remesas()
            _info_msg(self, "Remesas SEPA", f"Operación añadida a la remesa #{rid}.")
        except Exception as e:
            _error_msg(self, "Remesas SEPA", str(e))

    def _nuevo_mandato(self):
        from src.gui.proyectos_gui import _FormDialog
        d = _FormDialog(self, "Nuevo mandato SEPA", [
            {"key": "referencia_mandato", "label": "Referencia del mandato:"},
            {"key": "nombre_deudor", "label": "Nombre del deudor:"},
            {"key": "iban_deudor", "label": "IBAN del deudor:"},
            {"key": "tipo", "label": "Tipo:", "tipo": "combo",
             "opciones": [("CORE (particulares)", "CORE"), ("B2B (empresas)", "B2B")]},
        ])
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        v = d.datos()
        try:
            mid = _S.crear_mandato(v["referencia_mandato"], v["nombre_deudor"], v["iban_deudor"],
                                   tipo=v["tipo"], id_empresa=_empresa())
            if mid is None:
                raise RuntimeError("No se pudo crear el mandato.")
            self._load_mandatos()
            _info_msg(self, "Mandatos SEPA", f"Mandato #{mid} creado correctamente.")
        except Exception as e:
            _error_msg(self, "Mandatos SEPA", str(e))

    def _generar_remesa(self):
        from src.gui.mfa_gui import step_up_sesion
        try:
            rid = int(self.in_remesa.text() or 0)
        except ValueError:
            return
        if not step_up_sesion("finanzas.critica", self):
            return
        try:
            res = _SEPA.generar_xml(rid, id_empresa=_empresa())
            if res.get("ok"):
                _info_msg(self, "SEPA", f"XML generado y validado (XSD).\n"
                                       f"Mensaje: {res['mensaje_id']}")
            else:
                _error_msg(self, "SEPA", f"No válido: {res.get('errores')}")
            self._load_remesas()
        except Exception as e:
            _error_msg(self, "Error", str(e))

    # ── Cash Flow ─────────────────────────────────────────────────────────────
    def _tab_cashflow(self):
        w = QWidget(); w.setStyleSheet(f"background:{_BG};"); lay = QVBoxLayout(w)
        bar = QHBoxLayout()
        self.cmb_gran = _combo([("Mensual", "mensual"), ("Semanal", "semanal"),
                                ("Diario", "diario"), ("Anual", "anual")])
        self.cmb_gran.setMinimumWidth(150)   # evita texto cortado en el desplegable
        self.cmb_esc = _combo([("Real", "real"), ("Previsto", "previsto")])
        self.cmb_esc.setMinimumWidth(150)
        bar.addWidget(QLabel("Granularidad:")); bar.addWidget(self.cmb_gran)
        bar.addWidget(QLabel("Escenario:")); bar.addWidget(self.cmb_esc)
        # `lambda: self._load_cashflow()` (no conectar el método directamente): la señal `clicked(bool)`
        # de Qt pasa su `checked` POSICIONALMENTE al único parámetro del slot (`avisar`), así que un
        # `_btn(txt, self._load_cashflow, ...)` directo dejaba `avisar` siempre en `False` en cada
        # click real — el aviso de éxito/error nunca se mostraba (bug real, ya corregido). El botón
        # "Actualizar" (`_btn_cargando`) no tenía este problema porque su wrapper interno ya llama a
        # `cb()` sin argumentos.
        bar.addWidget(_btn("Calcular", lambda: self._load_cashflow(), primary=True))
        bar.addStretch(); bar.addWidget(self._btn_actualizar(self._load_cashflow)); lay.addLayout(bar)
        self.tbl_cf = _tabla(["Periodo", "Entradas", "Salidas", "Neto", "Acumulado"])
        lay.addWidget(self.tbl_cf)
        self.tabs.addTab(w, "Flujo de caja")
        self._load_cashflow(avisar=False)

    def _load_cashflow(self, avisar=True):
        """`avisar=False` en la carga inicial de la pestaña y en `refrescar()` (no son una acción del
        usuario, no deben mostrar un aviso emergente) — antes el aviso se disparaba solo con abrir
        Tesorería. El botón 'Calcular' y el 'Actualizar' propio de esta pestaña usan `avisar=True`
        (valor por defecto)."""
        try:
            gran = self.cmb_gran.currentData() or "mensual"
            esc = self.cmb_esc.currentData() or "real"
            anio = _dt.date.today().year
            filas = _CF.flujo(_empresa(), desde=f"{anio}-01-01", hasta=f"{anio}-12-31",
                              granularidad=gran, escenario=esc)
            self.tbl_cf.setRowCount(len(filas))
            for i, f in enumerate(filas):
                for j, v in enumerate([f["periodo"], f"{f['entradas']:.2f}", f"{f['salidas']:.2f}",
                                       f"{f['neto']:.2f}", f"{f['acumulado']:.2f}"]):
                    self.tbl_cf.setItem(i, j, _it(v))
            if avisar:
                _info_msg(self, "Flujo de caja", f"Calculado: {len(filas)} periodo(s).")
        except Exception as e:
            logger.error("cashflow: %s", e)
            if avisar:
                _error_msg(self, "Flujo de caja", f"No se pudo calcular: {e}")

    # ── Previsión ─────────────────────────────────────────────────────────────
    def _tab_prevision(self):
        w = QWidget(); w.setStyleSheet(f"background:{_BG};"); lay = QVBoxLayout(w)
        self.lbl_alertas_liq = QLabel(""); self.lbl_alertas_liq.setStyleSheet(f"color:{T.ADVERTENCIA};")
        lay.addWidget(self.lbl_alertas_liq)
        # Actualizar pegado a la esquina superior derecha de LA TABLA (sin la fila de alertas de por
        # medio, que ahora queda por encima de este botón en vez de entre el botón y la tabla).
        top = QHBoxLayout(); top.addStretch(1); top.addWidget(self._btn_actualizar(self._load_prevision))
        lay.addLayout(top)
        self.tbl_prev = _tabla(["Horizonte", "Fecha", "Por cobrar", "Comprometido",
                                "Operativo est.", "Liquidez est.", "Tensión"])
        lay.addWidget(self.tbl_prev)
        self.tabs.addTab(w, "Previsión")
        self._load_prevision()

    def _load_prevision(self):
        try:
            proy = _PF.proyeccion_liquidez(_empresa())
            ps = proy["proyecciones"]
            self.tbl_prev.setRowCount(len(ps))
            for i, p in enumerate(ps):
                vals = [f"{p['horizonte_dias']} d", p["fecha"], f"{p['por_cobrar']:.2f}",
                        f"{p['comprometido']:.2f}", f"{p['flujo_operativo_estimado']:.2f}",
                        f"{p['liquidez_estimada']:.2f}", "⚠️" if p["tension"] else "OK"]
                for j, v in enumerate(vals):
                    self.tbl_prev.setItem(i, j, _it(v))
            alertas = _PF.alertas_liquidez(_empresa())
            self.lbl_alertas_liq.setText(
                f"⚠️ {len(alertas)} horizonte(s) en tensión de liquidez." if alertas
                else "Sin alertas de tensión de liquidez.")
        except Exception as e:
            logger.error("prevision: %s", e)

    # ── Refresco global ───────────────────────────────────────────────────────
    def refrescar(self):
        for fn in (self._load_posicion, self._load_cuentas, self._load_movimientos,
                   self._load_vencimientos, self._load_remesas, self._load_mandatos,
                   self._load_prevision):
            try:
                fn()
            except Exception as e:
                logger.debug("refrescar: %s", e)
        try:
            self._load_cashflow(avisar=False)
        except Exception as e:
            logger.debug("refrescar cashflow: %s", e)
