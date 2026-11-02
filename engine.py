"""Raster watermark pipeline shared by preview and batch export."""
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import math
import os
import re
import tempfile

import pymupdf as fitz
from PIL import Image, ImageOps
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QPointF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath

SUPPORTED = {'.pdf', '.png', '.jpg', '.jpeg', '.bmp', '.webp', '.tif', '.tiff'}


@dataclass(frozen=True)
class Options:
    text: str = '水印'
    family: str = '微软雅黑'
    size: float = 96
    opacity: int = 25
    angle: int = -30
    color: str = '#969696'
    tiled: bool = True
    columns: int = 4
    rows: int = 3
    dpi: int = 100
    compression: int = 20
    pages: str = ''


class Cancelled(Exception):
    pass


def selected_pages(spec, count):
    if not spec.strip():
        return list(range(count))
    spec = spec.replace('，', ',').replace('、', ',').replace('–', '-').replace('—', '-')
    chosen = set()
    for part in spec.split(','):
        match = re.fullmatch(r'\s*(\d+)\s*(?:-\s*(\d+)\s*)?', part)
        if not match:
            raise ValueError('页码格式不正确，请使用 1-3,5,8 这样的格式。')
        first = int(match[1])
        last = int(match[2] or first)
        if first < 1 or last < first or last > count:
            raise ValueError(f'页码超出范围：{part.strip()}，此文件共 {count} 页。')
        chosen.update(range(first - 1, last))
    return sorted(chosen)


def png_bytes(image):
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, 'PNG'):
        raise RuntimeError('无法编码页面图片。')
    buffer.close()
    return bytes(data)


def compression_quality(options):
    return round(100 - options.compression * 0.65)


def pdf_image_bytes(image, options):
    rgb = image.convertToFormat(QImage.Format.Format_RGB888)
    if options.compression == 0:
        return png_bytes(rgb)
    pixels = Image.frombytes('RGB', (rgb.width(), rgb.height()), bytes(rgb.bits()),
                             'raw', 'RGB', rgb.bytesPerLine(), 1)
    data = BytesIO()
    pixels.save(data, format='JPEG', quality=compression_quality(options), subsampling=0, optimize=True)
    return data.getvalue()


def pdf_image(page, dpi):
    # Refuse unexpectedly huge rasters before allocating hundreds of MB.
    if math.ceil(page.rect.width * dpi / 72) * math.ceil(page.rect.height * dpi / 72) > 100_000_000:
        raise ValueError('此页面在所选分辨率下过大，请降低 DPI 后重试。')
    pix = page.get_pixmap(dpi=round(dpi), colorspace=fitz.csRGB, alpha=False)
    return QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()


def pil_image(image):
    rgba = ImageOps.exif_transpose(image).convert('RGBA')
    return QImage(rgba.tobytes(), rgba.width, rgba.height, rgba.width * 4,
                  QImage.Format.Format_RGBA8888).copy()


def watermark(image, options, dpi):
    result = image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    painter = QPainter(result)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        font = QFont(options.family)
        font.setPixelSize(max(1, round(options.size * dpi / 72)))
        path = QPainterPath()
        for line_number, line in enumerate(options.text.splitlines()):
            path.addText(QPointF(0, line_number * font.pixelSize() * 1.3), font, line)
        bounds = path.boundingRect()
        color = QColor(options.color)
        color.setAlphaF(options.opacity / 100)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        columns = options.columns if options.tiled else 1
        rows = options.rows if options.tiled else 1
        for row in range(rows):
            for column in range(columns):
                painter.save()
                painter.translate((column + 0.5) * result.width() / columns,
                                  (row + 0.5) * result.height() / rows)
                painter.rotate(options.angle)
                painter.translate(-bounds.center())
                painter.drawPath(path)
                painter.restore()
    finally:
        painter.end()
    return result


