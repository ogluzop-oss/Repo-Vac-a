# AUDITORÍA ESTRATÉGICA PREVIA — FASE 3

## Bloque: Facturación Profesional Avanzada

> **Naturaleza:** informe de arquitectura y planificación. **NO contiene implementación.**
> Objetivo: decidir el alcance exacto de la FASE 3 antes de tocar código.
> **Fecha:** 2026-06-29 · Base: FASE 1 (auditoría) + FASE 2 (pasos 1–8, migr 0071–0075).

---

## 0. Activos ya existentes (NO rehacer)

La auditoría del código confirma que hay infraestructura empresarial **ya construida** que la
FASE 3 debe **reutilizar/cablear**, no reimplementar:

| Activo existente | Ubicación | Estado real |
|---|---|---|
| Núcleo fiscal Verifactu (hash chain, QR, cola) | `src/db/fiscal.py`, `src/services/fiscal/` | Operativo; enlazado a factura (FASE 2) |
| **Facturae 3.2.x + FACe/FACeB2B** | `src/services/fiscal/facturae/` | Existe; cableado al **registro fiscal**, NO a la factura comercial |
| **SEPA pain.001/008 + conciliación N43/CAMT** | `src/services/tesoreria/sepa.py` (+ módulo) | Operativo (tesorería); NO genera remesas desde factura cliente |
| **Motor de vencimientos AR/AP** (cobro/pago) | `src/db/vencimientos.py` | Operativo; la factura cliente NO crea vencimiento AR automático |
| Cobros / pagos | `src/db/cobros.py`, `src/db/pagos.py` | Operativos a nivel de venta/tesorería |
| **Cobro mixto** (efectivo+tarjeta) | venta/autocobro (`conexion.py`, self_checkout) | Existe en la VENTA; la factura solo guarda 1 `forma_pago` |
| Retención (compras) | migr `0053_compras_retencion` | Solo lado COMPRAS; no hay IRPF en ventas/cliente |
| Modelos AEAT (303/390/111/190/347/349) | `src/services/aeat/` | Operativos; leen ventas/compras, no la capa factura_* nueva |
| `factura_impuestos.tipo_recargo/cuota_recargo` | migr 0071 | Columnas **provisionadas**, sin lógica |
| `factura_eventos` | migr 0071 | Operativo (generada/vista/anulada); faltan eventos export/email |
| `factura_qr` | migr 0071 | Guarda QR Verifactu; falta QR interno propio |

**Implicación estratégica:** gran parte de la FASE 3 es **integración** (cablear factura↔SEPA,
factura↔vencimientos AR, factura↔Facturae/FACe) más que desarrollo desde cero.

---

## 1. Análisis de impacto por bloque

Para cada bloque se evalúan los 15 ejes solicitados. Se marca el nivel de impacto:
**(A)lto · (M)edio · (B)ajo · (—) nulo**. Solo se detallan los ejes con impacto real.

### PARCIALES

#### P1 · Formas de pago avanzadas (cobro mixto y pagos parciales)
- **Funcional (A):** la factura debe reflejar varios medios de pago y cobros parciales (la venta ya soporta mixto; falta trasladarlo a la factura).
- **Fiscal (B):** la forma de pago no altera base/IVA; sí es dato exigible en algunos formatos (Facturae `PaymentDetails`).
- **Documental (M):** el PDF/snapshot debe listar el desglose de pago.
- **Verifactu (—):** no afecta a la huella ni al QR.
- **AEAT (B):** medios de cobro relevantes para 347 (cobros en metálico > umbral).
- **CRM (M):** condiciones de pago del cliente.
- **TPV (M):** reutilizar el cobro mixto de la venta como origen.
- **Kárdex (—).** **Auditoría doc. (B):** evento de cobro.
- **SaaS multi (B):** por empresa/tienda.
- **Compat. históricas/snapshots/hashes/numeración/sistema validado (B):** aditivo (tabla de pagos por factura + campo); snapshots antiguos sin desglose siguen válidos.

