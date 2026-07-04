"""
Modelos Django que persisten el resultado del pipeline de normalización
(`core.normalizer.TransactionNormalizer`).

`NormalizedTransaction` refleja 1:1 el esquema canónico (`core.schema.CanonicalTransaction`).
`ValidationErrorLog` refleja `core.schema.ValidationErrorRecord`.
`ProcessingRun` agrupa una ejecuccion de importación y guarda sus métricas agregadas,
lo que permite comparar ejecuccions a lo largo del tiempo desde el dashboard.
"""
from django.db import models


class CanonicalStatusChoices(models.TextChoices):
    SUCCESS = "SUCCESS", "Success"
    FAILED = "FAILED", "Failed"
    PENDING = "PENDING", "Pending"


class ProcessingRun(models.Model):
    """Agrupa los resultados de una ejecución del pipeline sobre un archivo/lote."""

    created_at = models.DateTimeField(auto_now_add=True)
    source_label = models.CharField(max_length=255, default="sample_data/transactions.json")
    total_processed = models.PositiveIntegerField(default=0)
    total_valid = models.PositiveIntegerField(default=0)
    total_invalid = models.PositiveIntegerField(default=0)
    status_counts = models.JSONField(default=dict)
    currency_totals = models.JSONField(default=dict)
    error_type_counts = models.JSONField(default=dict)
    source_counts = models.JSONField(default=dict)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Run #{self.pk} ({self.created_at:%Y-%m-%d %H:%M:%S})"


class NormalizedTransaction(models.Model):
    """Transacción ya normalizada al esquema canónico."""

    run = models.ForeignKey(ProcessingRun, related_name="transactions", on_delete=models.CASCADE)
    external_id = models.CharField(max_length=255, db_index=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, db_index=True)
    timestamp = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=10, choices=CanonicalStatusChoices.choices, db_index=True)
    source = models.CharField(max_length=50, db_index=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["status", "currency"]),
        ]

    def __str__(self) -> str:
        return f"{self.external_id} ({self.currency} {self.amount}, {self.status})"


class ValidationErrorLog(models.Model):
    """Registro de un error de transformación/validación con contexto completo."""

    run = models.ForeignKey(ProcessingRun, related_name="errors", on_delete=models.CASCADE)
    source = models.CharField(max_length=50)
    error_type = models.CharField(max_length=100, db_index=True)
    field = models.CharField(max_length=100, null=True, blank=True)
    value = models.TextField(null=True, blank=True)
    reason = models.TextField()
    raw_record = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.error_type} @ {self.field} ({self.source})"
