# src/utils/api_client.py
"""
Cliente para comunicarse con el backend API.
Proporciona métodos para login, obtener datos, etc.
"""
import requests
import logging

logger = logging.getLogger(__name__)


class APIClient:
    def __init__(self, base_url="http://127.0.0.1:5000"):
        self.base_url = base_url
        self.session = requests.Session()

    def login(self, usuario, password):
        """Realiza login y retorna perfil si exitoso."""
        try:
            response = self.session.post(
                f"{self.base_url}/api/login",
                json={"usuario": usuario, "password": password},
                timeout=5,
            )
            response.raise_for_status()
            data = response.json()
            return data if data.get("success") else None
        except requests.exceptions.RequestException as e:
            logger.error(f"Error en login API: {e}")
            return None

    def get_articulos(self):
        """Obtiene lista de artículos."""
        try:
            response = self.session.get(f"{self.base_url}/api/articulos", timeout=5)
            response.raise_for_status()
            return response.json().get("articulos", [])
        except requests.exceptions.RequestException as e:
            logger.error(f"Error obteniendo artículos: {e}")
            return []


# Instancia global
api_client = APIClient()
