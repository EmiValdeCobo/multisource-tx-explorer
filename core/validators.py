"""
Validación de negocio sobre transacciones ya transformadas al esquema
canónico. Se ejecuta como una segunda línea de defensa, después de que
los `Strategy` transformers ya hicieron su propia validación de bajo nivel.
"""
from __future__ import annotations

from datetime import datetime

from core.exceptions import TransactionValidationError
from core.schema import CanonicalStatus


class TransactionValidator:
    """Valida un dict con campos canónicos (id, amount, currency, timestamp, status, source)."""

    REQUIRED_FIELDS = ("id", "amount", "currency", "timestamp", "status", "source")
    VALID_STATUSES = {s.value for s in CanonicalStatus}

    def validate(self, tx: dict, source: str) -> None:
        """Lanza `TransactionValidationError` en el primer problema encontrado."""
        self._check_required_fields(tx, source)
        self._check_amount(tx, source)
        self._check_timestamp(tx, source)
        self._check_status(tx, source)

    def _check_required_fields(self, tx: dict, source: str) -> None:
        for f in self.REQUIRED_FIELDS:
            if tx.get(f) in (None, ""):
                raise TransactionValidationError(
                    f"Campo requerido faltante o vacío tras la normalización: '{f}'",
                    field=f,
                    value=tx.get(f),
                    source=source,
                )

    def _check_amount(self, tx: dict, source: str) -> None:
        amount = tx.get("amount")
        if not isinstance(amount, (int, float)):
            raise TransactionValidationError(
                "El monto normalizado no es numérico", field="amount", value=amount, source=source
            )
        if amount < 0:
            raise TransactionValidationError(
                f"El monto no puede ser negativo: {amount}", field="amount", value=amount, source=source
            )

    def _check_timestamp(self, tx: dict, source: str) -> None:
        ts = tx.get("timestamp")
        try:
            datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
        except (TypeError, ValueError) as exc:
            raise TransactionValidationError(
                f"Timestamp normalizado inválido: '{ts}' ({exc})", field="timestamp", value=ts, source=source
            ) from exc

    def _check_status(self, tx: dict, source: str) -> None:
        status = tx.get("status")
        if status not in self.VALID_STATUSES:
            raise TransactionValidationError(
                f"Estado fuera del conjunto canónico: '{status}'", field="status", value=status, source=source
            )
