"""
Patrón Factory: detección automática de la variante de estructura de un
registro crudo, y creación del `FieldMapper` correspondiente.

Añadir una nueva fuente de datos consiste únicamente en:
  1. Definir una nueva subclase de `VariantDetector` con su heurística.
  2. Registrarla en `VariantDetectorFactory.DETECTORS`.
Sin tocar el resto del núcleo (Open/Closed Principle).
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from core.schema import SourceVariant


class VariantDetector(ABC):
    """Estrategia de detección para una variante concreta."""

    variant: SourceVariant

    @abstractmethod
    def matches(self, raw: dict) -> bool:
        """Devuelve True si `raw` corresponde a esta variante."""


class Variant1Detector(VariantDetector):
    """id / amount(str) / currency / timestamp / status"""

    variant = SourceVariant.VARIANT_1

    def matches(self, raw: dict) -> bool:
        return "id" in raw and "timestamp" in raw and "status" in raw


class Variant2Detector(VariantDetector):
    """transaction_id / total / currency_code / created_at / state"""

    variant = SourceVariant.VARIANT_2

    def matches(self, raw: dict) -> bool:
        return "transaction_id" in raw and "created_at" in raw and "state" in raw


class Variant3Detector(VariantDetector):
    """ref / amount(str) / date / result"""

    variant = SourceVariant.VARIANT_3

    def matches(self, raw: dict) -> bool:
        return "ref" in raw and "date" in raw and "result" in raw


class VariantDetectorFactory:
    """Factory que recorre los detectores registrados y devuelve la variante."""

    DETECTORS: list[VariantDetector] = [
        Variant1Detector(),
        Variant2Detector(),
        Variant3Detector(),
    ]

    @classmethod
    def detect(cls, raw: dict) -> SourceVariant:
        for detector in cls.DETECTORS:
            if detector.matches(raw):
                return detector.variant
        return SourceVariant.UNKNOWN

    @classmethod
    def register(cls, detector: VariantDetector) -> None:
        """Permite registrar nuevas variantes en tiempo de ejecución (extensibilidad)."""
        cls.DETECTORS.append(detector)
