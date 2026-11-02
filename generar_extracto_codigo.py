#!/usr/bin/env python3
"""
Genera EXTRACTO_CODIGO_SMART_MANAGER.pdf a partir de los ficheros indicados en el apartado 4.2
(secciones A, B y C) de MEMORIA_TECNICA_REGISTRO_PI.md, para su depósito ante el Registro de la
Propiedad Intelectual (Derechos de Autor).

Uso:
    python generar_extracto_codigo.py
    python generar_extracto_codigo.py --force   # incluye igualmente los ficheros con avisos NO
                                                 # críticos, tras haberlos revisado a mano

Antes de generar una sola página, el script LEE y ESCANEA todos los ficheros en busca de posibles
credenciales/claves/tokens embebidos (ver `escanear_credenciales`). Si encuentra algo, no genera el
PDF (salvo avisos no críticos con --force) — es preferible que el script se detenga a que un secreto
real acabe en un documento depositado públicamente.
"""

import argparse
import os
import re
import sys

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

# ── Configuración general ───────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(ROOT, "EXTRACTO_CODIGO_SMART_MANAGER.pdf")

# Requisito 1: la obra se nombra EXCLUSIVAMENTE como "Smart Manager" (nunca "Smart Manager AI").
TITULO_OBRA = "Smart Manager"
AUTOR = "Mohamed Assbai Ahammar"
FECHA_PORTADA = "Septiembre 2026"

FUENTE_CODIGO = "Courier"
TAMANO_CODIGO = 9              # 8-9pt según requisito 3
INTERLINEA_CODIGO = TAMANO_CODIGO * 1.25
FUENTE_UI = "Helvetica"

ANCHO_PAGINA, ALTO_PAGINA = A4
MARGEN_IZQ, MARGEN_DER = 20 * mm, 15 * mm
MARGEN_SUP, MARGEN_INF = 22 * mm, 18 * mm
ANCHO_UTIL = ANCHO_PAGINA - MARGEN_IZQ - MARGEN_DER
ALTO_UTIL_SUP = ALTO_PAGINA - MARGEN_SUP    # techo del área de contenido (bajo la cabecera)
Y_MIN = MARGEN_INF                          # suelo del área de contenido (sobre el pie)

# Courier es monoespaciada con avance de carácter exacto 0.6·tamaño en las métricas de reportlab.
CAR_POR_LINEA = max(20, int(ANCHO_UTIL / (TAMANO_CODIGO * 0.6)))

# Apartado 4.2 de la Memoria Técnica — secciones A, B y C (rutas relativas a la raíz del repo).
SECCIONES = [
    ("A", "Arranque y arquitectura núcleo", [
        "src/main.py",
        "src/db/conexion.py",
        "src/services/autorizacion.py",
        "src/services/seguridad/catalogo.py",
        "src/services/seguridad/modulos_menu.py",
        "src/services/seguridad/pestanas_app.py",
    ]),
    ("B", "Núcleo: algoritmos propios", [
        "src/services/seguridad/mfa.py",
        "src/services/fiscal/emisores/verifactu_aeat.py",
        "src/soma/kernel.py",
        "src/services/prediccion/heuristicas.py",
    ]),
    ("C", "Profundidad de dominio y cliente móvil", [
        "src/services/mrp/ordenes.py",
        "src/services/gmao/ordenes.py",
        "src/database/migraciones/0001_baseline.py",
        "mobile_client/src/App.tsx",
        "mobile_client/src/navigation/index.tsx",
    ]),
]


