import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"

TEMPLATE_NAME = os.getenv("XLSM_TEMPLATE_NAME", "01.Инфо для покупателей на витрине.xlsm")
TEMPLATE_PATH = TEMPLATES_DIR / TEMPLATE_NAME
