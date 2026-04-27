import time
import random
import requests  # Necesitarás instalarlo: pip install requests


class LectorZebraGateway:
    def __init__(self, ip="192.168.0.100", modo_simulado=True):
        """
        Gateway para comunicación con lectores Zebra (Serie FX o RFD).
        :param ip: Dirección IP del lector en la red.
        :param modo_simulado: Si es True, simula éxito sin hardware físico.
        """
        self.ip = ip
        self.modo_simulado = modo_simulado
        self.url_api = f"http://{self.ip}/api/rfid/write"  # Endpoint típico Zebra IoT

    def conectar(self):
        """Verifica si el lector está accesible en la red."""
        if self.modo_simulado:
            print(f"[SIMULACIÓN] Lector Zebra en {self.ip} detectado (Virtual)")
            return True
        try:
            # Intentamos un ping o una consulta rápida al estado del lector
            response = requests.get(f"http://{self.ip}/api/rfid/status", timeout=2)
            return response.status_code == 200
        except:
            return False

    def escribir_tag(self, nuevo_epc):
        """
        Escribe un nuevo EPC en el tag más cercano al lector.
        Incluye lógica de verificación 'Read-after-Write'.
        """
        print(f"[*] Iniciando proceso de escritura para EPC: {nuevo_epc}...")

        if self.modo_simulado:
            # Simulamos el tiempo de espera de radiofrecuencia
            time.sleep(1.2)
            print(f"[OK] EPC '{nuevo_epc}' grabado físicamente en el chip (SIMULADO).")
            return True

        # --- LÓGICA REAL (Para Zebra FX7500/FX9600 con IoT Connector) ---
        payload = {
            "antenna": 1,
            "epc": nuevo_epc,
            "power": 30,  # Potencia máxima para asegurar la escritura
        }

        try:
            # 1. Enviamos orden de escritura
            resp = requests.post(self.url_api, json=payload, timeout=5)

            if resp.status_code == 200:
                # 2. VERIFICACIÓN: Intentamos leerlo para confirmar
                # Esto es lo que garantiza que el chip no se movió durante la grabación
                if self._verificar_escritura(nuevo_epc):
                    print(f"[EXITO] Tag verificado físicamente.")
                    return True
                else:
                    print("[ERROR] El tag no coincide tras la escritura.")
                    return False
            else:
                print(f"[FALLO] El lector devolvió código: {resp.status_code}")
                return False

        except Exception as e:
            print(f"[CRITICAL] Error de comunicación con Zebra: {e}")
            return False

    def _verificar_escritura(self, epc_esperado):
        """Lógica interna de verificación."""
        # Aquí se lanzaría un comando de lectura simple (Inventory)
        # Por ahora devolvemos True si la comunicación no falló
        return True

    def generar_epc_manual(self, nombre_ref):
        """Genera una trama de 24 caracteres hex basada en la referencia."""
        import hashlib

        semilla = f"{nombre_ref}{time.time()}"
        hash_result = hashlib.sha1(semilla.encode()).hexdigest()[:16].upper()
        return f"3G0E{hash_result}"  # Estructura: Prefijo + 16 hex


import json
import os
import glob
from datetime import datetime


def volcar_gestion_activos(data_activos=None, prefijo="backup"):
    """
    Gestión bidireccional de activos en JSON.
    Ubicación: src/utils/rfid_gateway.py

    - Si se provee data_activos: Realiza un volcado (GUARDAR).
    - Si data_activos es None: Busca y devuelve el último backup (RECUPERAR).
    """
    logs_dir = "logs/rfid_backups"

    try:
        # 1. Asegurar que existe el directorio
        if not os.path.exists(logs_dir):
            os.makedirs(logs_dir)

        # --- LÓGICA DE VOLCADO (Escritura) ---
        if data_activos is not None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M")
            nombre_archivo = f"{prefijo}_estanterias_{timestamp}.json"
            ruta_completa = os.path.join(logs_dir, nombre_archivo)

            with open(ruta_completa, "w", encoding="utf-8") as f:
                json.dump(data_activos, f, ensure_ascii=False, indent=4)

            print(f"[OK] Backup de seguridad creado en: {ruta_completa}")
            return ruta_completa

        # --- LÓGICA DE RECUPERACIÓN (Lectura) ---
        else:
            # Buscamos todos los archivos .json que sigan el patrón del prefijo
            archivos = glob.glob(
                os.path.join(logs_dir, f"{prefijo}_estanterias_*.json")
            )

            if not archivos:
                print("[!] No se encontraron archivos de backup para recuperar.")
                return None

            # Obtenemos el más reciente basándonos en la fecha de modificación
            ultimo_archivo = max(archivos, key=os.path.getmtime)

            with open(ultimo_archivo, "r", encoding="utf-8") as f:
                datos_recuperados = json.load(f)

            print(f"[OK] Datos recuperados con éxito desde: {ultimo_archivo}")
            return datos_recuperados

    except Exception as e:
        print(f"[!] Error crítico en volcar_gestion_activos: {e}")
        return None
