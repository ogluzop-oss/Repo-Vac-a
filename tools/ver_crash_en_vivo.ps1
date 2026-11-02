# Muestra en ESTA terminal, en vivo, cualquier crash nativo (p.ej. 0xc0000005 en Qt6Widgets.dll)
# que ocurra en la app mientras se prueba en OTRA terminal. `faulthandler` (ya activo en
# src/main.py) solo puede escribir a un fichero, nunca a la vez a la terminal donde corre la
# app -- este script lee ese fichero en vivo para verlo aparecer al instante.
#
# Uso: abre una terminal aparte y ejecuta este script ANTES de lanzar `python -m src.main` en la
# otra; déjalo abierto mientras pruebas. Cuando la app se cierre de golpe, el stack real
# aparecerá aquí en segundos.
Write-Host "Vigilando logs\faulthandler.log -- deja esta ventana abierta mientras pruebas la app." -ForegroundColor Cyan
Get-Content (Join-Path $PSScriptRoot "..\logs\faulthandler.log") -Wait -Tail 0 -Encoding UTF8
