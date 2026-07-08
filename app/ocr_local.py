from pathlib import Path
import re
import cv2
import easyocr
import fitz


reader = easyocr.Reader(['ru'], gpu=False)


def pdf_first_page_to_png(pdf_path: str) -> str:
    pdf_file = Path(pdf_path)
    out_path = pdf_file.with_suffix(".page1.png")

    doc = fitz.open(pdf_path)
    page = doc.load_page(0)
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
    pix.save(str(out_path))
    doc.close()

    return str(out_path)


def load_image_any(path: str):
    file_path = Path(path)
    suffix = file_path.suffix.lower()

    actual_image_path = path
    if suffix == ".pdf":
        actual_image_path = pdf_first_page_to_png(path)

    img = cv2.imread(actual_image_path)
    if img is None:
        raise FileNotFoundError(f"Не удалось открыть изображение: {actual_image_path}")

    return img, actual_image_path


def safe_crop(img, x: int, y: int, w: int, h: int):
    img_h, img_w = img.shape[:2]

    x1 = max(0, x)
    y1 = max(0, y)
    x2 = min(img_w, x + w)
    y2 = min(img_h, y + h)

    if x2 <= x1 or y2 <= y1:
        return None

    roi = img[y1:y2, x1:x2]
    if roi is None or roi.size == 0:
        return None

    return roi


def preprocess_time_roi(roi):
    if roi is None or roi.size == 0:
        return None

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    up = cv2.resize(gray, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
    blur = cv2.GaussianBlur(up, (3, 3), 0)
    thr = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    return thr


def clean_time_text(text: str) -> str:
    if not text:
        return ""

    text = str(text).strip()
    repl = {
        ".": ":",
        ";": ":",
        ",": ":",
        " ": "",
        "I": "1", "l": "1", "|": "1", "!": "1",
        "O": "0", "o": "0", "О": "0", "о": "0",
        "S": "5", "s": "5",
        "B": "8",
    }

    for a, b in repl.items():
        text = text.replace(a, b)

    text = re.sub(r"[^0-9:]", "", text)
    return text


def normalize_time_candidate(text: str):
    text = clean_time_text(text)
    if not text:
        return None

    if ":" in text:
        parts = [p for p in text.split(":") if p]
        if len(parts) >= 2:
            h, m = parts[0], parts[1]
        else:
            return None
    else:
        digits = re.sub(r"\D", "", text)
        if len(digits) == 4:
            h, m = digits[:2], digits[2:]
        elif len(digits) == 3:
            h, m = digits[0], digits[1:]
        else:
            return None

    if len(h) == 1:
        h = h.zfill(2)
    if len(m) == 1:
        m = m + "0"

    if len(h) != 2 or len(m) != 2:
        return None
    if not h.isdigit() or not m.isdigit():
        return None

    hh = int(h)
    mm = int(m)

    if 0 <= hh <= 23 and 0 <= mm <= 59:
        return f"{hh:02d}:{mm:02d}"

    return None


def score_time_candidate(raw_text: str, normalized: str):
    if not normalized:
        return -1

    score = 0
    raw = clean_time_text(raw_text)

    if ":" in raw:
        score += 3

    if len(raw) in (4, 5):
        score += 2

    return score


def read_time_best(img, x: int, y: int, w: int, h: int, row_index: int, debug_dir: Path):
    offsets = [-10, -5, 0, 5, 10]
    best = {
        "raw": "",
        "normalized": None,
        "score": -1,
        "y_used": y,
    }

    for off in offsets:
        roi = safe_crop(img, x, y + off, w, h)
        if roi is None:
            continue

        prep = preprocess_time_roi(roi)
        if prep is None or prep.size == 0:
            continue

        result = reader.readtext(
            prep,
            detail=0,
            allowlist='0123456789:.-',
        )

        raw_text = result[0] if result else ""
        normalized = normalize_time_candidate(raw_text)
        score = score_time_candidate(raw_text, normalized)

        if score > best["score"]:
            best = {
                "raw": raw_text,
                "normalized": normalized,
                "score": score,
                "y_used": y + off,
            }

        if row_index < 5:
            cv2.imwrite(str(debug_dir / f"row_{row_index+1:02d}_time_off_{off:+d}.png"), prep)

    return best


def extract_date_time_rows(image_path: str, rows_count: int) -> list[dict]:
    img, actual_image_path = load_image_any(image_path)
    print("OCR IMAGE SOURCE:", actual_image_path)

    h, w = img.shape[:2]
    print("OCR IMAGE SIZE:", w, "x", h)

    debug_dir = Path(actual_image_path).parent / "ocr_debug"
    debug_dir.mkdir(exist_ok=True)

    rows = []

    start_y = int(h * 0.22)
    row_h = max(24, int(h * 0.028))

    date_x = int(w * 0.58)
    date_w = max(90, int(w * 0.18))

    time_x = int(w * 0.77)
    time_w = max(80, int(w * 0.16))

    print(
        f"COORDS start_y={start_y}, row_h={row_h}, "
        f"date_x={date_x}, date_w={date_w}, "
        f"time_x={time_x}, time_w={time_w}"
    )

    overlay = img.copy()

    for i in range(rows_count):
        y = start_y + i * row_h

        cv2.rectangle(overlay, (date_x, y), (date_x + date_w, y + row_h), (0, 255, 0), 2)
        cv2.rectangle(overlay, (time_x, y), (time_x + time_w, y + row_h), (0, 0, 255), 2)
        cv2.putText(overlay, str(i + 1), (date_x - 35, y + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)

        date_roi = safe_crop(img, date_x, y, date_w, row_h)
        date_raw = ""

        if date_roi is not None:
            date_gray = cv2.cvtColor(date_roi, cv2.COLOR_BGR2GRAY)
            date_up = cv2.resize(date_gray, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
            date_thr = cv2.threshold(date_up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

            date_result = reader.readtext(
                date_thr,
                detail=0,
                allowlist='0123456789.-',
            )
            date_raw = date_result[0] if date_result else ""

            if i < 5:
                cv2.imwrite(str(debug_dir / f"row_{i+1:02d}_date.png"), date_thr)

        time_best = read_time_best(img, time_x, y, time_w, row_h, i, debug_dir)

        print(
            f"OCR ROW {i+1}: y={y}, "
            f"date_raw={date_raw!r}, "
            f"time_raw={time_best['raw']!r}, "
            f"time_norm={time_best['normalized']!r}, "
            f"time_score={time_best['score']}, "
            f"y_used={time_best['y_used']}"
        )

        rows.append({
            "date": date_raw,
            "time": time_best["normalized"] or "",
            "time_raw": time_best["raw"],
            "time_score": time_best["score"],
            "time_y_used": time_best["y_used"],
            "row_y": y,
        })

    cv2.imwrite(str(debug_dir / "overlay_boxes.png"), overlay)

    return rows
