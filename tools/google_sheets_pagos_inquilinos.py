"""
Tool: Pago mensual del inquilino (Google Sheets)
Lee la hoja de pagos mensuales del edificio (gastos comunes/mantenimiento por
departamento) usando el mismo Service Account de solo lectura.

DATOS SENSIBLES: el monto que paga un inquilino es información privada. Esta tool
exige AUTENTICACIÓN DE DOS FACTORES antes de revelar nada:
  1) número de departamento (Bloque inmobiliario), y
  2) nombre del titular / responsable de pago.
Ambos deben coincidir con la MISMA fila. Si no coinciden, se niega el acceso y
NUNCA se listan los datos de otros inquilinos.

Estructura de la hoja (importante):
  - Fila 1: grupos de categoría (celdas combinadas → muchas vacías) y, al final,
            las etiquetas de resumen (SubTotal, Total, ...).
  - Fila 2: cabeceras detalladas (Bloque inmobiliario, Responsable de Pago, ...).
  - Filas 3..N: un inquilino por fila (col A = nº de dpto).
  - Última fila: "Total" general (se descarta: col A no es numérica).
La cabecera efectiva se arma combinando fila 2 (preferente) con fila 1 (fallback).

Autor: Ing. Kevin Inofuente Colque - DataPath
"""

import os
import unicodedata

from dotenv import load_dotenv, find_dotenv
from langchain_core.tools import tool

from tools.google_sheets_auth import get_client

load_dotenv(find_dotenv())

# ============================================
# CONFIGURACIÓN DE GOOGLE SHEETS (PAGOS)
# ============================================
SPREADSHEET_ID = os.getenv("GOOGLE_SHEETS_PAGOS_SPREADSHEET_ID")
WORKSHEET_NAME = os.getenv("GOOGLE_SHEETS_PAGOS_WORKSHEET", "")  # vacío = primera hoja

# Filas de cabecera (1-indexadas, como en la UI de Google Sheets)
HEADER_ROW_1 = int(os.getenv("GOOGLE_SHEETS_PAGOS_HEADER_ROW_1", "1"))
HEADER_ROW_2 = int(os.getenv("GOOGLE_SHEETS_PAGOS_HEADER_ROW_2", "2"))

if not SPREADSHEET_ID:
    raise ValueError(
        "❌ Falta GOOGLE_SHEETS_PAGOS_SPREADSHEET_ID en .env\n"
        "Es el ID del Google Sheet de pagos (la parte entre /d/ y /edit de la URL)."
    )

# Etiquetas de columna que forman el desglose de resumen que mostramos al inquilino.
_COLUMNAS_RESUMEN_EXTRA = {"subtotal", "descuentos por saldos"}

# Cliente perezoso: las credenciales se validan al importar (en
# tools.google_sheets_auth); la conexión a Google se abre en la primera consulta.
_client = None


def _get_worksheet():
    """Devuelve la hoja de pagos configurada (autentica en la primera llamada)."""
    global _client
    if _client is None:
        _client = get_client()
    spreadsheet = _client.open_by_key(SPREADSHEET_ID)
    if WORKSHEET_NAME:
        return spreadsheet.worksheet(WORKSHEET_NAME)
    return spreadsheet.sheet1


def _normalizar(texto: str) -> str:
    """Minúsculas, sin acentos y sin espacios extremos (para comparar nombres)."""
    texto = (texto or "").strip().lower()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return " ".join(texto.split())


def _combinar_cabecera(fila1: list, fila2: list) -> list:
    """Cabecera efectiva: valor de la fila 2 y, si está vacío, el de la fila 1."""
    ancho = max(len(fila1), len(fila2))
    fila1 = fila1 + [""] * (ancho - len(fila1))
    fila2 = fila2 + [""] * (ancho - len(fila2))
    return [(c2.strip() or c1.strip()) for c1, c2 in zip(fila1, fila2)]


def _nombre_coincide(nombre_ingresado: str, nombre_registro: str) -> bool:
    """
    True si el nombre ingresado corresponde al del registro.
    Tolerante: acepta nombre parcial (ej. solo apellido) mientras cada palabra
    ingresada aparezca en el nombre registrado. Ignora acentos y mayúsculas.
    """
    ing = _normalizar(nombre_ingresado)
    reg = _normalizar(nombre_registro)
    if not ing or not reg:
        return False
    if ing == reg or ing in reg:
        return True
    palabras_reg = set(reg.split())
    return all(palabra in palabras_reg for palabra in ing.split())


