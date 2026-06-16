from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"
IMAGE_DIR = STATIC_DIR / "images"
REPORT_DIR = STATIC_DIR / "reports"
DASHBOARD_DIR = STATIC_DIR / "dashboard"
DATABASE_URL = f"sqlite:///{DATA_DIR / 'power_inspection.db'}"

for directory in (DATA_DIR, IMAGE_DIR, REPORT_DIR, DASHBOARD_DIR):
    directory.mkdir(parents=True, exist_ok=True)
