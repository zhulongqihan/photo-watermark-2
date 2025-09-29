import os
import sys
import math
from dataclasses import dataclass
from typing import Optional, Tuple
from PIL import Image, ImageDraw, ImageFont

RGBA = Tuple[int, int, int, int]

# ========= 自动寻找系统字体 =========
def find_default_font() -> str | None:
    """根据操作系统自动返回一个可用的系统字体路径；找不到则返回 None。"""
    candidates = []
    if sys.platform.startswith("win"):  # Windows
        candidates += [
            r"C:\Windows\Fonts\msyh.ttc",        # 微软雅黑
            r"C:\Windows\Fonts\simhei.ttf",      # 黑体
            r"C:\Windows\Fonts\simsun.ttc",      # 宋体
            r"C:\Windows\Fonts\arial.ttf",       # Arial
        ]
    elif sys.platform == "darwin":  # macOS
        candidates += [
            "/System/Library/Fonts/PingFang.ttc",          # 苹方
            "/System/Library/Fonts/Songti.ttc",            # 宋体
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/Supplemental/Arial.ttf"
        ]
    else:  # Linux
        candidates += [
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        ]

    for p in candidates:
        if os.path.exists(p):
            return p
    return None

# ========= 数据类定义 =========
@dataclass
class ExportOptions:
    out_format: str            # "JPEG" or "PNG"
    jpeg_quality: int = 90     # 0-100
    scale_mode: str = "none"   # "none" | "width" | "height" | "percent"
    scale_value: int = 100     # px or %

@dataclass
class NamingRule:
    mode: str = "suffix"       # "keep" | "prefix" | "suffix"
    prefix: str = "wm_"
    suffix: str = "_watermarked"

@dataclass
class TextStyle:
    family_path: Optional[str]   # path to .ttf / .ttc or None -> default
    size: int
    bold: bool = False
    italic: bool = False
    color: RGBA = (255, 255, 255, 180)
    stroke: bool = False
    stroke_width: int = 2
    stroke_color: RGBA = (0, 0, 0, 200)
    shadow: bool = False
    shadow_offset: Tuple[int, int] = (2, 2)
    shadow_color: RGBA = (0, 0, 0, 160)

@dataclass
class WatermarkConfig:
    kind: str                   # "text" | "image"
    text: str = ""
    text_style: Optional[TextStyle] = None
    image_path: Optional[str] = None
    image_alpha: int = 180      # 0-255
    scale_percent: int = 100
    angle_deg: float = 0.0
    pos: Tuple[int, int] = (0, 0)

# ========= 字体与绘制 =========
def _load_font(style: TextStyle) -> ImageFont.FreeTypeFont:
    # 优先用用户指定路径；否则自动寻找系统字体；再不行用 Pillow 默认字体
    path = style.family_path or find_default_font()
    try:
        if path:
            return ImageFont.truetype(path, style.size)
    except Exception:
        pass
    return ImageFont.load_default()

def _draw_text(draw: ImageDraw.ImageDraw, text: str, xy: Tuple[int,int], style: TextStyle):
    if style.shadow:
        sx = xy[0] + style.shadow_offset[0]
        sy = xy[1] + style.shadow_offset[1]
        draw.text((sx, sy), text, font=_load_font(style), fill=style.shadow_color)
    draw.text(xy, text, font=_load_font(style), fill=style.color,
              stroke_width=style.stroke_width if style.stroke else 0,
              stroke_fill=style.stroke_color if style.stroke else None)

# ========= 文本水印渲染（已修复旋转尺寸不一致问题） =========
def _render_text_layer(base_size: Tuple[int,int], cfg: WatermarkConfig) -> Image.Image:
    W, H = base_size
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    # 计算文本尺寸
    tmp = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    dtmp = ImageDraw.Draw(tmp)
    stroke_w = cfg.text_style.stroke_width if cfg.text_style and cfg.text_style.stroke else 0
    font = _load_font(cfg.text_style)
    bbox = dtmp.textbbox((0, 0), cfg.text, font=font, stroke_width=stroke_w)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    if tw <= 0 or th <= 0:
        return layer

    # 画到紧致画布
    text_img = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    d = ImageDraw.Draw(text_img)
    _draw_text(d, cfg.text, (0, 0), cfg.text_style)

    # 旋转
    if abs(cfg.angle_deg) > 0.01:
        text_img = text_img.rotate(cfg.angle_deg, resample=Image.BICUBIC, expand=1)

    # 粘贴回大画布
    x, y = cfg.pos
    layer.paste(text_img, (int(x), int(y)), text_img)
    return layer

# ========= 图片水印渲染 =========
def _render_image_layer(base_size: Tuple[int,int], cfg: WatermarkConfig) -> Image.Image:
    W, H = base_size
    layer = Image.new("RGBA", (W, H), (0,0,0,0))
    wm = Image.open(cfg.image_path).convert("RGBA")
    # 缩放
    if cfg.scale_percent != 100:
        nw = max(1, int(wm.width * cfg.scale_percent / 100))
        nh = max(1, int(wm.height * cfg.scale_percent / 100))
        wm = wm.resize((nw, nh), Image.LANCZOS)
    # 透明度
    if cfg.image_alpha < 255:
        r,g,b,a = wm.split()
        a = a.point(lambda x: int(x * (cfg.image_alpha/255.0)))
        wm = Image.merge("RGBA", (r,g,b,a))
    # 旋转
    if abs(cfg.angle_deg) > 0.01:
        wm = wm.rotate(cfg.angle_deg, resample=Image.BICUBIC, expand=1)
    # 粘贴
    x, y = cfg.pos
    layer.paste(wm, (x, y), wm)
    return layer

# ========= 总入口 =========
def apply_watermark(src: Image.Image, cfg: WatermarkConfig) -> Image.Image:
    base = src.convert("RGBA")
    if cfg.kind == "text" and cfg.text_style is not None:
        layer = _render_text_layer(base.size, cfg)
    elif cfg.kind == "image" and cfg.image_path:
        layer = _render_image_layer(base.size, cfg)
    else:
        return base
    out = Image.alpha_composite(base, layer)
    return out

def resize_for_export(img: Image.Image, opts: ExportOptions) -> Image.Image:
    if opts.scale_mode == "none":
        return img
    W, H = img.size
    if opts.scale_mode == "percent":
        p = max(1, int(opts.scale_value))
        return img.resize((max(1,int(W*p/100)), max(1,int(H*p/100))), Image.LANCZOS)
    if opts.scale_mode == "width":
        new_w = max(1, int(opts.scale_value))
        new_h = max(1, int(H * new_w / W))
        return img.resize((new_w, new_h), Image.LANCZOS)
    if opts.scale_mode == "height":
        new_h = max(1, int(opts.scale_value))
        new_w = max(1, int(W * new_h / H))
        return img.resize((new_w, new_h), Image.LANCZOS)
    return img

def export_image(img: Image.Image, out_path: str, opts: ExportOptions):
    fmt = opts.out_format.upper()
    if fmt == "JPEG":
        bg = Image.new("RGB", img.size, (255,255,255))
        bg.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
        bg.save(out_path, "JPEG", quality=max(0, min(100, opts.jpeg_quality)))
    else:
        img.save(out_path, "PNG")
