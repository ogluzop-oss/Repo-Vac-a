"""
GUI de RRHH — gestión de empleados y visor de expediente (F4.4).

Capa VISUAL sobre la infraestructura ya existente (no recalcula, no toca motor/
persistencia/migraciones): consume `src/rrhh/db/*` (empleados + expediente) y reutiliza
los patrones de `catalogo_gestion`/`contabilidad_gestion` (sidebar, helpers, estilo).

- Listado de empleados (búsqueda + filtro por estado, por id_empresa/id_tienda).
- Alta/edición de empleado (rrhh_empleados) con validaciones.
- Visor de expediente (ficha + contratos + nóminas + vacaciones + ausencias + documentos)
  vía `empleados.expediente()`.
"""

import json
import logging
import os

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QDialog, QFormLayout, QFrame, QHBoxLayout,
                             QLabel, QPushButton, QStackedWidget, QTabWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from src.gui.catalogo_gestion import (_BG, _BG2, _BORDE, _CIAN, _DIM, _SIDEBAR, _TEXT,
                                      _btn, _btn_cargando, _btn_salir_sidebar, _btn_x, _combo,
                                      _dialogo_frameless, _inp, _tabla)
from src.gui.foundation.tab_badges import instalar_badges_sidebar
from src.gui.transiciones import instalar_transicion_tabs

logger = logging.getLogger("rrhh.gui")

def _normalizar_fecha(txt):
    """Acepta AAAA-MM-DD (formato pedido en el campo) o DD/MM/AAAA (formato habitual al
    teclear en España) y devuelve siempre ISO — o None si no se pudo interpretar. Sin esto,
    un usuario que teclea "02/06/1999" (en vez de "1999-06-02") provocaba un INSERT que
    fallaba en MariaDB con "Incorrect date value", silenciado por el except genérico de
    `crear_empleado` y mal reportado en la GUI como si fuera un NIF duplicado."""
    txt = (txt or "").strip()
    if not txt:
        return None
    import datetime as _dt
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return _dt.datetime.strptime(txt, fmt).date().isoformat()
        except ValueError:
            continue
    return None


_ESTADOS = [("Activo", "activo"), ("Baja", "baja"), ("Suspendido", "suspendido"),
            ("Excedencia", "excedencia")]
_SEXOS = [("—", ""), ("Hombre", "H"), ("Mujer", "M"), ("Otro", "X")]
_AMARILLO = "#FFD60A"   # color del botón Vac./Ausencias (mismo diseño que los primarios)

# Descripción de cada función laboral (mostrada en su pestaña).
_LABORAL_DESC = {
    "CONTRATO": "Genera contratos laborales con validación legal automática (indefinido, "
                "temporal, fijo discontinuo, parcial, prácticas, sustitución).",
    "NÓMINA": "Cálculo y generación de nóminas con IRPF y cotización.",
    "ALTA": "Tramita altas en la Seguridad Social (preparado para SS RED).",
    "BAJA": "Tramita bajas y situaciones de incapacidad temporal.",
    "FINIQUITO": "Genera finiquitos con cálculo automático de conceptos.",
    "CERTIFICADO": "Emite certificados de empresa y de vida laboral.",
    "CERT LABORAL": "Certificados laborales: antigüedad, funciones, ingresos y jornada.",
    "CARTA DESPIDO": "Redacta cartas de despido con motivos predeterminados y validación legal.",
    "VACACIONES": "Solicitudes, aprobaciones y denegaciones de vacaciones.",
    "MODELO145": "Modelo 145 AEAT (comunicación de datos al pagador) y cálculo real del % de IRPF.",
}

# Descripción de la pestaña "Periodo prueba" (despido por no superar el período de prueba).
_PRUEBA_DESC = ("Genera el documento de extinción del contrato durante el período de prueba "
                "(art. 14 ET) para trabajadores que NO lo hayan superado. Reutiliza el asistente "
                "de cartas de despido con el motivo «Período de prueba» preseleccionado.")


def _it(txt):
    return QTableWidgetItem("" if txt is None else str(txt))


def _es_superadmin() -> bool:
    """Gobernanza de la aprobación borrador→aprobada (nóminas/finiquitos, migr 0264/0265): solo
    SUPERADMIN ve el botón «Aprobar» — mismo criterio de rol usado en el resto de acciones
    críticas de la app (`sesion_global.es_superadmin`)."""
    try:
        from src.db.usuario import sesion_global
        return sesion_global.es_superadmin()
    except Exception:
        return False


# ── Feedback (éxito/error/confirmación) ──────────────────────────────────────
# `QMessageBox` nativo se sustituye por el diálogo propio de la app: sobre la ventana anfitriona
# FRAMELESS de todo Smart Manager, un QMessageBox nativo puede quedar sin handle correcto y no
# llegar a mostrarse — mismo criterio ya documentado y aplicado en `catalogo_gestion._InfoDialog`/
# `seguridad_gui._InfoDialog`/`saas_admin._aviso` en esta misma auditoría.
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


def _confirmar(parent, titulo, mensaje) -> bool:
    try:
        from assets.estilo_global import mostrar_confirmacion
        return mostrar_confirmacion(parent, titulo, mensaje)
    except Exception:
        return False


_MODALIDADES_CONTRATO = [("Indefinido", "INDEFINIDO"), ("Temporal", "TEMPORAL"),
                         ("Fijo discontinuo", "FIJO_DISCONTINUO"), ("Parcial", "PARCIAL"),
                         ("Prácticas", "PRACTICAS"), ("Sustitución", "SUSTITUCION")]
_ESTADOS_CONTRATO = [("Vigente", "vigente"), ("Finalizado", "finalizado"), ("Anulado", "anulado")]


class _EditarContratoDialog(QDialog):
    """Edición de un contrato ya existente (`contratos.actualizar_contrato`) — hueco detectado en
    la auditoría: la pestaña «Contratos» del expediente era de solo lectura."""

    def __init__(self, contrato, parent=None):
        super().__init__(parent)
        v = _dialogo_frameless(self, "Editar contrato", ancho=380)
        v.addWidget(QLabel("Modalidad:"))
        self.cmb_modalidad = _combo(_MODALIDADES_CONTRATO, contrato.get("modalidad"))
        v.addWidget(self.cmb_modalidad)
        v.addWidget(QLabel("Fecha inicio (AAAA-MM-DD):"))
        self.inp_inicio = _inp("AAAA-MM-DD")
        self.inp_inicio.setText(str(contrato.get("fecha_inicio") or ""))
        v.addWidget(self.inp_inicio)
        v.addWidget(QLabel("Fecha fin (AAAA-MM-DD, vacío = indefinido):"))
        self.inp_fin = _inp("AAAA-MM-DD")
        self.inp_fin.setText(str(contrato.get("fecha_fin") or ""))
        v.addWidget(self.inp_fin)
        v.addWidget(QLabel("Salario:"))
        self.inp_salario = _inp("0.00")
        self.inp_salario.setText(str(contrato.get("salario") or ""))
        v.addWidget(self.inp_salario)
        v.addWidget(QLabel("Estado:"))
        self.cmb_estado = _combo(_ESTADOS_CONTRATO, contrato.get("estado"))
        v.addWidget(self.cmb_estado)
        fila = QHBoxLayout(); fila.addStretch()
        fila.addWidget(_btn("Cancelar", self.reject))
        fila.addWidget(_btn("Guardar", self.accept, primary=True))
        v.addLayout(fila)

    def valores(self):
        campos = {"modalidad": self.cmb_modalidad.currentData(), "estado": self.cmb_estado.currentData(),
                  "fecha_fin": self.inp_fin.text().strip() or None}
        if self.inp_inicio.text().strip():
            campos["fecha_inicio"] = self.inp_inicio.text().strip()
        if self.inp_salario.text().strip():
            try:
                campos["salario"] = float(self.inp_salario.text().strip().replace(",", "."))
            except ValueError:
                pass
        return campos


class _EditarAusenciaDialog(QDialog):
    """Edición de una ausencia ya registrada (`ausencias_servicio.editar`) — hueco detectado en
    la auditoría: la pestaña «Ausencias» solo permitía dar de alta, nunca corregir ni eliminar."""

    def __init__(self, ausencia, tipos, parent=None):
        super().__init__(parent)
        v = _dialogo_frameless(self, "Editar ausencia", ancho=380)
        v.addWidget(QLabel("Tipo:"))
        self.cmb_tipo = _combo([(et, k) for k, et in tipos.items()], ausencia.get("tipo"))
        v.addWidget(self.cmb_tipo)
        v.addWidget(QLabel("Fecha inicio (AAAA-MM-DD):"))
        self.inp_ini = _inp("AAAA-MM-DD")
        self.inp_ini.setText(str(ausencia.get("fecha_inicio") or ""))
        v.addWidget(self.inp_ini)
        v.addWidget(QLabel("Fecha fin (AAAA-MM-DD):"))
        self.inp_fin = _inp("AAAA-MM-DD")
        self.inp_fin.setText(str(ausencia.get("fecha_fin") or ""))
        v.addWidget(self.inp_fin)
        v.addWidget(QLabel("Motivo:"))
        self.inp_mot = _inp("Motivo")
        self.inp_mot.setText(str(ausencia.get("motivo") or ""))
        v.addWidget(self.inp_mot)
        fila = QHBoxLayout(); fila.addStretch()
        fila.addWidget(_btn("Cancelar", self.reject))
        fila.addWidget(_btn("Guardar", self.accept, primary=True))
        v.addLayout(fila)

    def valores(self):
        campos = {"tipo": self.cmb_tipo.currentData(), "motivo": self.inp_mot.text().strip()}
        if self.inp_ini.text().strip():
            campos["fecha_inicio"] = self.inp_ini.text().strip()
        if self.inp_fin.text().strip():
            campos["fecha_fin"] = self.inp_fin.text().strip()
        return campos


class _EditarNominaDialog(QDialog):
    """Edición de una nómina ya generada (`nominas.actualizar_nomina`) — hueco detectado en la
    auditoría: la pestaña «Nóminas» del expediente era de solo lectura."""

    _CAMPOS = [("bruto", "Bruto"), ("base", "Base cotización"), ("irpf_pct", "IRPF (%)"),
              ("irpf_importe", "Retención IRPF"), ("ss_pct", "SS trabajador (%)"),
              ("ss_importe", "Retención SS"), ("neto", "Neto")]

    def __init__(self, nomina, parent=None):
        super().__init__(parent)
        v = _dialogo_frameless(self, f"Editar nómina {nomina.get('mes')}/{nomina.get('anio')}", ancho=380)
        self._inputs = {}
        for clave, etiqueta in self._CAMPOS:
            v.addWidget(QLabel(f"{etiqueta}:"))
            inp = _inp("0.00")
            inp.setText(str(nomina.get(clave) if nomina.get(clave) is not None else ""))
            self._inputs[clave] = inp
            v.addWidget(inp)
        fila = QHBoxLayout(); fila.addStretch()
        fila.addWidget(_btn("Cancelar", self.reject))
        fila.addWidget(_btn("Guardar", self.accept, primary=True))
        v.addLayout(fila)

    def valores(self):
        campos = {}
        for clave, _et in self._CAMPOS:
            txt = self._inputs[clave].text().strip()
            if not txt:
                continue
            try:
                campos[clave] = float(txt.replace(",", "."))
            except ValueError:
                pass
        return campos


