# Contexto del proyecto: sistema de clipping automatizado

## Objetivo

Este workspace contiene un sistema autónomo para detectar campañas de recompensas, interpretar sus reglas, resolver recursos autorizados, transcribir vídeo, seleccionar segmentos con MiniMax, renderizar clips con FFmpeg y validar el resultado de forma determinista antes de la revisión humana y, en fases posteriores, publicación y métricas.

No debe confundirse el diseño con la implementación comprobada. Antes de afirmar que una capacidad funciona, verificar código, tests, logs o una prueba end-to-end.

## Arquitectura

### Diagrama lógico

```
                        INTERNET
                           │
                           ▼
                 ┌───────────────────┐
                 │ Campaign Sources  │
                 │                   │
                 │ - campañas        │
                 │ - vídeos          │
                 │ - PDFs            │
                 │ - documentos      │
                 │ - imágenes        │
                 └─────────┬─────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                            VPS                               │
│                                                               │
│                       CONTROL PLANE                          │
│                                                               │
│   ┌─────────────────────┐                                    │
│   │ Campaign Collector  │                                    │
│   └─────────┬───────────┘                                    │
│             ▼                                                │
│   ┌─────────────────────┐                                    │
│   │ Campaign Selector   │                                    │
│   └─────────┬───────────┘                                    │
│             ▼                                                │
│   ┌─────────────────────┐                                    │
│   │ Campaign Analyzer   │                                    │
│   │ / Rule Parser       │                                    │
│   └─────────┬───────────┘                                    │
│             ▼                                                │
│   ┌─────────────────────┐                                    │
│   │ CampaignSpec        │                                    │
│   └─────────┬───────────┘                                    │
│             ▼                                                │
│   ┌─────────────────────┐                                    │
│   │ Asset Resolver      │                                    │
│   └─────────┬───────────┘                                    │
│             ▼                                                │
│   ┌─────────────────────┐                                    │
│   │ Job Orchestrator    │                                    │
│   └─────────┬───────────┘                                    │
│             ▼                                                │
│   ┌─────────────────────┐                                    │
│   │ PostgreSQL          │                                    │
│   │ State + Metadata    │                                    │
│   └─────────┬───────────┘                                    │
│             │                                                │
│             ▼                                                │
│        Job Queue                                              │
│             │                                                │
└─────────────┼────────────────────────────────────────────────┘
              │
              │ Tailscale
              ▼
┌──────────────────────────────────────────────────────────────┐
│                      WINDOWS GPU WORKER                      │
│                                                               │
│   Download                                                    │
│       ↓                                                       │
│   WhisperX                                                    │
│       ↓                                                       │
│   Transcript                                                  │
│       ↓                                                       │
│   FFmpeg                                                      │
│       ↓                                                       │
│   Render                                                      │
│       ↓                                                       │
│   QA                                                          │
│       ↓                                                       │
│   Upload results                                              │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

### Responsabilidades por componente

| Componente | Ubicación | Estado | Responsabilidad |
|---|---|---|---|
| **Campaign Sources** | Internet | Externo | Campañas, vídeos fuente, PDFs, documentos, imágenes |
| **Campaign Collector** | VPS | Pendiente | Ingesta periódica desde fuentes externas |
| **Campaign Selector** | VPS | Pendiente | Filtra y prioriza campañas relevantes. Ver [docs/campaign_selector.md](docs/campaign_selector.md) para diseño como skill + cron en OpenClaw |
| **Campaign Analyzer / Rule Parser** | VPS | Pendiente | Interpreta reglas en lenguaje natural → `CampaignSpec` |
| **CampaignSpec** | VPS | Pendiente | Representación estructurada con evidencia, fuente y confianza |
| **Asset Resolver** | VPS | Pendiente | Resuelve vídeos y assets autorizados para una campaña |
| **Job Orchestrator** | VPS | Validado | Crea jobs en PostgreSQL según `CampaignSpec` y assets |
| **PostgreSQL + Job Queue** | VPS | Validado | Persistencia + cola con `FOR UPDATE SKIP LOCKED` |
| **API central** | VPS | Validado | FastAPI con Bearer auth, `/jobs`, `/worker/*` |
| **Worker (Download)** | Windows | Validado | Descarga vídeos por streaming (`FileManager`) |
| **Worker (WhisperX)** | Windows | Validado E2E | Transcripción GPU `large-v3` + alineamiento |
| **Worker (FFmpeg/Render)** | Windows | Validado local | Recorte + escalado 16:9/9:16, watermark y captions opcionales |
| **Worker (QA)** | Windows | Validado local | Validación determinista con `ffprobe` |
| **Upload results** | Windows | Validado | `POST /worker/jobs/{id}/result` con `{"result": ...}` |
| **Revisión humana + Publicación** | Fuera del flujo Worker | Pendiente | Bot de Telegram y panel web |

### Notas arquitectónicas

- **OpenClaw** se ejecuta en el VPS y orquesta el flujo. No procesa vídeo directamente.
- **VPS Ubuntu** aloja la API central, PostgreSQL, la cola de jobs, Campaign Engine, ingestor, resolver de assets, parser documental, bot de Telegram y OpenClaw.
- **Windows GPU Worker** (`clipping-windows-worker/`) hace polling a la API central por Tailscale y ejecuta el trabajo pesado.
- **Hardware validado del Worker:** Windows 11, AMD Ryzen 7 5800X, 64 GB RAM y NVIDIA GeForce RTX 5070 Ti de 16 GB.
- **Procesamiento validado:** FFmpeg, FFprobe, WhisperX 3.8.6, PyTorch 2.8.0+cu128, CUDA 12.8, transcripción y alineamiento en español sobre vídeo real.
- Los **vídeos fuente** hoy viven solo en el Windows Worker (tests). No hay todavía resolución de assets real: el **Asset Resolver** en el VPS es el siguiente bloque a construir.
- El Worker referencia vídeos por path Windows absoluto (`C:\...`) o URL HTTP(S); nunca accede a almacenamiento remoto sin descargar primero.

Flujo objetivo:

`Campaign → CampaignSpec → assets autorizados → transcripción → candidatos → render → QA → revisión → publicación`

> **El flujo detallado paso a paso, quién hace qué y en qué orden, está en [docs/architecture_flow.md](docs/architecture_flow.md). Es la fuente única de verdad del flujo; cualquier cambio se acuerda y se modifica ahí.**

## Estado confirmado

Ya están conseguidos y no deben reinstalarse ni diagnosticarse de nuevo sin evidencia en contrario:

- API central del VPS.
- PostgreSQL y cola de jobs.
- Tailscale entre VPS y Windows.
- Autenticación Bearer mediante `API_TOKEN`.
- Polling del Worker y contrato `job_type` → `type`.
- Inicio y reclamación de jobs.
- Transcripción WhisperX end-to-end **en el Worker**: el job `d9690909-0c4c-4f05-b065-2d0bf27515bd` produjo `transcript.json` con `language="es"`, `duration=595.799`, `segments=122`, `words=1941`.
- **Flujo transcribe end-to-end cerrado**: VPS persiste `result.data` con la shape `{language, duration, segments, words, transcript_path}` validada en `GET /jobs/{id}`.
- Envío de resultados.
- Envío de fallos con `{"error_message": "..."}`.
- Jobs `health` completos end-to-end.
- FFmpeg y FFprobe detectados y utilizables.
- WhisperX instalado y operativo.
- CUDA disponible en el entorno Python correcto.
- RTX 5070 Ti detectada directamente por PyTorch.
- Transcripción y alineamiento WhisperX con CUDA, `float16` y `batch_size=16` validados.
- **Job `render` validado localmente** sobre `test_video.mp4` (recorte 5-15 s, 16:9): clip generado `1920x1080`, 60 fps, h264 + aac, 1.27 MB. Ver [test_render_local.py](clipping-windows-worker/test_render_local.py).
- **Job `qa` validado localmente** sobre el clip: 5/5 checks PASS (duration 9.5-10.5, resolution 1920x1080, fps>=24, audio presente, codec h264). Ver [test_qa_local.py](clipping-windows-worker/test_qa_local.py).

La detección de GPU del Worker también está corregida. `psutil` se instaló y se verificó la detección de RAM: 63.9 GB totales y 38.5 GB disponibles en la comprobación realizada.

## API y cola

La API está en `100.109.27.21:8080` dentro de Tailscale. Endpoints relevantes:

- `GET /health`
- `GET /system/info`
- `GET /worker/jobs/next?worker_id=...`
- `POST /worker/jobs/{job_id}/start?worker_id=...`
- `POST /worker/jobs/{job_id}/result?worker_id=...`
- `POST /worker/jobs/{job_id}/fail?worker_id=...`
- `POST /worker/jobs/{job_id}/heartbeat?worker_id=...`

No inventar endpoints. Si un contrato no está claro, consultar `/openapi.json`. No existen `/worker/register` ni un heartbeat general equivalente; `register_worker()` y el heartbeat general son legado y no deben reintroducirse.

La reclamación usa PostgreSQL con `FOR UPDATE SKIP LOCKED`, orden por prioridad descendente y antigüedad ascendente. Los jobs usan leases y transiciones `pending → assigned → processing → completed|failed|pending`.

## Reglas de trabajo

- No pedir, imprimir ni copiar el API token. El token vive en los archivos `.env` locales.
- No reinstalar PyTorch, CUDA o WhisperX sin una prueba que muestre un fallo real.
- No modificar múltiples archivos si solo se necesita uno. Preferir cambios pequeños, controlados y verificables.
- Al modificar un Python importante, entregar o mantener el archivo completo para evitar errores de indentación parciales.
- Consultar primero el estado real del archivo en disco; no asumir que una edición interrumpida se guardó.
- Mantener la separación: MiniMax decide y razona; FFmpeg/FFprobe ejecutan y validan procesamiento técnico.
- Las reglas numéricas y estructurales deben validarse determinísticamente: duración, aspect ratio, resolución, FPS, codec, audio, captions y watermark aplicado por el renderer.
- Usar OCR o visión solo para requisitos visuales o semánticos que no puedan comprobarse con el pipeline.
- Cada `CampaignSpec` importante debe conservar evidencia, fuente, página o sección y nivel de confianza cuando sea posible.
- No generar clips antes de interpretar las reglas de campaña.
- Actualizar este documento conforme se consigan checkpoints o se tome una decisión técnica importante.

## Estado pendiente inmediato

1. Revisar el contenido real de `clipping-windows-worker/app/services/system_info.py` y mantener la detección GPU sin reinstalar PyTorch. **Hecho según confirmación del usuario.**
2. Añadir `psutil` a `requirements.txt` e instalarlo para detectar RAM. **Hecho según verificación: total 63.9 GB, disponible 38.5 GB.**
3. Conseguir un startup limpio del Worker con GPU, VRAM, CUDA, RAM y herramientas correctos.
4. Crear y probar un job real `transcribe` desde el VPS hasta el Worker y vuelta.
5. Normalizar el `TranscriptResult` con segmentos, palabras, speakers y timestamps.
6. Después: selección de candidatos con MiniMax, render, captions, watermark y QA determinista.

> Render y QA ya están validados localmente; pendiente probarlos end-to-end desde el VPS.

## Decisiones técnicas tomadas

- **`worker_id` esperado en el VPS:** `windows-gpu-worker-01` (es el ID que el Worker se auto-asigna según `.env`; verificar antes de crear jobs).
- **Validación de accesibilidad de `video` en VPS:**
  - HTTP(S) → HEAD con timeout 5s, rechaza si 4xx/5xx o unreachable.
  - Path Linux (`/...`) → `os.path.isfile`, rechaza si no existe.
  - Path Windows (`C:\...`) o Tailscale (`\\VPS\share\...`) → VPS no verifica, el Worker valida al procesar.
- **OpenAPI se regenera automáticamente** con FastAPI; cualquier cambio en `JobCreate` se refleja en `/openapi.json`.
- **Persistencia:** `result.data` se guarda tal cual en `jobs.result` y `error_message` se persiste en caso de fail.

## Contratos de jobs del Worker

Validados en local. El VPS debe producir payloads con esta forma exacta:

### `transcribe` (validado end-to-end)

```json
{
  "job_type": "transcribe",
  "payload": {
    "video": "C:\\path\\to\\video.mp4",
    "language": "es",
    "options": {
      "model": "large-v3",
      "device": "cuda",
      "compute_type": "float16",
      "batch_size": 16,
      "align": true
    }
  },
  "priority": 5
}
```

Acepta también `"video_path"` por retrocompatibilidad. `result.data`:

```json
{"language":"es","duration":595.799,"segments":[...],"words":[...],"transcript_path":"..."}
```

### `render` (validado localmente)

```json
{
  "job_type": "render",
  "payload": {
    "input_video": "C:\\path\\to\\source.mp4",
    "start": 5.0,
    "end": 15.0,
    "output_format": "16:9"
  },
  "priority": 5
}
```

- `output_format`: `"16:9"` o `"9:16"` (16:9 → 1920×1080, 9:16 → 1080×1920).
- Opcionales: `captions` (SRT), `watermark` (`{path, position}` con position ∈ top_left|top_right|bottom_left|bottom_right|center).
- Codificador: `libx264` CRF 23 + `aac` 128k + `+faststart`. Recorte `-ss` antes de `-i` para precisión de keyframe.

`result.data`:

```json
{"output_path":"...\\clip.mp4","filename":"clip.mp4","size":1272676,"format":"16:9"}
```

### `qa` (validado localmente)

```json
{
  "job_type": "qa",
  "payload": {
    "video": "C:\\path\\to\\clip.mp4",
    "rules": {
      "min_duration": 9.5,
      "max_duration": 10.5,
      "width": 1920,
      "height": 1080,
      "min_fps": 24,
      "require_audio": true,
      "codec": "h264"
    }
  },
  "priority": 5
}
```

- Reglas opcionales: omitir las que no apliquen.
- Determinista: usa `ffprobe` para duration, resolución, fps, codec y audio.

`result.data`:

```json
{
  "status":"PASS",
  "checks":[
    {"name":"duration","status":"PASS","actual":10.0,"expected":"9.5-10.5"},
    {"name":"resolution","status":"PASS","actual":"1920x1080","expected":"1920x1080"},
    {"name":"fps","status":"PASS","actual":60.0,"expected":">=24"},
    {"name":"audio","status":"PASS","actual":true,"expected":true},
    {"name":"codec","status":"PASS","actual":"h264","expected":"h264"}
  ]
}
```

## División de trabajo actual

- **OpenClaw/VPS:** Campaign Ingestor, Document Parser, Asset Resolver, Campaign Engine, `CampaignSpec`, auditor LLM, creación de jobs y persistencia de resultados.
- **Windows GPU Worker:** job `transcribe`, selección/render/QA, procesamiento pesado con GPU.
- **El Worker no debe procesar directamente reglas de campaña ni decidir publicación.**

## Estado del trabajo en VPS (OpenClaw)

**Último checkpoint (05/09/2026 16:48):**

- ✅ 47/47 tests PASSED en el VPS (10 nuevos para `transcribe` + 1 actualizado).
- ✅ POST `/jobs` con `video=C:\CODIANT\clipping\test_video.mp4` → 201, `pending`, contrato completo.
- ✅ POST `/jobs` sin `video` → 400 con `{"detail":"transcribe payload must include 'video' (string)"}`.
- ✅ Flujo fail end-to-end: `create → /next → /start → /fail` → `status=failed`, `error_message` persistido, `worker_id` conservado.
- ✅ Flujo complete end-to-end: `create → /next → /start → /result` → `status=completed`, `result.data` con la shape exacta `{language, duration, segments, words}`.
- ✅ `/openapi.json` actualizado con el schema de `JobCreate`.

**Próximo paso desde Windows:** lanzar el curl de prueba, observar logs del Worker, validar que el job pasa `pending → assigned → processing → completed` y que `result.data` llega con `language=es`, `duration=598.0`, `segments`, `words`.

**Si algo falla:** pasar a OpenClaw el curl exacto lanzado + respuesta del servidor.

## Comandos y ubicaciones

Worker:

```powershell
cd C:\CODIANT\clipping\clipping-windows-worker
python run.py
```

Prueba CUDA directa, usando el mismo intérprete Python que ejecuta el Worker:

```powershell
python -c "import torch; print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NO GPU')"
```

No ejecutar esta prueba con un intérprete diferente al del Worker antes de concluir que CUDA está rota.

---

## Plantilla para lanzar un job `transcribe` desde Windows

```powershell
# Obtener token desde el .env del VPS (solo si ya lo tienes exportado)
$TOKEN = $env:API_TOKEN

# Crear job
curl.exe -s -X POST `
  -H "Authorization: Bearer $TOKEN" `
  -H "Content-Type: application/json" `
  -d '{"job_type":"transcribe","payload":{"video":"C:\CODIANT\clipping\test_video.mp4","language":"es","options":{"model":"large-v3","device":"cuda","compute_type":"float16","batch_size":16,"align":true}},"priority":5}' `
  http://100.109.27.21:8080/jobs
```

Verificación de un job por ID:

```powershell
curl.exe -s -H "Authorization: Bearer $TOKEN" http://100.109.27.21:8080/jobs/<job_id>
```

## Documentación de referencia

El historial técnico completo, comandos de la API, checkpoints y errores resueltos está en `HANDOFF — Clipping System - OpenClaw - Windows GPU Worker.md`. Ese documento es la fuente de contexto del proyecto; actualizarlo solo cuando cambie el estado verificado o se tome una decisión técnica importante.
