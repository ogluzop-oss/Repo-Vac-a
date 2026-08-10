# INFORME — Servicio Corporativo de Resolución de Destinatarios

**Proyecto:** Smart Manager AI · **Bloque:** Evolución del módulo de Correo → infraestructura
corporativa de comunicación · **Estado:** implementado y validado · **Fecha:** 2026-07-12

---

## 1. Objetivo cumplido

El módulo de correo deja de ser un editor SMTP donde el destinatario se teclea a mano. Se ha creado
un **Servicio Corporativo de Resolución de Destinatarios**: un servicio autónomo, único y reutilizable
que localiza, clasifica, sugiere y resuelve destinatarios a partir de TODA la información del ERP,
respetando el aislamiento multiempresa y **sin alterar la lógica de envío existente**. Correo lo
consume; cualquier canal futuro (WhatsApp, SMS, push, IA, Bots, firma, envío documental) podrá
consumirlo igual.

---

## 2. Arquitectura implementada

Capa nueva **desacoplada** (sin PyQt, sin dependencia del módulo Correo) bajo `src/services/
destinatarios/`, más una capa GUI fina que solo consume el servicio.

```
src/services/destinatarios/
  __init__.py     Fachada pública (API única): buscar_destinatarios, resolver_para_documento,
                  registrar_envio, marcar_favorito/quitar_favorito, registrar_fuente, registrar_politica
  modelo.py       Destinatario (objeto ENRIQUECIDO) + tipos + etiquetas + estados con aviso
  fuzzy.py        Normalización sin acentos + coincidencia difusa + puntuación (stdlib; sin IA)
  historico.py    Histórico de aprendizaje + favoritos (multiempresa, por usuario)
  fuentes.py      Registro de adaptadores + FuenteTabla (adaptador genérico tenant-safe) + 8 fuentes
  servicio.py     Orquestación: multiempresa → fuentes + histórico → fuzzy → dedup → orden → políticas

src/gui/
  destinatarios_autocomplete.py   Autocompletado enriquecido para cualquier QLineEdit (consume servicio)
  agenda_corporativa.py           Agenda Corporativa Virtual (vista consolidada de solo lectura)

src/database/migraciones/0123_destinatarios_resolucion.py   Tablas histórico + favoritos (aditiva)
tests/unit/test_destinatarios.py                            Batería de validación (7 tests)
```

**Flujo de una resolución:** `buscar_destinatarios(id_empresa, texto, contexto, usuario)` →
(1) exige `id_empresa`; (2) recolecta candidatos de TODAS las fuentes registradas (cada una filtra por
`id_empresa`) + histórico; (3) deduplica por correo; (4) anota favoritos; (5) puntúa (fuzzy + boosts de
favorito/frecuencia/contexto); (6) ordena; (7) aplica el pipeline de políticas (no-op hoy); (8)
devuelve los N mejores `Destinatario`.

---

## 3. Servicio corporativo creado (API)

| Función | Propósito |
|---|---|
| `buscar_destinatarios(id_empresa, texto, *, contexto, usuario, limite)` | Resolución/sugerencia principal. Devuelve `List[Destinatario]` ordenada. |
| `resolver_para_documento(*, id_empresa, contexto, correo, nombre, nif, tipo, usuario)` | Resolución documental automática (Parte N). Único punto para documentos. |
| `registrar_envio(correo, nombre, *, id_empresa, usuario, contexto)` | Aprendizaje: +1 envío y último uso. |
| `marcar_favorito` / `quitar_favorito` | Favoritos por usuario. |
| `registrar_fuente(fuente)` | **Punto de extensión** oficial para nuevas fuentes. |
| `registrar_politica(fn)` | **Punto de extensión** para políticas corporativas futuras (no-op hoy). |

**Objeto `Destinatario` (enriquecido, nunca cadena):** `correo`, `nombre_mostrado`, `tipo`, `etiqueta`,
`id_empresa`, `modulo_origen`, `id_origen`, `estado`, `avisos[]`, `score`, `favorito`, `reciente`,
`num_envios`, `extra`. La conversión a texto (la propia dirección) la hace el consumidor.

---

## 4. Módulos integrados

- **Correo** (`src/gui/correo_corporativo.py`): el campo *DESTINATARIO* del `EnviarDocumentoDialog`
  tiene autocompletado corporativo (sugerencias enriquecidas con etiqueta y aviso). Tras un envío OK
  se registra el destinatario en el histórico. `enviar_documento_por_correo(...)` acepta ahora
  `contexto` y `pistas` (opcionales, retrocompatibles) para priorizar sugerencias y para la resolución
  documental automática. **El motor de envío (`enviar_documento`) no se ha tocado.**
- **Agenda Corporativa Virtual**: botón "AGENDA" en Correo → vista consolidada de solo lectura.

---

## 5. Fuentes de datos utilizadas (todas tenant-safe)

Registradas hoy (8), todas leyendo su módulo/tabla original (no se duplican datos):

| Fuente | Tabla | Tipo | Multiempresa |
|---|---|---|---|
| Clientes | `clientes` | cliente | `id_empresa` |
| Proveedores | `proveedores` | proveedor (+ aviso *bloqueado*) | `id_empresa` |
| Empleados | `rrhh_empleados` | empleado | `id_empresa` |
| Usuarios | `usuarios` | usuario (+ aviso *deshabilitado*) | `id_empresa` |
| Contactos de cliente | `clientes_contactos` | contacto | `id_empresa` |
| Contactos de proveedor | `proveedores_contactos` | contacto | **JOIN** a `proveedores` |
| Centros de trabajo | `centros_trabajo` | centro (+ aviso *archivado*) | `id_empresa` |
| Leads CRM | `crm_leads` | lead/candidato | `id_empresa` |