#### P2 · Eventos de exportación
- **Funcional (M):** registrar cada exportación (PDF/Facturae/CSV/XML).
- **Documental (A):** traza de qué se exportó, cuándo, por quién, a qué formato/destino.
- **Auditoría doc. (A):** núcleo de la trazabilidad legal.
- **Verifactu/AEAT (B):** la exportación de Facturae/Verifactu debe quedar registrada.
- **SaaS multi (B).** **Resto (—).**
- **Compat. (B):** aditivo puro (usa `factura_eventos` + nueva `factura_exportaciones`).

#### P3 · Eventos de envío por email
- **Funcional (A):** enviar la factura al cliente y registrar el envío.
- **Documental (A):** acuse/estado de envío.
- **CRM (M):** email del cliente (ya existe en cliente).
- **Comunicaciones (M):** reutilizar SMTP existente (`plantillas_correo`, módulo correo).
- **Auditoría doc. (A):** evento de envío.
- **Resto (—).** **Compat. (B):** aditivo (`factura_envios` + evento).

#### P4 · QR interno documental
- **Funcional (M):** QR de verificación interna cuando NO hay Verifactu.
- **Documental (M):** se incrusta en el PDF (snapshot lo congela).
- **Verifactu (B):** NO debe colisionar con el QR legal (prioridad: QR Verifactu si activo).
- **Auditoría doc. (M):** vincula PDF↔hash interno.
- **Resto (—).** **Compat. (M):** snapshots ya emitidos NO llevan QR interno → debe ser
  opcional y no romper la regeneración de los antiguos.

#### P5 · Recargo de equivalencia
- **Funcional (M):** aplicable a clientes en régimen de recargo.
- **Fiscal (A):** añade una cuota adicional por tipo (4%→5,2% / 1,4% / 0,5%…).
- **Documental (A):** el PDF debe mostrar base, IVA y recargo por tipo.
- **Verifactu (A):** el desglose entra en la huella/registro (campos de cuota).
- **AEAT (A):** afecta a 303/390.
- **CRM (A):** atributo fiscal del cliente (¿está en recargo?).
- **TPV (M):** la venta debería marcar el régimen para arrastrarlo.
- **Auditoría/SaaS (B).** **Kárdex (—).**
- **Compat. (M):** columnas ya existen (0071); el motor multi-IVA debe extenderse SIN
  cambiar el resultado de las facturas actuales (cuando no hay recargo, idéntico a hoy).

### PENDIENTES

#### D1 · `factura_exportaciones`
- **Documental/Auditoría (A):** tabla de registro de exportaciones (formato, ruta, hash, destino, usuario, fecha).
- **AEAT/Verifactu (B):** registra la generación de Facturae/Verifactu.
- **SaaS multi (B).** **Resto (—).** **Compat. (B):** tabla nueva aditiva.

#### D2 · `factura_envios`
- **Documental/Auditoría (A):** registro de envíos (canal email/FACe, destinatario, estado, reintentos).
- **Comunicaciones (M):** reutiliza SMTP/colas existentes.
- **Compat. (B):** tabla nueva aditiva.

#### D3 · Factura proforma
- **Funcional (A):** documento NO contable, sin valor fiscal.
- **Fiscal (A):** NO genera asiento ni IVA repercutido real; NO va a Verifactu/AEAT.
- **Documental (M):** PDF con marca "PROFORMA"; snapshot propio.
- **Verifactu (A):** debe EXCLUIRSE del registro fiscal/numeración fiscal.
- **CRM (M).** **Numeración (A):** serie propia (no consume la serie fiscal).
- **Compat. (M):** requiere el framework de `tipo_documento` + series por tipo.

#### D4 · Factura simplificada (ticket-factura)
- **Funcional (A):** sin datos completos del cliente; límite de importe.
- **Fiscal (A):** válida hasta umbral legal; reglas distintas de la completa.
- **Verifactu (A):** tipo de registro distinto (F2 simplificada vs F1 completa).
- **AEAT (M):** tratamiento diferenciado.
- **TPV (A):** es el caso natural del ticket → puente ticket↔factura simplificada.
- **Numeración (A):** serie propia. **Compat. (M):** framework de tipos.

