# Arquitectura de seguridad — Smart Manager AI (C1)

Módulo central `src/seguridad/` reutilizable por escritorio y futura API/SaaS/móvil.
Respeta la arquitectura multiempresa/multitienda y **no rompe usuarios existentes**.

## Hashing de contraseñas (Argon2id + migración)

- `src/seguridad/passwords.py`: las contraseñas nuevas se guardan con **Argon2id**
  (`$argon2id$…`, sal embebida; OWASP `time_cost=3`, `memory_cost=64MB`, `parallelism=2`).
- **Migración transparente desde SHA-256:** los hashes antiguos (64 hex) se siguen
  validando; en el **primer login correcto** se **rehashean** a Argon2id
  (`verificar()` devuelve el nuevo hash y la capa de usuario lo persiste).
- Soporte dual aplicado en las tres vías de verificación:
  - `validar_login(perfil, password)` — login por perfil (escritorio).
  - `validar_login_empleado(nombre, password)` — login individual (TPV).
  - `validar_pin_fichaje(pin)` — antes comparaba por igualdad SQL (incompatible con
    Argon2id); ahora verifica fila a fila con soporte dual y rehash.
- Altas y cambios de contraseña (`crear_perfil`, `cambiar_password_usuario`) usan ya
  Argon2id (`encriptar_password` redirige a `hash_password`).

### Compatibilidad / riesgos cubiertos
- Ningún usuario se bloquea: verificación dual + rehash en caliente.
- `password VARCHAR(255)` admite tanto los 64 hex antiguos como los `$argon2id$`.
- Producción intacta: solo cambia *cómo* se verifica/almacena el hash.
- Cubierto por tests: `tests/unit/test_passwords.py` y `tests/integration/test_auth_login.py`
  (login Argon2, migración legado→Argon2, login por nombre, PIN dual).

## Build
`argon2-cffi` añadido a `requirements.txt` y al `collect_all` de `SmartManagerAI.spec`
para empaquetar su binario en el `.exe`.

## Pendiente de C1 (siguientes sub-bloques)
- Cifrado en reposo de secretos (pasarelas/ecommerce/correo/integraciones).
- Bloqueo por intentos fallidos + política de contraseñas.
- Identidad por usuario único por empresa (login individual) + diseño JWT/refresh
  y rotación de clave maestra (MultiFernet) para la futura API/SaaS.