# ── Requisito 5: verificación de seguridad (credenciales / claves / tokens) ────────────────────
# "Críticos": nunca se incluyen, con o sin --force (evidencia casi segura de secreto real).
PATRONES_CRITICOS = [
    (re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----"), "bloque de clave privada PEM"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "posible AWS Access Key ID"),
    (re.compile(r"\bASIA[0-9A-Z]{16}\b"), "posible AWS temporary Access Key ID"),
]
# "Sospechosos": asignación literal de algo con pinta de credencial — puede tener falsos positivos
# (p. ej. nombres de variable), así que SÍ se pueden aceptar con --force tras revisión manual.
PATRON_SOSPECHOSO = re.compile(
    r"(?i)\b(api[_-]?key|secret[_-]?key|client[_-]?secret|access[_-]?key|password|passwd|"
    r"private[_-]?key|token)\s*[:=]\s*['\"]([^'\"\s]{6,})['\"]"
)
PLACEHOLDERS_ACEPTABLES = {
    "", "changeme", "change_me", "xxxx", "xxxxxxxx", "your_key_here", "todo", "none",
    "null", "test", "example", "placeholder", "fixme", "tu_clave_aqui", "admin123",
}


def escanear_credenciales(texto):
    """Devuelve (criticos, sospechosos): listas de (num_linea, motivo, fragmento)."""
    criticos, sospechosos = [], []
    for i, linea in enumerate(texto.splitlines(), start=1):
        for patron, motivo in PATRONES_CRITICOS:
            if patron.search(linea):
                criticos.append((i, motivo, linea.strip()[:120]))
        m = PATRON_SOSPECHOSO.search(linea)
        if m:
            valor = m.group(2).strip().lower()
            # Lectura desde variable de entorno / configuración externa: no es un secreto embebido.
            si_env = any(s in linea for s in ("os.environ", "os.getenv", "process.env", "getenv("))
            if valor not in PLACEHOLDERS_ACEPTABLES and not si_env:
                sospechosos.append((i, "posible credencial/token embebido", linea.strip()[:120]))
    return criticos, sospechosos


def cargar_ficheros():
    """Lee todos los ficheros de SECCIONES. Devuelve lista de dicts {seccion, titulo_seccion, ruta,
    texto} y aborta con un listado claro si falta alguno."""
    faltantes = []
    resultado = []
    for clave, titulo, rutas in SECCIONES:
        for rel in rutas:
            abs_path = os.path.join(ROOT, rel.replace("/", os.sep))
            if not os.path.isfile(abs_path):
                faltantes.append(rel)
                continue
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                texto = f.read()
            resultado.append({"seccion": clave, "titulo_seccion": titulo, "ruta": rel, "texto": texto})
    if faltantes:
        print("ERROR: no se han encontrado estos ficheros del apartado 4.2:")
        for r in faltantes:
            print(f"  - {r}")
        sys.exit(1)
    return resultado


def verificar_seguridad(ficheros, forzar):
    """Escanea todos los ficheros. Aborta si hay hallazgos críticos; aborta si hay sospechosos y
    no se pasó --force. Devuelve tranquilamente si todo está limpio."""
    hay_criticos = False
    hay_sospechosos = False
    for f in ficheros:
        criticos, sospechosos = escanear_credenciales(f["texto"])
        if criticos:
            hay_criticos = True
            print(f"\n[CRÍTICO] {f['ruta']}")
            for num, motivo, frag in criticos:
                print(f"    línea {num}: {motivo} -> {frag}")
        if sospechosos:
            hay_sospechosos = True
            print(f"\n[AVISO] {f['ruta']}")
            for num, motivo, frag in sospechosos:
                print(f"    línea {num}: {motivo} -> {frag}")

    if hay_criticos:
        print("\nSe han detectado posibles secretos CRÍTICOS (claves privadas / AWS access keys).")
        print("No se genera el PDF bajo ninguna circunstancia. Elimina el secreto del fichero fuente")
        print("(o excluye ese fichero del extracto) y vuelve a ejecutar el script.")
        sys.exit(1)

    if hay_sospechosos and not forzar:
        print("\nSe han detectado posibles credenciales/tokens embebidos (ver AVISO arriba).")
        print("Revísalos a mano. Si son falsos positivos (nombres de variable, placeholders, etc.),")
        print("vuelve a ejecutar con --force para generar el PDF de todos modos.")
        sys.exit(1)

    if hay_sospechosos and forzar:
        print("\n--force activo: se generará el PDF pese a los avisos NO críticos anteriores.")

    print("\nVerificación de seguridad: sin hallazgos críticos." + (" (avisos aceptados con --force)" if hay_sospechosos else ""))


# ── Maquetación del PDF ──────────────────────────────────────────────────────
class Maquetador:
    """Escribe el PDF página a página: cabecera (fichero actual) + pie (nº de página) en cada
    página de contenido; la portada no lleva ni cabecera ni numeración."""

    def __init__(self, ruta_salida):
        self.c = canvas.Canvas(ruta_salida, pagesize=A4)
        self.num_pagina = 0          # 0 = portada (sin numerar)
        self.cabecera_texto = ""
        self.y = ALTO_UTIL_SUP

    # -- páginas --------------------------------------------------------
    def portada(self):
        c = self.c
        c.setFont(FUENTE_UI + "-Bold", 22)
        c.drawCentredString(ANCHO_PAGINA / 2, ALTO_PAGINA - 110 * mm,
                            f"Extracto de Código Fuente — {TITULO_OBRA}")
        c.setFont(FUENTE_UI, 13)
        c.drawCentredString(ANCHO_PAGINA / 2, ALTO_PAGINA - 130 * mm, f"Autor: {AUTOR}")
        c.drawCentredString(ANCHO_PAGINA / 2, ALTO_PAGINA - 140 * mm, f"Fecha: {FECHA_PORTADA}")
        c.setFont(FUENTE_UI, 9)
        c.setFillGray(0.45)
        c.drawCentredString(
            ANCHO_PAGINA / 2, ALTO_PAGINA - 160 * mm,
            "Extracto representativo del código fuente para depósito ante el Registro de la "
            "Propiedad Intelectual")
        c.setFillGray(0)
        c.showPage()

    def nueva_pagina_contenido(self):
        self._pie_pagina()
        self.c.showPage()
        self.num_pagina += 1
        self.y = ALTO_UTIL_SUP
        self._cabecera()

    def _cabecera(self):
        c = self.c
        c.setFont(FUENTE_UI, 8)
        c.setFillGray(0.35)
        c.drawString(MARGEN_IZQ, ALTO_PAGINA - MARGEN_SUP + 8 * mm, TITULO_OBRA)
        c.drawRightString(ANCHO_PAGINA - MARGEN_DER, ALTO_PAGINA - MARGEN_SUP + 8 * mm,
                          self.cabecera_texto)
        c.setStrokeGray(0.6)
        c.line(MARGEN_IZQ, ALTO_PAGINA - MARGEN_SUP + 5 * mm,
              ANCHO_PAGINA - MARGEN_DER, ALTO_PAGINA - MARGEN_SUP + 5 * mm)
        c.setFillGray(0)
        c.setStrokeGray(0)

    def _pie_pagina(self):
        if self.num_pagina == 0:
            return
        c = self.c
        c.setFont(FUENTE_UI, 8)
        c.setFillGray(0.35)
        c.drawCentredString(ANCHO_PAGINA / 2, MARGEN_INF - 10 * mm, str(self.num_pagina))
        c.setFillGray(0)

    # -- contenido --------------------------------------------------------
    def establecer_cabecera(self, texto):
        self.cabecera_texto = texto

    def titulo_seccion(self, texto):
        """Título de sección (p. ej. 'SECCIÓN A — Arranque y arquitectura núcleo'), en página
        nueva, antes de empezar a volcar sus ficheros."""
        self.nueva_pagina_contenido()
        c = self.c
        c.setFont(FUENTE_UI + "-Bold", 13)
        c.drawString(MARGEN_IZQ, self.y, texto)
        self.y -= 10 * mm
        c.setStrokeGray(0.7)
        c.line(MARGEN_IZQ, self.y, ANCHO_PAGINA - MARGEN_DER, self.y)
        c.setStrokeGray(0)
        self.y -= 10 * mm

    def titulo_fichero(self, ruta):
        """Línea de encabezado dentro del cuerpo, al empezar cada fichero nuevo."""
        if self.y < Y_MIN + 30 * mm:
            self.nueva_pagina_contenido()
        c = self.c
        c.setFont(FUENTE_UI + "-Bold", 10)
        c.drawString(MARGEN_IZQ, self.y, f"Fichero: {ruta}")
        self.y -= 8 * mm

    def linea_codigo(self, texto):
        if self.y < Y_MIN:
            self.nueva_pagina_contenido()
        self.c.setFont(FUENTE_CODIGO, TAMANO_CODIGO)
        self.c.drawString(MARGEN_IZQ, self.y, texto)
        self.y -= INTERLINEA_CODIGO

    def cerrar(self):
        self._pie_pagina()
        self.c.save()


def envolver_linea(linea, ancho_max):
    """Requisito 3: saltos de línea automáticos. Se expanden tabuladores (equivalencia visual a 4
    espacios) y se trocea en bloques de `ancho_max` caracteres sin reescribir el contenido."""
    linea = linea.rstrip("\n").expandtabs(4)
    if linea == "":
        return [""]
    return [linea[i:i + ancho_max] for i in range(0, len(linea), ancho_max)]


def generar_pdf(ficheros):
    m = Maquetador(SALIDA)
    m.portada()

    seccion_actual = None
    for f in ficheros:
        if f["seccion"] != seccion_actual:
            seccion_actual = f["seccion"]
            m.titulo_seccion(f"SECCIÓN {f['seccion']} — {f['titulo_seccion']}")
        m.establecer_cabecera(f"Sección {f['seccion']} · {f['ruta']}")
        m.titulo_fichero(f["ruta"])
        for linea in f["texto"].splitlines():
            for trozo in envolver_linea(linea, CAR_POR_LINEA):
                m.linea_codigo(trozo)
        m.y -= 6 * mm   # separación entre ficheros

    m.cerrar()


def main():
    ap = argparse.ArgumentParser(description="Genera EXTRACTO_CODIGO_SMART_MANAGER.pdf")
    ap.add_argument("--force", action="store_true",
                    help="incluye los ficheros pese a avisos NO críticos, tras revisarlos a mano")
    args = ap.parse_args()

    ficheros = cargar_ficheros()
    verificar_seguridad(ficheros, args.force)
    generar_pdf(ficheros)
    print(f"\nGenerado: {SALIDA}")


if __name__ == "__main__":
    main()