#### D5 · Factura intracomunitaria
- **Fiscal (A):** exención de IVA (entrega intracomunitaria) + leyenda legal.
- **Documental (A):** NIF-IVA del cliente + validación VIES.
- **AEAT (A):** modelo 349 (ya existe) debe alimentarse desde estas facturas.
- **CRM (A):** cliente UE con NIF-IVA/VIES.
- **Verifactu (M):** clave de operación exenta. **Numeración (M):** serie recomendable.
- **Compat. (M):** motor fiscal + datos de cliente.

#### D6 · Inversión del sujeto pasivo (ISP)
- **Fiscal (A):** factura SIN IVA repercutido (lo liquida el destinatario) + leyenda.
- **Documental (A):** leyenda legal obligatoria.
- **Verifactu/AEAT (A):** clave de régimen especial; afecta a 303.
- **CRM (M):** marca de operación ISP por cliente/operación.
- **Compat. (M):** motor fiscal de líneas.

---

## 2. Elementos empresariales habituales NO contemplados (evaluación)

| Elemento | ¿Existe? | Dónde | Prioridad |
|---|---|---|---|
| **Facturae** | 🟡 en núcleo fiscal, NO en factura comercial | `fiscal/facturae/` | **ALTA** (cablear) |
| **FACe / FACeB2B** | 🟡 en núcleo fiscal, NO en factura comercial | `fiscal/facturae/emisores/` | **ALTA** (cablear) |
| **EDI** (EDIFACT/XML B2B) | ⬜ no | — | BAJA |
| **Remesas SEPA** (recibos cliente) | 🟡 motor SEPA sí; no desde factura | `tesoreria/sepa.py` | MEDIA |
| **Cobros recurrentes** | ⬜ no (solo SaaS billing interno) | — | MEDIA |
| **Facturación periódica** | ⬜ no | — | MEDIA |
| **Series documentales avanzadas** | 🟡 serie por empresa/tienda/caja; falta por tipo/ejercicio | `fiscal.serie_efectiva` | **ALTA** |
| **Facturación internacional** (multi-divisa/idioma/país) | 🟡 multidivisa sí; reglas fiscales país no | `divisas`, `fiscalidad` | MEDIA |
| **Autofacturación** | ⬜ no | — | BAJA |
| **Retenciones IRPF** (ventas) | ⬜ solo compras | `0053` (compras) | **ALTA** |
| **Gestión de vencimientos** (AR) | 🟡 motor sí; factura no lo crea | `vencimientos.py` | **ALTA** (cablear) |
| **Gestión de impagos** | ⬜ no (estado 'vencida' básico) | `facturas_cliente` | MEDIA |
| **Estados de cobro avanzados** | 🟡 básico (parcial/cobrada/vencida) | `facturas_cliente` | MEDIA |

---

## 3. Clasificación por prioridad

### 🔴 PRIORIDAD ALTA — imprescindible para un ERP moderno
1. **Datos/condiciones fiscales del cliente** (régimen: general / recargo equiv. / exento /
   intracomunitario+VIES / extranjero / ISP; retención IRPF; condiciones de pago). *Es la base.*
2. **Motor fiscal de líneas ampliado**: recargo de equivalencia, ISP, exención
   intracomunitaria, retención IRPF. *(reusa `factura_impuestos`).*
3. **Framework de tipos de documento + series por tipo/ejercicio** (factura / proforma /
   simplificada / rectificativa / intracomunitaria) con elegibilidad Verifactu por tipo.
4. **Cableado Facturae + FACe** desde la factura comercial (no solo registro fiscal).
5. **Cableado factura → vencimientos AR** (cuentas a cobrar reales).
6. **Factura simplificada** (puente natural ticket↔factura, caso más usado en retail/TPV).

### 🟠 PRIORIDAD MEDIA — valor empresarial relevante
7. **Formas de pago avanzadas** en factura (cobro mixto + pagos parciales).
8. **`factura_envios`** (email + FACe) + eventos de envío.
9. **`factura_exportaciones`** + eventos de exportación.
10. **Remesas SEPA de recibos de cliente** (desde vencimientos AR).
11. **Estados de cobro avanzados + gestión de impagos** (reclamación/escalado).
12. **Facturación periódica / cobros recurrentes**.
13. **QR interno documental**.