# ── Formulario de alta / edición ──────────────────────────────────────────────
class EmpleadoFormDialog(QDialog):
    """Alta/edición sobre rrhh_empleados. `empleado` (dict) → modo edición."""

    def __init__(self, empleado=None, id_empresa=None, parent=None):
        super().__init__(parent)
        self.empleado = empleado or {}
        self.id_empresa = id_empresa
        self.resultado_id = None
        self.setWindowTitle("Editar empleado" if empleado else "Nuevo empleado")
        self.setStyleSheet(f"QLabel{{color:{_TEXT};font-size:12px;}}")
        self._build()

    def _build(self):
        root = _dialogo_frameless(self, "Editar empleado" if self.empleado else "Nuevo empleado", ancho=560)
        tabs = QTabWidget()
        # Sin borde en el pane (se retiran las líneas grises que rodeaban Identificación/Contacto/Laboral).
        tabs.setStyleSheet(f"QTabBar::tab{{background:{_SIDEBAR};color:{_DIM};padding:8px 14px;}}"
                           f"QTabBar::tab:selected{{color:{_CIAN};}}"
                           f"QTabWidget::pane{{border:none;}}")
        e = self.empleado
        # Identificación
        self.in_nombre = _inp("Nombre", ); self.in_nombre.setText(e.get("nombre", ""))
        self.in_apellidos = _inp(); self.in_apellidos.setText(e.get("apellidos") or "")
        self.cb_sexo = _combo(_SEXOS, e.get("sexo") or "")
        self.in_fnac = _inp("AAAA-MM-DD"); self.in_fnac.setText(str(e.get("fecha_nacimiento") or ""))
        self.in_nac = _inp(); self.in_nac.setText(e.get("nacionalidad") or "")
        self.in_nif = _inp("NIF/NIE *"); self.in_nif.setText(e.get("nif") or "")
        self.in_ss = _inp(); self.in_ss.setText(e.get("num_ss") or "")
        self.in_discapacidad = _inp("0-100")
        self.in_discapacidad.setText(str(e.get("discapacidad_pct")) if e.get("discapacidad_pct") else "")
        self.in_discapacidad.setToolTip("Grado de discapacidad reconocido (%). A partir de 33% cuenta "
                                        "como contratación bonificada en la Calculadora Fiscal.")
        tabs.addTab(self._form([
            ("Nombre *", self.in_nombre), ("Apellidos", self.in_apellidos), ("Sexo", self.cb_sexo),
            ("Fecha nacimiento", self.in_fnac), ("Nacionalidad", self.in_nac),
            ("NIF/NIE *", self.in_nif), ("Nº Seguridad Social", self.in_ss),
            ("Grado discapacidad (%)", self.in_discapacidad)]), "Identificación")
        # Contacto
        self.in_dir = _inp(); self.in_dir.setText(e.get("direccion") or "")
        self.in_mun = _inp(); self.in_mun.setText(e.get("municipio") or "")
        self.in_prov = _inp(); self.in_prov.setText(e.get("provincia") or "")
        self.in_cp = _inp(); self.in_cp.setText(e.get("cp") or "")
        self.in_pais = _inp(); self.in_pais.setText(e.get("pais") or "ESPAÑA")
        self.in_tel = _inp(); self.in_tel.setText(e.get("telefono") or "")
        self.in_email = _inp(); self.in_email.setText(e.get("email") or "")
        tabs.addTab(self._form([
            ("Dirección", self.in_dir), ("Municipio", self.in_mun), ("Provincia", self.in_prov),
            ("CP", self.in_cp), ("País", self.in_pais), ("Teléfono", self.in_tel),
            ("Email", self.in_email)]), "Contacto")
        # Laboral
        self.cb_centro = _combo(self._opciones_centros(), e.get("id_centro"))
        self.in_cat = _inp(); self.in_cat.setText(e.get("categoria") or "")
        self.in_grupo = _inp(); self.in_grupo.setText(e.get("grupo_prof") or "")
        self.in_conv = _inp(); self.in_conv.setText(e.get("convenio") or "")
        self.in_puesto = _inp(); self.in_puesto.setText(e.get("puesto") or "")
        self.in_sal = _inp("0.00"); self.in_sal.setText(str(e.get("salario_base") or ""))
        self.in_jor = _inp(); self.in_jor.setText(e.get("jornada") or "")
        self.cb_estado = _combo(_ESTADOS, e.get("estado") or "activo")
        # Responsable directo (petición explícita — base de la aprobación jerárquica en cascada de
        # vacaciones/ausencias): cualquier otro empleado de la empresa.
        self.cb_responsable = _combo(self._opciones_responsables(), e.get("id_responsable"))
        # IBAN (petición explícita — domiciliación de nómina): se guarda CIFRADO y se cablea con
        # Nóminas mostrando SOLO los 4 últimos dígitos (nunca el número completo en pantalla ni en
        # los documentos generados). En edición, muestra la máscara ya guardada como placeholder —
        # si no se teclea nada nuevo, el IBAN existente no se toca (ver `_campos()`).
        self.in_iban = _inp("ESxx xxxx xxxx xxxx xxxx xxxx")
        self._iban_mascara_actual = e.get("iban_mascara") or ""
        if self._iban_mascara_actual:
            self.in_iban.setPlaceholderText(f"{self._iban_mascara_actual} (déjalo en blanco para no cambiarlo)")
        self.in_iban.setToolTip("Se cifra al guardar. En Nóminas y en los documentos generados solo "
                                "se muestran los 4 últimos dígitos.")
        tabs.addTab(self._form([
            ("Centro de trabajo", self.cb_centro), ("Categoría", self.in_cat),
            ("Grupo profesional", self.in_grupo), ("Convenio", self.in_conv),
            ("Puesto", self.in_puesto), ("Salario base mensual", self.in_sal),
            ("Jornada", self.in_jor), ("Estado", self.cb_estado),
            ("Responsable directo", self.cb_responsable),
            ("IBAN (domiciliación nómina)", self.in_iban)]), "Laboral")
        # Animación de deslizamiento al cambiar de pestaña — mismo mecanismo reutilizado en
        # `GestionLaboralDialog` (`src/gui/transiciones.py`), no una segunda implementación.
        instalar_transicion_tabs(tabs)
        root.addWidget(tabs)
        # Aviso INLINE (no un segundo diálogo modal encima de este): un SmartMessageDialog
        # anidado dentro de OTRO diálogo frameless ya modal (en vez de sobre la ventana principal,
        # el caso habitual) dejaba su botón "Aceptar" sin estilo aplicado — invisible sobre el
        # panel oscuro (bug real reportado). Mismo criterio que camaras_gui/marketplace_gui: en
        # un contexto de riesgo, una etiqueta en la propia pantalla en vez de un modal.
        self.lbl_error = QLabel(""); self.lbl_error.setWordWrap(True)
        self.lbl_error.setStyleSheet("color:#F85149;font-weight:700;font-size:12px;")
        self.lbl_error.setVisible(False)
        root.addWidget(self.lbl_error)
        botones = QHBoxLayout()
        # En modo edición: botón para ELIMINAR el empleado (rojo, a la izquierda).
        if self.empleado.get("id"):
            botones.addWidget(_btn("Eliminar", self._eliminar, danger=True))
        botones.addStretch()
        # Sin "Cancelar": ya existe el botón X rojo de _dialogo_frameless — era redundante.
        botones.addWidget(_btn("Guardar", self._guardar, primary=True))
        root.addLayout(botones)

    def _eliminar(self):
        from src.rrhh.db import empleados
        eid = self.empleado.get("id")
        if not eid:
            return
        nom = f"{self.empleado.get('nombre','')} {self.empleado.get('apellidos','')}".strip()
        if not _confirmar(self, "Eliminar empleado",
                          f"¿Eliminar a «{nom or eid}»?\nEsta acción no se puede deshacer."):
            return
        try:
            ok = empleados.eliminar_empleado(eid, self.id_empresa)
        except Exception as ex:
            logger.error("eliminar_empleado(%s): %s", eid, ex); ok = False
        if ok:
            self.resultado_id = None
            self.accept()   # el llamador (_editar) recarga la lista
        else:
            self._mostrar_error("No se pudo eliminar el empleado.")

    def _form(self, filas):
        w = QWidget(); fl = QFormLayout(w)
        for et, widget in filas:
            lab = QLabel(et); lab.setStyleSheet(f"color:{_DIM};")
            fl.addRow(lab, widget)
        return w

    def _opciones_centros(self):
        ops = [("— Sin centro —", None)]
        try:
            from src.rrhh.db import centros
            for c in centros.listar_centros(self.id_empresa):
                ops.append((c.get("nombre_centro") or c.get("id_centro"), c.get("id_centro")))
        except Exception as ex:
            logger.error("opciones_centros: %s", ex)
        return ops

    def _opciones_responsables(self):
        ops = [("— Sin responsable —", None)]
        try:
            from src.rrhh.db import empleados
            mi_id = self.empleado.get("id")
            for emp in empleados.listar_empleados(self.id_empresa, estado="activo"):
                if emp.get("id") == mi_id:
                    continue  # un empleado no puede ser su propio responsable
                nombre = f"{emp.get('nombre','')} {emp.get('apellidos') or ''}".strip()
                ops.append((nombre or emp.get("nif"), emp.get("id")))
        except Exception as ex:
            logger.error("opciones_responsables: %s", ex)
        return ops

    def _campos(self):
        def _f(x):
            try:
                return float(str(x).replace(",", ".")) if str(x).strip() else 0.0
            except ValueError:
                return 0.0
        def _pct_disc(x):
            try:
                v = int(float(str(x).replace(",", ".").strip())) if str(x).strip() else None
            except ValueError:
                return None
            return max(0, min(100, v)) if v is not None else None
        campos = dict(
            nombre=self.in_nombre.text().strip(), apellidos=self.in_apellidos.text().strip(),
            sexo=self.cb_sexo.currentData(), fecha_nacimiento=_normalizar_fecha(self.in_fnac.text()),
            nacionalidad=self.in_nac.text().strip(), nif=self.in_nif.text().strip().upper(),
            num_ss=self.in_ss.text().strip(), direccion=self.in_dir.text().strip(),
            municipio=self.in_mun.text().strip(), provincia=self.in_prov.text().strip(),
            cp=self.in_cp.text().strip(), pais=self.in_pais.text().strip(),
            telefono=self.in_tel.text().strip(), email=self.in_email.text().strip(),
            id_centro=self.cb_centro.currentData(), categoria=self.in_cat.text().strip(),
            grupo_prof=self.in_grupo.text().strip(), convenio=self.in_conv.text().strip(),
            puesto=self.in_puesto.text().strip(), salario_base=_f(self.in_sal.text()),
            jornada=self.in_jor.text().strip(), estado=self.cb_estado.currentData() or "activo",
            discapacidad_pct=_pct_disc(self.in_discapacidad.text()),
            id_responsable=self.cb_responsable.currentData())
        # IBAN: solo se incluye (y por tanto solo se toca en BD) si el usuario tecleó algo nuevo —
        # dejarlo en blanco en edición conserva el IBAN ya guardado (ver placeholder con la máscara).
        iban_tecleado = self.in_iban.text().strip()
        if iban_tecleado:
            campos["iban"] = iban_tecleado
        return campos

    def _mostrar_error(self, mensaje):
        self.lbl_error.setText(mensaje)
        self.lbl_error.setVisible(True)

    def _guardar(self):
        from src.rrhh.db import empleados
        self.lbl_error.setVisible(False)
        # Validar la fecha ANTES de normalizarla en silencio: si el usuario tecleó algo que no
        # se puede interpretar (ni AAAA-MM-DD ni DD/MM/AAAA), avisar en vez de guardar sin fecha
        # o — el bug real encontrado — dejar que el INSERT falle en la BD con un error opaco que
        # la GUI reportaba, siempre, como "¿NIF duplicado?" sin serlo.
        if self.in_fnac.text().strip() and _normalizar_fecha(self.in_fnac.text()) is None:
            self._mostrar_error("Fecha de nacimiento no válida. Usa el formato AAAA-MM-DD (o DD/MM/AAAA).")
            return
        campos = self._campos()
        if not campos["nombre"] or not campos["nif"]:
            self._mostrar_error("Nombre y NIF/NIE son obligatorios.")
            return
        try:
            if self.empleado.get("id"):
                ok = empleados.actualizar_empleado(self.empleado["id"], self.id_empresa, **campos)
                if ok:
                    self.resultado_id = self.empleado["id"]; self.accept()
                else:
                    self._mostrar_error("No se pudo actualizar el empleado.")
            else:
                eid = empleados.crear_empleado(id_empresa=self.id_empresa, **campos)
                if eid:
                    self.resultado_id = eid; self.accept()
                else:
                    self._mostrar_error(
                        "No se pudo crear el empleado (¿NIF duplicado en esta empresa? "
                        "revisa también el resto de campos — consulta el registro de errores "
                        "para más detalle).")
        except ValueError as ex:
            self._mostrar_error(str(ex))


