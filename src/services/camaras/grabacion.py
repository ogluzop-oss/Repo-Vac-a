"""
Grabación de cámaras (RecorderService) — grabación continua 24 h, DEGRADABLE.

Cada cámara graba de su `fuente` (URL RTSP/ONVIF vía OpenCV) o, si no hay fuente/real, de un feed
SIMULADO (frames sintéticos con fecha/hora superpuesta). Escribe el fichero del día
`documentos/grabaciones/<id_empresa>/<id_centro>/<id_camara>/<YYYY-MM-DD>.mp4` (aislado por tenant/
departamento) y lo registra en `camaras_grabaciones` + Documentos. La grabación NO se detiene por
reproducir. API-First (sin PyQt). cv2/numpy en importación perezosa (robustez).
"""

import datetime as _dt
import logging
import os
import threading

logger = logging.getLogger("camaras.grabacion")

_ANCHO, _ALTO, _FPS = 320, 240, 4   # ligero (simulado); una cámara real usa su propia resolución
RETENCION_DIAS = 30                 # días de grabaciones que se conservan (purga automática de lo anterior)
_REINTENTO_SEG = 5                  # cada cuánto se intenta reconectar una fuente real caída


def _base_grabaciones():
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    return os.path.join(raiz, "documentos", "grabaciones")


def ruta_dia(id_empresa, id_centro, id_camara, fecha=None) -> str:
    fecha = fecha or _dt.date.today().isoformat()
    carpeta = os.path.join(_base_grabaciones(), str(id_empresa), str(id_centro), str(id_camara))
    os.makedirs(carpeta, exist_ok=True)
    return os.path.join(carpeta, f"{fecha}.mp4")


def _frame_simulado(texto):
    import numpy as np
    img = np.zeros((_ALTO, _ANCHO, 3), dtype=np.uint8)
    img[:] = (18, 18, 22)
    try:
        import cv2
        cv2.putText(img, texto, (10, _ALTO - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 198), 1)
        cv2.circle(img, (_ANCHO - 20, 20), 6, (60, 60, 240), -1)   # "REC"
    except Exception:
        pass
    return img


