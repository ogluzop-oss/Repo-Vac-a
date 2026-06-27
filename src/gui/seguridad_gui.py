"""
Seguridad · administración RBAC / ACL (FASE 11).

Pantalla NUEVA (no modifica las existentes). Permite gestionar roles, sus permisos, las
asignaciones de rol a usuario, grupos y ACL — sin tocar código. Estilo coherente (dark+cian);
acotada a la empresa activa. Sincroniza el catálogo y los roles del sistema al abrir.
"""

import logging

from PyQt6.QtWidgets import (QHBoxLayout, QInputDialog, QLabel, QMessageBox, QTableWidgetItem,
                             QTabWidget, QVBoxLayout, QWidget)

from src.db import rbac as _R
from src.gui.catalogo_gestion import _BG, _CIAN, _DIM, _btn, _combo, _inp, _tabla
from src.services.seguridad import catalogo as _cat

logger = logging.getLogger("seguridad.gui")


def _it(v):
    return QTableWidgetItem("" if v is None else str(v))


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
        cab.addWidget(_btn("Actualizar", self.refrescar))
        if callback_vuelta:
            cab.addWidget(_btn("Volver", self._volver))
        root.addLayout(cab)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs)
        self._tab_roles()
        self._tab_asignaciones()
        self._tab_acl()

    # ── Roles + permisos ──────────────────────────────────────────────────────
    def _tab_roles(self):
        w = QWidget(); w.setStyleSheet(f"background:{_BG};"); lay = QVBoxLayout(w)
        bar = QHBoxLayout()
        bar.addWidget(_btn("Nuevo rol", self._nuevo_rol, primary=True)); bar.addStretch()
        lay.addLayout(bar)
        cuerpo = QHBoxLayout()
        self.tbl_roles = _tabla(["ID", "Código", "Nombre", "Sistema"])
        self.tbl_roles.cellClicked.connect(self._sel_rol)
        cuerpo.addWidget(self.tbl_roles, 1)
        der = QVBoxLayout()
        f = QHBoxLayout()
        self.cmb_permiso = _combo([(p, p) for p in _cat.CATALOGO])
        f.addWidget(QLabel("Permiso:")); f.addWidget(self.cmb_permiso)
        f.addWidget(_btn("Conceder", self._conceder)); f.addWidget(_btn("Quitar", self._quitar))
        der.addLayout(f)
        self.tbl_permisos = _tabla(["Permiso del rol"])
        der.addWidget(self.tbl_permisos)
        cw = QWidget(); cw.setLayout(der); cuerpo.addWidget(cw, 1)
        lay.addLayout(cuerpo)
        self.tabs.addTab(w, "Roles")
        self._sel_rol_id = None
        self._load_roles()

    def _load_roles(self):
        filas = _R.listar_roles(_empresa())
        self.tbl_roles.setRowCount(len(filas))
        for i, r in enumerate(filas):
            for j, v in enumerate([r["id"], r["codigo"], r["nombre"], r.get("es_sistema")]):
                self.tbl_roles.setItem(i, j, _it(v))

    def _sel_rol(self, row, _c):
        try:
            self._sel_rol_id = int(self.tbl_roles.item(row, 0).text())
            self._load_permisos()
        except Exception:
            self._sel_rol_id = None

    def _load_permisos(self):
        if not self._sel_rol_id:
            return
        perms = _R.permisos_de_rol(self._sel_rol_id)
        self.tbl_permisos.setRowCount(len(perms))
        for i, p in enumerate(perms):
            self.tbl_permisos.setItem(i, 0, _it(p))

    def _nuevo_rol(self):
        cod, ok = QInputDialog.getText(self, "Nuevo rol", "Código:")
        if not ok or not cod:
            return
        nom, ok = QInputDialog.getText(self, "Nuevo rol", "Nombre:")
        if not ok:
            return
        _R.crear_rol(cod.strip().upper(), nom or cod, id_empresa=_empresa())
        self._load_roles()

    def _conceder(self):
        if self._sel_rol_id:
            _R.asignar_permiso_rol(self._sel_rol_id, self.cmb_permiso.currentData(), id_empresa=_empresa())
            self._load_permisos()

    def _quitar(self):
        if self._sel_rol_id:
            _R.quitar_permiso_rol(self._sel_rol_id, self.cmb_permiso.currentData(), id_empresa=_empresa())
            self._load_permisos()

    # ── Asignación rol ↔ usuario ──────────────────────────────────────────────
    def _tab_asignaciones(self):
        w = QWidget(); w.setStyleSheet(f"background:{_BG};"); lay = QVBoxLayout(w)
        f = QHBoxLayout()
        self.in_uid = _inp("ID usuario"); self.in_uid.setFixedWidth(110)
        self.cmb_rol = _combo([(r["codigo"], r["id"]) for r in _R.listar_roles(_empresa())])
        f.addWidget(QLabel("Usuario:")); f.addWidget(self.in_uid)
        f.addWidget(QLabel("Rol:")); f.addWidget(self.cmb_rol)
        f.addWidget(_btn("Asignar", self._asignar, primary=True))
        f.addWidget(_btn("Quitar", self._desasignar)); f.addStretch()
        lay.addLayout(f)
        self.tbl_asig = _tabla(["Rol ID", "Código", "Nombre"])
        lay.addWidget(self.tbl_asig)
        self.tabs.addTab(w, "Asignaciones")

    def _asignar(self):
        try:
            uid = int(self.in_uid.text() or 0)
        except ValueError:
            return
        _R.asignar_rol_usuario(uid, self.cmb_rol.currentData(), id_empresa=_empresa())
        self._load_asig(uid)

    def _desasignar(self):
        try:
            uid = int(self.in_uid.text() or 0)
        except ValueError:
            return
        _R.quitar_rol_usuario(uid, self.cmb_rol.currentData(), id_empresa=_empresa())
        self._load_asig(uid)

    def _load_asig(self, uid):
        roles = _R.roles_de_usuario(uid, _empresa())
        self.tbl_asig.setRowCount(len(roles))
        for i, r in enumerate(roles):
            for j, v in enumerate([r["id"], r["codigo"], r["nombre"]]):
                self.tbl_asig.setItem(i, j, _it(v))

    # ── ACL ───────────────────────────────────────────────────────────────────
    def _tab_acl(self):
        w = QWidget(); w.setStyleSheet(f"background:{_BG};"); lay = QVBoxLayout(w)
        self.tbl_acl = _tabla(["Recurso", "ID", "Sujeto", "Sujeto ID", "Acción", "Permitido"])
        lay.addWidget(self.tbl_acl)
        self.tabs.addTab(w, "ACL")
        self._load_acl()

    def _load_acl(self):
        filas = _R.listar_acl(id_empresa=_empresa())
        self.tbl_acl.setRowCount(len(filas))
        for i, a in enumerate(filas):
            vals = [a["recurso_tipo"], a.get("recurso_id"), a["sujeto_tipo"], a["sujeto_id"],
                    a["accion"], a["permitido"]]
            for j, v in enumerate(vals):
                self.tbl_acl.setItem(i, j, _it(v))

    def refrescar(self):
        for fn in (self._load_roles, self._load_acl):
            try:
                fn()
            except Exception as e:
                logger.debug("refrescar: %s", e)
