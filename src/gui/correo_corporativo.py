"""
Sección de administración del CORREO CORPORATIVO (multi-tenant / licenciable).

Lista los buzones de la empresa activa con su proveedor, estado, tienda, licencia
y última sincronización; permite dar de alta buzones (con su licencia), conectar
OAuth 2.0 (Google), enviar un correo de prueba y eliminar (revoca tokens).

Identidad: empresa → tienda → correo. Solo ADMINISTRADOR / GERENTE.
"""
from __future__ import annotations

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.db import correo as correo_db
from src.db.conexion import obtener_conexion
from src.db.usuario import sesion_global
from src.gui.gestion_usuarios import _NeonComboBox
from src.services import correo as correo_svc
from src.utils.i18n import tr

try:
    from assets.estilo_global import mostrar_confirmacion, mostrar_mensaje
except Exception:  # pragma: no cover
    mostrar_mensaje = mostrar_confirmacion = None

logger = logging.getLogger("gui.correo")

_BG = "#0E1117"
_BG2 = "#161B22"
_CIAN = "#00FFC6"
_BORDE = "#30363D"
_TEXT = "#E6EDF3"
_DIM = "#8B949E"


def _listar_tiendas() -> list[dict]:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, nombre, codigo_tienda FROM tiendas WHERE COALESCE(activo,1)=1 ORDER BY id")
            filas = cur.fetchall()
        out = []
        for f in filas:
            if isinstance(f, dict):
                out.append(f)
            else:
                out.append({"id": f[0], "nombre": f[1], "codigo_tienda": f[2]})
        return out
    except Exception as e:
        logger.error("Error listar tiendas: %s", e)
        return []


