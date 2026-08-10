"""
IOC v2 · IdentityValidationEngine (Parte 1.9) — motor de validación INDEPENDIENTE (no se mezclan
validaciones dentro de los servicios). Se apoya en `IdentityResolver`/`IdentityRepository`. Devuelve
un resultado ESTRUCTURADO (`IdentityValidationResult`: errores/avisos/bloqueantes/informativos).
Reutilizable por Workflow/Scheduler/SOMA/Documentos/API/Importadores sin duplicar lógica. Publica
`identidad.validada`. No accede a la BD directamente ni a módulos funcionales.
"""

import logging
from dataclasses import asdict, dataclass, field

from src.services.identidad import _base as B
from src.services.identidad.repository import repository
from src.services.identidad.resolver import resolver
from src.services.identidad.tipos import (
    ESTADOS_GOBIERNO, NIVELES, TIPOS_CENTRO, TRANSICIONES_GOBIERNO,
)

logger = logging.getLogger("identidad.validation")


@dataclass
class IdentityValidationResult:
    valido: bool = True
    bloqueantes: list = field(default_factory=list)
    errores: list = field(default_factory=list)
    avisos: list = field(default_factory=list)
    informativos: list = field(default_factory=list)

    def add(self, nivel, codigo, mensaje):
        item = {"codigo": codigo, "mensaje": mensaje}
        if nivel == "bloqueante":
            self.bloqueantes.append(item); self.valido = False
        elif nivel == "error":
            self.errores.append(item); self.valido = False
        elif nivel == "aviso":
            self.avisos.append(item)
        else:
            self.informativos.append(item)

    def to_dict(self) -> dict:
        return asdict(self)


class IdentityValidationEngine:
    def __init__(self):
        self._repo = repository()
        self._resolver = resolver()

    def validar_centro(self, id_centro, *, id_empresa=None) -> IdentityValidationResult:
        emp = B.emp(id_empresa)
        r = IdentityValidationResult()
        centro = self._repo.get_centro(id_centro, id_empresa=emp)
        # UUID / existencia
        if not centro:
            r.add("bloqueante", "UUID_INEXISTENTE", f"No existe centro {id_centro}")
            self._publicar(emp, id_centro, r)
            return r
        # Empresa
        if not centro.get("id_empresa"):
            r.add("error", "SIN_EMPRESA", "El centro no tiene empresa propietaria")
        # Tipo
        if (centro.get("tipo") or "OTRO") not in TIPOS_CENTRO:
            r.add("aviso", "TIPO_DESCONOCIDO", f"Tipo no catalogado: {centro.get('tipo')}")
        # Nivel
        if (centro.get("nivel") or "CENTRO") not in NIVELES:
            r.add("error", "NIVEL_INVALIDO", f"Nivel inválido: {centro.get('nivel')}")
        # Estado de gobierno
        est = centro.get("estado_gobierno") or "ACTIVO"
        if est not in ESTADOS_GOBIERNO:
            r.add("error", "ESTADO_INVALIDO", f"Estado no oficial: {est}")
        if est in ("ARCHIVADO", "ELIMINACION_PENDIENTE", "HISTORICO"):
            r.add("informativo", "CENTRO_NO_OPERATIVO", f"Centro en estado {est}")
        # Jerarquía: padre existente y sin ciclos
        padre = centro.get("id_centro_padre")
        if padre:
            if padre == id_centro:
                r.add("bloqueante", "CICLO_JERARQUIA", "El centro es su propio padre")
            elif not self._repo.get_centro(padre, id_empresa=emp):
                r.add("error", "PADRE_INEXISTENTE", f"Centro padre inexistente: {padre}")
            else:
                # Detección de ciclo ascendente.
                asc = {n.get("id") for n in self._repo.get_ascendentes(id_centro, id_empresa=emp)}
                if list(asc).count(id_centro) > 1:
                    r.add("bloqueante", "CICLO_JERARQUIA", "Ciclo detectado en la cadena ascendente")
        # Referencia cruzada de empresa con el padre
        if padre:
            p = self._repo.get_centro(padre, id_empresa=emp)
            if p and p.get("id_empresa") and centro.get("id_empresa") and \
               p["id_empresa"] != centro["id_empresa"]:
                r.add("bloqueante", "CRUCE_EMPRESA", "El padre pertenece a otra empresa")
        self._publicar(emp, id_centro, r)
        return r

    def validar_transicion(self, estado_actual, nuevo_estado) -> IdentityValidationResult:
        r = IdentityValidationResult()
        if nuevo_estado not in ESTADOS_GOBIERNO:
            r.add("error", "ESTADO_INVALIDO", f"Estado destino no oficial: {nuevo_estado}")
            return r
        permitidas = TRANSICIONES_GOBIERNO.get(estado_actual, ())
        if nuevo_estado != estado_actual and nuevo_estado not in permitidas:
            r.add("bloqueante", "TRANSICION_INVALIDA",
                  f"{estado_actual}→{nuevo_estado} no permitida")
        return r

    def validar_codigos(self, id_centro, *, id_empresa=None) -> IdentityValidationResult:
        """Detecta duplicados de código operativo dentro de la misma empresa (mismo tipo/valor)."""
        emp = B.emp(id_empresa)
        r = IdentityValidationResult()
        codigos = self._repo.get_codigos(id_centro)
        for tipo_cod, valor in codigos.items():
            otro = self._repo.buscar_por_codigo(tipo_cod, valor, id_empresa=emp)
            if otro and otro.get("id_centro") and otro["id_centro"] != id_centro:
                r.add("error", "CODIGO_DUPLICADO",
                      f"Código {tipo_cod}={valor} ya usado por {otro['id_centro']}")
        return r

    def validar_terminal(self, id_terminal, *, id_empresa=None) -> IdentityValidationResult:
        emp = B.emp(id_empresa)
        r = IdentityValidationResult()
        t = self._repo.get_terminal(id_terminal, id_empresa=emp)
        if not t:
            r.add("bloqueante", "TERMINAL_INEXISTENTE", f"Terminal {id_terminal} no existe")
            return r
        if t.get("id_centro") and not self._repo.get_centro(t["id_centro"], id_empresa=emp):
            r.add("error", "TERMINAL_SIN_CENTRO", "El centro asignado al terminal no existe")
        return r

    def validar_contexto(self, ctx, *, id_empresa=None) -> IdentityValidationResult:
        """Valida un IdentityContext completo (consistencia de la cadena resuelta)."""
        emp = B.emp(id_empresa)
        r = IdentityValidationResult()
        d = ctx.to_dict() if hasattr(ctx, "to_dict") else dict(ctx)
        if not d.get("id_empresa"):
            r.add("bloqueante", "CONTEXTO_SIN_EMPRESA", "Contexto sin empresa")
        if d.get("id_centro") and not d.get("centro"):
            r.add("error", "CENTRO_NO_RESUELTO", "id_centro sin datos de centro")
        if d.get("id_terminal") and not d.get("terminal"):
            r.add("aviso", "TERMINAL_NO_RESUELTO", "id_terminal sin datos de terminal")
        return r

    def _publicar(self, id_empresa, ref_id, resultado):
        try:
            from src.services import eventos
            eventos.publicar("identidad.validada", id_empresa=id_empresa, ref_entidad="identidad",
                             ref_id=ref_id, payload={"valido": resultado.valido,
                             "bloqueantes": len(resultado.bloqueantes), "errores": len(resultado.errores)})
        except Exception:
            pass


_ENGINE = IdentityValidationEngine()


def validation_engine() -> IdentityValidationEngine:
    return _ENGINE
