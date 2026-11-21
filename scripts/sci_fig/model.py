"""sci_fig.model
核心数据模型：图稿规格(spec)的读写、受控资产加载、单位换算、默认值归一化。

设计约定：
- spec 是唯一事实源（single source of truth），全部几何坐标使用毫米(mm)。
- 实体/关系/分组/数据源/图例中的每个科学元素都必须带 source_refs，指向 sources[].id。
- 渲染器只消费经过 validate 校验的 spec，不自行发明科学内容。
"""
from __future__ import annotations

import json
import datetime as _dt
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"

# submission/scripts/sci_fig/model.py -> 上溯三级到 submission/
_PKG_DIR = Path(__file__).resolve()
ASSETS_DIR = _PKG_DIR.parents[2] / "assets"

# 单位换算常量
MM_PER_INCH = 25.4
PT_PER_INCH = 72.0
MM_PER_PT = MM_PER_INCH / PT_PER_INCH  # 0.3527778
PT_PER_MM = PT_PER_INCH / MM_PER_INCH  # 2.8346457
PX_PER_INCH_REF = 96.0


class SpecError(Exception):
    """规格结构或内容错误。"""


def utc_now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- 基础换算
def mm_to_pt(mm: float) -> float:
    return float(mm) * PT_PER_MM


def pt_to_mm(pt: float) -> float:
    return float(pt) * MM_PER_PT


def mm_to_px(mm: float, dpi: float) -> float:
    return float(mm) / MM_PER_INCH * float(dpi)


def px_to_mm(px: float, dpi: float) -> float:
    return float(px) * MM_PER_INCH / float(dpi)


def pt_to_px(pt: float, dpi: float) -> float:
    return float(pt) / PT_PER_INCH * float(dpi)


# ---------------------------------------------------------------- JSON IO
def load_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise SpecError(f"文件不存在: {p}")
    try:
        with p.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise SpecError(f"JSON 解析失败 {p}: {exc}") from exc


def save_json(data: Any, path: str | Path, *, indent: int = 2) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=indent)
        fh.write("\n")
    return p


_ASSET_CACHE: dict[str, dict] = {}


def load_asset(name: str) -> dict[str, Any]:
    """加载 assets/ 下的受控资产（带缓存）。name 不含扩展名。"""
    if name not in _ASSET_CACHE:
        cand = ASSETS_DIR / f"{name}.json"
        if not cand.exists():
            raise SpecError(f"受控资产缺失: {cand}")
        _ASSET_CACHE[name] = load_json(cand)
    return _ASSET_CACHE[name]


# ---------------------------------------------------------------- 规格归一化
def new_spec(case_id: str = "", figure_id: str = "figure01") -> dict[str, Any]:
    """生成空白规格骨架，供 Agent 抽取阶段填充。"""
    return {
        "schema_version": SCHEMA_VERSION,
        "case_id": case_id,
        "figure": {
            "id": figure_id,
            "title": "",
            "type": "mechanism",
            "preset": "default_print",
            "canvas": {
                "width_mm": 120, "height_mm": 80, "dpi": 300,
                "color_space": "sRGB", "background": "#FFFFFF", "margin_mm": 8,
            },
            "font": {
                "family": "Liberation Sans", "size_pt": 8,
                "title_pt": 10, "label_pt": 7,
            },
            "stroke": {"width_pt": 1.0},
        },
        "sources": [],
        "entities": [],
        "relationships": [],
        "groups": [],
        "datasets": [],
        "legend": {"title": "Legend", "items": []},
        "annotations": [],
        "uncertainties": [],
        "change_records": [],
        "layout": {
            "engine": "hierarchical", "direction": "LR",
            "rank_sep_mm": 16, "node_sep_mm": 8, "padding_mm": 3,
        },
    }


def normalize_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """补齐缺失字段并应用预设默认值；不改变任何科学内容。"""
    base = new_spec(spec.get("case_id", ""), spec.get("figure", {}).get("id", "figure01"))
    for key, default in base.items():
        if key == "figure":
            fig = spec.get("figure", {})
            for sub, sub_default in default.items():
                if isinstance(sub_default, dict):
                    node = fig.setdefault(sub, {})
                    for k, v in sub_default.items():
                        node.setdefault(k, v)
                else:
                    fig.setdefault(sub, sub_default)
        else:
            spec.setdefault(key, default if not isinstance(default, (dict, list)) else type(default)())
    # 列表类保证存在
    for key in ("sources", "entities", "relationships", "groups",
                "datasets", "annotations", "uncertainties", "change_records"):
        spec.setdefault(key, [])
    spec.setdefault("legend", {"title": "Legend", "items": []})
    spec.setdefault("layout", base["layout"])
    spec["schema_version"] = spec.get("schema_version", SCHEMA_VERSION)
    return spec


def apply_preset(spec: dict[str, Any]) -> dict[str, Any]:
    """把期刊预设的基线参数写入 figure（仅填充未显式给出的值）。"""
    preset_name = spec.get("figure", {}).get("preset", "default_print")
    presets = load_asset("presets")["presets"]
    if preset_name not in presets:
        raise SpecError(f"未知预设 '{preset_name}'，可选: {sorted(presets)}")
    return presets[preset_name]


# ---------------------------------------------------------------- 受控词表查询
def relation_def(relation: str) -> dict[str, Any]:
    rels = load_asset("relation_vocab")["relations"]
    if relation not in rels:
        raise SpecError(f"未受控关系类型: {relation}")
    return rels[relation]


def entity_type_def(etype: str) -> dict[str, Any]:
    types = load_asset("entity_vocab")["entity_types"]
    if etype not in types:
        raise SpecError(f"未受控实体类型: {etype}")
    return types[etype]


def palette(name: str) -> dict[str, Any]:
    pals = load_asset("color_palettes")["palettes"]
    if name not in pals:
        raise SpecError(f"未知色板: {name}")
    return pals[name]


def semantic_color(key: str) -> str:
    return load_asset("color_palettes")["semantic_colors"][key]


def index_by_id(rows: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in rows:
        rid = row.get("id")
        if rid:
            out[rid] = row
    return out


def add_change_record(spec: dict[str, Any], action: str, element: str,
                      reason: str, operator: str = "agent") -> None:
    spec.setdefault("change_records", []).append({
        "timestamp": utc_now_iso(),
        "action": action,
        "element": element,
        "reason": reason,
        "operator": operator,
    })
