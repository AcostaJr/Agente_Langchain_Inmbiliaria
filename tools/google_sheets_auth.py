"""
Autenticación compartida para las tools de Google Sheets.

Prioridad de credenciales (la primera disponible gana):
  1) GOOGLE_SHEETS_SERVICE_ACCOUNT_KEY → contenido JSON de la clave del service
     account inyectado como variable de entorno. Recomendado para despliegues
     (EasyPanel, Docker, etc.): evita montar/hornear el archivo. Acepta el JSON
     directo o codificado en base64 (útil si el panel maneja mal saltos de línea).
  2) GOOGLE_SHEETS_CREDENTIALS_FILE → ruta a la clave JSON en disco. Fallback
     cómodo para desarrollo local.

Solo lectura (scope spreadsheets.readonly). Se valida la fuente de credenciales
al importar (fallo temprano, RNF-03); la conexión a Google se abre en la primera
consulta (cliente perezoso en cada tool).

Autor: Ing. Kevin Inofuente Colque - DataPath
"""

import base64
import json
import os

from dotenv import load_dotenv, find_dotenv
import gspread

load_dotenv(find_dotenv())

# Raíz del proyecto (este archivo vive en tools/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Solo lectura: el agente nunca modifica las hojas
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

_SERVICE_ACCOUNT_KEY = os.getenv("GOOGLE_SHEETS_SERVICE_ACCOUNT_KEY", "").strip()
_CREDENTIALS_FILE = os.getenv(
    "GOOGLE_SHEETS_CREDENTIALS_FILE", "credentials/google-service-account.json"
)
# Ruta de la clave JSON resuelta contra la raíz del proyecto (portable)
if not os.path.isabs(_CREDENTIALS_FILE):
    _CREDENTIALS_FILE = os.path.join(BASE_DIR, _CREDENTIALS_FILE)


def _parse_service_account_key(raw: str) -> dict:
    """Convierte el valor de la env var en el dict de credenciales.
    Acepta JSON directo o JSON codificado en base64."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        try:
            return json.loads(base64.b64decode(raw).decode("utf-8"))
        except Exception as e:
            raise ValueError(
                "❌ GOOGLE_SHEETS_SERVICE_ACCOUNT_KEY no es un JSON válido "
                "(ni JSON directo ni base64). Pega el contenido COMPLETO de la "
                "clave del service account (el archivo .json)."
            ) from e


# ============================================
# VALIDACIÓN TEMPRANA (RNF-03): debe existir al menos una fuente de credenciales
# ============================================
if _SERVICE_ACCOUNT_KEY:
    _SERVICE_ACCOUNT_INFO = _parse_service_account_key(_SERVICE_ACCOUNT_KEY)
elif os.path.exists(_CREDENTIALS_FILE):
    _SERVICE_ACCOUNT_INFO = None  # se usará el archivo en disco
else:
    raise ValueError(
        "❌ Faltan credenciales de Google Sheets.\n"
        "Define GOOGLE_SHEETS_SERVICE_ACCOUNT_KEY (contenido JSON de la clave del "
        "service account) en las variables de entorno, o coloca el archivo en\n"
        f"{_CREDENTIALS_FILE} (configurable con GOOGLE_SHEETS_CREDENTIALS_FILE)."
    )


def get_client() -> gspread.Client:
    """Devuelve un cliente gspread autenticado (solo lectura).
    Usa GOOGLE_SHEETS_SERVICE_ACCOUNT_KEY si está definida; si no, la clave JSON
    en disco."""
    if _SERVICE_ACCOUNT_INFO is not None:
        return gspread.service_account_from_dict(_SERVICE_ACCOUNT_INFO, scopes=SCOPES)
    return gspread.service_account(filename=_CREDENTIALS_FILE, scopes=SCOPES)
