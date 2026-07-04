"""
Patrón Repository (independiente de framework).

Define la interfaz de acceso a datos normalizados y a errores de
validación. `InMemoryTransactionRepository` se usa en pruebas unitarias y
en modo standalone (sin Django). `django_project/transactions/repository.py`
implementa la misma interfaz sobre el ORM de Django, de modo que la capa
de negocio (`core.normalizer`) nunca depende directamente de Django.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from core.schema import CanonicalTransaction, ValidationErrorRecord


class AbstractTransactionRepository(ABC):
    @abstractmethod
    def save_many(self, transactions: list[CanonicalTransaction]) -> None:
        ...

    @abstractmethod
    def list(self, filters: dict | None = None) -> list[CanonicalTransaction]:
        ...


class AbstractErrorRepository(ABC):
    @abstractmethod
    def save_many(self, errors: list[ValidationErrorRecord]) -> None:
        ...

    @abstractmethod
    def list(self) -> list[ValidationErrorRecord]:
        ...


class InMemoryTransactionRepository(AbstractTransactionRepository):
    def __init__(self):
        self._data: list[CanonicalTransaction] = []

    def save_many(self, transactions: list[CanonicalTransaction]) -> None:
        self._data.extend(transactions)

    def list(self, filters: dict | None = None) -> list[CanonicalTransaction]:
        results = self._data
        if not filters:
            return list(results)

        status = filters.get("status")
        currency = filters.get("currency")
        amount_min = filters.get("amount_min")
        amount_max = filters.get("amount_max")
        date_from = filters.get("date_from")
        date_to = filters.get("date_to")

        def keep(tx: CanonicalTransaction) -> bool:
            if status and tx.status != status:
                return False
            if currency and tx.currency != currency:
                return False
            if amount_min is not None and tx.amount < amount_min:
                return False
            if amount_max is not None and tx.amount > amount_max:
                return False
            if date_from and tx.timestamp < date_from:
                return False
            if date_to and tx.timestamp > date_to:
                return False
            return True

        return [tx for tx in results if keep(tx)]


class InMemoryErrorRepository(AbstractErrorRepository):
    def __init__(self):
        self._data: list[ValidationErrorRecord] = []

    def save_many(self, errors: list[ValidationErrorRecord]) -> None:
        self._data.extend(errors)

    def list(self) -> list[ValidationErrorRecord]:
        return list(self._data)