### 🟢 PRIORIDAD BAJA — fases futuras
14. **Facturación internacional** (reglas fiscales por país, idioma del documento).
15. **Autofacturación** (proveedor que factura por cuenta del emisor).
16. **EDI** (EDIFACT/peppol B2B).

---

## 4. Mapa completo de dependencias

```
            ┌─────────────────────────────────────────────────────────────┐
 CAPA 0     │  Datos fiscales del CLIENTE/empresa (régimen IVA, recargo,    │
 (base)     │  exento, intracom+VIES, ISP, IRPF, condiciones de pago)       │
            └───────────────┬───────────────────────────┬──────────────────┘
                            │                            │
            ┌───────────────▼─────────────┐   ┌──────────▼──────────────────┐
 CAPA 1     │  MOTOR FISCAL de líneas      │   │  FRAMEWORK tipo_documento +  │
            │  (recargo equiv · ISP ·      │   │  series por tipo/ejercicio + │
            │  intracom exención · IRPF)   │   │  elegibilidad Verifactu      │
            └───────┬──────────────┬───────┘   └──────────┬───────────┬──────┘
                    │              │                       │           │
        ┌───────────▼───┐  ┌───────▼─────────┐   ┌─────────▼───┐  ┌────▼──────────┐
 CAPA 2 │ Verifactu por │  │ AEAT (303/390/  │   │ Proforma /  │  │ Simplificada  │
        │ tipo+régimen  │  │ 349/347) feed   │   │ rectificat. │  │ (TPV puente)  │
        └───────────────┘  └─────────────────┘   └─────────────┘  └───────────────┘
                    │
        ┌───────────▼─────────────────────────────────────────────────────┐
 CAPA 3 │ FINANCIERO: cobro mixto · factura→vencimientos AR · estados de   │
        │ cobro avanzados · impagos · remesas SEPA (recibos) · recurrencia  │
        └───────────┬─────────────────────────────────────────────────────┘
                    │
        ┌───────────▼─────────────────────────────────────────────────────┐
 CAPA 4 │ DISTRIBUCIÓN: factura_envios (email/FACe) · factura_exportaciones │
        │ · eventos · Facturae cableado · QR interno (independiente)        │
        └─────────────────────────────────────────────────────────────────┘

 INDEPENDIENTES (sin dependencias fuertes): QR interno · factura_exportaciones
                  (registro) · eventos email/export (sobre factura_eventos).
```

**Lectura clave (qué va primero para evitar retrabajo):**
- **CAPA 0 antes que nada.** Si el motor fiscal o los tipos de documento se construyen sin los
  atributos fiscales del cliente, habrá que reescribir su lógica de decisión → retrabajo seguro.
- **CAPA 1 (motor fiscal) antes que los tipos especiales.** Proforma/simplificada/intracom/ISP
  son *casos* del motor; si se hacen primero, cada uno reimplementa el desglose.
- **FRAMEWORK de tipos antes que cada tipo concreto.** La numeración por serie/ejercicio y la
  elegibilidad Verifactu son transversales; hacerlas por-tipo genera duplicación.
- **DISTRIBUCIÓN (envíos/export/Facturae) al final**, cuando el documento y su fiscalidad son
  estables (si no, se regeneran exportaciones inválidas).

---

## 5. Roadmap recomendado de FASE 3 (por dependencias, no por función)

