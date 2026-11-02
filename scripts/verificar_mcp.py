"""
Script de verificación manual del servidor MCP de Smart Manager (SOMA).

Ejecuta el baile OAuth 2.1 + PKCE completo contra un backend REAL en marcha
(`python -m src.backend.app`) y llama a un par de herramientas MCP reales,
para comprobar de un vistazo que todo responde correctamente.

USO:
    python -m src.backend.app                     # en una terminal (deja corriendo)
    python scripts/verificar_mcp.py USUARIO PASS   # en otra terminal

No requiere nada más que `requests` (ya en requirements.txt). No crea datos
permanentes: el cliente MCP que registra (DCR) queda vinculado a tu usuario
real y puedes revocarlo después desde Configuración → Asistente SOMA →
"SOMA Conectores Externos (MCP)" → Revocar.
"""
import base64
import hashlib
import secrets
import sys
from urllib.parse import parse_qs, urlparse

import requests

BASE = "http://localhost:8090"
REDIRECT_URI = "http://localhost:9999/callback"  # no necesita estar escuchando


def _pkce():
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(40)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def main():
    if len(sys.argv) < 3:
        print("Uso: python scripts/verificar_mcp.py USUARIO PASSWORD [ID_EMPRESA]")
        sys.exit(1)
    usuario, password = sys.argv[1], sys.argv[2]
    id_empresa = sys.argv[3] if len(sys.argv) > 3 else ""

    print("1) Descubrimiento OAuth...")
    meta = requests.get(f"{BASE}/.well-known/oauth-authorization-server").json()
    print("   authorization_endpoint:", meta.get("authorization_endpoint"))

    print("2) Registro dinámico de cliente (DCR)...")
    reg = requests.post(f"{BASE}/mcp/oauth/register", json={
        "client_name": "Script de verificación", "redirect_uris": [REDIRECT_URI],
    }).json()
    client_id = reg["client_id"]
    print("   client_id:", client_id)

    print("3) Autorización (login real)...")
    verifier, challenge = _pkce()
    s = requests.Session()
    r = s.post(f"{BASE}/mcp/oauth/authorize", data={
        "response_type": "code", "client_id": client_id, "redirect_uri": REDIRECT_URI,
        "state": "xyz", "code_challenge": challenge, "code_challenge_method": "S256",
        "scope": "mcp", "usuario": usuario, "password": password, "id_empresa": id_empresa,
    }, allow_redirects=False)
    if r.status_code != 302:
        print("   ERROR: login rechazado (revisa usuario/contraseña, o si pide MFA no soportado por este script).")
        print("   Respuesta:", r.status_code, r.text[:300])
        sys.exit(1)
    code = parse_qs(urlparse(r.headers["Location"]).query)["code"][0]
    print("   código de autorización obtenido.")

    print("4) Canje del código por token (PKCE)...")
    tok = requests.post(f"{BASE}/mcp/oauth/token", data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI,
        "client_id": client_id, "code_verifier": verifier,
    }).json()
    access = tok["access_token"]
    print("   access_token obtenido (expira en", tok.get("expires_in"), "s).")

    headers = {"Authorization": f"Bearer {access}", "Content-Type": "application/json"}

    print("5) initialize...")
    r = requests.post(f"{BASE}/mcp", headers=headers, json={
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                   "clientInfo": {"name": "verificar_mcp.py", "version": "1.0"}},
    }).json()
    print("   servidor:", r["result"]["serverInfo"])

    print("6) tools/list...")
    r = requests.post(f"{BASE}/mcp", headers=headers, json={
        "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {},
    }).json()
    nombres = [t["name"] for t in r["result"]["tools"]]
    print("   herramientas disponibles:", nombres)

    print("7) tools/call -> whoami...")
    r = requests.post(f"{BASE}/mcp", headers=headers, json={
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "whoami", "arguments": {}},
    }).json()
    print("   resultado:", r["result"]["content"])

    print("\nTODO CORRECTO. El cliente MCP quedó registrado con client_id:", client_id)
    print("Puedes revocarlo desde Configuración → Asistente SOMA → Conectores Externos (MCP).")


if __name__ == "__main__":
    main()
