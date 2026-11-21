"""sci_fig.export
多后端导出与自动降级。

后端优先级：cairosvg -> rsvg-convert -> inkscape -> 内置 reportlab 矢量兜底；
位图可由矢量 PDF 经 ghostscript/pdftocairo 栅格化；TIFF 由 Pillow 写 LZW 并
携带 DPI。每次导出记录实际使用的后端与参数，失败不伪造，写入 result 供复核。
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from . import model


def detect_backends() -> dict[str, Any]:
    backends: dict[str, Any] = {}
    try:
        import cairosvg  # noqa: F401
        backends["cairosvg"] = getattr(cairosvg, "__version__", "?")
    except Exception:
        pass
    for binary in ("rsvg-convert", "inkscape", "gs", "pdftocairo", "convert"):
        if shutil.which(binary):
            backends[binary] = shutil.which(binary)
    try:
        import reportlab  # noqa: F401
        backends["reportlab"] = getattr(reportlab, "Version", "?")
    except Exception:
        pass
    try:
        import PIL  # noqa: F401
        backends["pillow"] = getattr(PIL, "__version__", "?")
    except Exception:
        pass
    return backends


def _run(cmd: list[str], timeout: int = 120) -> tuple[bool, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if proc.returncode == 0:
            return True, ""
        return False, (proc.stderr or proc.stdout)[:400]
    except Exception as exc:
        return False, str(exc)


# ---------------------------------------------------------------- reportlab 兜底
def _pdf_via_reportlab(spec: dict, out_pdf: Path) -> tuple[bool, str]:
    try:
        from reportlab.pdfgen import canvas as rl_canvas
        from reportlab.lib.colors import HexColor, white
        W = model.mm_to_pt(spec["figure"]["canvas"]["width_mm"])
        H = model.mm_to_pt(spec["figure"]["canvas"]["height_mm"])
        c = rl_canvas.Canvas(str(out_pdf), pagesize=(W, H))

        def Y(y_mm: float) -> float:
            return H - model.mm_to_pt(y_mm)

        def text(x_mm: float, y_mm: float, s: str, size_pt: float,
                 bold: bool = False, anchor: str = "middle") -> None:
            font = "Helvetica-Bold" if bold else "Helvetica"
            c.setFont(font, size_pt)
            xp = model.mm_to_pt(x_mm)
            if anchor == "middle":
                xp -= c.stringWidth(str(s), font, size_pt) / 2
            elif anchor == "end":
                xp -= c.stringWidth(str(s), font, size_pt)
            c.setFillColor(HexColor("#111111"))
            c.drawString(xp, Y(y_mm) - size_pt * 0.3, str(s))

        # 区室
        for grp in spec["groups"]:
            b = grp.get("bounds")
            if not b:
                continue
            c.setFillColor(HexColor("#F2F2F2")); c.setStrokeColor(HexColor("#7F7F7F"))
            c.setLineWidth(0.5)
            c.roundRect(model.mm_to_pt(b["x_mm"]), Y(b["y_mm"] + b["h_mm"]),
                        model.mm_to_pt(b["w_mm"]), model.mm_to_pt(b["h_mm"]), 3, fill=1, stroke=1)
            text(b["x_mm"] + 2, b["y_mm"] + 3, grp.get("label", ""),
                 spec["figure"]["font"]["label_pt"], bold=True, anchor="start")

        # 关系（含简化端头）
        for rel in spec["relationships"]:
            route = rel.get("route")
            if not route:
                continue
            rdef = model.relation_def(rel["relation"])
            color = rel.get("color") or (
                model.semantic_color("activation") if rdef["polarity"] == "positive" else
                model.semantic_color("inhibition") if rdef["polarity"] == "negative" else
                model.semantic_color("neutral_edge"))
            c.setStrokeColor(HexColor(color)); c.setFillColor(HexColor(color))
            c.setLineWidth(spec["figure"]["stroke"]["width_pt"])
            if rdef["dash"] == "dashed":
                c.setDash(2, 1.5)
            pts = [(model.mm_to_pt(x), Y(y)) for x, y in route["points"]]
            path = c.beginPath(); path.moveTo(*pts[0])
            for p in pts[1:]:
                path.lineTo(*p)
            c.drawPath(path, fill=0, stroke=1)
            c.setDash()
            ex, ey = pts[-1]
            glyph = rdef["glyph"]
            if glyph == "arrow":
                tri = c.beginPath(); tri.moveTo(ex, ey); tri.lineTo(ex - 5, ey + 2.6); tri.lineTo(ex - 5, ey - 2.6); tri.close()
                c.drawPath(tri, fill=1, stroke=0)
            elif glyph == "tbar":
                c.setLineWidth(1.4); c.line(ex, ey - 4, ex, ey + 4)
            elif glyph in ("circle", "arrow_circle"):
                c.circle(ex - 3, ey, 3, stroke=1, fill=1 if glyph == "arrow_circle" else 0)

        # 实体
        ent_vocab = model.load_asset("entity_vocab")["entity_types"]
        for ent in spec["entities"]:
            p, s = ent.get("position"), ent.get("size")
            if not p or not s:
                continue
            shape = ent_vocab.get(ent["type"], ent_vocab["protein"])["shape"]
            c.setFillColor(white); c.setStrokeColor(HexColor("#222222"))
            c.setLineWidth(0.8)
            xp, yp = model.mm_to_pt(p["x_mm"]), Y(p["y_mm"] + s["h_mm"])
            ww, hh = model.mm_to_pt(s["w_mm"]), model.mm_to_pt(s["h_mm"])
            if shape in ("box", "rounded"):
                c.roundRect(xp, yp, ww, hh, 3 if shape == "rounded" else 0, fill=1, stroke=1)
            elif shape == "ellipse":
                c.ellipse(xp, yp, xp + ww, yp + hh, fill=1, stroke=1)
            else:
                c.rect(xp, yp, ww, hh, fill=1, stroke=1)
            label = ent["label"]
            if ent.get("value") not in (None, ""):
                label = f'{label} {ent["value"]} {ent.get("unit", "")}'.strip()
            text(p["x_mm"] + s["w_mm"] / 2, p["y_mm"] + s["h_mm"] / 2, label,
                 spec["figure"]["font"]["size_pt"])

        # 图例
        b = spec["legend"].get("bounds")
        if b:
            c.setFillColor(white); c.setStrokeColor(HexColor("#999999")); c.setLineWidth(0.4)
            c.roundRect(model.mm_to_pt(b["x_mm"]), Y(b["y_mm"] + b["h_mm"]),
                        model.mm_to_pt(b["w_mm"]), model.mm_to_pt(b["h_mm"]), 2, 1, 1)
        for item in spec["legend"]["items"]:
            p = item.get("position")
            if not p:
                continue
            c.setFillColor(HexColor(item.get("color", "#333333")))
            c.rect(model.mm_to_pt(p["x_mm"]), Y(p["y_mm"] + 2.6),
                   model.mm_to_pt(6.5), model.mm_to_pt(2.6), fill=1, stroke=0)
            text(p["x_mm"] + 8, p["y_mm"] + 1.7, item.get("label", ""),
                 spec["figure"]["font"]["label_pt"], anchor="start")

        c.showPage(); c.save()
        return True, ""
    except Exception as exc:
        return False, f"reportlab 导出失败: {exc}"


# ---------------------------------------------------------------- 单格式导出
def _export_pdf(svg_path: Path, out: Path, spec: dict, backends: dict) -> dict[str, Any]:
    if "cairosvg" in backends:
        try:
            import cairosvg
            cairosvg.svg2pdf(url=str(svg_path), write_to=str(out))
            return {"ok": True, "backend": "cairosvg"}
        except Exception as exc:
            last = str(exc)
    else:
        last = "cairosvg 不可用"
    if "rsvg-convert" in backends:
        ok, err = _run(["rsvg-convert", "-f", "pdf", "-o", str(out), str(svg_path)])
        if ok:
            return {"ok": True, "backend": "rsvg-convert"}
        last = err
    if "inkscape" in backends:
        ok, err = _run(["inkscape", str(svg_path), "--export-type=pdf", f"--export-filename={out}"])
        if ok:
            return {"ok": True, "backend": "inkscape"}
        last = err
    ok, err = _pdf_via_reportlab(spec, out)
    if ok:
        return {"ok": True, "backend": "reportlab-fallback"}
    return {"ok": False, "backend": "none", "error": f"{last}; {err}"}


def _normalize_png(out: Path, dpi: int) -> tuple[bool, str]:
    """期刊位图规范化：透明通道合成白底，转 RGB，写入 DPI 元数据。"""
    try:
        from PIL import Image
        with Image.open(out) as im:
            if im.mode in ("RGBA", "LA", "P"):
                rgba = im.convert("RGBA")
                bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                merged = Image.alpha_composite(bg, rgba).convert("RGB")
            else:
                merged = im.convert("RGB")
            merged.save(out, format="PNG", dpi=(dpi, dpi))
        return True, ""
    except Exception as exc:
        return False, f"PNG 规范化失败: {exc}"


def _export_png(svg_path: Path, out: Path, pdf_path: Path,
                dpi: int, backends: dict) -> dict[str, Any]:
    backend_used, last = "", "cairosvg 不可用"
    if "cairosvg" in backends:
        try:
            import cairosvg
            cairosvg.svg2png(url=str(svg_path), write_to=str(out), dpi=dpi)
            backend_used = "cairosvg"
        except Exception as exc:
            last = str(exc)
    if not backend_used and "rsvg-convert" in backends:
        ok, err = _run(["rsvg-convert", "-d", str(dpi), "-p", str(dpi),
                        "-f", "png", "-o", str(out), str(svg_path)])
        if ok:
            backend_used = "rsvg-convert"
        last = err
    if not backend_used and "gs" in backends and pdf_path.exists():
        ok, err = _run(["gs", "-dSAFER", "-dBATCH", "-dNOPAUSE", "-sDEVICE=png16m",
                        f"-r{dpi}", f"-sOutputFile={out}", str(pdf_path)])
        if ok:
            backend_used = "ghostscript"
        last = err
    if not backend_used and "pdftocairo" in backends and pdf_path.exists():
        prefix = out.with_suffix("")
        ok, err = _run(["pdftocairo", "-png", "-singlefile", "-r", str(dpi),
                        str(pdf_path), str(prefix)])
        if ok:
            backend_used = "pdftocairo"
        last = err
    if not backend_used:
        return {"ok": False, "backend": "none", "error": last, "dpi": dpi}

    ok, err = _normalize_png(out, dpi)
    if not ok:
        return {"ok": False, "backend": backend_used, "error": err, "dpi": dpi}
    return {"ok": True, "backend": backend_used, "dpi": dpi}


def _export_tiff(png_path: Path, out: Path, dpi: int, backends: dict) -> dict[str, Any]:
    if "pillow" in backends and png_path.exists():
        try:
            from PIL import Image
            with Image.open(png_path) as im:
                im.convert("RGB").save(out, format="TIFF", compression="tiff_lzw",
                                       dpi=(dpi, dpi))
            return {"ok": True, "backend": "pillow", "compression": "LZW", "dpi": dpi}
        except Exception as exc:
            last = str(exc)
    else:
        last = "pillow/PNG 不可用"
    if "convert" in backends:
        ok, err = _run(["convert", str(png_path), "-compress", "LZW",
                        "-units", "PixelsPerInch", "-density", str(dpi), str(out)])
        if ok:
            return {"ok": True, "backend": "imagemagick", "compression": "LZW", "dpi": dpi}
        last = err
    return {"ok": False, "backend": "none", "error": last}


def _export_eps(pdf_path: Path, out: Path, backends: dict) -> dict[str, Any]:
    if "gs" in backends and pdf_path.exists():
        ok, err = _run(["gs", "-dSAFER", "-dBATCH", "-dNOPAUSE", "-sDEVICE=eps2write",
                        f"-sOutputFile={out}", str(pdf_path)])
        if ok:
            return {"ok": True, "backend": "ghostscript"}
        return {"ok": False, "backend": "ghostscript", "error": err}
    return {"ok": False, "backend": "none", "error": "eps 需要 ghostscript 且需先有 PDF"}


def export_artifacts(spec: dict, svg_path: str | Path, out_dir: str | Path,
                     formats: list[str]) -> dict[str, Any]:
    svg_path, out_dir = Path(svg_path), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    backends = detect_backends()
    fig_id = spec["figure"]["id"]
    dpi = spec["figure"]["canvas"]["dpi"]
    records: list[dict[str, Any]] = []
    pdf_path = out_dir / f"{fig_id}.pdf"

    for fmt in formats:
        out = out_dir / f"{fig_id}.{fmt}"
        if fmt == "svg":
            records.append({"format": "svg", "path": str(svg_path),
                            "ok": True, "backend": "native"})
        elif fmt == "pdf":
            rec = _export_pdf(svg_path, out, spec, backends)
            rec.update({"format": "pdf", "path": str(out)}); records.append(rec)
        elif fmt == "png":
            rec = _export_png(svg_path, out, pdf_path, dpi, backends)
            rec.update({"format": "png", "path": str(out)}); records.append(rec)
        elif fmt == "tiff":
            png_for_tiff = out_dir / f"{fig_id}.png"
            if not png_for_tiff.exists():
                pre = _export_png(svg_path, png_for_tiff, pdf_path, dpi, backends)
                if not pre["ok"]:
                    records.append({"format": "tiff", "path": str(out), "ok": False,
                                    "error": pre["error"]}); continue
            rec = _export_tiff(png_for_tiff, out, dpi, backends)
            rec.update({"format": "tiff", "path": str(out)}); records.append(rec)
        elif fmt == "eps":
            if not pdf_path.exists():
                pre = _export_pdf(svg_path, pdf_path, spec, backends)
                if not pre["ok"]:
                    records.append({"format": "eps", "path": str(out), "ok": False,
                                    "error": pre["error"]}); continue
            rec = _export_eps(pdf_path, out, backends)
            rec.update({"format": "eps", "path": str(out)}); records.append(rec)
        else:
            records.append({"format": fmt, "path": str(out), "ok": False,
                            "error": f"不支持的格式: {fmt}"})

    return {"backends_detected": backends, "artifacts": records,
            "all_ok": all(r.get("ok") for r in records)}
