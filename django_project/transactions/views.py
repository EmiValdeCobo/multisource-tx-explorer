"""
Vistas Django para la interfaz web interactiva de normalización de transacciones.

  /                        → dashboard (métricas de la última ejecuccion)
  /upload/                 → subir un nuevo archivo JSON para procesar
  /runs/                   → historial de todas las ejecuccions
  /runs/<id>/              → detalle de una ejecuccion específica
  /transactions/           → listado paginado con filtros
  /transactions/<id>/      → detalle de una transacción
  /errors/                 → listado de registros inválidos con motivo
  /download/json/          → descarga JSON de transacciones filtradas
  /download/csv/           → descarga CSV de transacciones filtradas
  /runs/<id>/download/json → descarga JSON de una ejecuccion específica
  /runs/<id>/download/csv  → descarga CSV de una ejecuccion específica
  /runs/<id>/delete/       → eliminar una ejecuccion y sus datos
"""
from __future__ import annotations

import csv
import json
from io import StringIO

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST, require_http_methods

import sys
from django.conf import settings
sys.path.insert(0, str(settings.PROJECT_ROOT))

from core.normalizer import TransactionNormalizer
from core.logging_config import logger
from django_project.django_project.transactions.models import (
    CanonicalStatusChoices,
    NormalizedTransaction,
    ProcessingRun,
    ValidationErrorLog,
)
from django_project.django_project.transactions.repository import DjangoTransactionRepository, DjangoErrorRepository

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_STATUS_CHOICES = [("", "Todos los estados")] + [(c.value, c.label) for c in CanonicalStatusChoices]
_CURRENCY_CHOICES = [("", "Todas las monedas"), ("USD", "USD"), ("EUR", "EUR"), ("GBP", "GBP")]

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


def _build_filters(request) -> dict:
    filters = {}
    if status := request.GET.get("status"):
        filters["status"] = status
    if currency := request.GET.get("currency"):
        filters["currency"] = currency.upper()
    if amount_min := request.GET.get("amount_min"):
        try:
            filters["amount_min"] = float(amount_min)
        except ValueError:
            pass
    if amount_max := request.GET.get("amount_max"):
        try:
            filters["amount_max"] = float(amount_max)
        except ValueError:
            pass
    if date_from := request.GET.get("date_from"):
        filters["date_from"] = date_from
    if date_to := request.GET.get("date_to"):
        filters["date_to"] = date_to
    return filters