# ============================================
# FUNCIÓN INTERNA DE LECTURA + AUTENTICACIÓN
# ============================================
def _consultar_pago_interno(departamento: str, nombre_inquilino: str) -> str:
    """
    Devuelve el detalle de pago del inquilino SOLO si departamento + nombre
    coinciden con la misma fila. En cualquier otro caso, niega el acceso.
    """
    depto = (departamento or "").strip()
    nombre = (nombre_inquilino or "").strip()

    # Exigir ambos factores
    if not depto or not nombre:
        return (
            "Para consultar tu pago necesito DOS datos por seguridad: "
            "el número de tu departamento y el nombre del titular. "
            "¿Me confirmas ambos?"
        )

    try:
        worksheet = _get_worksheet()
        valores = worksheet.get_all_values()
    except Exception as e:
        return f"Error al consultar los pagos en Google Sheets: {type(e).__name__}: {e}"

    if len(valores) <= HEADER_ROW_2:
        return "La hoja de pagos no tiene datos por el momento."

    cabecera = _combinar_cabecera(valores[HEADER_ROW_1 - 1], valores[HEADER_ROW_2 - 1])
    filas = valores[HEADER_ROW_2:]  # datos: después de la fila de cabecera 2

    # Columna A = departamento (Bloque inmobiliario); Columna B = responsable
    col_depto = 0
    col_nombre = 1

    # 1) Ubicar la fila por número de departamento (identificador único).
    #    Solo filas cuyo dpto es numérico (descarta la fila "Total" final).
    fila_match = None
    depto_norm = depto.lower().lstrip("0") or "0"
    for fila in filas:
        celda = (fila[col_depto] if len(fila) > col_depto else "").strip()
        if not celda.isdigit():
            continue
        if celda.lower().lstrip("0") == depto_norm:
            fila_match = fila
            break

    # 2) Verificar el segundo factor (nombre) sobre esa misma fila.
    #    Mensaje de denegación genérico: no revela qué factor falló ni si el
    #    departamento existe (evita enumeración de inquilinos).
    denegado = (
        "Los datos no coinciden con nuestros registros. Por seguridad, para "
        "consultar tu pago necesito el número de departamento y el nombre del "
        "titular tal como figuran en el contrato. ¿Puedes verificarlos?"
    )
    if fila_match is None:
        return denegado

    responsable = (fila_match[col_nombre] if len(fila_match) > col_nombre else "").strip()
    if not _nombre_coincide(nombre, responsable):
        return denegado

    # 3) Autenticado: armar el desglose de resumen.
    periodo = ""
    try:
        periodo = worksheet.spreadsheet.title  # ej. "Pagos de Abril 2026 - Edificio Rio Sul"
    except Exception:
        pass

    total_col = len(cabecera) - 1  # última columna = Total general
    lineas_resumen = []
    for i, etiqueta in enumerate(cabecera):
        et = etiqueta.strip()
        if not et or i in (col_depto, col_nombre) or i == total_col:
            continue
        et_norm = et.lower()
        es_total_grupo = et_norm.startswith("total")
        es_extra = et_norm in _COLUMNAS_RESUMEN_EXTRA
        if not (es_total_grupo or es_extra):
            continue
        valor = (fila_match[i] if len(fila_match) > i else "").strip()
        if valor:
            lineas_resumen.append(f"- {et}: {valor}")

    total_valor = (fila_match[total_col] if len(fila_match) > total_col else "").strip()

    partes = []
    if periodo:
        partes.append(f"📄 {periodo}")
    partes.append(f"Departamento: {fila_match[col_depto].strip()}")
    partes.append(f"Titular: {responsable}")
    if lineas_resumen:
        partes.append("\nDesglose:")
        partes.extend(lineas_resumen)
    if total_valor:
        partes.append(f"\n💰 TOTAL A PAGAR: {total_valor}")

    return "\n".join(partes)


# ============================================
# TOOL EXPORTABLE
# ============================================
@tool
def consultar_pago_inquilino(departamento: str = "", nombre_inquilino: str = "") -> str:
    """
    Consulta el pago mensual (gastos comunes/mantenimiento) de UN inquilino.

    ⚠️ INFORMACIÓN PRIVADA: el monto de un inquilino es confidencial. Antes de
    llamar a esta herramienta DEBES tener DOS datos que el usuario proporcione:
      - departamento: número del departamento (ej. "101", "604").
      - nombre_inquilino: nombre del titular/responsable de pago.
    Si te falta alguno, PÍDESELO al usuario; no inventes ni asumas valores. La
    herramienta solo revela el pago si ambos coinciden con la misma fila; si no,
    niega el acceso.

    Usa esta herramienta cuando el usuario pregunte por:
    - Cuánto debe pagar este mes / su cuota de gastos comunes o mantenimiento.
    - El desglose de su pago (agua, servicios, administración, etc.).

    NO uses esta herramienta para:
    - Departamentos disponibles para alquilar (usa buscar_departamentos_alquiler).
    - Preguntas sobre políticas o la inmobiliaria (usa buscar_datapath).
    - Consultar el pago de OTRA persona sin sus datos: está prohibido.

    Args:
        departamento: Número de departamento del inquilino (ej. "101").
        nombre_inquilino: Nombre del titular/responsable de pago.
    """
    print(
        f"   🔐 Consultando pago (dpto: '{departamento or '?'}', "
        f"titular: '{nombre_inquilino or '?'}')"
    )
    return _consultar_pago_interno(departamento, nombre_inquilino)
