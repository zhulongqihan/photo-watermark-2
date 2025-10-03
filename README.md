# Photo Watermark 2

一个跨平台的图片批量加水印工具，支持 Windows 和 MacOS。  
提供直观的图形界面，支持文字水印和图片水印，方便用户快速处理大量图片。

---

## ✨ 功能说明

- **批量导入图片和文件夹**  
  支持一次性导入多张照片或整个目录，适合批量处理。

- **文本水印**  
  用户可以输入任意文本作为水印，透明度、颜色、字号、描边、阴影、旋转均可调节。  
  程序会自动检测系统字体，避免乱码。

- **图片水印**  
  用户可选择 PNG 图片作为水印，支持透明通道。  
  水印图片可以自由缩放、旋转和调节透明度，常用于添加 Logo。

- **水印位置**  
  提供九宫格快速定位（四角+中心），也支持鼠标拖拽到任意位置。

- **导出功能**  
  - 支持 JPEG/PNG 导出  
  - JPEG 模式下可调节输出质量（压缩率）  
  - 支持缩放图片尺寸（按宽度、高度或比例）  
  - 文件命名规则可选择：保留原名、加前缀或加后缀  
  - 默认禁止覆盖原图，避免误操作

- **模板管理**  
  可保存当前所有水印设置（文字内容、字体、颜色、透明度、位置等）为模板，方便下次直接加载。  
  程序关闭时会自动保存上一次设置，启动时自动恢复。

- **性能优化**  
  - 预览窗口使用缩小图，提升刷新速度  
  - 拖动和旋转时增加刷新节流，保证操作流畅

---

## 🚀 使用方法

### 1. 下载可执行文件（推荐）
- 前往 [Releases 页面](https://github.com/zhulongqihan/photo-watermark-2/releases/latest) 下载 `PhotoWatermark2.exe`  
- Windows 用户直接双击运行即可（如遇到 SmartScreen 提示，请点击“更多信息 → 仍要运行”）

### 2. 从源码运行
```bash
git clone https://github.com/zhulongqihan/photo-watermark-2.git
cd photo-watermark-2
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
python -m app.main