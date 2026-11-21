#!/usr/bin/env python3
"""scifig.py — 科研示意图生成与编辑技能的统一命令行入口。

子命令：
  ingest    读取 /input 材料，生成 work/ingest_bundle.json 与 reading/ 文本
  validate  校验 spec（防幻觉门），输出校验报告
  layout    运行分层布局，坐标/路由写回 spec
  render    由 spec 渲染分层可编辑 SVG
  export    导出 pdf/png/tiff/eps（多后端自动降级）
  check     导出件合规检查
  pipeline  顺序执行 validate->layout->render->export->check->result.json
  backends  探测当前环境可用导出后端
  new       生成空白 spec 骨架

用法示例：
  python3 scifig.py ingest --input /input --work /app/work
  python3 scifig.py pipeline --spec /app/work/spec.json --output /app/output
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 不在技能目录内写 .pyc，保持提交包为纯 UTF-8 文本且文件数稳定
sys.dont_write_bytecode = True

# 保证以任意 cwd 调用时都能导入同级 sci_fig 包
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sci_fig import model, validate, layout, svg_render, export, compliance, result, ingest  # noqa: E402


def _cmd_ingest(a: argparse.Namespace) -> int:
    bundle = ingest.run_ingest(a.input, a.work)
    n = len(bundle["sources"])
    print(f"[ingest] 已登记 {n} 个来源 -> {Path(a.work) / 'ingest_bundle.json'}")
    for s in bundle["sources"]:
        print(f"  {s['id']:<4}{s['kind']:<6}{s['name']}")
    for w in bundle["warnings"]:
        print(f"  [warn] {w}")
    return 0


def _cmd_validate(a: argparse.Namespace) -> int:
    spec = model.load_json(a.spec)
    rep = validate.validate_spec(spec)
    model.save_json(rep, a.report) if a.report else None
    print(f"[validate] {rep['status']} | errors={len(rep['errors'])} "
          f"warnings={len(rep['warnings'])} provenance={rep['provenance_coverage']}")
    for e in rep["errors"]:
        print(f"  ERROR {e['code']}: {e['message']}")
    for w in rep["warnings"]:
        print(f"  warn  {w['code']}: {w['message']}")
    return 0 if rep["status"] == "pass" else 2


def _cmd_layout(a: argparse.Namespace) -> int:
    spec = model.load_json(a.spec)
    rep = layout.run_layout(spec)
    model.save_json(spec, a.spec)  # 坐标写回
    model.save_json(rep, a.report) if a.report else None
    print(f"[layout] {rep['status']} | ranks={len(rep['ranks'])} "
          f"feedback={len(rep['feedback_edges'])} depth={rep['content_depth_mm']}mm")
    for w in rep["warnings"]:
        print(f"  warn {w['code']}: {w['message']}")
    return 0


def _cmd_render(a: argparse.Namespace) -> int:
    spec = model.load_json(a.spec)
    svg = svg_render.render_svg(spec)
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8")
    print(f"[render] SVG -> {out} ({len(svg)} bytes)")
    return 0


def _cmd_export(a: argparse.Namespace) -> int:
    spec = model.load_json(a.spec)
    svg_path = Path(a.svg) if a.svg else Path(a.spec).with_suffix(".svg")
    if not svg_path.exists():
        svg_path.write_text(svg_render.render_svg(spec), encoding="utf-8")
    rep = export.export_artifacts(spec, svg_path, a.output, a.formats.split(","))
    model.save_json(rep, Path(a.output) / "export_report.json")
    print(f"[export] all_ok={rep['all_ok']}")
    for r in rep["artifacts"]:
        tag = "ok " if r.get("ok") else "FAIL"
        print(f"  {tag} {r['format']:<5}{r.get('backend', '')} {r.get('path', '')} {r.get('error', '')}")
    return 0 if rep["all_ok"] else 3


def _cmd_check(a: argparse.Namespace) -> int:
    spec = model.load_json(a.spec)
    rep = compliance.check_compliance(spec, a.files)
    model.save_json(rep, a.report) if a.report else None
    print(f"[check] {rep['status']}")
    for c in rep["checks"]:
        print(f"  {'ok ' if c['ok'] else 'FAIL'} {c.get('format', '')} {c['file']}")
        for issue in c.get("issues", []):
            print(f"       - {issue}")
    return 0 if rep["status"] == "pass" else 4


def _cmd_pipeline(a: argparse.Namespace) -> int:
    work = Path(a.work) if a.work else Path(a.spec).parent
    out_dir = Path(a.output); out_dir.mkdir(parents=True, exist_ok=True)
    spec = model.normalize_spec(model.load_json(a.spec))
    fig_id = spec["figure"]["id"]

    vrep = validate.validate_spec(spec)
    model.save_json(vrep, work / "validation_report.json")
    print(f"[1/6] validate: {vrep['status']} ({len(vrep['errors'])} errors)")
    if vrep["status"] == "fail":
        # 不阻断：产出诚实的失败结果，便于复核
        print("[pipeline] 校验未通过，仍生成可检查的部分结果")

    lrep = layout.run_layout(spec)
    model.save_json(spec, a.spec)
    print(f"[2/6] layout: {lrep['status']} ({len(lrep['warnings'])} warnings)")

    svg_path = out_dir / f"{fig_id}.svg"
    svg_path.write_text(svg_render.render_svg(spec), encoding="utf-8")
    print(f"[3/6] render: {svg_path}")

    formats = [f.strip() for f in a.formats.split(",") if f.strip()]
    erep = export.export_artifacts(spec, svg_path, out_dir, formats)
    model.save_json(erep, out_dir / "export_report.json")
    print(f"[4/6] export: all_ok={erep['all_ok']}")

    artifact_files = [r["path"] for r in erep["artifacts"] if r.get("ok")]
    crep = compliance.check_compliance(spec, artifact_files)
    model.save_json(crep, out_dir / "compliance_report.json")
    print(f"[5/6] compliance: {crep['status']}")

    spec_out = out_dir / "spec.json"
    model.save_json(spec, spec_out)
    rj = result.build_result(
        spec, validation=vrep, layout=lrep, export=erep, compliance=crep,
        output_dir=out_dir, spec_path=spec_out, svg_path=svg_path)
    model.save_json(rj, out_dir / "result.json")
    print(f"[6/6] result.json: status={rj['status']} -> {out_dir / 'result.json'}")
    return 0 if rj["status"] == "success" else 5


def _cmd_backends(_a: argparse.Namespace) -> int:
    for k, v in export.detect_backends().items():
        print(f"  {k:<14}{v}")
    return 0


def _cmd_new(a: argparse.Namespace) -> int:
    model.save_json(model.new_spec(a.case_id, a.figure_id), a.spec)
    print(f"[new] 空白 spec -> {a.spec}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="scifig", description="科研示意图生成与编辑")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("ingest"); s.add_argument("--input", required=True)
    s.add_argument("--work", required=True); s.set_defaults(fn=_cmd_ingest)

    s = sub.add_parser("validate"); s.add_argument("--spec", required=True)
    s.add_argument("--report"); s.set_defaults(fn=_cmd_validate)

    s = sub.add_parser("layout"); s.add_argument("--spec", required=True)
    s.add_argument("--report"); s.set_defaults(fn=_cmd_layout)

    s = sub.add_parser("render"); s.add_argument("--spec", required=True)
    s.add_argument("--output", required=True); s.set_defaults(fn=_cmd_render)

    s = sub.add_parser("export"); s.add_argument("--spec", required=True)
    s.add_argument("--svg"); s.add_argument("--output", required=True)
    s.add_argument("--formats", default="pdf,png"); s.set_defaults(fn=_cmd_export)

    s = sub.add_parser("check"); s.add_argument("--spec", required=True)
    s.add_argument("--files", nargs="+", required=True)
    s.add_argument("--report"); s.set_defaults(fn=_cmd_check)

    s = sub.add_parser("pipeline"); s.add_argument("--spec", required=True)
    s.add_argument("--output", required=True); s.add_argument("--work")
    s.add_argument("--formats", default="svg,pdf,png,tiff")
    s.set_defaults(fn=_cmd_pipeline)

    s = sub.add_parser("backends"); s.set_defaults(fn=_cmd_backends)

    s = sub.add_parser("new"); s.add_argument("--spec", required=True)
    s.add_argument("--case-id", default=""); s.add_argument("--figure-id", default="figure01")
    s.set_defaults(fn=_cmd_new)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
