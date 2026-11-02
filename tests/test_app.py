"""Run with: python -m unittest discover -s tests -v"""
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from dataclasses import replace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pymupdf as fitz
from PIL import Image
from PySide6.QtCore import QEventLoop, QSettings, QTimer, Qt
from PySide6.QtWidgets import QApplication, QScrollArea

from engine import Options, Cancelled, export_file, page_count, selected_pages, watermark, pdf_image, png_bytes, preview
from main import MainWindow, STYLE

app = QApplication.instance() or QApplication([])
app.setStyle('Fusion')
app.setStyleSheet(STYLE)


class WatermarkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.pdf = self.root / '中文画册.pdf'
        with fitz.open() as doc:
            for index in range(3):
                page = doc.new_page(width=360, height=240)
                page.insert_text((30, 35), f'Original page {index + 1}', fontsize=16)
                page.draw_rect(fitz.Rect(50, 70, 300, 200), color=(0.1, 0.3, 0.6), fill=(0.9, 0.94, 1))
                if index == 2:
                    page.set_rotation(90)
            doc.save(self.pdf)
        self.png = self.root / '透明图片.png'
        Image.new('RGBA', (600, 400), (250, 250, 250, 110)).save(self.png)
        self.out = self.root / '导出'
        self.options = Options(size=28, columns=3, rows=2, opacity=35, compression=0)

    def tearDown(self):
        self.temp.cleanup()

    def test_page_ranges(self):
        self.assertEqual(selected_pages('1-3，5,3', 5), [0,1,2,4])
        for invalid in ['0', '3-2', '1,', '4', 'abc', '1--3']:
            with self.assertRaises(ValueError):
                selected_pages(invalid, 3)

    def test_pdf_flattening_dpi_ranges_rotations_and_source(self):
        before = hashlib.sha256(self.pdf.read_bytes()).digest()
        result = export_file(self.pdf, self.out, replace(self.options, pages='1,3'))
        with fitz.open(self.pdf) as original, fitz.open(result) as output:
            self.assertEqual(len(output), 3)
            self.assertFalse(output.get_ocgs())
            for index, page in enumerate(output):
                images = page.get_images(full=True)
                self.assertEqual(len(images), 1)
                self.assertEqual(images[0][1], 0)
                self.assertFalse(page.get_text().strip())
                self.assertFalse(list(page.annots() or []))
                self.assertEqual(page.rect, original[index].rect)
                self.assertAlmostEqual(images[0][2] / page.rect.width * 72, 100, delta=0.3)
                raw = pdf_image(original[index], 100)
                expected = watermark(raw, self.options, 100) if index != 1 else raw
                actual = fitz.Pixmap(output, images[0][0])
                expected_rgb = fitz.Pixmap(png_bytes(expected))
                if expected_rgb.alpha:
                    expected_rgb = fitz.Pixmap(expected_rgb, 0)
                self.assertEqual(actual.samples, expected_rgb.samples)
        self.assertEqual(hashlib.sha256(self.pdf.read_bytes()).digest(), before)

    def test_transparency_dimensions_collision(self):
        one = export_file(self.png, self.out, self.options)
        two = export_file(self.png, self.out, self.options)
        self.assertNotEqual(one, two)
        with Image.open(one) as image:
            self.assertEqual(image.size, (600,400))
            self.assertEqual(image.mode, 'RGBA')
            self.assertEqual(image.getpixel((0,0))[3], 110)
            self.assertGreater(image.getchannel('A').getextrema()[1], 110)

    def test_formats_and_multiframe_tiff(self):
        for extension in ['jpg', 'jpeg', 'bmp', 'webp', 'tiff', 'tif']:
            source = self.root / f'图片.{extension}'
            Image.new('RGB', (400,300), 'white').save(source)
            result = export_file(source, self.out, self.options)
            with Image.open(result) as image:
                self.assertEqual(image.size, (400,300))
                self.assertLess(image.convert('RGB').getextrema()[0][0], 255)
        source = self.root / '多页.tiff'
        Image.new('RGB', (400,300), 'white').save(source, save_all=True,
            append_images=[Image.new('RGB', (400,300), '#102040')])
        result = export_file(source, self.out, self.options)
        self.assertEqual(page_count(result), 2)
        self.assertFalse(preview(result, 1, self.options).isNull())

    def test_cancellation_leaves_no_partial_file(self):
        with self.assertRaises(Cancelled):
            export_file(self.pdf, self.out, self.options, cancelled=lambda: True)
        self.assertEqual(list(self.out.iterdir()), [])
        with self.assertRaises(ValueError):
            export_file(self.pdf, self.out, replace(self.options, pages='99'))
        self.assertEqual(list(self.out.iterdir()), [])

    def test_mid_document_cancellation_and_encrypted_pdf(self):
        event = threading.Event()
        with self.assertRaises(Cancelled):
            export_file(self.pdf, self.out, self.options,
                        progress=lambda done, total: event.set(), cancelled=event.is_set)
        self.assertEqual(list(self.out.iterdir()), [])
        protected = self.root / 'protected.pdf'
        with fitz.open(self.pdf) as doc:
            doc.save(protected, encryption=fitz.PDF_ENCRYPT_AES_256,
                     owner_pw='owner-password', user_pw='secret')
        with self.assertRaisesRegex(ValueError, '密码'):
            page_count(protected)

    def test_exif_orientation(self):
        source = self.root / 'rotated.jpg'
        image = Image.new('RGB', (120, 80), 'white')
        exif = Image.Exif()
        exif[274] = 6
        image.save(source, exif=exif)
        result = export_file(source, self.out, self.options)
        with Image.open(result) as output:
            self.assertEqual(output.size, (80, 120))
            self.assertNotEqual(output.getexif().get(274), 6)
    def test_centre_fonts_and_text_change_image(self):
        with fitz.open(self.pdf) as doc:
            base = pdf_image(doc[0], 100)
        first = watermark(base, replace(self.options, tiled=False), 100)
        second = watermark(base, replace(self.options, text='机密文件', family='SimSun', size=40), 100)
        self.assertNotEqual(png_bytes(base), png_bytes(first))
        self.assertNotEqual(png_bytes(first), png_bytes(second))

    def test_pdf_compression_and_resolution(self):
        lossless = export_file(self.pdf, self.out, self.options)
        compressed = export_file(self.pdf, self.out, replace(self.options, compression=80))
        for filename, expected_filter in [(lossless, '/FlateDecode'), (compressed, '/DCTDecode')]:
            with fitz.open(filename) as doc:
                for page in doc:
                    images = page.get_images(full=True)
                    self.assertEqual(len(images), 1)
                    self.assertEqual(images[0][1], 0)
                    filter_name = doc.xref_get_key(images[0][0], 'Filter')[1]
                    self.assertIn(expected_filter, filter_name)
        high_dpi = export_file(self.pdf, self.out, replace(self.options, dpi=200, compression=30))
        with fitz.open(high_dpi) as doc:
            self.assertAlmostEqual(doc[0].get_images()[0][2] / doc[0].rect.width * 72, 200, delta=0.3)

    def test_gui_preview_and_background_batch(self):
        settings = QSettings(str(self.root / 'settings.ini'), QSettings.Format.IniFormat)
        window = MainWindow(settings=settings, interactive=False)
        window.show()
        window.apply_options(self.options)
        window.dpi_slider.setValue(150)
        self.assertEqual(window.dpi_spin.value(), 150)
        window.dpi_spin.setValue(100)
        self.assertEqual(window.dpi_slider.value(), 100)
        window.compression_slider.setValue(50)
        self.assertEqual(window.get_options().compression, 50)
        window.add_files([str(self.pdf), str(self.png), str(self.pdf)])
        self.assertEqual(window.file_list.count(), 2)
        window.refresh_preview()
        self.assertIsNotNone(window.preview_image)
        before = png_bytes(window.preview_image)
        window.text_edit.setPlainText('内部资料')
        window.size_spin.setValue(38)
        window.refresh_preview()
        self.assertNotEqual(before, png_bytes(window.preview_image))
        window.mode_combo.setCurrentIndex(1)
        self.assertFalse(window.rows_spin.isEnabled())
        window.mode_combo.setCurrentIndex(0)
        self.assertTrue(window.rows_spin.isEnabled())
        window.folder_edit.setText(str(self.out))
        window.start_export()
        self.assertIsNotNone(window.worker)
        self.assertFalse(window.export_button.isEnabled())
        loop = QEventLoop()
        window.worker.finished.connect(loop.quit)
        QTimer.singleShot(30000, loop.quit)
        loop.exec()
        app.processEvents()
        self.assertIsNone(window.worker)
        self.assertEqual(window.last_errors, [])
        self.assertEqual(len(window.last_outputs), 2)
        self.assertTrue(window.export_button.isEnabled())
        self.assertEqual(window.progress_bar.value(), 100)
        window.close()
        window = MainWindow(settings=settings, interactive=False)
        self.assertEqual(window.text_edit.toPlainText(), '内部资料')
        window.close()

    def test_document_ui_screenshot(self):
        source = self.pdf
        window = MainWindow(settings=QSettings(str(self.root/'ui.ini'), QSettings.Format.IniFormat), interactive=False)
        window.show()
        window.add_files([str(source)])
        window.apply_options(Options(size=120))
        window.page_spin.setValue(1)
        app.processEvents()
        window.refresh_preview()
        app.processEvents()
        folder = Path(__file__).resolve().parent / 'artifacts'
        folder.mkdir(exist_ok=True)
        window.grab().save(str(folder / 'desktop-preview.png'))
        scroll = window.options_panel.findChild(QScrollArea)
        scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
        app.processEvents()
        window.grab().save(str(folder / 'desktop-sliders.png'))
        self.assertIsNotNone(window.preview_image)
        window.close()

    def test_batch_continues_after_bad_file(self):
        settings = QSettings(str(self.root/'error.ini'), QSettings.Format.IniFormat)
        window = MainWindow(settings=settings, interactive=False)
        window.add_files([str(self.pdf), str(self.png)])
        self.pdf.write_bytes(b'broken pdf')
        window.folder_edit.setText(str(self.out))
        # File unreadable since import: worker records failure and continues.
        from main import ExportWorker
        worker = ExportWorker([str(self.pdf), str(self.png)], str(self.out), self.options)
        result = []
        worker.completed.connect(lambda outputs, errors, cancelled: result.append((outputs, errors)))
        loop = QEventLoop()
        worker.finished.connect(loop.quit)
        worker.start()
        QTimer.singleShot(30000, loop.quit)
        loop.exec()
        app.processEvents()
        self.assertEqual(len(result[0][0]), 1)
        self.assertEqual(len(result[0][1]), 1)
        worker.wait()
        window.close()


if __name__ == '__main__':
    unittest.main()
