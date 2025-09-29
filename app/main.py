import os
import sys
import pathlib
from typing import List, Tuple, Optional
from PIL import Image, ImageQt
from PySide6.QtCore import Qt, QSize, QPoint
from PySide6.QtGui import QPixmap, QImage, QAction
from PySide6.QtWidgets import (
    QApplication, QWidget, QFileDialog, QListWidget, QListWidgetItem, QLabel,
    QHBoxLayout, QVBoxLayout, QPushButton, QSlider, QLineEdit, QColorDialog,
    QComboBox, QSpinBox, QCheckBox, QMessageBox, QGroupBox, QFormLayout, QMenuBar
)

try:
    from .watermarking import (
        WatermarkConfig, TextStyle, ExportOptions, NamingRule,
        apply_watermark, resize_for_export, export_image, find_default_font
    )
    from . import templates as tpl
except ImportError:
    from watermarking import (
        WatermarkConfig, TextStyle, ExportOptions, NamingRule,
        apply_watermark, resize_for_export, export_image, find_default_font
    )
    import templates as tpl



SUPPORTED_INPUT = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}

def pil_to_qpix(img: Image.Image) -> QPixmap:
    return QPixmap.fromImage(ImageQt.ImageQt(img.convert("RGBA")))

class DraggablePreview(QLabel):
    """可拖拽水印位置的预览区域（只显示当前选中图片）"""
    def __init__(self, get_cfg_callable, set_pos_callable, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self._pix: Optional[QPixmap] = None
        self._orig_img: Optional[Image.Image] = None
        self._get_cfg = get_cfg_callable
        self._set_pos = set_pos_callable
        self._dragging = False
        self._offset = QPoint(0,0)
        self._wm_bbox_size = (200, 60)  # 估计一个框，拖拽时参考；实际渲染用 Pillow

    def set_image(self, img: Image.Image):
        self._orig_img = img
        self.refresh()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._dragging = True
            self._offset = ev.position().toPoint()

    def mouseMoveEvent(self, ev):
        if self._dragging and self._orig_img:
            # 将鼠标点映射到图像坐标
            cfg = self._get_cfg()
            # 简易映射：按显示尺寸和原图尺寸比例（忽略保持纵横比的空白）
            label_w = self.width()
            label_h = self.height()
            img_w, img_h = self._orig_img.size
            # 填充模式：整体等比缩放后置中
            scale = min(label_w/img_w, label_h/img_h)
            disp_w = int(img_w*scale)
            disp_h = int(img_h*scale)
            margin_x = (label_w - disp_w)//2
            margin_y = (label_h - disp_h)//2
            mx = int((ev.position().x() - margin_x)/scale)
            my = int((ev.position().y() - margin_y)/scale)
            mx = max(0, min(mx, img_w-1))
            my = max(0, min(my, img_h-1))
            self._set_pos((mx, my))
            self.refresh()

    def mouseReleaseEvent(self, ev):
        self._dragging = False

    def refresh(self):
        if self._orig_img is None:
            self.setText("拖入或选择图片进行预览")
            return
        cfg = self._get_cfg()
        preview = apply_watermark(self._orig_img, cfg)
        qpix = pil_to_qpix(preview)
        self.setPixmap(qpix.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.refresh()

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Photo Watermark 2")
        self.resize(1200, 720)

        self.images: List[str] = []
        self.current_index: int = -1
        self.current_pil: Optional[Image.Image] = None

        # 状态：水印 & 导出设置
        self.kind = "text"  # "text" or "image"
        self.text_content = "© Your Name"
        self.text_color = (255,255,255,180)
        self.stroke_on = True
        self.stroke_width = 2
        self.stroke_color = (0,0,0,200)
        self.shadow_on = True
        self.shadow_offset = (2,2)
        self.shadow_color = (0,0,0,160)
        self.font_path = find_default_font()
        self.font_size = 48
        self.bold = False
        self.italic = False

        self.img_wm_path = None
        self.img_wm_alpha = 180
        self.img_wm_scale = 100

        self.angle = 0.0
        self.pos = (50,50)

        self.out_dir = ""
        self.out_format = "PNG"
        self.jpeg_quality = 90
        self.scale_mode = "none"
        self.scale_value = 100

        self.naming = NamingRule(mode="suffix", prefix="wm_", suffix="_watermarked")

        # UI
        root = QHBoxLayout(self)

        # 左侧：文件列表
        left_box = QVBoxLayout()
        self.listw = QListWidget()
        self.listw.currentRowChanged.connect(self.on_select)
        left_box.addWidget(self.listw)

        file_btns = QHBoxLayout()
        btn_add_files = QPushButton("添加图片")
        btn_add_files.clicked.connect(self.add_files)
        btn_add_dir = QPushButton("导入文件夹")
        btn_add_dir.clicked.connect(self.add_dir)
        file_btns.addWidget(btn_add_files)
        file_btns.addWidget(btn_add_dir)
        left_box.addLayout(file_btns)

        root.addLayout(left_box, 2)

        # 中间：预览
        mid_box = QVBoxLayout()
        self.preview = DraggablePreview(self.get_cfg, self.set_pos)
        mid_box.addWidget(self.preview, 10)

        # 九宫格预设
        grid = QHBoxLayout()
        for name, relx, rely in [
            ("左上",0.05,0.05), ("上中",0.5,0.05), ("右上",0.95,0.05),
            ("左中",0.05,0.5), ("正中",0.5,0.5), ("右中",0.95,0.5),
            ("左下",0.05,0.95), ("下中",0.5,0.95), ("右下",0.95,0.95),
        ]:
            b = QPushButton(name)
            def make_cb(rx=relx, ry=rely):
                def cb():
                    if self.current_pil:
                        W,H = self.current_pil.size
                        self.pos = (int(W*rx), int(H*ry))
                        self.preview.refresh()
                return cb
            b.clicked.connect(make_cb())
            grid.addWidget(b)
        mid_box.addLayout(grid)
        root.addLayout(mid_box, 5)

        # 右侧：控制面板（文本/图片水印、样式、导出、模板）
        right = QVBoxLayout()

        # 水印类型
        grp_kind = QGroupBox("水印类型")
        kform = QHBoxLayout()
        self.cb_kind = QComboBox()
        self.cb_kind.addItems(["文本水印", "图片水印"])
        self.cb_kind.currentIndexChanged.connect(self.on_kind_change)
        kform.addWidget(self.cb_kind)
        grp_kind.setLayout(kform)
        right.addWidget(grp_kind)

        # 文本样式
        grp_text = QGroupBox("文本水印设置")
        f = QFormLayout()

        self.ed_text = QLineEdit(self.text_content)
        self.ed_text.textChanged.connect(self.on_text_change)
        f.addRow("内容", self.ed_text)

        self.btn_color = QPushButton("颜色")
        self.btn_color.clicked.connect(self.pick_text_color)
        f.addRow("颜色/透明", self.btn_color)

        self.sp_alpha = QSlider(Qt.Horizontal); self.sp_alpha.setRange(0,255); self.sp_alpha.setValue(self.text_color[3])
        self.sp_alpha.valueChanged.connect(lambda v:self.set_text_alpha(v))
        f.addRow("不透明度", self.sp_alpha)

        self.sp_fontsize = QSpinBox(); self.sp_fontsize.setRange(8,400); self.sp_fontsize.setValue(self.font_size)
        self.sp_fontsize.valueChanged.connect(lambda v:self.set_font_size(v))
        f.addRow("字号", self.sp_fontsize)

        self.btn_font = QPushButton("选择字体文件(.ttf/.ttc)")
        self.btn_font.clicked.connect(self.pick_font)
        f.addRow("字体文件", self.btn_font)

        self.ck_bold = QCheckBox("粗体"); self.ck_bold.setChecked(self.bold)
        self.ck_bold.stateChanged.connect(lambda _ : self.toggle_bold())
        self.ck_italic = QCheckBox("斜体"); self.ck_italic.setChecked(self.italic)
        self.ck_italic.stateChanged.connect(lambda _ : self.toggle_italic())
        row = QHBoxLayout(); row.addWidget(self.ck_bold); row.addWidget(self.ck_italic)
        roww = QWidget(); roww.setLayout(row)
        f.addRow("字重/斜体", roww)

        self.ck_stroke = QCheckBox("描边"); self.ck_stroke.setChecked(self.stroke_on)
        self.ck_stroke.stateChanged.connect(lambda _ : self.toggle_stroke())
        self.sp_stroke_w = QSpinBox(); self.sp_stroke_w.setRange(1,10); self.sp_stroke_w.setValue(self.stroke_width)
        self.btn_stroke_color = QPushButton("描边色"); self.btn_stroke_color.clicked.connect(self.pick_stroke_color)
        h = QHBoxLayout(); [h.addWidget(w) for w in (self.ck_stroke, self.sp_stroke_w, self.btn_stroke_color)]
        wrap = QWidget(); wrap.setLayout(h)
        f.addRow("描边", wrap)

        self.ck_shadow = QCheckBox("阴影"); self.ck_shadow.setChecked(self.shadow_on)
        self.ck_shadow.stateChanged.connect(lambda _ : self.toggle_shadow())
        self.sp_shadow_dx = QSpinBox(); self.sp_shadow_dx.setRange(-50,50); self.sp_shadow_dx.setValue(self.shadow_offset[0])
        self.sp_shadow_dy = QSpinBox(); self.sp_shadow_dy.setRange(-50,50); self.sp_shadow_dy.setValue(self.shadow_offset[1])
        self.btn_shadow_color = QPushButton("阴影色"); self.btn_shadow_color.clicked.connect(self.pick_shadow_color)
        hh = QHBoxLayout(); [hh.addWidget(w) for w in (self.ck_shadow, self.sp_shadow_dx, self.sp_shadow_dy, self.btn_shadow_color)]
        w2 = QWidget(); w2.setLayout(hh)
        f.addRow("阴影", w2)

        self.sl_angle = QSlider(Qt.Horizontal); self.sl_angle.setRange(-180,180); self.sl_angle.setValue(int(self.angle))
        self.sl_angle.valueChanged.connect(lambda v: self.set_angle(v))
        f.addRow("旋转角度", self.sl_angle)

        grp_text.setLayout(f)
        right.addWidget(grp_text)

        # 图片水印
        grp_img = QGroupBox("图片水印设置")
        g = QFormLayout()
        self.btn_pick_wm = QPushButton("选择 PNG/Logo 作为水印")
        self.btn_pick_wm.clicked.connect(self.pick_wm_image)
        g.addRow("水印图片", self.btn_pick_wm)
        self.sl_img_alpha = QSlider(Qt.Horizontal); self.sl_img_alpha.setRange(0,255); self.sl_img_alpha.setValue(self.img_wm_alpha)
        self.sl_img_alpha.valueChanged.connect(lambda v: self.set_img_alpha(v))
        g.addRow("不透明度", self.sl_img_alpha)
        self.sp_img_scale = QSpinBox(); self.sp_img_scale.setRange(1,400); self.sp_img_scale.setValue(self.img_wm_scale)
        self.sp_img_scale.valueChanged.connect(lambda v: self.set_img_scale(v))
        g.addRow("缩放(%)", self.sp_img_scale)
        grp_img.setLayout(g)
        right.addWidget(grp_img)

        # 导出设置
        grp_exp = QGroupBox("导出设置")
        e = QFormLayout()
        self.btn_outdir = QPushButton("选择输出文件夹")
        self.btn_outdir.clicked.connect(self.pick_outdir)
        e.addRow("输出目录", self.btn_outdir)

        self.cb_format = QComboBox(); self.cb_format.addItems(["PNG","JPEG"])
        self.cb_format.currentIndexChanged.connect(lambda _ : self.set_out_format(self.cb_format.currentText()))
        e.addRow("输出格式", self.cb_format)

        self.sl_quality = QSlider(Qt.Horizontal); self.sl_quality.setRange(1,100); self.sl_quality.setValue(self.jpeg_quality)
        self.sl_quality.valueChanged.connect(lambda v: self.set_quality(v))
        e.addRow("JPEG质量", self.sl_quality)

        self.cb_scale_mode = QComboBox(); self.cb_scale_mode.addItems(["none","width","height","percent"])
        self.cb_scale_mode.currentIndexChanged.connect(lambda _ : self.set_scale_mode(self.cb_scale_mode.currentText()))
        self.sp_scale_value = QSpinBox(); self.sp_scale_value.setRange(1,10000); self.sp_scale_value.setValue(self.scale_value)
        self.sp_scale_value.valueChanged.connect(lambda v: self.set_scale_value(v))
        hh2 = QHBoxLayout(); hh2.addWidget(self.cb_scale_mode); hh2.addWidget(self.sp_scale_value)
        ww2 = QWidget(); ww2.setLayout(hh2)
        e.addRow("尺寸调整", ww2)

        # 命名规则
        self.cb_naming = QComboBox(); self.cb_naming.addItems(["保持原名","前缀","后缀"])
        self.cb_naming.currentIndexChanged.connect(self.on_naming_change)
        self.ed_prefix = QLineEdit(self.naming.prefix)
        self.ed_suffix = QLineEdit(self.naming.suffix)
        self.ed_prefix.textChanged.connect(lambda t: setattr(self.naming, "prefix", t))
        self.ed_suffix.textChanged.connect(lambda t: setattr(self.naming, "suffix", t))
        row3 = QHBoxLayout(); row3.addWidget(self.cb_naming); row3.addWidget(QLabel("前缀")); row3.addWidget(self.ed_prefix); row3.addWidget(QLabel("后缀")); row3.addWidget(self.ed_suffix)
        w3 = QWidget(); w3.setLayout(row3)
        e.addRow("命名规则", w3)

        grp_exp.setLayout(e)
        right.addWidget(grp_exp)

        # 模板
        grp_tpl = QGroupBox("模板")
        t = QHBoxLayout()
        self.cb_tpls = QComboBox(); self.refresh_tpls()
        btn_load = QPushButton("加载")
        btn_load.clicked.connect(self.load_tpl)
        btn_save = QPushButton("保存为...")
        btn_save.clicked.connect(self.save_tpl)
        btn_del = QPushButton("删除")
        btn_del.clicked.connect(self.delete_tpl)
        t.addWidget(self.cb_tpls); t.addWidget(btn_load); t.addWidget(btn_save); t.addWidget(btn_del)
        grp_tpl.setLayout(t)
        right.addWidget(grp_tpl)

        # 批量导出
        btn_export = QPushButton("批量导出")
        btn_export.clicked.connect(self.do_export)
        right.addWidget(btn_export)

        right.addStretch(1)
        root.addLayout(right, 4)

        # 拖拽导入
        self.setAcceptDrops(True)

        # 加载 last used
        self.load_last_used()

    # ----------------- 拖拽文件 -----------------
    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        paths = []
        for u in ev.mimeData().urls():
            p = u.toLocalFile()
            if os.path.isdir(p):
                for root, _, files in os.walk(p):
                    for fn in files:
                        if pathlib.Path(fn).suffix.lower() in SUPPORTED_INPUT:
                            paths.append(os.path.join(root, fn))
            else:
                if pathlib.Path(p).suffix.lower() in SUPPORTED_INPUT:
                    paths.append(p)
        self.add_paths(paths)

    # ----------------- 文件导入 -----------------
    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择图片", "", "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)")
        self.add_paths(files)

    def add_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择文件夹", "")
        if d:
            paths = []
            for root, _, files in os.walk(d):
                for fn in files:
                    if pathlib.Path(fn).suffix.lower() in SUPPORTED_INPUT:
                        paths.append(os.path.join(root, fn))
            self.add_paths(paths)

    def add_paths(self, paths: List[str]):
        added = 0
        for p in paths:
            if p not in self.images:
                self.images.append(p)
                item = QListWidgetItem(os.path.basename(p))
                self.listw.addItem(item)
                added += 1
        if added > 0 and self.current_index < 0:
            self.listw.setCurrentRow(0)

    # ----------------- 列表选择 -----------------
    def on_select(self, row: int):
        self.current_index = row
        if 0 <= row < len(self.images):
            self.load_current_pil()
        else:
            self.current_pil = None
            self.preview.set_image(None)

    def load_current_pil(self):
        path = self.images[self.current_index]
        self.current_pil = Image.open(path).convert("RGBA")
        self.preview.set_image(self.current_pil)

    # ----------------- 状态 -> 配置 -----------------
    def get_cfg(self) -> WatermarkConfig:
        if self.kind == "text":
            style = TextStyle(
                family_path=self.font_path,
                size=self.font_size,
                bold=self.bold, italic=self.italic,
                color=self.text_color,
                stroke=self.stroke_on, stroke_width=self.stroke_width,
                stroke_color=self.stroke_color,
                shadow=self.shadow_on, shadow_offset=self.shadow_offset,
                shadow_color=self.shadow_color
            )
            return WatermarkConfig(
                kind="text", text=self.text_content, text_style=style,
                angle_deg=self.angle, pos=self.pos
            )
        else:
            return WatermarkConfig(
                kind="image", image_path=self.img_wm_path,
                image_alpha=self.img_wm_alpha, scale_percent=self.img_wm_scale,
                angle_deg=self.angle, pos=self.pos
            )

    def set_pos(self, pos: Tuple[int,int]):
        self.pos = pos

    # ----------------- 文本控件回调 -----------------
    def on_text_change(self, t: str):
        self.text_content = t
        self.preview.refresh()

    def pick_text_color(self):
        c = QColorDialog.getColor()
        if c.isValid():
            self.text_color = (c.red(), c.green(), c.blue(), self.text_color[3])
            self.preview.refresh()

    def set_text_alpha(self, v: int):
        r,g,b,_ = self.text_color
        self.text_color = (r,g,b,v)
        self.preview.refresh()

    def pick_font(self):
        file, _ = QFileDialog.getOpenFileName(self, "选择字体文件", "", "Fonts (*.ttf *.ttc)")
        if file:
            self.font_path = file
            self.preview.refresh()

    def set_font_size(self, v:int):
        self.font_size = v
        self.preview.refresh()

    def toggle_bold(self):
        self.bold = self.ck_bold.isChecked()
        self.preview.refresh()

    def toggle_italic(self):
        self.italic = self.ck_italic.isChecked()
        self.preview.refresh()

    def toggle_stroke(self):
        self.stroke_on = self.ck_stroke.isChecked()
        self.preview.refresh()

    def pick_stroke_color(self):
        c = QColorDialog.getColor()
        if c.isValid():
            self.stroke_color = (c.red(), c.green(), c.blue(), self.stroke_color[3])
            self.preview.refresh()

    def toggle_shadow(self):
        self.shadow_on = self.ck_shadow.isChecked()
        self.preview.refresh()

    def pick_shadow_color(self):
        c = QColorDialog.getColor()
        if c.isValid():
            self.shadow_color = (c.red(), c.green(), c.blue(), self.shadow_color[3])
            self.preview.refresh()

    def set_angle(self, v:int):
        self.angle = float(v)
        self.preview.refresh()

    # ----------------- 图片水印回调 -----------------
    def on_kind_change(self, idx:int):
        self.kind = "text" if idx==0 else "image"
        self.preview.refresh()

    def pick_wm_image(self):
        f, _ = QFileDialog.getOpenFileName(self, "选择水印图片", "", "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)")
        if f:
            self.img_wm_path = f
            self.preview.refresh()

    def set_img_alpha(self, v:int):
        self.img_wm_alpha = v
        self.preview.refresh()

    def set_img_scale(self, v:int):
        self.img_wm_scale = v
        self.preview.refresh()

    # ----------------- 导出设置回调 -----------------
    def pick_outdir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录", "")
        if d:
            self.out_dir = d

    def set_out_format(self, fmt: str):
        self.out_format = fmt

    def set_quality(self, v:int):
        self.jpeg_quality = v

    def set_scale_mode(self, m:str):
        self.scale_mode = m

    def set_scale_value(self, v:int):
        self.scale_value = v

    def on_naming_change(self, idx:int):
        if idx==0: self.naming.mode="keep"
        elif idx==1: self.naming.mode="prefix"
        else: self.naming.mode="suffix"

    # ----------------- 批量导出 -----------------
    def do_export(self):
        if not self.images:
            QMessageBox.warning(self, "提示", "请先导入图片")
            return
        if not self.out_dir:
            QMessageBox.warning(self, "提示", "请选择输出目录")
            return
        # 覆盖保护：禁止导出到原目录（默认）
        if any(os.path.dirname(p) == self.out_dir for p in self.images):
            QMessageBox.warning(self, "警告", "默认禁止导出到原目录，请选择不同的输出目录。")
            return

        cnt = 0
        for p in self.images:
            img = Image.open(p).convert("RGBA")
            preview = apply_watermark(img, self.get_cfg())
            final = resize_for_export(preview, ExportOptions(
                out_format=self.out_format,
                jpeg_quality=self.jpeg_quality,
                scale_mode=self.scale_mode,
                scale_value=self.scale_value
            ))
            # 命名
            stem = pathlib.Path(p).stem
            if self.naming.mode == "keep":
                out_name = f"{stem}"
            elif self.naming.mode == "prefix":
                out_name = f"{self.naming.prefix}{stem}"
            else:
                out_name = f"{stem}{self.naming.suffix}"
            ext = ".png" if self.out_format.upper()=="PNG" else ".jpg"
            out_path = os.path.join(self.out_dir, out_name + ext)
            export_image(final, out_path, ExportOptions(
                out_format=self.out_format,
                jpeg_quality=self.jpeg_quality,
                scale_mode="none"
            ))
            cnt += 1
        QMessageBox.information(self, "完成", f"成功导出 {cnt} 张图片")

    # ----------------- 模板 & last used -----------------
    def collect_state(self) -> dict:
        return {
            "kind": self.kind,
            "text_content": self.text_content,
            "text_color": self.text_color,
            "stroke_on": self.stroke_on,
            "stroke_width": self.stroke_width,
            "stroke_color": self.stroke_color,
            "shadow_on": self.shadow_on,
            "shadow_offset": self.shadow_offset,
            "shadow_color": self.shadow_color,
            "font_path": self.font_path,
            "font_size": self.font_size,
            "bold": self.bold,
            "italic": self.italic,
            "img_wm_path": self.img_wm_path,
            "img_wm_alpha": self.img_wm_alpha,
            "img_wm_scale": self.img_wm_scale,
            "angle": self.angle,
            "pos": self.pos,
            "out_dir": self.out_dir,
            "out_format": self.out_format,
            "jpeg_quality": self.jpeg_quality,
            "scale_mode": self.scale_mode,
            "scale_value": self.scale_value,
            "naming": {
                "mode": self.naming.mode,
                "prefix": self.naming.prefix,
                "suffix": self.naming.suffix
            }
        }

    def apply_state(self, s: dict):
        if not s: return
        self.kind = s.get("kind", self.kind)
        self.text_content = s.get("text_content", self.text_content)
        self.text_color = tuple(s.get("text_color", self.text_color))
        self.stroke_on = s.get("stroke_on", self.stroke_on)
        self.stroke_width = s.get("stroke_width", self.stroke_width)
        self.stroke_color = tuple(s.get("stroke_color", self.stroke_color))
        self.shadow_on = s.get("shadow_on", self.shadow_on)
        self.shadow_offset = tuple(s.get("shadow_offset", self.shadow_offset))
        self.shadow_color = tuple(s.get("shadow_color", self.shadow_color))
        self.font_path = s.get("font_path", self.font_path)
        self.font_size = s.get("font_size", self.font_size)
        self.bold = s.get("bold", self.bold)
        self.italic = s.get("italic", self.italic)
        self.img_wm_path = s.get("img_wm_path", self.img_wm_path)
        self.img_wm_alpha = s.get("img_wm_alpha", self.img_wm_alpha)
        self.img_wm_scale = s.get("img_wm_scale", self.img_wm_scale)
        self.angle = float(s.get("angle", self.angle))
        self.pos = tuple(s.get("pos", self.pos))
        self.out_dir = s.get("out_dir", self.out_dir)
        self.out_format = s.get("out_format", self.out_format)
        self.jpeg_quality = s.get("jpeg_quality", self.jpeg_quality)
        self.scale_mode = s.get("scale_mode", self.scale_mode)
        self.scale_value = s.get("scale_value", self.scale_value)
        nm = s.get("naming", {})
        self.naming.mode = nm.get("mode", self.naming.mode)
        self.naming.prefix = nm.get("prefix", self.naming.prefix)
        self.naming.suffix = nm.get("suffix", self.naming.suffix)

        # 刷新控件状态
        self.cb_kind.setCurrentIndex(0 if self.kind=="text" else 1)
        self.ed_text.setText(self.text_content)
        self.sp_alpha.setValue(self.text_color[3])
        self.sp_fontsize.setValue(self.font_size)
        self.ck_bold.setChecked(self.bold)
        self.ck_italic.setChecked(self.italic)
        self.ck_stroke.setChecked(self.stroke_on)
        self.sp_stroke_w.setValue(self.stroke_width)
        self.ck_shadow.setChecked(self.shadow_on)
        self.sp_shadow_dx.setValue(self.shadow_offset[0])
        self.sp_shadow_dy.setValue(self.shadow_offset[1])
        self.sl_angle.setValue(int(self.angle))
        self.cb_format.setCurrentText(self.out_format)
        self.sl_quality.setValue(self.jpeg_quality)
        self.cb_scale_mode.setCurrentText(self.scale_mode)
        self.sp_scale_value.setValue(self.scale_value)
        self.cb_naming.setCurrentIndex({"keep":0,"prefix":1,"suffix":2}[self.naming.mode])
        self.ed_prefix.setText(self.naming.prefix)
        self.ed_suffix.setText(self.naming.suffix)
        self.preview.refresh()

    def refresh_tpls(self):
        self.cb_tpls.clear()
        names = tpl.list_templates()
        self.cb_tpls.addItems(names)

    def save_tpl(self):
        name, ok = QFileDialog.getSaveFileName(self, "模板名（保存为 .json）", "", "Template (*.json)")
        if ok or name:
            # 兼容直接输入名字
            base = os.path.basename(name)
            if base.endswith(".json"):
                base = base[:-5]
            tpl.save_template(base, self.collect_state())
            self.refresh_tpls()
            QMessageBox.information(self, "OK", f"模板已保存：{base}")

    def load_tpl(self):
        name = self.cb_tpls.currentText()
        if not name:
            return
        s = tpl.load_template(name)
        self.apply_state(s)

    def delete_tpl(self):
        name = self.cb_tpls.currentText()
        if not name:
            return
        tpl.delete_template(name)
        self.refresh_tpls()

    def closeEvent(self, ev):
        tpl.save_last_used(self.collect_state())
        return super().closeEvent(ev)

    def load_last_used(self):
        s = tpl.load_last_used()
        self.apply_state(s)


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
if __name__ == "__main__":
    main()
