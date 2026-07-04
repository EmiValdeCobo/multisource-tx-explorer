"""
Excepciones específicas del dominio de normalización de transacciones.

Cada excepción lleva contexto suficiente (fuente, campo, valor) para que
el `ErrorCollector` pueda registrar un motivo detallado sin perder
información sobre dónde y por qué falló el procesamiento.
"""
from __future__ import annotations


class TransactionProcessingError(Exception):
    """Excepción base para cualquier fallo durante el procesamiento de una transacción."""

    def __init__(self, message: str, *, field: str | None = None, value=None, source: str | None = None):
        self.field = field
        self.value = value
        self.source = source
        super().__init__(message)

    def to_dict(self) -> dict:
        return {
            "error_type": self.__class__.__name__,
            "message": str(self),
            "field": self.field,
            "value": self.value,
            "source": self.source,
        }


class VariantDetectionError(TransactionProcessingError):
    """No fue posible determinar a qué variante de estructura pertenece el registro."""


class FieldMappingError(TransactionProcessingError):
    """Un campo requerido no existe o es nulo tras el mapeo de campos."""


class AmountConversionError(TransactionProcessingError):
    """El monto no pudo convertirse a un número válido (o es negativo)."""


class DateParsingError(TransactionProcessingError):
    """La fecha no pudo interpretarse en ninguno de los formatos soportados."""


class CurrencyNormalizationError(TransactionProcessingError):
    """El código/símbolo de moneda no es reconocido."""


class StatusMappingError(TransactionProcessingError):
    """El estado no pudo mapearse al conjunto canónico SUCCESS|FAILED|PENDING."""


class TransactionValidationError(TransactionProcessingError):
    """Fallo genérico de validación de negocio sobre una transacción ya normalizada."""
