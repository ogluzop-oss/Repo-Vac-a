"""Adaptador contratos ↔ IOC (Bloque V) — homogéneo (factory). Sobre IdentityAPI."""

from src.services.identidad.adaptador import construir

_A = construir("contratos")

empresa_id = _A.empresa_id
tienda_actual = _A.tienda_actual
almacen_actual = _A.almacen_actual
empresa_tienda_almacen = _A.empresa_tienda_almacen
contexto = _A.contexto
identidad = _A.identidad
telemetria = _A.telemetria