**Histórico corporativo:** además, todo destinatario ya usado (aunque **no** pertenezca al ERP) se
guarda en `destinatarios_historico` y vuelve a sugerirse (recientes).

**Añadir una entidad nueva** = registrar un adaptador (`registrar_fuente(FuenteTabla(...))`), sin tocar
el núcleo. Entidades no presentes hoy como tablas (transportistas, bancos, asesorías, mutuas…) se
incorporarán con una línea cuando existan.

---

## 6. Cumplimiento de las restricciones arquitectónicas

1. **Punto único** — Correo y la resolución documental usan solo el servicio. ✔
2. **Adaptadores registrables** — `FuenteTabla` + `registrar_fuente`; sin consultas rígidas. ✔
3. **Objetos enriquecidos** — siempre `Destinatario`, nunca cadenas. ✔
4. **Multiempresa estricto / SaaS-ready** — `id_empresa` obligatorio y propagado; validado sin cruces. ✔
5. **Documental sin lógica propia** — `resolver_para_documento` centraliza. ✔
6. **Preparado para políticas** — pipeline `registrar_politica` (listas negras/blancas, consentimiento,
   preferencias, prioridades, canales) como no-op activable después. ✔
7. **Extensible/desacoplado/permanente** — núcleo agnóstico de framework. ✔

---

## 7. Validaciones realizadas (Parte U)

- **Búsqueda difusa:** `mercadna`→Mercadona, `garca`→García, `jse`→José. ✔
- **Multiempresa (0 cruces):** empresa A nunca ve contactos de B, ni por texto ni como sugerencia;
  verificado también en el filtro por JOIN (contactos de proveedor). ✔
- **Avisos:** proveedor bloqueado / usuario deshabilitado / centro archivado marcados, sin impedir
  el envío. ✔
- **Orden inteligente:** favorito primero; recientes por frecuencia; contexto de módulo prioriza
  (compras→proveedores) sin ocultar el resto. ✔
- **Histórico/aprendizaje:** correos externos al ERP se sugieren tras su primer uso. ✔
- **Resolución documental:** por NIF, por nombre y por correo directo. ✔
- **No regresión de Correo:** `enviar_documento` con firma intacta; suite OAuth/Gmail/SMTP/IMAP
  verde. ✔
- **Suite:** `smoke_test` (5) + `test_correo_oauth` + `test_destinatarios` (7) → **20 passed**.
- **Reversibilidad de la migración:** `revertir` elimina las tablas y `aplicar` las recrea. ✔

Comando: `QT_QPA_PLATFORM=offscreen DB_NAME=smart_manager_test python -m pytest -o addopts="" -q -p
no:cacheprovider tests/smoke_test.py tests/integration/test_correo_oauth.py tests/unit/test_destinatarios.py`

---

## 8. Riesgos detectados y mitigación

- **Rendimiento a gran escala:** cada fuente acota su búsqueda (prefiltro SQL `LIKE` por tokens, tope
  200 + muestra reciente, tope 400) y el autocompletado va con *debounce* (180 ms). Para tenants muy
  grandes se puede subir a índices/consulta full-text sin cambiar la API. *Riesgo bajo.*
- **Esquemas heterogéneos:** el adaptador genérico valida la existencia de columnas antes de consultar
  (degrada a vacío si difieren). *Riesgo bajo.*
- **Difusa vs. exactitud:** el umbral difuso (0.62) evita ruido; el orden prioriza exacto/prefijo sobre
  difuso. *Riesgo bajo.*
- **Fuentes futuras sin `id_empresa` directo:** cubiertas con filtro por JOIN (patrón demostrado con
  contactos de proveedor). *Riesgo bajo.*

---

## 9. Rollback

- **Migración:** `0123_destinatarios_resolucion` es reversible (`revertir` elimina
  `destinatarios_historico` y `destinatarios_favoritos`).
- **Integración:** 100% aditiva. Los nuevos parámetros de `enviar_documento_por_correo` (`contexto`,
  `pistas`) son opcionales; retirar la instalación del autocompletado y el `registrar_envio` deja el
  módulo de Correo exactamente como estaba. El motor de envío no se modificó, así que no hay nada que
  revertir ahí.
- **Servicio:** eliminar el paquete `src/services/destinatarios` y sus dos consumidores GUI no afecta a
  ninguna funcionalidad previa.

---

## 10. Evolución futura

- **Políticas corporativas de comunicación** (ya con punto de enganche): listas negras/blancas,
  consentimiento (RGPD), preferencias y canales preferidos por contacto, prioridades, reglas de
  automatización — se implementan como funciones `registrar_politica(...)` sin rediseño.
- **Más fuentes**: transportistas, bancos/acreedores, asesorías, mutuas, seguros, departamentos,
  candidatos RRHH… en cuanto existan como entidades, una línea de `registrar_fuente`.
- **Búsqueda full-text / índices** para tenants muy grandes.
- **SaaS multitenant**: el `id_empresa`/tenant ya se exige y propaga en toda la cadena.

---

## 11. Reutilización por otros canales

El servicio es agnóstico de canal y de framework. Cualquier sistema de comunicación resuelve
destinatarios con la MISMA API:

```python
from src.services import destinatarios
for d in destinatarios.buscar_destinatarios(id_empresa, texto, contexto="compras"):
    enviar_por_whatsapp(d.telefono_o_correo)   # el canal decide qué campo usar
```

Aplicable a: **Correo (hecho), WhatsApp Business, SMS, Notificaciones Push, Firma Electrónica,
Automatizaciones, Bots, IA/Agentes y Envío documental.** Un único punto de resolución, coherente,
multiempresa y permanente para todo el ERP.
