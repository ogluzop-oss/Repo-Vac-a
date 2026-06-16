"""
Núcleo de SEGURIDAD de Smart Manager AI (C1).

Reúne hashing de contraseñas (Argon2id con migración desde SHA-256), política de
contraseñas, cifrado de secretos en reposo y (diseño) de tokens JWT/refresh. Es
reutilizable por el escritorio y por la futura API/SaaS/móvil.
"""

from src.seguridad.passwords import (es_hash_legado, hash_password,
                                     necesita_actualizar, verificar)

__all__ = ["hash_password", "verificar", "es_hash_legado", "necesita_actualizar"]
