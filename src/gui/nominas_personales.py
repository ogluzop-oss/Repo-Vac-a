"""
Nóminas personales (petición explícita) — módulo de nivel superior para ADMINISTRADOR/OPERARIO.

Resuelve el gap de acceso que dejó la retirada del Portal del Empleado del menú principal
(`menu_principal.py`, comentario junto a la construcción del footer): un OPERARIO/ADMINISTRADOR
sin acceso a RRHH/Documentos no tenía NINGUNA vía de escritorio para ver sus propias nóminas. En
vez de reabrir el Portal completo (mucho más amplio — contratos/vacaciones/ausencias/control
horario), se añade este módulo FOCALIZADO solo en nóminas.

"Envío automático" (petición explícita, sin intervención manual uno a uno): YA EXISTE un job de
fin de mes que genera un borrador de `rrhh_nominas` para cada empleado activo con contrato vigente
(`rrhh.nomina_servicio.generar_borradores_mes_cerrado`, con el motor real de cálculo — IRPF,
contingencias SS, IT, bolsa de horas), registrado en el Scheduler Enterprise desde el arranque de
la app (`scheduler_registry.CATALOGO["rrhh_nominas_borrador_mensual"]`, intervalo 24h, habilitado
por defecto). Este módulo NO reimplementa ni duplica esa generación: solo la EXPONE al titular de
cada nómina. En cuanto el job (o una generación manual desde el expediente RRHH) persiste la fila,
queda visible aquí — sin ningún paso de "enviar a X empleado".

Confidencialidad (petición explícita: nunca la nómina de un empleado en el módulo de otro) GARANTIZADA
POR CONSTRUCCIÓN, no añadida aquí: se reutiliza íntegra la fachada ya probada
`rrhh.portal_servicio.resolver_empleado` (resuelve la ficha de empleado — la "ficha de empleado
generada en el módulo RRHH" que pide el encargo — a partir de `id_usuario`, el vínculo de la cuenta
que ha iniciado sesión) + `rrhh.db.nominas.listar_nominas(id_empleado=...)` (siempre filtrado por
ESE empleado). Mismo mecanismo de aislamiento que ya cubren los tests de
`tests/integration/test_rrhh_portal.py` (aislamiento entre usuarios y multiempresa) — no se
reinventa la seguridad aquí, se hereda.
"""

import logging
import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QTableWidgetItem, QVBoxLayout, QWidget

from src.gui.catalogo_gestion import _BG, _CIAN, _DIM, _btn, _btn_x, _tabla

logger = logging.getLogger("rrhh.nominas_personales.gui")

_ESTADO_ETIQUETA = {"borrador": "Borrador (pendiente de aprobación RRHH)", "aprobada": "Aprobada"}


def _it(v):
    return QTableWidgetItem("" if v is None else str(v))


# `QMessageBox` nativo se sustituye por el diálogo propio de la app (mismo criterio ya aplicado en
# `portal_empleado.py`/`rrhh_gestion.py`: sobre una ventana anfitriona FRAMELESS, un QMessageBox
# nativo puede quedar sin handle correcto y no llegar a mostrarse).
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


class NominasPersonalesWindow(QWidget):
    """Autoconsulta de nóminas propias — SOLO LECTURA (mismo criterio que el Portal del
    Empleado). Ninguna lógica de negocio ni de seguridad propia: toda la orquestación vive en
    `rrhh.portal_servicio`/`rrhh.db.nominas`, aquí solo se presenta."""

    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("Mis nóminas")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t)
        cab.addStretch()
        if callback_vuelta:
            cab.addWidget(_btn_x(self._volver))
        root.addLayout(cab)

        self.empleado = self._resolver()
        if not self.empleado:
            aviso = QLabel("Tu cuenta no tiene un expediente de empleado vinculado.\n"
                           "Contacta con RRHH para activar el acceso a tus nóminas.")
            aviso.setStyleSheet(f"color:{_DIM};font-size:14px;")
            root.addWidget(aviso, alignment=Qt.AlignmentFlag.AlignCenter)
            return

        nota = QLabel("Aquí aparecen automáticamente, cada mes, tus propias nóminas generadas "
                      "por RRHH — no hace falta que nadie te las envíe.")
        nota.setStyleSheet(f"color:{_DIM};font-size:12px;")
        root.addWidget(nota)

        self._nominas = self._cargar_nominas()
        self.tbl = self._tabla_nominas()
        root.addWidget(self.tbl)
        acciones = QHBoxLayout()
        acciones.addWidget(_btn("Abrir PDF", self._abrir_pdf, primary=True))
        acciones.addStretch()
        root.addLayout(acciones)

    # ── resolución segura (idéntica al Portal del Empleado: misma fachada, mismo aislamiento) ──
    def _id_empresa(self):
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return None

    def _resolver(self):
        from src.rrhh import portal_servicio
        try:
            return portal_servicio.resolver_empleado(self.usuario, self._id_empresa())
        except Exception as e:
            logger.error("resolver nominas personales: %s", e)
            return None

    def _cargar_nominas(self):
        from src.rrhh.db import nominas as _db_nominas
        return _db_nominas.listar_nominas(self.empleado["id"], self._id_empresa())

    def _tabla_nominas(self):
        t = _tabla(["Año", "Mes", "Bruto", "Neto", "IRPF", "SS", "Estado", "PDF"])
        filas = self._nominas or []
        t.setRowCount(len(filas))
        for i, r in enumerate(filas):
            estado = _ESTADO_ETIQUETA.get(r.get("estado") or "borrador", r.get("estado") or "")
            tiene_pdf = "Sí" if r.get("ref_documento") else "Pendiente"
            for j, v in enumerate([r.get("anio"), r.get("mes"), r.get("bruto"), r.get("neto"),
                                   r.get("irpf_importe"), r.get("ss_importe"), estado, tiene_pdf]):
                t.setItem(i, j, _it(v))
        return t

    def _abrir_pdf(self):
        i = self.tbl.currentRow()
        if not (0 <= i < len(self._nominas)):
            _info_msg(self, "Mis nóminas", "Selecciona una nómina.")
            return
        ruta = self._nominas[i].get("ref_documento")
        if not (ruta and os.path.exists(ruta)):
            _info_msg(self, "Mis nóminas",
                      "Esta nómina todavía no tiene un PDF generado (borrador pendiente de "
                      "aprobación por RRHH).")
            return
        try:
            # "Repositorio cifrado" (migr. 0322): las nóminas se cifran en disco al generarse —
            # `resolver_ruta_legible` es el punto único de lectura para cualquier consumidor de un
            # fichero potencialmente cifrado (descifra a un temporal si hace falta).
            from src.utils import cripto, plataforma
            ruta_legible = cripto.resolver_ruta_legible(ruta)
            plataforma.abrir_archivo(ruta_legible)
        except Exception as e:
            _error_msg(self, "Mis nóminas", f"No se pudo abrir: {e}")
