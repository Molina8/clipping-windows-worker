"""Logging estructurado.

Usa structlog si está disponible; si no, cae a logging estándar.
Proporciona un logger listo para usar en todo el proyecto.
"""

from __future__ import annotations

import logging
import sys

try:  # pragma: no cover - depende de la instalación
    import structlog

    _HAS_STRUCTLOG = True
except ImportError:  # pragma: no cover
    _HAS_STRUCTLOG = False


def configure_logging(level: str = "INFO") -> None:
    """Configura el logging global del proceso."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    if _HAS_STRUCTLOG:
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.dev.ConsoleRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )
    else:
        logging.basicConfig(
            level=numeric_level,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
            stream=sys.stdout,
        )


def get_logger(name: str = "worker"):
    """Devuelve un logger (structlog o estándar).

    Si structlog no está instalado, devuelve un wrapper que acepta
    kwargs (clave=valor) y los formatea en el mensaje, de modo que el
    código que usa `logger.info("msg", key=value)` funciona en ambos casos.
    """
    if _HAS_STRUCTLOG:
        return structlog.get_logger(name)
    return _KwargsLogger(logging.getLogger(name))


class _KwargsLogger:
    """Adaptador de logging estándar que acepta kwargs estilo structlog."""

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def _log(self, level: int, msg: str, kwargs: dict) -> None:
        if kwargs:
            rendered = " ".join(f"{k}={v!r}" for k, v in kwargs.items())
            msg = f"{msg} [{rendered}]"
        self._logger.log(level, msg)

    def debug(self, msg: str, **kwargs) -> None:
        self._log(logging.DEBUG, msg, kwargs)

    def info(self, msg: str, **kwargs) -> None:
        self._log(logging.INFO, msg, kwargs)

    def warning(self, msg: str, **kwargs) -> None:
        self._log(logging.WARNING, msg, kwargs)

    def error(self, msg: str, **kwargs) -> None:
        self._log(logging.ERROR, msg, kwargs)

    def exception(self, msg: str, **kwargs) -> None:
        self._logger.exception(msg)