| Paso | Contenido | Capa | Migr. estimada |
|---|---|---|---|
| **3.1** | **Atributos fiscales de cliente/empresa**: régimen IVA, recargo equiv., exento, NIF-IVA/VIES, ISP, IRPF %, condiciones de pago. (CRM + empresa) | 0 | nueva |
| **3.2** | **Motor fiscal de líneas ampliado**: recargo equiv. (reusa columnas 0071), ISP, exención intracom., retención IRPF; salida en `factura_impuestos` + totales. **Sin cambiar el resultado de las facturas sin régimen especial.** | 1 | (reusa) |
| **3.3** | **Framework `tipo_documento` + series por tipo/ejercicio + elegibilidad Verifactu por tipo** (factura/proforma/simplificada/rectificativa/intracom). | 1 | nueva |
| **3.4** | **Tipos concretos**: simplificada (puente TPV), proforma, intracomunitaria. Cada uno = config sobre 3.2+3.3. | 2 | (reusa) |
| **3.5** | **Cableado Facturae + FACe** desde la factura comercial (genera XML legal desde el snapshot). | 2 | (reusa) |
| **3.6** | **Financiero**: cobro mixto + pagos parciales en factura; **factura→vencimiento AR**; estados de cobro avanzados; gestión de impagos. | 3 | nueva |
| **3.7** | **Remesas SEPA de recibos de cliente** (desde vencimientos AR, reusa `sepa.py`). | 3 | (reusa) |
| **3.8** | **Distribución documental**: `factura_envios` (email/FACe) + `factura_exportaciones` + eventos; **QR interno** (puede adelantarse, es independiente). | 4 | nueva |
| **3.9** | **Recurrencia**: facturación periódica + cobros recurrentes (programador). | 5 | nueva |
| **3.10** | (Futuro) Internacional, autofacturación, EDI. | — | — |

> Regla de oro: **3.1 → 3.2 → 3.3** son la columna vertebral; nada de lo demás debe empezar
> antes de cerrarlas. **QR interno (parte de 3.8)** es el único que puede adelantarse sin riesgo.

---

## 6. Riesgos

### 6.1 Riesgos de implementación
- **Acoplamiento con tesorería/AEAT existentes:** cablear factura→vencimientos/SEPA/Facturae sin
  romper sus pruebas. Mitigación: integración aditiva + best-effort (patrón ya usado en `gancho_venta`).
- **Doble fuente de verdad fiscal:** el motor de impuestos debe ser ÚNICO (`fiscalidad`), no
  reimplementar en cada tipo de documento.
- **Complejidad del framework de tipos:** sobre-ingeniería. Mitigación: tabla de reglas por tipo.

### 6.2 Riesgos fiscales
- **Recargo/ISP/intracom/IRPF mal aplicados** → liquidaciones AEAT incorrectas (303/349). Mitigación:
  motor único + pruebas por régimen + el régimen lo determina el cliente (CAPA 0), no el operador.
- **Proforma/simplificada que se cuelen en Verifactu** → registro fiscal indebido. Mitigación:
  elegibilidad Verifactu por tipo (3.3) ANTES de crear los tipos (3.4).
- **VIES no validado** en intracomunitaria → exención improcedente.

### 6.3 Riesgos documentales
- **Snapshots ya emitidos** no contienen los nuevos campos (recargo, tipo, QR interno). Mitigación:
  los nuevos campos son **opcionales**; la regeneración desde snapshot antiguo debe seguir siendo
  idéntica (no asumir campos nuevos).
- **Exportaciones desfasadas** si se exporta antes de estabilizar fiscalidad → registrar versión.

### 6.4 Riesgos de retrocompatibilidad
- **Facturas históricas:** todas las columnas nuevas NULLABLE/aditivas; las migraciones 0071–0075
  ya marcan el patrón (idempotentes/reversibles). Riesgo BAJO si se mantiene.
- **Hashes documentales / Verifactu:** el motor fiscal ampliado NO debe alterar la huella de los
  registros existentes ni la cadena. Mitigación: el cálculo nuevo solo aplica a documentos nuevos.
- **Numeraciones ya emitidas:** introducir series por tipo/ejercicio NO debe renumerar lo existente;
  las series actuales (A, A-T…) se conservan; las nuevas conviven.
- **Sistema validado (kárdex, ventas, contabilidad, tesorería):** la FASE 3 es aditiva sobre la
  factura comercial; no toca el kárdex ni la salida de stock. Riesgo BAJO.

---

## 7. Estimación de completitud del módulo de facturación

Respecto al objetivo del **Bloque Facturación Profesional Avanzada** (documento fiscal completo,
multi-tipo, multi-régimen, distribuido y conciliado):

