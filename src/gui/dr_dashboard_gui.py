"""
DR-E (GUI) — Panel de Disaster Recovery. Muestra ultimo backup, RPO/RTO, replicacion,
almacenamiento, ultimo restore test e incidentes DR. Permite crear snapshot, runbook,
listar/restaurar snapshots (a un snapshot concreto o al mas cercano a un instante) y
gestionar replicacion/failover manual — antes el panel solo creaba snapshots, nunca
permitia restaurarlos (huella crítica encontrada en auditoría app-wide).

RBAC vía `services.autorizacion` (permisos `dr.ver`, `dr.snapshot`, `dr.restaurar`,
`dr.drills`, `dr.admin` — ya existían en el catálogo pero esta ventana no los comprobaba).
"""

import logging

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QTabWidget, QVBoxLayout, QWidget

from src.gui.catalogo_gestion import (_BG, _CIAN, _DIM, _btn, _btn_cargando, _combo, _dialogo_frameless,
                                      _info, _inp, _lbl, _tabla)

try:
    from assets.estilo_global import mostrar_confirmacion
except Exception:  # pragma: no cover
    mostrar_confirmacion = None

logger = logging.getLogger("gui.dr")


def _it(v):
    from PyQt6.QtWidgets import QTableWidgetItem
    return QTableWidgetItem("" if v is None else str(v))


def _confirmar(parent, titulo, mensaje):
    if mostrar_confirmacion is not None:
        return mostrar_confirmacion(parent, titulo, mensaje)
    return True


def _puede(usuario, permiso) -> bool:
    try:
        from src.services import autorizacion
        return autorizacion.puede(usuario or {}, permiso)
    except Exception:
        return True


class _TareaWorker(QObject):
    """Ejecuta una función SIN ARGUMENTOS en un QThread aparte (patrón `rfid_worker.py`: QObject +
    moveToThread, nunca toca widgets desde el hilo secundario). Los simulacros DR hacen backup/
    restore reales de la BD (pueden tardar minutos) — ejecutarlos en el hilo de UI congelaba la
    ventana entera (Windows llegaba a marcarla "no responde")."""
    terminado = pyqtSignal(object)
    fallo = pyqtSignal(str)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            r = self._fn()
        except Exception as e:
            self.fallo.emit(str(e))
            return
        self.terminado.emit(r)