def _run_pipeline(raw_records: list[dict], source_label: str) -> ProcessingRun:
    """Ejecuta el pipeline de normalización y persiste los resultados. Devuelve el ProcessingRun creado."""
    normalizer = TransactionNormalizer()
    valid_txs, error_collector, metrics = normalizer.process_batch(raw_records)

    run = ProcessingRun.objects.create(
        source_label=source_label,
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

    logger.info("ejecuccion #%s creada: %s válidas, %s inválidas", run.pk, metrics.total_valid, metrics.total_invalid)
    return run


def _tx_to_dict(tx) -> dict:
    return {
        "id": tx.external_id,
        "amount": float(tx.amount),
        "currency": tx.currency,
        "timestamp": tx.timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": tx.status,
        "source": tx.source,
    }


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@require_GET
def dashboard(request):
    runs = ProcessingRun.objects.all()
    latest_run = runs.first()
    context = {
        "latest_run": latest_run,
        "runs": runs[:5],
        "recent_runs": runs[:5],
        "total_transactions": NormalizedTransaction.objects.count(),
        "total_errors": ValidationErrorLog.objects.count(),
        "total_runs": runs.count(),
    }
    return render(request, "transactions/dashboard.html", context)


# ---------------------------------------------------------------------------
# Upload — GET muestra el formulario, POST procesa el archivo
# ---------------------------------------------------------------------------

@require_http_methods(["GET", "POST"])
def upload_json(request):
    """
    GET  → formulario de subida con drag-and-drop y previsualización.
    POST → valida el archivo, ejecuta el pipeline y redirige al detalle de la ejecuccion.
    """
    if request.method == "GET":
        recent_runs = ProcessingRun.objects.all()[:5]
        return render(request, "transactions/upload.html", {"recent_runs": recent_runs})

    # --- POST ---
    def _render_upload(status=200):
        return render(request, "transactions/upload.html",
                      {"recent_runs": ProcessingRun.objects.all()[:5]}, status=status)

    uploaded_file = request.FILES.get("json_file")
    if not uploaded_file:
        messages.error(request, "No se recibió ningún archivo. Selecciona un .json antes de enviar.")
        return _render_upload(400)

    if not uploaded_file.name.lower().endswith(".json"):
        messages.error(request, f"El archivo '{uploaded_file.name}' no tiene extensión .json.")
        return _render_upload(400)

    if uploaded_file.size > MAX_UPLOAD_BYTES:
        messages.error(request, f"El archivo supera el límite de 10 MB ({uploaded_file.size / 1024 / 1024:.1f} MB).")
        return _render_upload(400)

    raw_bytes = uploaded_file.read()
    try:
        raw_records = json.loads(raw_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        messages.error(request, f"El archivo no es un JSON válido: {exc}")
        return _render_upload(400)

    if not isinstance(raw_records, list):
        messages.error(request, "El JSON debe contener una lista [ ] de objetos en el nivel raíz.")
        return _render_upload(400)

    if len(raw_records) == 0:
        messages.error(request, "El archivo está vacío (lista sin elementos).")
        return _render_upload(400)

    # Usar etiqueta personalizada si se proporcionó
    source_label = request.POST.get("source_label", "").strip() or uploaded_file.name

    try:
        run = _run_pipeline(raw_records, source_label=source_label)
    except Exception as exc:
        logger.exception("Error inesperado en el pipeline tras upload: %s", exc)
        messages.error(request, f"Error interno al procesar el archivo: {exc}")
        return _render_upload(500)

    messages.success(
        request,
        f"✓ ejecuccion #{run.pk} completada — {run.total_valid} válidas, {run.total_invalid} inválidas."
    )
    return redirect("run_detail", pk=run.pk)


# ---------------------------------------------------------------------------
# Run history & detail
# ---------------------------------------------------------------------------

@require_GET
def run_list(request):
    runs = ProcessingRun.objects.all()
    paginator = Paginator(runs, 15)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    return render(request, "transactions/run_list.html", {"page_obj": page_obj})


@require_GET
def run_detail(request, pk: int):
    run = get_object_or_404(ProcessingRun, pk=pk)
    transactions = NormalizedTransaction.objects.filter(run=run).order_by("-timestamp")
    errors = ValidationErrorLog.objects.filter(run=run)
    paginator = Paginator(transactions, 20)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    context = {
        "run": run,
        "page_obj": page_obj,
        "errors": errors,
        "status_choices": _STATUS_CHOICES,
    }
    return render(request, "transactions/run_detail.html", context)


@require_POST
def run_delete(request, pk: int):
    run = get_object_or_404(ProcessingRun, pk=pk)
    run_id = run.pk
    run.delete()
    messages.success(request, f"ejecuccion #{run_id} eliminada correctamente.")
    return redirect("run_list")


# ---------------------------------------------------------------------------
# Transaction list (todas las ejecuccions, con filtros)
# ---------------------------------------------------------------------------

@require_GET
def transaction_list(request):
    repo = DjangoTransactionRepository()
    filters = _build_filters(request)

    # Filtro adicional por ejecuccion
    run_id = request.GET.get("run")
    qs = repo.list(filters if filters else None)
    if run_id:
        qs = qs.filter(run_id=run_id)

    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    context = {
        "page_obj": page_obj,
        "filters": filters,
        "raw_params": request.GET.urlencode(),
        "status_choices": _STATUS_CHOICES,
        "currency_choices": _CURRENCY_CHOICES,
        "selected_status": request.GET.get("status", ""),
        "selected_currency": request.GET.get("currency", ""),
        "amount_min": request.GET.get("amount_min", ""),
        "amount_max": request.GET.get("amount_max", ""),
        "date_from": request.GET.get("date_from", ""),
        "date_to": request.GET.get("date_to", ""),
        "runs": ProcessingRun.objects.all(),
        "selected_run": run_id or "",
    }
    return render(request, "transactions/transaction_list.html", context)


# ---------------------------------------------------------------------------
# Transaction detail
# ---------------------------------------------------------------------------

@require_GET
def transaction_detail(request, pk: int):
    tx = get_object_or_404(NormalizedTransaction, pk=pk)
    return render(request, "transactions/transaction_detail.html", {"tx": tx})


# ---------------------------------------------------------------------------
# Error list
# ---------------------------------------------------------------------------

@require_GET
def error_list(request):
    run_id = request.GET.get("run")
    qs = ValidationErrorLog.objects.select_related("run").all()
    if run_id:
        qs = qs.filter(run_id=run_id)

    error_type_filter = request.GET.get("error_type", "")
    if error_type_filter:
        qs = qs.filter(error_type=error_type_filter)

    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    error_types = ValidationErrorLog.objects.values_list("error_type", flat=True).distinct()
    runs = ProcessingRun.objects.all()

    context = {
        "page_obj": page_obj,
        "error_types": list(error_types),
        "runs": runs,
        "selected_run": run_id or "",
        "selected_error_type": error_type_filter,
    }
    return render(request, "transactions/error_list.html", context)


# ---------------------------------------------------------------------------
# Download: global (con filtros) o por ejecuccion específica
# ---------------------------------------------------------------------------

@require_GET
def download_json(request):
    repo = DjangoTransactionRepository()
    filters = _build_filters(request)
    run_id = request.GET.get("run")
    qs = repo.list(filters if filters else None)
    if run_id:
        qs = qs.filter(run_id=run_id)
    data = [_tx_to_dict(tx) for tx in qs]
    response = HttpResponse(json.dumps(data, indent=2, ensure_ascii=False), content_type="application/json")
    response["Content-Disposition"] = 'attachment; filename="transactions.json"'
    return response


@require_GET
def download_csv(request):
    repo = DjangoTransactionRepository()
    filters = _build_filters(request)
    run_id = request.GET.get("run")
    qs = repo.list(filters if filters else None)
    if run_id:
        qs = qs.filter(run_id=run_id)

    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "amount", "currency", "timestamp", "status", "source"])
    for tx in qs:
        d = _tx_to_dict(tx)
        writer.writerow([d["id"], d["amount"], d["currency"], d["timestamp"], d["status"], d["source"]])

    response = HttpResponse(buffer.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="transactions.csv"'
    return response


@require_GET
def run_download_json(request, pk: int):
    run = get_object_or_404(ProcessingRun, pk=pk)
    qs = NormalizedTransaction.objects.filter(run=run)
    data = [_tx_to_dict(tx) for tx in qs]
    response = HttpResponse(json.dumps(data, indent=2, ensure_ascii=False), content_type="application/json")
    response["Content-Disposition"] = f'attachment; filename="run_{pk}_transactions.json"'
    return response


@require_GET
def run_download_csv(request, pk: int):
    run = get_object_or_404(ProcessingRun, pk=pk)
    qs = NormalizedTransaction.objects.filter(run=run)
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "amount", "currency", "timestamp", "status", "source"])
    for tx in qs:
        d = _tx_to_dict(tx)
        writer.writerow([d["id"], d["amount"], d["currency"], d["timestamp"], d["status"], d["source"]])
    response = HttpResponse(buffer.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="run_{pk}_transactions.csv"'
    return response
