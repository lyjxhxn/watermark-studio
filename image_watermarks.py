"""Image watermark models, shared placement and managed local assets."""
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
import hashlib
import math
import uuid

from PIL import Image, ImageOps
from PySide6.QtCore import QRectF, QStandardPaths
from PySide6.QtGui import QImage
import pymupdf as fitz

IMAGE_FORMATS = {'.png', '.jpg', '.jpeg', '.bmp', '.webp', '.tif', '.tiff'}


@dataclass(frozen=True)
class ImageWatermark:
    asset_path: str
    name: str = '图片水印'
    uid: str = field(default_factory=lambda: uuid.uuid4().hex)
    center_x: float = 0.5
    center_y: float = 0.5
    width_ratio: float = 0.2
    opacity: int = 100
    enabled: bool = True

    def __post_init__(self):
        values = (self.center_x, self.center_y, self.width_ratio, self.opacity)
        if not all(isinstance(v, (float, int)) and math.isfinite(v) for v in values):
            raise ValueError('图片水印的位置或大小无效。')
        if not (0 <= self.center_x <= 1 and 0 <= self.center_y <= 1 and
                0 < self.width_ratio <= 1 and 1 <= self.opacity <= 100):
            raise ValueError('图片水印的位置、大小或透明度超出范围。')
        if not isinstance(self.asset_path, str) or not isinstance(self.uid, str) or not self.uid:
            raise ValueError('图片水印记录无效。')


def read_image(mark):
    image = QImage(mark.asset_path)
    if image.isNull():
        raise ValueError(f'图片水印“{mark.name}”缺失或损坏，请移除后重新添加。')
    if image.width() * image.height() > 100_000_000:
        raise ValueError(f'图片水印“{mark.name}”过大，请先缩小原图。')
    return image


def load_images(marks):
    return {mark.uid: read_image(mark) for mark in marks if mark.enabled}


def image_geometry(mark, page_width, page_height, image):
    """Shared normalized placement, always fitted and clamped inside the page."""
    width = page_width * mark.width_ratio
    height = width * image.height() / image.width()
    fit = min(1.0, page_width / width, page_height / height)
    width, height = width * fit, height * fit
    x = min(max(mark.center_x * page_width - width / 2, 0), max(0, page_width - width))
    y = min(max(mark.center_y * page_height - height / 2, 0), max(0, page_height - height))
    return QRectF(x, y, width, height)


class AssetCache:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory is not None else (
            Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)) / 'watermark-images'
        )
        self.directory.mkdir(parents=True, exist_ok=True)

    def import_image(self, source):
        source = Path(source)
        if source.suffix.lower() not in IMAGE_FORMATS:
            raise ValueError('请选择 PNG、JPG、BMP、WebP 或静态 TIFF 图片。')
        try:
            with Image.open(source) as original:
                if getattr(original, 'n_frames', 1) != 1:
                    raise ValueError('图片水印需要静态单帧图片，暂不支持动画或多页图片。')
                if original.width * original.height > 100_000_000:
                    raise ValueError('图片水印过大，请先缩小原图。')
                image = ImageOps.exif_transpose(original).convert('RGBA')
                if image.getchannel('A').getbbox() is None:
                    raise ValueError('这张图片完全透明，请选择包含可见内容的图片。')
                data = BytesIO()
                image.save(data, format='PNG')
        except (OSError, Image.DecompressionBombError) as exc:
            raise ValueError('无法读取图片，请检查文件是否完整。') from exc
        return self._store(data.getvalue(), source.name)

    def import_pdf(self, source, page_index=0):
        source = Path(source)
        try:
            with fitz.open(source) as document:
                if document.needs_pass:
                    raise ValueError('此 PDF 需要密码，请先解密后再添加。')
                if not 0 <= page_index < len(document):
                    raise ValueError('所选 PDF 水印页码超出范围。')
                page = document[page_index]
                scale = min(300/72, 4096/max(page.rect.width,page.rect.height))
                pix = page.get_pixmap(matrix=fitz.Matrix(scale,scale), colorspace=fitz.csRGB, alpha=True)
                # MuPDF returns premultiplied RGBA. Convert before PNG encoding
                # to avoid dark fringes and double-multiplying transparent colors.
                rgba = QImage(pix.samples,pix.width,pix.height,pix.stride,
                              QImage.Format.Format_RGBA8888_Premultiplied).convertToFormat(QImage.Format.Format_RGBA8888)
                image = Image.frombytes('RGBA', (pix.width,pix.height), bytes(rgba.constBits()))
                if image.getchannel('A').getbbox() is None:
                    raise ValueError('所选 PDF 页面为空白，无法作为可见水印。')
                data = BytesIO()
                image.save(data,format='PNG')
        except (fitz.FileDataError, fitz.FileNotFoundError, OSError) as exc:
            raise ValueError('无法读取 PDF 水印，请检查文件是否完整。') from exc
        return self._store(data.getvalue(), f'{source.name}（第 {page_index+1} 页）')

    def _store(self, contents, name):
        destination = self.directory / (hashlib.sha256(contents).hexdigest() + '.png')
        if not destination.exists():
            temporary = self.directory / (uuid.uuid4().hex + '.tmp')
            try:
                temporary.write_bytes(contents)
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)
        return ImageWatermark(asset_path=str(destination), name=name)

    def cleanup(self, marks):
        referenced = {Path(mark.asset_path).resolve() for mark in marks}
        for file in self.directory.glob('*.png'):
            if len(file.stem) == 64 and all(c in '0123456789abcdef' for c in file.stem) and file.resolve() not in referenced:
                try:
                    file.unlink()
                except OSError:
                    pass
