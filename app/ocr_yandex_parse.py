import json
import re
from pathlib import Path

INPUT_JSON = Path(r"H:\Projects\ocr_excel_web\output.json")
OUTPUT_JSON = Path(r"H:\Projects\ocr_excel_web\yandex_rows.json")

def to_num(v):
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        v = v.strip().replace(",", ".")
        try:
            return float(v)
        except:
            return 0.0
    return 0.0

def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def get_vertices(obj):
    bb = obj.get("boundingBox", {})
    vertices = bb.get("vertices", [])
    pts = []
    for v in vertices:
        x = to_num(v.get("x", 0))
        y = to_num(v.get("y", 0))
        pts.append((x, y))
    return pts

def bbox_stats(vertices):
    if not vertices:
        return None
    xs = [p[0] for p in vertices]
    ys = [p[1] for p in vertices]
    return {
        "x1": min(xs),
        "y1": min(ys),
        "x2": max(xs),
        "y2": max(ys),
        "cx": sum(xs) / len(xs),
        "cy": sum(ys) / len(ys),
        "w": max(xs) - min(xs),
        "h": max(ys) - min(ys),
    }

def collect_words(node, out):
    if isinstance(node, dict):
        if "text" in node and "boundingBox" in node:
            text = str(node.get("text", "")).strip()
            vertices = get_vertices(node)
            stats = bbox_stats(vertices)
            if text and stats:
                out.append({
                    "text": text,
                    **stats
                })
        for v in node.values():
            collect_words(v, out)
    elif isinstance(node, list):
        for item in node:
            collect_words(item, out)

def normalize_text(s: str) -> str:
    s = s.strip()
    s = s.replace("О", "0").replace("о", "0").replace("O", "0")
    s = s.replace("I", "1").replace("l", "1").replace("|", "1")
    s = s.replace(",", ":").replace(";", ":").replace(".", ":")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def extract_first_time(s: str):
    s = normalize_text(s)
    m = re.search(r"\b(\d{1,2}:\d{2})\b", s)
    if m:
        return m.group(1)

    m = re.search(r"\b(\d{4})\b", s)
    if m:
        raw = m.group(1)
        hh, mm = raw[:2], raw[2:]
        hhi = int(hh)
        mmi = int(mm)
        if 0 <= hhi <= 23 and 0 <= mmi <= 59:
            return f"{hhi:02d}:{mmi:02d}"

    return ""

def extract_first_day(s: str):
    s = normalize_text(s)
    matches = re.findall(r"\b(\d{1,2})\b", s)
    for val in matches:
        n = int(val)
        if 1 <= n <= 31:
            return str(n)
    return ""

def group_rows(words, y_threshold=18):
    words = sorted(words, key=lambda w: (w["cy"], w["cx"]))
    rows = []

    for w in words:
        placed = False
        for row in rows:
            if abs(row["cy"] - w["cy"]) <= y_threshold:
                row["words"].append(w)
                row["cy_values"].append(w["cy"])
                row["cy"] = sum(row["cy_values"]) / len(row["cy_values"])
                placed = True
                break
        if not placed:
            rows.append({
                "cy": w["cy"],
                "cy_values": [w["cy"]],
                "words": [w]
            })

    for row in rows:
        row["words"] = sorted(row["words"], key=lambda w: w["cx"])

    return rows

def main():
    data = load_json(INPUT_JSON)

    words = []
    collect_words(data, words)

    print("TOTAL RAW WORDS:", len(words))

    words = [w for w in words if w["cx"] >= 250 and w["cy"] >= 250 and w["cy"] <= 1550]
    print("FILTERED WORDS:", len(words))

    rows = group_rows(words, y_threshold=18)
    print("GROUPED ROWS:", len(rows))

    result = []

    for idx, row in enumerate(rows, start=1):
        row_words = row["words"]

        date_words = [w for w in row_words if 700 <= w["cx"] <= 820]
        time_words = [w for w in row_words if 930 <= w["cx"] <= 1030]

        date_text_raw = " ".join(w["text"] for w in date_words).strip()
        time_text_raw = " ".join(w["text"] for w in time_words).strip()

        result.append({
            "row_index": idx,
            "y": round(row["cy"], 1),
            "date_raw": date_text_raw,
            "date_norm": extract_first_day(date_text_raw),
            "time_raw": time_text_raw,
            "time_norm": extract_first_time(time_text_raw),
            "all_text": " | ".join(w["text"] for w in row_words)
        })

    with OUTPUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    for r in result[:60]:
        print(
            f"ROW {r['row_index']:02d}  "
            f"y={r['y']:>6}  "
            f"date_raw={r['date_raw']!r:<12}  "
            f"date_norm={r['date_norm']!r:<4}  "
            f"time_raw={r['time_raw']!r:<18}  "
            f"time_norm={r['time_norm']!r}"
        )

    print("SAVED:", OUTPUT_JSON)

if __name__ == "__main__":
    main()
