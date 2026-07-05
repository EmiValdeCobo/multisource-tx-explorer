"""
Cargador de configuración desde `rules.json`.

Lee el archivo una sola vez al importar el módulo (singleton de módulo).
Las claves se exponen como constantes tipadas que reemplazan los dicts
hardcodeados en `core/transformers.py`.

Para recargar la config en caliente durante pruebas, llama a `reload_config()`.
"""
from __future__ import annotations

import json
from pathlib import Path

from core.logging_config import logger

# Ruta relativa a la raíz del proyecto (un nivel arriba de core/)
_CONFIG_PATH = Path(__file__).resolve().parent.parent / "rules.json"


def _load() -> dict:
    try:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            raw = json.load(f)
        logger.info("Configuración cargada desde %s", _CONFIG_PATH)
        return raw
    except FileNotFoundError:
        logger.error("rules.json no encontrado en %s — se usarán valores por defecto vacíos", _CONFIG_PATH)
        return {}
    except json.JSONDecodeError as exc:
        logger.error("rules.json contiene JSON inválido: %s — se usarán valores por defecto vacíos", exc)
        return {}


_raw: dict = _load()


# ---------------------------------------------------------------------------
# Accesores públicos (todos retornan copias para evitar mutación accidental)
# ---------------------------------------------------------------------------

def get_status_map() -> dict[str, str]:
    """Devuelve {valor_crudo_lower: 'SUCCESS'|'FAILED'|'PENDING'}."""
    raw = _raw.get("status_mappings", {})
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def get_supported_currencies() -> set[str]:
    """Devuelve el conjunto de códigos ISO 4217 aceptados."""
    codes = _raw.get("currencies", {}).get("supported_codes", [])
    return set(codes)


def get_currency_symbol_map() -> dict[str, str]:
    """Devuelve {símbolo: código_ISO}."""
    raw = _raw.get("currencies", {}).get("symbol_map", {})
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def get_date_formats(variant: str) -> list[str]:
    """Devuelve la lista de formatos strptime para una variante dada."""
    section = _raw.get("date_formats", {}).get(variant, {})
    return list(section.get("formats", []))


def get_validation_rules() -> dict:
    """Devuelve las reglas de validación de negocio."""
    return dict(_raw.get("validation_rules", {}))


def get_max_upload_mb() -> int:
    return _raw.get("validation_rules", {}).get("upload", {}).get("max_file_size_mb", 10)


def reload_config() -> None:
    """Recarga rules.json en memoria (útil en tests y hot-reload manual)."""
    global _raw
    _raw = _load()
    logger.info("Configuración recargada.")
