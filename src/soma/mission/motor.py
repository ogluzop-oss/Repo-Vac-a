"""
MissionEngine (Fase 6) — el "Director de Orquesta" de SOMA. Convierte un OBJETIVO en una MISIÓN,
la descompone en tareas con dependencias, coordina a los Especialistas IA (AgentManager) ejecutando
en PARALELO lo independiente, consolida una ÚNICA respuesta y solicita aprobaciones (Autonomía/
Workflow/Gobierno) para lo crítico — sin ejecutar acciones críticas por su cuenta. El usuario habla
SOLO con SOMA; los especialistas nunca hablan con el usuario.

Todo en SEGUNDO PLANO (hilos daemon + pool) para no bloquear la UI; los avances vuelven al hilo
principal por señales Qt. Reutiliza AgentManager/Simulador/Predicción/Gemelo/Autonomía/Scheduler/BD.
"""

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from PyQt6.QtCore import QObject, pyqtSignal

from src.soma.mission import modelo as M
from src.soma.mission import plantillas

logger = logging.getLogger("soma.mission")

_ESPECIALISTA_LEGIBLE = {
    "financiero": "Tesorería", "tesoreria": "Tesorería", "comercial": "Comercial", "ventas": "Comercial",
    "compras": "Compras", "stock": "Inventario", "inventario": "Inventario", "rrhh": "RRHH",
    "fiscal": "Fiscal", "logistico": "Logística", "auditoria": "Auditoría",
    "prediccion": "Predicción", "simulacion": "Simulación", "gemelo": "Gemelo Digital",
    "aprobacion": "Workflow", "bi": "Centro de Inteligencia",
}


def _emp(id_empresa=None):
    try:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)
    except Exception:
        return id_empresa


