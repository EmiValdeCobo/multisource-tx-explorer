"""
Configuración centralizada de logging para todo el pipeline de normalización.

Cada transformación, validación fallida y excepción capturada se registra
con contexto completo (origen, campo, valor, motivo) para facilitar
auditoría y depuración en producción.
"""
from __future__ import annotations

import logging
import sys

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def get_logger(name: str = "transaction_normalizer", level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(handler)
        logger.setLevel(level)
        logger.propagate = False
    return logger


logger = get_logger()
