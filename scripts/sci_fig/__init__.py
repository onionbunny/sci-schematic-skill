"""sci_fig：科研示意图生成与编辑技能的可执行工具包。

模块划分：
  model      规格/资产/单位
  ingest     读取 case.json、task.md 与各类科研材料
  validate   实体关系完整性与防幻觉校验门
  layout     分层布局与正交布线路径
  svg_render 分层可编辑 SVG 渲染
  export     多后端 PDF/PNG/TIFF/EPS 导出
  compliance 导出件期刊合规检查
  result     result.json 组装
"""

__version__ = "1.0.0"