# ── Visor de expediente ───────────────────────────────────────────────────────
class ExpedienteDialog(QDialog):
    def __init__(self, id_empleado, id_empresa=None, parent=None):
        super().__init__(parent)
        self.id_empleado = id_empleado
        self.id_empresa = id_empresa
        self.setWindowTitle("Expediente del trabajador")
        self.setMinimumSize(820, 560)
        self.setStyleSheet(f"QDialog{{background:{_BG};}} QLabel{{color:{_TEXT};}}")
        self._build()

    def _build(self):
        from src.rrhh.db import empleados
        exp = empleados.expediente(self.id_empleado, self.id_empresa) or {}
        self.exp = exp
        root = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.setStyleSheet(f"QTabBar::tab{{background:{_SIDEBAR};color:{_DIM};padding:8px 14px;}}"
                           f"QTabBar::tab:selected{{color:{_CIAN};}}"
                           f"QTabWidget::pane{{border:1px solid {_BORDE};}}")
        emp = exp.get("empleado") or {}
        tabs.addTab(self._ficha(emp), "Ficha")
        tabs.addTab(self._tab_contratos(exp.get("contratos")), "Contratos")
        tabs.addTab(self._tab_nominas(exp.get("nominas")), "Nóminas")
        tabs.addTab(self._tab_finiquitos(exp.get("finiquitos")), "Finiquitos")
        tabs.addTab(self._tabla_simple(exp.get("vacaciones"),
                    ["Año", "Tipo", "Inicio", "Fin", "Días", "Estado"],
                    lambda r: [r.get("anio"), r.get("tipo"), r.get("fecha_inicio"),
                               r.get("fecha_fin"), r.get("dias"), r.get("estado")]), "Vacaciones")
        tabs.addTab(self._tabla_simple(exp.get("ausencias"),
                    ["Tipo", "Inicio", "Fin", "Días", "Motivo"],
                    lambda r: [r.get("tipo"), r.get("fecha_inicio"), r.get("fecha_fin"),
                               r.get("dias"), r.get("motivo")]), "Ausencias")
        tabs.addTab(self._tabla_simple(exp.get("control_horario"),
                    ["Fecha", "Entrada", "Salida", "Efectivo (min)", "Exceso", "Déficit"],
                    lambda r: [r.get("fecha"), r.get("hora_entrada"), r.get("hora_salida"),
                               r.get("tiempo_efectivo_min"), r.get("exceso_min"),
                               r.get("deficit_min")]), "Control horario")
        tabs.addTab(self._docs(exp.get("documentos")), "Documentos")
        root.addWidget(tabs)
        cerrar = _btn("Cerrar", self.accept)
        root.addWidget(cerrar, alignment=Qt.AlignmentFlag.AlignRight)

    def _ficha(self, emp):
        w = QWidget(); fl = QFormLayout(w)
        campos = [("Nombre", f"{emp.get('nombre','')} {emp.get('apellidos','') or ''}".strip()),
                  ("NIF/NIE", emp.get("nif")), ("Nº SS", emp.get("num_ss")),
                  ("Puesto", emp.get("puesto")), ("Categoría", emp.get("categoria")),
                  ("Grupo prof.", emp.get("grupo_prof")), ("Convenio", emp.get("convenio")),
                  ("Salario base", emp.get("salario_base")), ("Jornada", emp.get("jornada")),
                  ("Estado", emp.get("estado")), ("Email", emp.get("email")),
                  ("Teléfono", emp.get("telefono"))]
        for et, val in campos:
            lab = QLabel(et); lab.setStyleSheet(f"color:{_DIM};")
            v = QLabel("" if val is None else str(val)); v.setStyleSheet(f"color:{_TEXT};font-weight:700;")
            fl.addRow(lab, v)
        return w

    # ── Contratos (editable — F4.1.2 sin frontend previo) ───────────────────────
    def _tab_contratos(self, contratos):
        w = QWidget(); ly = QVBoxLayout(w)
        self.tbl_contratos = _tabla(["ID", "Modalidad", "Inicio", "Fin", "Salario", "Estado"])
        self.tbl_contratos.cellClicked.connect(self._sel_contrato)
        self._contratos_data = contratos or []
        self._contrato_sel = None
        self._refrescar_tabla_contratos()
        ly.addWidget(self.tbl_contratos)
        bar = QHBoxLayout()
        bar.addWidget(_btn("Editar", self._editar_contrato))
        bar.addWidget(_btn("Eliminar", self._eliminar_contrato, danger=True))
        bar.addStretch()
        ly.addLayout(bar)
        return w

    def _refrescar_tabla_contratos(self):
        self.tbl_contratos.setRowCount(len(self._contratos_data))
        for i, r in enumerate(self._contratos_data):
            for j, val in enumerate([r.get("id"), r.get("modalidad"), r.get("fecha_inicio"),
                                     r.get("fecha_fin"), r.get("salario"), r.get("estado")]):
                self.tbl_contratos.setItem(i, j, _it(val))

    def _sel_contrato(self, row, _c):
        try:
            self._contrato_sel = self._contratos_data[row]
        except (IndexError, AttributeError):
            self._contrato_sel = None

    def _editar_contrato(self):
        if not self._contrato_sel:
            _info_msg(self, "Contratos", "Selecciona primero un contrato en la tabla.")
            return
        dlg = _EditarContratoDialog(self._contrato_sel, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        from src.rrhh.db import contratos as CT
        if CT.actualizar_contrato(self._contrato_sel["id"], id_empresa=self.id_empresa, **dlg.valores()):
            _info_msg(self, "Contratos", "Contrato actualizado correctamente.")
            self._recargar_contratos()
        else:
            _error_msg(self, "Contratos", "No se pudo actualizar el contrato.")

    def _eliminar_contrato(self):
        if not self._contrato_sel:
            _info_msg(self, "Contratos", "Selecciona primero un contrato en la tabla.")
            return
        if not _confirmar(
                self, "Eliminar contrato",
                f"¿Eliminar el contrato «{self._contrato_sel.get('modalidad') or self._contrato_sel['id']}»?\n"
                "Esta acción no se puede deshacer."):
            return
        from src.rrhh.db import contratos as CT
        if CT.eliminar_contrato(self._contrato_sel["id"], id_empresa=self.id_empresa):
            _info_msg(self, "Contratos", "Contrato eliminado correctamente.")
            self._recargar_contratos()
        else:
            _error_msg(self, "Contratos", "No se pudo eliminar el contrato.")

    def _recargar_contratos(self):
        from src.rrhh.db import contratos as CT
        self._contratos_data = CT.listar_contratos(self.id_empleado, self.id_empresa)
        self._refrescar_tabla_contratos()
        self._contrato_sel = None

    # ── Nóminas (editable — F4.1.2 sin frontend previo) ─────────────────────────
    def _tab_nominas(self, nominas):
        w = QWidget(); ly = QVBoxLayout(w)
        self.tbl_nominas = _tabla(["ID", "Año", "Mes", "Bruto", "Base", "IRPF", "SS", "Neto", "Estado"])
        self.tbl_nominas.cellClicked.connect(self._sel_nomina)
        self._nominas_data = nominas or []
        self._nomina_sel = None
        self._refrescar_tabla_nominas()
        ly.addWidget(self.tbl_nominas)
        bar = QHBoxLayout()
        bar.addWidget(_btn("Editar", self._editar_nomina))
        # Aprobar (borrador→aprobada, migr 0264 `rrhh_nominas.estado`): igual que en Finiquitos,
        # solo SUPERADMIN puede cerrar la aprobación de una nómina — ver `_es_superadmin`.
        if _es_superadmin():
            bar.addWidget(_btn("Aprobar", self._aprobar_nomina))
        bar.addWidget(_btn("Eliminar", self._eliminar_nomina, danger=True))
        bar.addStretch()
        ly.addLayout(bar)
        return w

    def _refrescar_tabla_nominas(self):
        self.tbl_nominas.setRowCount(len(self._nominas_data))
        for i, r in enumerate(self._nominas_data):
            for j, val in enumerate([r.get("id"), r.get("anio"), r.get("mes"), r.get("bruto"),
                                     r.get("base"), r.get("irpf_importe"), r.get("ss_importe"),
                                     r.get("neto"), r.get("estado") or "borrador"]):
                self.tbl_nominas.setItem(i, j, _it(val))

    def _aprobar_nomina(self):
        if not self._nomina_sel:
            _info_msg(self, "Nóminas", "Selecciona primero una nómina en la tabla.")
            return
        if (self._nomina_sel.get("estado") or "borrador") == "aprobada":
            _info_msg(self, "Nóminas", "Esta nómina ya está aprobada.")
            return
        if not _confirmar(
                self, "Aprobar nómina",
                f"¿Aprobar la nómina {self._nomina_sel.get('mes')}/{self._nomina_sel.get('anio')}?\n"
                "Una vez aprobada queda como registro definitivo."):
            return
        from src.rrhh.db import nominas as NM
        from src.db.usuario import sesion_global
        aprobado_por = (sesion_global.usuario_actual or {}).get("nombre") \
            or (sesion_global.usuario_actual or {}).get("usuario")
        if NM.aprobar_nomina(self._nomina_sel["id"], id_empresa=self.id_empresa,
                             aprobado_por=aprobado_por):
            _info_msg(self, "Nóminas", "Nómina aprobada correctamente.")
            self._recargar_nominas()
        else:
            _error_msg(self, "Nóminas", "No se pudo aprobar la nómina.")

    def _sel_nomina(self, row, _c):
        try:
            self._nomina_sel = self._nominas_data[row]
        except (IndexError, AttributeError):
            self._nomina_sel = None

    def _editar_nomina(self):
        if not self._nomina_sel:
            _info_msg(self, "Nóminas", "Selecciona primero una nómina en la tabla.")
            return
        dlg = _EditarNominaDialog(self._nomina_sel, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        from src.rrhh.db import nominas as NM
        if NM.actualizar_nomina(self._nomina_sel["id"], id_empresa=self.id_empresa, **dlg.valores()):
            _info_msg(self, "Nóminas", "Nómina actualizada correctamente.")
            self._recargar_nominas()
        else:
            _error_msg(self, "Nóminas", "No se pudo actualizar la nómina.")

    def _eliminar_nomina(self):
        if not self._nomina_sel:
            _info_msg(self, "Nóminas", "Selecciona primero una nómina en la tabla.")
            return
        if not _confirmar(
                self, "Eliminar nómina",
                f"¿Eliminar la nómina {self._nomina_sel.get('mes')}/{self._nomina_sel.get('anio')}?\n"
                "Esta acción no se puede deshacer."):
            return
        from src.rrhh.db import nominas as NM
        if NM.eliminar_nomina(self._nomina_sel["id"], id_empresa=self.id_empresa):
            _info_msg(self, "Nóminas", "Nómina eliminada correctamente.")
            self._recargar_nominas()
        else:
            _error_msg(self, "Nóminas", "No se pudo eliminar la nómina.")

    def _recargar_nominas(self):
        from src.rrhh.db import nominas as NM
        self._nominas_data = NM.listar_nominas(self.id_empleado, self.id_empresa)
        self._refrescar_tabla_nominas()
        self._nomina_sel = None

    # ── Finiquitos (borrador/aprobada, rrhh_finiquitos, migr 0265) ──────────────
    def _tab_finiquitos(self, finiquitos):
        w = QWidget(); ly = QVBoxLayout(w)
        self.tbl_finiquitos = _tabla(
            ["ID", "Fecha efectos", "Bruto", "Líquido", "Estado", "Documento"])
        self.tbl_finiquitos.cellClicked.connect(self._sel_finiquito)
        self._finiquitos_data = finiquitos or []
        self._finiquito_sel = None
        self._refrescar_tabla_finiquitos()
        ly.addWidget(self.tbl_finiquitos)
        bar = QHBoxLayout()
        # Solo SUPERADMIN puede aprobar un finiquito (documento legal): mismo criterio de
        # gobernanza que el resto de acciones críticas de RRHH/nóminas en esta app.
        if _es_superadmin():
            bar.addWidget(_btn("Aprobar", self._aprobar_finiquito))
        bar.addWidget(_btn("Eliminar", self._eliminar_finiquito, danger=True))
        bar.addStretch()
        ly.addLayout(bar)
        return w

    def _refrescar_tabla_finiquitos(self):
        self.tbl_finiquitos.setRowCount(len(self._finiquitos_data))
        for i, r in enumerate(self._finiquitos_data):
            doc = (r.get("ref_documento") or "").replace("\\", "/").rsplit("/", 1)[-1]
            for j, val in enumerate([r.get("id"), r.get("fecha_efectos"), r.get("total_bruto"),
                                     r.get("total_liquido"), r.get("estado") or "borrador",
                                     doc or "—"]):
                self.tbl_finiquitos.setItem(i, j, _it(val))

    def _sel_finiquito(self, row, _c):
        try:
            self._finiquito_sel = self._finiquitos_data[row]
        except (IndexError, AttributeError):
            self._finiquito_sel = None

    def _aprobar_finiquito(self):
        if not self._finiquito_sel:
            _info_msg(self, "Finiquitos", "Selecciona primero un finiquito en la tabla.")
            return
        if (self._finiquito_sel.get("estado") or "borrador") == "aprobada":
            _info_msg(self, "Finiquitos", "Este finiquito ya está aprobado.")
            return
        if not _confirmar(
                self, "Aprobar finiquito",
                f"¿Aprobar el finiquito con fecha de efectos "
                f"{self._finiquito_sel.get('fecha_efectos')}?\n"
                "Una vez aprobado queda como liquidación definitiva."):
            return
        from src.rrhh.db import finiquitos as FQ
        from src.db.usuario import sesion_global
        aprobado_por = (sesion_global.usuario_actual or {}).get("nombre") \
            or (sesion_global.usuario_actual or {}).get("usuario")
        if FQ.aprobar_finiquito(self._finiquito_sel["id"], id_empresa=self.id_empresa,
                                aprobado_por=aprobado_por):
            _info_msg(self, "Finiquitos", "Finiquito aprobado correctamente.")
            self._recargar_finiquitos()
        else:
            _error_msg(self, "Finiquitos", "No se pudo aprobar el finiquito.")

    def _eliminar_finiquito(self):
        if not self._finiquito_sel:
            _info_msg(self, "Finiquitos", "Selecciona primero un finiquito en la tabla.")
            return
        if not _confirmar(
                self, "Eliminar finiquito",
                f"¿Eliminar el finiquito con fecha de efectos "
                f"{self._finiquito_sel.get('fecha_efectos')}?\nEsta acción no se puede deshacer."):
            return
        from src.rrhh.db import finiquitos as FQ
        if FQ.eliminar_finiquito(self._finiquito_sel["id"], id_empresa=self.id_empresa):
            _info_msg(self, "Finiquitos", "Finiquito eliminado correctamente.")
            self._recargar_finiquitos()
        else:
            _error_msg(self, "Finiquitos", "No se pudo eliminar el finiquito.")

    def _recargar_finiquitos(self):
        from src.rrhh.db import finiquitos as FQ
        self._finiquitos_data = FQ.listar_finiquitos(self.id_empleado, self.id_empresa)
        self._refrescar_tabla_finiquitos()
        self._finiquito_sel = None

    def _tabla_simple(self, filas, cols, fila_fn):
        filas = filas or []
        t = _tabla(cols)
        t.setRowCount(len(filas))
        for i, r in enumerate(filas):
            for j, val in enumerate(fila_fn(r)):
                t.setItem(i, j, _it(val))
        return t

    def _docs(self, docs):
        docs = docs or []
        w = QWidget(); ly = QVBoxLayout(w)
        self.tbl_docs = _tabla(["Fecha", "Tipo", "Estado firma", "Referencia"])
        self.tbl_docs.setRowCount(len(docs))
        self._docs_data = docs
        for i, d in enumerate(docs):
            estado = d.get("estado_firma") if d.get("requiere_firma") else "—"
            self.tbl_docs.setItem(i, 0, _it(d.get("fecha")))
            self.tbl_docs.setItem(i, 1, _it(d.get("tipo_doc")))
            self.tbl_docs.setItem(i, 2, _it(estado))
            self.tbl_docs.setItem(i, 3, _it(d.get("ref_documento")))
        ly.addWidget(self.tbl_docs)
        bar = QHBoxLayout()
        bar.addWidget(_btn("Abrir PDF", self._abrir_pdf))
        bar.addWidget(_btn("Ver datos", self._ver_snapshot))
        ly.addLayout(bar)
        return w

    def _doc_sel(self):
        i = self.tbl_docs.currentRow()
        return self._docs_data[i] if 0 <= i < len(self._docs_data) else None

    def _abrir_pdf(self):
        d = self._doc_sel()
        ruta = (d or {}).get("ref_documento")
        if ruta and os.path.exists(ruta):
            try:
                from src.utils import plataforma
                plataforma.abrir_archivo(ruta)
            except Exception as ex:
                _error_msg(self, "RRHH", f"No se pudo abrir: {ex}")
        else:
            _info_msg(self, "RRHH", "El PDF no está disponible en disco.")

    def _ver_snapshot(self):
        d = self._doc_sel()
        snap = (d or {}).get("datos_snapshot")
        if not snap:
            _info_msg(self, "RRHH", "Sin datos de snapshot."); return
        try:
            txt = json.dumps(json.loads(snap), ensure_ascii=False, indent=2)
        except Exception:
            txt = str(snap)
        _info_msg(self, "Datos del documento", txt[:4000])


# ── Ventana principal ─────────────────────────────────────────────────────────
class RRHHWindow(QWidget):
    # Módulo LABORAL clasificado por pestañas (icono, etiqueta sidebar, tipo de wizard).
    # (icono, etiqueta, tipo_wizard, subtipo_inicial)
    _LABORAL_SECCIONES = [
        ("📄", "Contratos", "CONTRATO", None),
        ("📊", "Nóminas", "NÓMINA", None),
        ("✅", "Altas laborales", "ALTA", None),
        ("❌", "Bajas laborales", "BAJA", None),
        ("💼", "Finiquitos", "FINIQUITO", None),
        ("🏢", "Certificados de empresa", "CERTIFICADO", None),
        ("📃", "Certificados laborales", "CERT LABORAL", None),
        ("📮", "Cartas de despido", "CARTA DESPIDO", None),
        # Vacaciones se gestiona en la pestaña Empleados (Vac./Ausencias). Aquí: periodo de prueba.
        ("🧪", "Periodo prueba no superado", "CARTA DESPIDO", "PERÍODO DE PRUEBA"),
        # Fase B2 (plan RRHH/IRPF): añadida AL FINAL de la lista para minimizar colisión con otras
        # fases que tocan este mismo fichero en paralelo (Fase C, bajas laborales).
        ("🧾", "Modelo Fiscal Empleados", "MODELO145", None),
    ]

    # Índice del botón/página "Nóminas" en `_sb_btns`/`stack` (Empleados=0, luego cada sección
    # laboral en orden). Calculado, no hardcodeado, para no desincronizarse si `_LABORAL_SECCIONES`
    # cambia de orden — usado por el badge de actividad (Centro de Actividad, pestaña "nominas").
    _IDX_NOMINAS = 1 + next(i for i, (_ic, _lab, _t, _s) in enumerate(_LABORAL_SECCIONES)
                            if _lab == "Nóminas")

    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.main = main
        # OJO: no fijar el stylesheet de fondo en la VENTANA — se propaga a los botones del
        # sidebar y rompe su estilo. El fondo se aplica al panel derecho (como Contabilidad).

        root = QHBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        root.addWidget(self._build_sidebar())

        right = QWidget(); right.setStyleSheet(f"background:{_BG};"); rcol = QVBoxLayout(right)
        rcol.setContentsMargins(24, 18, 24, 18); rcol.setSpacing(14)
        self._lbl_tit = QLabel("Recursos Humanos · Empleados")
        self._lbl_tit.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        rcol.addWidget(self._lbl_tit)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._page_empleados())                      # 0 — Empleados
        # LAZY LOADING (regla de arquitectura): cada pestaña laboral monta un formulario pesado
        # (consulta de empleados y, en Contratos, el motor del asistente). Construirlas todas al abrir
        # RRHH congelaba la carga. Se difieren: se crea un placeholder y el contenido real se monta en
        # el PRIMER acceso a la pestaña (ver _ir).
        self._lazy_laboral = {}
        for i, (ic, lab, tipo, sub) in enumerate(self._LABORAL_SECCIONES, start=1):  # 1..9
            ph = QWidget(); phl = QVBoxLayout(ph); phl.setContentsMargins(0, 0, 0, 0)
            self.stack.addWidget(ph)
            self._lazy_laboral[i] = (phl, ic, lab, tipo, sub)
        # RRHH Pro (evaluaciones/formación/reclutamiento/turnos/anticipos): mismo patrón de carga
        # perezosa que las pestañas laborales — placeholder ahora, contenido real en el primer acceso.
        self._idx_pro = len(self._LABORAL_SECCIONES) + 1   # 10
        ph_pro = QWidget(); self._phl_pro = QVBoxLayout(ph_pro); self._phl_pro.setContentsMargins(0, 0, 0, 0)
        self.stack.addWidget(ph_pro)
        rcol.addWidget(self.stack, 1)
        root.addWidget(right, 1)

        self._ir(0)
        self._cargar()

        # Pre-carga de IMPORTS en segundo plano (no construye widgets → no bloquea la UI ni causa
        # tirones). Calienta los módulos pesados que usan los formularios (reportlab/fuentes de los
        # generadores PDF y el motor del asistente) para que el PRIMER clic en cada pestaña solo
        # cueste montar sus widgets. Hilo demonio, silencioso ante cualquier fallo.
        self._precargar_imports_en_segundo_plano()

        # NOTA: el pre-cacheo en segundo plano de las pestañas laborales (construirlas todas tras
        # abrir, para que el cambio de pestaña fuera instantáneo) se RETIRÓ: cada formulario
        # (`DocumentoInlineForm` y similares) hace una consulta a BD síncrona en su propio __init__
        # (`_cargar_empleados`), así que el "pre-cacheo ocioso" en realidad bloqueaba el hilo de
        # eventos una vez por pestaña — la ventana se veía abierta pero no respondía a clics/teclado
        # durante varios segundos tras abrir RRHH. Ahora cada pestaña laboral se construye
        # ÚNICAMENTE en su primer acceso real (ver `_ir`/`_construir_laboral`), con un pequeño coste
        # solo en ese primer clic, en vez de congelar toda la ventana de antemano.

        # P3 (UX-TPV-01): sidebar colapsable con persistencia por usuario.
        try:
            from src.gui.sidebar_colapsable import instalar_sidebar_colapsable
            if getattr(self, "sidebar", None) is not None:
                instalar_sidebar_colapsable(self, self.sidebar, usuario=self.usuario, clave="rrhh")
        except Exception:
            pass

    # ── Sidebar + navegación ─────────────────────────────────────────────────
    def _build_sidebar(self):
        from PyQt6.QtWidgets import QScrollArea
        from src.gui.foundation.tokens import qss_scrollbar
        wrap = QFrame(); wrap.setObjectName("sw"); wrap.setFixedWidth(280); self.sidebar = wrap
        wrap.setStyleSheet(f"#sw{{background:{_SIDEBAR};}}")
        outer = QVBoxLayout(wrap); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        # El contenido de la sidebar va dentro de un QScrollArea con la scrollbar ESTÁNDAR del
        # software (turquesa) — mismo patrón que Contabilidad/Tesorería/Seguridad. SIN esto, con
        # 12 secciones a 55px cada una el sidebar entero (sin scroll) obliga a que la VENTANA pida
        # un alto mínimo mayor que el de pantallas de portátil habituales (1366×768): Windows no
        # puede darle ese alto y devuelve una geometría más baja de la pedida, recortando el
        # contenido de las pestañas (bug real confirmado por el log: "Unable to set geometry
        # 1366x797 ... Resulting geometry: 1366x728").
        scroll = QScrollArea(wrap); scroll.setObjectName("sb_scroll")
        scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"QScrollArea#sb_scroll{{background:{_SIDEBAR};border:none;}}")
        scroll.verticalScrollBar().setStyleSheet(qss_scrollbar())

        content = QWidget(); content.setObjectName("sb_content")
        content.setStyleSheet(f"#sb_content{{background:{_SIDEBAR};}}")
        lay = QVBoxLayout(content); lay.setContentsMargins(0, 22, 0, 16); lay.setSpacing(2)
        cab = QLabel("SMART RRHH")   # título de marca de la sidebar (igual en todos los idiomas)
        cab.setStyleSheet("color:#FFFFFF;padding:0 0 24px 28px;font-size:16px;font-weight:900;"
                          "letter-spacing:2px;background:transparent;")
        lay.addWidget(cab)
        self._sb_btns = []
        secciones = ([("👥", "Empleados")] + [(ic, lab) for ic, lab, _, _ in self._LABORAL_SECCIONES]
                    + [("🚀", "Seguimiento Empleados")])
        # Reglas de acceso (Seguridad · Pestañas): con acceso completo al módulo, todas visibles por
        # defecto; sin acceso completo (entró solo por una concesión de pestaña suelta), solo la(s)
        # concedida(s) — mismo criterio que Contabilidad/Tesorería/Clientes/BI/Seguridad.
        from src.services.seguridad import pestanas_app
        _tiene_completo = pestanas_app.tiene_modulo_completo("rrhh", self.usuario, False)
        _slugs = ["empleados", "contratos", "nominas", "altas", "bajas", "finiquitos",
                 "cert_empresa", "cert_laboral", "cartas_despido", "periodo_prueba",
                 "modelo_145", "rrhh_pro"]
        for i, (ic, lab) in enumerate(secciones):
            b = QPushButton(f"   {lab.upper()}")   # sin icono, mayúsculas
            # Mismo tamaño de texto (12px, base) que el resto de sidebars de la app — consistencia
            # exigida explícitamente; la variante +2pt (`lg="true"`) se retira aquí.
            b.setObjectName("btn_sidebar")   # estilo global (acento, hover swap, sin brillo)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setCheckable(True); b.setFixedHeight(55)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(lambda _=False, idx=i: self._ir(idx))
            if not pestanas_app.visible(f"rrhh.{_slugs[i]}", self.usuario, _tiene_completo):
                b.setVisible(False)
            self._sb_btns.append(b); lay.addWidget(b)
        # Badges de actividad (Centro de Actividad): círculo rojo sobre "Nóminas" con el nº de
        # eventos pendientes (NOMINA_GENERADA), calculado al vuelo — mismo patrón sidebar+stack
        # que `instalar_badges_sidebar` ya soporta (menú principal usa la variante QTabWidget).
        self._gestor_badges = instalar_badges_sidebar(
            self._sb_btns, self._contar_badges_sidebar, self._al_entrar_seccion_badge)
        self._timer_badges = QTimer(self)
        self._timer_badges.timeout.connect(self._gestor_badges.refrescar)
        self._timer_badges.start(60000)
        lay.addStretch(1)
        if self._volver:
            lay.addWidget(_btn_salir_sidebar(self._volver))
        scroll.setWidget(content)
        outer.addWidget(scroll)
        return wrap

    _SS_OFF = (f"QPushButton{{background:transparent;color:#FFFFFF;text-align:left;"
               f"padding:8px 8px 8px 24px;border:none;border-left:4px solid transparent;"
               f"border-radius:0px;font-size:13px;font-weight:900;}}"
               f"QPushButton:hover{{background:#FFFFFF;color:{_SIDEBAR};}}")
    _SS_ON = (f"QPushButton{{background:#1A2230;color:{_CIAN};text-align:left;"
              f"padding:8px 8px 8px 24px;border:none;border-left:4px solid {_CIAN};"
              f"border-radius:0px;font-size:13px;font-weight:900;}}")

    def _precargar_imports_en_segundo_plano(self):
        """Importa (en un hilo demonio) los módulos pesados de los formularios laborales para que el
        primer acceso a cada pestaña no pague el coste de importación (reportlab/fuentes/motor). Solo
        realiza imports: no crea ni toca widgets Qt. Silencioso ante cualquier error."""
        import threading

        def _warm():
            # "src.gui.gestion_usuarios" (Configuración) SE RETIRA de esta lista: es la MISMA
            # importación en segundo plano que YA hace `menu_principal._precargar_modulos_pesados`
            # — con las dos activas a la vez (se solapan si el usuario visita RRHH poco después de
            # abrir el menú), Configuración podía dejar de abrir con un crash nativo. Se deja SOLO
            # la copia de `menu_principal.py` (la que ya existía antes de esta ronda de cambios)
            # para aislar si el problema era justamente ese doble import concurrente.
            for mod in (
                "src.rrhh.maestros",
                "src.rrhh.documents.render.estilo_pdf",       # reportlab + fuentes (base común)
                "src.rrhh.documents.render.nomina_pdf",
                "src.gui.rrhh_doc_inline",
                "src.gui.rrhh_nomina_inline",
                "src.gui.rrhh_contrato_inline",
                "src.gui.rrhh_modelo145_inline",
            ):
                try:
                    __import__(mod)
                except Exception:
                    pass

        try:
            threading.Thread(target=_warm, name="rrhh-warm-imports", daemon=True).start()
        except Exception:
            logger.debug("pre-carga de imports RRHH no disponible")

    def _construir_laboral(self, idx):
        """Monta el contenido real de una pestaña laboral (lazy loading) si aún no está construida.
        La apertura de RRHH no construye ninguna (solo Empleados) → abre al instante; cada formulario
        se monta por pre-cacheo en segundo plano o, si el usuario se adelanta, en su primer clic."""
        lz = getattr(self, "_lazy_laboral", {}).pop(idx, None)
        if lz:
            phl, ic, lab, tipo, sub = lz
            phl.addWidget(self._page_laboral(ic, lab, tipo, sub))
            return
        if idx == self._idx_pro and self._phl_pro.count() == 0:
            self._phl_pro.addWidget(self._page_rrhh_pro())

    def _ir(self, idx):
        # Lazy loading: construir el contenido real de la pestaña laboral en su primer acceso
        # (si el pre-cacheo aún no la ha montado).
        self._construir_laboral(idx)
        self.stack.setCurrentIndex(idx)
        for i, b in enumerate(self._sb_btns):
            b.setChecked(i == idx)   # estilo via QSS global #btn_sidebar:checked
        # Refresca el desplegable de empleados del formulario inline (si lo tiene y no hay selección en
        # curso), para que muestre los empleados creados/editados en la pestaña Empleados sin reabrir el
        # módulo (los inline lo cargaban solo al construirse).
        try:
            pagina = self.stack.widget(idx)
            for form in pagina.findChildren(QWidget):
                if hasattr(form, "_cargar_empleados") and hasattr(form, "cb_emp"):
                    if form.cb_emp.currentIndex() <= 0:   # sin empleado elegido → recarga la lista
                        form._cargar_empleados()
                    break
        except Exception:
            pass

    # ── Página 0: Empleados (registro/creación) ──────────────────────────────
    def _page_empleados(self):
        # Sin lista de "documentos/registros del empleado seleccionado" (auditoría lista-por-
        # pestaña, ver informe de la tarea): esta pestaña NO tiene el patrón "desplegable arriba +
        # formulario abajo que genera un documento/registro" — es el listado/búsqueda MAESTRO de
        # empleados en sí (con filtros propios), y el botón "Expediente" ya abre el visor completo
        # de todo el historial de CADA empleado (contratos/nóminas/finiquitos/vacaciones/
        # ausencias/control horario/documentos, ver `ExpedienteDialog`). Forzar aquí una lista
        # filtrada sería redundante con ese expediente.
        w = QWidget(); col = QVBoxLayout(w); col.setContentsMargins(0, 0, 0, 0); col.setSpacing(12)
        tb = QHBoxLayout()
        self.in_buscar = _inp("Buscar nombre / apellidos / NIF…")
        self.in_buscar.returnPressed.connect(self._cargar)
        self.cb_filtro = _combo([("Todos", ""), ("Activos", "activo"), ("Bajas", "baja"),
                                 ("Suspendidos", "suspendido"), ("Excedencias", "excedencia")], "")
        self.cb_filtro.setMinimumWidth(160)   # evita texto cortado en el desplegable
        self.cb_filtro.currentIndexChanged.connect(self._cargar)
        tb.addWidget(self.in_buscar, 2); tb.addWidget(self.cb_filtro, 1)
        # Buscar/Editar/Control horario con el mismo diseño turquesa que Nuevo/Expediente.
        tb.addWidget(_btn("🔍", self._cargar, primary=True))
        tb.addWidget(_btn("Nuevo", self._nuevo, primary=True))
        tb.addWidget(_btn("Editar", self._editar, primary=True))
        # Vac./Ausencias: mismo diseño que Nuevo/Expediente pero en AMARILLO.
        btn_vac = _btn("Vac./Ausencias", self._gestion_laboral)
        btn_vac.setStyleSheet(
            f"QPushButton{{background:{_BG2};color:{_AMARILLO};border:2px solid {_AMARILLO};"
            f"border-radius:8px;font-weight:900;font-size:12px;padding:0 14px;font-family:'Segoe UI';}}"
            f"QPushButton:hover{{background:{_AMARILLO};color:{_BG};border-color:{_AMARILLO};}}")
        tb.addWidget(btn_vac)
        tb.addWidget(_btn("Control horario", self._control_horario, primary=True))
        tb.addWidget(_btn("Expediente", self._expediente, primary=True))
        col.addLayout(tb)
        # Aviso INLINE (no modal): evita el cuelgue de diálogos modales con el audio de SOMA y avisa
        # cuando se pulsa una acción sin haber seleccionado un empleado.
        self.lbl_msg = QLabel(""); self.lbl_msg.setStyleSheet(f"color:{_AMARILLO};font-weight:900;font-size:12px;")
        self.lbl_msg.setVisible(False)
        col.addWidget(self.lbl_msg)
        self.tbl = _tabla(["Nombre", "Apellidos", "NIF/NIE", "Puesto", "Convenio", "Estado", "Alta"])
        self.tbl.doubleClicked.connect(self._expediente)
        col.addWidget(self.tbl)
        return w

    def _flash(self, msg, color=None):
        """Aviso inline temporal en la pestaña Empleados (sin diálogos modales)."""
        color = color or _AMARILLO
        if hasattr(self, "lbl_msg") and self.lbl_msg is not None:
            self.lbl_msg.setStyleSheet(f"color:{color};font-weight:900;font-size:12px;")
            self.lbl_msg.setText(f"ℹ️  {msg}")
            self.lbl_msg.setVisible(True)
            QTimer.singleShot(3500, lambda: (self.lbl_msg.setVisible(False)
                                             if hasattr(self, "lbl_msg") and self.lbl_msg else None))

    # ── Páginas 1..9: funciones del módulo laboral (lanzan el wizard existente) ──
    def _page_laboral(self, icono, titulo, tipo, subtipo=None):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0); ly.setSpacing(14)
        cab = QLabel(f"{icono}  {titulo.upper()}")
        cab.setStyleSheet(f"color:{_CIAN};font-size:18px;font-weight:900;")
        ly.addWidget(cab)

        # CONTRATOS: formulario INLINE (reutiliza el motor de generación del asistente, sin tocarlo).
        if tipo == "CONTRATO":
            try:
                from src.gui.rrhh_contrato_inline import ContratoInlineForm
                ly.addWidget(ContratoInlineForm(self._id_empresa, parent=w), 1)
                return w
            except Exception as e:
                logger.error("formulario inline contrato: %s", e)  # fallback al asistente si falla

        # NÓMINAS: formulario INLINE (los campos se rellenan directamente en la pestaña, sin asistente).
        if tipo == "NÓMINA":
            try:
                from src.gui.rrhh_nomina_inline import NominaInlineForm
                ly.addWidget(NominaInlineForm(self._id_empresa, parent=w), 1)
                return w
            except Exception as e:
                logger.error("formulario inline nómina: %s", e)  # fallback al asistente si algo falla

        # MODELO FISCAL EMPLEADOS (Modelo 145 AEAT): formulario INLINE (Fase B2, IRPF).
        if tipo == "MODELO145":
            try:
                from src.gui.rrhh_modelo145_inline import Modelo145InlineForm
                ly.addWidget(Modelo145InlineForm(self._id_empresa, parent=w), 2)
                # Impuestos y tasas de EMPRESA (IBI/autónomos/tasas…): complemento company-wide a
                # este mismo tab fiscal, debajo del formulario por empleado — registra en el MISMO
                # motor `registrar_gasto` que "Libro de Gastos" de Contabilidad (ver
                # `rrhh_impuestos_inline.py`), nunca una tabla/motor paralelo.
                from src.gui.rrhh_impuestos_inline import ImpuestoEmpresaInlineForm
                ly.addWidget(ImpuestoEmpresaInlineForm(self._id_empresa, parent=w), 1)
                return w
            except Exception as e:
                logger.error("formulario inline modelo 145: %s", e)  # fallback al asistente si falla

        # ALTAS LABORALES: formulario INLINE de REGISTRO (sin PDF — upsert directo sobre
        # `rrhh_empleados`, ver `rrhh_alta_inline.py`). NO cae al asistente de PDF si falla: esta
        # pestaña es pura registración, nunca debe generar un documento.
        if tipo == "ALTA":
            try:
                ly.addWidget(self._form_alta(w), 1)
            except Exception as e:
                logger.error("formulario de registro de alta: %s", e)
                ly.addWidget(self._error_carga_formulario())
            return w

        # BAJAS LABORALES: formulario INLINE de REGISTRO (sin PDF — escribe en `rrhh_ausencias`
        # vía `ausencias_servicio`, ver `rrhh_baja_inline.py`). NO cae al asistente de PDF si
        # falla: esta pestaña es pura registración, nunca debe generar un documento.
        if tipo == "BAJA":
            try:
                ly.addWidget(self._form_baja(w), 1)
            except Exception as e:
                logger.error("formulario de registro de baja: %s", e)
                ly.addWidget(self._error_carga_formulario())
            return w

        # FINIQUITOS: formulario INLINE genérico (con importes/totales calculados en el PDF).
        if tipo == "FINIQUITO":
            try:
                ly.addWidget(self._form_finiquito(w), 1)
                return w
            except Exception as e:
                logger.error("formulario inline finiquito: %s", e)  # fallback al asistente si algo falla

        # CERTIFICADO DE EMPRESA (SEPE): formulario INLINE con tabla mensual de bases.
        if tipo == "CERTIFICADO":
            try:
                ly.addWidget(self._form_cert_empresa(w), 1)
                return w
            except Exception as e:
                logger.error("formulario inline cert. empresa: %s", e)  # fallback al asistente

        # CERTIFICADO LABORAL: formulario INLINE genérico.
        if tipo == "CERT LABORAL":
            try:
                ly.addWidget(self._form_cert_laboral(w), 1)
                return w
            except Exception as e:
                logger.error("formulario inline cert. laboral: %s", e)  # fallback al asistente

        # CARTA DE DESPIDO (no periodo de prueba): formulario INLINE genérico.
        if tipo == "CARTA DESPIDO" and subtipo != "PERÍODO DE PRUEBA":
            try:
                ly.addWidget(self._form_carta_despido(w), 1)
                return w
            except Exception as e:
                logger.error("formulario inline carta despido: %s", e)  # fallback al asistente

        # CARTA DE NO SUPERACIÓN DEL PERÍODO DE PRUEBA: formulario INLINE genérico.
        if tipo == "CARTA DESPIDO" and subtipo == "PERÍODO DE PRUEBA":
            try:
                ly.addWidget(self._form_periodo_prueba(w), 1)
                return w
            except Exception as e:
                logger.error("formulario inline periodo prueba: %s", e)  # fallback al asistente

        texto = _PRUEBA_DESC if subtipo == "PERÍODO DE PRUEBA" else _LABORAL_DESC.get(tipo, "")
        desc = QLabel(texto)
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color:{_DIM};font-size:13px;")
        ly.addWidget(desc)
        ly.addSpacing(8)
        btn = _btn(f"ABRIR ASISTENTE · {titulo.upper()}",
                   lambda _=False, t=tipo, s=subtipo: self._abrir_wizard_laboral(t, s), primary=True)
        ly.addWidget(btn)
        ly.addStretch()
        return w

    def _error_carga_formulario(self):
        lbl = QLabel("No se pudo cargar el formulario de registro. Revisa el registro de errores.")
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color:#F85149;font-weight:700;font-size:13px;")
        return lbl

    def _form_alta(self, parent):
        """Formulario inline de REGISTRO de ALTA LABORAL (sin PDF): upsert directo sobre
        `rrhh_empleados` — mismo backend que la pestaña Empleados (`EmpleadoFormDialog`). Ver
        `rrhh_alta_inline.AltaLaboralForm`."""
        from src.gui.rrhh_alta_inline import AltaLaboralForm
        return AltaLaboralForm(self._id_empresa, parent=parent)

    def _form_baja(self, parent):
        """Formulario inline de REGISTRO de BAJA/AUSENCIA LABORAL (sin PDF): escribe en
        `rrhh_ausencias` vía `src.rrhh.ausencias_servicio` — el MISMO motor real que usa el
        diálogo "Vac./Ausencias" de la pestaña Empleados (`GestionLaboralDialog._tab_aus`). Ver
        `rrhh_baja_inline.BajaLaboralForm`."""
        from src.gui.rrhh_baja_inline import BajaLaboralForm
        return BajaLaboralForm(self._id_empresa, parent=parent)

    def _form_finiquito(self, parent):
        """Formulario inline de FINIQUITO: selección de empleado + "Calcular" (motor
        `finiquito_servicio`, reutiliza `nomina_motor`/`nomina_servicio` — salario proporcional,
        vacaciones no disfrutadas, pagas extra pendientes y horas de bolsa pendientes se calculan
        automáticamente desde los datos reales del empleado) + "Generar finiquito (PDF)"."""
        from src.gui.rrhh_finiquito_inline import FiniquitoInlineForm
        return FiniquitoInlineForm(self._id_empresa, parent=parent)

    def _form_cert_empresa(self, parent):
        """Formulario inline del CERTIFICADO DE EMPRESA (SEPE) con tabla mensual de bases de cotización."""
        from src.gui.rrhh_doc_inline import DocumentoInlineForm
        from src.rrhh.documents.render import certificado_empresa_pdf as C

        secciones = [
            ("Datos del trabajador/a", C.TRABAJADOR_CAMPOS),
            ("Relación laboral", C.RELACION_CAMPOS),
            ("Bases de cotización (relación mensual — hasta 6 meses)",
             {"tabla": ("bases_mensuales", C.BASES_COLUMNAS, 6)}),
            ("Vacaciones", C.VACACIONES_CAMPOS),
            ("Causa del cese", [C.CAUSA_CESE_CAMPO]),
        ]

        def _autollenar(emp, dc, setter):
            self._autollenar_maestros(emp, setter)  # datos maestros unificados

        return DocumentoInlineForm(
            self._id_empresa, secciones, C.generar_certificado_empresa_pdf,
            tipo_doc="certificado_empresa", autollenar_fn=_autollenar,
            campos_combo={"motivo_baja": C.MOTIVOS_BAJA, "causa_cese": C.CAUSAS_CESE},
            campos_empresa=C.EMPRESA_CAMPOS, parent=parent)

    def _form_cert_laboral(self, parent):
        """Formulario inline del CERTIFICADO LABORAL (genérico) con funciones multilínea y finalidad."""
        from src.gui.rrhh_doc_inline import DocumentoInlineForm
        from src.rrhh.documents.render import cert_laboral_pdf as L

        secciones = [
            ("Datos del trabajador/a", L.TRABAJADOR_CAMPOS),
            ("Contenido del certificado", L.CONTENIDO_CAMPOS + [L.FUNCIONES_CAMPO]),
            ("Finalidad", [L.FINALIDAD_CAMPO]),
            ("Expedición y firma", L.EXPEDICION_CAMPOS),
        ]

        def _autollenar(emp, dc, setter):
            self._autollenar_maestros(emp, setter)  # datos maestros unificados
            if emp.get("municipio"):
                setter("lugar", emp.get("municipio"))

        return DocumentoInlineForm(
            self._id_empresa, secciones, L.generar_cert_laboral_pdf, tipo_doc="certificado_laboral",
            autollenar_fn=_autollenar, campos_grandes=("funciones",),
            campos_combo={"finalidad": L.FINALIDADES},
            campos_empresa=L.EMPRESA_CAMPOS, parent=parent)

    def _form_carta_despido(self, parent):
        """Formulario inline de la CARTA DE DESPIDO (genérico) con relato de hechos y firmas."""
        from src.gui.rrhh_doc_inline import DocumentoInlineForm
        from src.rrhh.documents.render import carta_despido_pdf as D

        secciones = [
            ("Datos del trabajador/a", D.TRABAJADOR_CAMPOS),
            ("Encabezado", D.ENCABEZADO_CAMPOS),
            ("Datos laborales", D.DATOS_LABORALES_CAMPOS),
            ("Comunicación de despido", D.COMUNICACION_CAMPOS),
            ("Relato de los hechos (cronológico y detallado)", [D.HECHOS_CAMPO]),
            ("Liquidación", D.LIQUIDACION_CAMPOS),
            ("Firmas", [("recibi_estado", "Estado del recibí"), D.TESTIGOS_CAMPO]),
        ]

        def _autollenar(emp, dc, setter):
            self._autollenar_maestros(emp, setter)  # datos maestros unificados

        return DocumentoInlineForm(
            self._id_empresa, secciones, D.generar_carta_despido_pdf, tipo_doc="carta_despido",
            autollenar_fn=_autollenar, campos_grandes=("hechos",),
            campos_combo={"tipo_despido": D.TIPOS_DESPIDO, "recibi_estado": D.RECIBI_ESTADOS},
            campos_empresa=D.EMPRESA_CAMPOS, parent=parent)

    def _form_periodo_prueba(self, parent):
        """Formulario inline de la CARTA DE NO SUPERACIÓN DEL PERÍODO DE PRUEBA (art. 14 ET)."""
        from src.gui.rrhh_doc_inline import DocumentoInlineForm
        from src.rrhh.documents.render import periodo_prueba_pdf as P

        secciones = [
            ("Datos del trabajador/a", P.TRABAJADOR_CAMPOS),
            ("Datos del contrato", P.CONTRATO_CAMPOS),
            ("Comunicación", P.COMUNICACION_CAMPOS),
            ("Explicación (opcional — no obligatoria en período de prueba)", [P.EXPLICACION_CAMPO]),
            ("Devolución de bienes de la empresa", P.BIENES_CAMPOS),
            ("Firmas", [("recibi_estado", "Estado del recibí"),
                        ("representante_empresa", "Representante de la empresa"),
                        ("cargo", "Cargo"), P.TESTIGOS_CAMPO]),
        ]

        def _autollenar(emp, dc, setter):
            self._autollenar_maestros(emp, setter)  # datos maestros unificados

        bienes_combo = {c[0]: P.ESTADO_BIEN for c in P.BIENES_CAMPOS}
        return DocumentoInlineForm(
            self._id_empresa, secciones, P.generar_periodo_prueba_pdf, tipo_doc="periodo_prueba",
            autollenar_fn=_autollenar, campos_grandes=("explicacion",),
            campos_combo={"recibi_estado": P.RECIBI_ESTADOS, **bienes_combo},
            campos_empresa=P.EMPRESA_CAMPOS, parent=parent)

    def _autollenar_maestros(self, emp, setter):
        """Autocompleta cualquier documento desde la capa de datos MAESTROS unificada
        (Empresa · Trabajador · Contrato · Nómina · Incidencias · Extinción). Cada formulario
        recoge solo las claves que tiene; el resto se ignora. Fuente única = coherencia."""
        try:
            from src.rrhh import maestros
            for clave, valor in maestros.campos_documento(emp, self._id_empresa()).items():
                setter(clave, valor)
        except Exception as e:
            logger.debug("autollenar maestros: %s", e)

    def _id_empresa(self):
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            return None

    def _contar_badges_sidebar(self):
        """Nº de eventos pendientes (Centro de Actividad) para el botón "Nóminas" del sidebar.
        Best-effort: ante cualquier error, sin badges."""
        try:
            from src.services.actividad import badges as actividad_badges
            counts = actividad_badges.contar_subtabs(
                "rrhh", usuario=self.usuario, id_empresa=self._id_empresa())
        except Exception:
            return {}
        n = counts.get("nominas", 0)
        return {self._IDX_NOMINAS: n} if n else {}

    def _al_entrar_seccion_badge(self, indice):
        """Marca como visto el badge de "Nóminas" al pulsar ese botón del sidebar (además del
        cambio de página que ya gestiona `_ir`, conectado por separado)."""
        if indice != self._IDX_NOMINAS:
            return
        try:
            from src.services.actividad import badges as actividad_badges
            actividad_badges.marcar_visto(
                "rrhh.nominas", usuario=self.usuario, id_empresa=self._id_empresa())
            self._gestor_badges.refrescar()
        except Exception:
            pass

    # ── Documentación LABORAL (migrada): reutiliza el wizard existente (lógica intacta) ──
    def _abrir_wizard_laboral(self, tipo, subtipo=None):
        try:
            from src.gui.gestion_usuarios import _WizardDocumentoFiscal
            _WizardDocumentoFiscal(tipo_inicial=tipo, parent=self,
                                   subtipo_inicial=subtipo).exec()
        except Exception as e:
            logger.error("wizard laboral: %s", e)

    # ── RRHH Pro: evaluaciones/formación/reclutamiento/turnos/anticipos ────────
    # Motor en `src.services.rrhh.rrhh_pro`/`nominas_pro` — existía sin ningún frontend antes de
    # esta auditoría. GUI = orquestación pura; toda la lógica sigue en esos servicios.
    def _page_rrhh_pro(self):
        # "Seguimiento Empleados" en el sidebar. Sin lista "por empleado seleccionado" (auditoría
        # lista-por-pestaña, ver informe de la tarea): cada una de sus 5 sub-pestañas
        # (Evaluaciones/Formación/Reclutamiento/Turnos/Anticipos) ya tiene su propia tabla
        # `tbl_pro_*` que lista TODOS los registros de la EMPRESA (con una columna "Empleado"
        # propia) — no el patrón "desplegable de empleado arriba + formulario abajo" de las demás
        # pestañas laborales, y ninguna genera un PDF que reabrir. Filtrar esas tablas al último
        # empleado tocado sería una regresión (dejarían de servir como panel de gestión conjunta).
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 0, 0, 0)
        tabs = QTabWidget()
        tabs.setStyleSheet(f"QTabBar::tab{{background:{_SIDEBAR};color:{_DIM};padding:8px 14px;}}"
                           f"QTabBar::tab:selected{{color:{_CIAN};}}"
                           f"QTabWidget::pane{{border:none;}}")
        tabs.addTab(self._tab_pro_evaluaciones(), "Evaluaciones")
        tabs.addTab(self._tab_pro_formacion(), "Formación")
        tabs.addTab(self._tab_pro_reclutamiento(), "Reclutamiento")
        tabs.addTab(self._tab_pro_turnos(), "Turnos")
        tabs.addTab(self._tab_pro_anticipos(), "Anticipos")
        try:
            from src.gui.transiciones import instalar_transicion_tabs
            instalar_transicion_tabs(tabs)
        except Exception:
            pass
        ly.addWidget(tabs)
        return w

    def _combo_empleados_pro(self):
        from src.rrhh.db import empleados as EMP_DB
        emps = EMP_DB.listar_empleados(self._id_empresa())
        opciones = [(f"{e.get('nombre', '')} {e.get('apellidos', '') or ''}".strip() or f"#{e['id']}",
                    e["id"]) for e in emps]
        # Desplegable vacío = de verdad no hay empleados dados de alta todavía (no es un bug): se
        # deja un primer elemento explícito en vez de una lista en blanco indistinguible de un fallo.
        return _combo(opciones or [("— Sin empleados dados de alta —", None)])

    def _nombres_empleados_pro(self):
        from src.rrhh.db import empleados as EMP_DB
        return {e["id"]: f"{e.get('nombre', '')} {e.get('apellidos', '') or ''}".strip()
               for e in EMP_DB.listar_empleados(self._id_empresa())}

    # · Evaluaciones de desempeño ·
    def _tab_pro_evaluaciones(self):
        w = QWidget(); ly = QVBoxLayout(w)
        f = QHBoxLayout()
        self.pro_ev_emp = self._combo_empleados_pro()
        self.pro_ev_periodo = _inp("Periodo (p.ej. 2026-S1)")
        self.pro_ev_evaluador = _inp("Evaluador")
        for wd in (self.pro_ev_emp, self.pro_ev_periodo, self.pro_ev_evaluador):
            f.addWidget(wd)
        ly.addLayout(f)
        f2 = QHBoxLayout()
        self.pro_ev_comp = _inp("Competencias: clave=valor, clave=valor…")
        self.pro_ev_coment = _inp("Comentarios")
        f2.addWidget(self.pro_ev_comp); f2.addWidget(self.pro_ev_coment)
        ly.addLayout(f2)
        self.tbl_pro_ev = _tabla(["ID", "Empleado", "Periodo", "Evaluador", "Estado", "Puntuación"])
        self.tbl_pro_ev.cellClicked.connect(self._pro_sel_evaluacion)
        ly.addWidget(self.tbl_pro_ev)
        b = QHBoxLayout()
        b.addWidget(_btn("Crear evaluación", self._pro_crear_evaluacion, primary=True))
        b.addWidget(_btn("Cerrar evaluación seleccionada", self._pro_cerrar_evaluacion, danger=True))
        b.addWidget(_btn_cargando("🔄 Actualizar", self._pro_cargar_evaluaciones, primary=True))
        b.addStretch()
        ly.addLayout(b)
        self._pro_ev_sel = None
        self._pro_cargar_evaluaciones()
        return w

    def _pro_cargar_evaluaciones(self):
        from src.services.rrhh import rrhh_pro as RP
        nombres = self._nombres_empleados_pro()
        self._pro_evs = RP.evaluaciones(self._id_empresa())
        self.tbl_pro_ev.setRowCount(len(self._pro_evs))
        for i, r in enumerate(self._pro_evs):
            vals = [r.get("id"), nombres.get(r.get("id_empleado"), r.get("id_empleado")),
                    r.get("periodo"), r.get("evaluador"), r.get("estado"), r.get("puntuacion")]
            for j, v in enumerate(vals):
                self.tbl_pro_ev.setItem(i, j, _it(v))
        self._pro_ev_sel = None

    def _pro_sel_evaluacion(self, row, _c):
        try:
            self._pro_ev_sel = self._pro_evs[row]
        except (IndexError, AttributeError):
            self._pro_ev_sel = None

    def _pro_crear_evaluacion(self):
        from src.services.rrhh import rrhh_pro as RP
        eid = self.pro_ev_emp.currentData()
        if not eid:
            _info_msg(self, "Evaluaciones", "No hay empleados disponibles.")
            return
        competencias = {}
        for par in self.pro_ev_comp.text().split(","):
            if "=" not in par:
                continue
            k, v = par.split("=", 1); k = k.strip()
            if not k:
                continue
            try:
                competencias[k] = float(v.strip().replace(",", "."))
            except ValueError:
                competencias[k] = v.strip()
        rid = RP.crear_evaluacion(eid, periodo=self.pro_ev_periodo.text().strip() or None,
                                  evaluador=self.pro_ev_evaluador.text().strip() or None,
                                  competencias=competencias, comentarios=self.pro_ev_coment.text().strip() or None,
                                  id_empresa=self._id_empresa())
        if rid:
            _info_msg(self, "Evaluaciones", "Evaluación creada correctamente.")
            self.pro_ev_periodo.clear(); self.pro_ev_evaluador.clear()
            self.pro_ev_comp.clear(); self.pro_ev_coment.clear()
            self._pro_cargar_evaluaciones()
        else:
            _error_msg(self, "Evaluaciones", "No se pudo crear la evaluación.")

    def _pro_cerrar_evaluacion(self):
        from src.services.rrhh import rrhh_pro as RP
        if not self._pro_ev_sel:
            _info_msg(self, "Evaluaciones", "Selecciona primero una evaluación en la tabla.")
            return
        r = RP.cerrar_evaluacion(self._pro_ev_sel["id"], id_empresa=self._id_empresa())
        if r.get("ok"):
            _info_msg(self, "Evaluaciones",
                                    f"Evaluación cerrada. Puntuación media: {r.get('puntuacion', '—')}")
            self._pro_cargar_evaluaciones()
        else:
            _error_msg(self, "Evaluaciones", r.get("motivo") or "No se pudo cerrar la evaluación.")

    # · Formación / capacitación ·
    def _tab_pro_formacion(self):
        w = QWidget(); ly = QVBoxLayout(w)
        f = QHBoxLayout()
        self.pro_fo_titulo = _inp("Título del curso/formación")
        self.pro_fo_tipo = _combo([("Curso", "curso"), ("Taller", "taller"),
                                   ("Certificación", "certificacion"), ("Online", "online")])
        self.pro_fo_proveedor = _inp("Proveedor")
        for wd in (self.pro_fo_titulo, self.pro_fo_tipo, self.pro_fo_proveedor):
            f.addWidget(wd)
        ly.addLayout(f)
        f2 = QHBoxLayout()
        self.pro_fo_horas = _inp("Horas")
        self.pro_fo_coste = _inp("Coste (€)")
        self.pro_fo_ini = _inp("Inicio AAAA-MM-DD")
        self.pro_fo_fin = _inp("Fin AAAA-MM-DD")
        for wd in (self.pro_fo_horas, self.pro_fo_coste, self.pro_fo_ini, self.pro_fo_fin):
            f2.addWidget(wd)
        f2.addWidget(_btn("Crear formación", self._pro_crear_formacion, primary=True))
        ly.addLayout(f2)
        self.tbl_pro_fo = _tabla(["ID", "Título", "Tipo", "Proveedor", "Horas", "Coste", "Estado"])
        self.tbl_pro_fo.cellClicked.connect(self._pro_sel_formacion)
        ly.addWidget(self.tbl_pro_fo)
        f3 = QHBoxLayout()
        self.pro_fo_emp = self._combo_empleados_pro()
        f3.addWidget(QLabel("Empleado:")); f3.addWidget(self.pro_fo_emp)
        f3.addWidget(_btn("Inscribir en formación seleccionada", self._pro_inscribir_formacion, primary=True))
        self.pro_fo_aprov = _inp("Aprovechamiento (0-100)")
        f3.addWidget(self.pro_fo_aprov)
        f3.addWidget(_btn("Registrar aprovechamiento", self._pro_aprovechamiento_formacion, primary=True))
        ly.addLayout(f3)
        self._pro_fo_sel = None
        self._pro_cargar_formaciones()
        return w

    def _pro_cargar_formaciones(self):
        from src.services.rrhh import rrhh_pro as RP
        self._pro_fos = RP.formaciones(self._id_empresa())
        self.tbl_pro_fo.setRowCount(len(self._pro_fos))
        for i, r in enumerate(self._pro_fos):
            vals = [r.get("id"), r.get("titulo"), r.get("tipo"), r.get("proveedor"),
                    r.get("horas"), r.get("coste"), r.get("estado")]
            for j, v in enumerate(vals):
                self.tbl_pro_fo.setItem(i, j, _it(v))
        self._pro_fo_sel = None

    def _pro_sel_formacion(self, row, _c):
        try:
            self._pro_fo_sel = self._pro_fos[row]
        except (IndexError, AttributeError):
            self._pro_fo_sel = None

    def _pro_crear_formacion(self):
        from src.services.rrhh import rrhh_pro as RP
        titulo = self.pro_fo_titulo.text().strip()
        if not titulo:
            _info_msg(self, "Formación", "Indica un título.")
            return
        try:
            horas = float(self.pro_fo_horas.text().strip().replace(",", ".") or 0)
            coste = float(self.pro_fo_coste.text().strip().replace(",", ".") or 0)
        except ValueError:
            _error_msg(self, "Formación", "Horas/coste deben ser numéricos.")
            return
        fid = RP.crear_formacion(titulo, tipo=self.pro_fo_tipo.currentData(),
                                 proveedor=self.pro_fo_proveedor.text().strip() or None,
                                 horas=horas, coste=coste,
                                 fecha_inicio=self.pro_fo_ini.text().strip() or None,
                                 fecha_fin=self.pro_fo_fin.text().strip() or None,
                                 id_empresa=self._id_empresa())
        if fid:
            _info_msg(self, "Formación", "Formación creada correctamente.")
            for wd in (self.pro_fo_titulo, self.pro_fo_proveedor, self.pro_fo_horas,
                      self.pro_fo_coste, self.pro_fo_ini, self.pro_fo_fin):
                wd.clear()
            self._pro_cargar_formaciones()
        else:
            _error_msg(self, "Formación", "No se pudo crear la formación.")

    def _pro_inscribir_formacion(self):
        from src.services.rrhh import rrhh_pro as RP
        if not self._pro_fo_sel:
            _info_msg(self, "Formación", "Selecciona primero una formación en la tabla.")
            return
        eid = self.pro_fo_emp.currentData()
        if not eid:
            _info_msg(self, "Formación", "No hay empleados disponibles.")
            return
        r = RP.inscribir_formacion(self._pro_fo_sel["id"], eid)
        if r.get("ok"):
            _info_msg(self, "Formación", "Empleado inscrito correctamente.")
        else:
            _error_msg(self, "Formación", r.get("motivo") or "No se pudo inscribir.")

    def _pro_aprovechamiento_formacion(self):
        from src.services.rrhh import rrhh_pro as RP
        if not self._pro_fo_sel:
            _info_msg(self, "Formación", "Selecciona primero una formación en la tabla.")
            return
        eid = self.pro_fo_emp.currentData()
        if not eid:
            _info_msg(self, "Formación", "No hay empleados disponibles.")
            return
        try:
            aprov = float(self.pro_fo_aprov.text().strip().replace(",", "."))
        except ValueError:
            _error_msg(self, "Formación", "El aprovechamiento debe ser numérico (0-100).")
            return
        r = RP.registrar_aprovechamiento(self._pro_fo_sel["id"], eid, aprov)
        if r.get("ok"):
            _info_msg(self, "Formación", "Aprovechamiento registrado correctamente.")
            self.pro_fo_aprov.clear()
        else:
            _error_msg(self, "Formación", r.get("motivo") or "No se pudo registrar.")

    # · Reclutamiento (ATS ligero) ·
    def _tab_pro_reclutamiento(self):
        from src.services.rrhh.rrhh_pro import _FASES
        w = QWidget(); ly = QVBoxLayout(w)
        f = QHBoxLayout()
        self.pro_rc_nombre = _inp("Nombre del candidato")
        self.pro_rc_vacante = _inp("Vacante")
        self.pro_rc_email = _inp("Email")
        self.pro_rc_tel = _inp("Teléfono")
        for wd in (self.pro_rc_nombre, self.pro_rc_vacante, self.pro_rc_email, self.pro_rc_tel):
            f.addWidget(wd)
        f.addWidget(_btn("Registrar candidato", self._pro_registrar_candidato, primary=True))
        ly.addLayout(f)
        self.tbl_pro_rc = _tabla(["ID", "Nombre", "Vacante", "Fase", "Valoración", "Email"])
        self.tbl_pro_rc.cellClicked.connect(self._pro_sel_candidato)
        ly.addWidget(self.tbl_pro_rc)
        f2 = QHBoxLayout()
        self.pro_rc_fase = _combo([(fa, fa) for fa in _FASES])
        self.pro_rc_valoracion = _inp("Valoración (0-10)")
        self.pro_rc_notas = _inp("Notas")
        f2.addWidget(self.pro_rc_fase); f2.addWidget(self.pro_rc_valoracion); f2.addWidget(self.pro_rc_notas)
        f2.addWidget(_btn("Mover de fase", self._pro_mover_fase_candidato, primary=True))
        ly.addLayout(f2)
        self._pro_rc_sel = None
        self._pro_cargar_candidatos()
        return w

    def _pro_cargar_candidatos(self):
        from src.services.rrhh import rrhh_pro as RP
        self._pro_rcs = RP.candidatos(self._id_empresa())
        self.tbl_pro_rc.setRowCount(len(self._pro_rcs))
        for i, r in enumerate(self._pro_rcs):
            vals = [r.get("id"), r.get("nombre"), r.get("vacante"), r.get("fase"),
                    r.get("valoracion"), r.get("email")]
            for j, v in enumerate(vals):
                self.tbl_pro_rc.setItem(i, j, _it(v))
        self._pro_rc_sel = None

    def _pro_sel_candidato(self, row, _c):
        try:
            self._pro_rc_sel = self._pro_rcs[row]
        except (IndexError, AttributeError):
            self._pro_rc_sel = None

    def _pro_registrar_candidato(self):
        from src.services.rrhh import rrhh_pro as RP
        nombre = self.pro_rc_nombre.text().strip()
        if not nombre:
            _info_msg(self, "Reclutamiento", "Indica el nombre del candidato.")
            return
        cid = RP.registrar_candidato(nombre, vacante=self.pro_rc_vacante.text().strip() or None,
                                     email=self.pro_rc_email.text().strip() or None,
                                     telefono=self.pro_rc_tel.text().strip() or None,
                                     id_empresa=self._id_empresa())
        if cid:
            _info_msg(self, "Reclutamiento", "Candidato registrado correctamente.")
            for wd in (self.pro_rc_nombre, self.pro_rc_vacante, self.pro_rc_email, self.pro_rc_tel):
                wd.clear()
            self._pro_cargar_candidatos()
        else:
            _error_msg(self, "Reclutamiento", "No se pudo registrar el candidato.")

    def _pro_mover_fase_candidato(self):
        from src.services.rrhh import rrhh_pro as RP
        if not self._pro_rc_sel:
            _info_msg(self, "Reclutamiento", "Selecciona primero un candidato en la tabla.")
            return
        valoracion = None
        if self.pro_rc_valoracion.text().strip():
            try:
                valoracion = float(self.pro_rc_valoracion.text().strip().replace(",", "."))
            except ValueError:
                _error_msg(self, "Reclutamiento", "La valoración debe ser numérica.")
                return
        r = RP.mover_fase_candidato(self._pro_rc_sel["id"], self.pro_rc_fase.currentData(),
                                    valoracion=valoracion, notas=self.pro_rc_notas.text().strip() or None)
        if r.get("ok"):
            _info_msg(self, "Reclutamiento", "Candidato movido de fase correctamente.")
            self._pro_cargar_candidatos()
        else:
            _error_msg(self, "Reclutamiento", r.get("motivo") or "No se pudo mover de fase.")

    # · Turnos de personal ·
    def _tab_pro_turnos(self):
        w = QWidget(); ly = QVBoxLayout(w)
        f = QHBoxLayout()
        self.pro_tu_emp = self._combo_empleados_pro()
        self.pro_tu_fecha = _inp("Fecha AAAA-MM-DD")
        self.pro_tu_ini = _inp("Hora inicio HH:MM")
        self.pro_tu_fin = _inp("Hora fin HH:MM")
        self.pro_tu_rol = _inp("Rol/puesto del turno")
        for wd in (self.pro_tu_emp, self.pro_tu_fecha, self.pro_tu_ini, self.pro_tu_fin, self.pro_tu_rol):
            f.addWidget(wd)
        ly.addLayout(f)
        # "Planificar turno" baja a la misma fila que "Ver cuadrante": en la fila de arriba (con
        # 5 campos + el propio "Rol/puesto del turno") no quedaba sitio y su texto se cortaba con
        # el hover; aquí abajo las 2 barras de fecha tienen sobra para encogerse un poco.
        f2 = QHBoxLayout()
        self.pro_tu_desde = _inp("Ver cuadrante desde AAAA-MM-DD")
        self.pro_tu_hasta = _inp("Ver cuadrante hasta AAAA-MM-DD")
        f2.addWidget(self.pro_tu_desde); f2.addWidget(self.pro_tu_hasta)
        f2.addWidget(_btn("Planificar turno", self._pro_planificar_turno, primary=True))
        f2.addWidget(_btn("Ver cuadrante", self._pro_ver_cuadrante, primary=True))
        ly.addLayout(f2)
        self.tbl_pro_tu = _tabla(["ID", "Empleado", "Fecha", "Inicio", "Fin", "Rol"])
        ly.addWidget(self.tbl_pro_tu)
        # Auto-carga al abrir la pestaña (bug real reportado: la tabla se quedaba vacía hasta
        # rellenar el rango a mano y pulsar "Ver cuadrante" — un usuario que solo entra a mirar
        # nunca llegaba a ver los turnos ya planificados). Rango por defecto: 7 días atrás a 30
        # días adelante, centrado en hoy.
        import datetime as _dt
        hoy = _dt.date.today()
        self.pro_tu_desde.setText((hoy - _dt.timedelta(days=7)).isoformat())
        self.pro_tu_hasta.setText((hoy + _dt.timedelta(days=30)).isoformat())
        self._pro_ver_cuadrante(silencioso=True)
        return w

    def _pro_planificar_turno(self):
        from src.services.rrhh import rrhh_pro as RP
        eid = self.pro_tu_emp.currentData()
        if not eid:
            _info_msg(self, "Turnos", "No hay empleados disponibles.")
            return
        fecha = self.pro_tu_fecha.text().strip()
        if not fecha:
            _info_msg(self, "Turnos", "Indica la fecha del turno (AAAA-MM-DD).")
            return
        tid = RP.planificar_turno(eid, fecha, hora_inicio=self.pro_tu_ini.text().strip() or None,
                                  hora_fin=self.pro_tu_fin.text().strip() or None,
                                  rol=self.pro_tu_rol.text().strip() or None, id_empresa=self._id_empresa())
        if tid:
            _info_msg(self, "Turnos", "Turno planificado correctamente.")
            self.pro_tu_fecha.clear(); self.pro_tu_ini.clear(); self.pro_tu_fin.clear(); self.pro_tu_rol.clear()
            # La tabla de abajo (el mismo cuadrante de "Ver cuadrante") no se refrescaba sola tras
            # planificar — el turno quedaba guardado pero invisible hasta pulsar "Ver cuadrante" a
            # mano (bug real reportado). Si el usuario no tiene ya un rango propio puesto, se usa el
            # día recién planificado como rango mínimo para que aparezca de inmediato.
            if not self.pro_tu_desde.text().strip():
                self.pro_tu_desde.setText(fecha)
            if not self.pro_tu_hasta.text().strip():
                self.pro_tu_hasta.setText(fecha)
            self._pro_ver_cuadrante(silencioso=True)
        else:
            _error_msg(self, "Turnos", "No se pudo planificar el turno.")

    def _pro_ver_cuadrante(self, silencioso=False):
        from src.services.rrhh import rrhh_pro as RP
        desde, hasta = self.pro_tu_desde.text().strip(), self.pro_tu_hasta.text().strip()
        if not desde or not hasta:
            if not silencioso:
                _info_msg(self, "Turnos", "Indica el rango de fechas (desde/hasta).")
            return
        nombres = self._nombres_empleados_pro()
        filas = RP.cuadrante(desde, hasta, id_empresa=self._id_empresa())
        self.tbl_pro_tu.setRowCount(len(filas))
        for i, r in enumerate(filas):
            vals = [r.get("id"), nombres.get(r.get("id_empleado"), r.get("id_empleado")), r.get("fecha"),
                    r.get("hora_inicio"), r.get("hora_fin"), r.get("rol")]
            for j, v in enumerate(vals):
                self.tbl_pro_tu.setItem(i, j, _it(v))
        if silencioso:
            return
        if filas:
            _info_msg(self, "Turnos", f"{len(filas)} turno(s) encontrado(s) en ese rango.")
        else:
            _info_msg(self, "Turnos", "Sin turnos planificados en ese rango.")

    # · Anticipos y conceptos recurrentes ·
    def _tab_pro_anticipos(self):
        w = QWidget(); ly = QVBoxLayout(w)
        f = QHBoxLayout()
        self.pro_an_emp = self._combo_empleados_pro()
        self.pro_an_emp.currentIndexChanged.connect(self._pro_cargar_anticipos)
        self.pro_an_importe = _inp("Importe total")
        self.pro_an_cuotas = _inp("Cuotas")
        self.pro_an_motivo = _inp("Motivo")
        for wd in (self.pro_an_emp, self.pro_an_importe, self.pro_an_cuotas, self.pro_an_motivo):
            f.addWidget(wd)
        f.addWidget(_btn("Solicitar anticipo", self._pro_solicitar_anticipo, primary=True))
        ly.addLayout(f)
        self.tbl_pro_an = _tabla(["ID", "Importe", "Cuotas", "Cuota", "Pendiente", "Estado"])
        self.tbl_pro_an.cellClicked.connect(self._pro_sel_anticipo)
        ly.addWidget(self.tbl_pro_an)
        b = QHBoxLayout()
        b.addWidget(_btn("Aprobar anticipo seleccionado", self._pro_aprobar_anticipo, primary=True))
        b.addStretch()
        ly.addLayout(b)
        f2 = QHBoxLayout()
        f2.addWidget(QLabel("Concepto recurrente (retribución flexible / plus fijo):"))
        self.pro_cr_clave = _inp("clave (p.ej. plus_transporte)")
        self.pro_cr_importe = _inp("Importe")
        f2.addWidget(self.pro_cr_clave); f2.addWidget(self.pro_cr_importe)
        f2.addWidget(_btn("Guardar concepto", self._pro_set_concepto, primary=True))
        ly.addLayout(f2)
        self._pro_an_sel = None
        self._pro_cargar_anticipos()
        return w

    def _pro_cargar_anticipos(self):
        from src.services.rrhh import nominas_pro as NP
        eid = self.pro_an_emp.currentData()
        self._pro_ans = NP.anticipos_empleado(eid, id_empresa=self._id_empresa()) if eid else []
        self.tbl_pro_an.setRowCount(len(self._pro_ans))
        for i, r in enumerate(self._pro_ans):
            vals = [r.get("id"), r.get("importe_total"), r.get("cuotas"), r.get("importe_cuota"),
                    r.get("pendiente"), r.get("estado")]
            for j, v in enumerate(vals):
                self.tbl_pro_an.setItem(i, j, _it(v))
        self._pro_an_sel = None

    def _pro_sel_anticipo(self, row, _c):
        try:
            self._pro_an_sel = self._pro_ans[row]
        except (IndexError, AttributeError):
            self._pro_an_sel = None

    def _pro_solicitar_anticipo(self):
        from src.services.rrhh import nominas_pro as NP
        eid = self.pro_an_emp.currentData()
        if not eid:
            _info_msg(self, "Anticipos", "No hay empleados disponibles.")
            return
        try:
            importe = float(self.pro_an_importe.text().strip().replace(",", "."))
            cuotas = int(self.pro_an_cuotas.text().strip() or 1)
        except ValueError:
            _error_msg(self, "Anticipos", "Importe/cuotas deben ser numéricos.")
            return
        if importe <= 0:
            _error_msg(self, "Anticipos", "El importe debe ser mayor que 0.")
            return
        aid = NP.solicitar_anticipo(eid, importe, cuotas=cuotas,
                                    motivo=self.pro_an_motivo.text().strip() or None,
                                    id_empresa=self._id_empresa())
        if aid:
            _info_msg(self, "Anticipos", "Anticipo solicitado correctamente.")
            self.pro_an_importe.clear(); self.pro_an_cuotas.clear(); self.pro_an_motivo.clear()
            self._pro_cargar_anticipos()
        else:
            _error_msg(self, "Anticipos", "No se pudo solicitar el anticipo.")

    def _pro_aprobar_anticipo(self):
        from src.services.rrhh import nominas_pro as NP
        if not self._pro_an_sel:
            _info_msg(self, "Anticipos", "Selecciona primero un anticipo en la tabla.")
            return
        r = NP.aprobar_anticipo(self._pro_an_sel["id"], aprobado_por=self._usuario_pro(),
                                id_empresa=self._id_empresa())
        if r.get("ok"):
            _info_msg(self, "Anticipos", "Anticipo aprobado correctamente.")
            self._pro_cargar_anticipos()
        else:
            _error_msg(self, "Anticipos", r.get("motivo") or "No se pudo aprobar (¿ya no está solicitado?).")

    def _pro_set_concepto(self):
        from src.services.rrhh import nominas_pro as NP
        eid = self.pro_an_emp.currentData()
        clave = self.pro_cr_clave.text().strip()
        if not eid or not clave:
            _info_msg(self, "Anticipos", "Selecciona un empleado e indica la clave del concepto.")
            return
        try:
            importe = float(self.pro_cr_importe.text().strip().replace(",", "."))
        except ValueError:
            _error_msg(self, "Anticipos", "El importe debe ser numérico.")
            return
        r = NP.set_concepto_recurrente(eid, clave, importe, id_empresa=self._id_empresa())
        if r.get("ok"):
            _info_msg(self, "Anticipos", f"Concepto «{clave}» guardado correctamente.")
            self.pro_cr_clave.clear(); self.pro_cr_importe.clear()
        else:
            _error_msg(self, "Anticipos", r.get("motivo") or "No se pudo guardar el concepto.")

    def _usuario_pro(self):
        u = self.usuario or {}
        return u.get("nombre") if isinstance(u, dict) else None

    def _cargar(self):
        from src.rrhh.db import empleados
        estado = self.cb_filtro.currentData() or None
        texto = self.in_buscar.text().strip() or None
        self._filas = empleados.listar_empleados(self._id_empresa(), estado=estado, texto=texto)
        self.tbl.setRowCount(len(self._filas))
        for i, e in enumerate(self._filas):
            vals = [e.get("nombre"), e.get("apellidos"), e.get("nif"), e.get("puesto"),
                    e.get("convenio"), e.get("estado"), e.get("fecha_alta")]
            for j, v in enumerate(vals):
                self.tbl.setItem(i, j, _it(v))

    def _sel(self):
        i = self.tbl.currentRow()
        return self._filas[i] if 0 <= i < len(self._filas) else None

    def _nuevo(self):
        dlg = EmpleadoFormDialog(id_empresa=self._id_empresa(), parent=self)
        if dlg.exec():
            self._cargar()

    def _editar(self, *_):
        e = self._sel()
        if not e:
            self._flash("Selecciona un empleado de la lista para editarlo."); return
        dlg = EmpleadoFormDialog(empleado=e, id_empresa=self._id_empresa(), parent=self)
        if dlg.exec():
            self._cargar()

    def _expediente(self, *_):
        e = self._sel()
        if not e:
            self._flash("Selecciona un empleado de la lista para ver su expediente."); return
        ExpedienteDialog(e["id"], self._id_empresa(), parent=self).exec()

    def _gestion_laboral(self, *_):
        e = self._sel()
        if not e:
            self._flash("Selecciona un empleado de la lista para gestionar vacaciones/ausencias."); return
        GestionLaboralDialog(e["id"], self._id_empresa(), parent=self).exec()

    def _control_horario(self, *_):
        e = self._sel()
        if not e:
            self._flash("Selecciona un empleado de la lista para su control horario."); return
        ControlHorarioDialog(e["id"], self._id_empresa(), parent=self).exec()


