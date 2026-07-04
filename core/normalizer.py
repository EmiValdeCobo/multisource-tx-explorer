"""
Orquestador principal del pipeline de normalización.

Flujo por registro:
  1. `VariantDetectorFactory.detect`  -> determina la variante (Factory).
  2. `TransformerFactory.create`      -> obtiene el conjunto de estrategias (Strategy).
  3. `VariantTransformer.transform`   -> produce un dict canónico (o lanza excepción).
  4. `TransactionValidator.validate`  -> segunda pasada de validación de negocio.
  5. Éxito  -> se agrega a la lista de `CanonicalTransaction` válidas.
     Fallo   -> se captura la excepción, se registra en el `ErrorCollector`
                y el procesamiento continúa con el siguiente registro
                (ningún error interrumpe el lote).

Todas las excepciones son capturadas explícitamente: no se descarta
ningún registro en silencio.
"""
from __future__ import annotations

from core.detectors import VariantDetectorFactory
from core.exceptions import TransactionProcessingError
from core.logging_config import logger
from core.schema import (
    CanonicalTransaction,
    ProcessingMetrics,
    SourceVariant,
    ValidationErrorRecord,
)
from core.transformers import TransformerFactory
from core.validators import TransactionValidator


class ErrorCollector:
    """Repositorio en memoria de errores de validación/transformación."""

    def __init__(self):
        self._errors: list[ValidationErrorRecord] = []

    def add(self, raw_record: dict, source: str, exc: TransactionProcessingError) -> None:
        record = ValidationErrorRecord(
            raw_record=raw_record,
            source=source,
            error_type=exc.__class__.__name__,
            field=exc.field,
            value=exc.value if _is_jsonable(exc.value) else str(exc.value),
            reason=str(exc),
        )
        self._errors.append(record)
        logger.warning(
            "Registro inválido | source=%s | tipo=%s | campo=%s | valor=%s | motivo=%s",
            source,
            record.error_type,
            record.field,
            record.value,
            record.reason,
        )

    @property
    def errors(self) -> list[ValidationErrorRecord]:
        return list(self._errors)


def _is_jsonable(value) -> bool:
    return isinstance(value, (str, int, float, bool, type(None)))


class TransactionNormalizer:
    """Punto de entrada de alto nivel del pipeline de normalización."""

    def __init__(self, validator: TransactionValidator | None = None):
        self.validator = validator or TransactionValidator()

    def process_batch(self, raw_records: list[dict]) -> tuple[list[CanonicalTransaction], ErrorCollector, ProcessingMetrics]:
        """Procesa una lista de registros crudos heterogéneos.

        Devuelve (transacciones_validas, coleccion_de_errores, metricas).
        """
        metrics = ProcessingMetrics()
        errors = ErrorCollector()
        valid_transactions: list[CanonicalTransaction] = []

        for raw in raw_records:
            metrics.total_processed += 1
            source = "unknown"
            try:
                variant = VariantDetectorFactory.detect(raw)
                if variant == SourceVariant.UNKNOWN:
                    raise TransactionProcessingError(
                        "No se pudo determinar la variante de estructura del registro",
                        field=None,
                        value=list(raw.keys()),
                        source="unknown",
                    )
                source = variant.value
                transformer = TransformerFactory.create(variant)
                canonical_dict = transformer.transform(raw)
                self.validator.validate(canonical_dict, source)

                tx = CanonicalTransaction(**canonical_dict)
                valid_transactions.append(tx)
                metrics.register_valid(tx)
                logger.info("Transacción normalizada OK | id=%s | source=%s", tx.id, tx.source)

            except TransactionProcessingError as exc:
                exc.source = exc.source or source
                errors.add(raw, source, exc)
                metrics.register_invalid(exc.__class__.__name__)

            except Exception as exc:  # salvaguarda: nunca dejar una excepción sin capturar
                logger.exception("Error inesperado procesando registro: %s", raw)
                wrapped = TransactionProcessingError(f"Error inesperado: {exc}", source=source)
                errors.add(raw, source, wrapped)
                metrics.register_invalid("UnexpectedError")

        return valid_transactions, errors, metrics
