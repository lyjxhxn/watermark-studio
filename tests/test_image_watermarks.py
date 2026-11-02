from dataclasses import asdict, replace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pymupdf as fitz
from PIL import Image, ImageDraw, ImageChops
from PySide6.QtCore import Qt, QSettings, QPointF, QTimer, QRectF
from PySide6.QtGui import QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from engine import Options, export_file, watermark, preview, pdf_image, png_bytes, options_from_dict, validate_options
from image_watermarks import AssetCache, ImageWatermark, image_geometry
from main import MainWindow, configure_appearance, configure_language
from version import APP_VERSION
from pdf_watermark_dialog import PdfWatermarkDialog

app = QApplication.instance() or QApplication([])
configure_appearance(app)
configure_language(app)


class ImageWatermarkTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.cache = AssetCache(self.root/'cache')
        self.logo = self.root/'logo.png'
        logo = Image.new('RGBA', (100, 50))
        ImageDraw.Draw(logo).rectangle((10, 10, 89, 39), fill=(255, 0, 0, 128))
        logo.save(self.logo)
        self.mark = self.cache.import_image(self.logo)
        self.page_image = QImage(1000, 600, QImage.Format.Format_RGB888)
        self.page_image.fill(Qt.GlobalColor.white)
        self.options = Options(text_enabled=False, image_watermarks=(self.mark,), compression=0)
        self.source = self.root/'page.png'
        Image.new('RGB', (1000, 600), 'white').save(self.source)
        self.pdf = self.root/'pages.pdf'
        with fitz.open() as doc:
            for size in [(360, 240), (240, 360), (240, 240)]:
                page = doc.new_page(width=size[0], height=size[1])
                page.insert_text((20, 30), 'Synthetic document', fontsize=14)
            doc.save(self.pdf)
        self.windows = []

    def tearDown(self):
        for window in self.windows:
            if window.worker:
                window.worker.cancel_event.set()
                window.worker.wait(30000)
                app.processEvents()
            window.close()
        app.processEvents()
        self.temporary.cleanup()

    def window(self, settings=None):
        window = MainWindow(settings=settings or QSettings(str(self.root/'settings.ini'), QSettings.Format.IniFormat),
                            interactive=False, cache_dir=self.root/'gui-cache')
        self.windows.append(window)
        window.show()
        app.processEvents()
        return window

    def test_alpha_and_per_image_opacity(self):
        image = watermark(self.page_image, self.options, 100)
        self.assertEqual(image.pixelColor(405, 255).name(), '#ffffff')
        center = image.pixelColor(500, 300)
        self.assertEqual(center.red(), 255)
        self.assertAlmostEqual(center.green(), 127, delta=1)
        image = watermark(self.page_image, replace(self.options, image_watermarks=(replace(self.mark, opacity=50),)), 100)
        self.assertAlmostEqual(image.pixelColor(500, 300).green(), 191, delta=1)

    def test_pdf_page_import_selection_alpha_and_original_removal(self):
        source = self.root/'watermark.pdf'
        with fitz.open() as doc:
            for color in [(1,0,0),(0,1,0),(0,0,1)]:
                page = doc.new_page(width=100,height=100)
                page.draw_rect(fitz.Rect(10,10,90,90),fill=color,color=None,fill_opacity=.5)
            doc.save(source)
        dialog = PdfWatermarkDialog(source)
        dialog.show()
        app.processEvents()
        dialog.page_spin.setValue(2)
        self.assertEqual(dialog.selected_page_index,1)
        self.assertIsNotNone(dialog.page_pixmap)
        dialog.close()
        mark = self.cache.import_pdf(source,1)
        self.assertIn('第 2 页',mark.name)
        with Image.open(mark.asset_path) as image:
            pixel=image.getpixel((image.width//2,image.height//2))
            self.assertEqual(pixel[1],255)
            self.assertAlmostEqual(pixel[3],127,delta=2)
            self.assertEqual(image.getpixel((0,0))[3],0)
        window = self.window()
        def pick():
            chooser = app.activeModalWidget()
            chooser.page_spin.setValue(3)
            chooser.accept()
        QTimer.singleShot(100,pick)
        window.add_watermark_images([str(source)])
        self.assertIn('第 3 页',window.image_marks[0].name)
        self.assertGreater(window.image_assets[window.image_marks[0].uid].pixelColor(200,200).blue(),240)
        before=len(window.image_marks)
        QTimer.singleShot(100,lambda: app.activeModalWidget().reject())
        window.add_watermark_images([str(source)])
        self.assertEqual(len(window.image_marks),before)
        source.unlink()
        self.assertTrue(validate_options(replace(self.options,image_watermarks=(mark,))))
        with self.assertRaises((ValueError,OSError)):
            self.cache.import_pdf(source,0)

    def test_preview_scene_and_export_pixels_match(self):
        window = self.window()
        window.add_files([str(self.source)])
        window.apply_options(replace(self.options,image_watermarks=(replace(self.mark,center_x=.72,center_y=.43,width_ratio=.313,opacity=67),)))
        window.refresh_preview()
        window.canvas.set_editable(False)
        page = window.canvas.sceneRect()
        rendered=QImage(round(page.width()),round(page.height()),QImage.Format.Format_ARGB32_Premultiplied)
        rendered.fill(Qt.GlobalColor.transparent)
        painter=QPainter(rendered)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        window.canvas.scene().render(painter,QRectF(0,0,page.width(),page.height()),page,Qt.AspectRatioMode.IgnoreAspectRatio)
        painter.end()
        from io import BytesIO
        with Image.open(BytesIO(png_bytes(rendered))) as actual, Image.open(BytesIO(png_bytes(preview(self.source,0,window.get_options())))) as expected:
            difference=ImageChops.difference(actual.convert('RGB'),expected.convert('RGB'))
            self.assertLessEqual(max(high for low,high in difference.getextrema()),2)

    def test_layer_order_and_disabled_images(self):
        green = self.root/'green.png'
        Image.new('RGBA', (100,50), (0,255,0,255)).save(green)
        green_mark = self.cache.import_image(green)
        mixed = replace(self.options, image_watermarks=(self.mark, green_mark))
        color = watermark(self.page_image, mixed, 100).pixelColor(500,300)
        self.assertGreater(color.red(), 120)
        self.assertGreater(color.green(), 120)
        reversed_options = replace(mixed, image_watermarks=tuple(reversed(mixed.image_watermarks)))
        self.assertEqual(watermark(self.page_image, reversed_options,100).pixelColor(500,300).name(), '#00ff00')
        disabled = replace(mixed, image_watermarks=(replace(self.mark, enabled=False), green_mark))
        self.assertEqual(watermark(self.page_image, disabled,100).pixelColor(500,300).name(), '#00ff00')

    def test_shared_geometry_mixed_pages_and_flattening(self):
        options = replace(self.options, image_watermarks=(replace(self.mark, center_x=.95,center_y=.95,width_ratio=.8),), pages='1,3')
        result = export_file(self.pdf, self.root/'out', options)
        with fitz.open(self.pdf) as original, fitz.open(result) as output:
            for index, page in enumerate(output):
                images = page.get_images(full=True)
                self.assertEqual(len(images), 1)
                self.assertEqual(images[0][1], 0)
                self.assertFalse(page.get_text().strip())
                raw = pdf_image(original[index], 100)
                expected = watermark(raw, options,100) if index != 1 else raw
                expected = expected.convertToFormat(QImage.Format.Format_RGB888)
                self.assertEqual(fitz.Pixmap(output, images[0][0]).samples, fitz.Pixmap(png_bytes(expected)).samples)
                self.assertFalse(list(page.annots() or []))
                self.assertEqual(page.rect, original[index].rect)
        image = QImage(self.mark.asset_path)
        for size in [(1000,600), (600,1000), (200,100)]:
            rect = image_geometry(options.image_watermarks[0], *size, image)
            self.assertGreaterEqual(rect.left(), 0)
            self.assertGreaterEqual(rect.top(), 0)
            self.assertLessEqual(rect.right(), size[0])
            self.assertLessEqual(rect.bottom(), size[1])
            self.assertAlmostEqual(rect.width()/rect.height(), 2)

    def test_image_only_png_preserves_alpha_and_snapshot(self):
        source = self.root/'transparent.png'
        Image.new('RGBA', (1000,600), (0,0,0,0)).save(source)
        assets = validate_options(self.options)
        Path(self.mark.asset_path).unlink()
        with self.assertRaisesRegex(ValueError, '缺失'):
            validate_options(self.options)
        output = export_file(source,self.root/'out',self.options,image_assets=assets)
        with Image.open(output) as image:
            self.assertEqual(image.size, (1000,600))
            self.assertEqual(image.getpixel((0,0))[3], 0)
            self.assertEqual(image.getpixel((500,300))[3],128)
        with self.assertRaises(ValueError):
            export_file(self.source,self.root/'out',replace(self.options,image_watermarks=()))

    def test_cached_assets_survive_original_and_deduplicate_cleanup(self):
        duplicate = self.cache.import_image(self.logo)
        self.assertEqual(self.mark.asset_path, duplicate.asset_path)
        self.assertNotEqual(self.mark.uid, duplicate.uid)
        self.logo.unlink()
        self.assertTrue(validate_options(self.options))
        self.cache.cleanup([duplicate])
        self.assertTrue(Path(self.mark.asset_path).exists())
        self.cache.cleanup([])
        self.assertFalse(Path(self.mark.asset_path).exists())

    def test_bad_dynamic_and_fully_transparent_assets_rejected(self):
        transparent = self.root/'empty.png'
        Image.new('RGBA',(10,10)).save(transparent)
        with self.assertRaisesRegex(ValueError,'完全透明'):
            self.cache.import_image(transparent)
        animated = self.root/'animated.webp'
        Image.new('RGBA',(10,10),'red').save(animated,save_all=True,append_images=[Image.new('RGBA',(10,10),'blue')],duration=100)
        with self.assertRaisesRegex(ValueError,'静态'):
            self.cache.import_image(animated)
        broken = self.root/'broken.png'
        broken.write_bytes(b'broken')
        with self.assertRaisesRegex(ValueError,'读取'):
            self.cache.import_image(broken)

    def test_settings_migration_reopen_missing_asset_and_reset(self):
        settings = QSettings(str(self.root/'persist.ini'),QSettings.Format.IniFormat)
        settings.setValue('options',json.dumps({'text':'旧版设置','size':72}))
        window = self.window(settings)
        self.assertEqual(window.text_edit.toPlainText(),'旧版设置')
        self.assertEqual(window.image_marks,[])
        window.add_watermark_images([str(self.logo),str(self.logo)])
        window.text_enabled.setChecked(False)
        window.change_image_value('opacity',55)
        window.image_geometry_changed(window.selected_image_uid(),.7,.4,.3)
        window.save_settings()
        cached = window.image_marks[0].asset_path
        self.logo.unlink()
        window.close()
        reopened = self.window(settings)
        self.assertEqual(len(reopened.image_marks),2)
        self.assertFalse(reopened.text_enabled.isChecked())
        self.assertEqual(reopened.image_marks[0].opacity,55)
        self.assertEqual(reopened.image_marks[0].center_x,.7)
        Path(cached).unlink()
        reopened.reload_images()
        self.assertFalse(reopened.export_button.isEnabled())
        self.assertEqual(len(reopened.image_errors),2)
        reopened.reset_options()
        self.assertEqual(reopened.image_marks,[])
        self.assertTrue(reopened.text_enabled.isChecked())
        self.assertTrue(reopened.export_button.isEnabled())

    def test_gui_selection_order_page_exclusion_and_version(self):
        window = self.window()
        window.add_files([str(self.pdf)])
        window.add_watermark_images([str(self.logo),str(self.logo)])
        self.assertIn(APP_VERSION,window.windowTitle())
        self.assertEqual(window.version_label.text(),'v'+APP_VERSION)
        window.refresh_preview()
        top = window.image_marks[0].uid
        window.image_list.setCurrentRow(1)
        self.assertEqual([m.uid for m in window.image_marks][0],top)
        bottom_item = window.canvas.overlays[window.image_marks[1].uid]
        self.assertIs(window.canvas.selected_overlay(),bottom_item)
        for index,handle in enumerate(bottom_item.handles):
            target,corner = window.canvas.handle_at(window.canvas.mapFromScene(handle.scenePos()))
            self.assertIs(target,bottom_item)
            self.assertEqual(corner,index)
        window.move_image(-1)
        self.assertNotEqual(window.image_marks[0].uid,top)
        window.range_edit.setText('1')
        window.page_spin.setValue(2)
        window.refresh_preview()
        self.assertEqual(window.canvas.overlays,{})
        self.assertIn('不在',window.preview_info.text())
        window.set_busy(True)
        self.assertFalse(window.canvas.editable)
        self.assertFalse(window.options_panel.isEnabled())
        window.set_busy(False)
        self.assertTrue(window.canvas.editable)
        window.page_spin.setValue(1)
        window.refresh_preview()
        window.grab().save(str(self.root/'gui.png'))

    def test_mouse_drag_all_four_handles_and_window_resize(self):
        window = self.window()
        window.add_files([str(self.source)])
        window.add_watermark_images([str(self.logo)])
        window.text_enabled.setChecked(False)
        window.refresh_preview()
        window.preview_timer.stop()
        uid = window.image_marks[0].uid
        canvas = window.canvas
        item = canvas.overlays[uid]
        start = canvas.mapFromScene(item.mapRectToScene(item.boundingRect()).center())
        end = start + __import__('PySide6.QtCore',fromlist=['QPoint']).QPoint(35,20)
        with patch('main.preview',wraps=preview) as renderer:
            QTest.mousePress(canvas.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,start)
            QTest.mouseMove(canvas.viewport(),end,30)
            QTest.mouseRelease(canvas.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,end)
            self.assertGreater(window.image_marks[0].center_x,.5)
            self.assertEqual(renderer.call_count,0)
        window.resize(1120,790)
        app.processEvents()
        window.preview_timer.stop()
        for corner,signs in enumerate([(-1,-1),(1,-1),(1,1),(-1,1)]):
            window.center_image()
            window.change_image_value('width_ratio',.2)
            item = canvas.overlays[uid]
            before = item.width
            handle = item.handles[corner]
            start = canvas.mapFromScene(handle.scenePos())
            end = canvas.mapFromScene(handle.scenePos()+QPointF(signs[0]*40,signs[1]*40))
            QTest.mousePress(canvas.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,start)
            QTest.mouseMove(canvas.viewport(),end,30)
            QTest.mouseRelease(canvas.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,end)
            self.assertGreater(item.width,before,corner)
            self.assertAlmostEqual(item.width/item.height,2)
            rect = item.mapRectToScene(item.boundingRect())
            self.assertGreaterEqual(rect.left(),-1e-6)
            self.assertLessEqual(rect.right(),1000+1e-6)


if __name__ == '__main__':
    unittest.main()
