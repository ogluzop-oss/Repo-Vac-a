"""
SaaS — Administración de tenants + Portal del cliente (FASE SAAS-H / SAAS-N).

Panel de plataforma (SUPERADMIN): empresas, plan, estado, métricas SaaS (MRR/ARR/churn).
Portal del cliente: plan actual, consumo, suscripción. Estilo dark+cian.
"""

import logging

from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QMessageBox, QTableWidgetItem, QTabWidget,
                             QVBoxLayout, QWidget)

from src.gui.catalogo_gestion import _BG, _CIAN, _DIM, _btn, _btn_x, _combo, _tabla
from src.services.saas import licensing as _L, metricas as _M, planes as _P, suscripciones as _S

logger = logging.getLogger("saas.gui")


def _it(v):
    return QTableWidgetItem("" if v is None else str(v))


def _empresa():
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return EMPRESA_DEFAULT_ID


def _es_superadmin():
    try:
        from src.db.usuario import sesion_global
        return str((getattr(sesion_global, "usuario_actual", None) or {}).get("perfil", "")).upper() == "SUPERADMIN"
    except Exception:
        return False


class SaaSAdminWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background:{_BG};")
        try:
            _P.sincronizar_planes()
        except Exception:
            pass
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("SaaS · Administración y Portal")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        # "Actualizar" se reubica en la esquina superior derecha de la tabla (ver _tab_portal).
        if callback_vuelta:
            cab.addWidget(_btn_x(self._volver))
        root.addLayout(cab)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)
        self._tab_portal()
        if _es_superadmin():
            self._tab_tenants()
            self._tab_crm_saas()   # funnel de venta del PROPIO Smart Manager (movido desde CRM Comercial)

    # ── Portal cliente (empresa activa) ───────────────────────────────────────
    def _tab_portal(self):
        w = QWidget(); w.setStyleSheet(f"background:{_BG};"); lay = QVBoxLayout(w)
        self.lbl_plan = QLabel(""); self.lbl_plan.setStyleSheet(f"color:{_CIAN};font-size:15px;")
        lay.addWidget(self.lbl_plan)
        bar = QHBoxLayout()
        self.cmb_plan = _combo([(c, c) for c in _P.PLANES])
        self.cmb_plan.setMinimumWidth(150)   # evita texto cortado en el desplegable
        bar.addWidget(QLabel("Plan:")); bar.addWidget(self.cmb_plan)
        bar.addWidget(_btn("Cambiar plan", self._cambiar_plan, primary=True))
        bar.addWidget(_btn("Renovar", self._renovar))
        bar.addWidget(_btn("Descargar última factura", self._descargar_factura))
        bar.addStretch()
        # "Actualizar" en la esquina superior derecha, justo encima de la tabla.
        bar.addWidget(_btn("🔄 Actualizar", self.refrescar))
        lay.addLayout(bar)
        self.tbl_consumo = _tabla(["Recurso", "Consumo"])
        lay.addWidget(self.tbl_consumo)
        self.tabs.addTab(w, "Mi plan")
        self._load_portal()

    def _load_portal(self):
        lic = _L.licencia_activa(_empresa())
        sus = _S.estado(_empresa())
        self.lbl_plan.setText(f"Plan: {lic['codigo_plan'] if lic else '(sin licencia)'} · "
                              f"Estado: {lic['estado'] if lic else 'sin_licencia'}"
                              + (f" · Suscripción: {sus['estado']}" if sus else ""))
        cons = _M.consumo_empresa(_empresa())
        self.tbl_consumo.setRowCount(len(cons))
        for i, (k, v) in enumerate(cons.items()):
            self.tbl_consumo.setItem(i, 0, _it(k)); self.tbl_consumo.setItem(i, 1, _it(v))

    # ── CRM SaaS (funnel de venta de Smart Manager) — nivel plataforma/operador ────────────────
    def _tab_crm_saas(self):
        """Embudo comercial del PROPIO Smart Manager (lead→demo→prueba→cliente). Es una función del
        OPERADOR/vendedor del software (captación de empresas suscriptoras), no del cliente-suscriptor que
        gestiona SUS clientes en CRM Comercial → por eso vive aquí, junto a la administración SaaS."""
        w = QWidget(); w.setStyleSheet(f"background:{_BG};"); lay = QVBoxLayout(w)
        bar = QHBoxLayout()
        lbl = QLabel("Embudo de venta de Smart Manager (lead → demo → prueba → cliente).")
        lbl.setStyleSheet(f"color:{_DIM};")
        bar.addWidget(lbl); bar.addStretch()
        bar.addWidget(_btn("🔄  Actualizar", self._load_crm_saas))
        lay.addLayout(bar)
        self.tbl_crm_saas = _tabla(["Fase", "Nº"])
        lay.addWidget(self.tbl_crm_saas)
        self.tabs.addTab(w, "CRM SaaS (funnel)")
        self._load_crm_saas()

    def _load_crm_saas(self):
        try:
            from src.services.crm import crm_saas
            emb = crm_saas.embudo()
            self.tbl_crm_saas.setRowCount(len(emb))
            for i, (f, n) in enumerate(emb.items()):
                self.tbl_crm_saas.setItem(i, 0, _it(f)); self.tbl_crm_saas.setItem(i, 1, _it(n))
        except Exception as e:
            logger.debug("crm_saas embudo: %s", e)

    def _cambiar_plan(self):
        from src.gui.mfa_gui import step_up_sesion
        if not step_up_sesion("saas.admin", self):
            return
        try:
            _S.cambiar_plan(_empresa(), self.cmb_plan.currentData())
            self._load_portal()
        except Exception as e:
            QMessageBox.warning(self, "SaaS", str(e))

    def _renovar(self):
        from src.gui.mfa_gui import step_up_sesion
        if not step_up_sesion("saas.admin", self):
            return
        try:
            _S.renovar(_empresa())
            self._load_portal()
        except Exception as e:
            QMessageBox.warning(self, "SaaS", str(e))

    def _descargar_factura(self):
        try:
            from src.services.saas import facturas as _F
            fs = _F.listar_facturas(_empresa())
            if not fs:
                QMessageBox.information(self, "SaaS", "No hay facturas."); return
            ruta = _F.factura_pdf(fs[0]["id"], id_empresa=_empresa())
            QMessageBox.information(self, "SaaS", f"Factura generada: {ruta}" if ruta else "No disponible (falta reportlab).")
        except Exception as e:
            QMessageBox.warning(self, "SaaS", str(e))

    # ── Panel de tenants (SUPERADMIN) ─────────────────────────────────────────
    def _tab_tenants(self):
        w = QWidget(); w.setStyleSheet(f"background:{_BG};"); lay = QVBoxLayout(w)
        self.lbl_metrics = QLabel(""); self.lbl_metrics.setStyleSheet(f"color:{_CIAN};font-size:14px;")
        lay.addWidget(self.lbl_metrics)
        self.tbl_tenants = _tabla(["Empresa", "Plan", "Estado", "Próx. cobro"])
        lay.addWidget(self.tbl_tenants)
        self.tabs.addTab(w, "Tenants (plataforma)")
        self._load_tenants()

    def _load_tenants(self):
        try:
            m = _M.resumen()
            self.lbl_metrics.setText(
                f"Empresas activas: {m['empresas_activas']} · Usuarios: {m['usuarios_activos']} · "
                f"MRR: {m['mrr']:.2f} € · ARR: {m['arr']:.2f} € · Churn: {m['churn_pct']}%")
            from src.db.conexion import obtener_conexion
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("SELECT id_empresa, codigo_plan, estado, proximo_cobro FROM empresa_licencia "
                            "ORDER BY fecha_alta DESC LIMIT 500")
                filas = [r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))
                         for r in cur.fetchall()]
            self.tbl_tenants.setRowCount(len(filas))
            for i, d in enumerate(filas):
                for j, v in enumerate([d["id_empresa"], d["codigo_plan"], d["estado"], d.get("proximo_cobro")]):
                    self.tbl_tenants.setItem(i, j, _it(v))
        except Exception as e:
            logger.error("load_tenants: %s", e)

    def refrescar(self):
        self._load_portal()
        if hasattr(self, "tbl_tenants"):
            self._load_tenants()
