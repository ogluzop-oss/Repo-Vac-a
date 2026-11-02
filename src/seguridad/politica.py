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


def validar(password: str, *, longitud_minima: int = LONGITUD_MINIMA) -> tuple[bool, str]:
    """Valida una contraseña según la política. Devuelve (ok, motivo).

    `longitud_minima`: por defecto la política estándar (`LONGITUD_MINIMA`, usuarios de escritorio y
    panel fundador) — un llamador puede pasar un mínimo distinto para un contexto con requisitos
    propios (p.ej. el alta de proveedores externos, `suministradores.completar_onboarding`, usa 8) sin
    afectar al resto de usos de esta política compartida."""
    if password is None:
        return (False, "La contraseña es obligatoria.")
    pw = str(password)
    if len(pw) < longitud_minima:
        return (False, f"Debe tener al menos {longitud_minima} caracteres.")
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


# PINes de 4 dígitos triviales/predecibles (secuencias y repeticiones obvias).
_PINES_COMUNES = {
    "0000", "1111", "2222", "3333", "4444", "5555", "6666", "7777", "8888", "9999",
    "1234", "4321", "0123", "1212", "2580", "0852",
}


def validar_pin(pin: str) -> tuple[bool, str]:
    """Valida el PIN de acceso de un perfil de EMPLEADO — formato oficial de la app para el
    login nominal (escritorio, identificación TPV): EXACTAMENTE 4 dígitos numéricos, sin
    ser una secuencia/repetición trivial. La brevedad (elegida a propósito para que el
    personal no tenga que memorizar contraseñas largas en el día a día) se compensa con dos
    controles que NO dependen de la longitud del PIN: el bloqueo por intentos fallidos
    (`db.usuario._registrar_fallo`, escalado 1/5/15 min tras 5 fallos — hace inviable probar
    las 10 000 combinaciones) y, para SUPERADMIN/ADMINISTRADOR, el segundo factor (MFA) que
    la política de la empresa puede exigir. Devuelve (ok, motivo)."""
    if pin is None:
        return (False, "El PIN es obligatorio.")
    p = str(pin)
    if len(p) != 4 or not p.isdigit():
        return (False, "El PIN debe ser exactamente 4 dígitos numéricos.")
    if p in _PINES_COMUNES:
        return (False, "Ese PIN es demasiado predecible (secuencia o repetición); elige otro.")
    return (True, "")
