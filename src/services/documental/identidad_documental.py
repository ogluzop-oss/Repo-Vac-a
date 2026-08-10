"""
Adaptador documental ↔ IOC (Bloque III) — punto oficial por el que documental resuelve identidad vía IdentityAPI.
Homogéneo: construido sobre el factory único `identidad.adaptador`. Behavior-preserving (empresa_id con
fallback). No accede a Repository/Cache/SQL. Dirección: documental → IdentityAPI → … → IOC.
"""

from src.services.identidad.adaptador import construir

_A = construir("documental")

empresa_id = _A.empresa_id
tienda_actual = _A.tienda_actual
almacen_actual = _A.almacen_actual
empresa_tienda_almacen = _A.empresa_tienda_almacen
contexto = _A.contexto
identidad = _A.identidad
telemetria = _A.telemetria
