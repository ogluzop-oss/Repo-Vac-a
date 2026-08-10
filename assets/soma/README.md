# Character Pack oficial de SOMA

Coloca aquí las **ilustraciones maestras** del personaje SOMA. El sistema es **agnóstico al formato**:
para cada estado buscará, por orden de prioridad:

1. `<estado>.gif` / `<estado>.apng`  → animado (`QMovie`)
2. `<estado>.sheet.png` + `<estado>.json`  → sprite sheet (frames)
3. `<estado>.png`  → ilustración estática (con transformaciones/microanimaciones)

Si falta el asset de un estado, se usa un **placeholder** dibujado (para que la app funcione durante el
desarrollo). Sustituir los placeholders es tan simple como dejar el PNG correcto con el nombre indicado.

## Archivos esperados (nombres exactos)

| Archivo | Estado / uso |
|---|---|
| `dormido.png`      | Reposo / DORMIDO (durmiendo) |
| `escuchando.png`   | ESCUCHANDO (mano hacia la oreja) |
| `pensando.png`     | PENSANDO (mano en la barbilla) |
| `procesando.png`   | PENSANDO alternativo (engranajes / procesando) — opcional |
| `hablando.png`     | HABLANDO (bocadillo) |
| `esperando.png`    | ESPERANDO (relajado) |
| `explicando.png`   | Explicando — opcional (conversación) |
| `feliz.png`        | Feliz — opcional (confirmaciones positivas) |
| `confirmacion.png` | CONFIRMACION (manos juntas) |
| `error.png`        | ERROR (404 / mareado) |
| `sorprendido.png`  | Sorprendido — opcional |
| `parpadeo.png`     | Ojos cerrados (para el **parpadeo**) |

> Recomendado: PNG con transparencia, ~500×500 px, personaje centrado. El sistema recorta/escala.

## Mapa estado del Kernel → ilustración

`DORMIDO→dormido · APARECIENDO→escuchando · ESCUCHANDO→escuchando · PENSANDO→pensando(→procesando) ·
HABLANDO→hablando · ESPERANDO→esperando(→feliz) · CONFIRMACION→confirmacion · ERROR→error ·
DESAPARECIENDO→(ilustración actual con transición de salida)`

El parpadeo (`parpadeo.png`) se superpone brevemente sobre las ilustraciones con ojos abiertos.
