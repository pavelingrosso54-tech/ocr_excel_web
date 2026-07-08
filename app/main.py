from pathlib import Path
import shutil
import traceback

from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.excel_writer import write_rows_to_excel
from app.ocr_yandex import get_yandex_rows


app = FastAPI(debug=True)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

STORAGE_DIR = BASE_DIR / "storage"
TEMPLATE_DIR = STORAGE_DIR / "templates"
TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)

ACTIVE_TEMPLATE_PATH = TEMPLATE_DIR / "current_template.xlsm"

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "template_exists": ACTIVE_TEMPLATE_PATH.exists(),
            "template_name": ACTIVE_TEMPLATE_PATH.name if ACTIVE_TEMPLATE_PATH.exists() else "Шаблон не загружен"
        }
    )


@app.get("/template/download")
async def download_template():
    if not ACTIVE_TEMPLATE_PATH.exists():
        raise HTTPException(status_code=404, detail="Шаблон не найден")

    return FileResponse(
        path=str(ACTIVE_TEMPLATE_PATH),
        filename="template.xlsm",
        media_type="application/vnd.ms-excel.sheet.macroEnabled.12"
    )


@app.post("/template/upload")
async def upload_template(template_file: UploadFile = File(...)):
    try:
        if not template_file.filename:
            raise HTTPException(status_code=400, detail="Файл не выбран")

        ext = Path(template_file.filename).suffix.lower()
        if ext != ".xlsm":
            raise HTTPException(status_code=400, detail="Разрешён только файл .xlsm")

        with ACTIVE_TEMPLATE_PATH.open("wb") as buffer:
            shutil.copyfileobj(template_file.file, buffer)

        return RedirectResponse(url="/", status_code=303)

    except HTTPException:
        raise
    except Exception:
        err = traceback.format_exc()
        print(err)
        return PlainTextResponse(err, status_code=500)


@app.post("/run")
async def run_process(image_file: UploadFile = File(...)):
    try:
        print("START /run")
        print("IMAGE NAME:", image_file.filename)

        image_path = UPLOAD_DIR / image_file.filename
        print("IMAGE PATH:", image_path)

        with image_path.open("wb") as buffer:
            shutil.copyfileobj(image_file.file, buffer)

        print("IMAGE SAVED:", image_path.exists())

        yandex_rows = get_yandex_rows(str(image_path))

        print("YANDEX ROWS COUNT:", len(yandex_rows))
        for i, r in enumerate(yandex_rows[:15], start=1):
            print(
                f"YANDEX ROW {i}: "
                f"date={r.get('date')!r}, "
                f"time={r.get('time')!r}, "
                f"time_raw={r.get('time_raw')!r}, "
                f"time_score={r.get('time_score')!r}, "
                f"time_y_used={r.get('time_y_used')!r}"
            )

        output_path = UPLOAD_DIR / "result_info_teke.xlsm"
        print("OUTPUT PATH:", output_path)

        write_rows_to_excel(yandex_rows, str(output_path))

        print("DONE:", output_path.exists())

        return FileResponse(
            path=str(output_path),
            filename=output_path.name,
            media_type="application/vnd.ms-excel.sheet.macroEnabled.12"
        )

    except Exception:
        err = traceback.format_exc()
        print(err)
        return PlainTextResponse(err, status_code=500)