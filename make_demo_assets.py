"""Generate shareable screenshots using synthetic document content only."""
from pathlib import Path
import tempfile

from PIL import Image, ImageDraw, ImageFont
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QColorDialog, QScrollArea

from main import MainWindow, configure_appearance, configure_language
from engine import Options

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'docs/images'


def create_demo(path):
    image = Image.new('RGB', (1680, 940), '#f7f8fc')
    draw = ImageDraw.Draw(image)
    font_path = 'C:/Windows/Fonts/msyh.ttc'
    title = ImageFont.truetype(font_path, 70)
    subtitle = ImageFont.truetype(font_path, 28)
    body = ImageFont.truetype(font_path, 34)
    number = ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf', 58)
    draw.rectangle((0, 0, 1680, 310), fill='#292649')
    draw.rounded_rectangle((90, 62, 275, 106), radius=12, fill='#7765df')
    draw.text((111, 67), '演示内容', font=subtitle, fill='white')
    draw.text((90, 138), '项目方案示例', font=title, fill='white')
    draw.text((93, 240), '所有内容均由软件生成，仅用于展示水印效果', font=subtitle, fill='#d6d2ef')
    for index, text in enumerate(['方案概览', '设计思路', '实施计划']):
        left = 90 + index * 510
        draw.rounded_rectangle((left, 370, left + 480, 800), radius=24, fill='white', outline='#e4e7f0', width=2)
        draw.text((left + 34, 402), f'0{index+1}', font=number, fill='#8b7cda')
        draw.text((left + 34, 497), text, font=body, fill='#242d43')
        for row, length in enumerate([390, 345, 365, 270]):
            draw.rounded_rectangle((left + 34, 584 + row * 38, left + length, 596 + row * 38), radius=6, fill='#e9ecf3')
    draw.text((92, 856), 'WATERMARK STUDIO   /   示例文件', font=subtitle, fill='#8b93a8')
    image.save(path)


def generate():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    configure_appearance(app)
    configure_language(app)
    with tempfile.TemporaryDirectory(prefix='watermark-demo-') as temporary:
        folder = Path(temporary)
        source = folder / '演示方案.png'
        create_demo(source)
        window = MainWindow(settings=QSettings(str(folder/'settings.ini'), QSettings.Format.IniFormat), interactive=False)
        window.show()
        window.add_files([str(source)])
        window.apply_options(Options(size=88, columns=3, rows=2, opacity=24, color='#7869ca'))
        window.folder_edit.setText('请选择输出文件夹')
        window.status.setText('演示界面  ·  所有文件内容均为生成的示例。')
        app.processEvents()
        window.refresh_preview()
        window.text_edit.clearFocus()
        app.processEvents()
        window.grab().save(str(OUTPUT / 'desktop.png'))
        window.options_panel.grab().save(str(OUTPUT / 'controls.png'))
        scroll = window.options_panel.findChild(QScrollArea)
        scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
        app.processEvents()
        window.grab().save(str(OUTPUT / 'export-settings.png'))
        menu = window.text_edit.createStandardContextMenu()
        menu.show()
        app.processEvents()
        menu.grab().save(str(OUTPUT / 'context-menu.png'))
        menu.close()
        dialog = QColorDialog(QColor(window.color), window)
        dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog)
        dialog.show()
        app.processEvents()
        dialog.grab().save(str(OUTPUT / 'color-dialog.png'))
        dialog.reject()
        shots = []
        for color in ['#34964b', '#ffffff', '#161b2b', '#6c5ce7']:
            window.color = color
            window.update_color()
            app.processEvents()
            shots.append(window.color_button.grab())
        scale = shots[0].devicePixelRatio()
        width = max(shot.width()/scale for shot in shots)
        height = sum(shot.height()/scale+12 for shot in shots)+12
        swatches = QPixmap(round((width+24)*scale), round(height*scale))
        swatches.setDevicePixelRatio(scale)
        swatches.fill(QColor('#f5f6fa'))
        painter = QPainter(swatches)
        top = 12
        for shot in shots:
            painter.drawPixmap(12, round(top), shot)
            top += shot.height()/scale+12
        painter.end()
        swatches.save(str(OUTPUT / 'color-swatches.png'))
        window.close()
    print('Generated shareable demo screenshots:', OUTPUT)


if __name__ == '__main__':
    generate()