class _RestaurarInstanteDialog(QDialog):
    """Pide un instante (fecha/hora) para restaurar al snapshot recuperable más cercano por
    debajo de ese instante (`dr_pitr.restaurar_a_timestamp`)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = _dialogo_frameless(self, "Restaurar a un instante", ancho=380)
        v.addWidget(_lbl("Fecha y hora (AAAA-MM-DD HH:MM:SS)"))
        self.in_ts = _inp("2026-09-09 12:00:00")
        v.addWidget(self.in_ts)
        fila = QHBoxLayout(); fila.addStretch()
        fila.addWidget(_btn("Restaurar", self.accept, primary=True))
        v.addLayout(fila)


class DRDashboardWindow(QWidget):
    def __init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw):
        super().__init__(parent)
        self._volver = callback_vuelta
        self.usuario = usuario or {}
        self.setStyleSheet(f"background:{_BG};")
        root = QVBoxLayout(self)
        cab = QHBoxLayout()
        t = QLabel("Disaster Recovery · Panel")
        t.setStyleSheet(f"color:{_CIAN};font-size:20px;font-weight:bold;")
        cab.addWidget(t); cab.addStretch()
        cab.addWidget(_btn("Crear snapshot", self._snapshot, primary=True))
        cab.addWidget(_btn("Runbook PDF", self._runbook, primary=True))
        cab.addWidget(_btn_cargando("🔄  Actualizar", self._load, primary=True))
        if callback_vuelta:
            cab.addWidget(_btn("Volver", self._volver))
        root.addLayout(cab)

        self.lbl = QLabel(""); self.lbl.setStyleSheet(f"color:{_DIM};")
        root.addWidget(self.lbl)

        self.tabs = QTabWidget()
        self.tbl = _tabla(["Indicador", "Valor"])
        self.tabs.addTab(self._envolver(self.tbl), "Panel")
        self.tabs.addTab(self._tab_snapshots(), "Snapshots")
        self.tabs.addTab(self._tab_replicacion(), "Replicación")
        root.addWidget(self.tabs)
        self._load()

    # ── construcción de pestañas ────────────────────────────────────────────
    def _envolver(self, tabla):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 12, 0, 0)
        ly.addWidget(tabla)
        return w

    def _tab_snapshots(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 12, 0, 0)
        barra = QHBoxLayout()
        self.cmb_simulacro = _combo([("Verificación diaria", "verify"),
                                     ("Restore test semanal", "restore"),
                                     ("Consistencia mensual", "consistency")])
        barra.addWidget(self.cmb_simulacro)
        self.btn_simulacro = _btn("Ejecutar simulacro", self._simulacro, primary=True)
        barra.addWidget(self.btn_simulacro)
        barra.addStretch()
        barra.addWidget(_btn("♻ Restaurar seleccionado", self._restaurar_snapshot, danger=True))
        btn_restaurar_instante = _btn("🕐 Restaurar a instante", self._restaurar_instante, danger=True)
        btn_restaurar_instante.setMinimumWidth(btn_restaurar_instante.sizeHint().width() + 36)
        barra.addWidget(btn_restaurar_instante)
        ly.addLayout(barra)
        self.tbl_snap = _tabla(["Id", "Fecha", "Backend", "Tamaño (MB)", "Estado"])
        ly.addWidget(self.tbl_snap)
        return w

    def _tab_replicacion(self):
        w = QWidget(); ly = QVBoxLayout(w); ly.setContentsMargins(0, 12, 0, 0)
        self.lbl_repl = QLabel(""); self.lbl_repl.setStyleSheet(f"color:{_DIM};")
        ly.addWidget(self.lbl_repl)
        barra = QHBoxLayout()
        barra.addWidget(_btn("🔁 Sincronizar réplica", self._sync_replica, primary=True))
        barra.addWidget(_btn("⚠ Promover réplica (failover)", self._promover_replica, danger=True))
        barra.addStretch()
        ly.addLayout(barra)
        ly.addStretch()
        return w

    # ── carga ────────────────────────────────────────────────────────────────
    def _load(self):
        try:
            from src.services.dr import dr_dashboard
            p = dr_dashboard.panel()
            filas = [
                ("Último backup (horas)", p.get("ultimo_backup_horas")),
                ("RPO (horas)", (p.get("rpo") or {}).get("rpo_horas")),
                ("RTO estimado (min)", (p.get("rto") or {}).get("rto_min")),
                ("Replicación", (p.get("replicacion") or {}).get("estado")),
                ("Almacenamiento", (p.get("almacenamiento") or {}).get("backend")),
                ("Último restore test", (p.get("ultimo_restore_test") or {}).get("estado")),
                ("Incidentes DR", len(p.get("incidentes_dr") or [])),
            ]
            self.tbl.setRowCount(len(filas))
            for i, (k, v) in enumerate(filas):
                self.tbl.setItem(i, 0, _it(k)); self.tbl.setItem(i, 1, _it(v))
            self.lbl.setText("Panel DR actualizado.")
        except Exception as e:
            logger.error("load DR: %s", e)
            self.lbl.setText(f"Error: {e}")
        self._load_snapshots()
        self._load_replicacion()

    def _load_snapshots(self):
        try:
            from src.services.dr import dr_pitr
            snaps = dr_pitr.listar_snapshots(limite=100)
            self.tbl_snap.setRowCount(len(snaps))
            for i, s in enumerate(snaps):
                tam_mb = round((s.get("tamano_bytes") or 0) / 1_000_000, 1)
                for j, v in enumerate([s.get("id"), s.get("creado_en"), s.get("backend"),
                                       tam_mb, s.get("estado")]):
                    self.tbl_snap.setItem(i, j, _it(v))
        except Exception as e:
            logger.error("load snapshots: %s", e)

    def _load_replicacion(self):
        try:
            from src.services.dr import dr_replicacion
            r = dr_replicacion.estado_replicacion()
            if r.get("estado") == "no_configurada":
                self.lbl_repl.setText(
                    "Replicación no configurada (variable de entorno SM_DR_REPLICA_HOST sin definir). "
                    "Los botones de esta pestaña no tendrán efecto hasta configurarla.")
            else:
                self.lbl_repl.setText(f"Replicación: {r.get('estado')} · réplica: {r.get('replica')} · "
                                      f"modo: {r.get('modo')}")
        except Exception as e:
            logger.error("load replicacion: %s", e)
            self.lbl_repl.setText(f"Error: {e}")

    # ── acciones existentes ──────────────────────────────────────────────────
    def _snapshot(self):
        if not _puede(self.usuario, "dr.snapshot"):
            _info(self, "Snapshot", "No tiene permiso para crear snapshots (dr.snapshot).")
            return
        from src.services.dr import dr_pitr
        r = dr_pitr.crear_snapshot(motivo="manual_gui")
        _info(self, "Snapshot", "Snapshot creado correctamente." if r.get("ok")
             else f"Error al crear el snapshot: {r.get('error')}")
        self._load()

    def _runbook(self):
        from src.services.dr import dr_dashboard
        r = dr_dashboard.runbook("pdf")
        _info(self, "Runbook", f"Runbook generado en: {r.get('ruta')}" if r.get("ok")
             else "No se pudo generar el runbook.")
        self._load()

    # ── simulacros (verify_diario / restore_test_semanal / consistency_mensual) ─────
    def _simulacro(self):
        if not _puede(self.usuario, "dr.drills"):
            _info(self, "Simulacro DR", "No tiene permiso para ejecutar simulacros (dr.drills).")
            return
        tipo = self.cmb_simulacro.currentData()
        from src.services.dr import dr_drills
        fn = {"verify": dr_drills.verify_diario, "restore": dr_drills.restore_test_semanal,
              "consistency": dr_drills.consistency_mensual}[tipo]
        self.btn_simulacro.setEnabled(False)
        self._simulacro_texto_orig = self.btn_simulacro.text()
        self.btn_simulacro.setText("⏳ Ejecutando…")
        self._simulacro_tipo = tipo
        self._simulacro_thread = QThread()
        self._simulacro_worker = _TareaWorker(fn)
        self._simulacro_worker.moveToThread(self._simulacro_thread)
        self._simulacro_thread.started.connect(self._simulacro_worker.run)
        self._simulacro_worker.terminado.connect(self._simulacro_ok)
        self._simulacro_worker.fallo.connect(self._simulacro_error)
        self._simulacro_worker.terminado.connect(self._simulacro_thread.quit)
        self._simulacro_worker.fallo.connect(self._simulacro_thread.quit)
        self._simulacro_thread.finished.connect(self._simulacro_thread.deleteLater)
        self._simulacro_thread.start()

    def _simulacro_fin(self):
        self.btn_simulacro.setEnabled(True)
        self.btn_simulacro.setText(self._simulacro_texto_orig)

    def _simulacro_ok(self, r):
        self._simulacro_fin()
        _info(self, "Simulacro DR",
             f"Simulacro «{self._simulacro_tipo}»: {'OK' if r.get('ok') else 'FALLIDO'}.")
        self._load()

    def _simulacro_error(self, msg):
        self._simulacro_fin()
        _info(self, "Simulacro DR", f"Error al ejecutar el simulacro: {msg}")

    # ── snapshots: restaurar ─────────────────────────────────────────────────
    def _snapshot_sel(self):
        r = self.tbl_snap.currentRow()
        if r < 0 or self.tbl_snap.item(r, 0) is None:
            _info(self, "Snapshots", "Selecciona antes un snapshot en la tabla.")
            return None
        try:
            return int(self.tbl_snap.item(r, 0).text())
        except (TypeError, ValueError):
            return None

    def _restaurar_snapshot(self):
        if not _puede(self.usuario, "dr.restaurar"):
            _info(self, "Restaurar snapshot", "No tiene permiso para restaurar (dr.restaurar).")
            return
        sid = self._snapshot_sel()
        if not sid:
            return
        if not _confirmar(self, "Restaurar snapshot",
                          f"¿RESTAURAR la base de datos al snapshot #{sid}?\n\n"
                          "Esto SOBRESCRIBIRÁ todos los datos actuales con los del snapshot. "
                          "Esta acción no se puede deshacer."):
            return
        from src.services.dr import dr_pitr
        r = dr_pitr.restaurar_a_snapshot(sid)
        _info(self, "Restaurar snapshot",
             f"Restaurado correctamente al snapshot #{sid}." if r.get("ok")
             else f"No se pudo restaurar: {r.get('error') or r.get('detalle')}")
        self._load()

    def _restaurar_instante(self):
        if not _puede(self.usuario, "dr.restaurar"):
            _info(self, "Restaurar a instante", "No tiene permiso para restaurar (dr.restaurar).")
            return
        dlg = _RestaurarInstanteDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        ts = dlg.in_ts.text().strip()
        if not ts:
            return
        if not _confirmar(self, "Restaurar a un instante",
                          f"¿RESTAURAR la base de datos al snapshot recuperable más cercano "
                          f"anterior a «{ts}»?\n\nEsto SOBRESCRIBIRÁ todos los datos actuales. "
                          "Esta acción no se puede deshacer."):
            return
        from src.services.dr import dr_pitr
        r = dr_pitr.restaurar_a_timestamp(ts)
        _info(self, "Restaurar a instante", "Restaurado correctamente." if r.get("ok")
             else f"No se pudo restaurar: {r.get('error')}")
        self._load()

    # ── replicación / failover manual ───────────────────────────────────────
    def _sync_replica(self):
        if not _puede(self.usuario, "dr.admin"):
            _info(self, "Replicación", "No tiene permiso para gestionar la replicación (dr.admin).")
            return
        from src.services.dr import dr_replicacion
        r = dr_replicacion.sincronizar_replicas()
        if r.get("estado") == "no_configurada":
            _info(self, "Replicación", "La replicación no está configurada (SM_DR_REPLICA_HOST).")
        else:
            _info(self, "Replicación", "Sincronización delegada a MariaDB replication." if r.get("ok")
                 else "No se pudo sincronizar.")
        self._load()

    def _promover_replica(self):
        if not _puede(self.usuario, "dr.admin"):
            _info(self, "Replicación", "No tiene permiso para gestionar la replicación (dr.admin).")
            return
        from src.services.dr import dr_replicacion
        if not dr_replicacion.configurada():
            _info(self, "Replicación", "La replicación no está configurada (SM_DR_REPLICA_HOST).")
            return
        if not _confirmar(self, "Promover réplica (failover)",
                          "¿Solicitar la promoción de la réplica a primaria?\n\n"
                          "Esto marca la intención de failover manual; la ejecución real la realiza "
                          "el operador/infraestructura según el runbook. Úsalo solo ante una caída "
                          "confirmada de la primaria."):
            return
        r = dr_replicacion.promover_replica()
        _info(self, "Replicación", "Promoción de réplica solicitada." if r.get("ok")
             else "No se pudo solicitar la promoción.")
        self._load()