def _frame_sin_senal(w, h, texto):
    """Fotograma honesto de PÉRDIDA DE SEÑAL (fuente real caída). NO fabrica imagen de vigilancia: deja
    constancia de que la cámara estaba sin señal en ese momento."""
    import numpy as np
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:] = (0, 0, 35)
    try:
        import cv2
        cv2.putText(img, "SIN SENAL", (max(5, w // 2 - 90), h // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
        cv2.putText(img, texto, (10, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
    except Exception:
        pass
    return img


def _abrir_captura(fuente):
    """Abre la fuente (RTSP/ONVIF/fichero) con OpenCV. Devuelve el VideoCapture abierto o None."""
    try:
        import cv2
        cap = cv2.VideoCapture(fuente)
        if not cap.isOpened():
            cap.release()
            return None
        return cap
    except Exception:
        return None


_FFMPEG = None   # ruta del binario ffmpeg (cacheada); "" = no instalado


def _ffmpeg_disponible() -> bool:
    """¿Está FFmpeg instalado? Habilita la grabación de PRODUCCIÓN por stream-copy (sin re-codificar)."""
    global _FFMPEG
    if _FFMPEG is None:
        import shutil
        _FFMPEG = shutil.which("ffmpeg") or ""
    return bool(_FFMPEG)


def _registrar_grabacion(camara, fecha, ruta, duracion_seg, estado):
    from src.db.conexion import obtener_conexion
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO camaras_grabaciones (id_empresa, id_centro, id_camara, fecha, ruta, "
                "duracion_seg, estado) VALUES (%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE ruta=VALUES(ruta), duracion_seg=VALUES(duracion_seg), "
                "estado=VALUES(estado), actualizado=NOW()",
                (camara.get("id_empresa"), camara.get("id_centro"), camara.get("id"), fecha, ruta,
                 int(duracion_seg), estado))
            conn.commit()
    except Exception as e:
        logger.debug("registrar grabacion: %s", e)
    if estado == "cerrada":
        try:
            from src.db.documentos import registrar_documento
            id_tienda = camara.get("id_centro") if camara.get("tipo_centro") == "tienda" else None
            registrar_documento(ruta, tipo="grabacion", nombre=f"{fecha}.mp4", referencia=str(fecha),
                                id_empresa=camara.get("id_empresa"), id_tienda=id_tienda)
        except Exception:
            pass


def grabar_dia(camara, *, fecha=None, duracion_seg=1, fps=_FPS, stop_event=None,
               reintento_seg=_REINTENTO_SEG, motor="auto", audio=True, detectar=True) -> str | None:
    """Graba el fichero del día de una cámara durante `duracion_seg` (o hasta `stop_event`).

    En PRODUCCIÓN usa FFmpeg por STREAM-COPY (copia los paquetes sin re-codificar → CPU mínima, códec y fps
    NATIVOS, base de tiempo correcta) si FFmpeg está instalado. Si no, degrada a OpenCV con el fps REAL del
    stream (reconexión + 'SIN SEÑAL'); si la fuente es 'simulado', feed de demo. `motor` ∈ {auto,ffmpeg,opencv}.
    """
    fecha = fecha or _dt.date.today().isoformat()
    ruta = ruta_dia(camara.get("id_empresa"), camara.get("id_centro"), camara.get("id"), fecha)
    fuente_visible = camara.get("fuente") or "simulado"          # enmascarada (sin contraseña)
    fuente_real = bool(fuente_visible) and fuente_visible != "simulado"
    url = _fuente_conexion(camara) or fuente_visible             # URL REAL (credenciales descifradas)
    if fuente_real and motor in ("auto", "ffmpeg") and _ffmpeg_disponible():
        r = grabar_dia_ffmpeg(camara, fecha=fecha, duracion_seg=duracion_seg, stop_event=stop_event,
                              ruta=ruta, fuente=url, audio=audio)
        if r or motor == "ffmpeg":
            return r
        # ffmpeg falló en modo 'auto' → degrada a OpenCV (no se pierde la grabación).
    return _grabar_dia_opencv(camara, ruta=ruta, fecha=fecha, duracion_seg=duracion_seg, fps=fps,
                              stop_event=stop_event, reintento_seg=reintento_seg, fuente=url,
                              fuente_real=fuente_real, detectar=detectar)


def _fuente_conexion(camara):
    """URL REAL de conexión (descifra las credenciales RTSP protegidas). Nunca se registra en logs."""
    try:
        from src.services.camaras.registro import fuente_efectiva
        return fuente_efectiva(camara)
    except Exception:
        return camara.get("fuente")


def grabar_dia_ffmpeg(camara, *, fecha=None, duracion_seg=1, stop_event=None, ruta=None,
                      fuente=None, audio=True) -> str | None:
    """Grabación de PRODUCCIÓN por STREAM-COPY con FFmpeg: copia los paquetes RTSP (vídeo + audio) al fichero
    SIN decodificar ni re-codificar → CPU mínima, códec/fps NATIVOS, duración/velocidad correctas. Reconexión
    de red por FFmpeg; mp4 FRAGMENTADO (reproducible aunque se interrumpa). Degradable: None si falta ffmpeg.
    `audio=False` graba solo vídeo (`-an`) para despliegues con restricciones legales de captación de sonido."""
    import subprocess
    import time
    fecha = fecha or _dt.date.today().isoformat()
    ruta = ruta or ruta_dia(camara.get("id_empresa"), camara.get("id_centro"), camara.get("id"), fecha)
    fuente = fuente or _fuente_conexion(camara)
    if not _ffmpeg_disponible() or not fuente:
        return None
    cmd = [_FFMPEG, "-nostdin", "-loglevel", "error", "-rtsp_transport", "tcp",
           "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
           "-i", str(fuente), "-t", str(max(1, int(duracion_seg))), "-c", "copy"]
    if not audio:
        cmd.append("-an")                    # sin audio (solo vídeo)
    cmd += ["-movflags", "+frag_keyframe+empty_moov+default_base_moof", "-y", ruta]
    _registrar_grabacion(camara, fecha, ruta, 0, "grabando")
    t0 = time.time()
    try:
        from src.utils.plataforma import kwargs_sin_consola
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                stdin=subprocess.DEVNULL, **kwargs_sin_consola())
    except Exception as e:
        logger.warning("ffmpeg no se pudo lanzar: %s", e)
        _registrar_grabacion(camara, fecha, ruta, 0, "error")
        return None
    try:
        while True:
            if stop_event is not None and stop_event.is_set():
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except Exception:
                    proc.kill()
                break
            try:
                proc.wait(timeout=1)
                break
            except subprocess.TimeoutExpired:
                continue
    finally:
        if proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
    valido = os.path.exists(ruta) and os.path.getsize(ruta) > 0
    _registrar_grabacion(camara, fecha, ruta, round(time.time() - t0, 1), "cerrada" if valido else "error")
    return ruta if valido else None


def _grabar_dia_opencv(camara, *, ruta, fecha, duracion_seg, fps, stop_event, reintento_seg, fuente,
                       fuente_real, detectar=True) -> str | None:
    """Fallback OpenCV (cuando no hay FFmpeg): decodifica y re-encoda, pero usando el fps REAL del stream
    (corrige la velocidad/duración) y con reconexión + fotogramas 'SIN SEÑAL'. Como decodifica fotogramas,
    ejecuta además la DETECCIÓN DE MOVIMIENTO (solo sobre imagen REAL de la cámara) y registra eventos."""
    try:
        import cv2
    except Exception as e:
        logger.warning("cv2 no disponible: %s", e)
        return None
    import time
    detector = registrar_evento = None
    ultimo_evento, cooldown_evt = 0.0, 10
    if detectar and fuente_real:
        try:
            from src.services.camaras.deteccion import COOLDOWN_SEG, DetectorMovimiento, registrar_evento
            detector = DetectorMovimiento()
            cooldown_evt = COOLDOWN_SEG
        except Exception:
            detector = registrar_evento = None
    cap = _abrir_captura(fuente) if fuente_real else None
    w, h, fps_efectivo = _ANCHO, _ALTO, fps
    if cap is not None:
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or _ANCHO) or _ANCHO
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or _ALTO) or _ALTO
        try:
            f = float(cap.get(cv2.CAP_PROP_FPS) or 0)
        except (TypeError, ValueError):
            f = 0.0
        if 1.0 <= f <= 60.0:                 # fps REAL del stream (si es fiable)
            fps_efectivo = int(round(f))
    writer = cv2.VideoWriter(ruta, cv2.VideoWriter_fourcc(*"mp4v"), fps_efectivo, (w, h))
    _registrar_grabacion(camara, fecha, ruta, 0, "grabando")
    total = max(1, int(duracion_seg * fps_efectivo))
    escritos = 0
    ultimo_reintento = 0.0
    nombre = camara.get("nombre", "CAM")
    try:
        for _ in range(total):
            if stop_event is not None and stop_event.is_set():
                break
            frame = None
            es_real = False
            if cap is not None:
                ok, frame = cap.read()
                if ok and frame is not None:
                    es_real = True
                else:
                    frame = None
            if frame is None:
                ahora = _dt.datetime.now().strftime("%H:%M:%S")
                if fuente_real:
                    # RECONEXIÓN de la fuente real caída; mientras tanto, fotograma "SIN SEÑAL".
                    if time.time() - ultimo_reintento > reintento_seg:
                        ultimo_reintento = time.time()
                        if cap is not None:
                            try:
                                cap.release()
                            except Exception:
                                pass
                        cap = _abrir_captura(fuente)
                        if cap is not None:
                            ok, frame = cap.read()
                            if ok and frame is not None:
                                es_real = True
                            else:
                                frame = None
                    if frame is None:
                        frame = _frame_sin_senal(w, h, f"{nombre}  {ahora}")
                else:
                    frame = _frame_simulado(f"{nombre}  {ahora}")
            if frame.shape[1] != w or frame.shape[0] != h:
                try:
                    frame = cv2.resize(frame, (w, h))
                except Exception:
                    continue
            writer.write(frame)
            escritos += 1
            # DETECCIÓN DE MOVIMIENTO: solo sobre imagen REAL de la cámara (nunca 'SIN SEÑAL'/simulada),
            # con antirrebote para no inundar de eventos.
            if detector is not None and es_real:
                score = detector.procesar(frame)
                if score >= detector.area_min_ratio and (time.time() - ultimo_evento) > cooldown_evt:
                    ultimo_evento = time.time()
                    try:
                        registrar_evento(camara, "movimiento", score=score)
                    except Exception:
                        pass
    finally:
        writer.release()
        if cap is not None:
            cap.release()
    _registrar_grabacion(camara, fecha, ruta, escritos / fps_efectivo, "cerrada")
    return ruta


# ── Retención / purga ─────────────────────────────────────────────────────────
def purgar_grabaciones_antiguas(dias=RETENCION_DIAS, id_empresa=None) -> int:
    """Elimina las grabaciones (fichero + registro en `camaras_grabaciones`) con fecha anterior a hoy-`dias`.
    Evita que el disco se llene. Aislado por empresa si se indica. Devuelve el nº de grabaciones borradas."""
    from src.db.conexion import obtener_conexion
    corte = (_dt.date.today() - _dt.timedelta(days=int(dias))).isoformat()
    borradas = 0
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            q = "SELECT id, ruta FROM camaras_grabaciones WHERE fecha < %s"
            p = [corte]
            if id_empresa:
                q += " AND id_empresa=%s"
                p.append(id_empresa)
            cur.execute(q, tuple(p))
            filas = cur.fetchall()
            for row in filas:
                gid = row[0] if not isinstance(row, dict) else row["id"]
                ruta = row[1] if not isinstance(row, dict) else row["ruta"]
                if ruta and os.path.exists(ruta):
                    try:
                        os.remove(ruta)
                    except Exception:
                        pass
                cur.execute("DELETE FROM camaras_grabaciones WHERE id=%s", (gid,))
                borradas += 1
            conn.commit()
    except Exception as e:
        logger.debug("purgar_grabaciones_antiguas: %s", e)
    return borradas


# ── Recorder continuo (24/7) ──────────────────────────────────────────────────
class RecorderService:
    """Graba en segundo plano todas las cámaras activas de un departamento, un fichero por día,
    rotando a medianoche. Degradable. La grabación no se detiene por reproducir."""

    def __init__(self, terminal=None):
        self._hilos = {}
        self._stops = {}
        self._ambito = []            # [(id_empresa, id_centro|None)] gestionados por esta terminal
        try:
            from src.services.camaras.orquestacion import terminal_id
            self._terminal = terminal or terminal_id()
        except Exception:
            self._terminal = terminal or "terminal"

    def iniciar_camara(self, camara):
        cid = camara.get("id")
        if cid in self._hilos and self._hilos[cid].is_alive():
            return
        stop = threading.Event()
        self._stops[cid] = stop
        t = threading.Thread(target=self._bucle, args=(camara, stop), daemon=True,
                             name=f"rec-cam-{cid}")
        self._hilos[cid] = t
        t.start()

    def _es_real(self, cam):
        f = (cam.get("fuente") or "").strip()
        return bool(f) and f != "simulado"

    def arrancar_departamento(self, id_empresa, id_centro) -> int:
        """Arranca el grabador de las cámaras REALES (no 'simulado') de un departamento que ESTA terminal
        logre RECLAMAR (una sola terminal graba cada cámara; failover si otra cae). Devuelve el nº arrancadas."""
        from src.services.camaras import orquestacion, registro
        if (id_empresa, id_centro) not in self._ambito:
            self._ambito.append((id_empresa, id_centro))
        n = 0
        for cam in registro.listar_camaras(id_empresa=id_empresa, id_centro=id_centro):
            if not self._es_real(cam):
                continue
            if orquestacion.reclamar(cam.get("id"), terminal=self._terminal, id_empresa=id_empresa):
                self.iniciar_camara(cam)
                n += 1
        return n

    def arrancar_empresa(self, id_empresa) -> int:
        from src.services.camaras import registro
        return sum(self.arrancar_departamento(id_empresa, dep["id_centro"])
                   for dep in registro.departamentos(id_empresa))

    def renovar(self) -> int:
        """Heartbeat multi-terminal: renueva las concesiones propias y reclama/arranca las cámaras libres o
        caducadas de su ámbito (FAILOVER de una terminal caída) o cuyo hilo haya muerto. Devuelve nº activas."""
        from src.services.camaras import orquestacion, registro
        empresas = {emp for emp, _ in self._ambito}
        for emp in empresas:
            orquestacion.renovar(terminal=self._terminal, id_empresa=emp)
        for emp, centro in list(self._ambito):
            deps = ([{"id_centro": centro}] if centro is not None
                    else registro.departamentos(emp))
            for dep in deps:
                for cam in registro.listar_camaras(id_empresa=emp, id_centro=dep["id_centro"]):
                    cid = cam.get("id")
                    if not self._es_real(cam):
                        continue
                    vivo = cid in self._hilos and self._hilos[cid].is_alive()
                    if vivo:
                        continue
                    if orquestacion.reclamar(cid, terminal=self._terminal, id_empresa=emp):
                        self.iniciar_camara(cam)
        return self.activas()

    def activas(self) -> int:
        return sum(1 for t in self._hilos.values() if t.is_alive())

    def _bucle(self, camara, stop):
        while not stop.is_set():
            hoy = _dt.date.today().isoformat()
            # Segundos hasta medianoche (rotación diaria).
            ahora = _dt.datetime.now()
            fin_dia = _dt.datetime.combine(ahora.date() + _dt.timedelta(days=1), _dt.time.min)
            dur = max(1, int((fin_dia - ahora).total_seconds()))
            try:
                grabar_dia(camara, fecha=hoy, duracion_seg=dur, stop_event=stop)
            except Exception as e:
                logger.debug("recorder cam %s: %s", camara.get("id"), e)
                stop.wait(5)

    def detener(self):
        for stop in self._stops.values():
            stop.set()
        self._hilos.clear()
        self._stops.clear()
        try:                                   # cede las concesiones para que otra terminal pueda tomarlas
            from src.services.camaras import orquestacion
            for emp in {e for e, _ in self._ambito}:
                orquestacion.liberar(terminal=self._terminal, id_empresa=emp)
        except Exception:
            pass
        self._ambito.clear()


_servicio = RecorderService()
_hb_stop = None


def servicio() -> RecorderService:
    return _servicio


def arrancar_automatico() -> int:
    """Arranca el grabador continuo de las cámaras REALES de ESTA terminal: las de su tienda/departamento
    activo si está fijado (evita que varias terminales graben lo mismo), o las de toda la empresa si no.
    Best-effort: nunca lanza. Devuelve el nº de cámaras arrancadas."""
    try:
        from src.db.empresa import empresa_actual_id
        emp = empresa_actual_id()
        if not emp:
            return 0
        try:
            from src.db.empresa import tienda_actual_id
            tid = tienda_actual_id()
        except Exception:
            tid = None
        n = (_servicio.arrancar_departamento(emp, str(tid)) if tid is not None
             else _servicio.arrancar_empresa(emp))
        _arrancar_heartbeat()
        if n:
            logger.info("Videovigilancia: %s cámara(s) real(es) grabando.", n)
        return n
    except Exception as e:
        logger.debug("arrancar_automatico: %s", e)
        return 0


def _arrancar_heartbeat() -> None:
    """Hilo de latido: renueva las concesiones y reclama cámaras libres/caducadas (failover multi-terminal)."""
    global _hb_stop
    if _hb_stop is not None:
        return
    from src.services.camaras.orquestacion import TTL_SEG
    _hb_stop = threading.Event()

    def _loop(stop):
        while not stop.wait(max(15, TTL_SEG // 2)):
            try:
                _servicio.renovar()
            except Exception as e:
                logger.debug("heartbeat: %s", e)

    threading.Thread(target=_loop, args=(_hb_stop,), daemon=True, name="rec-heartbeat").start()


def detener_automatico() -> None:
    """Detiene todos los grabadores y cede las concesiones (cierre ordenado de la terminal)."""
    global _hb_stop
    try:
        if _hb_stop is not None:
            _hb_stop.set()
            _hb_stop = None
    except Exception:
        pass
    try:
        _servicio.detener()
    except Exception:
        pass


def job_retencion(id_empresa=None) -> str:
    """Callable para el Scheduler: purga las grabaciones anteriores a `RETENCION_DIAS`."""
    n = purgar_grabaciones_antiguas(RETENCION_DIAS, id_empresa)
    return f"grabaciones purgadas={n} (retención {RETENCION_DIAS} días)"
