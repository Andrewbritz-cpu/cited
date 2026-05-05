"""
Shared Jinja templates instance.

Both main.py and the various router modules need to render templates. Keeping
the instance here means everyone uses the same configuration.
"""

from pathlib import Path

from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent.parent

templates = Jinja2Templates(directory=BASE_DIR / "templates")
