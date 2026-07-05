

## 1. Contexto del proyecto

El sistema fue desarrollado para normalizar registros financieros provenientes de múltiples fuentes con estructuras heterogéneas. La restricción principal era que el núcleo de transformación debía ser extensible sin tocar código existente, y que ningún error de un registro individual debía interrumpir el procesamiento del lote.

La implementación fue asistida por IA (Claude, Anthropic) como herramienta de generación de código base y scaffolding. Este documento registra qué fue generado, qué fue ajustado y por qué.

---

## 2. Decisiones de diseño propias

### 2.1 `rules.json` como fuente de verdad configurable

**Decisión:** Los mapeos de estado, monedas soportadas, símbolos de moneda y formatos de fecha se externalizan en `rules.json`, no en el código.

**Motivación:** La IA generó inicialmente estos mapeos como constantes hardcodeadas en `transformers.py`. Ese diseño rompe el principio Open/Closed porque agregar un nuevo estado o moneda requiere modificar y re-desplegar código fuente. Con `rules.json`, un operador puede extender el sistema editando un archivo de texto sin tocar Python, sin tests nuevos y sin despliegue.

**Ajuste concreto:** Se creó `core/config_loader.py` como capa de indirección entre el archivo JSON y los transformadores. El loader se evaluá una vez al importar el módulo (patrón singleton de módulo) y expone funciones tipadas (`get_status_map()`, `get_supported_currencies()`, etc.) en lugar de exponer el dict crudo.

### 2.2 `StrptimeDateStrategy` con múltiples formatos en secuencia

**Decisión:** En lugar de asignar un único formato strptime por variante, la estrategia intenta todos los formatos configurados en `rules.json["date_formats"]` para esa variante, en orden, y usa el primero que funcione.

**Motivación:** En producción, un mismo proveedor suele enviar fechas con pequeñas inconsistencias (con o sin segundos, separador `/` vs `-`). Fijar un único formato genera errores innecesarios. La IA generó originalmente `StrptimeDateStrategy(field, fmt)` con un único formato fijo; se refactorizó para recibir `variant_key` y delegar la lista de formatos al config.

**Trade-off documentado:** El orden de los formatos en `rules.json` importa: si `"%Y-%m-%d %H:%M"` precede a `"%Y-%m-%d %H:%M:%S"`, un valor con segundos igualmente encajará (el parseo de strptime es estricto en longitud). Se documentó este comportamiento explícitamente en `rules.json["_doc"]`.

### 2.3 Subida de archivos con validación doble (cliente + servidor)

**Decisión:** La vista `/upload/` valida el archivo tanto en JavaScript (antes de enviar) como en Python (tras recibirlo). Ambas capas son independientes.

**Motivación:** La IA generó únicamente validación server-side. Se añadió la validación client-side para experiencia de usuario (feedback instantáneo, conteo de registros, preview de los primeros 3), pero nunca como sustituto de la validación de servidor, que es la autoridad real. El JS puede ser bypasseado; el Python no.

### 2.4 `ProcessingRun` como entidad de primera clase

**Decisión:** Cada importación crea un `ProcessingRun` en base de datos con sus métricas agregadas como `JSONField`. Las transacciones y errores tienen FK a su corrida.

**Motivación:** La IA planteó originalmente un modelo plano de transacciones sin agrupación. Se añadió `ProcessingRun` para habilitar: historial de ejecución, comparación entre importaciones, descarga por corrida individual y borrado granular sin afectar otras ejecución. El `JSONField` para métricas evita joins al renderizar el dashboard.

---

## 3. Uso de IA en el desarrollo

### Qué generó la IA sin ajustes relevantes

- Esqueleto de clases abstractas (`AmountTransformStrategy`, `CurrencyTransformStrategy`, `DateTransformStrategy`).
- Implementación de `ISO8601DateStrategy` con manejo de `fromisoformat()` y conversión a UTC.
- Estructura de `ErrorCollector` y `ValidationErrorRecord`.
- Implementaciones base de los repositorios in-memory y Django ORM.
- Lógica de paginación y filtros en las vistas Django.
- Templates HTML/CSS del dashboard y listados.
- Suite de tests unitarios para transformadores y validadores.

