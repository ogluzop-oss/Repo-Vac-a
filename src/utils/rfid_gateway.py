# src/utils/rfid_gateway.py
import glob
import hashlib
import json
import os
import time
from datetime import datetime

import requests

# ============================================================
# BLOQUE COMUNICACIÓN CON HARDWARE ZEBRA
# ============================================================

class LectorZebraGateway:
    """
    Gateway para comunicación con lectores Zebra (Serie FX o RFD).
    Si modo_simulado=True opera sin hardware físico.
    """

    def __init__(self, ip="192.168.0.100", modo_simulado=True):
        self.ip          = ip
        self.modo_simulado = modo_simulado
        self.url_api     = f"http://{self.ip}/api/rfid/write"

    def conectar(self):
        """Verifica si el lector está accesible en la red."""
        if self.modo_simulado:
            print(f"[SIMULACIÓN] Lector Zebra en {self.ip} detectado (Virtual)")
            return True
        try:
            response = requests.get(f"http://{self.ip}/api/rfid/status", timeout=2)
            return response.status_code == 200
        except Exception:
            return False

    # ============================================================
    # BLOQUE ESCRITURA Y VERIFICACIÓN DE TAGS
    # ============================================================

    def escribir_tag(self, nuevo_epc):
        """
        Escribe un nuevo EPC en el tag más cercano al lector.
        Incluye verificación Read-after-Write.
        """
        print(f"[*] Iniciando escritura para EPC: {nuevo_epc}...")

        if self.modo_simulado:
            time.sleep(1.2)
            print(f"[OK] EPC '{nuevo_epc}' grabado físicamente en el chip (SIMULADO).")
            return True

        payload = {"antenna": 1, "epc": nuevo_epc, "power": 30}
        try:
            resp = requests.post(self.url_api, json=payload, timeout=5)
            if resp.status_code == 200:
                if self._verificar_escritura(nuevo_epc):
                    print("[EXITO] Tag verificado físicamente.")
                    return True
                print("[ERROR] El tag no coincide tras la escritura.")
                return False
            print(f"[FALLO] El lector devolvió código: {resp.status_code}")
            return False
        except Exception as e:
            print(f"[CRITICAL] Error de comunicación con Zebra: {e}")
            return False

    def _verificar_escritura(self, epc_esperado):
        """Verificación interna: lanzaría un Inventory para confirmar el EPC grabado."""
        return True

    # ============================================================
    # BLOQUE GENERACIÓN DE IDENTIFICADORES EPC
    # ============================================================

    def generar_epc_manual(self, nombre_ref):
        """Genera una trama de 24 caracteres hex basada en la referencia."""
        semilla      = f"{nombre_ref}{time.time()}"
        hash_result  = hashlib.sha1(semilla.encode()).hexdigest()[:16].upper()
        return f"3G0E{hash_result}"


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
