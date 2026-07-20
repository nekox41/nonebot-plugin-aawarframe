# renderers/html_renderer.py

from pathlib import Path
from typing import Dict, Any, Callable, Optional, Union
from nonebot.log import logger
from nonebot_plugin_htmlkit import html_to_pic

# 定义渲染函数类型：接收数据字典和模板路径，返回HTML字符串
RenderFunc = Callable[[Dict[str, Any], str], str]

class HtmlImageRenderer:
    """
    通用的HTML图片渲染器
    支持注册多种数据→HTML的转换函数，自动适配不同模板
    """

    def __init__(
        self,
        template_dir: Path,
        output_dir: Optional[Path] = None,
    ):
        self.template_dir = Path(template_dir).resolve()
        self.output_dir = Path(output_dir).resolve() if output_dir else None
        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)

        # 注册表：template_type -> {"func": RenderFunc, "config": dict}
        self._renderers: Dict[str, Dict[str, Any]] = {}

        logger.info(f"HtmlImageRenderer initialized, template_dir: {self.template_dir}")

    def register_renderer(self, template_type: str, func: RenderFunc, config: Optional[Dict] = None):
        """
        注册一种数据渲染方式
        :param template_type: 模板标识，如 "archimedea"
        :param func: 接收 (data, template_path) 并返回 HTML 字符串的函数
        :param config: 该模板专属的渲染参数（会覆盖默认参数），键与 html_to_pic 参数一致
        """
        if template_type in self._renderers:
            logger.warning(f"模板类型 '{template_type}' 已注册，将被覆盖")
        self._renderers[template_type] = {
            "func": func,
            "config": config or {}
        }
        logger.info(f"Registered renderer for template type: {template_type} (config: {config})")

    def get_renderer(self, template_type: str) -> Optional[RenderFunc]:
        """获取指定类型的渲染函数"""
        entry = self._renderers.get(template_type)
        return entry["func"] if entry else None

    async def render(
            self,
            data: Dict[str, Any],
            template_type: str,
            template_filename: Optional[str] = None,
            output_filename: Optional[str] = None,
            **override_config,
    ) -> bytes:
        """
        渲染数据为图片
        :param data: 要渲染的数据（字典）
        :param template_type: 模板类型（用于查找对应的渲染函数和配置）
        :param template_filename: 模板文件名（若为None，则使用 template_type + '.html'）
        :param output_filename: 如果指定，则保存到文件
        :param override_config: 覆盖渲染参数（最高优先级）
        :return: 图片二进制数据
        """
        # 1. 获取对应的渲染函数
        entry = self._renderers.get(template_type)
        if not entry:
            raise ValueError(f"未注册的模板类型: {template_type}")
        render_func = entry["func"]

        # 2. 确定模板文件路径
        if template_filename is None:
            template_filename = f"{template_type}.html"
        template_path = self.template_dir / template_filename
        if not template_path.exists():
            raise FileNotFoundError(f"模板文件不存在: {template_path}")

        # 3. 调用渲染函数生成HTML
        html = render_func(data, str(template_path))
        logger.debug(f"Generated HTML for {template_type}, length: {len(html)}")

        # 4. 合并渲染参数：默认配置 + 模板配置 + 调用覆盖
        # 模板配置
        template_config = entry.get("config", {})
        # 调用覆盖
        template_config.update(override_config)

        logger.info(f"Config: {template_config}")
        # 5. 转图片
        try:
            img_bytes = await html_to_pic(
                html,
                base_url=f"file://{self.template_dir}/",
                **template_config,  # 展开所有参数
            )
        except Exception as e:
            logger.error(f"HTML转图片失败: {e}")
            raise

        # 6. 可选保存
        if self.output_dir and output_filename:
            filepath = self.output_dir / output_filename
            with open(filepath, "wb") as f:
                f.write(img_bytes)
            logger.info(f"图片已保存: {filepath}")

        return img_bytes