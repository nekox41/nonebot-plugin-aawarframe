# renderers/__init__.py

from pathlib import Path
from .html_renderer import HtmlImageRenderer
from ..data_processor import render_archimedea_panel  # 导入我们定义的函数

# 确定模板目录
TEMPLATE_DIR = Path(__file__).parent.parent / "assets" / "templates"
OUTPUT_DIR = Path(__file__).parent.parent / "images"   # 用于缓存

# 创建全局渲染器实例
renderer = HtmlImageRenderer(
    template_dir=TEMPLATE_DIR,
    output_dir=OUTPUT_DIR,
)

# 注册 archimedea 模板，同时指定该模板专属的渲染参数
renderer.register_renderer(
    template_type="archimedea",
    func=render_archimedea_panel,
    config={
        "max_width": 1060,       # archimedea 需要更宽
        "allow_refit": False
    }
)