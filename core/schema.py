"""
Esquema canónico al que se normalizan todas las transacciones,
independientemente de su fuente/estructura original.

Definido a partir de `image.png` (File 3):

    {
      "id": "string",
      "amount": 99.99,
      "currency": "USD",
      "timestamp": "ISO-8601",
      "status": "SUCCESS | FAILED | PENDING",
      "source": "string"
    }
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum


class CanonicalStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PENDING = "PENDING"


class SourceVariant(str, Enum):
    """Identifica el sistema/estructura de origen detectado."""

    VARIANT_1 = "variant_1"  # id / amount(str) / currency / timestamp / status
    VARIANT_2 = "variant_2"  # transaction_id / total(int, cents) / currency_code / created_at / state
    VARIANT_3 = "variant_3"  # ref / amount(str symbol+coma) / date(ISO) / result
    UNKNOWN = "unknown"


@dataclass
class CanonicalTransaction:
    """Representación normalizada (esquema canónico) de una transacción."""

    id: str
    amount: float
    currency: str
    timestamp: str  # ISO-8601 UTC, formato YYYY-MM-DDTHH:MM:SSZ
    status: str  # uno de CanonicalStatus
    source: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ValidationErrorRecord:
    """Registro detallado de un error de validación/transformación."""

    raw_record: dict
    source: str
    error_type: str
    field: str | None
    value: object
    reason: str

    def to_dict(self) -> dict:
        return {
            "raw_record": self.raw_record,
            "source": self.source,
            "error_type": self.error_type,
            "field": self.field,
            "value": self.value,
            "reason": self.reason,
        }


@dataclass
class ProcessingMetrics:
    """Métricas consolidadas de una corrida de normalización."""

    total_processed: int = 0
    total_valid: int = 0
    total_invalid: int = 0
    status_counts: dict = field(default_factory=lambda: {s.value: 0 for s in CanonicalStatus})
    currency_totals: dict = field(default_factory=dict)
    error_type_counts: dict = field(default_factory=dict)
    source_counts: dict = field(default_factory=dict)

    def register_valid(self, tx: CanonicalTransaction) -> None:
        self.total_valid += 1
        self.status_counts[tx.status] = self.status_counts.get(tx.status, 0) + 1
        self.currency_totals[tx.currency] = round(
            self.currency_totals.get(tx.currency, 0.0) + tx.amount, 2
        )
        self.source_counts[tx.source] = self.source_counts.get(tx.source, 0) + 1

    def register_invalid(self, error_type: str) -> None:
        self.total_invalid += 1
        self.error_type_counts[error_type] = self.error_type_counts.get(error_type, 0) + 1

    def to_dict(self) -> dict:
        return {
            "total_processed": self.total_processed,
            "total_valid": self.total_valid,
            "total_invalid": self.total_invalid,
            "status_counts": self.status_counts,
            "currency_totals": self.currency_totals,
            "error_type_counts": self.error_type_counts,
            "source_counts": self.source_counts,
        }
