"""
Management command: load_transactions
Uso:
    python manage.py load_transactions
    python manage.py load_transactions --file /ruta/a/transactions.json
"""
import json
import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

import sys
sys.path.insert(0, str(settings.PROJECT_ROOT))

from core.normalizer import TransactionNormalizer
from core.schema import ProcessingMetrics
from django_project.django_project.transactions.models import ProcessingRun
from django_project.django_project.transactions.repository import DjangoTransactionRepository, DjangoErrorRepository


class Command(BaseCommand):
    help = "Carga, normaliza y persiste transacciones desde un archivo JSON"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            default=str(settings.SOURCE_DATA_PATH),
            help="Ruta al archivo JSON con registros crudos (default: SOURCE_DATA_PATH en settings)",
        )

    def handle(self, *args, **options):
        filepath = options["file"]
        if not os.path.exists(filepath):
            raise CommandError(f"Archivo no encontrado: {filepath}")

        self.stdout.write(self.style.NOTICE(f"Leyendo: {filepath}"))

        try:
            with open(filepath, encoding="utf-8") as f:
                raw_records = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            raise CommandError(f"Error leyendo el archivo: {exc}") from exc

        if not isinstance(raw_records, list):
            raise CommandError("El archivo JSON debe contener una lista de objetos en el nivel raíz.")

        normalizer = TransactionNormalizer()
        valid_txs, error_collector, metrics = normalizer.process_batch(raw_records)

        run = ProcessingRun.objects.create(
            source_label=filepath,
            total_processed=metrics.total_processed,
            total_valid=metrics.total_valid,
            total_invalid=metrics.total_invalid,
            status_counts=metrics.status_counts,
            currency_totals=metrics.currency_totals,
            error_type_counts=metrics.error_type_counts,
            source_counts=metrics.source_counts,
        )

        tx_repo = DjangoTransactionRepository()
        err_repo = DjangoErrorRepository()
        tx_repo.save_many(run, valid_txs)
        err_repo.save_many(run, error_collector.errors)

        self.stdout.write(self.style.SUCCESS(
            f"\n=== ejecuccion #{run.pk} completada ===\n"
            f"  Total procesados : {metrics.total_processed}\n"
            f"  Válidos          : {metrics.total_valid}\n"
            f"  Inválidos        : {metrics.total_invalid}\n"
            f"  Por estado       : {metrics.status_counts}\n"
            f"  Totales moneda   : {metrics.currency_totals}\n"
        ))