class _NuevoCorreoDialog(QDialog):
    """Alta de un buzón corporativo + su licencia."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resultado = None
        self._build()

    def _build(self):
        card = QFrame(self)
        card.setStyleSheet(f"QFrame{{background:{_BG};border:2px solid {_CIAN};border-radius:18px;}}")
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.addWidget(card)
        ly = QVBoxLayout(card); ly.setContentsMargins(26, 22, 26, 22); ly.setSpacing(12)

        t = QLabel("✉️  " + tr("correo.nuevo_titulo", default="NUEVO CORREO CORPORATIVO"))
        t.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:15px;background:transparent;border:none;")
        ly.addWidget(t)

        def _lbl(txt):
            x = QLabel(txt); x.setStyleSheet(f"color:{_DIM};font-family:'Segoe UI';font-weight:900;font-size:11px;background:transparent;border:none;")
            return x

        self.inp_dir = QLineEdit(); self.inp_dir.setPlaceholderText("tienda001@empresa.com")
        self.inp_dir.setFixedHeight(38)
        ly.addWidget(_lbl(tr("correo.col_direccion", default="DIRECCIÓN DE CORREO")))
        ly.addWidget(self.inp_dir)

        fila = QHBoxLayout(); fila.setSpacing(12)
        col1 = QVBoxLayout(); col1.addWidget(_lbl(tr("correo.col_proveedor", default="PROVEEDOR")))
        self.cb_prov = _NeonComboBox(); self.cb_prov.setFixedHeight(38)
        self.cb_prov.setCursor(Qt.CursorShape.PointingHandCursor)
        for p in correo_db.PROVEEDORES:
            self.cb_prov.addItem(p.capitalize(), p)
        col1.addWidget(self.cb_prov); fila.addLayout(col1)

        col2 = QVBoxLayout(); col2.addWidget(_lbl(tr("correo.col_tipo", default="TIPO")))
        self.cb_tipo = _NeonComboBox(); self.cb_tipo.setFixedHeight(38)
        self.cb_tipo.setCursor(Qt.CursorShape.PointingHandCursor)
        for t_ in correo_db.TIPOS_CORREO:
            self.cb_tipo.addItem(t_.capitalize(), t_)
        col2.addWidget(self.cb_tipo); fila.addLayout(col2)
        ly.addLayout(fila)

        fila2 = QHBoxLayout(); fila2.setSpacing(12)
        col3 = QVBoxLayout(); col3.addWidget(_lbl(tr("correo.col_tienda", default="TIENDA")))
        self.cb_tienda = _NeonComboBox(); self.cb_tienda.setFixedHeight(38)
        self.cb_tienda.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cb_tienda.addItem(tr("correo.sin_tienda", default="— Empresa (sin tienda) —"), None)
        for t_ in _listar_tiendas():
            self.cb_tienda.addItem(f"{t_.get('codigo_tienda') or ''}  {t_['nombre']}", t_["id"])
        col3.addWidget(self.cb_tienda); fila2.addLayout(col3)

        col4 = QVBoxLayout(); col4.addWidget(_lbl(tr("correo.col_licencia", default="LICENCIA")))
        self.cb_lic = _NeonComboBox(); self.cb_lic.setFixedHeight(38)
        self.cb_lic.setCursor(Qt.CursorShape.PointingHandCursor)
        for lt in correo_db.TIPOS_LICENCIA:
            self.cb_lic.addItem(lt.replace("correo_", "").capitalize(), lt)
        col4.addWidget(self.cb_lic); fila2.addLayout(col4)
        ly.addLayout(fila2)

        botones = QHBoxLayout(); botones.addStretch()
        bc = QPushButton(tr("correo.cancelar", default="CANCELAR")); bc.setFixedSize(130, 40)
        bc.setCursor(Qt.CursorShape.PointingHandCursor)
        bc.setStyleSheet(f"QPushButton{{background:{_BG};color:#F85149;border:2px solid #F85149;border-radius:10px;font-weight:900;}}QPushButton:hover{{background:#F85149;color:{_BG};}}")
        bc.clicked.connect(self.reject)
        bk = QPushButton("✔  " + tr("correo.crear", default="CREAR")); bk.setFixedSize(180, 40)
        bk.setCursor(Qt.CursorShape.PointingHandCursor)
        bk.setStyleSheet(f"QPushButton{{background:{_BG};color:{_CIAN};border:2px solid {_CIAN};border-radius:10px;font-weight:900;}}QPushButton:hover{{background:{_CIAN};color:{_BG};}}")
        bk.clicked.connect(self._aceptar)
        botones.addWidget(bc); botones.addWidget(bk)
        ly.addLayout(botones)
        self.setFixedWidth(560)

    def _aceptar(self):
        direccion = self.inp_dir.text().strip()
        if "@" not in direccion or "." not in direccion:
            if mostrar_mensaje:
                mostrar_mensaje(self, tr("correo.error_titulo", default="Datos incompletos"),
                                tr("correo.error_direccion", default="Introduce una dirección de correo válida."), "warning")
            return
        self.resultado = {
            "direccion": direccion,
            "proveedor": self.cb_prov.currentData(),
            "tipo": self.cb_tipo.currentData(),
            "id_tienda": self.cb_tienda.currentData(),
            "tipo_licencia": self.cb_lic.currentData(),
        }
        self.accept()


class EnviarDocumentoDialog(QDialog):
    """Diálogo reutilizable: enviar un documento generado (PDF, etc.) desde un
    buzón corporativo de la empresa. Lo usan los módulos que generan documentos
    (albaranes, facturas, nóminas, informes...) para 'enviar desde el correo de
    la tienda'."""

    def __init__(self, ruta_documento: str, asunto: str = "", destinatario: str = "", parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._ruta = ruta_documento
        self._buzones = [c for c in correo_db.listar_correos() if c.get("estado") == "activo"]
        self._build(asunto, destinatario)

    def _build(self, asunto, destinatario):
        import os
        card = QFrame(self)
        card.setStyleSheet(f"QFrame{{background:{_BG};border:2px solid {_CIAN};border-radius:18px;}}")
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.addWidget(card)
        ly = QVBoxLayout(card); ly.setContentsMargins(26, 22, 26, 22); ly.setSpacing(10)

        t = QLabel("📤  " + tr("correo.env_titulo", default="ENVIAR DOCUMENTO POR CORREO"))
        t.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:15px;background:transparent;border:none;")
        ly.addWidget(t)

        def _lbl(x):
            q = QLabel(x); q.setStyleSheet(f"color:{_DIM};font-family:'Segoe UI';font-weight:900;font-size:11px;background:transparent;border:none;")
            return q

        adj = QLabel("📎  " + os.path.basename(self._ruta or ""))
        adj.setStyleSheet(f"color:{_TEXT};font-family:'Segoe UI';font-size:12px;background:{_BG2};border:1px solid {_BORDE};border-radius:8px;padding:8px 10px;")
        ly.addWidget(_lbl(tr("correo.env_adjunto", default="DOCUMENTO ADJUNTO")))
        ly.addWidget(adj)

        ly.addWidget(_lbl(tr("correo.env_buzon", default="ENVIAR DESDE (BUZÓN)")))
        self.cb_buzon = _NeonComboBox(); self.cb_buzon.setFixedHeight(38)
        self.cb_buzon.setCursor(Qt.CursorShape.PointingHandCursor)
        for b in self._buzones:
            etq = b["direccion"] + (f"  ·  {b.get('tienda_nombre')}" if b.get("tienda_nombre") else "")
            self.cb_buzon.addItem(etq, b["id_correo"])
        ly.addWidget(self.cb_buzon)

        ly.addWidget(_lbl(tr("correo.env_destinatario", default="DESTINATARIO")))
        self.inp_dest = QLineEdit(destinatario); self.inp_dest.setFixedHeight(38)
        self.inp_dest.setPlaceholderText("destinatario@ejemplo.com")
        ly.addWidget(self.inp_dest)

        ly.addWidget(_lbl(tr("correo.env_asunto", default="ASUNTO")))
        self.inp_asunto = QLineEdit(asunto); self.inp_asunto.setFixedHeight(38)
        ly.addWidget(self.inp_asunto)

        botones = QHBoxLayout(); botones.addStretch()
        bc = QPushButton(tr("correo.cancelar", default="CANCELAR")); bc.setFixedSize(130, 40)
        bc.setCursor(Qt.CursorShape.PointingHandCursor)
        bc.setStyleSheet(f"QPushButton{{background:{_BG};color:#F85149;border:2px solid #F85149;border-radius:10px;font-weight:900;}}QPushButton:hover{{background:#F85149;color:{_BG};}}")
        bc.clicked.connect(self.reject)
        bk = QPushButton("📤  " + tr("correo.env_enviar", default="ENVIAR")); bk.setFixedSize(180, 40)
        bk.setCursor(Qt.CursorShape.PointingHandCursor)
        bk.setStyleSheet(f"QPushButton{{background:{_BG};color:{_CIAN};border:2px solid {_CIAN};border-radius:10px;font-weight:900;}}QPushButton:hover{{background:{_CIAN};color:{_BG};}}")
        bk.clicked.connect(self._enviar)
        botones.addWidget(bc); botones.addWidget(bk)
        ly.addLayout(botones)
        self.setFixedWidth(560)

    def _enviar(self):
        if not self._buzones:
            if mostrar_mensaje:
                mostrar_mensaje(self, tr("correo.aviso", default="Aviso"),
                                tr("correo.env_sin_buzones", default="No hay buzones corporativos activos. Crea uno en la sección Correo."), "warning")
            return
        dest = self.inp_dest.text().strip()
        if "@" not in dest:
            if mostrar_mensaje:
                mostrar_mensaje(self, tr("correo.error_titulo", default="Datos incompletos"),
                                tr("correo.env_falta_dest", default="Introduce un destinatario válido."), "warning")
            return
        ok, msg = correo_svc.enviar_documento(
            self.cb_buzon.currentData(), dest, self.inp_asunto.text().strip(),
            tr("correo.env_cuerpo", default="Documento adjunto generado por Smart Manager AI."),
            [self._ruta] if self._ruta else None,
        )
        if mostrar_mensaje:
            mostrar_mensaje(self, tr("correo.envio_titulo", default="Envío"), msg, "info" if ok else "error")
        if ok:
            self.accept()


def enviar_documento_por_correo(parent, ruta_documento: str, asunto: str = "", destinatario: str = "") -> bool:
    """Punto de entrada reutilizable para 'enviar documento desde el correo de la
    tienda'. Lo pueden llamar albaranes, facturas, nóminas, informes, etc."""
    dlg = EnviarDocumentoDialog(ruta_documento, asunto, destinatario, parent)
    return dlg.exec() == QDialog.DialogCode.Accepted


class CorreoCorporativoWindow(QWidget):
    """Pantalla de gestión de correos corporativos de la empresa activa."""

    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self._main = main
        self.setStyleSheet(f"background:{_BG};")
        self._build()
        self.refrescar()

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(28, 22, 28, 22); root.setSpacing(16)

        cab = QHBoxLayout()
        titulo = QLabel("📧  " + tr("correo.titulo", default="CORREO CORPORATIVO"))
        titulo.setStyleSheet(f"color:{_CIAN};font-family:'Segoe UI';font-weight:900;font-size:22px;background:transparent;")
        cab.addWidget(titulo); cab.addStretch()
        if self._volver:
            bvol = QPushButton("←  " + tr("correo.volver", default="VOLVER AL MENÚ"))
            bvol.setCursor(Qt.CursorShape.PointingHandCursor); bvol.setFixedHeight(38)
            bvol.setStyleSheet(f"QPushButton{{background:transparent;color:{_DIM};border:1px solid {_BORDE};border-radius:9px;font-weight:900;padding:0 14px;}}QPushButton:hover{{border-color:{_CIAN};color:{_CIAN};}}")
            bvol.clicked.connect(self._volver_menu)
            cab.addWidget(bvol)
        root.addLayout(cab)

        # Barra de acciones
        acc = QHBoxLayout(); acc.setSpacing(10)
        def _btn(txt, slot, primary=False):
            b = QPushButton(txt); b.setFixedHeight(40); b.setCursor(Qt.CursorShape.PointingHandCursor)
            c = _CIAN if primary else _DIM
            b.setStyleSheet(f"QPushButton{{background:{_BG2};color:{c};border:2px solid {c if primary else _BORDE};border-radius:10px;font-weight:900;font-size:12px;padding:0 16px;}}QPushButton:hover{{background:{c};color:{_BG};border-color:{c};}}")
            b.clicked.connect(slot); return b
        acc.addWidget(_btn("✉️  " + tr("correo.nuevo", default="NUEVO CORREO"), self._nuevo, primary=True))
        acc.addWidget(_btn("🔗  " + tr("correo.conectar", default="CONECTAR (OAuth)"), self._conectar))
        acc.addWidget(_btn("📤  " + tr("correo.enviar_prueba", default="ENVIAR PRUEBA"), self._enviar_prueba))
        acc.addStretch()
        acc.addWidget(_btn("🗑  " + tr("correo.eliminar", default="ELIMINAR"), self._eliminar))
        root.addLayout(acc)

        # Tabla
        cols = [
            tr("correo.col_direccion", default="CORREO"),
            tr("correo.col_proveedor", default="PROVEEDOR"),
            tr("correo.col_tipo", default="TIPO"),
            tr("correo.col_estado", default="ESTADO"),
            tr("correo.col_tienda", default="TIENDA"),
            tr("correo.col_licencia", default="LICENCIA"),
            tr("correo.col_lic_estado", default="EST. LIC."),
            tr("correo.col_oauth", default="OAUTH"),
            tr("correo.col_sync", default="ÚLT. SINC."),
            tr("correo.col_alta", default="ALTA"),
        ]
        self.tabla = QTableWidget(0, len(cols))
        self.tabla.setHorizontalHeaderLabels(cols)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tabla.setStyleSheet(f"""
            QTableWidget{{background:{_BG2};color:{_TEXT};border:2px solid {_BORDE};
                          border-radius:12px;gridline-color:{_BORDE};font-family:'Segoe UI';font-size:13px;}}
            QHeaderView::section{{background:{_BG};color:{_CIAN};border:none;border-bottom:2px solid {_BORDE};
                                  padding:10px;font-weight:900;font-size:11px;}}
            QTableWidget::item{{padding:8px;}}
            QTableWidget::item:selected{{background:#00FFC622;color:white;}}
        """)
        root.addWidget(self.tabla, 1)

        self.lbl_estado = QLabel("")
        self.lbl_estado.setStyleSheet(f"color:{_DIM};font-family:'Segoe UI';font-size:11px;background:transparent;")
        root.addWidget(self.lbl_estado)

    def _volver_menu(self):
        if self._volver:
            self._volver()
        self.close()

    # ── Datos ───────────────────────────────────────────────────────────────
    def refrescar(self):
        self._filas = correo_db.listar_correos()
        self.tabla.setRowCount(len(self._filas))
        for r, c in enumerate(self._filas):
            est_oauth = correo_svc.estado_oauth(c["id_correo"])
            oauth_txt = "✔" if est_oauth["conectado"] else "—"
            valores = [
                c.get("direccion", ""),
                str(c.get("proveedor", "")).capitalize(),
                str(c.get("tipo", "")).capitalize(),
                str(c.get("estado", "")).capitalize(),
                c.get("tienda_nombre") or tr("correo.sin_tienda_corta", default="(empresa)"),
                str(c.get("tipo_licencia") or "—").replace("correo_", "").capitalize(),
                str(c.get("licencia_estado") or "—").capitalize(),
                oauth_txt,
                str(c.get("ultima_sincronizacion") or "—"),
                str(c.get("fecha_alta") or "—"),
            ]
            for col, v in enumerate(valores):
                it = QTableWidgetItem("  " + str(v))
                if col == 0:
                    it.setForeground(Qt.GlobalColor.white)
                self.tabla.setItem(r, col, it)
        self.lbl_estado.setText(
            tr("correo.resumen", default="{n} buzón(es) en esta empresa.", n=len(self._filas))
        )

    def _correo_seleccionado(self) -> dict | None:
        r = self.tabla.currentRow()
        if r < 0 or r >= len(self._filas):
            if mostrar_mensaje:
                mostrar_mensaje(self, tr("correo.aviso", default="Aviso"),
                                tr("correo.selecciona", default="Selecciona un correo de la lista."), "info")
            return None
        return self._filas[r]

    # ── Acciones ────────────────────────────────────────────────────────────
    def _nuevo(self):
        dlg = _NuevoCorreoDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.resultado:
            return
        d = dlg.resultado
        lic = correo_db.crear_licencia(tipo_licencia=d["tipo_licencia"], id_tienda=d["id_tienda"])
        cid = correo_db.crear_correo(
            d["direccion"], proveedor=d["proveedor"], tipo=d["tipo"],
            id_tienda=d["id_tienda"], id_licencia=lic,
        )
        if cid and mostrar_mensaje:
            mostrar_mensaje(self, tr("correo.creado_titulo", default="Correo creado"),
                            tr("correo.creado_msg", default="Buzón {dir} dado de alta.", dir=d["direccion"]), "info")
        elif not cid and mostrar_mensaje:
            mostrar_mensaje(self, tr("correo.error_titulo", default="Error"),
                            tr("correo.error_crear", default="No se pudo crear el correo (¿duplicado?)."), "error")
        self.refrescar()

    def _conectar(self):
        c = self._correo_seleccionado()
        if not c:
            return
        if c.get("proveedor") != "google":
            if mostrar_mensaje:
                mostrar_mensaje(self, tr("correo.aviso", default="Aviso"),
                                tr("correo.solo_google", default="La conexión OAuth está disponible para proveedor Google."), "info")
            return
        if not correo_svc.oauth_google_configurado():
            if mostrar_mensaje:
                mostrar_mensaje(self, tr("correo.oauth_no_conf_titulo", default="OAuth no configurado"),
                                tr("correo.oauth_no_conf_msg", default="Coloca 'google_oauth_client.json' en la carpeta documentos/ (descárgalo de Google Cloud Console) para conectar cuentas de Google."), "warning")
            return
        ok, msg = correo_svc.iniciar_oauth_google(c["id_correo"])
        if mostrar_mensaje:
            mostrar_mensaje(self, tr("correo.oauth_titulo", default="Conexión OAuth"),
                            msg, "info" if ok else "error")
        self.refrescar()

    def _enviar_prueba(self):
        c = self._correo_seleccionado()
        if not c:
            return
        ok, msg = correo_svc.enviar_documento(
            c["id_correo"], c["direccion"],
            tr("correo.prueba_asunto", default="Correo de prueba — Smart Manager"),
            tr("correo.prueba_cuerpo", default="Este es un envío de prueba desde Smart Manager AI."),
        )
        if mostrar_mensaje:
            mostrar_mensaje(self, tr("correo.envio_titulo", default="Envío"),
                            msg, "info" if ok else "error")
        self.refrescar()

    def _eliminar(self):
        c = self._correo_seleccionado()
        if not c:
            return
        if mostrar_confirmacion and not mostrar_confirmacion(
            self, tr("correo.eliminar_titulo", default="Eliminar correo"),
            tr("correo.eliminar_msg", default="¿Eliminar {dir}? Se revocarán sus tokens.", dir=c["direccion"])):
            return
        correo_db.eliminar_correo(c["id_correo"])
        self.refrescar()
