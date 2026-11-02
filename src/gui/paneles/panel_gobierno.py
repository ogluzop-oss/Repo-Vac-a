"""
Panel Gobierno Corporativo — pestaña alojada dentro de Seguridad (misma familia: control de acceso y
autoridad). Sub-secciones: Organigrama · Autoridad · Delegaciones (unifica autoridad organizativa +
delegación de tareas) · Políticas · Escalados, más indicadores. Orquesta SOLO el GovernanceService.

Se construye con componentes Enterprise (regla: única librería visual). No migra la ventana de
Seguridad al shell (Strangler): solo añade esta pestaña, de forma aditiva y compatible.
"""

import logging

from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton, QTabWidget,
                             QVBoxLayout, QWidget)

from src.gui.components import (EnterpriseCard, EnterpriseDashboardGrid,
                                EnterpriseTable)
from src.gui.foundation import tokens as T

logger = logging.getLogger("gui.paneles.gobierno")


def _emp(id_empresa=None):
    try:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)
    except Exception:
        return id_empresa


def _svc():
    from src.services import gobierno
    return gobierno.servicio()


class _FormDialog(QDialog):
    """Diálogo de formulario genérico para las altas de Gobierno (nodo/delegación/política): la
    librería Enterprise (`gui/components`) no tiene un primitivo de formulario modal, así que se
    reutilizan aquí los mismos `_dialogo_frameless`/`_inp`/`_combo`/`_btn` que ya usa
    `panel_tareas_empleados._DescripcionDialog` (mismo módulo `gui/paneles`, mismo precedente
    documentado) en vez de duplicar un QDialog manual. `campos`: lista de dicts {key,label,tipo,ph,
    default,opciones}."""

    def __init__(self, parent, titulo, campos, texto_guardar="Crear"):
        super().__init__(parent)
        from src.gui.catalogo_gestion import _btn, _combo, _dialogo_frameless, _inp, _lbl
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


