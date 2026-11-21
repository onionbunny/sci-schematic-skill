"""sci_fig.compliance
导出件合规检查（投稿前机器闸门）。

覆盖：
- SVG：viewBox 与画布一致、语义图层齐全、文字为 <text> 未转曲、marker 均有定义、
  每个实体/关系 id 可在文件中找到；
- PDF：pdfinfo 页面尺寸与目标 mm 一致，pdffonts 全部字体已嵌入；
- PNG/TIFF：Pillow 校验 RGB/sRGB、像素尺寸=mm/25.4*dpi、DPI 元数据、TIFF 压缩。
检查失败按硬伤返回，不通过的导出件不得标记为合规。
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from xml.etree import ElementTree as ET

from . import model


def _check_svg(path: Path, spec: dict) -> dict:
    issues: list[str] = []
    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        return {"ok": False, "issues": [f"SVG 无法解析: {exc}"]}
    root = tree.getroot()
    W = spec["figure"]["canvas"]["width_mm"]
    H = spec["figure"]["canvas"]["height_mm"]
    vb = (root.get("viewBox") or "").split()
    if len(vb) != 4 or abs(float(vb[2]) - W) > 0.5 or abs(float(vb[3]) - H) > 0.5:
        issues.append(f"viewBox {vb} 与画布 {W}x{H}mm 不一致")

    layer_ids = {el.get("id") for el in root.iter() if el.tag.endswith("g")}
    for need in ("layer-compartments", "layer-relationships", "layer-entities"):
        if need not in layer_ids:
            issues.append(f"缺少语义图层 {need}")

    defined_markers = {f'url(#{el.get("id")})' for el in root.iter()
                       if el.tag.split("}")[-1] == "marker"}
    for el in root.iter():
        for attr in ("marker-end", "marker-start"):
            ref = el.get(attr)
            if ref and ref not in defined_markers:
                issues.append(f"引用了未定义的 marker: {ref}")

    text_labels = {"".join(el.itertext()).strip() for el in root.iter()
                   if el.tag.split("}")[-1] == "text"}
    for ent in spec["entities"]:
        if ent["label"] not in text_labels:
            issues.append(f"实体标签未以 <text> 出现（可能被转曲或丢失）: {ent['label']}")
    if not text_labels:
        issues.append("SVG 中不存在任何 <text>，文字不可选")

    ids_in_file = {el.get("id") for el in root.iter()}
    for ent in spec["entities"] + spec["relationships"]:
        if ent["id"] not in ids_in_file:
            issues.append(f"元素 id 未出现在 SVG: {ent['id']}")
    return {"ok": not issues, "issues": issues,
            "text_selectable": bool(text_labels),
            "layer_count": len(layer_ids)}


def _pdf_info(path: Path) -> dict[str, str]:
    try:
        proc = subprocess.run(["pdfinfo", str(path)], capture_output=True,
                              text=True, timeout=60)
        out: dict[str, str] = {}
        for line in proc.stdout.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                out[k.strip()] = v.strip()
        return out
    except Exception:
        return {}


def _pdf_fonts(path: Path) -> list[dict[str, str]]:
    try:
        proc = subprocess.run(["pdffonts", str(path)], capture_output=True,
                              text=True, timeout=60)
        lines = proc.stdout.splitlines()
        if len(lines) < 3:
            return []
        header = lines[0]
        col = [header.index("name"), header.index("type"), header.index("emb"),
               header.index("sub"), header.index("uni")]
        fonts = []
        for line in lines[2:]:
            if not line.strip():
                continue
            fonts.append({
                "name": line[col[0]:col[1]].strip(),
                "type": line[col[1]:col[2]].strip(),
                "emb": line[col[2]:col[3]].strip(),
                "sub": line[col[3]:col[4]].strip(),
                "uni": line[col[4]:].strip().split()[0] if line[col[4]:].strip() else "",
            })
        return fonts
    except Exception:
        return []


def _check_pdf(path: Path, spec: dict) -> dict:
    issues: list[str] = []
    info = _pdf_info(path)
    if not info:
        return {"ok": False, "issues": ["pdfinfo 无法读取，PDF 可能损坏"]}
    target_w = model.mm_to_pt(spec["figure"]["canvas"]["width_mm"])
    target_h = model.mm_to_pt(spec["figure"]["canvas"]["height_mm"])
    page = info.get("Page size", "")
    dims = [float(x) for x in page.replace("pts", "").split("x")] if "x" in page else []
    if len(dims) == 2:
        if abs(dims[0] - target_w) > 1.5 or abs(dims[1] - target_h) > 1.5:
            issues.append(f"页面尺寸 {dims} 与目标 {target_w:.1f}x{target_h:.1f}pt 不符")
    fonts = _pdf_fonts(path)
    if not fonts:
        issues.append("未检测到字体表（可能为全位图 PDF，不满足矢量要求）")
    unembedded = [f["name"] for f in fonts if f["emb"] != "yes"]
    if unembedded:
        issues.append(f"字体未嵌入: {unembedded}")
    return {"ok": not issues, "issues": issues,
            "page_size_pt": dims, "fonts": fonts,
            "all_fonts_embedded": not unembedded and bool(fonts)}


def _check_raster(path: Path, spec: dict, fmt: str) -> dict:
    issues: list[str] = []
    try:
        from PIL import Image
    except Exception:
        return {"ok": False, "issues": ["Pillow 不可用，无法检查位图"]}
    with Image.open(path) as im:
        mode = im.mode
        dpi = im.info.get("dpi", (0, 0))
        w_px, h_px = im.width, im.height
        meta = {"mode": mode, "width_px": w_px, "height_px": h_px,
                "dpi": [round(float(x), 1) for x in dpi]}
        if fmt == "tiff":
            meta["compression"] = im.info.get("compression", "")
    target_dpi = spec["figure"]["canvas"]["dpi"]
    exp_w = model.mm_to_px(spec["figure"]["canvas"]["width_mm"], target_dpi)
    exp_h = model.mm_to_px(spec["figure"]["canvas"]["height_mm"], target_dpi)
    if mode not in ("RGB",):
        issues.append(f"色彩模式 {mode} 非 sRGB/RGB（期刊位图不接受 CMYK/索引/带透明通道）")
    if abs(w_px - exp_w) > max(2, 0.02 * exp_w) or abs(h_px - exp_h) > max(2, 0.02 * exp_h):
        issues.append(f"像素 {w_px}x{h_px} 与 {exp_w:.0f}x{exp_h:.0f}（{target_dpi}dpi）不符")
    if not dpi or float(dpi[0]) < target_dpi * 0.95:
        issues.append(f"DPI 元数据 {dpi} 低于目标 {target_dpi}")
    if fmt == "tiff" and meta.get("compression") not in ("tiff_lzw", "lzw"):
        issues.append("TIFF 未使用 LZW 压缩")
    return {"ok": not issues, "issues": issues, **meta}


def check_compliance(spec: dict, artifact_paths: list[str | Path]) -> dict:
    spec = model.normalize_spec(spec)
    results = []
    for p in map(Path, artifact_paths):
        if not p.exists():
            results.append({"file": str(p), "ok": False,
                            "issues": ["文件不存在"]})
            continue
        ext = p.suffix.lower().lstrip(".")
        if ext == "svg":
            rec = _check_svg(p, spec)
        elif ext == "pdf":
            rec = _check_pdf(p, spec)
        elif ext in ("png", "tiff", "tif"):
            rec = _check_raster(p, spec, "tiff" if ext == "tif" else ext)
        else:
            rec = {"ok": True, "issues": [], "note": "该格式仅做存在性检查"}
        rec["file"] = str(p); rec["format"] = ext
        results.append(rec)
    return {
        "status": "pass" if all(r["ok"] for r in results) else "fail",
        "checks": results,
        "preset": spec["figure"].get("preset"),
        "checked_at": model.utc_now_iso(),
    }