### Qué fue ajustado o rechazado

| Sugerencia de IA | Problema detectado | Ajuste aplicado |
|---|---|---|
| Mapas de estado/moneda hardcodeados en `transformers.py` | No extensible sin modificar código | Externalizados a `rules.json` con `config_loader.py` |
| `StrptimeDateStrategy` con un único formato fijo | Rompe ante variaciones menores del proveedor | Refactorizada para iterar lista de formatos del config |
| Validación de monto solo en `validators.py` | `allow_zero` como regla de negocio no estaba en config | Integrado en `validation_rules` de `rules.json` |
| `ProcessingRun` ausente; modelo plano de transacciones | Sin historial ni granularidad por corrida | Añadida entidad `ProcessingRun` con FK desde TX y errores |
| Upload solo con validación server-side | UX pobre; el usuario no sabe si su archivo es válido hasta esperar el POST | Añadida validación client-side con FileReader + JSON.parse |
| Templates con Bootstrap CDN | Dependencia externa; no funciona offline | Reemplazado por CSS propio inline en `base.html` |
| Formato de `rules.json` con comentarios `#` | `#` no es JSON válido; el parser falla | Convertidos a campos `"_doc"` dentro del propio JSON |
| `VariantDetector.matches()` retornando el nombre como string | Sin type-safety; fácil de desincronizar | Cambiado a retornar el enum `SourceVariant` |

### Qué fue generado por IA y revisado sin cambios

- La jerarquía de excepciones (`core/exceptions.py`) fue aceptada íntegramente: cada excepción lleva `field`, `value` y `source`, lo que permite logging estructurado sin try/except anidados en el normalizer.
- El patrón de `TransformerFactory.create()` fue aceptado sin cambios: devuelve un `VariantTransformer` pre-ensamblado que la capa de negocio llama de forma uniforme.
- Los archivos de datos de prueba (`valid_transactions.json`, `invalid_transactions.json`, `mixed_batch.json`) fueron elaborados manualmente con anotaciones `_error_expected` y `_note` para documentar cada caso.

---

## 4. Lecciones del proceso

**La IA es eficaz para scaffolding, débil en decisiones de ciclo de vida.** Los patrones de clases, la estructura de módulos y el código repetitivo (views, templates, tests) se generaron en minutos con calidad suficiente. Las decisiones que requieren pensar en operaciones, mantenimiento a largo plazo y extensibilidad (¿qué pasa cuando hay que añadir una moneda en producción a las 2am?) requirieron intervención humana.

**Los `_doc` en JSON son una convención adoptada aquí** porque JSON estándar no soporta comentarios. Se prefirió sobre alternativas como YAML (dependencia extra) o TOML (menos familiar al equipo Django).

**La doble validación (JS + Python) no es redundancia, es defensa en profundidad.** Son dos capas con propósitos distintos: UX vs. seguridad. Eliminar la capa Python porque "ya valida el JS" sería un error de seguridad.

---

## 5. Decisiones pendientes / deuda técnica conocida

| Área | Deuda | Propuesta futura |
|---|---|---|
| `rules.json` | Se carga al arrancar el proceso; un cambio requiere reinicio | Añadir endpoint `/admin/reload-config/` que llame a `config_loader.reload_config()` |
| Monedas | `get_supported_currencies()` no diferencia entre "aceptar cualquier ISO 4217" y "lista explícita" | Añadir flag `allow_any_iso4217: true` en el config |
| Tests | No hay tests de integración para las vistas Django (solo para el pipeline) | Añadir `django.test.Client` tests para `/upload/`, `/runs/`, filtros y descargas |
| Upload | No hay límite de registros por archivo, solo de tamaño | Añadir `max_records` en `validation_rules.upload` |
| Concurrencia | `bulk_create` sin transacción explícita; si falla a mitad, el `ProcessingRun` queda con métricas inconsistentes | Envolver `ProcessingRun.create + bulk_create` en `django.db.transaction.atomic()` |