class PanelGobierno(QWidget):
    def __init__(self, usuario=None, id_empresa=None, parent=None):
        super().__init__(parent)
        self.usuario = usuario or {}
        self.id_empresa = _emp(id_empresa)
        self.setStyleSheet(f"background:{T.BG};color:{T.TEXT};")
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        self.grid = EnterpriseDashboardGrid(columnas=5)
        root.addWidget(self.grid)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(T.qss_tabs())   # mismo diseño de pestañas que el Centro de Inteligencia
        root.addWidget(self.tabs, 1)

        # Cada tabla lleva su Actualizar (emoji) a la derecha de su barra de búsqueda.
        self.t_org = EnterpriseTable(["Id", "Tipo", "Nombre", "Nivel", "Estado"], con_busqueda=True,
                                     con_actualizar=self._cargar)
        self.t_aut = EnterpriseTable(["Rol", "Permisos"], con_busqueda=True, con_actualizar=self._cargar)
        self.t_del = EnterpriseTable(["Id", "Origen", "Delegado", "Desde", "Hasta"], con_busqueda=True,
                                     con_actualizar=self._cargar)
        self.t_pol = EnterpriseTable(["Clave", "Valor", "Ámbito"], con_busqueda=True,
                                     con_actualizar=self._cargar)
        self.t_esc = EnterpriseTable(["Referencia", "Desde", "Hacia", "Nivel", "Horas"], con_busqueda=True,
                                     con_actualizar=self._cargar)
        self.t_res = EnterpriseTable(["Nodo", "Rol", "Usuario"], con_busqueda=True,
                                     con_actualizar=self._cargar)
        self.tabs.addTab(self._wrap(self.t_org, self._barra_organigrama()), "Organigrama")
        self.tabs.addTab(self._wrap(self.t_aut), "Autoridad")
        self.tabs.addTab(self._wrap(self.t_del, self._barra_delegaciones()), "Delegaciones")
        self.tabs.addTab(self._wrap(self.t_pol, self._barra_politicas()), "Políticas")
        self.tabs.addTab(self._wrap(self.t_esc, self._barra_escalados()), "Escalados")
        self.tabs.addTab(self._wrap(self.t_res, self._barra_responsables()), "Responsables")

        self._cargar()

    def _wrap(self, tabla, barra=None):
        w = QWidget(); w.setStyleSheet(f"background:{T.BG};")
        lay = QVBoxLayout(w)
        if barra:
            lay.addLayout(barra)
        lay.addWidget(tabla)
        return w

    def _accion_btn(self, texto, slot, color=None):
        color = color or T.INFO
        bt = QPushButton(texto)
        bt.clicked.connect(slot)
        bt.setStyleSheet(f"QPushButton{{background:{T.BG2};color:{color};"
                         f"border:2px solid {color};border-radius:8px;font-weight:800;padding:4px 12px;}}"
                         f"QPushButton:hover{{background:{color};color:{T.BG};}}")
        return bt

    def _barra_organigrama(self):
        b = QHBoxLayout(); b.addStretch(1)
        b.addWidget(self._accion_btn("＋ Nuevo nodo", self._nuevo_nodo))
        return b

    def _barra_delegaciones(self):
        b = QHBoxLayout()
        lbl = QLabel("Sustitución de autoridad (Gobierno) + delegación de tareas (Workflow)")
        lbl.setStyleSheet(f"color:{T.DIM};font-size:11px;")
        b.addWidget(lbl); b.addStretch(1)
        b.addWidget(self._accion_btn("＋ Nueva delegación", self._nueva_delegacion))
        b.addWidget(self._accion_btn("Revocar", self._revocar_delegacion, color=T.CRITICO))
        return b

    def _barra_politicas(self):
        b = QHBoxLayout(); b.addStretch(1)
        b.addWidget(self._accion_btn("＋ Nueva / editar política", self._nueva_politica))
        return b

    def _barra_escalados(self):
        b = QHBoxLayout(); b.addStretch(1)
        bt = QPushButton("Revisar escalados")
        bt.clicked.connect(self._revisar_escalados)
        bt.setStyleSheet(f"QPushButton{{background:{T.BG2};color:{T.ADVERTENCIA};"
                         f"border:2px solid {T.ADVERTENCIA};border-radius:8px;font-weight:800;padding:4px 12px;}}"
                         f"QPushButton:hover{{background:{T.ADVERTENCIA};color:{T.BG};}}")
        b.addWidget(bt)
        return b

    def _barra_responsables(self):
        b = QHBoxLayout(); b.addStretch(1)
        b.addWidget(self._accion_btn("＋ Asignar responsable", self._asignar_responsable))
        return b

    def _asignar_responsable(self):
        from assets.estilo_global import mostrar_mensaje
        from src.services.gobierno import organigrama as _O
        from src.services.gobierno import responsables as _R
        nodos = _O.listar(self.id_empresa)
        if not nodos:
            mostrar_mensaje(self, "Responsables", "Crea antes un nodo en el Organigrama.", "warning")
            return
        opciones_nodo = [(f"{n.get('nombre')} ({n.get('tipo')})", n.get("id")) for n in nodos]
        dlg = _FormDialog(self, "Asignar responsable", [
            {"key": "nodo", "label": "Nodo del organigrama", "tipo": "combo", "opciones": opciones_nodo},
            {"key": "rol_org", "label": "Rol", "tipo": "combo",
             "opciones": [(r.capitalize(), r) for r in _R.ROLES_ORG], "default": "principal"},
            {"key": "usuario", "label": "Usuario *", "ph": "Nombre de usuario"},
        ])
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        d = dlg.datos()
        if not d["usuario"]:
            mostrar_mensaje(self, "Responsables", "Indica el usuario responsable.", "warning")
            return
        if _R.asignar(d["nodo"], d["rol_org"], d["usuario"], id_empresa=self.id_empresa):
            mostrar_mensaje(self, "Responsables", "Responsable asignado correctamente.", "success")
            self._cargar()
        else:
            mostrar_mensaje(self, "Responsables", "No se pudo asignar el responsable.", "error")

    def _nuevo_nodo(self):
        from assets.estilo_global import mostrar_mensaje
        from src.services.gobierno import organigrama as _O
        nodos = _O.listar(self.id_empresa)
        opciones_padre = [("— Raíz (sin padre) —", None)] + [
            (f"{n.get('nombre')} ({n.get('tipo')})", n.get("id")) for n in nodos]
        dlg = _FormDialog(self, "Nuevo nodo del organigrama", [
            {"key": "tipo", "label": "Tipo", "tipo": "combo",
             "opciones": [(t.capitalize(), t) for t in _O.TIPOS], "default": "departamento"},
            {"key": "nombre", "label": "Nombre *", "ph": "Nombre del nodo"},
            {"key": "padre", "label": "Nodo padre", "tipo": "combo", "opciones": opciones_padre},
        ])
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        d = dlg.datos()
        if not d["nombre"]:
            mostrar_mensaje(self, "Organigrama", "El nombre es obligatorio.", "warning")
            return
        nid = _O.crear_nodo(d["tipo"], d["nombre"], padre_id=d["padre"], id_empresa=self.id_empresa)
        if nid:
            mostrar_mensaje(self, "Organigrama", "Nodo creado correctamente.", "success")
            self._cargar()
        else:
            mostrar_mensaje(self, "Organigrama", "No se pudo crear el nodo.", "error")

    def _nueva_delegacion(self):
        from assets.estilo_global import mostrar_mensaje
        dlg = _FormDialog(self, "Nueva delegación", [
            {"key": "origen", "label": "Usuario que delega (ausente) *", "ph": "usuario_origen"},
            {"key": "delegado", "label": "Usuario delegado *", "ph": "usuario_delegado"},
            {"key": "motivo", "label": "Motivo (opcional)", "ph": "Vacaciones, baja, permiso…"},
            {"key": "desde", "label": "Desde (AAAA-MM-DD, opcional)", "ph": "2026-09-08"},
            {"key": "hasta", "label": "Hasta (AAAA-MM-DD, opcional)", "ph": "2026-09-20"},
        ])
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        d = dlg.datos()
        if not d["origen"] or not d["delegado"]:
            mostrar_mensaje(self, "Delegaciones", "Indica el usuario de origen y el delegado.", "warning")
            return
        did = _svc().delegar(d["origen"], d["delegado"], motivo=d["motivo"] or None,
                             desde=d["desde"] or None, hasta=d["hasta"] or None, id_empresa=self.id_empresa)
        if did:
            mostrar_mensaje(self, "Delegaciones", "Delegación creada correctamente.", "success")
            self._cargar()
        else:
            mostrar_mensaje(self, "Delegaciones", "No se pudo crear la delegación.", "error")

    def _revocar_delegacion(self):
        from assets.estilo_global import mostrar_mensaje
        r = self.t_del.tabla.currentRow()
        if r < 0 or self.t_del.tabla.item(r, 0) is None:
            mostrar_mensaje(self, "Delegaciones", "Selecciona antes una delegación en la tabla.", "warning")
            return
        try:
            did = int(self.t_del.tabla.item(r, 0).text())
        except (TypeError, ValueError):
            return
        from src.services.gobierno import delegacion as _D
        if _D.revocar(did, id_empresa=self.id_empresa):
            mostrar_mensaje(self, "Delegaciones", "Delegación revocada.", "success")
            self._cargar()
        else:
            mostrar_mensaje(self, "Delegaciones", "No se pudo revocar la delegación.", "error")

    def _nueva_politica(self):
        from assets.estilo_global import mostrar_mensaje
        dlg = _FormDialog(self, "Nueva / editar política (empresa)", [
            {"key": "clave", "label": "Clave *", "ph": "Ej: aprobacion_max_horas"},
            {"key": "valor", "label": "Valor *", "ph": "Ej: 48"},
        ], texto_guardar="Guardar")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        d = dlg.datos()
        if not d["clave"] or not d["valor"]:
            mostrar_mensaje(self, "Políticas", "Indica la clave y el valor de la política.", "warning")
            return
        from src.services.gobierno import politicas as _P
        if _P.set_politica(d["clave"], d["valor"], id_empresa=self.id_empresa):
            mostrar_mensaje(self, "Políticas", "Política guardada correctamente.", "success")
            self._cargar()
        else:
            mostrar_mensaje(self, "Políticas", "No se pudo guardar la política.", "error")

    def _revisar_escalados(self):
        from assets.estilo_global import mostrar_mensaje
        try:
            resultado = _svc().revisar_escalados(self.id_empresa)
            n = len(resultado) if isinstance(resultado, list) else 0
            if n:
                sustantivo = "aprobación pendiente" if n == 1 else "aprobaciones pendientes"
                mostrar_mensaje(self, "Escalados",
                                f"Se {'ha' if n == 1 else 'han'} escalado {n} {sustantivo}.", "success")
            else:
                mostrar_mensaje(self, "Escalados",
                                "No hay ninguna aprobación pendiente que supere el umbral de horas.", "info")
        except Exception as e:
            logger.debug("revisar escalados: %s", e)
            mostrar_mensaje(self, "Escalados", "No se pudo revisar los escalados.", "error")
        self._cargar()

    def _cargar(self):
        emp = self.id_empresa
        svc = _svc()
        # Indicadores
        self.grid.limpiar()
        try:
            ind = svc.dashboard(emp)
            for clave, etiqueta, concepto in (("nodos_total", "Nodos", "gobierno"),
                                              ("tiendas", "Tiendas", "tienda"),
                                              ("delegaciones_activas", "Delegaciones", "usuario"),
                                              ("aprobaciones_pendientes", "Aprob. pend.", "tarea"),
                                              ("escalados", "Escalados", "riesgo")):
                self.grid.add_card(EnterpriseCard(etiqueta, ind.get(clave, 0), modo="kpi", concepto=concepto))
        except Exception as e:
            logger.debug("dashboard gobierno: %s", e)

        # Organigrama
        try:
            self.t_org.set_datos([{"Id": n.get("id"), "Tipo": n.get("tipo"), "Nombre": n.get("nombre"),
                                   "Nivel": n.get("nivel"), "Estado": n.get("estado")}
                                  for n in _importar_mapa(emp)])
        except Exception as e:
            logger.debug("organigrama: %s", e)

        # Autoridad (matriz rol → permisos)
        try:
            from src.services.gobierno import autoridad as _A
            self.t_aut.set_datos([{"Rol": rol, "Permisos": ", ".join(sorted(_A.permisos_de(rol)))}
                                  for rol in getattr(_A, "ROLES_ORG", ())])
        except Exception as e:
            logger.debug("autoridad: %s", e)

        # Delegaciones activas
        try:
            self.t_del.set_datos([{"Id": d.get("id"), "Origen": d.get("usuario_origen"),
                                   "Delegado": d.get("usuario_delegado"),
                                   "Desde": d.get("desde"), "Hasta": d.get("hasta")}
                                  for d in svc.delegaciones_activas(emp)])
        except Exception as e:
            logger.debug("delegaciones: %s", e)

        # Políticas efectivas
        try:
            from src.services.gobierno import politicas as _P
            efect = _P.efectivas(emp) if hasattr(_P, "efectivas") else {}
            filas = [{"Clave": k, "Valor": v, "Ámbito": "empresa"} for k, v in (efect or {}).items()]
            self.t_pol.set_datos(filas)
        except Exception as e:
            logger.debug("politicas: %s", e)

        # Escalados
        try:
            from src.services.gobierno.escalado import listar_escalados
            rows = listar_escalados(emp)
            self.t_esc.set_datos([{"Referencia": r.get("referencia"), "Desde": r.get("desde_usuario"),
                                   "Hacia": r.get("hacia_usuario"), "Nivel": r.get("nivel"),
                                   "Horas": r.get("horas")} for r in rows])
        except Exception as e:
            logger.debug("escalados tabla: %s", e)

        # Responsables (no hay un listado global: se itera cada nodo del organigrama y se acumulan
        # sus responsables por rol_org, mismo criterio que `responsables.py` expone).
        try:
            from src.services.gobierno import organigrama as _O
            from src.services.gobierno import responsables as _R
            filas_res = []
            for n in _O.listar(emp):
                for rol_org, usuario in (_R.responsables_de(n.get("id"), emp) or {}).items():
                    filas_res.append({"Nodo": n.get("nombre"), "Rol": rol_org, "Usuario": usuario})
            self.t_res.set_datos(filas_res)
        except Exception as e:
            logger.debug("responsables: %s", e)


def _importar_mapa(emp):
    from src.services.gobierno import organigrama as _O
    return _O.mapa(emp)
