# CERTIFICACIÓN ARQUITECTÓNICA — SISTEMA MFA EMPRESARIAL

## Smart Manager AI · Multi-Factor Authentication

**Proyecto:** implementación integral del MFA empresarial sobre la infraestructura existente.
**Fases:** 0–8 ejecutadas y cerradas.
**Resultado de la suite:** `546 passed, 1 skipped` (MFA: 26 tests nuevos; baseline previo 505 → +41 en todo el programa).

---

## 1. Fases ejecutadas

| Fase | Objetivo | Estado |
|---|---|---|
| 0 | Preparación y gobernanza (RBAC `mfa.*`, política por empresa, eventos) | ✅ |
| 1 | Enrolamiento MFA en la interfaz (QR + recovery codes) | ✅ |
| 2 | MFA en la API humana (cierre del bypass) | ✅ |
| 3 | Recuperación y reset administrativo | ✅ |
| 4 | Dispositivos de confianza (sobre `ioc_terminales`) | ✅ |
| 5 | WebAuthn / Passkeys (relying party, degradable) | ✅ |
| 6 | MFA adaptativo por empresa y rol | ✅ |
| 7 | Step-up authentication | ✅ |
| 8 | Certificación (este documento) | ✅ |

## 2. Verificación de invariantes (con evidencia)

### Seguridad
| Criterio | ✔ | Evidencia |
|---|---|---|
| No bypass MFA | ✅ | `/auth/login` no emite JWT con 2º factor activo; `mfa_token` (`type='mfa_pending'`) rechazado por el guard `access` (`test_mfa_api`). |
| No secretos en logs | ✅ | `mfa_eventos._sanea` enmascara; grep en `mfa*.py`: ningún log del secreto/código/recovery (solo se loguean excepciones). |
| No secretos en claro | ✅ | Secreto TOTP cifrado (Fernet, `utils/cripto`); recovery codes hasheados (Argon2/SHA-256); WebAuthn solo datos públicos. |
| Rate limiting | ✅ | `/auth/mfa` 5/5min → 429 (`test_mfa_reset`). |
| Recuperación segura | ✅ | Recovery codes de uso único + regeneración invalida los anteriores (`test_mfa_reset`). |
| Reset admin auditado | ✅ | `mfa_admin.reset_mfa` (RBAC + evento `MFA_RESET`) (`test_mfa_reset`). |
| Step-up | ✅ | Ventana efímera + `verificar` TOTP/recovery (`test_mfa_stepup`). |

### Arquitectura (N7)
| Criterio | ✔ | Evidencia |
|---|---|---|
| Un solo motor TOTP | ✅ | `verificar_totp`/`generar_secreto` definidos **solo** en `mfa.py`. |
| Sin motores paralelos | ✅ | 8 módulos MFA orquestan el motor único; 3 tablas nuevas (0160–0162) + reuso de `mfa_usuarios`/`mfa_recovery_codes` (0060). |
| Reutilización | ✅ | `cripto` (Fernet), `tokens`/`sesiones` (JWT/refresh), `autorizacion`/`catalogo` (RBAC), `ioc_terminales`/`terminal_rol`, `log_auditoria`/`registrar_evento`, `rate_limit`. |

### Multiempresa
| Criterio | ✔ | Evidencia |
|---|---|---|
| Política por empresa | ✅ | `mfa_politica` (fila por `id_empresa`) (`test_mfa_politica`/`_adaptativo`). |
| Override por rol | ✅ | `roles_obligatorios` + suelo `ROLES_CRITICOS` (`test_mfa_adaptativo`). |
| Factor por usuario | ✅ | `mfa_usuarios.id_usuario` (UNIQUE). |
| Contexto de empresa activo | ✅ | `politica_efectiva`/`mfa_decision` resuelven por `id_empresa`. |

