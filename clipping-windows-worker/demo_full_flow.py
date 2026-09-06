"""Demo del flujo completo de entrada→salida sin depender del VPS.

Ejecuta una secuencia realista de jobs a través de la arquitectura del worker
usando MockAPIClient:

    test_video.mp4
        ├── 1. TRANSCRIBE  → transcript.json (WhisperX + GPU)
        ├── 2. RENDER      → clip.mp4 (9:16, subtítulos + watermark)
        └── 3. QA          → VALIDACIÓN del clip (FFprobe)

Para cada job se recorre el ciclo real: claimed → processing → completed → upload.

Uso:
    .venv\\Scripts\\python demo_full_flow.py [ruta_al_video.mp4]
"""

from __future__ import annotations

import sys
from pathlib import Path

# Asegurar el paquete app importable.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.models.job import Job
from app.services.api_client import MockAPIClient
from app.services.job_manager import JobManager
from app.services.job_runner import JobRunner
from app.utils.logging import configure_logging, get_logger

logger = get_logger("demo")


def srt_timestamp(seconds: float) -> str:
    """Formatea segundos como timestamp SRT (HH:MM:SS,mmm)."""
    ms = int(round((seconds % 1.0) * 1000))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(segments: list[dict], start: float, end: float) -> str:
    """Genera un SRT con los segmentos que caen dentro de [start, end].

    FFmpeg recorta con -ss (input seek), así que la línea de tiempo de salida
    empieza en 0. Los timestamps del SRT deben ser relativos al clip.
    """
    lines: list[str] = []
    idx = 1
    for seg in segments:
        s = float(seg["start"])
        e = float(seg["end"])
        if e < start or s > end:
            continue
        s_rel = max(0.0, s - start)
        e_rel = min(e, end) - start
        if e_rel <= s_rel:
            continue
        lines.append(str(idx))
        lines.append(f"{srt_timestamp(s_rel)} --> {srt_timestamp(e_rel)}")
        lines.append(seg.get("text", "").strip())
        lines.append("")
        idx += 1
    return "\n".join(lines)


def build_watermark(path: Path, ffmpeg_bin: str, width: int = 400, height: int = 120) -> Path:
    """Genera un logo PNG de ejemplo usando ffmpeg (color + drawtext).

    Usa `fontfile` relativo con cwd en C:\\Windows\\Fonts para evitar la
    incompatibilidad de escapar rutas Windows en los filtros de ffmpeg.
    """
    from app.utils.subprocess import run_command

    cmd = [
        ffmpeg_bin, "-y",
        "-f", "lavfi", "-i", f"color=c=0xE11D48:s={width}x{height}:d=1",
        "-vf", (
            "drawtext=text='CLIP':"
            "fontfile=arialbd.ttf:"
            "fontsize=60:fontcolor=white:"
            "x=(w-text_w)/2:y=(h-text_h)/2"
        ),
        "-frames:v", "1", str(path),
    ]
    run_command(cmd, timeout=60, cwd=r"C:\Windows\Fonts")
    return path


