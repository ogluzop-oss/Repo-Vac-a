"""
Seguridad · administración RBAC / ACL (FASE 11).

Pantalla NUEVA (no modifica las existentes). Permite gestionar roles, sus permisos, las
asignaciones de rol a usuario, grupos y ACL — sin tocar código. Estilo coherente (dark+cian);
acotada a la empresa activa. Sincroniza el catálogo y los roles del sistema al abrir.
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel, QTableWidgetItem,
                             QTabWidget, QVBoxLayout, QWidget)

from src.db import rbac as _R
from src.gui.catalogo_gestion import (_BG, _CIAN, _DIM, _ROJO, _TEXT, _btn, _btn_cargando, _btn_x,
                                      _chk, _combo, _dialogo_frameless, _inp, _tabla)
from src.gui.foundation import tokens as T
from src.services.seguridad import catalogo as _cat
from src.services.seguridad import modulos_menu as _mm
from src.services.seguridad import pestanas_app as _pa

try:
    from assets.estilo_global import estilizar_completer as _estilizar_completer
except Exception:  # pragma: no cover
    _estilizar_completer = None

logger = logging.getLogger("seguridad.gui")


def _it(v):
    return QTableWidgetItem("" if v is None else str(v))


class _InfoDialog(QDialog):
    """Aviso propio (sustituye a QMessageBox.information/.warning): sin barra de Windows, esquinas
    redondeadas y un único botón «Aceptar». Los QMessageBox nativos, sobre una ventana anfitriona
    frameless (como todas las ventanas completas de la app), pueden quedar sin handle nativo correcto
    y comportarse de forma errática — mismo criterio ya aplicado en `almacenes_gui.py`."""

    def __init__(self, titulo, mensaje, parent=None):
        super().__init__(parent)
        v = _dialogo_frameless(self, titulo, ancho=380)
        lbl = QLabel(mensaje)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color:{_DIM};font-size:13px;")
        v.addWidget(lbl)
        fila = QHBoxLayout()
        fila.addStretch()
        fila.addWidget(_btn("Aceptar", self.accept, primary=True))
        v.addLayout(fila)


def _info(parent, titulo, mensaje):
    _InfoDialog(titulo, mensaje, parent).exec()


class _NuevoGrupoDialog(QDialog):
    """Alta de un grupo (código + nombre) — mismo patrón frameless que `_InfoDialog`."""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = _dialogo_frameless(self, "Nuevo grupo", ancho=360)
        v.addWidget(QLabel("Código:"))
        self.inp_codigo = _inp("p. ej. ALMACEN_NORTE")
        v.addWidget(self.inp_codigo)
        v.addWidget(QLabel("Nombre:"))
        self.inp_nombre = _inp("Nombre descriptivo del grupo")
        v.addWidget(self.inp_nombre)
        fila = QHBoxLayout()
        fila.addStretch()
        fila.addWidget(_btn("Crear", self.accept, primary=True))
        v.addLayout(fila)

    def valores(self):
        return self.inp_codigo.text().strip(), self.inp_nombre.text().strip()


class _ComboPopupCompleter(QComboBox):
    """QComboBox cuya flecha abre el MISMO popup que el autocompletado, en vez del desplegable
    nativo de Qt (`QComboBoxPrivateContainer`) — reproducido y confirmado (captura de pantalla real
    del popup) que ese desplegable nativo recorta mal las esquinas derechas y a veces esconde su
    propia scrollbar en esta app, incluso con el filtro global de estilos aplicado. El popup del
    QCompleter (`estilizar_completer`, máscara redondeada real) sí se ve correcto, así que se
    reutiliza para AMBOS casos: escribir para filtrar Y pulsar la flecha para ver la lista completa."""

    def showPopup(self):
        completer = self.completer()
        if completer is None:
            super().showPopup()
            return
        self.setFocus()
        completer.setCompletionPrefix("")
        completer.complete()


def _combo_buscable(opciones, filas_visibles=None):
    """QComboBox editable con autocompletado (case-insensitive, coincide en cualquier parte del
    texto) — permite escribir el permiso deseado a mano en vez de solo desplegar la lista. La
    flecha del desplegable también usa este mismo popup (ver `_ComboPopupCompleter`).

    `filas_visibles`: si se indica, reserva altura para mostrar ese número de filas sin scroll
    (con más opciones que eso, aparece la scrollbar)."""
    from PyQt6.QtCore import Qt as _Qt
    from PyQt6.QtCore import QStringListModel
    from PyQt6.QtWidgets import QCompleter
    cb = _combo(opciones, cls=_ComboPopupCompleter)
    cb.setEditable(True)
    cb.setInsertPolicy(cb.InsertPolicy.NoInsert)
    modelo = QStringListModel([etq for etq, _v in opciones])
    completer = QCompleter(modelo, cb)
    completer.setCaseSensitivity(_Qt.CaseSensitivity.CaseInsensitive)
    completer.setFilterMode(_Qt.MatchFlag.MatchContains)
    cb.setCompleter(completer)
    # El popup de sugerencias del completer es un QAbstractItemView TOTALMENTE APARTE del propio
    # desplegable de la combo (no hereda su estilo ni el del combo). Un QSS de borde/radio normal
    # NO recorta un popup top-level (por eso un `_CornerCover` tampoco valía aquí, ver commits
    # previos) — se reutiliza `estilizar_completer`, el MISMO helper ya usado por todas las barras
    # de búsqueda de artículos de la app: sustituye el popup por una vista con máscara redondeada
    # real (`showEvent`/`resizeEvent`) + el QSS turquesa estándar. Un único diseño de scrollbar en
    # toda la app, en vez de reinventar uno propio aquí.
    if _estilizar_completer is not None:
        try:
            _estilizar_completer(completer)
        except Exception:
            pass
    if filas_visibles:
        popup = completer.popup()
        alto_fila = popup.fontMetrics().height() + 14   # padding vertical del QSS (7px arriba+abajo)
        popup.setMinimumHeight(filas_visibles * alto_fila + 14)   # + padding del propio popup
    # Sin esto, `modelo` (objeto Python sin dueño C++ — no se pasó como `parent`) queda sin
    # referencias vivas en cuanto termina esta función y PyQt lo destruye por GC: el completer se
    # queda con `model()` a None y deja de filtrar nada en silencio (bug real reproducido).
    cb._modelo_completer = modelo
    cb._completer_permiso = completer
    return cb


def _recargar_combo_buscable(cb, opciones):
    """Repuebla un combo creado con `_combo_buscable` DESPUÉS de construido — a diferencia de un
    `clear()`+`addItem()` a secas, también actualiza el modelo del QCompleter (`cb._modelo_completer`,
    la MISMA instancia que ya usa su popup de autocompletado), para que buscar escribiendo siga
    encontrando las opciones nuevas en vez de las que había al construirlo."""
    cb.blockSignals(True)
    cb.clear()
    for etq, val in opciones:
        cb.addItem(etq, val)
    cb.blockSignals(False)
    modelo = getattr(cb, "_modelo_completer", None)
    if modelo is not None:
        modelo.setStringList([etq for etq, _v in opciones])


def _empresa():
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return EMPRESA_DEFAULT_ID


class SeguridadWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background:{_BG};")
        # Asegura catálogo + roles del sistema de la empresa (idempotente).
        try:
            _cat.sincronizar_roles_sistema(_empresa())
        except Exception as e:
            logger.debug("sincronizar al abrir: %s", e)

        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("Seguridad · Roles, Permisos, Grupos y ACL")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        # (El "Actualizar" global se retiró: cada pestaña con tabla tiene su propio botón de refresco.)
        if callback_vuelta:
            cab.addWidget(_btn_x(self._volver))
        root.addLayout(cab)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(T.qss_tabs())   # mismo diseño de pestañas que el Centro de Inteligencia
        root.addWidget(self.tabs)

        # Lazy loading (init en primer acceso): Roles/Asignaciones/Reglas de acceso hacen su propia
        # consulta a BD durante la construcción y Gobierno embebe un panel completo — construir las
        # 4 de golpe es lo que hacía que el módulo tardara en abrirse. Se registra un placeholder por
        # pestaña y el contenido real se construye la primera vez que el usuario la visita.
        from src.gui.transiciones import instalar_pestanas_lazy
        instalar_pestanas_lazy(self.tabs, [
            ("Roles", self._construir_tab_roles),
            ("Reglas de acceso", self._construir_tab_acl),
            ("Grupos", self._construir_tab_grupos),
            ("Gobierno", self._construir_tab_gobierno),
            ("RGPD", self._construir_tab_rgpd),
            ("Política de contraseñas", self._construir_tab_password_politica),
            ("Incidentes", self._construir_tab_incidentes),
            ("Sesiones activas", self._construir_tab_sesiones),
        ])
        self._tab_continuidad()   # infra/continuidad: DR + Resiliencia (dashboards embebidos)

        # Reglas de acceso (Seguridad · Pestañas): con acceso completo al módulo, todas visibles
        # por defecto; sin acceso completo (entró solo por una concesión de pestaña suelta), solo
        # la(s) concedida(s) — mismo criterio que el resto de módulos con pestañas registradas.
        _tiene_completo = _pa.tiene_modulo_completo("seguridad", self.usuario, False)
        for _i, _slug in enumerate(["roles", "reglas_acceso", "grupos", "gobierno",
                                    "rgpd", "password_politica", "incidentes", "sesiones",
                                    "dr", "resiliencia"]):
            if not _pa.visible(f"seguridad.{_slug}", self.usuario, _tiene_completo):
                self.tabs.setTabVisible(_i, False)

    def _tab_continuidad(self):
        """Aloja los paneles de infraestructura/continuidad (Disaster Recovery y Resiliencia/Offline)
        como pestañas de Seguridad, reutilizando las ventanas existentes sin duplicarlas."""
        try:
            from src.gui.dr_dashboard_gui import DRDashboardWindow
            self.tabs.addTab(DRDashboardWindow(callback_vuelta=None, usuario=self.usuario),
                             "Disaster Recovery")
        except Exception as e:
            logger.debug("tab DR: %s", e)
        try:
            from src.gui.resiliencia_dashboard import ResilienciaDashboardWindow
            self.tabs.addTab(ResilienciaDashboardWindow(callback_vuelta=None, usuario=self.usuario),
                             "Resiliencia")
        except Exception as e:
            logger.debug("tab resiliencia: %s", e)

    def _construir_tab_gobierno(self):
        """Enterprise 7: Gobierno Corporativo (Organigrama/Autoridad/Delegaciones/Políticas/
        Escalados) alojado en Seguridad. Aditivo; no altera las pestañas existentes."""
        try:
            from src.gui.paneles.panel_gobierno import PanelGobierno
            return PanelGobierno(usuario=self.usuario)
        except Exception as e:
            logger.debug("tab gobierno: %s", e)
            return QWidget()

    # ── Roles (perfil base) + acceso a módulos completos por usuario ────────────
    def _construir_tab_roles(self):
        w = QWidget(); w.setStyleSheet(f"background:{_BG};"); lay = QVBoxLayout(w)
        # Fila superior, ANCHO COMPLETO — así ambas tablas de abajo arrancan a la misma altura
        # (nada las precede en su propia columna que pudiera robarles espacio de forma desigual).
        acc = QHBoxLayout()
        acc.addWidget(_btn("Conceder", self._conceder_modulo, primary=True))
        acc.addWidget(_btn("Quitar", self._quitar_modulo, danger=True))
        acc.addStretch()
        lay.addLayout(acc)
        self.btn_conceder_mod = acc.itemAt(0).widget()
        self.btn_quitar_mod = acc.itemAt(1).widget()
        # `:disabled` explícito (gris apagado) — `_btn` no lo define — así el estado apagado/
        # iluminado se distingue con claridad según haya o no una celda seleccionada en su columna.
        for _b in (self.btn_conceder_mod, self.btn_quitar_mod):
            _b.setStyleSheet(_b.styleSheet() +
                             "QPushButton:disabled{background:#161B22;color:#4B5563;border-color:#30363D;}")
        self.btn_conceder_mod.setEnabled(False)
        self.btn_quitar_mod.setEnabled(False)

        cuerpo = QHBoxLayout()
        self.tbl_usuarios_perm = _tabla(["ID", "Usuario", "Rol"])
        self.tbl_usuarios_perm.cellClicked.connect(self._sel_usuario_perm)
        cuerpo.addWidget(self.tbl_usuarios_perm, 1)
        # Módulos: UNA sola tabla de 2 columnas (no dos tablas separadas) — así queda garantizada
        # la misma altura que la tabla de la izquierda, al estar en la misma fila del layout.
        self.tbl_modulos = _tabla(["Módulos Añadidos", "Módulos sin añadir"])
        from PyQt6.QtWidgets import QAbstractItemView
        # Selección de CELDA, no de fila completa (con SelectRows, pulsar un módulo resaltaba
        # también la celda vecina — confuso). Hover turquesa por celda para feedback visual claro.
        self.tbl_modulos.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.tbl_modulos.setMouseTracking(True)
        self.tbl_modulos.setStyleSheet(
            self.tbl_modulos.styleSheet() + "QTableWidget::item:hover{background:#00FFC633;}")
        self.tbl_modulos.cellClicked.connect(self._sel_celda_modulo)
        cuerpo.addWidget(self.tbl_modulos, 1)
        lay.addLayout(cuerpo)

        self._sel_uid_perm = None
        self._usuarios_perm = []
        self._sel_modulo = None   # (v_id, columna) de la última celda pulsada en tbl_modulos
        self._modulos_col = {0: [], 1: []}   # v_ids por columna, para resolver el clic por fila
        self._load_usuarios_perm()
        return w

    def _load_usuarios_perm(self):
        """Usuarios de la tienda (perfil != SUPERADMIN — ese ya tiene acceso completo por defecto)."""
        try:
            from src.db.usuario import listar_usuarios_empresa
            usuarios = [u for u in listar_usuarios_empresa(_empresa())
                       if str(u.get("perfil") or "").upper() != "SUPERADMIN"]
        except Exception as e:
            logger.debug("listar usuarios para permisos: %s", e)
            usuarios = []
        self._usuarios_perm = usuarios
        self.tbl_usuarios_perm.setRowCount(len(usuarios))
        for i, u in enumerate(usuarios):
            for j, v in enumerate([u["id"], u["nombre"], u.get("perfil")]):
                self.tbl_usuarios_perm.setItem(i, j, _it(v))
        self.tbl_modulos.setRowCount(0)
        self._sel_uid_perm = None
        self._sel_modulo = None
        self.btn_conceder_mod.setEnabled(False)
        self.btn_quitar_mod.setEnabled(False)

    def _sel_usuario_perm(self, row, _c):
        try:
            self._sel_uid_perm = int(self.tbl_usuarios_perm.item(row, 0).text())
            self._load_modulos_usuario()
        except Exception:
            self._sel_uid_perm = None

    def _load_modulos_usuario(self):
        """Módulos Añadidos / Módulos sin añadir para el usuario seleccionado: por defecto según su
        perfil base (`modulos_menu.default_visible`), salvo que exista una regla ACL explícita
        (Conceder/Quitar de esta misma pestaña) que la sustituya, en cualquier dirección."""
        self._sel_modulo = None
        self.btn_conceder_mod.setEnabled(False)
        self.btn_quitar_mod.setEnabled(False)
        if not self._sel_uid_perm:
            self.tbl_modulos.setRowCount(0)
            return
        u = next((x for x in self._usuarios_perm if x["id"] == self._sel_uid_perm), None)
        perfil = (u.get("perfil") if u else "") or ""
        emp = _empresa()
        reglas = {r.get("recurso_id"): bool(r.get("permitido"))
                 for r in _R.listar_acl(recurso_tipo="modulo", id_empresa=emp)
                 if r.get("sujeto_tipo") == "usuario" and str(r.get("sujeto_id")) == str(self._sel_uid_perm)}
        anadidos, sin_anadir = [], []
        for texto, v_id in _mm.disponibles(emp):
            if v_id is None:
                continue
            tiene = reglas.get(v_id, _mm.default_visible(v_id, perfil))
            (anadidos if tiene else sin_anadir).append((texto, v_id))
        self._modulos_col = {0: anadidos, 1: sin_anadir}
        filas = max(len(anadidos), len(sin_anadir))
        self.tbl_modulos.setRowCount(filas)
        for i in range(filas):
            self.tbl_modulos.setItem(i, 0, _it(anadidos[i][0] if i < len(anadidos) else ""))
            self.tbl_modulos.setItem(i, 1, _it(sin_anadir[i][0] if i < len(sin_anadir) else ""))

    def _sel_celda_modulo(self, row, col):
        lista = self._modulos_col.get(col, [])
        if row >= len(lista):
            self._sel_modulo = None
            self.btn_conceder_mod.setEnabled(False)
            self.btn_quitar_mod.setEnabled(False)
            return
        v_id = lista[row][1]
        self._sel_modulo = (v_id, col)
        self.btn_conceder_mod.setEnabled(col == 1)
        self.btn_quitar_mod.setEnabled(col == 0)

    def _uid_perm_seleccionado(self):
        if not self._sel_uid_perm:
            _info(self, "Roles", "Selecciona primero un usuario en la tabla.")
            return None
        return self._sel_uid_perm

    def _conceder_modulo(self):
        uid = self._uid_perm_seleccionado()
        if uid is None:
            return
        if not self._sel_modulo or self._sel_modulo[1] != 1:
            _info(self, "Roles", "Selecciona un módulo de la columna «Módulos sin añadir».")
            return
        v_id = self._sel_modulo[0]
        from src.gui.mfa_gui import step_up_sesion
        if not step_up_sesion("permisos.cambiar", self):
            return
        if _R.set_acl("modulo", v_id, "usuario", uid, "acceder", permitido=True, id_empresa=_empresa()):
            self._load_modulos_usuario()
            _info(self, "Roles", "Módulo añadido correctamente.")
        else:
            _info(self, "Roles", "No se pudo conceder el acceso al módulo.")

    def _quitar_modulo(self):
        uid = self._uid_perm_seleccionado()
        if uid is None:
            return
        if not self._sel_modulo or self._sel_modulo[1] != 0:
            _info(self, "Roles", "Selecciona un módulo de la columna «Módulos Añadidos».")
            return
        v_id = self._sel_modulo[0]
        from src.gui.mfa_gui import step_up_sesion
        if not step_up_sesion("permisos.cambiar", self):
            return
        if _R.set_acl("modulo", v_id, "usuario", uid, "acceder", permitido=False, id_empresa=_empresa()):
            self._load_modulos_usuario()
            _info(self, "Roles", "Módulo quitado correctamente.")
        else:
            _info(self, "Roles", "No se pudo quitar el acceso al módulo.")

    # ── ACL (Reglas de acceso: Usuario + Pestaña) ───────────────────────────────
    def _construir_tab_acl(self):
        w = QWidget(); w.setStyleSheet(f"background:{_BG};"); lay = QVBoxLayout(w)
        fila_sel = QHBoxLayout()
        self.cmb_usuario_acl = _combo_buscable(self._opciones_usuarios_acl(), filas_visibles=5)
        self.cmb_usuario_acl.setMinimumWidth(160)
        self.cmb_usuario_acl.currentIndexChanged.connect(self._usuario_acl_cambiado)
        self.cmb_pestana_acl = _combo_buscable([], filas_visibles=8)
        self.cmb_pestana_acl.setMinimumWidth(340)
        # Desactivado (gris) hasta elegir un usuario: la lista de pestañas depende de su perfil.
        self.cmb_pestana_acl.setEnabled(False)
        fila_sel.addWidget(QLabel("Usuario:")); fila_sel.addWidget(self.cmb_usuario_acl)
        fila_sel.addWidget(QLabel("Pestaña:")); fila_sel.addWidget(self.cmb_pestana_acl)
        # Sincroniza el estado inicial del desplegable «Pestaña» con lo que YA aparece elegido en
        # «Usuario» (el combo muestra su primer elemento por defecto en cuanto se puebla, antes de
        # que exista ninguna señal de cambio que lo dispare) — así no se queda gris "de adorno" si
        # ya hay un usuario real mostrado.
        self._usuario_acl_cambiado()
        fila_sel.addStretch()
        lay.addLayout(fila_sel)
        fila_acc = QHBoxLayout()
        fila_acc.addWidget(_btn("Permitir acceso", self._permitir_recurso, primary=True))
        fila_acc.addWidget(_btn("Denegar acceso", self._denegar_recurso, danger=True))
        fila_acc.addWidget(_btn("Quitar regla", self._quitar_regla_acl))
        fila_acc.addStretch()
        fila_acc.addWidget(_btn_cargando("🔄  Actualizar", self._load_acl, primary=True))
        lay.addLayout(fila_acc)
        self.tbl_acl = _tabla(["Recurso", "Nombre", "Sujeto", "Sujeto ID", "Acción", "Efecto"])
        self.tbl_acl.cellClicked.connect(self._sel_regla_acl)
        lay.addWidget(self.tbl_acl)
        self._acl_filas = []
        self._fila_acl_seleccionada = None
        self._load_acl()
        return w

    def _opciones_usuarios_acl(self):
        """Usuarios de la tienda (perfil != SUPERADMIN — nunca se le puede denegar una pestaña)."""
        try:
            from src.db.usuario import listar_usuarios_empresa
            return [(u["nombre"], u["id"]) for u in listar_usuarios_empresa(_empresa())
                   if str(u.get("perfil") or "").upper() != "SUPERADMIN"]
        except Exception as e:
            logger.debug("listar usuarios para ACL: %s", e)
            return []

    def _perfil_de_uid(self, uid):
        try:
            from src.db.usuario import listar_usuarios_empresa
            for u in listar_usuarios_empresa(_empresa()):
                if u["id"] == uid:
                    return u.get("perfil") or ""
        except Exception as e:
            logger.debug("perfil de usuario ACL: %s", e)
        return ""

    def _usuario_acl_cambiado(self):
        """Al elegir un usuario, la lista de «Pestaña» se repuebla según SU perfil (ADMINISTRADOR/
        OPERARIO tienen restringidos módulos distintos) y se activa; sin usuario, permanece
        desactivada — no tendría sentido elegir una pestaña sin saber a quién se le va a aplicar."""
        uid = self.cmb_usuario_acl.currentData()
        if not uid:
            _recargar_combo_buscable(self.cmb_pestana_acl, [])
            self.cmb_pestana_acl.setEnabled(False)
            return
        perfil = self._perfil_de_uid(uid)
        _recargar_combo_buscable(self.cmb_pestana_acl, _pa.opciones_para_perfil(perfil))
        self.cmb_pestana_acl.setEnabled(True)

    def _permitir_recurso(self):
        uid = self.cmb_usuario_acl.currentData()
        if not uid:
            _info(self, "Reglas de acceso", "Selecciona un usuario.")
            return
        pestana_id = self.cmb_pestana_acl.currentData()
        if not pestana_id:
            _info(self, "Reglas de acceso", "Selecciona una pestaña.")
            return
        from src.gui.mfa_gui import step_up_sesion
        if not step_up_sesion("permisos.cambiar", self):
            return
        if _R.set_acl("pestana", pestana_id, "usuario", uid, "acceder",
                      permitido=True, id_empresa=_empresa()):
            self._load_acl()
            _info(self, "Reglas de acceso", f"Acceso a «{_pa.etiqueta(pestana_id)}» permitido a "
                                            f"{self.cmb_usuario_acl.currentText()}.")
        else:
            _info(self, "Reglas de acceso", "No se pudo guardar la regla.")

    def _denegar_recurso(self):
        uid = self.cmb_usuario_acl.currentData()
        if not uid:
            _info(self, "Reglas de acceso", "Selecciona un usuario.")
            return
        pestana_id = self.cmb_pestana_acl.currentData()
        if not pestana_id:
            _info(self, "Reglas de acceso", "Selecciona una pestaña.")
            return
        from src.gui.mfa_gui import step_up_sesion
        if not step_up_sesion("permisos.cambiar", self):
            return
        if _R.set_acl("pestana", pestana_id, "usuario", uid, "acceder",
                      permitido=False, id_empresa=_empresa()):
            self._load_acl()
            _info(self, "Reglas de acceso", f"Acceso a «{_pa.etiqueta(pestana_id)}» denegado a "
                                            f"{self.cmb_usuario_acl.currentText()}.")
        else:
            _info(self, "Reglas de acceso", "No se pudo guardar la regla.")

    def _sel_regla_acl(self, row, _col):
        try:
            self._fila_acl_seleccionada = self._acl_filas[row]
        except (IndexError, AttributeError):
            self._fila_acl_seleccionada = None

    def _quitar_regla_acl(self):
        """A diferencia de Permitir/Denegar (que CREAN una regla nueva y por eso necesitan elegir
        usuario + pestaña en los desplegables), quitar una regla EXISTENTE es más simple
        seleccionándola directamente en la tabla de abajo — evita tener que reconstruir a mano la
        misma combinación exacta que ya se ve en pantalla."""
        a = self._fila_acl_seleccionada
        if not a:
            _info(self, "Reglas de acceso", "Selecciona primero una regla en la tabla de abajo.")
            return
        from src.gui.mfa_gui import step_up_sesion
        if not step_up_sesion("permisos.cambiar", self):
            return
        if _R.eliminar_acl(a["recurso_tipo"], a.get("recurso_id"), a["sujeto_tipo"], a["sujeto_id"],
                           a["accion"], id_empresa=_empresa()):
            self._fila_acl_seleccionada = None
            self._load_acl()
            _info(self, "Reglas de acceso", f"Regla quitada — «{a.get('_nombre')}» vuelve a su "
                                            f"acceso habitual.")
        else:
            _info(self, "Reglas de acceso", "Esa regla ya no existía (puede que se haya quitado "
                                            "desde otro sitio) — se refresca la tabla.")
            self._load_acl()

    def _load_acl(self):
        # Solo pestañas (recurso_tipo="pestana") — el acceso a módulos completos se gestiona y
        # visualiza ahora desde la pestaña "Roles" (columnas Módulos Añadidos/sin añadir).
        filas = _R.listar_acl(recurso_tipo="pestana", id_empresa=_empresa())
        self.tbl_acl.setRowCount(len(filas))
        for i, a in enumerate(filas):
            nombre = _pa.etiqueta(a.get("recurso_id"))
            a["_nombre"] = nombre
            vals = [a["recurso_tipo"], nombre, a["sujeto_tipo"], a["sujeto_id"],
                    a["accion"], "Permitir" if a["permitido"] else "Denegar"]
            for j, v in enumerate(vals):
                self.tbl_acl.setItem(i, j, _it(v))
        self._acl_filas = filas
        self._fila_acl_seleccionada = None

    # ── Grupos (conjuntos de permisos y miembros reutilizables) ─────────────────
    def _construir_tab_grupos(self):
        w = QWidget(); w.setStyleSheet(f"background:{_BG};"); lay = QVBoxLayout(w)

        cuerpo = QHBoxLayout()
        col_grp = QVBoxLayout()
        fila_grp_titulo = QHBoxLayout()
        lbl_grp_titulo = QLabel("Grupo:")
        lbl_grp_titulo.setFixedHeight(34)   # misma altura que los combos "Permiso:"/"Usuario:" de
        lbl_grp_titulo.setAlignment(Qt.AlignmentFlag.AlignVCenter)  # las otras 2 columnas, para que
        fila_grp_titulo.addWidget(lbl_grp_titulo)                   # las 3 tablas arranquen a la misma Y
        col_grp.addLayout(fila_grp_titulo)
        fila_grp_btn = QHBoxLayout()
        fila_grp_btn.addWidget(_btn("Nuevo grupo", self._nuevo_grupo, primary=True))
        fila_grp_btn.addWidget(_btn("Eliminar grupo", self._eliminar_grupo, danger=True))
        fila_grp_btn.addStretch()
        col_grp.addLayout(fila_grp_btn)
        self.tbl_grupos = _tabla(["ID", "Código", "Nombre"])
        self.tbl_grupos.cellClicked.connect(self._sel_grupo)
        col_grp.addWidget(self.tbl_grupos)
        cuerpo.addLayout(col_grp, 1)

        col_perm = QVBoxLayout()
        fila_perm = QHBoxLayout()
        self.cmb_permiso_grupo = _combo_buscable([(c, c) for c in _cat.CATALOGO], filas_visibles=8)
        self.cmb_permiso_grupo.setMinimumWidth(220)
        fila_perm.addWidget(QLabel("Permiso:")); fila_perm.addWidget(self.cmb_permiso_grupo)
        col_perm.addLayout(fila_perm)
        fila_perm_btn = QHBoxLayout()
        fila_perm_btn.addWidget(_btn("Añadir permiso", self._anadir_permiso_grupo, primary=True))
        fila_perm_btn.addWidget(_btn("Quitar permiso", self._quitar_permiso_grupo_sel, danger=True))
        fila_perm_btn.addStretch()
        col_perm.addLayout(fila_perm_btn)
        self.tbl_permisos_grupo = _tabla(["Permiso"])
        self.tbl_permisos_grupo.cellClicked.connect(self._sel_permiso_grupo)
        col_perm.addWidget(self.tbl_permisos_grupo)
        cuerpo.addLayout(col_perm, 1)

        col_mie = QVBoxLayout()
        fila_mie = QHBoxLayout()
        self.cmb_usuario_grupo = _combo_buscable(self._opciones_usuarios_acl(), filas_visibles=5)
        self.cmb_usuario_grupo.setMinimumWidth(160)
        fila_mie.addWidget(QLabel("Usuario:")); fila_mie.addWidget(self.cmb_usuario_grupo)
        col_mie.addLayout(fila_mie)
        fila_mie_btn = QHBoxLayout()
        fila_mie_btn.addWidget(_btn("Añadir miembro", self._anadir_miembro_grupo, primary=True))
        fila_mie_btn.addWidget(_btn("Quitar miembro", self._quitar_miembro_grupo_sel, danger=True))
        fila_mie_btn.addStretch()
        col_mie.addLayout(fila_mie_btn)
        self.tbl_miembros_grupo = _tabla(["ID", "Usuario"])
        self.tbl_miembros_grupo.cellClicked.connect(self._sel_miembro_grupo)
        col_mie.addWidget(self.tbl_miembros_grupo)
        cuerpo.addLayout(col_mie, 1)
        lay.addLayout(cuerpo)

        self._grupos = []
        self._grupo_sel = None
        self._permisos_grupo = []
        self._permiso_grupo_sel = None
        self._miembros_grupo = []
        self._miembro_grupo_sel = None
        self._load_grupos()
        return w

    def _load_grupos(self):
        self._grupos = _R.listar_grupos(_empresa())
        self.tbl_grupos.setRowCount(len(self._grupos))
        for i, g in enumerate(self._grupos):
            for j, v in enumerate([g["id"], g["codigo"], g["nombre"]]):
                self.tbl_grupos.setItem(i, j, _it(v))
        self._grupo_sel = None
        self.tbl_permisos_grupo.setRowCount(0)
        self.tbl_miembros_grupo.setRowCount(0)

    def _sel_grupo(self, row, _c):
        try:
            self._grupo_sel = self._grupos[row]
        except (IndexError, AttributeError):
            self._grupo_sel = None
        self._load_permisos_grupo()
        self._load_miembros_grupo()

    def _load_permisos_grupo(self):
        self._permisos_grupo = (_R.permisos_de_grupo(self._grupo_sel["id"], _empresa())
                                if self._grupo_sel else [])
        self.tbl_permisos_grupo.setRowCount(len(self._permisos_grupo))
        for i, p in enumerate(self._permisos_grupo):
            self.tbl_permisos_grupo.setItem(i, 0, _it(p["codigo"]))
        self._permiso_grupo_sel = None

    def _sel_permiso_grupo(self, row, _c):
        try:
            self._permiso_grupo_sel = self._permisos_grupo[row]
        except (IndexError, AttributeError):
            self._permiso_grupo_sel = None

    def _load_miembros_grupo(self):
        self._miembros_grupo = (_R.miembros_de_grupo(self._grupo_sel["id"], _empresa())
                                if self._grupo_sel else [])
        self.tbl_miembros_grupo.setRowCount(len(self._miembros_grupo))
        for i, m in enumerate(self._miembros_grupo):
            self.tbl_miembros_grupo.setItem(i, 0, _it(m["id"]))
            self.tbl_miembros_grupo.setItem(i, 1, _it(m["nombre"]))
        self._miembro_grupo_sel = None

    def _sel_miembro_grupo(self, row, _c):
        try:
            self._miembro_grupo_sel = self._miembros_grupo[row]
        except (IndexError, AttributeError):
            self._miembro_grupo_sel = None

    def _nuevo_grupo(self):
        dlg = _NuevoGrupoDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        codigo, nombre = dlg.valores()
        if not codigo or not nombre:
            _info(self, "Grupos", "Código y nombre son obligatorios.")
            return
        from src.gui.mfa_gui import step_up_sesion
        if not step_up_sesion("permisos.cambiar", self):
            return
        gid = _R.crear_grupo(codigo, nombre, id_empresa=_empresa())
        if gid:
            self._load_grupos()
            _info(self, "Grupos", f"Grupo «{nombre}» creado correctamente.")
        else:
            _info(self, "Grupos", "No se pudo crear el grupo (revisa que el código no esté repetido).")

    def _eliminar_grupo(self):
        if not self._grupo_sel:
            _info(self, "Grupos", "Selecciona primero un grupo en la tabla.")
            return
        from assets.estilo_global import mostrar_confirmacion
        if not mostrar_confirmacion(self, "Eliminar grupo",
                                    f"¿Eliminar el grupo «{self._grupo_sel['nombre']}»? "
                                    "Se quitarán también sus permisos y sus miembros."):
            return
        from src.gui.mfa_gui import step_up_sesion
        if not step_up_sesion("permisos.cambiar", self):
            return
        if _R.eliminar_grupo(self._grupo_sel["id"], id_empresa=_empresa()):
            _info(self, "Grupos", "Grupo eliminado correctamente.")
            self._load_grupos()
        else:
            _info(self, "Grupos", "No se pudo eliminar el grupo.")

    def _anadir_permiso_grupo(self):
        if not self._grupo_sel:
            _info(self, "Grupos", "Selecciona primero un grupo en la tabla.")
            return
        codigo = self.cmb_permiso_grupo.currentData() or self.cmb_permiso_grupo.currentText().strip()
        if not codigo:
            _info(self, "Grupos", "Selecciona un permiso.")
            return
        from src.gui.mfa_gui import step_up_sesion
        if not step_up_sesion("permisos.cambiar", self):
            return
        if _R.asignar_permiso_grupo(self._grupo_sel["id"], codigo, id_empresa=_empresa()):
            self._load_permisos_grupo()
            _info(self, "Grupos", f"Permiso «{codigo}» añadido al grupo.")
        else:
            _info(self, "Grupos", "No se pudo añadir el permiso (¿código de permiso inválido?).")

    def _quitar_permiso_grupo_sel(self):
        if not self._grupo_sel:
            _info(self, "Grupos", "Selecciona primero un grupo en la tabla.")
            return
        if not self._permiso_grupo_sel:
            _info(self, "Grupos", "Selecciona un permiso en su tabla.")
            return
        from src.gui.mfa_gui import step_up_sesion
        if not step_up_sesion("permisos.cambiar", self):
            return
        codigo = self._permiso_grupo_sel["codigo"]
        if _R.quitar_permiso_grupo(self._grupo_sel["id"], codigo, id_empresa=_empresa()):
            self._load_permisos_grupo()
            _info(self, "Grupos", f"Permiso «{codigo}» quitado del grupo.")
        else:
            _info(self, "Grupos", "No se pudo quitar el permiso.")

    def _anadir_miembro_grupo(self):
        if not self._grupo_sel:
            _info(self, "Grupos", "Selecciona primero un grupo en la tabla.")
            return
        uid = self.cmb_usuario_grupo.currentData()
        if not uid:
            _info(self, "Grupos", "Selecciona un usuario.")
            return
        from src.gui.mfa_gui import step_up_sesion
        if not step_up_sesion("permisos.cambiar", self):
            return
        nombre_usuario = self.cmb_usuario_grupo.currentText()
        if _R.asignar_grupo_usuario(uid, self._grupo_sel["id"], id_empresa=_empresa()):
            self._load_miembros_grupo()
            _info(self, "Grupos", f"«{nombre_usuario}» añadido al grupo.")
        else:
            _info(self, "Grupos", "No se pudo añadir el usuario al grupo.")

    def _quitar_miembro_grupo_sel(self):
        if not self._grupo_sel:
            _info(self, "Grupos", "Selecciona primero un grupo en la tabla.")
            return
        if not self._miembro_grupo_sel:
            _info(self, "Grupos", "Selecciona un miembro en su tabla.")
            return
        from src.gui.mfa_gui import step_up_sesion
        if not step_up_sesion("permisos.cambiar", self):
            return
        if _R.desasignar_grupo_usuario(self._miembro_grupo_sel["id"], self._grupo_sel["id"],
                                       id_empresa=_empresa()):
            self._load_miembros_grupo()
            _info(self, "Grupos", "Miembro quitado del grupo.")
        else:
            _info(self, "Grupos", "No se pudo quitar el miembro.")

    # ── RGPD (derecho de acceso/portabilidad/olvido sobre datos de clientes) ────
    def _construir_tab_rgpd(self):
        w = QWidget(); w.setStyleSheet(f"background:{_BG};"); lay = QVBoxLayout(w)
        info = QLabel("Derechos RGPD sobre clientes: cada acción pide seleccionar el cliente "
                      "afectado. «Acceso/exportar» y «Portabilidad» generan un JSON con sus datos "
                      "personales; «Olvido» los anonimiza conservando los registros con valor fiscal.")
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{_DIM};font-size:12px;")
        lay.addWidget(info)
        fila = QHBoxLayout()
        fila.addWidget(_btn("Acceso / exportar", lambda: self._rgpd_ejecutar("acceso"), primary=True))
        fila.addWidget(_btn("Portabilidad", lambda: self._rgpd_ejecutar("portabilidad"), primary=True))
        fila.addWidget(_btn("Olvido", lambda: self._rgpd_ejecutar("olvido"), danger=True))
        fila.addStretch()
        fila.addWidget(_btn_cargando("🔄  Actualizar", self._load_rgpd, primary=True))
        lay.addLayout(fila)
        self.tbl_rgpd = _tabla(["ID", "Tipo", "Sujeto", "Estado", "Ruta/Resultado", "Solicitante", "Fecha"])
        lay.addWidget(self.tbl_rgpd)
        self._load_rgpd()
        return w

    def _rgpd_ejecutar(self, tipo):
        from src.gui.mfa_gui import step_up_sesion
        if not step_up_sesion("rgpd.ejecutar", self):
            return
        from src.gui.factura_window import _SelectorClienteDialog
        dlg = _SelectorClienteDialog(self, texto_boton="Seleccionar cliente")
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.cliente:
            return
        id_cliente = dlg.cliente.get("id")
        nombre = dlg.cliente.get("nombre") or str(id_cliente)
        from src.services.seguridad import rgpd as _rgpd
        fn = {"acceso": _rgpd.acceso, "portabilidad": _rgpd.portabilidad, "olvido": _rgpd.olvido}[tipo]
        r = fn(id_cliente, id_empresa=_empresa(), solicitante=self.usuario.get("nombre"))
        if r.get("ok"):
            if tipo == "olvido":
                _info(self, "RGPD", f"Solicitud de olvido resuelta para «{nombre}»: "
                                    f"{r.get('registros_anonimizados', 0)} registro(s) anonimizado(s).")
            else:
                _info(self, "RGPD", f"Exportación de «{nombre}» generada en:\n{r.get('ruta')}")
        else:
            _info(self, "RGPD", f"No se pudo completar la solicitud para «{nombre}».")
        self._load_rgpd()

    def _load_rgpd(self):
        from src.services.seguridad import rgpd as _rgpd
        filas = _rgpd.listar_solicitudes(id_empresa=_empresa())
        self.tbl_rgpd.setRowCount(len(filas))
        for i, s in enumerate(filas):
            sujeto = f"{s.get('sujeto_tipo')}:{s.get('sujeto_id') or s.get('sujeto_nif') or ''}"
            vals = [s.get("id"), s.get("tipo"), sujeto, s.get("estado"),
                    s.get("resultado_ruta") or "", s.get("solicitante") or "", s.get("creado_en")]
            for j, v in enumerate(vals):
                self.tbl_rgpd.setItem(i, j, _it(v))

    # ── Política de contraseñas (complejidad/caducidad/historial) ──────────────
    def _construir_tab_password_politica(self):
        w = QWidget(); w.setStyleSheet(f"background:{_BG};"); lay = QVBoxLayout(w)
        titulo = QLabel("Política de contraseñas")
        titulo.setStyleSheet(f"color:{_CIAN};font-size:16px;font-weight:bold;")
        lay.addWidget(titulo)
        desc = QLabel("Reglas de complejidad, caducidad e historial de no-reutilización — capa "
                      "ADICIONAL sobre la validación de PIN (4 dígitos) ya existente en Usuarios; "
                      "ambas se aplican al cambiar el PIN de un empleado.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color:{_DIM};font-size:12px;")
        lay.addWidget(desc)

        fila1 = QHBoxLayout()
        fila1.addWidget(QLabel("Longitud mínima:"))
        self.inp_pp_longitud = _inp("8"); self.inp_pp_longitud.setFixedWidth(60)
        fila1.addWidget(self.inp_pp_longitud)
        fila1.addWidget(QLabel("Días de caducidad (0 = sin caducidad):"))
        self.inp_pp_caducidad = _inp("0"); self.inp_pp_caducidad.setFixedWidth(60)
        fila1.addWidget(self.inp_pp_caducidad)
        fila1.addWidget(QLabel("Historial (no reutilizar últimas N):"))
        self.inp_pp_historial = _inp("3"); self.inp_pp_historial.setFixedWidth(60)
        fila1.addWidget(self.inp_pp_historial)
        fila1.addStretch()
        lay.addLayout(fila1)

        fila2 = QHBoxLayout()
        self.chk_pp_mayus = _chk("Requiere mayúscula")
        self.chk_pp_minus = _chk("Requiere minúscula")
        self.chk_pp_digito = _chk("Requiere dígito")
        self.chk_pp_simbolo = _chk("Requiere símbolo")
        self.chk_pp_activo = _chk("Política activa")
        for c in (self.chk_pp_mayus, self.chk_pp_minus, self.chk_pp_digito,
                 self.chk_pp_simbolo, self.chk_pp_activo):
            # `_chk` (compartido por toda la app) queda en 12px — aquí se sube 1pt SOLO para estas 5
            # etiquetas (indicadores de la política de contraseñas), en Segoe UI Bold explícito, sin
            # tocar el helper global ni el resto de checkboxes de la app.
            c.setStyleSheet(f"QCheckBox{{color:{_TEXT};font-family:'Segoe UI';font-size:13px;"
                            f"font-weight:bold;}}QCheckBox::indicator{{width:18px;height:18px;}}")
            fila2.addWidget(c)
        fila2.addStretch()
        lay.addLayout(fila2)

        fila_btn = QHBoxLayout()
        fila_btn.addWidget(_btn("Guardar política", self._guardar_password_politica, primary=True))
        fila_btn.addStretch()
        lay.addLayout(fila_btn)

        self.lbl_pp_feedback = QLabel("")
        self.lbl_pp_feedback.setWordWrap(True)
        self.lbl_pp_feedback.setStyleSheet(f"color:{_DIM};font-size:12px;")
        lay.addWidget(self.lbl_pp_feedback)
        lay.addStretch()

        self._load_password_politica()
        return w

    def _load_password_politica(self):
        from src.services.seguridad import password_politica as _pp
        pol = _pp.obtener_politica(id_empresa=_empresa())
        self.inp_pp_longitud.setText(str(pol.get("longitud_min", 8)))
        self.inp_pp_caducidad.setText(str(pol.get("dias_caducidad", 0)))
        self.inp_pp_historial.setText(str(pol.get("historial_n", 3)))
        self.chk_pp_mayus.setChecked(bool(pol.get("requiere_mayus")))
        self.chk_pp_minus.setChecked(bool(pol.get("requiere_minus")))
        self.chk_pp_digito.setChecked(bool(pol.get("requiere_digito")))
        self.chk_pp_simbolo.setChecked(bool(pol.get("requiere_simbolo")))
        self.chk_pp_activo.setChecked(bool(pol.get("activo")))

    def _guardar_password_politica(self):
        from src.gui.mfa_gui import step_up_sesion
        if not step_up_sesion("password_politica.gestionar", self):
            return
        try:
            longitud = int(self.inp_pp_longitud.text().strip() or 8)
            caducidad = int(self.inp_pp_caducidad.text().strip() or 0)
            historial = int(self.inp_pp_historial.text().strip() or 3)
        except ValueError:
            self.lbl_pp_feedback.setStyleSheet(f"color:{_ROJO};font-size:12px;")
            self.lbl_pp_feedback.setText("Longitud mínima, caducidad e historial deben ser números enteros.")
            return
        from src.services.seguridad import password_politica as _pp
        r = _pp.guardar_politica(
            id_empresa=_empresa(),
            longitud_min=longitud,
            requiere_mayus=int(self.chk_pp_mayus.isChecked()),
            requiere_minus=int(self.chk_pp_minus.isChecked()),
            requiere_digito=int(self.chk_pp_digito.isChecked()),
            requiere_simbolo=int(self.chk_pp_simbolo.isChecked()),
            dias_caducidad=caducidad,
            historial_n=historial,
            activo=int(self.chk_pp_activo.isChecked()),
        )
        if r.get("ok"):
            self.lbl_pp_feedback.setStyleSheet(f"color:{_DIM};font-size:12px;")
            self.lbl_pp_feedback.setText("Política guardada correctamente.")
        else:
            self.lbl_pp_feedback.setStyleSheet(f"color:{_ROJO};font-size:12px;")
            self.lbl_pp_feedback.setText(f"No se pudo guardar: {r.get('motivo')}")

    @staticmethod
    def _ajustar_ancho_combo(combo, etiquetas):
        """Ensancha `combo` (creado con `_combo`, que no fija un ancho propio y deja el cálculo
        de `sizeHint` al estilo Qt) lo justo para que la etiqueta más larga de `etiquetas` quepa
        entera sin recortarse. Mide con `QFontMetrics` a la fuente real con la que se pinta el
        texto — 12px (font-size del QSS de `_combo`) y **negrita**, porque el filtro global de
        estilos (`aplicar_estilo_widget` → `_apply_font`) pone en bold TODOS los widgets,
        incluidos los combos, de forma diferida (`QTimer.singleShot`) tras construirse — si el
        ancho se calculase en peso normal, el `sizeHint` de Qt puede quedarse corto una vez el
        texto pasa a negrita (más ancho), justo el síntoma reportado (texto recortado con "…")."""
        from PyQt6.QtGui import QFont, QFontMetrics
        fuente = QFont("Segoe UI")
        fuente.setPixelSize(12)
        fuente.setWeight(QFont.Weight.Bold)
        fm = QFontMetrics(fuente)
        ancho_texto = max((fm.horizontalAdvance(etq) for etq in etiquetas), default=0)
        # padding horizontal (10px * 2, del QSS de `_combo`) + borde (2px * 2) + flecha del
        # desplegable (22px) + margen de seguridad generoso para que no quede al límite del recorte.
        ancho_min = ancho_texto + 20 + 4 + 22 + 24
        combo.setMinimumWidth(ancho_min)

    # ── Incidentes de seguridad (ciclo abierto→investigando→mitigado→cerrado) ──
    def _construir_tab_incidentes(self):
        w = QWidget(); w.setStyleSheet(f"background:{_BG};"); lay = QVBoxLayout(w)
        from src.services.seguridad import incidentes as _inc
        fila = QHBoxLayout()
        fila.addWidget(QLabel("Filtrar por estado:"))
        opciones_estado = [("Todos", None)] + [(e.capitalize(), e) for e in _inc.ESTADOS]
        self.cmb_incidentes_estado = _combo(opciones_estado)
        self.cmb_incidentes_estado.currentIndexChanged.connect(self._load_incidentes)
        fila.addWidget(self.cmb_incidentes_estado)
        fila.addStretch()
        fila.addWidget(_btn_cargando("🔄  Actualizar", self._load_incidentes, primary=True))
        lay.addLayout(fila)
        self.tbl_incidentes = _tabla(["ID", "Tipo", "Severidad", "Estado", "IP origen", "Detalle", "Creado"])
        self.tbl_incidentes.cellClicked.connect(self._sel_incidente)
        lay.addWidget(self.tbl_incidentes)
        fila_acc = QHBoxLayout()
        fila_acc.addWidget(QLabel("Cambiar estado a:"))
        opciones_nuevo_estado = [(e.capitalize(), e) for e in _inc.ESTADOS]
        self.cmb_incidentes_nuevo_estado = _combo(opciones_nuevo_estado)
        self._ajustar_ancho_combo(self.cmb_incidentes_nuevo_estado,
                                   [etq for etq, _v in opciones_nuevo_estado])
        fila_acc.addWidget(self.cmb_incidentes_nuevo_estado)
        fila_acc.addWidget(_btn("Aplicar", self._cambiar_estado_incidente, primary=True))
        fila_acc.addStretch()
        lay.addLayout(fila_acc)
        self._incidentes_filas = []
        self._incidente_sel = None
        self._load_incidentes()
        return w

    def _load_incidentes(self):
        from src.services.seguridad import incidentes as _inc
        estado = self.cmb_incidentes_estado.currentData()
        filas = _inc.listar(estado=estado, id_empresa=_empresa())
        self.tbl_incidentes.setRowCount(len(filas))
        for i, r in enumerate(filas):
            vals = [r.get("id"), r.get("tipo"), r.get("severidad"), r.get("estado"),
                    r.get("ip_origen") or "", r.get("detalle") or "", r.get("creado_en")]
            for j, v in enumerate(vals):
                self.tbl_incidentes.setItem(i, j, _it(v))
        self._incidentes_filas = filas
        self._incidente_sel = None

    def _sel_incidente(self, row, _c):
        try:
            self._incidente_sel = self._incidentes_filas[row]
        except (IndexError, AttributeError):
            self._incidente_sel = None

    def _cambiar_estado_incidente(self):
        if not self._incidente_sel:
            _info(self, "Incidentes", "Selecciona primero un incidente en la tabla.")
            return
        nuevo = self.cmb_incidentes_nuevo_estado.currentData()
        from src.gui.mfa_gui import step_up_sesion
        if not step_up_sesion("incidentes.gestionar", self):
            return
        from src.services.seguridad import incidentes as _inc
        try:
            ok = _inc.cambiar_estado(self._incidente_sel["id"], nuevo,
                                     usuario=self.usuario.get("nombre"), detalle=None)
        except ValueError as e:
            _info(self, "Incidentes", str(e))
            return
        if ok:
            iid = self._incidente_sel["id"]
            self._load_incidentes()
            _info(self, "Incidentes", f"Incidente #{iid} → «{nuevo}».")
        else:
            _info(self, "Incidentes", "No se pudo cambiar el estado del incidente.")

    # ── Sesiones activas (ver/cerrar sesiones de otros usuarios) ────────────────
    def _construir_tab_sesiones(self):
        w = QWidget(); w.setStyleSheet(f"background:{_BG};"); lay = QVBoxLayout(w)
        fila = QHBoxLayout()
        fila.addWidget(QLabel("Usuario:"))
        self.cmb_usuario_sesiones = _combo_buscable(self._opciones_usuarios_acl(), filas_visibles=5)
        self.cmb_usuario_sesiones.setMinimumWidth(200)
        self.cmb_usuario_sesiones.currentIndexChanged.connect(self._load_sesiones)
        fila.addWidget(self.cmb_usuario_sesiones)
        fila.addStretch()
        fila.addWidget(_btn_cargando("🔄  Actualizar", self._load_sesiones, primary=True))
        lay.addLayout(fila)
        self.tbl_sesiones = _tabla(["JTI", "Empresa", "Creada", "Expira"])
        self.tbl_sesiones.cellClicked.connect(self._sel_sesion)
        lay.addWidget(self.tbl_sesiones)
        fila_acc = QHBoxLayout()
        fila_acc.addWidget(_btn("Cerrar sesión", self._cerrar_sesion_sel, danger=True))
        fila_acc.addWidget(_btn("Revocar todas", self._revocar_todas_sesiones, danger=True))
        fila_acc.addStretch()
        lay.addLayout(fila_acc)
        self._sesiones_filas = []
        self._sesion_sel = None
        self._load_sesiones()
        return w

    def _load_sesiones(self):
        uid = self.cmb_usuario_sesiones.currentData()
        self.tbl_sesiones.setRowCount(0)
        self._sesiones_filas = []
        self._sesion_sel = None
        if not uid:
            return
        from src.services.seguridad import sesiones_admin as _sa
        filas = _sa.listar_sesiones(uid)
        self.tbl_sesiones.setRowCount(len(filas))
        for i, s in enumerate(filas):
            # `listar_sesiones` devuelve la columna real `emitido` (fecha de emisión de la sesión);
            # se admite también `creada` por si el fallback `SELECT *` de esa función alguna vez
            # aplica sobre un esquema distinto.
            creada = s.get("creada") if s.get("creada") is not None else s.get("emitido")
            vals = [s.get("jti"), s.get("id_empresa"), creada, s.get("expira")]
            for j, v in enumerate(vals):
                self.tbl_sesiones.setItem(i, j, _it(v))
        self._sesiones_filas = filas

    def _sel_sesion(self, row, _c):
        try:
            self._sesion_sel = self._sesiones_filas[row]
        except (IndexError, AttributeError):
            self._sesion_sel = None

    def _cerrar_sesion_sel(self):
        if not self._sesion_sel:
            _info(self, "Sesiones activas", "Selecciona primero una sesión en la tabla.")
            return
        from src.gui.mfa_gui import step_up_sesion
        if not step_up_sesion("sesiones.admin", self):
            return
        from src.services.seguridad import sesiones_admin as _sa
        if _sa.cerrar_sesion(self._sesion_sel["jti"]):
            self._load_sesiones()
            _info(self, "Sesiones activas", "Sesión cerrada correctamente.")
        else:
            _info(self, "Sesiones activas", "No se pudo cerrar la sesión.")

    def _revocar_todas_sesiones(self):
        uid = self.cmb_usuario_sesiones.currentData()
        if not uid:
            _info(self, "Sesiones activas", "Selecciona un usuario.")
            return
        from src.gui.mfa_gui import step_up_sesion
        if not step_up_sesion("sesiones.admin", self):
            return
        from src.services.seguridad import sesiones_admin as _sa
        if _sa.revocar_todas(uid):
            self._load_sesiones()
            _info(self, "Sesiones activas", "Todas las sesiones del usuario han sido revocadas.")
        else:
            _info(self, "Sesiones activas", "No se pudo revocar las sesiones.")

    def refrescar(self):
        # Roles/ACL/Grupos solo tienen sus tablas si el usuario ya visitó esa pestaña (lazy loading).
        if hasattr(self, "tbl_usuarios_perm"):
            try:
                self._load_usuarios_perm()
            except Exception as e:
                logger.debug("refrescar usuarios/permisos: %s", e)
        if hasattr(self, "tbl_acl"):
            try:
                self._load_acl()
            except Exception as e:
                logger.debug("refrescar acl: %s", e)
        if hasattr(self, "tbl_grupos"):
            try:
                self._load_grupos()
            except Exception as e:
                logger.debug("refrescar grupos: %s", e)
        if hasattr(self, "tbl_rgpd"):
            try:
                self._load_rgpd()
            except Exception as e:
                logger.debug("refrescar rgpd: %s", e)
        if hasattr(self, "inp_pp_longitud"):
            try:
                self._load_password_politica()
            except Exception as e:
                logger.debug("refrescar politica de contraseñas: %s", e)
        if hasattr(self, "tbl_incidentes"):
            try:
                self._load_incidentes()
            except Exception as e:
                logger.debug("refrescar incidentes: %s", e)
        if hasattr(self, "tbl_sesiones"):
            try:
                self._load_sesiones()
            except Exception as e:
                logger.debug("refrescar sesiones: %s", e)