def preview(source, page_index, options):
    source = Path(source)
    if source.suffix.lower() == '.pdf':
        with fitz.open(source) as doc:
            if doc.needs_pass:
                raise ValueError('此 PDF 需要密码，请先解密后再添加。')
            page = doc[page_index]
            # Preview dpi is chosen independently while retaining physical text size.
            dpi = max(1, min(options.dpi, 100, int(1600 * 72 / max(page.rect.width, page.rect.height))))
            image = pdf_image(page, dpi)
    else:
        with Image.open(source) as original:
            original.seek(page_index)
            image = pil_image(original)
        scale = min(1, 1600 / max(image.width(), image.height()))
        image = image.scaled(round(image.width() * scale), round(image.height() * scale),
                             Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        dpi = options.dpi * scale
    if source.suffix.lower() != '.pdf' or page_index in selected_pages(options.pages, page_count(source)):
        image = watermark(image, options, dpi)
    return image


def page_count(source):
    if Path(source).suffix.lower() == '.pdf':
        with fitz.open(source) as doc:
            if doc.needs_pass:
                raise ValueError('此 PDF 需要密码，请先解密后再添加。')
            return len(doc)
    with Image.open(source) as image:
        count = getattr(image, 'n_frames', 1)
        if count > 1 and Path(source).suffix.lower() not in {'.tif', '.tiff'}:
            raise ValueError('暂不支持动态图片，请先转成静态图片；多页 TIFF 可以直接处理。')
        return count


def unique_destination(folder, source):
    candidate = folder / f'{source.stem}_水印{source.suffix.lower()}'
    counter = 2
    while candidate.exists():
        candidate = folder / f'{source.stem}_水印_{counter}{source.suffix.lower()}'
        counter += 1
    return candidate


def export_file(source, folder, options, progress=lambda done,total: None, cancelled=lambda: False):
    source, folder = Path(source), Path(folder)
    if not options.text.strip():
        raise ValueError('请填写水印文字。')
    page_count(source)
    folder.mkdir(parents=True, exist_ok=True)
    destination = unique_destination(folder, source)
    descriptor, temporary = tempfile.mkstemp(prefix='.watermark-', suffix=source.suffix, dir=folder)
    os.close(descriptor)
    try:
        if source.suffix.lower() == '.pdf':
            with fitz.open(source) as doc, fitz.open() as output:
                if doc.needs_pass:
                    raise ValueError('此 PDF 需要密码，请先解密后再添加。')
                chosen = set(selected_pages(options.pages, len(doc)))
                for index, page in enumerate(doc):
                    if cancelled():
                        raise Cancelled()
                    image = pdf_image(page, options.dpi)
                    if index in chosen:
                        image = watermark(image, options, options.dpi)
                    new_page = output.new_page(width=page.rect.width, height=page.rect.height)
                    # Discard the opaque alpha channel so PDF contains no mask/layer.
                    image = image.convertToFormat(QImage.Format.Format_RGB888)
                    new_page.insert_image(new_page.rect, stream=pdf_image_bytes(image, options))
                    progress(index + 1, len(doc))
                if cancelled():
                    raise Cancelled()
                output.set_metadata({'title': source.stem + '（水印已合并）', 'creator': '水印工坊'})
                output.save(temporary, garbage=4, deflate=True)
        else:
            frames = []
            with Image.open(source) as original:
                total = getattr(original, 'n_frames', 1)
                for index in range(total):
                    if cancelled():
                        raise Cancelled()
                    original.seek(index)
                    image = watermark(pil_image(original), options, options.dpi)
                    with Image.open(BytesIO(png_bytes(image))) as encoded:
                        frame = encoded.copy()
                    if source.suffix.lower() in {'.jpg', '.jpeg', '.bmp'}:
                        background = Image.new('RGB', frame.size, 'white')
                        background.paste(frame, mask=frame.getchannel('A'))
                        frame = background
                    frames.append(frame)
                    progress(index + 1, total)
            if cancelled():
                raise Cancelled()
            kwargs = {'dpi': (options.dpi, options.dpi)}
            if source.suffix.lower() in {'.jpg', '.jpeg'}:
                kwargs.update(quality=compression_quality(options), subsampling=0, optimize=True)
            elif source.suffix.lower() == '.webp':
                kwargs.update(lossless=options.compression == 0, quality=compression_quality(options), method=6)
            elif source.suffix.lower() == '.png':
                kwargs.update(compress_level=9)
            elif source.suffix.lower() in {'.tif', '.tiff'}:
                kwargs.update(compression='tiff_deflate', save_all=True, append_images=frames[1:])
            frames[0].save(temporary, **kwargs)
        if cancelled():
            raise Cancelled()
        # Windows rename fails if another export acquired the same destination.
        os.rename(temporary, destination)
        return destination
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
