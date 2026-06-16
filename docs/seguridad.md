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

## Cifrado de secretos en reposo (C1.2)

- Reutiliza **Fernet** (`src/utils/cripto.py`). Nuevo `descifrar_seguro()` lee de
  forma **retrocompatible**: si el valor no parece cifrado, se asume legado en claro
  y se devuelve tal cual (permite migrar sin romper lecturas).
- **Cifrado transparente en la capa DB** (los servicios no cambian):
  - `pasarela_config`: `api_key`, `api_secret`, `webhook_secret`.
  - `ecommerce_config`: `api_key`, `api_secret`.
  - (`oauth_tokens` del correo ya estaba cifrado.)
- **Migración idempotente** `migrar_cifrado()` en cada módulo, invocada por
  `ensure_schema()` (best-effort): cifra los valores en claro existentes; detecta los
  ya cifrados por su prefijo. Si no hay backend de cifrado, no hace nada.
- Cubierto por `tests/integration/test_secretos_cifrado.py` (cifrado en reposo,
  lectura de legado en claro, migración) sin romper los webhooks (que leen el secreto
  descifrado para validar firma).

## Bloqueo por intentos + política de contraseñas (C1.3)

- Columnas en `usuarios` (ALTER aditivo): `intentos_fallidos`, `bloqueado_hasta`,
  `ultimo_login`, `must_change_password`.
- **Bloqueo escalado:** a los 5 fallos se bloquea 1 min; siguientes, 5 y 15 min.
  El acierto resetea el contador y registra `ultimo_login`. Lógica común en
  `_autenticar()` (salta candidatos bloqueados, rehashea, cuenta fallos).
- **Política** `src/seguridad/politica.py` (estilo NIST): mínimo 12 caracteres, sin
  contraseñas comunes, variedad mínima de 2 tipos, sin espacios en extremos. Aplicada
  en `crear_perfil` y `cambiar_password_usuario`.
- Cubierto por `tests/unit/test_politica.py` y `tests/integration/test_seguridad_acceso.py`.
- Nota: en login por perfil, el bloqueo cuenta por usuario(s) de ese perfil; con el
  modelo por-usuario (C1.4) será preciso por identidad.

## Identidad por usuario + JWT/refresh + rotación (C1.4)

- **Identidad por usuario único por empresa:** `usuarios.nombre` deja de ser único
  global y pasa a `UNIQUE(id_empresa, nombre)` (+ columna `email`). Nuevo
  `validar_login_usuario(identificador, password, id_empresa)` (login por nombre o
  email dentro de una empresa) con soporte dual de hash, rehash y bloqueo. Los
  login actuales (`validar_login` por perfil, `validar_login_empleado`) se mantienen.
- **JWT/refresh (diseño, sin endpoints):** `src/seguridad/tokens.py` emite/verifica
  access (15 min) y refresh (30 días) con claims multi-tenant (`sub`, `empresa`,
  `tienda`, `rol`). Refresh persistido **hasheado** y revocable en `sesiones`
  (`src/db/sesiones.py`). Firma HS256 con clave derivada de la maestra (o
  `SMART_MANAGER_JWT_SECRET`); pasable a RS256 sin cambiar la interfaz.
- **Identidades externas (OIDC):** tabla `identidades_externas` reservada para
  vincular Google/Microsoft/Apple en fase posterior.
- **Rotación de clave maestra:** `cripto` soporta **MultiFernet** vía
  `SMART_MANAGER_SECRET_KEYS` (la primera cifra, todas descifran) + helper `rotar()`
  para re-cifrar con la clave activa. Recomendado: clave maestra en variable de
  entorno/secrets manager, fuera del directorio de datos.
- Cubierto por `tests/unit/test_tokens.py` y `tests/integration/test_identidad_sesiones.py`.

## Imprescindible SaaS vs fase posterior
- **Hecho en C1 (imprescindible):** Argon2id+rehash, cifrado de secretos en reposo,
  bloqueo+política, identidad por usuario por empresa, diseño JWT/refresh + sesiones,
  rotación MultiFernet.
- **Fase posterior:** endpoints JWT de la API (A1), OIDC (Google/MS/Apple), MFA/2FA,
  claves por-tenant/KMS, comprobación HIBP, rotación forzada de contraseñas.
