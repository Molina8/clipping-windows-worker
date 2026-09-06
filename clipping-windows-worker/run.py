"""Punto de entrada del Windows GPU Worker.

Uso:
    python run.py
"""

import sys
from pathlib import Path

# Asegurar que el paquete `app` es importable desde cualquier cwd.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import main  # noqa: E402


if __name__ == "__main__":
    main()