### Compatibilidad
| Superficie | Estado |
|---|---|
| Escritorio | MFA en login (opt-in/adaptativo) + enrolamiento UI; TOTP. |
| REST / GraphQL | `/auth/login`+`/auth/mfa`+`/auth/webauthn/*`; claims `amr`/`mfa`. |
| Móvil | `mobile/auth` (ya usaba MFA) intacto. |
| TPV / PDA / MDE | Dispositivo de confianza; PIN operativo/cambio de cajero intactos. |
| Autocobro / kiosco | `contexto` sin MFA interactivo. |
| **API keys / M2M** | **Sin MFA humano** (ruta de auth separada, intacta). |

## 3. Componentes (mapa)

- Motor: `mfa.py` (TOTP+recovery+cifrado). Gobernanza: `mfa_politica.py` (0160). Decisión: `mfa_decision.py`.
- Reset admin: `mfa_admin.py`. Dispositivos: `mfa_dispositivos.py` (0161). WebAuthn: `mfa_webauthn.py` (0162).
- Step-up: `mfa_stepup.py`. Eventos: `mfa_eventos.py`. UI: `gui/mfa_gui.py`. API: `api/routers/auth.py`+`webauthn.py`.

## 4. Criterios de aceptación (21) — cumplidos

TOTP reutilizado ✅ · recovery reutilizados ✅ · MFA escritorio ✅ · MFA API humana ✅ · sin bypass ✅ ·
API keys operativas ✅ · enrolamiento UI ✅ · recuperación ✅ · reset admin seguro ✅ · dispositivos de
confianza ✅ · TPV sin TOTP por cambio de cajero ✅ · autocobro operativo ✅ · política por empresa ✅ ·
overrides por rol ✅ · WebAuthn/Passkeys ✅ · step-up ✅ · operaciones críticas auditadas ✅ · sin
secretos en logs ✅ · sin motores paralelos ✅ · compatibilidad hacia atrás ✅ · regresión en verde ✅.

## 5. Dependencias
- **Nueva**: `webauthn 3.0.0` (estándar, mantenida) — degradable (sin ella, WebAuthn se desactiva y TOTP
  sigue). Subió `cryptography`→49/`pyOpenSSL`→26; regresión completa verde. Recomendado fijar versiones
  al provisionar producción.

## 6. Certificación

Se **CERTIFICA** que el sistema MFA de Smart Manager cumple la arquitectura aprobada: TOTP + recovery
codes + política por empresa + overrides por rol + dispositivos de confianza + WebAuthn/Passkeys + MFA
adaptativo + step-up + auditoría; integrado con la infraestructura existente, **sin duplicidades, sin
motores paralelos** y **sin romper** login/RBAC/sesiones/API/móvil/TPV/PDA/MDE/autocobro/multiempresa.

**🔐 Arquitectura MFA: CONGELADA.**

## 7. Cierre y consolidación (post-certificación)

Completados los huecos de la auditoría de cierre (todo reutilizando la infraestructura, N7):

- **Guard único de escritorio**: `pedir_step_up` es el mecanismo oficial. Cableado en `mfa.recovery.regenerar`,
  `mfa.desactivar` (se retiró el reauth ad-hoc) y `password.cambiar`; `mfa.admin.reset` mantiene reauth+step-up.
- **MFA reciente tras login**: `main.py` registra step-up (`mfa_stepup.registrar`) al superar el 2º factor.
- **`debe_enrolar` con efecto real**: escritorio fuerza el alta (`_enrolar_mfa_obligatorio`); API marca el
  claim `enrollment_required` y los endpoints sensibles lo exigen.
- **`auth_time` + `amr`**: el access token lleva `auth_time` (instante de autenticación) y `amr`
  (`["pwd"]` / `["pwd","otp"]` / `["pwd","webauthn"]`); `tokens.mfa_reciente` deriva la recencia del token
  real (nunca de un booleano del cliente).
- **Step-up en API**: `api/security.requiere_step_up(accion)` (guard centralizado) + `/auth/step-up`
  (refresca `auth_time`). M2M/API keys pasan sin MFA humano.
