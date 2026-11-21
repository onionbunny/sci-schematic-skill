"""sci_fig.validate
图稿规格校验门（anti-hallucination gate）。

任何科学元素都必须能追溯到 sources；关系端头、受控词表、图例/数据映射、
矛盾与重复在这里被机器拦截。Agent 应在抽取后、布局前运行，按报告逐项修复，
直到 errors 为空。warnings 允许保留，但需在 uncertainties 中说明。
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from . import model


class _Report:
    def __init__(self) -> None:
        self.errors: list[dict[str, str]] = []
        self.warnings: list[dict[str, str]] = []
        self.info: list[dict[str, str]] = []

    def err(self, code: str, message: str, element: str = "") -> None:
        self.errors.append({"code": code, "message": message, "element": element})

    def warn(self, code: str, message: str, element: str = "") -> None:
        self.warnings.append({"code": code, "message": message, "element": element})

    def note(self, code: str, message: str, element: str = "") -> None:
        self.info.append({"code": code, "message": message, "element": element})


def _check_unique(rows: list[dict], kind: str, rep: _Report) -> set[str]:
    seen: dict[str, int] = defaultdict(int)
    for row in rows:
        rid = row.get("id", "")
        if not rid:
            rep.err("missing_id", f"{kind} 存在缺少 id 的条目", str(row)[:60])
            continue
        seen[rid] += 1
    for rid, n in seen.items():
        if n > 1:
            rep.err("duplicate_id", f"{kind} id 重复 {n} 次: {rid}", rid)
    return set(seen)


def _check_refs(element: dict, source_ids: set[str], rep: _Report, kind: str) -> None:
    eid = element.get("id", "?")
    refs = element.get("source_refs", [])
    if not refs:
        rep.err("no_provenance", f"{kind} {eid} 缺少 source_refs，无法追溯来源", eid)
        return
    for ref in refs:
        if ref not in source_ids:
            rep.err("bad_source_ref", f"{kind} {eid} 引用了不存在的来源 id: {ref}", eid)


def _detect_cycles(entities: list[dict], rels: list[dict], rep: _Report) -> None:
    adj: dict[str, list[str]] = defaultdict(list)
    for rel in rels:
        if rel.get("source") and rel.get("target"):
            adj[rel["source"]].append(rel["target"])
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {e["id"]: WHITE for e in entities if e.get("id")}
    cycles: list[list[str]] = []
    stack: list[str] = []

    def dfs(node: str) -> None:
        color[node] = GRAY
        stack.append(node)
        for nxt in adj.get(node, []):
            if nxt not in color:
                continue
            if color[nxt] == GRAY:
                idx = stack.index(nxt)
                cycles.append(stack[idx:] + [nxt])
            elif color[nxt] == WHITE:
                dfs(nxt)
        color[node] = BLACK
        stack.pop()

    for node in list(color):
        if color[node] == WHITE:
            dfs(node)
    for cyc in cycles:
        rep.note("feedback_cycle", f"检测到反馈环（生物学允许，布局将回退该边）: {' -> '.join(cyc)}", cyc[0])


def validate_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """对归一化后的 spec 执行全部硬校验，返回结构化报告。"""
    rep = _Report()
    spec = model.normalize_spec(spec)

    sources = spec["sources"]
    entities = spec["entities"]
    rels = spec["relationships"]
    groups = spec["groups"]
    datasets = spec["datasets"]
    legend = spec["legend"]["items"]

    source_ids = _check_unique(sources, "sources", rep)
    entity_ids = _check_unique(entities, "entities", rep)
    rel_ids = _check_unique(rels, "relationships", rep)
    group_ids = _check_unique(groups, "groups", rep)
    _check_unique(datasets, "datasets", rep)
    _check_unique(legend, "legend.items", rep)
    _check_unique(spec["annotations"], "annotations", rep)

    if not sources:
        rep.err("no_sources", "至少需要一个来源材料，否则任何实体都无法被追溯")

    # 受控词表
    rel_vocab = model.load_asset("relation_vocab")["relations"]
    ent_vocab = model.load_asset("entity_vocab")["entity_types"]
    palettes = model.load_asset("color_palettes")["palettes"]

    # 实体
    label_map: dict[str, set[str]] = defaultdict(set)
    container_ids: set[str] = set()
    for ent in entities:
        eid = ent.get("id", "?")
        if not ent.get("label"):
            rep.err("missing_label", f"实体 {eid} 缺少 label", eid)
        etype = ent.get("type", "")
        if etype not in ent_vocab:
            rep.err("bad_entity_type", f"实体 {eid} 类型未受控: {etype}", eid)
        else:
            if ent_vocab[etype]["shape"] == "container":
                container_ids.add(eid)
            label_map[ent.get("label", "")].add(etype)
        _check_refs(ent, source_ids, rep, "entity")
        if ent.get("value") not in (None, "") and not ent.get("unit"):
            rep.warn("missing_unit", f"实体 {eid} 给出数值 {ent.get('value')} 但未标注单位", eid)

    for label, types in label_map.items():
        if label and len(types) > 1:
            rep.warn("label_type_conflict",
                     f"同一标签 '{label}' 被赋予多个实体类型 {sorted(types)}，可能存在身份混淆", label)

    # 分组（区室）
    membership: dict[str, list[str]] = defaultdict(list)
    for grp in groups:
        gid = grp.get("id", "?")
        _check_refs(grp, source_ids, rep, "group")
        for member in grp.get("members", []):
            if member not in entity_ids:
                rep.err("bad_group_member", f"分组 {gid} 包含不存在的实体: {member}", gid)
            membership[member].append(gid)
    for eid, gs in membership.items():
        if len(gs) > 1:
            rep.err("multi_compartment", f"实体 {eid} 同时属于多个区室: {gs}", eid)

    # 关系
    pair_seen: set[tuple[str, str, str]] = set()
    polarity_pairs: dict[tuple[str, str], set[str]] = defaultdict(set)
    used_relations: set[str] = set()
    for rel in rels:
        rid = rel.get("id", "?")
        src, tgt = rel.get("source"), rel.get("target")
        if src not in entity_ids:
            rep.err("bad_endpoint", f"关系 {rid} 的起点不存在: {src}", rid)
        if tgt not in entity_ids:
            rep.err("bad_endpoint", f"关系 {rid} 的终点不存在: {tgt}", rid)
        if src in container_ids or tgt in container_ids:
            rep.err("endpoint_is_container", f"关系 {rid} 端头不能是区室容器，应连接容器内实体", rid)
        relation = rel.get("relation", "")
        if relation not in rel_vocab:
            rep.err("bad_relation", f"关系 {rid} 类型未受控: {relation}", rid)
        else:
            used_relations.add(relation)
            key = (src, tgt, relation)
            if key in pair_seen:
                rep.err("duplicate_relationship", f"重复关系: {src} {relation} {tgt}", rid)
            pair_seen.add(key)
            polarity_pairs[(src, tgt)].add(rel_vocab[relation]["polarity"])
        _check_refs(rel, source_ids, rep, "relationship")
    for pair, pols in polarity_pairs.items():
        if "positive" in pols and "negative" in pols:
            rep.warn("opposing_effects",
                     f"同一对实体 {pair[0]} -> {pair[1]} 同时存在正/负效应，需人工确认是否为不同条件下的真实调控",
                     pair[0])

    _detect_cycles(entities, rels, rep)

    # 数据集与数据映射
    for ds in datasets:
        did = ds.get("id", "?")
        if ds.get("source_ref") not in source_ids:
            rep.err("bad_dataset_source", f"数据集 {did} 的 source_ref 无效", did)
        columns = [c.get("name") if isinstance(c, dict) else c for c in ds.get("columns", [])]
        mapping = ds.get("mapping", {})
        color_by = mapping.get("color_by")
        if color_by is not None and color_by not in columns:
            rep.err("bad_mapping_column", f"数据集 {did} color_by 列不存在: {color_by}", did)
        pal_name = mapping.get("palette", "okabe_ito")
        if pal_name not in palettes:
            rep.err("bad_palette", f"数据集 {did} 使用未知色板: {pal_name}", did)
        cat_map = mapping.get("category_colors", {})
        rows = ds.get("rows", [])
        if color_by is not None and rows:
            idx = columns.index(color_by)
            observed = sorted({str(r[idx]) for r in rows})
            mapped = sorted(cat_map.keys())
            if mapped and observed != mapped:
                rep.err("legend_data_mismatch",
                        f"数据集 {did} 分类({observed})与映射键({mapped})不一致", did)
            if pal_name in palettes and not cat_map:
                if len(observed) > palettes[pal_name]["max_classes"]:
                    rep.err("palette_overflow",
                            f"数据集 {did} 分类数 {len(observed)} 超过色板 {pal_name} 上限", did)

    # 图例
    for item in legend:
        iid = item.get("id", "?")
        kind = item.get("kind")
        ref = item.get("ref")
        if kind == "relation" and ref not in rel_vocab:
            rep.err("bad_legend_ref", f"图例项 {iid} 引用未受控关系: {ref}", iid)
        if kind == "entity" and ref not in entity_ids:
            rep.err("bad_legend_ref", f"图例项 {iid} 引用不存在实体: {ref}", iid)
    legend_rels = {i.get("ref") for i in legend if i.get("kind") == "relation"}
    missing_legend = used_relations - legend_rels
    # 仅当图例本身用于解释关系（含 relation 条目）时，才要求关系类型齐全；
    # 纯分类/实体图例不强制关系条目。
    if missing_legend and legend_rels:
        rep.warn("legend_incomplete", f"图中使用但图例缺失的关系类型: {sorted(missing_legend)}")

    # 置信度与不确定性联动
    uncertain_elements = {u.get("element") for u in spec.get("uncertainties", [])}
    for ent in entities + rels:
        if ent.get("confidence") in ("low", "medium") and ent.get("id") not in uncertain_elements:
            rep.warn("confidence_unexplained",
                     f"{ent.get('id')} 置信度为 {ent.get('confidence')} 但 uncertainties 未说明",
                     ent.get("id", ""))

    # 画布/字体/预设基线
    try:
        preset = model.apply_preset(spec)
        fig = spec["figure"]
        canvas = fig["canvas"]
        if canvas["width_mm"] > preset["double_mm"] + 1:
            rep.warn("canvas_too_wide",
                     f"画布宽 {canvas['width_mm']}mm 超过预设 {preset['double_mm']}mm")
        if canvas["dpi"] < preset["raster_dpi"]:
            rep.warn("dpi_below_preset",
                     f"位图 DPI {canvas['dpi']} 低于预设 {preset['raster_dpi']}")
        if canvas["color_space"] not in ("sRGB", "RGB"):
            rep.err("bad_color_space", f"色彩空间 {canvas['color_space']} 不被期刊位图接受")
        if fig["font"]["family"] not in preset["font_families"]:
            rep.warn("font_not_in_preset",
                     f"字体 {fig['font']['family']} 不在预设名单 {preset['font_families']}")
        if fig["font"]["size_pt"] < preset["font_min_pt"]:
            rep.warn("font_too_small", f"字号 {fig['font']['size_pt']}pt 低于预设下限")
        if fig["stroke"]["width_pt"] < preset["stroke_min_pt"]:
            rep.warn("stroke_too_thin", f"线宽 {fig['stroke']['width_pt']}pt 低于预设下限")
    except model.SpecError as exc:
        rep.err("preset_error", str(exc))

    referenced = {r for el in entities + rels + groups for r in el.get("source_refs", [])}
    for sid in source_ids - referenced:
        rep.warn("unused_source", f"来源 {sid} 未被任何元素引用", sid)

    provenance_total = len(entities) + len(rels) + len(groups)
    provenance_ok = sum(1 for el in entities + rels + groups if el.get("source_refs"))
    coverage = 1.0 if provenance_total == 0 else round(provenance_ok / provenance_total, 4)

    return {
        "status": "pass" if not rep.errors else "fail",
        "schema_version": model.SCHEMA_VERSION,
        "errors": rep.errors,
        "warnings": rep.warnings,
        "info": rep.info,
        "counts": {
            "sources": len(sources), "entities": len(entities),
            "relationships": len(rels), "groups": len(groups),
            "datasets": len(datasets), "legend_items": len(legend),
        },
        "provenance_coverage": coverage,
    }