# ── Gestión operativa de vacaciones y ausencias (F4.7) ────────────────────────
class GestionLaboralDialog(QDialog):
    def __init__(self, id_empleado, id_empresa=None, parent=None):
        super().__init__(parent)
        self.id_empleado = id_empleado
        self.id_empresa = id_empresa
        self.setMinimumSize(760, 560)
        self.setStyleSheet(f"QLabel{{color:{_TEXT};}}")
        self._build()

    def _build(self):
        # `_dialogo_frameless` (mismo helper que `EmpleadoFormDialog` y el resto de la app):
        # quita la barra de título nativa de Windows, redondea las esquinas de verdad (recorte
        # nativo vía el filtro global de `estilo_global`, que actúa sobre cualquier QDialog
        # frameless+translúcido) y añade la cabecera con el título + la X roja circular de
        # cierre — sustituye por completo el antiguo botón "Cerrar".
        root = _dialogo_frameless(self, "Vacaciones y ausencias", ancho=760)
        self.lbl_saldo = QLabel(""); self.lbl_saldo.setStyleSheet(f"color:{_CIAN};font-weight:700;")
        root.addWidget(self.lbl_saldo)
        tabs = QTabWidget()
        # Sin borde en el pane (se retiran las líneas grises que rodeaban Vacaciones/Ausencias/
        # Calendario) — mismo criterio que `EmpleadoFormDialog`.
        tabs.setStyleSheet(f"QTabBar::tab{{background:{_SIDEBAR};color:{_DIM};padding:8px 14px;}}"
                           f"QTabBar::tab:selected{{color:{_CIAN};}}"
                           f"QTabWidget::pane{{border:none;}}")
        tabs.addTab(self._tab_vac(), "Vacaciones")
        tabs.addTab(self._tab_aus(), "Ausencias")
        tabs.addTab(self._tab_cal(), "Calendario")
        # Animación de deslizamiento al cambiar de pestaña — mismo mecanismo ya establecido en
        # toda la app (`src/gui/transiciones.py`, usado por el resto de QTabWidget/QStackedWidget
        # de navegación).
        instalar_transicion_tabs(tabs)
        root.addWidget(tabs)
        self._refrescar()

    # Vacaciones
    def _tab_vac(self):
        w = QWidget(); ly = QVBoxLayout(w)
        self.tbl_vac = _tabla(["id", "Inicio", "Fin", "Días", "Estado", "Aprob. por"])
        ly.addWidget(self.tbl_vac)
        f = QHBoxLayout()
        self.v_ini = _inp("Inicio AAAA-MM-DD"); self.v_fin = _inp("Fin AAAA-MM-DD")
        f.addWidget(self.v_ini); f.addWidget(self.v_fin)
        f.addWidget(_btn("Solicitar", self._solicitar, primary=True))
        ly.addLayout(f)
        a = QHBoxLayout()
        a.addWidget(_btn("Aprobar", lambda: self._estado_vac("aprobar"), success=True))
        a.addWidget(_btn("Denegar", lambda: self._estado_vac("denegar"), danger=True))
        a.addWidget(_btn("Cancelar", lambda: self._estado_vac("cancelar"), primary=True))
        ly.addLayout(a)
        return w

    # Ausencias — bajas laborales sin PDF (Fase C): formulario simple que escribe directamente
    # en `rrhh_ausencias` vía `ausencias_servicio.registrar()`; debajo, listado de lo ya
    # registrado para el empleado (`ausencias_servicio.listar()`).
    def _tab_aus(self):
        from src.rrhh import ausencias_servicio as AS
        w = QWidget(); ly = QVBoxLayout(w)
        self.tbl_aus = _tabla(["id", "Tipo", "Inicio", "Fin", "Días", "Motivo", "Contingencia"])
        self.tbl_aus.cellClicked.connect(self._sel_aus)
        ly.addWidget(self.tbl_aus)
        f = QHBoxLayout()
        self.a_tipo = _combo([(et, k) for k, et in AS.TIPOS.items()])
        self.a_tipo.currentIndexChanged.connect(self._actualizar_visibilidad_contingencia)
        self.a_ini = _inp("Inicio"); self.a_fin = _inp("Fin"); self.a_mot = _inp("Motivo")
        for wd in (self.a_tipo, self.a_ini, self.a_fin, self.a_mot):
            f.addWidget(wd)
        f.addWidget(_btn("Registrar", self._registrar_aus, primary=True))
        ly.addLayout(f)
        # Contingencia: solo visible/relevante cuando el tipo elegido es baja médica
        # (`AS.TIPO_BAJA_MEDICA`) — alimenta el motor de Incapacidad Temporal (Fase F).
        fc = QHBoxLayout()
        self.lbl_conting = QLabel("Tipo de contingencia:")
        fc.addWidget(self.lbl_conting)
        self.a_conting = _combo([(et, k) for k, et in AS.TIPOS_CONTINGENCIA.items()])
        fc.addWidget(self.a_conting)
        fc.addStretch()
        ly.addLayout(fc)
        self._actualizar_visibilidad_contingencia()
        eb = QHBoxLayout()
        eb.addWidget(_btn("Editar", self._editar_aus))
        eb.addWidget(_btn("Eliminar", self._eliminar_aus, danger=True))
        eb.addStretch()
        ly.addLayout(eb)
        self._aus_sel = None
        return w

    def _actualizar_visibilidad_contingencia(self, *_args):
        from src.rrhh import ausencias_servicio as AS
        es_baja_medica = self.a_tipo.currentData() == AS.TIPO_BAJA_MEDICA
        self.lbl_conting.setVisible(es_baja_medica)
        self.a_conting.setVisible(es_baja_medica)

    def _sel_aus(self, row, _c):
        try:
            self._aus_sel = self._aus[row]
        except (IndexError, AttributeError):
            self._aus_sel = None

    def _editar_aus(self):
        from src.rrhh import ausencias_servicio as AS
        if not self._aus_sel:
            _info_msg(self, "Ausencias", "Selecciona primero una ausencia en la tabla.")
            return
        dlg = _EditarAusenciaDialog(self._aus_sel, AS.TIPOS, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            AS.editar(self._aus_sel["id"], id_empresa=self.id_empresa, **dlg.valores())
        except AS.GestionLaboralError as e:
            _error_msg(self, "Ausencias", str(e)); return
        _info_msg(self, "Ausencias", "Ausencia actualizada correctamente.")
        self._refrescar()

    def _eliminar_aus(self):
        from src.rrhh import ausencias_servicio as AS
        if not self._aus_sel:
            _info_msg(self, "Ausencias", "Selecciona primero una ausencia en la tabla.")
            return
        if not _confirmar(
                self, "Eliminar ausencia",
                f"¿Eliminar la ausencia del {self._aus_sel.get('fecha_inicio')}?\nEsta acción no se puede deshacer."):
            return
        try:
            ok = AS.eliminar(self._aus_sel["id"], id_empresa=self.id_empresa)
        except AS.GestionLaboralError as e:
            _error_msg(self, "Ausencias", str(e)); return
        if ok:
            _info_msg(self, "Ausencias", "Ausencia eliminada correctamente.")
            self._refrescar()
        else:
            _error_msg(self, "Ausencias", "No se pudo eliminar la ausencia.")

    def _tab_cal(self):
        w = QWidget(); ly = QVBoxLayout(w)
        self.tbl_cal = _tabla(["Tipo", "Estado", "Inicio", "Fin", "Días"])
        ly.addWidget(self.tbl_cal)
        return w

    def _refrescar(self):
        from src.rrhh import ausencias_servicio as AS
        from src.rrhh import vacaciones_servicio as VS
        s = VS.saldo(self.id_empleado, id_empresa=self.id_empresa)
        self.lbl_saldo.setText(
            f"Saldo {s['anio']}: asignados {s['asignados']} · disfrutados {s['disfrutados']} · "
            f"pendientes {s['pendientes']} · disponibles {s['disponibles']}")
        self._vac = VS.listar(self.id_empleado, self.id_empresa)
        _ESTADOS_VAC_LBL = {VS.PENDIENTE: "Pendiente", VS.PENDIENTE_RESPONSABLE: "Pend. responsable",
                           VS.PENDIENTE_RRHH: "Pend. RRHH", VS.APROBADA: "Aprobada",
                           VS.DENEGADA: "Denegada", VS.CANCELADA: "Cancelada", VS.CONSUMIDA: "Consumida"}
        self.tbl_vac.setRowCount(len(self._vac))
        for i, v in enumerate(self._vac):
            estado_lbl = _ESTADOS_VAC_LBL.get(v.get("estado"), v.get("estado"))
            aprobador = v.get("aprobado_por") or v.get("aprobado_por_responsable")
            for j, val in enumerate([v.get("id"), v.get("fecha_inicio"), v.get("fecha_fin"),
                                     v.get("dias"), estado_lbl, aprobador]):
                self.tbl_vac.setItem(i, j, _it(val))
        self._aus = AS.listar(self.id_empleado, self.id_empresa)
        self.tbl_aus.setRowCount(len(self._aus))
        for i, a in enumerate(self._aus):
            for j, val in enumerate([a.get("id"), AS.TIPOS.get(a.get("tipo"), a.get("tipo")),
                                     a.get("fecha_inicio"), a.get("fecha_fin"), a.get("dias"),
                                     a.get("motivo"),
                                     AS.TIPOS_CONTINGENCIA.get(a.get("tipo_contingencia"),
                                                              a.get("tipo_contingencia"))]):
                self.tbl_aus.setItem(i, j, _it(val))
        self._aus_sel = None
        cal = AS.calendario(self.id_empleado, self.id_empresa)
        self.tbl_cal.setRowCount(len(cal))
        for i, ev in enumerate(cal):
            for j, val in enumerate([ev.get("tipo"), ev.get("estado"), ev.get("fecha_inicio"),
                                     ev.get("fecha_fin"), ev.get("dias")]):
                self.tbl_cal.setItem(i, j, _it(val))

    def _usuario(self):
        u = getattr(self.parent(), "usuario", None) or {}
        return u.get("nombre") if isinstance(u, dict) else None

    def _solicitar(self):
        from src.rrhh import vacaciones_servicio as VS
        try:
            VS.solicitar(self.id_empleado, self.v_ini.text().strip(), self.v_fin.text().strip(),
                         id_empresa=self.id_empresa)
        except VS.GestionLaboralError as e:
            _error_msg(self, "Vacaciones", str(e)); return
        self.v_ini.clear(); self.v_fin.clear(); self._refrescar()

    def _vac_sel(self):
        i = self.tbl_vac.currentRow()
        return self._vac[i] if 0 <= i < len(self._vac) else None

    def _estado_vac(self, accion):
        from src.rrhh import vacaciones_servicio as VS
        v = self._vac_sel()
        if not v:
            _info_msg(self, "Vacaciones", "Selecciona una solicitud."); return
        fn = {"aprobar": VS.avanzar_aprobacion, "denegar": VS.denegar, "cancelar": VS.cancelar}[accion]
        try:
            fn(v["id"], usuario=self._usuario(), id_empresa=self.id_empresa)
        except VS.GestionLaboralError as e:
            _error_msg(self, "Vacaciones", str(e)); return
        self._refrescar()

    def _registrar_aus(self):
        from src.rrhh import ausencias_servicio as AS
        from src.rrhh.vacaciones_servicio import GestionLaboralError
        tipo = self.a_tipo.currentData()
        conting = self.a_conting.currentData() if tipo == AS.TIPO_BAJA_MEDICA else None
        try:
            AS.registrar(self.id_empleado, tipo, self.a_ini.text().strip(),
                         self.a_fin.text().strip(), motivo=self.a_mot.text().strip(),
                         tipo_contingencia=conting, id_empresa=self.id_empresa)
        except GestionLaboralError as e:
            _error_msg(self, "Ausencias", str(e)); return
        self.a_ini.clear(); self.a_fin.clear(); self.a_mot.clear(); self._refrescar()


# ── Control horario (RD 8/2019) — F4.9 ────────────────────────────────────────
class ControlHorarioDialog(QDialog):
    def __init__(self, id_empleado, id_empresa=None, parent=None):
        super().__init__(parent)
        self.id_empleado = id_empleado
        self.id_empresa = id_empresa
        self.setWindowTitle("Control horario")
        self.setMinimumSize(820, 580)
        self.setStyleSheet(f"QDialog{{background:{_BG};}} QLabel{{color:{_TEXT};}}")
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        self.lbl_tot = QLabel(""); self.lbl_tot.setStyleSheet(f"color:{_CIAN};font-weight:700;")
        root.addWidget(self.lbl_tot)
        self.tbl = _tabla(["id", "Fecha", "Entrada", "Salida", "Pausa(s)", "Efectivo(min)",
                           "Exceso", "Déficit"])
        self.tbl.cellClicked.connect(self._sel_jornada)
        root.addWidget(self.tbl)
        # alta de jornada
        f = QHBoxLayout()
        self.in_fecha = _inp("Fecha AAAA-MM-DD")
        self.in_ent = _inp("Entrada AAAA-MM-DD HH:MM")
        self.in_sal = _inp("Salida AAAA-MM-DD HH:MM")
        self.in_plan = _inp("Plan. min (480)")
        for wd in (self.in_fecha, self.in_ent, self.in_sal, self.in_plan):
            f.addWidget(wd)
        f.addWidget(_btn("Registrar", self._registrar, primary=True))
        root.addLayout(f)
        b = QHBoxLayout()
        b.addWidget(_btn("Ver incidencias", self._incidencias))
        b.addWidget(_btn("Exportar CSV", self._export_csv))
        b.addWidget(_btn("Exportar Excel", self._export_excel))
        b.addWidget(_btn("Exportar PDF", self._export_pdf))
        b.addWidget(_btn("Importar fichajes", self._importar))
        b.addWidget(_btn("Eliminar jornada", self._eliminar_jornada, danger=True))
        b.addWidget(_btn("Cerrar", self.accept))
        root.addLayout(b)
        self._jornada_sel = None
        self._refrescar()

    def _sel_jornada(self, row, _c):
        try:
            self._jornada_sel = self._filas[row]
        except (IndexError, AttributeError):
            self._jornada_sel = None

    def _refrescar(self):
        from src.rrhh import control_horario as CH
        self._filas = CH.listar_jornadas(self.id_empleado, self.id_empresa)
        self.tbl.setRowCount(len(self._filas))
        for i, j in enumerate(self._filas):
            for k, val in enumerate([j.get("id"), j.get("fecha"), j.get("hora_entrada"),
                                     j.get("hora_salida"), j.get("pausa_segundos"),
                                     j.get("tiempo_efectivo_min"), j.get("exceso_min"),
                                     j.get("deficit_min")]):
                self.tbl.setItem(i, k, _it(val))
        t = CH._totales(self._filas)
        self.lbl_tot.setText(f"Días {t['dias']} · efectivo {t['efectivo_min']} min · "
                             f"exceso {t['exceso_min']} · déficit {t['deficit_min']}")
        self._jornada_sel = None

    def _registrar(self):
        from src.rrhh import control_horario as CH
        try:
            plan = int(self.in_plan.text().strip() or CH.JORNADA_DEFECTO_MIN)
            CH.registrar_jornada(self.id_empleado, self.in_fecha.text().strip(),
                                 self.in_ent.text().strip(), self.in_sal.text().strip() or None,
                                 planificada_min=plan, usuario=self._usuario(),
                                 id_empresa=self.id_empresa)
        except CH.ControlHorarioError as e:
            _error_msg(self, "Control horario", str(e)); return
        for w in (self.in_fecha, self.in_ent, self.in_sal, self.in_plan):
            w.clear()
        self._refrescar()

    def _usuario(self):
        u = getattr(self.parent(), "usuario", None) or {}
        return u.get("nombre") if isinstance(u, dict) else None

    def _incidencias(self):
        from src.rrhh import control_horario as CH
        inc = CH.alertas(self.id_empleado, self.id_empresa)
        if not inc:
            _info_msg(self, "Control horario", "Sin incidencias."); return
        txt = "\n".join(f"· {i['fecha']}: {i['tipo']} — {i['detalle']}" for i in inc[:40])
        _info_msg(self, "Incidencias", txt)

    def _export_csv(self):
        from src.rrhh import control_horario as CH
        from PyQt6.QtWidgets import QFileDialog
        ruta, _ = QFileDialog.getSaveFileName(self, "Exportar CSV", "control_horario.csv",
                                              "CSV (*.csv)")
        if not ruta:
            return
        try:
            with open(ruta, "w", encoding="utf-8", newline="") as fh:
                fh.write(CH.exportar_csv(self._filas))
            _info_msg(self, "Control horario", f"Exportado a {ruta}")
        except Exception as e:
            _error_msg(self, "Control horario", f"No se pudo exportar: {e}")

    def _export_excel(self):
        from src.rrhh import control_horario as CH
        from PyQt6.QtWidgets import QFileDialog
        ruta, _ = QFileDialog.getSaveFileName(self, "Exportar Excel", "control_horario.xlsx",
                                              "Excel (*.xlsx)")
        if not ruta:
            return
        r = CH.exportar_excel(self._filas, ruta)
        if r:
            _info_msg(self, "Control horario", f"Exportado a {r}")
        else:
            _error_msg(self, "Control horario",
                                "No se pudo exportar (falta la librería openpyxl).")

    def _export_pdf(self):
        from src.rrhh import control_horario as CH
        from PyQt6.QtWidgets import QFileDialog
        ruta, _ = QFileDialog.getSaveFileName(self, "Exportar PDF", "control_horario.pdf",
                                              "PDF (*.pdf)")
        if not ruta:
            return
        r = CH.exportar_pdf(self._filas, ruta, titulo=f"Control horario · empleado {self.id_empleado}")
        if r:
            _info_msg(self, "Control horario", f"Exportado a {r}")
        else:
            _error_msg(self, "Control horario",
                                "No se pudo exportar (falta la librería reportlab).")

    def _importar(self):
        from src.rrhh import control_horario as CH
        from src.rrhh.db import empleados as EMP
        emp = EMP.obtener_empleado(self.id_empleado, self.id_empresa)
        uid = emp.get("id_usuario") if emp else None
        if not uid:
            _error_msg(self, "Control horario",
                                "Este empleado no está vinculado a un usuario del sistema "
                                "(id_usuario); no se pueden importar sus fichajes.")
            return
        try:
            n = CH.importar_de_fichajes(self.id_empleado, uid, id_empresa=self.id_empresa)
        except Exception as e:
            _error_msg(self, "Control horario", f"No se pudo importar: {e}")
            return
        _info_msg(self, "Control horario", f"{n} jornada(s) importada(s) desde fichajes.")
        self._refrescar()

    def _eliminar_jornada(self):
        if not self._jornada_sel:
            _info_msg(self, "Control horario", "Selecciona primero una jornada en la tabla.")
            return
        if not _confirmar(self, "Eliminar jornada",
                          f"¿Eliminar la jornada del {self._jornada_sel.get('fecha')}?"):
            return
        from src.rrhh import control_horario as CH
        if CH.eliminar_jornada(self._jornada_sel["id"], id_empresa=self.id_empresa):
            _info_msg(self, "Control horario", "Jornada eliminada correctamente.")
            self._refrescar()
        else:
            _error_msg(self, "Control horario", "No se pudo eliminar la jornada.")
