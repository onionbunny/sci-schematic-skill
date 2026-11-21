"""sci_fig.ingest
输入材料读取与归一化。

运行时输入：/input/case.json 与 task.md，以及按题目挂载的材料（文本、表格、
PDF、图片、待编辑的 SVG）。本模块把异构材料转成统一编号的阅读包 ingest_bundle，
Agent 据此做实体关系抽取，所有 source_refs 直接使用这里分配的 S{n} id。

重型依赖（pandas/pdfplumber/fitz/PIL）全部惰性导入，缺失时诚实降级并记录。
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from . import model

TEXT_SUFFIX = {".txt", ".md", ".markdown"}
TABLE_SUFFIX = {".csv", ".tsv", ".xlsx", ".xls"}
PDF_SUFFIX = {".pdf"}
IMAGE_SUFFIX = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".gif", ".bmp"}
SVG_SUFFIX = {".svg"}
SKIP_NAMES = {"case.json", "task.md"}


def _new_source(sid: str, kind: str, path: Path) -> dict[str, Any]:
    return {
        "id": sid, "kind": kind, "path": str(path),
        "name": path.name, "locator": "", "excerpt": "",
    }


def _read_text(path: Path) -> str:
    for enc in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return path.read_bytes().decode("utf-8", errors="replace")


def _read_table(path: Path) -> dict[str, Any]:
    """返回 {columns, rows, engine}；优先 pandas，缺失时用 stdlib csv。"""
    ext = path.suffix.lower()
    if ext in (".xlsx", ".xls"):
        try:
            import pandas as pd  # 惰性
            df = pd.read_excel(path)
            return {"columns": [str(c) for c in df.columns],
                    "rows": df.astype(object).where(df.notna(), "").values.tolist(),
                    "engine": f"pandas {pd.__version__}"}
        except Exception as exc:  # 依赖缺失或文件损坏
            return {"error": f"Excel 读取失败: {exc}"}
    try:
        import pandas as pd
        sep = "\t" if ext == ".tsv" else ","
        df = pd.read_csv(path, sep=sep)
        return {"columns": [str(c) for c in df.columns],
                "rows": df.astype(object).where(df.notna(), "").values.tolist(),
                "engine": f"pandas {pd.__version__}"}
    except Exception:
        delimiter = "\t" if ext == ".tsv" else ","
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.reader(fh, delimiter=delimiter)
            rows = list(reader)
        if not rows:
            return {"columns": [], "rows": [], "engine": "csv-stdlib"}
        return {"columns": rows[0], "rows": rows[1:], "engine": "csv-stdlib"}


def _read_pdf(path: Path) -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                tables = page.extract_tables() or []
                pages.append({"page": i, "text": text,
                              "tables": [t for t in tables if t]})
        engine = f"pdfplumber"
    except Exception:
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(path)
            for i, page in enumerate(doc, start=1):
                pages.append({"page": i, "text": page.get_text(), "tables": []})
            engine = "pymupdf"
        except Exception as exc:
            return {"error": f"PDF 解析失败（pdfplumber/pymupdf 均不可用）: {exc}"}
    return {"pages": pages, "engine": engine}


def _read_image(path: Path) -> dict[str, Any]:
    try:
        from PIL import Image
        with Image.open(path) as im:
            dpi = im.info.get("dpi", ("", ""))
            return {"width_px": im.width, "height_px": im.height,
                    "mode": im.mode, "dpi": list(dpi)}
    except Exception as exc:
        return {"error": f"图片探测失败: {exc}"}


def _read_svg(path: Path) -> dict[str, Any]:
    """解析待编辑 SVG：抽取画布、文字、几何元素与带端头的连线，供保源编辑。

    关键：先由物理宽度与 viewBox 宽度求“用户单位 -> mm”比例，无单位子坐标按
    用户单位（而非 px）换算；并用父节点映射跳过 <defs> 内部元素。
    """
    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        return {"error": f"SVG 解析失败: {exc}"}
    root = tree.getroot()

    def abs_mm(val: str | None) -> float | None:
        if not val:
            return None
        m = re.match(r"([0-9.]+)(px|mm|pt)?", val)
        if not m:
            return None
        num = float(m.group(1)); unit = m.group(2)
        if unit == "mm":
            return num
        if unit == "pt":
            return model.pt_to_mm(num)
        return model.px_to_mm(num, model.PX_PER_INCH_REF)  # px 或无单位（根节点）

    phys_w = abs_mm(root.get("width"))
    vb = (root.get("viewBox") or "").split()
    if phys_w is not None and len(vb) == 4 and float(vb[2]) > 0:
        scale = phys_w / float(vb[2])  # mm / 用户单位
    else:
        scale = 1.0

    def coord(val: str | None) -> float | None:
        if val is None:
            return None
        m = re.match(r"([0-9.]+)(px|mm|pt)?", val)
        if not m:
            return None
        num = float(m.group(1)); unit = m.group(2)
        if unit == "mm":
            return num
        if unit == "pt":
            return model.pt_to_mm(num)
        if unit == "px":
            return model.px_to_mm(num, model.PX_PER_INCH_REF)
        return num * scale  # 无单位 = 用户单位

    parent_map = {child: parent for parent in root.iter() for child in parent}

    def in_defs(el: ET.Element) -> bool:
        cur = el
        while cur in parent_map:
            cur = parent_map[cur]
            if cur.tag.split("}")[-1] == "defs":
                return True
        return False

    texts, nodes, edges = [], [], []
    for el in root.iter():
        if in_defs(el):
            continue
        tag = el.tag.split("}")[-1]
        if tag == "text":
            label = "".join(el.itertext()).strip()
            if label:
                texts.append({"id": el.get("id", ""), "label": label,
                              "x_mm": coord(el.get("x")), "y_mm": coord(el.get("y"))})
        elif tag in ("rect", "ellipse", "circle", "polygon"):
            item = {"tag": tag, "id": el.get("id", ""),
                    "stroke": el.get("stroke"), "fill": el.get("fill")}
            for a in ("x", "y", "width", "height", "cx", "cy", "r", "rx", "ry"):
                if el.get(a) is not None:
                    item[f"{a}_mm"] = coord(el.get(a))
            nodes.append(item)
        elif tag == "path":
            edges.append({"tag": "path", "id": el.get("id", ""),
                          "stroke": el.get("stroke"), "fill": el.get("fill"),
                          "marker_end": el.get("marker-end"),
                          "dash": el.get("stroke-dasharray")})
        elif tag in ("line", "polyline"):
            edges.append({"tag": tag, "id": el.get("id", ""),
                          "stroke": el.get("stroke"),
                          "marker_end": el.get("marker-end"),
                          "dash": el.get("stroke-dasharray")})
    return {"viewbox": root.get("viewBox"),
            "width_mm": phys_w, "height_mm": abs_mm(root.get("height")),
            "mm_per_user_unit": round(scale, 5),
            "texts": texts, "nodes": nodes, "edges": edges}


def _discover_materials(input_dir: Path, case: dict[str, Any]) -> list[Path]:
    found: list[Path] = []
    for key in ("materials", "inputs", "files", "attachments", "sources"):
        val = case.get(key) if isinstance(case, dict) else None
        if isinstance(val, list):
            for item in val:
                cand = item.get("path") if isinstance(item, dict) else item
                if cand:
                    p = Path(cand)
                    found.append(p if p.is_absolute() else input_dir / p)
    if input_dir.exists():
        for p in sorted(input_dir.rglob("*")):
            if p.is_file() and p.name not in SKIP_NAMES and not p.name.startswith("."):
                found.append(p)
    # 去重保持顺序
    seen: set[str] = set(); uniq: list[Path] = []
    for p in found:
        rp = str(p.resolve())
        if rp not in seen and p.exists():
            seen.add(rp); uniq.append(p)
    return uniq


def run_ingest(input_dir: str | Path, work_dir: str | Path) -> dict[str, Any]:
    input_dir = Path(input_dir); work_dir = Path(work_dir)
    reading_dir = work_dir / "reading"
    reading_dir.mkdir(parents=True, exist_ok=True)

    case_path = input_dir / "case.json"
    task_path = input_dir / "task.md"
    case: dict[str, Any] = {}
    if case_path.exists():
        try:
            case = model.load_json(case_path)
        except model.SpecError:
            case = {}
    task_text = _read_text(task_path) if task_path.exists() else ""

    case_id = ""
    if isinstance(case, dict):
        case_id = str(case.get("case_id") or case.get("id") or "")

    bundle: dict[str, Any] = {
        "case_id": case_id,
        "task": {"path": str(task_path), "text": task_text},
        "case_json": case if isinstance(case, dict) else {},
        "sources": [],
        "warnings": [],
    }

    sid = 0
    for path in _discover_materials(input_dir, case):
        sid += 1
        ext = path.suffix.lower()
        if ext in TEXT_SUFFIX:
            kind = "text"
        elif ext in TABLE_SUFFIX:
            kind = "table"
        elif ext in PDF_SUFFIX:
            kind = "pdf"
        elif ext in IMAGE_SUFFIX:
            kind = "image"
        elif ext in SVG_SUFFIX:
            kind = "svg"
        else:
            kind = "other"
        src = _new_source(f"S{sid}", kind, path)

        if kind == "text":
            text = _read_text(path)
            (reading_dir / f"S{sid}.txt").write_text(text, encoding="utf-8")
            src["locator"] = path.name
            src["excerpt"] = text[:1500]
        elif kind == "table":
            data = _read_table(path)
            src["table"] = data
            if "error" in data:
                bundle["warnings"].append(data["error"])
            (reading_dir / f"S{sid}.table.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            src["excerpt"] = f"{len(data.get('columns', []))} 列 x {len(data.get('rows', []))} 行"
        elif kind == "pdf":
            data = _read_pdf(path)
            src["pdf"] = data
            full = "\n\n".join(f"--- page {p['page']} ---\n{p['text']}" for p in data.get("pages", []))
            (reading_dir / f"S{sid}.txt").write_text(full, encoding="utf-8")
            src["excerpt"] = full[:1500]
            src["locator"] = f"{path.name} ({len(data.get('pages', []))} pages, {data.get('engine')})"
        elif kind == "image":
            src["image"] = _read_image(path)
            src["excerpt"] = "图片材料：Agent 可直接查看图像；元数据见 image 字段"
        elif kind == "svg":
            src["svg"] = _read_svg(path)
            (reading_dir / f"S{sid}.svg_seed.json").write_text(
                json.dumps(src["svg"], ensure_ascii=False, indent=2), encoding="utf-8")
            src["excerpt"] = f"待编辑 SVG：{len(src['svg'].get('texts', []))} 文本 / {len(src['svg'].get('nodes', []))} 节点"
        bundle["sources"].append(src)

    model.save_json(bundle, work_dir / "ingest_bundle.json")
    return bundle
