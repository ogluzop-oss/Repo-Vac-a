# Informe Técnico — Módulo 20: Seguridad

**Auditoría (ya existía):** RBAC/ACL completo (roles/permisos/grupos + motor `autorizacion.puede`,
decoradores, fallback legacy — `services/seguridad/catalogo.py`), MFA TOTP + recuperación (`mfa.py`),
hashing **Argon2id** (`src/seguridad/passwords.py`), **bloqueo por intentos fallidos escalado**
(`db/usuario.py`: 5 intentos → bloqueo 1/5/15 min), administración de sesiones (`sesiones_admin.py`),
detección de anomalías (`anomalias.py`), incidentes, RGPD (`rgpd.py`), secret_manager, tenant_guard
y auditoría de seguridad.

**Gaps implementados (migr 0120 + `src/services/seguridad/password_politica.py`):**
- **Política de contraseñas empresarial** (`seguridad_password_politica`): `obtener_politica`/
  `guardar_politica` (longitud mínima, mayús/minús/dígito/símbolo, caducidad en días, tamaño de
  historial), `validar_complejidad`.
- **Historial de no-reutilización** (`seguridad_password_historial`): `registrar_cambio` (guarda hash
  y recorta a las N últimas; sella `usuarios.password_changed_at`), `reutilizada` (**reutiliza
  `passwords.verificar`** para comparar con las N anteriores).
- **Caducidad de contraseña** (`password_caducado`): compara `password_changed_at` + días de política.

**Reutilización:** `src/seguridad/passwords` (Argon2id) para hash/verificación; el bloqueo por
intentos fallidos existente NO se toca; auditoría; multiempresa. Columna `password_changed_at` añadida
con ALTER guardado por `information_schema`.

**Pruebas:** migr 0120; política a 10 chars+símbolo+caducidad 90d; validación débil/fuerte; historial
detecta reutilización de las 2 últimas; caducidad recién cambiada = no caducada. **smoke 5 passed.**

**Mejoras futuras:** forzar `must_change_password` cuando `password_caducado`; enganchar
`validar_complejidad`/`reutilizada` en el flujo real de cambio de contraseña de la GUI; IP allowlist
y expiración de sesión configurable.
