# IOC v2.0 — BLOQUE III.1: Integración IOC ↔ CRM (informe final)

> Primera adopción real de IOC por un módulo funcional (Strangler). Aditivo, behavior-preserving,
> multiempresa, auditado. Verificado; smoke 5 passed; cero regresiones.

## 1. Auditoría previa (resumen)

Ver `INFORME_IOC_V2_B3_1_CRM.md`. Conclusión: el CRM es **puramente empresa-scoped** (no usa
tienda/almacén/centro/códigos). Único seam de identidad = el helper `_emp(id_empresa)` replicado en 10
módulos (7 con `id_empresa or empresa_actual_id()`, 3 con `fuentes.emp`). Los 123 accesos SQL son a
tablas de **dominio CRM** (no de identidad) y quedan fuera de alcance.

## 2. Elementos migrados

- **Adaptador CRM↔IOC** nuevo: `src/services/crm/identidad_crm.py` (sobre `IdentityAPI`).
- **7 módulos CRM** migrados en su seam de identidad (`_emp` → `identidad_crm.empresa_id`):
  `actividades, analitica, automatizacion, crm_scoring, leads, oportunidades, pipeline`.
  El resto de su lógica funcional queda **intacto**.

## 3. Elementos pendientes (migración posterior, documentada)

- 3 módulos con variante `fuentes.emp` (`campanias, objetivos, rutas`): ya usan una abstracción de
  resolución; se migrarán al adaptador en una iteración posterior sin urgencia.
- Acceso a datos de **dominio CRM** (clientes/oportunidades): **no se migra** (es lógica funcional,
  no identidad; protegido por la regla de no tocar el CRM).
- GUI del CRM: sin cambios (comportamiento visible idéntico).

## 4. Métodos reutilizados (IOC, sin duplicar)

- `IdentityAPI.obtener_contexto()` → `identidad_crm.contexto()`.
- `IdentityAPI.resolver_por_empresa()` → `identidad_crm.identidad_cliente()`.
- `IdentityAPI.resolver()` → `identidad_crm.resolver()`.
- `IdentityAPI.telemetria()` → `identidad_crm.telemetria()`.
- Capa base IOC `identidad._base.emp()` → `identidad_crm.empresa_id()` (idéntico a `_emp` histórico).

## 5. Cambios realizados

1. `src/services/crm/identidad_crm.py` (nuevo adaptador: `empresa_id`, `contexto`,
   `identidad_cliente`, `resolver`, `telemetria`).
2. 7 ediciones quirúrgicas: cada `_emp` pasa a delegar en `identidad_crm.empresa_id(id_empresa)`
   (comportamiento idéntico, con *fallback* al comportamiento histórico si IOC no estuviera disponible).
- **Sin migración de BD.** Sin cambios en IOC v1/v2, IdentityService/Repository/Resolver/Validation/
  API. Sin cambios en la lógica funcional ni en la GUI del CRM.

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|-----------|
| Cambiar el comportamiento del CRM | `empresa_id` devuelve exactamente lo mismo que `_emp`; verificado (`==` en 7 módulos) |
| Fallo de IOC rompe el CRM | *Fallback* a `id_empresa or empresa_actual_id()` dentro del adaptador |
| Ciclo de dependencias | CRM→IOC (import lazy en `_emp`); IOC nunca importa CRM |
| Flujo de eventos excesivo | El camino caliente (`empresa_id`) NO publica eventos; solo las resoluciones significativas |
| Fugas multiempresa | Se resuelve siempre `id_empresa`; verificado aislamiento |

## 7. Compatibilidad garantizada

- IOC v1/v2 e IdentityAPI **intactos** y reutilizados.
- CRM: comportamiento y salida idénticos; multiempresa preservada; auditoría existente sin duplicar.
- Aditivo y reversible (revertir = restaurar los 7 `_emp` originales; sin BD que revertir).

## 8. Pruebas realizadas (todas verdes)

| Prueba | Resultado |
|--------|-----------|
| `_emp` idéntico al histórico (7 módulos) | ✔ (`==E` y `=='X'`) |
| Resolución de identidad vía IdentityAPI | ✔ |
| IdentityContext (empresa) | ✔ |
| Multiempresa (aislamiento, sin fugas) | ✔ |
| Evento `crm.identidad.resuelta` (publicado + en bus) | ✔ |
| Telemetría (adaptador + IdentityAPI) | ✔ |
| Clientes/empresas/contactos/actividades (CRM funcional) | ✔ (opera vía `_emp` migrado) |
| Compatibilidad IOC v1 / v2 | ✔ |
| Smoke tests | ✔ **5 passed** |
| Regresiones | ✔ **cero** |

## 9. Informe técnico final

El CRM inaugura la **adopción real de IOC**: su resolución de identidad (empresa) pasa ahora por la
`IdentityAPI` mediante un adaptador fino, sin alterar su lógica funcional ni su comportamiento visible,
con telemetría y eventos para las resoluciones significativas y *fallback* a prueba de fallos. El mismo
patrón (auditar seam de identidad → adaptador sobre `IdentityAPI` → migrar el seam, preservando
comportamiento) se replicará en Stock, Compras, Ventas, Producción, RRHH, Finanzas, TPV y el resto.

### Anexo — Ficheros
- Nuevo: `src/services/crm/identidad_crm.py`
- Editados (seam `_emp`): `crm/{actividades,analitica,automatizacion,crm_scoring,leads,oportunidades,pipeline}.py`
- Sin migración; sin cambios en IOC ni en la lógica/GUI del CRM.
