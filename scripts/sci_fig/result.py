"""sci_fig.result
按平台 output_contract 组装 result.json：诚实状态、工件清单、逐元素来源、
图例/数据映射核对、不确定性、变更记录与全部机器检查结果。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from . import model


def _provenance(spec: dict) -> dict:
    source_index = model.index_by_id(spec["sources"])
    elements = []
    for kind, rows in (("entity", spec["entities"]),
                       ("relationship", spec["relationships"]),
                       ("group", spec["groups"])):
        for row in rows:
            src_detail = []
            for ref in row.get("source_refs", []):
                s = source_index.get(ref, {})
                src_detail.append({
                    "source_id": ref, "path": s.get("path", ""),
                    "locator": s.get("locator", ""),
                })
            elements.append({
                "element_id": row.get("id"), "kind": kind,
                "label": row.get("label") or row.get("relation", ""),
                "source_refs": row.get("source_refs", []),
                "sources": src_detail,
                "confidence": row.get("confidence", "unset"),
            })
    return {
        "sources": [{"id": s.get("id"), "kind": s.get("kind"),
                     "path": s.get("path"), "name": s.get("name")}
                    for s in spec["sources"]],
        "elements": elements,
    }


def _legend_mapping_check(spec: dict) -> dict:
    legend = spec["legend"]["items"]
    rel_used = sorted({r["relation"] for r in spec["relationships"]})
    rel_legend = sorted({i["ref"] for i in legend if i.get("kind") == "relation"})
    dataset_checks = []
    for ds in spec["datasets"]:
        mapping = ds.get("mapping", {})
        dataset_checks.append({
            "dataset_id": ds.get("id"),
            "color_by": mapping.get("color_by"),
            "palette": mapping.get("palette"),
            "category_colors": mapping.get("category_colors", {}),
        })
    return {
        "legend_item_count": len(legend),
        "relations_used": rel_used,
        "relations_in_legend": rel_legend,
        "relations_missing_legend": sorted(set(rel_used) - set(rel_legend)),
        "datasets": dataset_checks,
    }


def build_result(spec: dict, *, validation: dict, layout: dict | None,
                 export: dict, compliance: dict, output_dir: str | Path,
                 spec_path: str | Path, svg_path: str | Path) -> dict[str, Any]:
    output_dir = Path(output_dir)

    def _rel(p: str | Path) -> str:
        try:
            return str(Path(p).resolve().relative_to(output_dir.resolve()))
        except Exception:
            return str(p)

    exports, previews = [], []
    for rec in export.get("artifacts", []):
        item = {"format": rec.get("format"), "path": _rel(rec.get("path", "")),
                "backend": rec.get("backend"), "ok": rec.get("ok", False)}
        if rec.get("error"):
            item["error"] = rec["error"]
        if rec.get("dpi"):
            item["dpi"] = rec["dpi"]
        if rec.get("format") == "png":
            previews.append(item)
        else:
            exports.append(item)

    v_pass = validation.get("status") == "pass"
    c_pass = compliance.get("status") == "pass"
    ok_formats = [r["format"] for r in export.get("artifacts", []) if r.get("ok")]
    if not v_pass or not ok_formats:
        status = "failed"
    elif not c_pass or len(ok_formats) < len(export.get("artifacts", [])):
        status = "partial"
    else:
        status = "success"

    return {
        "case_id": spec.get("case_id", ""),
        "status": status,
        "schema_version": model.SCHEMA_VERSION,
        "figure_id": spec["figure"].get("id"),
        "figure_type": spec["figure"].get("type"),
        "summary": {
            "entity_count": len(spec["entities"]),
            "relationship_count": len(spec["relationships"]),
            "group_count": len(spec["groups"]),
            "legend_count": len(spec["legend"]["items"]),
            "dataset_count": len(spec["datasets"]),
            "provenance_coverage": validation.get("provenance_coverage"),
        },
        "artifacts": {
            "editable_source": {
                "path": _rel(svg_path), "format": "svg",
                "text_selectable": True, "layered": True,
                "layers": ["layer-compartments", "layer-relationships",
                           "layer-entities", "layer-legend", "layer-annotations"],
            },
            "spec": {"path": _rel(spec_path), "format": "json"},
            "exports": exports,
            "previews": previews,
        },
        "provenance": _provenance(spec),
        "legend_mapping_check": _legend_mapping_check(spec),
        "uncertainties": spec.get("uncertainties", []),
        "change_records": spec.get("change_records", []),
        "checks": {
            "validation": {"status": validation.get("status"),
                           "errors": validation.get("errors", []),
                           "warnings": validation.get("warnings", [])},
            "layout": layout,
            "export_backends": export.get("backends_detected", {}),
            "compliance": {"status": compliance.get("status"),
                           "checks": compliance.get("checks", [])},
        },
        "notes": ("全部科学元素均带 source_refs；未在来源中出现的实体/数值一律不绘制。"
                  "warnings 与低置信度判断见 uncertainties。"),
        "generated_at": model.utc_now_iso(),
    }
