"""
Patrón Strategy: cada tipo de campo (monto, moneda, fecha, estado) tiene
una familia de estrategias de transformación intercambiables, seleccionadas
según la variante detectada por `VariantDetectorFactory`.

Todas las operaciones críticas (parseo numérico, parseo de fecha, mapeo de
estado/moneda) están envueltas en try/except explícito y lanzan excepciones
de dominio (`core.exceptions`) con contexto completo.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from core.exceptions import (
    AmountConversionError,
    CurrencyNormalizationError,
    DateParsingError,
    FieldMappingError,
    StatusMappingError,
)
from core.logging_config import logger
from core.schema import CanonicalStatus, SourceVariant

# ---------------------------------------------------------------------------
# Tablas de mapeo (fácilmente extensibles sin tocar la lógica)
# ---------------------------------------------------------------------------

CURRENCY_SYMBOL_MAP = {
    "€": "EUR",
    "$": "USD",
    "£": "GBP",
    "¥": "JPY",
}

KNOWN_ISO_CURRENCIES = {"USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "MXN", "BRL"}

STATUS_MAP = {
    "completed": CanonicalStatus.SUCCESS,
    "success": CanonicalStatus.SUCCESS,
    "ok": CanonicalStatus.SUCCESS,
    "succeeded": CanonicalStatus.SUCCESS,
    "failed": CanonicalStatus.FAILED,
    "failure": CanonicalStatus.FAILED,
    "error": CanonicalStatus.FAILED,
    "pending": CanonicalStatus.PENDING,
    "processing": CanonicalStatus.PENDING,
    "in_progress": CanonicalStatus.PENDING,
}


# ---------------------------------------------------------------------------
# Amount strategies
# ---------------------------------------------------------------------------

class AmountTransformStrategy(ABC):
    @abstractmethod
    def transform(self, raw: dict, source: str) -> float:
        ...


class StringAmountStrategy(AmountTransformStrategy):
    """Variante 1: amount viene como string decimal simple, ej. '100.50'."""

    def transform(self, raw: dict, source: str) -> float:
        value = raw.get("amount")
        if value is None:
            raise FieldMappingError("Campo 'amount' ausente", field="amount", value=value, source=source)
        try:
            amount = float(value)
        except (TypeError, ValueError) as exc:
            raise AmountConversionError(
                f"No se pudo convertir 'amount' a número: {exc}", field="amount", value=value, source=source
            ) from exc
        return amount


class CentsIntegerAmountStrategy(AmountTransformStrategy):
    """Variante 2: total es un entero que representa centavos."""

    def transform(self, raw: dict, source: str) -> float:
        value = raw.get("total")
        if value is None:
            raise FieldMappingError("Campo 'total' ausente", field="total", value=value, source=source)
        try:
            cents = int(value)
        except (TypeError, ValueError) as exc:
            raise AmountConversionError(
                f"No se pudo convertir 'total' a entero: {exc}", field="total", value=value, source=source
            ) from exc
        return round(cents / 100, 2)


class SymbolCommaAmountStrategy(AmountTransformStrategy):
    """Variante 3: amount como '€99,99' o '£75,50' (coma decimal + símbolo)."""

    _NUMBER_RE = re.compile(r"[-+]?\d+(?:[.,]\d+)?")

    def transform(self, raw: dict, source: str) -> float:
        value = raw.get("amount")
        if value is None:
            raise FieldMappingError("Campo 'amount' ausente", field="amount", value=value, source=source)
        match = self._NUMBER_RE.search(str(value))
        if not match:
            raise AmountConversionError(
                f"No se encontró un número válido en '{value}'", field="amount", value=value, source=source
            )
        numeric_str = match.group(0).replace(",", ".")
        try:
            return float(numeric_str)
        except ValueError as exc:
            raise AmountConversionError(
                f"No se pudo convertir '{value}' a número: {exc}", field="amount", value=value, source=source
            ) from exc


# ---------------------------------------------------------------------------
# Currency strategies
# ---------------------------------------------------------------------------

class CurrencyTransformStrategy(ABC):
    @abstractmethod
    def transform(self, raw: dict, source: str) -> str:
        ...


class DirectCodeCurrencyStrategy(CurrencyTransformStrategy):
    """Variantes 1 y 2: código directo en 'currency' o 'currency_code'."""

    def __init__(self, field_name: str):
        self.field_name = field_name

    def transform(self, raw: dict, source: str) -> str:
        value = raw.get(self.field_name)
        if not value:
            raise FieldMappingError(
                f"Campo '{self.field_name}' ausente", field=self.field_name, value=value, source=source
            )
        code = str(value).strip().upper()
        if code not in KNOWN_ISO_CURRENCIES:
            raise CurrencyNormalizationError(
                f"Código de moneda no reconocido: '{value}'", field=self.field_name, value=value, source=source
            )
        return code


class SymbolCurrencyStrategy(CurrencyTransformStrategy):
    """Variante 3: la moneda se infiere del símbolo dentro de 'amount'."""

    def transform(self, raw: dict, source: str) -> str:
        value = raw.get("amount", "")
        for symbol, code in CURRENCY_SYMBOL_MAP.items():
            if symbol in str(value):
                return code
        raise CurrencyNormalizationError(
            f"No se pudo inferir la moneda desde '{value}'", field="amount", value=value, source=source
        )


# ---------------------------------------------------------------------------
# Date strategies
# ---------------------------------------------------------------------------

class DateTransformStrategy(ABC):
    @abstractmethod
    def transform(self, raw: dict, source: str) -> str:
        ...


class StrptimeDateStrategy(DateTransformStrategy):
    """Estrategia genérica basada en un formato strptime concreto."""

    def __init__(self, field_name: str, fmt: str):
        self.field_name = field_name
        self.fmt = fmt

    def transform(self, raw: dict, source: str) -> str:
        value = raw.get(self.field_name)
        if not value:
            raise FieldMappingError(
                f"Campo '{self.field_name}' ausente", field=self.field_name, value=value, source=source
            )
        try:
            dt = datetime.strptime(str(value), self.fmt).replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise DateParsingError(
                f"Formato de fecha inválido para '{value}' (esperado {self.fmt}): {exc}",
                field=self.field_name,
                value=value,
                source=source,
            ) from exc
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class ISO8601DateStrategy(DateTransformStrategy):
    """Variante 3: la fecha ya viene en ISO-8601 (posiblemente con 'Z')."""

    def transform(self, raw: dict, source: str) -> str:
        value = raw.get("date")
        if not value:
            raise FieldMappingError("Campo 'date' ausente", field="date", value=value, source=source)
        normalized = str(value).replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise DateParsingError(
                f"Fecha ISO-8601 inválida: '{value}': {exc}", field="date", value=value, source=source
            ) from exc
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Status strategy (común a todas las variantes: solo cambia el campo origen)
# ---------------------------------------------------------------------------

class StatusTransformStrategy:
    def __init__(self, field_name: str):
        self.field_name = field_name

    def transform(self, raw: dict, source: str) -> str:
        value = raw.get(self.field_name)
        if not value:
            raise FieldMappingError(
                f"Campo '{self.field_name}' ausente", field=self.field_name, value=value, source=source
            )
        key = str(value).strip().lower()
        mapped = STATUS_MAP.get(key)
        if mapped is None:
            raise StatusMappingError(
                f"Estado no reconocido: '{value}'", field=self.field_name, value=value, source=source
            )
        return mapped.value


# ---------------------------------------------------------------------------
# Id / source strategies
# ---------------------------------------------------------------------------

class IdTransformStrategy:
    def __init__(self, field_name: str):
        self.field_name = field_name

    def transform(self, raw: dict, source: str) -> str:
        value = raw.get(self.field_name)
        if value is None or str(value).strip() == "":
            raise FieldMappingError(
                f"Campo '{self.field_name}' ausente", field=self.field_name, value=value, source=source
            )
        return str(value)


# ---------------------------------------------------------------------------
# Transformer bundle + Factory
# ---------------------------------------------------------------------------

class VariantTransformer:
    """Agrupa las estrategias necesarias para transformar una variante completa."""

    def __init__(
        self,
        variant: SourceVariant,
        id_strategy: IdTransformStrategy,
        amount_strategy: AmountTransformStrategy,
        currency_strategy: CurrencyTransformStrategy,
        date_strategy: DateTransformStrategy,
        status_strategy: StatusTransformStrategy,
    ):
        self.variant = variant
        self.id_strategy = id_strategy
        self.amount_strategy = amount_strategy
        self.currency_strategy = currency_strategy
        self.date_strategy = date_strategy
        self.status_strategy = status_strategy

    def transform(self, raw: dict) -> dict:
        """Aplica todas las estrategias y devuelve un dict con campos canónicos.

        No captura excepciones: se delega a la capa superior (normalizer)
        que decide cómo registrar el error sin abortar el lote completo.
        """
        source = self.variant.value
        logger.debug("Transformando registro variante=%s raw=%s", source, raw)
        return {
            "id": self.id_strategy.transform(raw, source),
            "amount": self.amount_strategy.transform(raw, source),
            "currency": self.currency_strategy.transform(raw, source),
            "timestamp": self.date_strategy.transform(raw, source),
            "status": self.status_strategy.transform(raw, source),
            "source": source,
        }


class TransformerFactory:
    """Factory que construye el `VariantTransformer` adecuado por variante."""

    @staticmethod
    def create(variant: SourceVariant) -> VariantTransformer:
        if variant == SourceVariant.VARIANT_1:
            return VariantTransformer(
                variant=variant,
                id_strategy=IdTransformStrategy("id"),
                amount_strategy=StringAmountStrategy(),
                currency_strategy=DirectCodeCurrencyStrategy("currency"),
                date_strategy=StrptimeDateStrategy("timestamp", "%Y-%m-%d %H:%M:%S"),
                status_strategy=StatusTransformStrategy("status"),
            )
        if variant == SourceVariant.VARIANT_2:
            return VariantTransformer(
                variant=variant,
                id_strategy=IdTransformStrategy("transaction_id"),
                amount_strategy=CentsIntegerAmountStrategy(),
                currency_strategy=DirectCodeCurrencyStrategy("currency_code"),
                date_strategy=StrptimeDateStrategy("created_at", "%d/%m/%Y %H:%M"),
                status_strategy=StatusTransformStrategy("state"),
            )
        if variant == SourceVariant.VARIANT_3:
            return VariantTransformer(
                variant=variant,
                id_strategy=IdTransformStrategy("ref"),
                amount_strategy=SymbolCommaAmountStrategy(),
                currency_strategy=SymbolCurrencyStrategy(),
                date_strategy=ISO8601DateStrategy(),
                status_strategy=StatusTransformStrategy("result"),
            )
        raise ValueError(f"No existe transformador registrado para la variante: {variant}")
