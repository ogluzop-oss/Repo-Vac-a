# src/utils/rfid_gateway.py
import glob
import hashlib
import json
import logging
import os
import threading
import time
from datetime import datetime

logger = logging.getLogger("rfid_gateway")

PUERTO_LLRP_DEFECTO = 5084  # puerto estándar LLRP (sllurp.llrp.LLRP_DEFAULT_PORT)

# ============================================================
# BLOQUE COMUNICACIÓN CON HARDWARE ZEBRA
# ============================================================


def _sllurp_disponible() -> bool:
    """True si la librería `sllurp` (cliente LLRP real) está instalada. Degradable: sin ella, el
    modo 'fisico' simplemente no puede conectar y lo informa con un mensaje claro — nunca lanza
    `ImportError` hacia el llamador (mismo patrón que `services.camaras.ptz._onvif_disponible`)."""
    try:
        import sllurp.llrp  # noqa: F401
        return True
    except Exception:
        return False


class LectorZebraGateway:
    """
    Gateway para comunicación con lectores Zebra (Serie FX o RFD).

    Dos modos:
      - `modo_simulado=True` (por defecto): opera sin hardware físico, para demos/desarrollo.
      - `modo_simulado=False`: habla LLRP (Low-Level Reader Protocol, estándar EPCglobal/GS1) REAL
        contra `ip:puerto` (puerto 5084 por defecto) vía `sllurp`. Degrada honesto en cualquier
        fallo (sllurp no instalado, IP inalcanzable, timeout, tag ausente) — nunca lanza, nunca
        finge un resultado: cada método real devuelve `False`/`None` con un mensaje de log claro.
    """

    def __init__(self, ip="192.168.0.100", modo_simulado=True, puerto=None):
        self.ip             = ip
        self.puerto         = int(puerto) if puerto else PUERTO_LLRP_DEFECTO
        self.modo_simulado  = modo_simulado
        # Último EPC escrito con éxito: en modo simulado representa "el tag que hay ahora mismo
        # en el campo del codificador" — permite que `leer_tag`/`_verificar_escritura` simulen una
        # lectura cruzada REAL (coincide con lo escrito) en vez de devolver True sin comprobar nada.
        self._ultimo_epc_escrito = None

    def conectar(self):
        """Verifica si el lector está accesible en la red."""
        if self.modo_simulado:
            print(f"[SIMULACIÓN] Lector Zebra en {self.ip} detectado (Virtual)")
            return True
        cliente = self._conectar_llrp(timeout=3.0)
        if cliente is None:
            return False
        self._desconectar_llrp(cliente)
        return True

    # ============================================================
    # BLOQUE CONEXIÓN LLRP REAL (sllurp)
    # ============================================================

    def _conectar_llrp(self, timeout=5.0):
        """Abre una conexión LLRP real al lector (ROSpec de inventario continuo arrancado por
        defecto, igual que hace `sllurp` al conectar con `start_inventory=True`). Devuelve el
        cliente conectado, o `None` si `sllurp` no está instalado o la conexión falla — nunca
        lanza; siempre deja en el log el motivo honesto (IP/puerto + la excepción real)."""
        if not _sllurp_disponible():
            logger.error("[RFID] sllurp no está instalado — ejecute 'pip install sllurp' para "
                         "comunicación real con el lector Zebra (modo físico).")
            return None
        from sllurp.llrp import LLRPReaderClient, LLRPReaderConfig

        config = LLRPReaderConfig({
            "antennas": [1],
            "tag_content_selector": {
                "EnableROSpecID": False, "EnableSpecIndex": False,
                "EnableInventoryParameterSpecID": False, "EnableAntennaID": True,
                "EnableChannelIndex": False, "EnablePeakRSSI": True,
                "EnableFirstSeenTimestamp": False, "EnableLastSeenTimestamp": True,
                "EnableTagSeenCount": True, "EnableAccessSpecID": True,
            },
            "report_every_n_tags": 1,
            "reset_on_connect": True,
            "start_inventory": True,
        })
        try:
            cliente = LLRPReaderClient(self.ip, self.puerto, config, timeout=timeout)
            cliente.connect()
        except Exception as e:
            logger.error("[RFID] Error de conexión con el lector Zebra en %s:%s: %s — compruebe "
                         "el cableado o la red.", self.ip, self.puerto, e)
            return None
        # Breve asentamiento: el handshake LLRP (capacidades, ROSpec add/enable/start) corre en el
        # hilo de fondo que `connect()` acaba de arrancar; sin esto, un `start_access_spec`
        # inmediato podría llegar antes de que el ROSpec esté activo.
        time.sleep(0.3)
        return cliente

    def _desconectar_llrp(self, cliente):
        try:
            cliente.disconnect()
        except Exception as e:
            logger.debug("[RFID] disconnect(): %s", e)
        try:
            cliente.join(1.5)
        except Exception as e:
            logger.debug("[RFID] join(): %s", e)

    # ============================================================
    # BLOQUE ESCRITURA Y VERIFICACIÓN DE TAGS
    # ============================================================

    def escribir_tag(self, nuevo_epc):
        """
        Escribe un nuevo EPC (hex, 24 caracteres / 96 bits) en el tag más cercano al lector.
        Incluye verificación Read-after-Write.
        """
        print(f"[*] Iniciando escritura para EPC: {nuevo_epc}...")

        if self.modo_simulado:
            time.sleep(1.2)
            self._ultimo_epc_escrito = nuevo_epc
            print(f"[OK] EPC '{nuevo_epc}' grabado físicamente en el chip (SIMULADO).")
            return True

        try:
            epc_bytes = bytes.fromhex((nuevo_epc or "").strip())
        except ValueError:
            logger.error("[RFID] EPC inválido (no es hexadecimal): %r", nuevo_epc)
            return False
        if len(epc_bytes) != 12:
            logger.error("[RFID] Solo se admite grabar un EPC de 96 bits (12 bytes); recibidos "
                         "%d.", len(epc_bytes))
            return False

        cliente = self._conectar_llrp(timeout=5.0)
        if cliente is None:
            return False

        resultado = {"ok": None}
        evento = threading.Event()
        try:
            from sllurp.llrp import C1G2Write

            def _en_reporte(reader, tags):
                for tag in tags:
                    op = tag.get("C1G2WriteOpSpecResult")
                    if op is not None:
                        resultado["ok"] = (op.get("Result") == 0)
                        evento.set()
                        break

            cliente.add_tag_report_callback(_en_reporte)
            # Banco EPC (MB=1): word0=CRC-16 (lo recalcula el propio tag), word1=PC (Protocol-
            # Control) — 0x3000 fija "EPC de 6 words = 96 bits", el valor estándar de la industria
            # para SGTIN-96. Se escribe JUNTO con el EPC (WordPtr=1, un único OpSpec) para que el
            # tag quede consistente en un solo ciclo, nunca a medias entre dos escrituras.
            pc = (6 << 11).to_bytes(2, "big")
            datos = pc + epc_bytes
            op_spec = C1G2Write(OpSpecID=1, AccessPassword=0, MB=1, WordPtr=1,
                                WriteDataWordCount=len(datos) // 2, WriteData=datos)
            cliente.start_access_spec(op_spec)
            evento.wait(5.0)
        except Exception as e:
            logger.error("[RFID] Error de comunicación con el lector Zebra en %s:%s durante la "
                         "grabación: %s", self.ip, self.puerto, e)
            return False
        finally:
            self._desconectar_llrp(cliente)

        if not resultado["ok"]:
            print("[FALLO] El lector no confirmó la escritura (sin tag en el campo, o rechazada "
                  "por el chip).")
            return False

        self._ultimo_epc_escrito = nuevo_epc.strip().upper()
        if self._verificar_escritura(nuevo_epc):
            print("[EXITO] Tag verificado físicamente.")
            return True
        print("[ERROR] El tag no coincide tras la escritura.")
        return False

    def leer_tag(self):
        """Lee el EPC del tag presente ahora mismo en el campo del lector/codificador (lectura
        cruzada de verificación, e inventario de un único tag). `None` si no hay tag en el campo o
        no hay hardware accesible — degradación honesta, nunca inventa un EPC."""
        if self.modo_simulado:
            time.sleep(0.4)
            return self._ultimo_epc_escrito

        cliente = self._conectar_llrp(timeout=3.0)
        if cliente is None:
            return None
        resultado = {"epc": None}
        evento = threading.Event()
        try:
            def _en_reporte(reader, tags):
                for tag in tags:
                    epc = tag.get("EPC")
                    if epc:
                        resultado["epc"] = _epc_a_texto(epc)
                        evento.set()
                        break

            cliente.add_tag_report_callback(_en_reporte)
            evento.wait(3.0)
            return resultado["epc"]
        except Exception as e:
            logger.error("[RFID] Error leyendo el tag desde %s:%s: %s", self.ip, self.puerto, e)
            return None
        finally:
            self._desconectar_llrp(cliente)

    def _verificar_escritura(self, epc_esperado):
        """Verificación READ-AFTER-WRITE real: relee el tag y confirma que el EPC coincide con el
        recién grabado — ya no es un stub que siempre da por buena la escritura."""
        leido = self.leer_tag()
        return bool(leido) and leido.strip().upper() == (epc_esperado or "").strip().upper()

    # ============================================================
    # BLOQUE INVENTARIO / LOCALIZACIÓN (barrido y proximidad)
    # ============================================================

    def inventario_conteo(self, duracion_seg=2.5):
        """Barrido RFID: devuelve {codigo_articulo: unidades_detectadas} agregando todos los
        EPC distintos vistos durante `duracion_seg`, resueltos a artículo vía `db.ubicaciones.
        obtener_por_epc` (la misma tabla que ya resuelve EPC↔artículo en todo el ERP). En modo
        simulado devuelve `None` (el servicio simula el barrido, `services.rfid.inventario`)."""
        if self.modo_simulado:
            return None
        cliente = self._conectar_llrp(timeout=3.0)
        if cliente is None:
            return None
        vistos = set()

        def _en_reporte(reader, tags):
            for tag in tags:
                epc = tag.get("EPC")
                if epc:
                    vistos.add(_epc_a_texto(epc))

        try:
            cliente.add_tag_report_callback(_en_reporte)
            time.sleep(max(0.5, duracion_seg))
        except Exception as e:
            logger.error("[RFID] Error en el barrido de inventario (%s:%s): %s",
                         self.ip, self.puerto, e)
            return None
        finally:
            self._desconectar_llrp(cliente)

        if not vistos:
            return {}
        from src.db import ubicaciones as ubi_db
        conteo = {}
        for epc in vistos:
            fila = ubi_db.obtener_por_epc(epc)
            codigo = (fila or {}).get("codigo_articulo")
            if codigo:
                conteo[codigo] = conteo.get(codigo, 0) + 1
        return conteo

    def leer_rssi(self, epc):
        """Intensidad de señal (dBm) del tag `epc` para el rastreo por proximidad. None si no
        hay hardware/lectura (el servicio simula la aproximación)."""
        if self.modo_simulado:
            return None
        cliente = self._conectar_llrp(timeout=2.5)
        if cliente is None:
            return None
        objetivo = (epc or "").strip().upper()
        resultado = {"rssi": None}

        def _en_reporte(reader, tags):
            for tag in tags:
                epc_tag = tag.get("EPC")
                if epc_tag and (not objetivo or _epc_a_texto(epc_tag) == objetivo):
                    rssi = tag.get("PeakRSSI")
                    if rssi is not None:
                        resultado["rssi"] = float(rssi)

        try:
            cliente.add_tag_report_callback(_en_reporte)
            time.sleep(1.0)
        except Exception as e:
            logger.error("[RFID] Error leyendo RSSI (%s:%s): %s", self.ip, self.puerto, e)
            return None
        finally:
            self._desconectar_llrp(cliente)
        return resultado["rssi"]

    # ============================================================
    # BLOQUE GENERACIÓN DE IDENTIFICADORES EPC
    # ============================================================

    def generar_epc_manual(self, nombre_ref):
        """Genera una trama de 24 caracteres hex basada en la referencia."""
        semilla      = f"{nombre_ref}{time.time()}"
        hash_result  = hashlib.sha1(semilla.encode()).hexdigest()[:16].upper()
        return f"3G0E{hash_result}"


def _epc_a_texto(epc_crudo) -> str:
    """Normaliza el campo `EPC` que `sllurp` entrega en cada TagReportData (bytes de hexlify, o ya
    str según la ruta de decodificación) a un string hex en MAYÚSCULAS — mismo formato que produce
    `services.rfid.sgtin.codificar_sgtin96`, para que las comparaciones de verificación funcionen."""
    if isinstance(epc_crudo, (bytes, bytearray)):
        return epc_crudo.decode("ascii").upper()
    return str(epc_crudo).upper()


# ============================================================
# BLOQUE GESTIÓN DE BACKUPS DE ACTIVOS RFID
# ============================================================

def volcar_gestion_activos(data_activos=None, prefijo="backup"):
    """
    Gestión bidireccional de activos en JSON.
    - Si data_activos no es None: guarda el volcado (GUARDAR).
    - Si data_activos es None: recupera el backup más reciente (RECUPERAR).
    """
    logs_dir = "logs/rfid_backups"

    try:
        os.makedirs(logs_dir, exist_ok=True)

        if data_activos is not None:
            timestamp      = datetime.now().strftime("%Y%m%d_%H%M")
            nombre_archivo = f"{prefijo}_estanterias_{timestamp}.json"
            ruta_completa  = os.path.join(logs_dir, nombre_archivo)
            with open(ruta_completa, "w", encoding="utf-8") as f:
                json.dump(data_activos, f, ensure_ascii=False, indent=4)
            print(f"[OK] Backup creado en: {ruta_completa}")
            return ruta_completa

        archivos = glob.glob(os.path.join(logs_dir, f"{prefijo}_estanterias_*.json"))
        if not archivos:
            print("[!] No se encontraron archivos de backup.")
            return None

        ultimo_archivo   = max(archivos, key=os.path.getmtime)
        with open(ultimo_archivo, encoding="utf-8") as f:
            datos_recuperados = json.load(f)
        print(f"[OK] Datos recuperados desde: {ultimo_archivo}")
        return datos_recuperados

    except Exception as e:
        print(f"[!] Error en volcar_gestion_activos: {e}")
        return None
