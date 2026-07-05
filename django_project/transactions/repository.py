"""
Implementación del patrón Repository sobre el ORM de Django.

Cumple la misma interfaz abstracta que `core.repository`, de modo que la
capa de negocio (`core.normalizer`) permanece agnóstica de Django: solo
esta capa "traduce" `CanonicalTransaction` / `ValidationErrorRecord` en
modelos ORM y viceversa.
"""
from __future__ import annotations

from datetime import datetime, timezone as dt_timezone

from django.db.models import QuerySet

from core.schema import CanonicalTransaction, ValidationErrorRecord
from transactions.models import NormalizedTransaction, ProcessingRun, ValidationErrorLog


class DjangoTransactionRepository:
    """Repositorio de transacciones normalizadas respaldado por Django ORM."""

    def save_many(self, run: ProcessingRun, transactions: list[CanonicalTransaction]) -> None:
        objs = [
            NormalizedTransaction(
                run=run,
                external_id=tx.id,
                amount=tx.amount,
                currency=tx.currency,
                timestamp=datetime.strptime(tx.timestamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt_timezone.utc),
                status=tx.status,
                source=tx.source,
            )
            for tx in transactions
        ]
        NormalizedTransaction.objects.bulk_create(objs)

    def list(self, filters: dict | None = None) -> QuerySet[NormalizedTransaction]:
        qs = NormalizedTransaction.objects.select_related("run").all()
        if not filters:
            return qs

        if status := filters.get("status"):
            qs = qs.filter(status=status)
        if currency := filters.get("currency"):
            qs = qs.filter(currency=currency.upper())
        if amount_min := filters.get("amount_min"):
            qs = qs.filter(amount__gte=amount_min)
        if amount_max := filters.get("amount_max"):
            qs = qs.filter(amount__lte=amount_max)
        if date_from := filters.get("date_from"):
            qs = qs.filter(timestamp__gte=date_from)
        if date_to := filters.get("date_to"):
            qs = qs.filter(timestamp__lte=date_to)
        return qs


class DjangoErrorRepository:
    """Repositorio de errores de validación respaldado por Django ORM."""

    def save_many(self, run: ProcessingRun, errors: list[ValidationErrorRecord]) -> None:
        objs = [
            ValidationErrorLog(
                run=run,
                source=err.source,
                error_type=err.error_type,
                field=err.field,
                value=str(err.value) if err.value is not None else None,
                reason=err.reason,
                raw_record=err.raw_record,
            )
            for err in errors
        ]
        ValidationErrorLog.objects.bulk_create(objs)

    def list(self) -> QuerySet[ValidationErrorLog]:
        return ValidationErrorLog.objects.select_related("run").all()