- **Política de métodos (Fase 10)**: un recovery code NO vale como step-up de alto riesgo salvo que la
  política de la empresa lo permita (`metodos` con `recovery`); TOTP/WebAuthn siempre.
- **WebAuthn**: el login por passkey fija `amr:["pwd","webauthn"]`+`auth_time`; el guard lo reconoce.
- **Eventos**: `STEP_UP_REQUIRED/SUCCESS/FAILURE` añadidos a la taxonomía; nunca se registran secretos.

**Tests**: +4 (`test_mfa_cierre.py`) + ajuste de gating. **Regresión: 550 passed, 1 skipped.**

## 8. Cableado de acciones críticas de negocio (fase final)

Las 12 acciones de `mfa_stepup.ACCIONES_CRITICAS` quedan **cableadas end-to-end** al guard oficial. Las 4
propias del MFA ya lo estaban (`password.cambiar`, `mfa.desactivar`, `mfa.recovery.regenerar`,
`mfa.admin.reset`); en esta fase se conectan las **8 de negocio** en su punto de decisión (chokepoint) del
escritorio, reutilizando **`gui.mfa_gui.step_up_sesion(accion)`** (atajo de `pedir_step_up` que toma el
usuario de `sesion_global`). RBAC se evalúa **antes** del step-up; nunca al revés.

| Acción crítica | Superficie escritorio (chokepoint) | REST humano |
|---|---|---|
| `roles.cambiar` | `seguridad_gui`: `_nuevo_rol` / `_asignar` / `_desasignar` | — (sin endpoint) |
| `permisos.cambiar` | `seguridad_gui`: `_conceder` / `_quitar` (ACL es solo lectura) | — |
| `pagos.pasarela.configurar` | `tpv._PasarelaConfigDialog._guardar` | — |
| `canal_web.dominios` | `tpv`: `_acc_cambiar/comprar/renovar_dominio` | — |
| `saas.admin` | `saas_admin`: `_cambiar_plan` / `_renovar` | — |
| `finanzas.critica` | `tesoreria_gui._generar_remesa` (SEPA) | — |
| `email.cambiar` | `gestion_usuarios._de_guardar_empresa` (solo si cambia `email_principal`) | — |
| `secretos.acceder` | **sin superficie**: los secretos son *write-only* (se cifran, nunca se muestran); `secret_manager.obtener_secreto` es de consumo interno/M2M → gate reservado, no se cablea (no romper M2M) | — |

**API/REST**: ninguna de las 8 acciones expone hoy un endpoint humano de escritura protegido por JWT
(el router `commerce` es solo GET; no hay endpoints de roles/pasarelas/dominios/SaaS/tesorería). El guard
`requiere_step_up(accion)` está probado (`test_mfa_cierre`) y listo para cablearse **si** esos dominios se
exponen a futuro. **API keys / M2M nunca** pasan por MFA humano.

**Garantías**: se reutiliza el guard único (0 motores nuevos, 0 tablas nuevas, 0 endpoints nuevos); el
step-up respeta usuario+empresa (`sesion_global` + `id_empresa`, sin reuso cross-empresa); nunca se
registran secretos; el guard es degradable (no bloquea flujos legítimos ante un fallo del subsistema MFA).

**Tests**: +4 (`test_mfa_acciones_criticas.py`: registro de las 8, delegación de `step_up_sesion` con
usuario de sesión, paso sin MFA activo, degradación ante error). **Regresión: 554 passed, 1 skipped.**

## 9. Mejoras futuras (fuera de alcance, requieren aprobación)
- Cablear `requiere_step_up` en los endpoints REST cuando esos dominios se expongan como escritura humana
  (Tesorería/pasarelas/dominios/secretos/SaaS).
- Provisión reproducible de `webauthn` (requirements pinneado) y paso a RS256 en multi-servicio.
