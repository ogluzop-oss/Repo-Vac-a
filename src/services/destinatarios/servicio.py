"""
Servicio Corporativo de Resolución de Destinatarios — PUNTO ÚNICO oficial (restricción 1).

`buscar_destinatarios(id_empresa, texto, contexto, usuario, limite)` es la API central: localiza,
clasifica, deduplica y ORDENA destinatarios a partir de todas las fuentes registradas + el histórico
de aprendizaje, respetando multiempresa de forma estricta. Devuelve SIEMPRE objetos `Destinatario`
enriquecidos (nunca cadenas), reutilizables por Correo, WhatsApp, SMS, push, IA, Bots, Firma…

Orden inteligente (Partes G/H/I/J/Q): favorito > frecuencia/reciente > coincidencia exacta > parcial
> contexto de módulo. Nunca solo alfabético.

Punto de extensión para POLÍTICAS corporativas futuras (Parte / restricción 6): listas negras/blancas,
consentimiento, preferencias, prioridades, canales… se registran como pipeline no-op ahora.

Núcleo agnóstico de framework (sin PyQt, sin importar el módulo Correo).
"""

import logging

import src.services.destinatarios.fuentes as _fuentes
import src.services.destinatarios.fuzzy as _fuzzy
import src.services.destinatarios.historico as _hist
from src.services.destinatarios.modelo import Destinatario, TIPO_HISTORICO

logger = logging.getLogger("destinatarios.servicio")

# Pesos del orden inteligente.
_PESO_FUZZY = 1.0
_BOOST_FAVORITO = 0.6
_BOOST_CONTEXTO = 0.28
_BOOST_FREC_MAX = 0.35
_BASE_SIN_TEXTO = 0.4        # base neutra cuando no se ha escrito nada (muestra favoritos/recientes)


def _empresa(id_empresa):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def _candidatos_historico(id_empresa, id_usuario) -> list:
    """Destinatarios del histórico (incluye correos que NO pertenecen al ERP) — Parte D."""
    out = []
    for h in _hist.listar_historico(id_empresa, id_usuario):
        out.append(Destinatario(
            correo=h.get("correo") or "",
            nombre_mostrado=h.get("nombre_mostrado") or h.get("correo") or "",
            tipo=TIPO_HISTORICO,
            id_empresa=id_empresa,
            modulo_origen="historico",
            reciente=True,
            num_envios=int(h.get("num_envios") or 0),
            extra={"_busqueda": [h.get("nombre_mostrado") or "", h.get("correo") or ""],
                   "modulo_contexto": h.get("modulo_contexto")},
        ))
    return out


def _fundir(a: Destinatario, b: Destinatario) -> Destinatario:
    """Funde dos candidatos con el mismo correo (Parte L/dedup). Prefiere el que tiene identidad de
    ERP (no histórico); combina avisos y conserva frecuencia/reciente."""
    principal, otro = (a, b)
    if a.tipo == TIPO_HISTORICO and b.tipo != TIPO_HISTORICO:
        principal, otro = b, a
    principal.reciente = principal.reciente or otro.reciente
    principal.num_envios = max(principal.num_envios, otro.num_envios)
    for av in otro.avisos:
        if av not in principal.avisos:
            principal.avisos.append(av)
    if not principal.nombre_mostrado and otro.nombre_mostrado:
        principal.nombre_mostrado = otro.nombre_mostrado
    # Conserva señales de búsqueda de ambos.
    bs = list(principal.extra.get("_busqueda", [])) + list(otro.extra.get("_busqueda", []))
    principal.extra["_busqueda"] = bs
    return principal