| Área | Peso | Completado |
|---|---|---|
| Núcleo documental (snapshot, numeración serie, anulación/abono, PDF) | 20% | ~95% |
| Fiscalidad básica (multi-IVA por línea, desglose) | 15% | ~80% |
| Enlace fiscal Verifactu (hash/QR/registro) | 15% | ~85% |
| Auditoría documental (eventos) | 10% | ~60% |
| Fiscalidad avanzada (recargo/ISP/intracom/IRPF) | 12% | ~10% (columnas) |
| Tipos de documento (proforma/simplificada/intracom) | 10% | ~5% (campo) |
| Distribución (Facturae/FACe/email/export cableados) | 8% | ~15% (existe núcleo) |
| Financiero (cobro mixto/AR/impagos/SEPA recibos/recurrencia) | 10% | ~20% (motores existen) |

> **Completitud global estimada: ≈ 50–55%.**
> El **núcleo está sólido** (documento, numeración, snapshot, multi-IVA, enlace Verifactu);
> lo pendiente es **amplitud fiscal/comercial** (regímenes especiales, tipos de documento,
> distribución y ciclo de cobro), gran parte **cableando motores que ya existen**.

---

## 8. Recomendación de alcance para FASE 3

Cerrar **3.1 → 3.2 → 3.3** (CAPA 0 y 1: cliente fiscal + motor fiscal + framework de tipos) como
**núcleo obligatorio e indivisible** de la FASE 3, porque condicionan todo lo demás y evitan
retrabajo. A partir de ahí, **3.4–3.8** son incrementos aditivos priorizables. **3.9–3.10** (recurrencia,
internacional, EDI, autofactura) → FASE 4.

> Pendiente de tu decisión: confirmar si la FASE 3 abarca solo el núcleo (3.1–3.5) o llega hasta
> el ciclo financiero/distribución (3.6–3.8). Ningún cambio se aplicará hasta tu aprobación.

---

## 9. CIERRE — FASE 3 COMPLETA (3.1–3.8 + QR interno) ✅

Ejecutada íntegra (migraciones **0076–0080**), aditiva/idempotente/reversible, sin tocar lo
certificado. 19 tests verde.

| Subfase | Entregado | Migr. |
|---|---|---|
| **3.1** Atributos fiscales del cliente | `clientes.*` + `perfil_fiscal()` (origen único) + form CRM "Fiscalidad" | 0076 |
| **3.2** Motor fiscal avanzado | `fiscalidad.calcular_fiscalidad()` (recargo equiv. · ISP · intracom exención · IRPF) + cabecera/impuestos + PDF (recargo/retención/leyenda) | 0077 |
| **3.3** Framework tipos documentales | `services/facturacion/tipos_documento.py` (verifactu/fiscal/serie/estado/marca por tipo) | — |
| **3.4** Tipos especiales | proforma (serie PRO, sin fiscal/Verifactu, marca PDF), simplificada (serie S), intracomunitaria (serie UE, exención) | 0078 |
| **3.5** Facturae + FACe | `facturae_factura.py` (XML **desde snapshot**, reusa núcleo fiscal) | — |
| **3.6** Ciclo financiero | cobro mixto/parcial (`factura_cobros`), enlace AR (`vencimientos`), estados impago | 0079 |
| **3.7** Remesas SEPA cliente | `remesas_cliente.py` (pain.008 ADEUDO desde vencimientos AR, reusa `db.sepa`) | — |
| **3.8** Distribución + QR interno | `factura_envios`/`factura_exportaciones` + `distribucion.py` (email/Facturae) + QR interno (prioridad 2 tras Verifactu) | 0080 |

**UI:** ventana de Facturas con selector de tipo (Factura/Simplificada/Proforma/Intracom) y
acción "Exportar / Enviar" (PDF, Facturae, email). CRM con pestaña de fiscalidad.

**Principio cumplido:** integración, no duplicación — se reutilizan Facturae/FACe, SEPA,
vencimientos AR, correo corporativo y el motor fiscal único. Compatibilidad total con facturas,
snapshots, hashes y numeraciones históricas (columnas/tablas nuevas NULLABLE/aditivas; el motor
avanzado solo afecta a documentos nuevos y con régimen especial).

**FASE 4 reservada** (no abordada): internacionalización avanzada, EDI, autofacturación,
recurrencia avanzada, escenarios enterprise especializados.