class MissionEngine(QObject):
    actualizada = pyqtSignal(str)          # mision_id (str) → refrescar workspace
    mensaje = pyqtSignal(str, str)         # (mision_id, texto natural) → SOMA lo dice
    terminada = pyqtSignal(str, object)    # (mision_id, resultado consolidado)

    def __init__(self):
        super().__init__()
        self._misiones = {}                 # id_str → Mision
        self._lock = threading.RLock()
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="soma-mission")
        self._activa = None                 # id_str de la misión en curso
        self._cola = []                     # ids en espera (por prioridad)

    # ── API pública ───────────────────────────────────────────────────────────
    def es_mision(self, texto):
        return plantillas.detectar(texto)

    def crear(self, texto, *, usuario=None, id_empresa=None, prioridad=M.P_NORMAL):
        clave = plantillas.detectar(texto)
        if not clave:
            return None
        emp = _emp(id_empresa)
        m = plantillas.construir(clave, texto, usuario=usuario, id_empresa=emp, prioridad=prioridad)
        self._persistir_nueva(m)
        with self._lock:
            self._misiones[str(m.id)] = m
        return m

    def iniciar(self, m):
        """Encola/inicia una misión. Si hay otra en curso, se encola por prioridad."""
        mid = str(m.id)
        with self._lock:
            if self._activa is not None and self._activa != mid:
                self._cola.append(mid)
                self._cola.sort(key=lambda i: M.orden_prioridad(self._misiones[i].prioridad), reverse=True)
                self.mensaje.emit(mid, f"Tomo nota del objetivo «{m.objetivo}». Lo pongo en cola tras la "
                                       "misión actual.")
                return
            self._activa = mid
        threading.Thread(target=self._orquestar, args=(m,), daemon=True,
                         name=f"soma-orq-{mid}").start()

    def mision(self, mid):
        with self._lock:
            return self._misiones.get(str(mid))

    def mision_dict(self, mid):
        with self._lock:
            m = self._misiones.get(str(mid))
            return m.to_dict() if m else None

    def activa(self):
        return self.mision(self._activa) if self._activa else None

    # ── Control (pausa/continúa/cancela) ──────────────────────────────────────
    def pausar(self, mid=None):
        m = self.mision(mid) if mid else self.activa()
        if m:
            m._pausada = True
            m.estado = M.M_PAUSADA
            self.actualizada.emit(str(m.id))
            self.mensaje.emit(str(m.id), "De acuerdo, pauso la misión. Dime «continúa» cuando quieras.")

    def reanudar(self, mid=None):
        m = self.mision(mid) if mid else self.activa()
        if m:
            m._pausada = False
            m.estado = M.M_EN_CURSO
            self.actualizada.emit(str(m.id))
            self.mensaje.emit(str(m.id), "Retomo la misión donde la dejamos.")

    def cancelar(self, mid=None):
        m = self.mision(mid) if mid else self.activa()
        if m:
            m._cancelada = True
            m.estado = M.M_CANCELADA
            self.actualizada.emit(str(m.id))
            self.mensaje.emit(str(m.id), "Misión cancelada. No he ejecutado ninguna acción crítica.")

    # ── Estado natural ("¿cómo va?") ──────────────────────────────────────────
    def estado_natural(self, mid=None) -> str:
        m = self.mision(mid) if mid else self.activa()
        if not m:
            return "Ahora mismo no tengo ninguna misión en marcha."
        hechas = [t for t in m.tareas if t.estado == M.T_HECHA]
        curso = [t for t in m.tareas if t.estado == M.T_EN_CURSO]
        esperando = [t for t in m.tareas if t.estado == M.T_ESPERA_APROB]
        partes = [f"Misión «{m.objetivo}»: {len(hechas)}/{len(m.tareas)} tareas completadas."]
        if curso:
            partes.append("Ahora mismo: " + ", ".join(
                _ESPECIALISTA_LEGIBLE.get(t.dominio, t.titulo) for t in curso) + ".")
        if esperando:
            partes.append("A la espera de aprobación en Workflow.")
        return " ".join(partes)

    # ── Explicabilidad ────────────────────────────────────────────────────────
    def explicar(self, mid=None) -> str:
        m = self.mision(mid) if mid else self.activa()
        if not m:
            return "No tengo una misión reciente que explicar."
        esp = ", ".join(_ESPECIALISTA_LEGIBLE.get(d, d) for d in
                        sorted({t.especialista for t in m.tareas if t.especialista}))
        pasos = "; ".join(f"{t.titulo}" for t in m.tareas)
        return (f"Para «{m.objetivo}» consulté a estos especialistas: {esp}. "
                f"Descompuse el objetivo en: {pasos}. Ejecuté en paralelo lo independiente y esperé a "
                "las dependencias; después consolidé todo en una sola conclusión. Las acciones críticas "
                "quedaron a la espera de aprobación (Workflow/Gobierno).")

    # ── Orquestación (hilo de fondo) ──────────────────────────────────────────
    def _orquestar(self, m):
        t0 = time.time()
        m.estado = M.M_EN_CURSO
        self._set_estado_bd(m)
        self.mensaje.emit(str(m.id), f"Entendido. Me pongo con «{m.objetivo}». Voy a coordinar a los "
                                     "especialistas necesarios y te aviso del progreso.")
        self.actualizada.emit(str(m.id))
        ctx = {"id_empresa": m.id_empresa, "usuario": m.usuario, "rol": "ADMINISTRADOR",
               "objetivo": m.objetivo}
        try:
            while True:
                if m._cancelada:
                    break
                if m._pausada:
                    time.sleep(0.2)
                    continue
                listas = m.listas()
                en_curso = [t for t in m.tareas if t.estado == M.T_EN_CURSO]
                if not listas and not en_curso:
                    break   # nada listo y nada en curso → terminado (o bloqueado)
                # Lanzar en PARALELO todas las tareas listas independientes.
                futuros = {}
                for t in listas:
                    t.estado = M.T_EN_CURSO
                    self._msg_inicio(m, t)
                    self.actualizada.emit(str(m.id))
                    futuros[self._pool.submit(self._ejecutar_tarea, m, t, ctx)] = t
                # Esperar a que terminen las lanzadas (y las que ya estaban en curso se resuelven solas).
                for fut in list(futuros):
                    t = futuros[fut]
                    try:
                        res = fut.result()
                    except Exception as e:
                        res = {"__error__": str(e)}
                    self._resolver_tarea(m, t, res)
                    self.actualizada.emit(str(m.id))
            # Consolidación / cierre
            if m._cancelada:
                self._cerrar(m, M.M_CANCELADA, t0)
                return
            espera = any(t.estado == M.T_ESPERA_APROB for t in m.tareas)
            estado_final = M.M_ESPERA_APROB if espera else (
                M.M_FALLIDA if m.errores and not any(t.estado == M.T_HECHA for t in m.tareas)
                else M.M_COMPLETADA)
            resultado = self._consolidar(m)
            m.resultado = resultado
            self._cerrar(m, estado_final, t0)
            self.terminada.emit(str(m.id), resultado)
        except Exception as e:
            logger.error("orquestación misión %s: %s", m.id, e)
            self._cerrar(m, M.M_FALLIDA, t0)
        finally:
            self._siguiente_en_cola()

    def _ejecutar_tarea(self, m, t, ctx):
        """Ejecuta UNA tarea con el especialista/servicio adecuado. Devuelve dict resultado."""
        t.progreso = 30
        dom = t.dominio
        try:
            if dom == "simulacion":
                from src.services import simulador
                r = simulador.servicio().simular_directo(getattr(m, "_sim_vars", []) or [], m.id_empresa)
                dif = {d["metrica"]: d for d in r.get("diferencias", [])}
                return {"texto": f"Simulación económica: ingresos "
                        f"{dif.get('ingresos',{}).get('delta_pct',0):+.1f}%, beneficio "
                        f"{dif.get('beneficio',{}).get('delta_pct',0):+.1f}% (VIRTUAL).",
                        "fuentes": ["Simulador"]}
            if dom == "prediccion":
                from src.services import prediccion
                rs = prediccion.servicio().riesgos(m.id_empresa) or []
                txt = "; ".join((x.get("texto") or "") for x in rs[:2] if x) or "sin riesgos destacados"
                return {"texto": f"Predicción: {txt}.", "fuentes": ["Predicción"]}
            if dom == "gemelo":
                from src.services import gemelo
                g = gemelo.servicio().estado_empresa(m.id_empresa)
                return {"texto": g.get("resumen", ""), "fuentes": ["Gemelo Digital"]}
            if dom == "aprobacion":
                return self._preparar_aprobacion(m, t)
            # Resto → Especialista IA (AgentManager). SOMA coordina; el usuario no ve al agente.
            from src.services.agentes import manager
            ag = manager().delegar(dom, m.objetivo, dict(ctx))
            if ag and ag.get("texto"):
                return {"texto": ag["texto"], "fuentes": ag.get("fuentes", [])}
            return {"texto": f"{t.titulo}: sin datos relevantes.", "fuentes": []}
        except Exception as e:
            return {"__error__": str(e)}

    def _preparar_aprobacion(self, m, t):
        """Acción CRÍTICA: NUNCA se ejecuta directa. Se prepara un plan gobernado (Autonomía) y se
        deja a la espera de aprobación (Workflow/Gobierno)."""
        t.estado = M.T_ESPERA_APROB
        m.aprobaciones += 1
        try:
            from src.services import autonomia
            svc = autonomia.servicio()
            pid = svc.crear_plan(f"Misión: {m.objetivo}", descripcion="Generado por SOMA (misión)",
                                 usuario=m.usuario, id_empresa=m.id_empresa)
            return {"texto": f"He dejado preparada la parte crítica como plan #{pid}, a la espera de "
                    "aprobación por Workflow/Gobierno. No he ejecutado nada por mi cuenta.",
                    "fuentes": ["Autonomía", "Workflow", "Gobierno"], "espera_aprobacion": True}
        except Exception as e:
            logger.debug("preparar aprobación: %s", e)
            return {"texto": "La parte crítica queda a la espera de aprobación (Workflow/Gobierno).",
                    "fuentes": ["Workflow", "Gobierno"], "espera_aprobacion": True}

    def _resolver_tarea(self, m, t, res):
        if isinstance(res, dict) and res.get("__error__"):
            t.estado = M.T_FALLIDA
            t.error = res["__error__"]
            m.errores += 1
            self.mensaje.emit(str(m.id), f"He tenido un problema con «{t.titulo}», pero continúo con el "
                                         "resto de la misión.")
        elif isinstance(res, dict) and res.get("espera_aprobacion"):
            t.estado = M.T_ESPERA_APROB
            t.resultado = res
            self.mensaje.emit(str(m.id), "Estoy esperando la aprobación del Workflow para la parte crítica.")
        else:
            t.estado = M.T_HECHA
            t.progreso = 100
            t.resultado = res if isinstance(res, dict) else {"texto": str(res)}
            self._msg_fin(m, t)
        self._persistir_tarea(m, t)

    def _consolidar(self, m):
        """Recoge todos los resultados, elimina duplicados y construye UNA respuesta coherente."""
        textos, fuentes = [], set()
        for t in m.tareas:
            r = t.resultado or {}
            if r.get("texto"):
                textos.append(r["texto"])
            for f in (r.get("fuentes") or []):
                fuentes.add(f)
        # Dedup preservando orden
        vistos, unicos = set(), []
        for tx in textos:
            k = tx.strip().lower()
            if k and k not in vistos:
                vistos.add(k)
                unicos.append(tx.strip())
        resumen = (f"Misión «{m.objetivo}» completada. Esto es lo que he coordinado:\n"
                   + "\n".join(f"• {u}" for u in unicos)) if unicos else \
                  f"Misión «{m.objetivo}» completada."
        visual = {"tipo": "tabla", "columnas": ["Tarea", "Especialista", "Estado"],
                  "filas": [{"Tarea": t.titulo, "Especialista": _ESPECIALISTA_LEGIBLE.get(t.dominio, t.dominio),
                             "Estado": t.estado} for t in m.tareas]}
        return {"texto": resumen, "fuentes": sorted(fuentes), "visual": visual}

    # ── Mensajes naturales (nunca técnicos) ───────────────────────────────────
    def _msg_inicio(self, m, t):
        esp = _ESPECIALISTA_LEGIBLE.get(t.dominio, t.titulo)
        frases = {"prediccion": "Predicción está calculando la demanda.",
                  "simulacion": "Estoy simulando el impacto económico.",
                  "aprobacion": "Preparo la parte crítica para pasarla por aprobación.",
                  "rrhh": "Ahora estoy consultando al Especialista de RRHH.",
                  "compras": "Compras está buscando proveedores.",
                  "financiero": "Estoy con el análisis financiero.",
                  "stock": "Reviso las necesidades de stock.",
                  "comercial": "Analizo la parte comercial y de clientes."}
        self.mensaje.emit(str(m.id), frases.get(t.dominio, f"Ahora estoy con {esp.lower()}."))

    def _msg_fin(self, m, t):
        frases = {"financiero": "He terminado el análisis financiero.",
                  "prediccion": "Ya tengo la predicción de demanda.",
                  "simulacion": "Simulación económica lista.",
                  "rrhh": "Listo lo de personal.", "compras": "Comparativa de proveedores lista.",
                  "stock": "Necesidades de stock calculadas.", "comercial": "Análisis comercial hecho."}
        self.mensaje.emit(str(m.id), frases.get(t.dominio, f"He terminado: {t.titulo}."))

    def _siguiente_en_cola(self):
        siguiente = None
        with self._lock:
            self._activa = None
            if self._cola:
                siguiente = self._misiones.get(self._cola.pop(0))
        if siguiente is not None:
            self.iniciar(siguiente)   # arranca la siguiente misión de la cola (por prioridad)

    # ── Persistencia (historial de misiones) ──────────────────────────────────
    def _persistir_nueva(self, m):
        try:
            from src.db.conexion import obtener_conexion
            with obtener_conexion() as c, c.cursor() as cur:
                cur.execute("INSERT INTO soma_misiones (id_empresa, usuario, objetivo, plantilla, "
                            "prioridad, estado) VALUES (%s,%s,%s,%s,%s,%s)",
                            (m.id_empresa, m.usuario, m.objetivo[:255], m.plantilla, m.prioridad, m.estado))
                m.id = cur.lastrowid
                for i, t in enumerate(m.tareas):
                    cur.execute("INSERT INTO soma_mision_tareas (id_mision, clave, orden, titulo, "
                                "dominio, deps, paralelo, especialista) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                                (m.id, t.clave, i, t.titulo[:160], t.dominio, json.dumps(t.deps),
                                 1 if t.paralelo else 0, t.especialista))
                c.commit()
        except Exception as e:
            logger.debug("persistir misión: %s", e)
            if m.id is None:
                m.id = int(time.time() * 1000)   # id efímero si la BD no está

    def _persistir_tarea(self, m, t):
        try:
            from src.db.conexion import obtener_conexion
            with obtener_conexion() as c, c.cursor() as cur:
                cur.execute("UPDATE soma_mision_tareas SET estado=%s, progreso=%s, resultado=%s "
                            "WHERE id_mision=%s AND clave=%s",
                            (t.estado, t.progreso, ((t.resultado or {}).get("texto") or "")[:4000],
                             m.id, t.clave))
                c.commit()
        except Exception as e:
            logger.debug("persistir tarea: %s", e)

    def _set_estado_bd(self, m):
        try:
            from src.db.conexion import obtener_conexion
            with obtener_conexion() as c, c.cursor() as cur:
                cur.execute("UPDATE soma_misiones SET estado=%s WHERE id=%s", (m.estado, m.id))
                c.commit()
        except Exception:
            pass

    def _cerrar(self, m, estado, t0):
        m.estado = estado
        m.cerrada = time.time()
        dur = int((m.cerrada - t0) * 1000)
        try:
            from src.db.conexion import obtener_conexion
            with obtener_conexion() as c, c.cursor() as cur:
                cur.execute("UPDATE soma_misiones SET estado=%s, especialistas=%s, resultado=%s, "
                            "aprobaciones=%s, errores=%s, duracion_ms=%s, cerrada=NOW() WHERE id=%s",
                            (estado, json.dumps(m.especialistas_usados()),
                             ((m.resultado or {}).get("texto") or "")[:8000], m.aprobaciones,
                             m.errores, dur, m.id))
                c.commit()
        except Exception as e:
            logger.debug("cerrar misión: %s", e)
        self.actualizada.emit(str(m.id))


_motor = None


def engine() -> MissionEngine:
    """Devuelve el MissionEngine residente (singleton)."""
    global _motor
    if _motor is None:
        _motor = MissionEngine()
    return _motor