def buscar_destinatarios(id_empresa=None, texto="", *, contexto=None, usuario=None,
                         limite=25) -> list:
    """Resuelve destinatarios. `id_empresa` OBLIGATORIO (se toma del contexto si no se pasa); sin
    empresa no se devuelve nada (multiempresa estricto). `contexto` = módulo desde el que se redacta
    (prioriza fuentes afines sin ocultar el resto). Devuelve List[Destinatario] ordenada."""
    id_empresa = _empresa(id_empresa)
    if not id_empresa:
        return []
    texto = (texto or "").strip()

    # 1) Recolecta candidatos de TODAS las fuentes (cada una filtra por id_empresa) + histórico.
    candidatos = []
    for f in _fuentes.fuentes():
        try:
            candidatos.extend(f.buscar(id_empresa, texto, limite=limite))
        except Exception as e:
            logger.debug("fuente %s falló: %s", getattr(f, "clave", "?"), e)
    candidatos.extend(_candidatos_historico(id_empresa, usuario))

    # 2) Deduplica por correo (multiempresa ya garantizado en cada fuente).
    unicos: dict = {}
    for c in candidatos:
        if not c.clave or "@" not in c.clave:
            continue
        unicos[c.clave] = _fundir(unicos[c.clave], c) if c.clave in unicos else c

    # 3) Anota favoritos del usuario (Parte I).
    favs = {f["correo"] for f in _hist.listar_favoritos(id_empresa, usuario)}

    # 4) Puntúa (fuzzy + boosts) y filtra por coincidencia si hay texto.
    ctx = (contexto or "").strip().lower()
    resultado = []
    for c in unicos.values():
        c.favorito = c.clave in favs
        campos = list(c.extra.get("_busqueda", [])) or [c.nombre_mostrado, c.correo]
        s_fuzzy = _fuzzy.puntuar(texto, *campos) if texto else _BASE_SIN_TEXTO
        if texto and s_fuzzy <= 0 and not c.favorito:
            continue   # con texto, descarta lo que no casa (salvo favorito explícito)
        score = _PESO_FUZZY * s_fuzzy
        if c.favorito:
            score += _BOOST_FAVORITO
        if c.num_envios > 0:
            # frecuencia con rendimientos decrecientes (aprendizaje, Parte Q).
            score += min(_BOOST_FREC_MAX, 0.08 * (1 + c.num_envios) ** 0.5)
        if ctx:
            fte = _fuentes.fuente(c.modulo_origen)
            if fte is not None and ctx in getattr(fte, "contextos", ()):
                score += _BOOST_CONTEXTO
        c.score = round(score, 4)
        resultado.append(c)

    # 5) Orden inteligente: score desc, luego nombre (nunca solo alfabético).
    resultado.sort(key=lambda d: (-d.score, (d.nombre_mostrado or d.correo).lower()))

    # 6) Pipeline de POLÍTICAS corporativas (no-op por defecto; restricción 6).
    resultado = _aplicar_politicas(resultado, id_empresa=id_empresa, contexto=contexto,
                                   usuario=usuario)

    return resultado[: int(limite)] if limite else resultado


# ── Resolución documental (Parte N / restricción 5) ──────────────────────────
def resolver_para_documento(*, id_empresa=None, contexto=None, correo=None, nombre=None,
                            nif=None, tipo=None, usuario=None) -> Destinatario | None:
    """Resuelve AUTOMÁTICAMENTE el destinatario de un documento (factura→cliente, pedido→proveedor,
    nómina/contrato→empleado…) usando EXCLUSIVAMENTE este servicio. Ningún módulo documental debe
    localizar destinatarios por su cuenta. Devuelve el mejor `Destinatario` (enriquecido) o None.

    Pistas admitidas (se usan por orden de precisión): `correo` directo → `nif` → `nombre`.
    `tipo` (opcional) restringe al tipo esperado (p. ej. 'cliente'). Multiempresa estricto."""
    id_empresa = _empresa(id_empresa)
    if not id_empresa:
        return None
    # 1) Correo directo: enriquece si existe en el ERP; si no, lo envuelve como destinatario válido.
    if correo and "@" in correo:
        clave = correo.strip().lower()
        for d in buscar_destinatarios(id_empresa, correo, contexto=contexto, usuario=usuario,
                                      limite=8):
            if d.clave == clave:
                return d
        return Destinatario(correo=correo.strip(), nombre_mostrado=(nombre or correo),
                            id_empresa=id_empresa, modulo_origen="documento")
    # 2) Búsqueda por identificador (nif) y luego por nombre; filtra por tipo si se indica.
    for pista in (nif, nombre):
        if not pista:
            continue
        res = buscar_destinatarios(id_empresa, str(pista), contexto=contexto, usuario=usuario,
                                   limite=10)
        if tipo:
            res = [d for d in res if d.tipo == tipo] or res
        if res:
            return res[0]
    return None


# ── Aprendizaje / favoritos (reexport API) ────────────────────────────────────
def registrar_envio(correo, nombre_mostrado=None, *, id_empresa=None, usuario=None,
                    contexto=None) -> bool:
    """Registra un envío para aprendizaje (Parte D/Q). Lo llaman los canales tras enviar OK."""
    return _hist.registrar_envio(correo, nombre_mostrado, id_empresa=id_empresa,
                                 id_usuario=usuario, modulo_contexto=contexto)


def marcar_favorito(correo, nombre_mostrado=None, tipo=None, *, id_empresa=None, usuario=None):
    return _hist.marcar_favorito(correo, nombre_mostrado, tipo, id_empresa=id_empresa,
                                 id_usuario=usuario)


def quitar_favorito(correo, *, id_empresa=None, usuario=None):
    return _hist.quitar_favorito(correo, id_empresa=id_empresa, id_usuario=usuario)


# ── Políticas corporativas de comunicación (extensión futura; hoy no-op) ──────
_POLITICAS: list = []


def registrar_politica(fn):
    """Registra una política que post-procesa (filtra/anota) la lista de destinatarios. Firma:
    fn(lista, *, id_empresa, contexto, usuario) -> lista. Base para listas negras/blancas,
    consentimiento, preferencias, prioridades y canales (restricción 6). No se activa ninguna aún."""
    _POLITICAS.append(fn)
    return fn


def _aplicar_politicas(lista, **ctx):
    for fn in _POLITICAS:
        try:
            lista = fn(lista, **ctx) or lista
        except Exception as e:
            logger.debug("política falló: %s", e)
    return lista