def main() -> int:
    # La consola de Windows usa cp1252 por defecto; habilitamos UTF-8 para
    # poder imprimir caracteres como ✓ / →.
    if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    settings = get_settings()
    settings.ensure_directories()
    configure_logging(settings.log_level)

    video_arg = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "test_video.mp4")
    video_path = Path(video_arg).resolve()
    if not video_path.exists():
        logger.error("video no encontrado", path=str(video_path))
        sys.exit(1)

    ffmpeg_bin = settings.ffmpeg_path or "ffmpeg"

    api = MockAPIClient(settings)
    manager = JobManager(settings)
    runner = JobRunner(settings, api, manager)

    summary: dict[str, Path] = {}

    # ==================================================================
    # 1. TRANSCRIBE
    # ==================================================================
    print("\n" + "=" * 60)
    print("PASO 1 — TRANSCRIBE  (WhisperX + GPU)")
    print("=" * 60)
    transcribe_job = Job(
        id="job_001_transcribe",
        type="transcribe",
        payload={
            "video_path": str(video_path),
            "language": "auto",
            "diarization": False,
        },
    )
    transcript = runner.run(transcribe_job)
    api.upload_result(transcribe_job.id, transcript)  # como Worker._process_job
    transcript_file = Path(transcript["transcript_path"])
    summary["transcript"] = transcript_file
    print(f"  ✓ transcript.json → {transcript_file}")
    print(f"  Idioma: {transcript['language']} | Duración: {transcript['duration']:.1f}s")
    print(f"  Segmentos: {len(transcript['segments'])} | Palabras: {len(transcript['words'])}")
    print("  Primeros segmentos:")
    for seg in transcript["segments"][:3]:
        print(f"    [{seg['start']:.1f}→{seg['end']:.1f}] {seg['text'][:60]}")

    # ==================================================================
    # 2. RENDER  (elegir ventana de clip + subtítulos + watermark)
    # ==================================================================
    print("\n" + "=" * 60)
    print("PASO 2 — RENDER  (FFmpeg · clip 9:16)")
    print("=" * 60)
    duration = float(transcript["duration"] or 60.0)
    start = 3.0
    end = min(start + 20.0, duration)
    if end <= start:
        end = duration

    srt_file = Path(settings.temp_dir) / "subtitles.srt"
    srt_file.write_text(build_srt(transcript["segments"], start, end), encoding="utf-8")
    summary["subtitles"] = srt_file
    print(f"  Ventana clip: [{start:.1f}s → {end:.1f}s] ({end - start:.1f}s)")
    print(f"  SRT generado → {srt_file}")

    wm_file = Path(settings.temp_dir) / "logo.png"
    build_watermark(wm_file, ffmpeg_bin)
    summary["watermark"] = wm_file
    print(f"  Watermark generado → {wm_file}")

    render_job = Job(
        id="job_002_render",
        type="render",
        payload={
            "input_video": str(video_path),
            "start": start,
            "end": end,
            "output_format": "9:16",
            "captions": {"enabled": True, "file": str(srt_file)},
            "watermark": {
                "enabled": True,
                "file": str(wm_file),
                "position": "top_right",
                "margin_x": 40,
                "margin_y": 40,
                "width": 160,
            },
        },
    )
    clip = runner.run(render_job)
    api.upload_result(render_job.id, clip)  # como Worker._process_job
    clip_file = Path(clip["output_path"])
    summary["clip"] = clip_file
    print(f"  ✓ clip.mp4 → {clip_file}")
    print(f"  Tamaño: {clip['size'] / (1024 * 1024):.1f} MB | Formato: {clip['format']}")

    # ==================================================================
    # 3. QA
    # ==================================================================
    print("\n" + "=" * 60)
    print("PASO 3 — QA (FFprobe)")
    print("=" * 60)
    qa_job = Job(
        id="job_003_qa",
        type="qa",
        payload={
            "video": str(clip_file),
            "rules": {
                "min_duration": 10,
                "max_duration": 120,
                "width": 1080,
                "height": 1920,
                "require_audio": True,
            },
        },
    )
    qa = runner.run(qa_job)
    api.upload_result(qa_job.id, qa)  # como Worker._process_job
    print(f"  Resultado QA: {qa['status']}")
    for check in qa["checks"]:
        print(f"    [{check['status']}] {check['name']}: actual={check['actual']}")

    # ==================================================================
    # Resumen
    # ==================================================================
    print("\n" + "=" * 60)
    print("RESUMEN DEL FLUJO COMPLETO")
    print("=" * 60)
    for name, path in summary.items():
        print(f"  {name:12s} → {path}")

    print("\n  Estados reportados por job:")
    by_job: dict[str, list] = {}
    for up in api._status_updates:
        by_job.setdefault(up["job_id"], []).append(up["status"])
    for job_id, states in by_job.items():
        print(f"    {job_id}: {' → '.join(states)}")

    print("\n  Resultados subidos a la API (mock):")
    for job_id in ("job_001_transcribe", "job_002_render", "job_003_qa"):
        result = api.get_result(job_id)
        print(f"    {job_id}: {list(result.keys()) if result else '—'}")

    print("\nFlujo completo ejecutado con éxito.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
