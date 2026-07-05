# Transaction Normalizer

Sistema **production-ready** de normalización de transacciones financieras heterogéneas. Procesa registros JSON de múltiples fuentes con estructuras distintas, los valida con manejo explícito de excepciones, genera métricas consolidadas y expone una interfaz web Django interactiva.

---

## Índice

1. [Características](#características)
2. [Estructura del proyecto](#estructura-del-proyecto)
3. [Setup rápido](#setup-rápido)
4. [Uso (CLI + Django)](#uso)
5. [Variantes de entrada soportadas](#variantes-de-entrada-soportadas)
6. [Arquitectura y patrones de diseño](#arquitectura-y-patrones-de-diseño)
7. [Esquema canónico de salida](#esquema-canónico-de-salida)
8. [Manejo de errores](#manejo-de-errores)
9. [Métricas expuestas](#métricas-expuestas)
10. [Pruebas](#pruebas)
11. [Extender el sistema](#extender-el-sistema)

---

## Características

- **Detección automática de variante** (Factory) — sin configuración manual por registro.
- **Transformaciones modulares por campo** (Strategy) — cada tipo de conversión es intercambiable.
- **Manejo exhaustivo de excepciones** — ningún error interrumpe el lote; todos se registran con contexto completo.
- **Repository pattern** — la lógica de negocio es agnóstica de Django; los repositorios encapsulan el acceso a datos.
- **Interfaz web Django** con dashboard, listado paginado, filtros multi-campo, detalle e inspección de errores.
- **Descarga en JSON y CSV** con los mismos filtros activos.
- **22 tests unitarios e integración** cubriendo casos de éxito y fallo conocidos.
- **Extensible**: agregar una nueva fuente/variante requiere solo crear un `VariantDetector` + `VariantTransformer` sin tocar el núcleo.

---

## Estructura del proyecto

```
transaction_normalizer/
│
├── core/                          # Núcleo (independiente de Django)
│   ├── exceptions.py              # Jerarquía de excepciones de dominio
│   ├── schema.py                  # Esquema canónico, enums, métricas (dataclasses)
│   ├── logging_config.py          # Logger centralizado
│   ├── detectors.py               # Factory: detección de variante de estructura
│   ├── transformers.py            # Strategy: transformación por campo y variante
│   ├── validators.py              # Validación de negocio post-transformación
│   ├── normalizer.py              # Orquestador del pipeline completo
│   └── repository.py             # Interfaces abstractas + implementación in-memory
│
├── django_project/
│   ├── manage.py
│   ├── config/
│   │   ├── settings.py
│   │   ├── urls.py
│   │   └── wsgi.py
│   └── transactions/              # App Django
│       ├── models.py              # ORM: NormalizedTransaction, ValidationErrorLog, ProcessingRun
│       ├── repository.py          # Implementación Django del Repository
│       ├── views.py               # Dashboard, list, detail, errors, download
│       ├── urls.py
│       ├── apps.py
│       ├── management/commands/
│       │   └── load_transactions.py  # Management command de importación
│       └── templates/transactions/
│           ├── base.html
│           ├── dashboard.html
│           ├── transaction_list.html
│           ├── transaction_detail.html
│           └── error_list.html
│
├── tests/
│   ├── test_transformers.py       # Tests unitarios por variante y estrategia
│   ├── test_validators.py         # Tests del validador canónico
│   └── test_normalizer.py         # Tests de integración del pipeline completo
│
├── sample_data/
│   └── transactions.json          # 10 registros de las 3 variantes (válidos e inválidos)
│
├── requirements.txt
├── README.md
└── TECHNICAL_DOCS.md
```

---

## Setup rápido

### 1. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 2. Migraciones de base de datos

```bash
cd django_project
python manage.py migrate
```

### 3. Cargar datos de muestra

```bash
python manage.py load_transactions
# Con archivo personalizado:
python manage.py load_transactions --file /ruta/a/mi_archivo.json
```

### 4. Iniciar servidor de desarrollo

```bash
python manage.py runserver
```

Abre `http://127.0.0.1:8000/` para acceder al dashboard.

---

## Uso

### Pipeline standalone (sin Django)

```python
import json
from core.normalizer import TransactionNormalizer

with open("sample_data/transactions.json") as f:
    raw_records = json.load(f)

normalizer = TransactionNormalizer()
valid_txs, errors, metrics = normalizer.process_batch(raw_records)

for tx in valid_txs:
    print(tx.to_dict())

print(metrics.to_dict())
```

### Interfaz web

| Ruta | Descripción |
|---|---|
| `/` | Dashboard con métricas de la última corrida |
| `/transactions/` | Listado paginado con filtros |
| `/transactions/<id>/` | Detalle de una transacción |
| `/errors/` | Registros inválidos con motivo de error |
| `/download/json/` | Descarga JSON (respeta filtros activos) |
| `/download/csv/` | Descarga CSV (respeta filtros activos) |

---

## Variantes de entrada soportadas

### Variante 1
```json
{
  "id": "tx_001",
  "amount": "100.50",
  "currency": "USD",
  "timestamp": "2025-03-10 14:22:00",
  "status": "completed"
}
```

### Variante 2
```json
{
  "transaction_id": 204,
  "total": 10050,
  "currency_code": "usd",
  "created_at": "10/03/2025 14:22",
  "state": "OK"
}
```
> `total` se interpreta como **centavos** y se convierte dividiéndolo por 100.

### Variante 3
```json
{
  "ref": "A-77",
  "amount": "€99,99",
  "date": "2025-03-10T14:22:00Z",
  "result": "success"
}
```
> La moneda se infiere del símbolo (`€`→`EUR`, `$`→`USD`, `£`→`GBP`). El separador decimal es coma.

---

## Arquitectura y patrones de diseño

### Factory — `core/detectors.py`

`VariantDetectorFactory.detect(raw)` itera sobre los `VariantDetector` registrados y devuelve la variante correspondiente. Para añadir una nueva fuente solo hay que:

```python
class MyNewDetector(VariantDetector):
    variant = SourceVariant.MY_NEW
    def matches(self, raw):
        return "my_field" in raw

VariantDetectorFactory.register(MyNewDetector())
```

### Strategy — `core/transformers.py`

Cada tipo de campo tiene una familia de estrategias intercambiables:

- `AmountTransformStrategy` → `StringAmountStrategy`, `CentsIntegerAmountStrategy`, `SymbolCommaAmountStrategy`
- `CurrencyTransformStrategy` → `DirectCodeCurrencyStrategy`, `SymbolCurrencyStrategy`
- `DateTransformStrategy` → `StrptimeDateStrategy`, `ISO8601DateStrategy`
- `StatusTransformStrategy` (configurable por nombre de campo)

`TransformerFactory.create(variant)` ensambla el `VariantTransformer` correcto.

### Repository — `core/repository.py` + `transactions/repository.py`

`AbstractTransactionRepository` define la interfaz. La implementación in-memory se usa en tests; la implementación Django se usa en producción. La lógica de negocio en `core/normalizer.py` nunca depende de Django.

### Pipeline orquestado — `core/normalizer.py`

```
raw_record
  │
  ├─ VariantDetectorFactory.detect()     → SourceVariant
  ├─ TransformerFactory.create()         → VariantTransformer
  ├─ VariantTransformer.transform()      → dict canónico  (o excepción)
  ├─ TransactionValidator.validate()     → ok             (o excepción)
  │
  ├── Éxito → CanonicalTransaction  →  lista de válidas + métricas
  └── Fallo → ValidationErrorRecord →  ErrorCollector    + métricas
```

---

## Esquema canónico de salida

```json
{
  "id":        "string",
  "amount":    99.99,
  "currency":  "USD",
  "timestamp": "2025-03-10T14:22:00Z",
  "status":    "SUCCESS | FAILED | PENDING",
  "source":    "variant_1 | variant_2 | variant_3"
}
```

### Mapeos de estado

| Valor original | Estado canónico |
|---|---|
| `completed`, `success`, `ok`, `succeeded` | `SUCCESS` |
| `failed`, `failure`, `error` | `FAILED` |
| `pending`, `processing`, `in_progress` | `PENDING` |

---

## Manejo de errores

Todas las operaciones críticas están envueltas en `try/except` explícito:

| Excepción | Cuándo se lanza |
|---|---|
| `VariantDetectionError` | El registro no coincide con ninguna variante |
| `FieldMappingError` | Campo requerido ausente o nulo |
| `AmountConversionError` | Monto no convertible a número |
| `DateParsingError` | Fecha con formato no reconocido |
| `CurrencyNormalizationError` | Código/símbolo de moneda no reconocido |
| `StatusMappingError` | Estado no mapeado al conjunto canónico |
| `TransactionValidationError` | Monto negativo u otra regla de negocio |

Cada error se registra en `ErrorCollector` con: `raw_record`, `source`, `error_type`, `field`, `value`, `reason`.

---

## Métricas

```json
{
  "total_processed": 10,
  "total_valid":     5,
  "total_invalid":   5,
  "status_counts":   {"SUCCESS": 3, "FAILED": 0, "PENDING": 2},
  "currency_totals": {"USD": 201.0, "EUR": 149.99, "GBP": 75.5},
  "error_type_counts": {
    "AmountConversionError": 1,
    "CurrencyNormalizationError": 1,
    "DateParsingError": 1,
    "StatusMappingError": 1,
    "TransactionValidationError": 1
  },
  "source_counts": {"variant_1": 1, "variant_2": 2, "variant_3": 2}
}
```

---

## Pruebas

```bash
# Desde la raíz del repositorio
python -m unittest discover -s tests -v
```

**22 tests** cubriendo:
- Transformación correcta por cada variante y campo
- Excepciones específicas para cada tipo de fallo
- Pipeline completo (integración) con métricas consistentes
- Repositorio in-memory con filtros
- Variante desconocida capturada como error sin romper el lote

---

## Extender el sistema

### Agregar nueva variante de estructura

1. Añadir valor en `core/schema.py` → `SourceVariant`.
2. Crear `MyDetector(VariantDetector)` en `core/detectors.py` y registrarlo.
3. Crear las estrategias necesarias en `core/transformers.py`.
4. Registrar el `VariantTransformer` en `TransformerFactory.create()`.
5. Escribir tests en `tests/test_transformers.py`.

**No** hay que modificar `normalizer.py`, `validators.py`, `repository.py` ni ninguna vista Django.

### Agregar nueva moneda

Añadir el código ISO a `KNOWN_ISO_CURRENCIES` en `core/transformers.py`.

### Agregar nuevo símbolo de moneda

Añadir entrada al dict `CURRENCY_SYMBOL_MAP` en `core/transformers.py`.

### Agregar nuevo mapeo de estado

Añadir entrada al dict `STATUS_MAP` en `core/transformers.py`.
