"""sci_fig.layout
确定性分层布局引擎（Sugiyama 风格的精简实现，质量优先版）。

能力：
- 文本测量驱动：节点按标签撑开，标题自动缩号/换行，图例按标签动态定宽；
- 反馈环识别并回退环路边，最长路径分层，重心法减少交叉，区室成员分块聚簇；
- 端口分布：同一节点的多条出入边在边界均分端口，消除扇出重叠；
- 正交折线布线，反馈边从整体底部绕行，标签落在水平段并带白描边；
- 容器防重叠迭代与画布溢出检测。只做几何，不修改科学语义。全部坐标 mm。
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from . import model


# 相对字宽（em），用于无字体引擎环境下的文本尺寸估算
_W = defaultdict(lambda: 0.55)
_W.update({
    " ": 0.28, "i": 0.27, "l": 0.27, "j": 0.3, "t": 0.33, "f": 0.34,
    "r": 0.38, "s": 0.44, "e": 0.52, "a": 0.52, "n": 0.56, "o": 0.57,
    "c": 0.52, "d": 0.56, "u": 0.56, "m": 0.83, "w": 0.78, "h": 0.56,
    ".": 0.3, ",": 0.3, "-": 0.35, ":": 0.3, ";": 0.3, "/": 0.32,
    "0": 0.56, "1": 0.56, "2": 0.56, "3": 0.56, "4": 0.56,
    "5": 0.56, "6": 0.56, "7": 0.56, "8": 0.56, "9": 0.56,
})
_UPPER = 0.72


def text_w_mm(text: str, font_pt: float) -> float:
    em = sum(_UPPER if ch.isupper() else _W[ch] for ch in str(text))
    return em * font_pt * model.MM_PER_PT


# 各 glyph 的端头间隙(mm)：路径终点在节点边界前缩短的距离，保证端头不被
# 后渲染的白色节点覆盖。箭头/圆形端头以 refX 令其前沿贴边界，间隙为 0；
# T 形端头(refX=0)需要外移。
GLYPH_CLEARANCE_MM = {
    "arrow": 0.0, "open_arrow": 0.0, "circle": 0.0, "arrow_circle": 0.0,
    "diamond": 0.0, "line": 0.0, "tbar": 0.7,
}


def _shorten_last(points: list[list[float]], clearance: float) -> list[list[float]]:
    """把路径终点沿最后一段朝内缩短 clearance(mm)。"""
    if clearance <= 0 or len(points) < 2:
        return points
    x2, y2 = points[-1]; x1, y1 = points[-2]
    dx, dy = x2 - x1, y2 - y1
    length = (dx * dx + dy * dy) ** 0.5
    if length <= 0:
        return points
    move = min(clearance, length * 0.9)
    k = move / length
    points[-1] = [round(x2 - dx * k, 3), round(y2 - dy * k, 3)]
    return points


def _wrap(text: str, size_pt: float, max_w_mm: float) -> list[str]:
    words = str(text).split()
    lines: list[str] = []; cur = ""
    for w in words:
        trial = w if not cur else f"{cur} {w}"
        if text_w_mm(trial, size_pt) <= max_w_mm or not cur:
            cur = trial
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines


def _rects_overlap(a: dict, b: dict, tol: float = 0.05) -> bool:
    return not (a["x"] + a["w"] <= b["x"] + tol or b["x"] + b["w"] <= a["x"] + tol
                or a["y"] + a["h"] <= b["y"] + tol or b["y"] + b["h"] <= a["y"] + tol)


def _find_feedback(ids: set[str], adj: dict[str, list[str]]) -> set[tuple[str, str]]:
    color = {n: 0 for n in ids}; feedback: set[tuple[str, str]] = set()

    def dfs(u: str) -> None:
        color[u] = 1
        for v in adj.get(u, []):
            if v not in color:
                continue
            if color[v] == 1:
                feedback.add((u, v))
            elif color[v] == 0:
                dfs(v)
        color[u] = 2

    for n in ids:
        if color[n] == 0:
            dfs(n)
    return feedback


# ---------------------------------------------------------------- 标题
def _layout_title(spec: dict) -> dict:
    fig = spec["figure"]; margin = fig["canvas"]["margin_mm"]
    W = fig["canvas"]["width_mm"]
    panel = next((a for a in spec["annotations"] if a.get("kind") == "panel_label"), None)
    panel_w = text_w_mm(panel["text"], fig["font"]["size_pt"] + 2) + 4 if panel else 0
    avail = W - 2 * margin - panel_w
    size = fig["font"]["title_pt"]; body = fig["font"]["size_pt"]
    lines = [fig.get("title", "")]
    while size > body:
        if text_w_mm(fig["title"], size) <= avail:
            break
        size -= 0.5
    if text_w_mm(fig["title"], size) > avail:
        lines = _wrap(fig["title"], size, avail)[:2]
    band = 3.6 if len(lines) == 1 else 7.6
    baselines = ([margin + 2.9] if len(lines) == 1
                 else [margin + 2.6, margin + 6.4])
    return {"lines": lines, "size_pt": round(size, 2),
            "baselines": baselines, "band_mm": band}


# ---------------------------------------------------------------- 图例
def _layout_legend(spec: dict, y_top: float) -> dict:
    fig = spec["figure"]; W = fig["canvas"]["width_mm"]
    margin = fig["canvas"]["margin_mm"]
    lpt = fig["font"]["label_pt"]
    items = spec["legend"]["items"]
    pad = 2.0; row_h = 5.4; title_h = 5.0
    max_w = text_w_mm(spec["legend"].get("title", "Legend"), lpt + 0.5)
    for it in items:
        max_w = max(max_w, 8.0 + text_w_mm(it.get("label", ""), lpt))
    legend_w = max_w + 2 * pad
    legend_h = title_h + len(items) * row_h + pad
    x = W - margin - legend_w; y = y_top
    geom = {"x": round(x, 3), "y": round(y, 3), "w": round(legend_w, 3),
            "h": round(legend_h, 3), "title_y": round(y + 3.4, 3), "rows": []}
    ry = y + title_h
    for it in items:
        geom["rows"].append({
            "id": it["id"], "swatch_x": round(x + pad, 3),
            "swatch_y": round(ry + 1.2, 3),
            "label_x": round(x + pad + 8.0, 3),
            "label_y": round(ry + 2.9, 3)})
        ry += row_h
    return geom


def _manual_layout(spec: dict, entities: dict, rels: list) -> dict:
    """保源编辑布局：保留实体显式坐标/尺寸与 id，仅重算关系路由与容器边界。

    要求每个实体已带 position 与 size；缺失则报错。关系若显式给 route_points
    则原样使用，否则按相对位置在边界端口间生成直线/正交路由。
    """
    warnings: list[dict] = []
    for eid, ent in entities.items():
        if not ent.get("position") or not ent.get("size"):
            warnings.append({"code": "manual_needs_geometry",
                             "message": f"手动模式要求实体 {eid} 提供 position 与 size",
                             "element": eid})

    def center(eid):
        p, s = entities[eid]["position"], entities[eid]["size"]
        return p["x_mm"] + s["w_mm"] / 2, p["y_mm"] + s["h_mm"] / 2

    for rel in rels:
        glyph = model.relation_def(rel["relation"])["glyph"]
        clearance = GLYPH_CLEARANCE_MM.get(glyph, 0.0)
        if rel.get("route_points"):
            pts = _shorten_last([list(p) for p in rel["route_points"]], clearance)
            rel["route"] = {"points": pts,
                            "label_pos": [round(sum(p[0] for p in pts) / len(pts), 3),
                                          round(sum(p[1] for p in pts) / len(pts), 3)]}
            continue
        s, t = rel["source"], rel["target"]
        csx, csy = center(s); ctx, cty = center(t)
        ps, ss = entities[s]["position"], entities[s]["size"]
        pt, st = entities[t]["position"], entities[t]["size"]
        if abs(csy - cty) < 0.5:  # 水平对齐：边界直连
            sp = (ps["x_mm"] + ss["w_mm"], csy); tp = (pt["x_mm"], cty)
            points = [[sp[0], sp[1]], [tp[0], tp[1]]]
        else:  # 正交折线
            midx = (ps["x_mm"] + ss["w_mm"] + pt["x_mm"]) / 2
            points = [[ps["x_mm"] + ss["w_mm"], csy], [midx, csy],
                      [midx, cty], [pt["x_mm"], cty]]
        points = _shorten_last(points, clearance)
        rel["route"] = {"points": [[round(a, 3), round(b, 3)] for a, b in points],
                        "label_pos": [round((csx + ctx) / 2, 3), round((csy + cty) / 2, 3)]}

    # 容器边界（若有分组）
    pad = spec["layout"].get("padding_mm", 3)
    for grp in spec["groups"]:
        members = [m for m in grp.get("members", []) if m in entities]
        if not members:
            continue
        xs = [entities[m]["position"]["x_mm"] for m in members]
        ys = [entities[m]["position"]["y_mm"] for m in members]
        xe = [entities[m]["position"]["x_mm"] + entities[m]["size"]["w_mm"] for m in members]
        ye = [entities[m]["position"]["y_mm"] + entities[m]["size"]["h_mm"] for m in members]
        grp["bounds"] = {
            "x_mm": round(min(xs) - pad, 3), "y_mm": round(min(ys) - pad - 4.5, 3),
            "w_mm": round(max(xe) - min(xs) + 2 * pad, 3),
            "h_mm": round(max(ye) - min(ys) + 2 * pad + 4.5, 3)}

    # 标注/图例定位
    for ann in spec["annotations"]:
        if not ann.get("position"):
            ann["position"] = {"x_mm": spec["figure"]["canvas"]["margin_mm"],
                               "y_mm": spec["figure"]["canvas"]["margin_mm"] + 2.9}
    if spec["legend"]["items"]:
        spec["legend"]["geom"] = _layout_legend(
            spec, spec["figure"]["canvas"]["margin_mm"])

    for eid, ent in entities.items():
        p, s = ent["position"], ent["size"]
        if (p["x_mm"] < 0 or p["y_mm"] < 0
                or p["x_mm"] + s["w_mm"] > spec["figure"]["canvas"]["width_mm"]
                or p["y_mm"] + s["h_mm"] > spec["figure"]["canvas"]["height_mm"]):
            warnings.append({"code": "canvas_overflow", "message": f"节点 {eid} 超出画布",
                             "element": eid})
    return {"status": "pass" if not warnings else "warn", "mode": "manual",
            "preserved_ids": [e for e in entities], "warnings": warnings}


def run_layout(spec: dict[str, Any]) -> dict[str, Any]:
    spec = model.normalize_spec(spec)
    fig = spec["figure"]; canvas = fig["canvas"]
    font_pt = fig["font"]["size_pt"]; lp = spec["layout"]

    ent_vocab = model.load_asset("entity_vocab")["entity_types"]
    entities = {e["id"]: e for e in spec["entities"] if e.get("id")}
    rels = [r for r in spec["relationships"]
            if r.get("source") in entities and r.get("target") in entities]

    # 保源编辑：手动坐标模式，保留原 id/位置，仅重算关系端头与几何
    if lp.get("engine") == "manual":
        return _manual_layout(spec, entities, rels)

    margin = canvas["margin_mm"]; rank_sep = lp["rank_sep_mm"]
    node_sep0 = lp["node_sep_mm"]; pad = lp["padding_mm"]
    horizontal = lp.get("direction", "LR") == "LR"

    # 标题带
    title_info = _layout_title(spec) if fig.get("title") else None
    title_band = title_info["band_mm"] if title_info else 0.0

    y0 = margin + title_band
    # 先给图例估算宽度（依赖 y0 仅用于纵向位置）
    legend_geom = _layout_legend(spec, y0) if spec["legend"]["items"] else None
    legend_w = (legend_geom["w"] + 5.0) if legend_geom else 0.0
    x0 = margin
    content_w = canvas["width_mm"] - 2 * margin - legend_w
    content_h = canvas["height_mm"] - y0 - margin

    # 1) 节点尺寸
    for eid, ent in entities.items():
        tdef = ent_vocab.get(ent.get("type"), ent_vocab["protein"])
        tw = text_w_mm(ent.get("label", ""), font_pt)
        ent["size"] = {"w_mm": round(max(tdef["default_w_mm"], tw + 2 * pad + 2), 3),
                       "h_mm": tdef["default_h_mm"]}

    # 2) 图、反馈边、分层
    adj: dict[str, list[str]] = defaultdict(list)
    pol_order = {p: i for i, p in enumerate(
        ("positive", "neutral", "contextual", "negative"))}
    rel_by_pair: dict[tuple[str, str], dict] = {}
    for rel in rels:
        adj[rel["source"]].append(rel["target"])
        rel_by_pair[(rel["source"], rel["target"])] = rel
    # 极性感知：正效应边优先访问，负效应返回边垫后，使 DFS 稳定地把返回边判为回边
    ordered_adj: dict[str, list[str]] = {}
    for u, vs in adj.items():
        ordered_adj[u] = sorted(
            vs, key=lambda v: pol_order.get(
                model.relation_def(rel_by_pair[(u, v)]["relation"])["polarity"], 1))
    feedback = _find_feedback(set(entities), ordered_adj)
    dag_edges = [(r["source"], r["target"]) for r in rels
                 if (r["source"], r["target"]) not in feedback]
    for rel in rels:
        rel["is_feedback"] = (rel["source"], rel["target"]) in feedback
    preds: dict[str, list[str]] = defaultdict(list)
    for s, t in dag_edges:
        preds[t].append(s)
    rank: dict[str, int] = {}; guard = 0; changed = True
    while changed and guard < len(entities) + 2:
        changed = False; guard += 1
        for eid in entities:
            ps = [p for p in preds[eid] if p in rank]
            nr = 0 if not preds[eid] else (
                1 + max(rank[p] for p in ps) if len(ps) == len(preds[eid]) else rank.get(eid, 0))
            if nr != rank.get(eid, -1):
                rank[eid] = nr; changed = True
    for eid in entities:
        rank.setdefault(eid, 0)
    ranks: dict[int, list[str]] = defaultdict(list)
    for eid, rk in rank.items():
        ranks[rk].append(eid)

    # 3) 重心排序 + 区室分块
    succ: dict[str, list[str]] = defaultdict(list)
    for s, t in dag_edges:
        succ[s].append(t)
    order = {rk: sorted(lst) for rk, lst in ranks.items()}
    for _ in range(2):
        for rk in sorted(ranks):
            def pos(n: str) -> float:
                ns = [x for x in succ[n] if x in order.get(rk + 1, [])]
                if not ns:
                    return order[rk].index(n)
                nxt = order[rk + 1]
                return sum(nxt.index(x) for x in ns) / len(ns)
            order[rk] = sorted(order[rk], key=pos)

    def grp_of(eid: str) -> str:
        for g in spec["groups"]:
            if eid in g.get("members", []):
                return g["id"]
        return "~"

    for rk in order:
        order[rk] = sorted(order[rk], key=lambda n: (grp_of(n), order[rk].index(n)))

    # 4) 坐标 + 容器防重叠迭代
    max_w = max((e["size"]["w_mm"] for e in entities.values()), default=20)
    n_ranks = max(ranks.keys(), default=0) + 1
    rank_pitch = max_w + rank_sep
    if (n_ranks - 1) * rank_pitch + max_w > content_w and n_ranks > 1:
        rank_pitch = max(max_w + 2 * pad, (content_w - max_w) / (n_ranks - 1))

    node_sep = node_sep0; warnings: list[dict] = []
    for attempt in range(6):
        col_heights = {
            rk: (sum(entities[n]["size"]["h_mm"] for n in order[rk])
                 + node_sep * (len(order[rk]) - 1)) for rk in order}
        for rk, nodes in order.items():
            if horizontal:
                x = x0 + rk * rank_pitch
                y = y0 + max(0.0, (content_h - col_heights[rk]) / 2)
                for n in nodes:
                    entities[n]["position"] = {"x_mm": round(x, 3), "y_mm": round(y, 3)}
                    y += entities[n]["size"]["h_mm"] + node_sep
            else:
                y = y0 + rk * rank_pitch
                x = x0 + max(0.0, (content_w - col_heights[rk]) / 2)
                for n in nodes:
                    entities[n]["position"] = {"x_mm": round(x, 3), "y_mm": round(y, 3)}
                    x += entities[n]["size"]["w_mm"] + node_sep
        for grp in spec["groups"]:
            members = [m for m in grp.get("members", []) if m in entities]
            if not members:
                continue
            xs = [entities[m]["position"]["x_mm"] for m in members]
            ys = [entities[m]["position"]["y_mm"] for m in members]
            xe = [entities[m]["position"]["x_mm"] + entities[m]["size"]["w_mm"] for m in members]
            ye = [entities[m]["position"]["y_mm"] + entities[m]["size"]["h_mm"] for m in members]
            grp["bounds"] = {
                "x_mm": round(min(xs) - pad, 3), "y_mm": round(min(ys) - pad - 4.5, 3),
                "w_mm": round(max(xe) - min(xs) + 2 * pad, 3),
                "h_mm": round(max(ye) - min(ys) + 2 * pad + 4.5, 3)}
        bounds = [{"x": g["bounds"]["x_mm"], "y": g["bounds"]["y_mm"],
                   "w": g["bounds"]["w_mm"], "h": g["bounds"]["h_mm"], "id": g["id"]}
                  for g in spec["groups"] if g.get("bounds")]
        clash = any(_rects_overlap(bounds[i], bounds[j])
                    for i in range(len(bounds)) for j in range(i + 1, len(bounds)))
        if not clash:
            break
        node_sep += 4.0

    # 5) 端口分布
    out_edges: dict[str, list[str]] = defaultdict(list)
    in_edges: dict[str, list[str]] = defaultdict(list)
    fb_src: dict[str, list[str]] = defaultdict(list); fb_tgt: dict[str, list[str]] = defaultdict(list)
    for rel in rels:
        if rel["is_feedback"]:
            fb_src[rel["source"]].append(rel["id"]); fb_tgt[rel["target"]].append(rel["id"])
        else:
            out_edges[rel["source"]].append(rel["id"]); in_edges[rel["target"]].append(rel["id"])

    def port(eid: str, frac: float, side: str) -> tuple[float, float]:
        p, s = entities[eid]["position"], entities[eid]["size"]
        if side == "right":
            return p["x_mm"] + s["w_mm"], p["y_mm"] + frac * s["h_mm"]
        if side == "left":
            return p["x_mm"], p["y_mm"] + frac * s["h_mm"]
        if side == "bottom":
            return p["x_mm"] + frac * s["w_mm"], p["y_mm"] + s["h_mm"]
        return p["x_mm"] + frac * s["w_mm"], p["y_mm"]

    ports: dict[str, dict[str, tuple[float, float]]] = defaultdict(dict)
    for eid in entities:
        for i, rid in enumerate(out_edges[eid]):
            ports[rid]["src"] = port(eid, (i + 0.5) / max(1, len(out_edges[eid])), "right")
        for i, rid in enumerate(in_edges[eid]):
            ports[rid]["tgt"] = port(eid, (i + 0.5) / max(1, len(in_edges[eid])), "left")
        for i, rid in enumerate(fb_src[eid]):
            # 起点靠节点右下外侧，避免穿过正下方同列节点
            frac = max(0.15, 0.85 - 0.25 * i)
            ports[rid]["src"] = port(eid, frac, "bottom")
        for i, rid in enumerate(fb_tgt[eid]):
            # 终点靠节点左下外侧
            frac = min(0.85, 0.15 + 0.25 * i)
            ports[rid]["tgt"] = port(eid, frac, "bottom")

    # 6) 布线
    global_bottom = max(e["position"]["y_mm"] + e["size"]["h_mm"] for e in entities.values())
    fb_lane = global_bottom + 8.0
    for rel in rels:
        sp, tp = ports[rel["id"]]["src"], ports[rel["id"]]["tgt"]
        if rel["is_feedback"]:
            points = [[sp[0], sp[1]], [sp[0], fb_lane], [tp[0], fb_lane], [tp[0], tp[1]]]
            lpos = [(sp[0] + tp[0]) / 2, fb_lane - 1.2]
        elif rank[rel["source"]] == rank[rel["target"]]:
            off = 4.0
            points = [[sp[0], sp[1]], [sp[0] + off, sp[1]],
                      [sp[0] + off, tp[1]], [tp[0], tp[1]]]
            lpos = [sp[0] + off + 0.5, (sp[1] + tp[1]) / 2]
        else:
            midx = (sp[0] + tp[0]) / 2
            points = [[sp[0], sp[1]], [midx, sp[1]], [midx, tp[1]], [tp[0], tp[1]]]
            lpos = [midx, (sp[1] + tp[1]) / 2]
        glyph = model.relation_def(rel["relation"])["glyph"]
        points = _shorten_last(points, GLYPH_CLEARANCE_MM.get(glyph, 0.0))
        rel["route"] = {"points": [[round(a, 3), round(b, 3)] for a, b in points],
                        "label_pos": [round(lpos[0], 3), round(lpos[1], 3)]}

    # 7) 标注定位
    for ann in spec["annotations"]:
        if ann.get("position"):
            continue
        if ann.get("kind") == "panel_label":
            ann["position"] = {"x_mm": margin, "y_mm": margin + 2.9}
        else:
            ann["position"] = {"x_mm": margin, "y_mm": canvas["height_mm"] - margin}

    # 8) 检测
    rects = [{"x": e["position"]["x_mm"], "y": e["position"]["y_mm"],
              "w": e["size"]["w_mm"], "h": e["size"]["h_mm"], "id": eid}
             for eid, e in entities.items()]
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            if _rects_overlap(rects[i], rects[j]):
                warnings.append({"code": "node_overlap",
                                 "message": f"节点重叠 {rects[i]['id']} / {rects[j]['id']}"})
    for eid, e in entities.items():
        p, s = e["position"], e["size"]
        if (p["x_mm"] < 0 or p["y_mm"] < 0
                or p["x_mm"] + s["w_mm"] > canvas["width_mm"]
                or p["y_mm"] + s["h_mm"] > canvas["height_mm"]):
            warnings.append({"code": "canvas_overflow", "message": f"节点 {eid} 超出画布", "element": eid})
    if legend_geom:
        spec["legend"]["geom"] = legend_geom
    if title_info:
        fig["title_render"] = title_info
    for grp in spec["groups"]:
        b = grp.get("bounds")
        if b and (b["x_mm"] < 0 or b["y_mm"] < 0
                  or b["x_mm"] + b["w_mm"] > canvas["width_mm"]
                  or b["y_mm"] + b["h_mm"] > canvas["height_mm"]):
            warnings.append({"code": "container_overflow", "message": f"区室 {grp['id']} 超出画布", "element": grp["id"]})

    # 边标签与节点碰撞：长标签会被节点遮挡，提示缩短或改道
    lpt = fig["font"]["label_pt"]
    for rel in rels:
        if not rel.get("label"):
            continue
        lx, ly = rel["route"]["label_pos"]
        lw = text_w_mm(rel["label"], lpt); lh = model.pt_to_mm(lpt)
        label_rect = {"x": lx - lw / 2, "y": ly - lh / 2, "w": lw, "h": lh}
        for rc in rects:
            if _rects_overlap(label_rect, rc, tol=0.0):
                warnings.append({
                    "code": "edge_label_collision",
                    "message": f"边 {rel['id']} 标签 '{rel['label']}' 与节点 {rc['id']} 重叠，应缩短标签或改道",
                    "element": rel["id"]})
                break

    return {
        "status": "pass" if not warnings else "warn",
        "direction": lp.get("direction", "LR"),
        "ranks": {str(k): v for k, v in order.items()},
        "feedback_edges": [{"rel_id": r["id"], "edge": [r["source"], r["target"]]}
                          for r in rels if r["is_feedback"]],
        "rank_pitch_mm": round(rank_pitch, 3),
        "node_sep_used_mm": round(node_sep, 3),
        "warnings": warnings,
    }
