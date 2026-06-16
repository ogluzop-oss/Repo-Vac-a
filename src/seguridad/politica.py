"""
Política de contraseñas (C1) — estilo NIST 800-63B: la longitud manda, sin
rotación forzada, bloqueo de contraseñas comunes. Pensada para evolucionar
(añadir comprobación HIBP en fase posterior).
"""

LONGITUD_MINIMA = 12

# Lista mínima de contraseñas/patrones triviales (ampliable / sustituible por HIBP).
_COMUNES = {
    "password", "contrasena", "contraseña", "123456", "12345678", "123456789",
    "1234567890", "qwerty", "111111", "000000", "admin", "administrador",
    "smartmanager", "smart manager", "iloveyou", "abc123", "password1",
}


def validar(password: str) -> tuple[bool, str]:
    """Valida una contraseña según la política. Devuelve (ok, motivo)."""
    if password is None:
        return (False, "La contraseña es obligatoria.")
    pw = str(password)
    if len(pw) < LONGITUD_MINIMA:
        return (False, f"Debe tener al menos {LONGITUD_MINIMA} caracteres.")
    if pw.strip() != pw:
        return (False, "No debe empezar ni terminar con espacios.")
    bajo = pw.lower()
    if bajo in _COMUNES:
        return (False, "Es una contraseña demasiado común.")
    # Variedad mínima: al menos dos tipos de carácter (frases largas válidas).
    tipos = sum([any(c.islower() for c in pw), any(c.isupper() for c in pw),
                 any(c.isdigit() for c in pw), any(not c.isalnum() for c in pw)])
    if tipos < 2:
        return (False, "Combina mayúsculas, minúsculas, números o símbolos.")
    return (True, "")


def es_valida(password: str) -> bool:
    return validar(password)[0]
