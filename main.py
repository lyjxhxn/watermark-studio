"""水印工坊 — Windows desktop watermark application."""
import json
import os
from pathlib import Path
import sys
import threading
from dataclasses import asdict, replace

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSettings, QUrl, QSize, QTranslator, QLibraryInfo, QRectF
from PySide6.QtGui import QColor, QDesktopServices, QFont, QFontDatabase, QIcon, QPixmap, QPalette, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QListWidget, QListWidgetItem, QSplitter,
    QScrollArea, QFormLayout, QPlainTextEdit, QComboBox, QDoubleSpinBox,
    QSpinBox, QSlider, QLineEdit, QColorDialog, QProgressBar, QMessageBox,
    QFrame, QSizePolicy, QAbstractItemView, QTabWidget, QCheckBox,
)

from engine import Options, SUPPORTED, Cancelled, export_file, page_count, preview, selected_pages, validate_options, options_from_dict
from single_instance import SingleInstance
from version import APP_VERSION
from image_watermarks import AssetCache, read_image, image_geometry
from watermark_canvas import WatermarkCanvas
from pdf_watermark_dialog import PdfWatermarkDialog

APP_NAME = '水印工坊'

STYLE = '''
QMainWindow, QWidget#root { background: #f5f6fa; color: #1b2540; }
QDialog { background: #f5f6fa; color: #26314a; }
QDialog QLabel { background: transparent; color: #26314a; }
QWidget { font-family: 'Microsoft YaHei UI', '微软雅黑'; font-size: 13px; color: #26314a; }
QFrame#card { background: white; border: 1px solid #e3e7ef; border-radius: 12px; }
QLabel#title { font-size: 25px; font-weight: 700; color: #18223b; }
QLabel#subtitle, QLabel#hint { color: #7a8499; font-size: 12px; }
QLabel#section { font-weight: 700; font-size: 15px; }
QLabel#badge { background: #ecebff; color: #6256cc; border-radius: 10px; padding: 5px 10px; }
QTabWidget::pane { border: 0; }
QTabBar::tab { background: #f4f5fa; color: #7a8499; padding: 8px 24px; border-radius: 6px; margin-right: 5px; }
QTabBar::tab:selected { background: #ece9ff; color: #6256cc; }
QCheckBox { spacing: 7px; }
QPushButton { background: white; border: 1px solid #dce1eb; border-radius: 7px; padding: 8px 12px; }
QPushButton:hover { background: #f0effc; border-color: #b5afe2; }
QPushButton:pressed { background: #e5e2fa; }
QPushButton:disabled { color: #a7adba; background: #f5f6f8; border-color: #e8ebf0; }
QPushButton#primary { color: white; background: #6c5ce7; border: 0; font-weight: 700; padding: 11px 25px; }
QPushButton#primary:hover { background: #5b4acf; }
QPushButton#primary:disabled { background: #beb7ee; }
QPushButton#quiet { background: transparent; border: 0; padding: 6px 8px; color: #768097; }
QPushButton#colorPickerButton { text-align: left; padding: 6px 12px; background: #fafbfe; }
QPushButton#colorPickerButton:hover { background: #f0effc; border-color: #b5afe2; }
QPushButton#colorPickerButton:pressed { background: #e5e2fa; }
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background: #fafbfe; border: 1px solid #dce1eb; border-radius: 6px; padding: 6px;
    selection-background-color: #6c5ce7;
}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: #8a7fed; }
QSpinBox, QDoubleSpinBox { padding-right: 34px; }
QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border; subcontrol-position: top right;
    width: 28px; margin-top: 1px; margin-right: 1px;
    background: #f0f2f8; border: 0; border-left: 1px solid #e3e7f0;
    border-top-right-radius: 5px;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border; subcontrol-position: bottom right;
    width: 28px; margin-bottom: 1px; margin-right: 1px;
    background: #f0f2f8; border: 0; border-left: 1px solid #e3e7f0;
    border-bottom-right-radius: 5px;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover { background: #e9e4ff; }
QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed,
QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed { background: #dcd4ff; }
QSpinBox::up-button:disabled, QDoubleSpinBox::up-button:disabled,
QSpinBox::down-button:disabled, QDoubleSpinBox::down-button:disabled { background: #f5f6fa; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    image: url("@ASSET_ROOT@/chevron-up.svg"); width: 12px; height: 12px;
}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    image: url("@ASSET_ROOT@/chevron-down.svg"); width: 12px; height: 12px;
}
QSpinBox::up-arrow:disabled, QDoubleSpinBox::up-arrow:disabled {
    image: url("@ASSET_ROOT@/chevron-up-disabled.svg");
}
QSpinBox::down-arrow:disabled, QDoubleSpinBox::down-arrow:disabled {
    image: url("@ASSET_ROOT@/chevron-down-disabled.svg");
}
QComboBox { padding-right: 34px; }
QComboBox::drop-down {
    subcontrol-origin: border; subcontrol-position: top right;
    border: 0; width: 30px; border-top-right-radius: 6px; border-bottom-right-radius: 6px;
}
QComboBox::drop-down:hover { background: #f0edf9; }
QComboBox::down-arrow { image: url("@ASSET_ROOT@/chevron-down.svg"); width: 12px; height: 12px; }
QComboBox::down-arrow:disabled { image: url("@ASSET_ROOT@/chevron-down-disabled.svg"); }
QListWidget { border: 0; background: transparent; outline: none; }
QListWidget::item { padding: 12px 9px; margin: 3px 0; border-radius: 8px; }
QListWidget::item:selected { background: #eeecff; color: #5848cd; }
QListWidget::item:hover:!selected { background: #f4f5f9; }
QScrollArea { border: 0; background: transparent; }
QWidget#previewCanvas { background: #e9edf4; border-radius: 8px; }
QSlider::groove:horizontal { height: 5px; background: #e5e6ee; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #8a7de8; border-radius: 2px; }
QSlider::handle:horizontal { background: #6c5ce7; width: 15px; margin: -5px 0; border-radius: 7px; }
QProgressBar { border: 0; background: #e6e8f1; border-radius: 4px; height: 7px; max-height: 7px; }
QProgressBar::chunk { background: #7b69e8; border-radius: 4px; }
QSplitter::handle { background: transparent; width: 12px; }
QScrollBar:vertical { width: 9px; background: transparent; }
QScrollBar::handle:vertical { background: #cfd4e1; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
'''
STYLE = STYLE.replace('@ASSET_ROOT@', Path(__file__).with_name('assets').as_posix())


def configure_language(app):
    translator = QTranslator(app)
    bundled = Path(__file__).with_name('translations') / 'qtbase_zh_CN.qm'
    loaded = translator.load(str(bundled))
    if not loaded:
        loaded = translator.load('qtbase_zh_CN', QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))
    if loaded:
        app.installTranslator(translator)
        # Keep the translator alive for all later menus and dialogs.
        app.qt_zh_translator = translator
    return loaded


def configure_appearance(app):
    # Match the whole application to its light UI, including popup palettes
    # and Windows title bars when the user's system uses dark mode.
    app.setStyle('Fusion')
    app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    palette = app.style().standardPalette()
    colors = {
        QPalette.ColorRole.Window: '#f5f6fa',
        QPalette.ColorRole.WindowText: '#26314a',
        QPalette.ColorRole.Base: '#ffffff',
        QPalette.ColorRole.AlternateBase: '#f5f6fa',
        QPalette.ColorRole.Text: '#26314a',
        QPalette.ColorRole.Button: '#ffffff',
        QPalette.ColorRole.ButtonText: '#26314a',
        QPalette.ColorRole.ToolTipBase: '#ffffff',
        QPalette.ColorRole.ToolTipText: '#26314a',
        QPalette.ColorRole.Highlight: '#6c5ce7',
        QPalette.ColorRole.HighlightedText: '#ffffff',
        QPalette.ColorRole.PlaceholderText: '#7a8499',
        QPalette.ColorRole.Link: '#6c5ce7',
    }
    for role, color in colors.items():
        palette.setColor(role, QColor(color))
    for role in [QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText]:
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor('#9aa3b4'))
    app.setPalette(palette)
    app.setFont(QFont('Microsoft YaHei UI', 10))
    app.setStyleSheet(STYLE)


def card():
    widget = QFrame()
    widget.setObjectName('card')
    return widget


def label(text, name=''):
    widget = QLabel(text)
    widget.setObjectName(name)
    return widget


class ExportWorker(QThread):
    progress = Signal(int, str)
    result = Signal(str, str)
    completed = Signal(object, object, bool)

    def __init__(self, sources, folder, options, image_assets=None):
        super().__init__()
        self.sources, self.folder, self.options = sources, folder, options
        self.image_assets = image_assets
        self.cancel_event = threading.Event()

    def run(self):
        outputs, errors = [], []
        cancelled = False
        for index, source in enumerate(self.sources):
            if self.cancel_event.is_set():
                cancelled = True
                break
            try:
                def update(done, total):
                    percentage = round((index + done / total) * 100 / len(self.sources))
                    self.progress.emit(percentage, f'{Path(source).name}  ·  {done}/{total} 页')
                destination = export_file(source, self.folder, self.options, update, self.cancel_event.is_set, self.image_assets)
                outputs.append(str(destination))
                self.result.emit(source, '已完成')
            except Cancelled:
                cancelled = True
                self.result.emit(source, '已取消')
                break
            except Exception as exc:
                errors.append(f'{Path(source).name}：{exc}')
                self.result.emit(source, '失败')
        self.completed.emit(outputs, errors, cancelled)


class MainWindow(QMainWindow):
    def __init__(self, settings=None, interactive=True, cache_dir=None):
        super().__init__()
        self.settings = settings or QSettings('WatermarkStudio', 'WatermarkStudio')
        self.interactive = interactive
        self.worker = None
        self.preview_image = None
        self.color = '#969696'
        self.last_outputs = []
        self.last_errors = []
        self.pending_summary = None
        self.image_marks = []
        self.image_assets = {}
        self.image_errors = {}
        self.asset_cache = AssetCache(cache_dir)
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(400)
        self.save_timer.timeout.connect(self.save_settings)
        self.setWindowTitle(f'{APP_NAME} v{APP_VERSION} · PDF 与图片水印')
        self.resize(1390, 900)
        self.setMinimumSize(1080, 760)
        self.setAcceptDrops(True)
        icon_path = Path(__file__).with_name('app.ico')
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(220)
        self.preview_timer.timeout.connect(self.refresh_preview)
        self.build_ui()
        self.load_settings()
        self.connect_controls()
        self.update_mode()
        self.sync_image_controls()

    def build_ui(self):
        root = QWidget()
        root.setObjectName('root')
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(25, 22, 25, 18)
        outer.setSpacing(18)
        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(4)
        name_line = QHBoxLayout()
        name_line.addWidget(label(APP_NAME, 'title'))
        self.version_label = label('v' + APP_VERSION, 'badge')
        name_line.addWidget(self.version_label)
        name_line.addStretch()
        titles.addLayout(name_line)
        titles.addWidget(label('让每一份文件，都有你的印记。', 'subtitle'))
        header.addLayout(titles)
        header.addStretch()
        header.addWidget(label('本地处理  ·  水印与内容合并', 'badge'))
        outer.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter, 1)
        self.file_panel = card()
        file_layout = QVBoxLayout(self.file_panel)
        file_layout.setContentsMargins(15, 18, 15, 14)
        files_header = QHBoxLayout()
        files_header.addWidget(label('文件列表', 'section'))
        files_header.addStretch()
        self.file_count = label('0 个文件', 'hint')
        files_header.addWidget(self.file_count)
        file_layout.addLayout(files_header)
        self.add_button = QPushButton('＋  添加 PDF / 图片')
        self.add_button.clicked.connect(self.choose_files)
        file_layout.addWidget(self.add_button)
        self.file_list = QListWidget()
        self.file_list.setWordWrap(True)
        self.file_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.file_list.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.file_list.currentItemChanged.connect(self.file_changed)
        file_layout.addWidget(self.file_list, 1)
        file_layout.addWidget(label('也可以把文件或文件夹拖到窗口', 'hint'))
        actions = QHBoxLayout()
        self.remove_button = QPushButton('移除所选')
        self.clear_button = QPushButton('清空')
        self.remove_button.setObjectName('quiet')
        self.clear_button.setObjectName('quiet')
        self.remove_button.clicked.connect(self.remove_current)
        self.clear_button.clicked.connect(self.clear_files)
        actions.addWidget(self.remove_button)
        actions.addWidget(self.clear_button)
        file_layout.addLayout(actions)
        splitter.addWidget(self.file_panel)

        self.preview_panel = card()
        preview_layout = QVBoxLayout(self.preview_panel)
        preview_layout.setContentsMargins(18, 18, 18, 16)
        preview_header = QHBoxLayout()
        preview_header.addWidget(label('效果预览', 'section'))
        preview_header.addStretch()
        self.page_spin = QSpinBox()
        self.page_spin.setRange(1, 1)
        self.page_spin.setFixedWidth(76)
        self.page_spin.valueChanged.connect(lambda: self.schedule_preview())
        preview_header.addWidget(label('页码', 'hint'))
        preview_header.addWidget(self.page_spin)
        self.page_total = label('/ 0', 'hint')
        preview_header.addWidget(self.page_total)
        preview_layout.addLayout(preview_header)
        self.preview_canvas = QWidget()
        self.preview_canvas.setObjectName('previewCanvas')
        canvas_layout = QVBoxLayout(self.preview_canvas)
        canvas_layout.setContentsMargins(16, 16, 16, 16)
        self.canvas = WatermarkCanvas()
        self.preview_label = self.canvas
        self.canvas.geometry_changed.connect(self.image_geometry_changed)
        self.canvas.image_selected.connect(self.canvas_image_selected)
        canvas_layout.addWidget(self.canvas)
        preview_layout.addWidget(self.preview_canvas, 1)
        self.preview_info = label('预览会按窗口缩放，导出使用右侧设置的分辨率。', 'hint')
        self.preview_info.setWordWrap(True)
        self.preview_info.setMinimumHeight(36)
        preview_layout.addWidget(self.preview_info)
        splitter.addWidget(self.preview_panel)

        self.options_panel = card()
        options_outer = QVBoxLayout(self.options_panel)
        options_outer.setContentsMargins(16, 18, 16, 10)
        options_outer.addWidget(label('水印设置', 'section'))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body.setStyleSheet('background: white;')
        settings_layout = QVBoxLayout(body)
        settings_layout.setContentsMargins(0, 8, 6, 8)
        self.watermark_tabs = QTabWidget()
        settings_layout.addWidget(self.watermark_tabs)
        text_page = QWidget()
        layout = QVBoxLayout(text_page)
        layout.setContentsMargins(0, 10, 0, 8)
        layout.setSpacing(10)
        self.text_enabled = QCheckBox('启用文字水印')
        self.text_enabled.setChecked(True)
        layout.addWidget(self.text_enabled)
        layout.addWidget(label('水印文字'))
        self.text_edit = QPlainTextEdit('水印')
        self.text_edit.setMaximumHeight(74)
        self.text_edit.setPlaceholderText('输入文字，支持换行')
        layout.addWidget(self.text_edit)
        layout.addWidget(label('字体'))
        self.font_combo = QComboBox()
        self.font_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.font_combo.setMinimumContentsLength(12)
        self.font_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.font_combo.setMaxVisibleItems(16)
        families = QFontDatabase.families()
        preferred = ['微软雅黑', 'Microsoft YaHei', 'Microsoft YaHei UI', '宋体', 'SimSun',
                     '黑体', 'SimHei', '楷体', 'KaiTi', '仿宋', 'FangSong', '等线', 'DengXian',
                     'Arial', 'Times New Roman', 'Calibri']
        common = [family for family in preferred if family in families]
        for family in common:
            self.font_combo.addItem(family)
        if common:
            self.font_combo.insertSeparator(self.font_combo.count())
        for family in sorted(set(families) - set(common), key=str.casefold):
            self.font_combo.addItem(family)
        self.font_combo.setToolTip('列出本机已安装字体；安装新字体后重启软件即可使用。')
        layout.addWidget(self.font_combo)
        form = QFormLayout()
        form.setSpacing(10)
        self.size_spin = QDoubleSpinBox()
        self.size_spin.setRange(6, 600)
        self.size_spin.setDecimals(0)
        self.size_spin.setSuffix(' pt')
        self.size_spin.setValue(96)
        form.addRow('文字大小', self.size_spin)
        self.angle_spin = QSpinBox()
        self.angle_spin.setRange(-180, 180)
        self.angle_spin.setSuffix('°')
        self.angle_spin.setValue(-30)
        form.addRow('旋转角度', self.angle_spin)
        self.color_button = QPushButton('选择颜色')
        self.color_button.setObjectName('colorPickerButton')
        self.color_button.setIconSize(QSize(20, 20))
        self.color_button.setToolTip('点击选择水印文字颜色')
        self.color_button.clicked.connect(self.choose_color)
        form.addRow('文字颜色', self.color_button)
        layout.addLayout(form)
        opacity_line = QHBoxLayout()
        opacity_line.addWidget(label('不透明度'))
        opacity_line.addStretch()
        self.opacity_value = label('25%', 'hint')
        opacity_line.addWidget(self.opacity_value)
        layout.addLayout(opacity_line)
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(1, 100)
        self.opacity_slider.setValue(25)
        self.opacity_slider.setToolTip('数值越小，水印越透明。')
        layout.addWidget(self.opacity_slider)
        layout.addWidget(label('排列方式'))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(['重复平铺整个页面', '单个水印居中'])
        layout.addWidget(self.mode_combo)
        grid_form = QFormLayout()
        self.columns_spin = QSpinBox()
        self.columns_spin.setRange(1, 20)
        self.columns_spin.setValue(4)
        self.rows_spin = QSpinBox()
        self.rows_spin.setRange(1, 20)
        self.rows_spin.setValue(3)
        grid_form.addRow('每行数量', self.columns_spin)
        grid_form.addRow('行数', self.rows_spin)
        layout.addLayout(grid_form)
        self.watermark_tabs.addTab(text_page, '文字')
        self.watermark_tabs.addTab(self.build_image_panel(), '图片 / PDF')
        layout = settings_layout
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet('color: #e7eaf1;')
        layout.addWidget(line)
        output_form = QFormLayout()
        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(72, 600)
        self.dpi_spin.setValue(100)
        self.dpi_spin.setSuffix(' DPI')
        self.dpi_spin.setToolTip('PDF 按此分辨率导出；图片保持原有像素尺寸。')
        output_form.addRow('导出分辨率', self.dpi_spin)
        layout.addLayout(output_form)
        self.dpi_slider = QSlider(Qt.Orientation.Horizontal)
        self.dpi_slider.setRange(72, 600)
        self.dpi_slider.setValue(100)
        self.dpi_slider.setToolTip('拖动调整 PDF 分辨率，也可在上方直接输入数值。')
        self.dpi_slider.valueChanged.connect(self.dpi_spin.setValue)
        self.dpi_spin.valueChanged.connect(self.dpi_slider.setValue)
        layout.addWidget(self.dpi_slider)
        layout.addWidget(label('72 DPI 小文件    ·    300 DPI 打印    ·    600 DPI', 'hint'))
        compression_line = QHBoxLayout()
        compression_line.addWidget(label('压缩强度'))
        compression_line.addStretch()
        self.compression_value = label('20% · 质量 87', 'hint')
        compression_line.addWidget(self.compression_value)
        layout.addLayout(compression_line)
        self.compression_slider = QSlider(Qt.Orientation.Horizontal)
        self.compression_slider.setRange(0, 100)
        self.compression_slider.setValue(20)
        self.compression_slider.setToolTip('仅对 PDF、JPG/JPEG、WebP 生效。0 为最高质量；PDF/WebP 在 0 时使用无损图像压缩。')
        self.compression_slider.valueChanged.connect(self.update_compression_label)
        layout.addWidget(self.compression_slider)
        compression_scale = QHBoxLayout()
        compression_scale.addWidget(label('更清晰', 'hint'))
        compression_scale.addStretch()
        compression_scale.addWidget(label('文件更小', 'hint'))
        layout.addLayout(compression_scale)
        compression_hint = label('适用 PDF、JPG、WebP；PNG、BMP、TIFF 保持无损。', 'hint')
        compression_hint.setWordWrap(True)
        layout.addWidget(compression_hint)
        layout.addWidget(label('PDF 加水印页码'))
        self.range_edit = QLineEdit()
        self.range_edit.setPlaceholderText('留空为全部，例如 1-3,5,8')
        self.range_edit.setToolTip('未选中的页也会保留；图片文件忽略此设置。')
        layout.addWidget(self.range_edit)
        note = label('PDF 每页与水印合成一张图片；图片水印直接写入像素。图片保持原尺寸。', 'hint')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.reset_button = QPushButton('恢复默认设置')
        self.reset_button.setObjectName('quiet')
        self.reset_button.clicked.connect(self.reset_options)
        layout.addWidget(self.reset_button)
        layout.addStretch()
        scroll.setWidget(body)
        options_outer.addWidget(scroll)
        splitter.addWidget(self.options_panel)
        splitter.setSizes([250, 700, 340])
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setCollapsible(2, False)
        self.options_panel.setMinimumWidth(285)
        self.file_panel.setMinimumWidth(205)

        footer = QHBoxLayout()
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText('添加文件后，将默认保存到原文件旁的“水印输出”文件夹')
        footer.addWidget(label('保存到'))
        footer.addWidget(self.folder_edit, 1)
        self.browse_button = QPushButton('选择文件夹')
        self.browse_button.clicked.connect(self.choose_folder)
        footer.addWidget(self.browse_button)
        self.open_button = QPushButton('打开输出目录')
        self.open_button.clicked.connect(self.open_folder)
        footer.addWidget(self.open_button)
        self.cancel_button = QPushButton('取消导出')
        self.cancel_button.clicked.connect(self.cancel_export)
        self.cancel_button.hide()
        footer.addWidget(self.cancel_button)
        self.export_button = QPushButton('开始批量导出')
        self.export_button.setObjectName('primary')
        self.export_button.clicked.connect(self.start_export)
        footer.addWidget(self.export_button)
        outer.addLayout(footer)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        outer.addWidget(self.progress_bar)
        self.status = label('就绪  ·  原文件会保留，重名输出会自动编号。', 'hint')
        self.status.setWordWrap(True)
        outer.addWidget(self.status)

    def build_image_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 10, 0, 8)
        layout.setSpacing(10)
        self.add_image_button = QPushButton('＋  添加图片 / PDF 水印')
        self.add_image_button.clicked.connect(self.choose_watermark_images)
        layout.addWidget(self.add_image_button)
        self.image_list = QListWidget()
        self.image_list.setIconSize(QSize(32, 32))
        self.image_list.setMinimumHeight(142)
        self.image_list.setMaximumHeight(180)
        self.image_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.image_list.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.image_list.currentItemChanged.connect(lambda: self.image_selection_changed())
        self.image_list.itemChanged.connect(self.image_enabled_changed)
        layout.addWidget(self.image_list)
        buttons = QHBoxLayout()
        self.image_up_button = QPushButton('上移一层')
        self.image_down_button = QPushButton('下移一层')
        self.image_remove_button = QPushButton('移除')
        self.image_up_button.clicked.connect(lambda: self.move_image(-1))
        self.image_down_button.clicked.connect(lambda: self.move_image(1))
        self.image_remove_button.clicked.connect(self.remove_image)
        for button in [self.image_up_button, self.image_down_button, self.image_remove_button]:
            button.setStyleSheet('padding: 7px 6px;')
            buttons.addWidget(button)
        layout.addLayout(buttons)
        form = QFormLayout()
        self.image_width_spin = QDoubleSpinBox()
        self.image_width_spin.setRange(1, 100)
        self.image_width_spin.setDecimals(1)
        self.image_width_spin.setSuffix(' %')
        self.image_width_spin.setToolTip('占页面宽度的比例，保持图片原始宽高比。')
        self.image_width_spin.valueChanged.connect(lambda value: self.change_image_value('width_ratio', value/100))
        form.addRow('图片大小', self.image_width_spin)
        self.image_opacity_spin = QSpinBox()
        self.image_opacity_spin.setRange(1, 100)
        self.image_opacity_spin.setSuffix(' %')
        self.image_opacity_spin.setToolTip('与图片原有的透明通道叠加；100% 保留原图透明效果。')
        self.image_opacity_spin.valueChanged.connect(lambda value: self.change_image_value('opacity', value))
        form.addRow('不透明度', self.image_opacity_spin)
        layout.addLayout(form)
        self.image_center_button = QPushButton('将所选图片居中')
        self.image_center_button.clicked.connect(self.center_image)
        layout.addWidget(self.image_center_button)
        self.image_hint = label('添加透明 PNG 等图片，在预览中拖动位置、拉动四角缩放。列表顶部显示在最前方。', 'hint')
        self.image_hint.setWordWrap(True)
        layout.addWidget(self.image_hint)
        layout.addStretch()
        return panel

    def selected_image_uid(self):
        item = self.image_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else ''

    def selected_image(self):
        uid = self.selected_image_uid()
        return next((mark for mark in self.image_marks if mark.uid == uid), None)

    def reload_images(self, selected_uid=None):
        selected_uid = self.selected_image_uid() if selected_uid is None else selected_uid
        self.image_assets, self.image_errors = {}, {}
        self.image_list.blockSignals(True)
        self.image_list.clear()
        for index, mark in enumerate(self.image_marks):
            item = QListWidgetItem(mark.name)
            item.setData(Qt.ItemDataRole.UserRole, mark.uid)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if mark.enabled else Qt.CheckState.Unchecked)
            try:
                image = read_image(mark)
                self.image_assets[mark.uid] = image
                item.setIcon(QIcon(QPixmap.fromImage(image)))
                item.setToolTip(mark.name)
            except ValueError as exc:
                self.image_errors[mark.uid] = str(exc)
                item.setText('缺失 / 损坏 · ' + mark.name)
                item.setForeground(QColor('#c85b61'))
                item.setToolTip(str(exc))
            self.image_list.addItem(item)
            if mark.uid == selected_uid:
                self.image_list.setCurrentRow(index)
        self.image_list.blockSignals(False)
        self.image_selection_changed()
        self.update_export_availability()

    def choose_watermark_images(self):
        paths, _ = QFileDialog.getOpenFileNames(self, '添加图片 / PDF 水印', '',
            '图片与 PDF (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff *.pdf)')
        self.add_watermark_images(paths)

    def add_watermark_images(self, paths):
        if self.worker:
            return
        errors, selected = [], self.selected_image_uid()
        for path in paths:
            try:
                if Path(path).suffix.lower() == '.pdf':
                    count = page_count(path)
                    page_index = 0
                    if count > 1:
                        dialog = PdfWatermarkDialog(path,self)
                        if dialog.exec() != PdfWatermarkDialog.DialogCode.Accepted:
                            continue
                        page_index = dialog.selected_page_index
                    mark = self.asset_cache.import_pdf(path,page_index)
                else:
                    mark = self.asset_cache.import_image(path)
                offset = 0.03 * (len(self.image_marks) % 6)
                mark = replace(mark, center_x=0.5+offset, center_y=0.5+offset)
                self.image_marks.insert(0, mark)
                selected = mark.uid
            except Exception as exc:
                errors.append(f'{Path(path).name}：{exc}')
        self.reload_images(selected)
        self.watermark_tabs.setCurrentIndex(1)
        self.images_changed()
        self.save_settings()
        if errors:
            self.show_message('部分图片未添加', '\n'.join(errors), warning=True)

    def image_selection_changed(self):
        self.canvas.select_image(self.selected_image_uid())
        self.sync_image_controls()

    def canvas_image_selected(self, uid):
        self.image_list.blockSignals(True)
        row = next((index for index, mark in enumerate(self.image_marks) if mark.uid == uid), -1)
        self.image_list.setCurrentRow(row)
        self.image_list.blockSignals(False)
        self.sync_image_controls()
        if uid:
            self.watermark_tabs.setCurrentIndex(1)

    def sync_image_controls(self):
        mark = self.selected_image()
        valid = mark is not None and mark.uid in self.image_assets
        for widget in [self.image_width_spin, self.image_opacity_spin, self.image_center_button]:
            widget.setEnabled(valid)
        row = self.image_list.currentRow()
        self.image_remove_button.setEnabled(mark is not None)
        self.image_up_button.setEnabled(row > 0)
        self.image_down_button.setEnabled(0 <= row < len(self.image_marks)-1)
        if mark:
            self.image_width_spin.blockSignals(True)
            self.image_opacity_spin.blockSignals(True)
            width = mark.width_ratio
            if valid and self.canvas.background_item is not None:
                page = self.canvas.sceneRect()
                width = image_geometry(mark, page.width(), page.height(), self.image_assets[mark.uid]).width()/page.width()
            self.image_width_spin.setValue(width * 100)
            self.image_opacity_spin.setValue(mark.opacity)
            self.image_width_spin.blockSignals(False)
            self.image_opacity_spin.blockSignals(False)
        if mark and mark.uid in self.image_errors:
            self.image_hint.setText(self.image_errors[mark.uid])
        else:
            self.image_hint.setText('在预览中拖动位置、拉动四角等比缩放。布局统一应用到选定页和批量文件，图片会自动保存到本机。')

    def images_changed(self):
        self.canvas.update_layers(self.image_marks, self.image_assets, self.selected_image_uid())
        self.sync_image_controls()
        self.update_export_availability()
        self.save_timer.start()

    def image_enabled_changed(self, item):
        if self.worker:
            return
        uid = item.data(Qt.ItemDataRole.UserRole)
        self.image_marks = [replace(mark, enabled=item.checkState() == Qt.CheckState.Checked) if mark.uid == uid else mark for mark in self.image_marks]
        self.images_changed()

    def change_image_value(self, field, value):
        if self.worker:
            return
        uid = self.selected_image_uid()
        self.image_marks = [replace(mark, **{field: value}) if mark.uid == uid else mark for mark in self.image_marks]
        self.images_changed()

    def image_geometry_changed(self, uid, x, y, width):
        if self.worker:
            return
        self.image_marks = [replace(mark, center_x=x, center_y=y, width_ratio=width) if mark.uid == uid else mark for mark in self.image_marks]
        self.sync_image_controls()
        self.save_timer.start()

    def remove_image(self):
        if self.worker:
            return
        row = self.image_list.currentRow()
        if row >= 0:
            self.image_marks.pop(row)
            selected = self.image_marks[min(row, len(self.image_marks)-1)].uid if self.image_marks else ''
            self.reload_images(selected)
            self.images_changed()
            self.save_settings()

    def move_image(self, direction):
        if self.worker:
            return
        row = self.image_list.currentRow()
        target = row + direction
        if 0 <= row < len(self.image_marks) and 0 <= target < len(self.image_marks):
            uid = self.image_marks[row].uid
            self.image_marks[row], self.image_marks[target] = self.image_marks[target], self.image_marks[row]
            self.reload_images(uid)
            self.images_changed()

    def center_image(self):
        if self.worker:
            return
        uid = self.selected_image_uid()
        self.image_marks = [replace(mark, center_x=0.5, center_y=0.5) if mark.uid == uid else mark for mark in self.image_marks]
        self.images_changed()

    def update_export_availability(self, *args):
        valid = ((self.text_enabled.isChecked() and bool(self.text_edit.toPlainText().strip())) or
                 any(mark.enabled for mark in self.image_marks))
        valid = valid and all(not mark.enabled or mark.uid in self.image_assets for mark in self.image_marks)
        self.export_button.setEnabled(bool(valid) and not getattr(self, '_busy', False))

    def save_settings(self):
        self.settings.setValue('options', json.dumps(asdict(self.get_options()), ensure_ascii=False))
        self.settings.setValue('folder', self.folder_edit.text())
        self.settings.sync()
        if self.settings.status() == QSettings.Status.NoError:
            self.asset_cache.cleanup(self.image_marks)
        else:
            self.status.setText('设置保存失败，请检查用户数据目录的写入权限。')

    def connect_controls(self):
        self.text_enabled.toggled.connect(self.schedule_preview)
        self.text_enabled.toggled.connect(self.update_export_availability)
        self.text_edit.textChanged.connect(self.update_export_availability)
        self.text_edit.textChanged.connect(self.schedule_preview)
        self.font_combo.currentTextChanged.connect(self.schedule_preview)
        for spin in [self.size_spin, self.angle_spin, self.columns_spin, self.rows_spin, self.dpi_spin]:
            spin.valueChanged.connect(self.schedule_preview)
        self.opacity_slider.valueChanged.connect(lambda value: self.opacity_value.setText(f'{value}%'))
        self.opacity_slider.valueChanged.connect(self.schedule_preview)
        self.mode_combo.currentIndexChanged.connect(self.update_mode)
        self.mode_combo.currentIndexChanged.connect(self.schedule_preview)
        self.range_edit.textChanged.connect(self.schedule_preview)

    def get_options(self):
        return Options(text=self.text_edit.toPlainText(), family=self.font_combo.currentText(),
                       size=self.size_spin.value(), opacity=self.opacity_slider.value(),
                       angle=self.angle_spin.value(), color=self.color,
                       tiled=self.mode_combo.currentIndex() == 0,
                       columns=self.columns_spin.value(), rows=self.rows_spin.value(),
                       dpi=self.dpi_spin.value(), compression=self.compression_slider.value(), pages=self.range_edit.text(),
                       text_enabled=self.text_enabled.isChecked(), image_watermarks=tuple(self.image_marks))

    def apply_options(self, options):
        self.text_enabled.setChecked(options.text_enabled)
        self.text_edit.setPlainText(options.text)
        index = self.font_combo.findText(options.family, Qt.MatchFlag.MatchExactly)
        if index >= 0:
            self.font_combo.setCurrentIndex(index)
        self.size_spin.setValue(options.size)
        self.opacity_slider.setValue(options.opacity)
        self.opacity_value.setText(f'{options.opacity}%')
        self.angle_spin.setValue(options.angle)
        self.color = options.color
        self.update_color()
        self.mode_combo.setCurrentIndex(0 if options.tiled else 1)
        self.columns_spin.setValue(options.columns)
        self.rows_spin.setValue(options.rows)
        self.dpi_spin.setValue(options.dpi)
        self.compression_slider.setValue(options.compression)
        self.update_compression_label()
        self.range_edit.setText(options.pages)
        self.image_marks = list(options.image_watermarks)
        self.reload_images()

    def update_compression_label(self, *args):
        value = self.compression_slider.value()
        text = '0% · PDF/WebP 无损' if value == 0 else f'{value}% · 质量 {round(100-value*0.65)}'
        self.compression_value.setText(text)

    def load_settings(self):
        try:
            options = options_from_dict(json.loads(self.settings.value('options', '{}')))
            self.apply_options(options)
            self.folder_edit.setText(self.settings.value('folder', ''))
        except (ValueError, TypeError):
            self.apply_options(Options())

    def reset_options(self):
        self.apply_options(Options())
        self.save_settings()
        self.schedule_preview()

    def update_mode(self):
        tiled = self.mode_combo.currentIndex() == 0
        self.columns_spin.setEnabled(tiled)
        self.rows_spin.setEnabled(tiled)

    def update_color(self):
        self.color_button.setText(self.color.upper())
        # Paint a padded swatch rather than using a thick CSS border, which
        # joins the button's corners and makes the color look clipped.
        swatch = QPixmap(60, 60)
        swatch.setDevicePixelRatio(3)
        swatch.fill(Qt.GlobalColor.transparent)
        painter = QPainter(swatch)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor('#d9dfeb'), 1))
        painter.setBrush(QColor('#ffffff'))
        painter.drawRoundedRect(QRectF(0.5, 0.5, 19, 19), 5, 5)
        painter.setPen(QPen(QColor('#cfd6e2'), 0.7))
        painter.setBrush(QColor(self.color))
        painter.drawRoundedRect(QRectF(3, 3, 14, 14), 3, 3)
        painter.end()
        self.color_button.setIcon(QIcon(swatch))
        self.color_button.setAccessibleName('选择水印文字颜色，当前颜色 ' + self.color.upper())

    def choose_color(self):
        color = QColorDialog.getColor(QColor(self.color), self, '选择水印文字颜色',
                                      QColorDialog.ColorDialogOption.DontUseNativeDialog)
        if color.isValid():
            self.color = color.name()
            self.update_color()
            self.schedule_preview()

    def choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, '添加 PDF 或图片', '',
                    'PDF 与图片 (*.pdf *.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff);;所有文件 (*)')
        self.add_files(paths)

    def activate_existing(self, paths):
        if paths and not self.worker:
            self.add_files([path for path in paths if Path(path).is_file()])
        if self.isMinimized():
            self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.show()
        self.raise_()
        self.activateWindow()
        QApplication.alert(self)

    def add_files(self, paths):
        if self.worker:
            return
        existing = {self.file_list.item(i).data(Qt.ItemDataRole.UserRole)['path'] for i in range(self.file_list.count())}
        errors = []
        added = 0
        for value in paths:
            path = Path(value).resolve()
            key = str(path)
            if key in existing:
                continue
            if path.suffix.lower() not in SUPPORTED:
                errors.append(f'{path.name}：不支持此格式')
                continue
            try:
                count = page_count(path)
                if count < 1:
                    raise ValueError('文件中没有可用页面')
            except Exception as exc:
                errors.append(f'{path.name}：{exc}')
                continue
            info = {'path': key, 'count': count, 'status': ''}
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, info)
            item.setToolTip(key)
            self.update_item(item)
            self.file_list.addItem(item)
            existing.add(key)
            added += 1
            if not self.folder_edit.text().strip():
                self.folder_edit.setText(str(path.parent / '水印输出'))
        self.file_count.setText(f'{self.file_list.count()} 个文件')
        if self.file_list.currentRow() < 0 and self.file_list.count():
            self.file_list.setCurrentRow(0)
        if errors:
            self.status.setText(f'已添加 {added} 个文件，{len(errors)} 个文件未添加。')
            self.show_message('部分文件未添加', '\n'.join(errors), warning=True)
        else:
            self.status.setText(f'已添加 {added} 个文件  ·  可直接调整右侧设置。')

    def update_item(self, item):
        info = item.data(Qt.ItemDataRole.UserRole)
        path = Path(info['path'])
        suffix = path.suffix[1:].upper()
        status = f"  ·  {info['status']}" if info['status'] else ''
        item.setText(f"{path.name}\n{suffix}  ·  {info['count']} 页{status}")

    def file_changed(self, item, previous=None):
        self.page_spin.blockSignals(True)
        self.page_spin.setRange(1, item.data(Qt.ItemDataRole.UserRole)['count'] if item else 1)
        self.page_spin.setValue(1)
        self.page_spin.blockSignals(False)
        self.page_total.setText('/ ' + str(item.data(Qt.ItemDataRole.UserRole)['count'] if item else 0))
        self.schedule_preview()

    def remove_current(self):
        row = self.file_list.currentRow()
        if row >= 0:
            self.file_list.takeItem(row)
        self.file_count.setText(f'{self.file_list.count()} 个文件')
        self.schedule_preview()

    def clear_files(self):
        self.file_list.clear()
        self.file_count.setText('0 个文件')
        self.schedule_preview()

    def schedule_preview(self, *args):
        self.preview_timer.start()

    def refresh_preview(self):
        item = self.file_list.currentItem()
        if not item:
            self.preview_image = None
            self.canvas.show_message('拖入 PDF 或图片\n即可预览水印效果')
            self.preview_info.setText('预览会按窗口缩放，导出使用右侧设置的分辨率。')
            return
        try:
            source = item.data(Qt.ItemDataRole.UserRole)['path']
            options = self.get_options()
            self.preview_image = preview(source, self.page_spin.value() - 1, options, include_images=False)
            allowed = Path(source).suffix.lower() != '.pdf' or self.page_spin.value()-1 in selected_pages(options.pages, item.data(Qt.ItemDataRole.UserRole)['count'])
            self.canvas.set_page(self.preview_image, self.image_marks, self.image_assets, allowed, self.selected_image_uid())
            note = '拖动图片移动，拉动四角等比缩放。' if allowed else '此页不在水印页码范围内，无法编辑水印。'
            if self.image_errors:
                note = '部分水印副本缺失或损坏，请在“图片 / PDF”页移除后重新添加。'
            self.preview_info.setText(f'{Path(source).name}  ·  第 {self.page_spin.value()} 页\n{note}')
            self.sync_image_controls()
        except Exception as exc:
            self.preview_image = None
            self.canvas.show_message('无法显示预览\n' + str(exc))
            self.preview_info.setText('请检查文件或页码设置。')

    def fit_preview(self):
        self.canvas.fit_page()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self.fit_preview)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, '选择输出文件夹', self.folder_edit.text())
        if folder:
            self.folder_edit.setText(folder)

    def open_folder(self):
        folder = Path(self.folder_edit.text().strip())
        if self.folder_edit.text().strip() and folder.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        else:
            self.show_message('输出目录', '请先选择或导出到一个有效的文件夹。')

    def set_busy(self, busy):
        self._busy = busy
        self.canvas.set_editable(not busy)
        for widget in [self.file_panel, self.options_panel, self.folder_edit, self.browse_button, self.export_button]:
            widget.setEnabled(not busy)
        self.cancel_button.setVisible(busy)
        self.cancel_button.setEnabled(busy)
        self.update_export_availability()

    def start_export(self):
        if self.worker:
            return
        sources = [self.file_list.item(i).data(Qt.ItemDataRole.UserRole)['path'] for i in range(self.file_list.count())]
        if not sources:
            self.show_message('请先添加文件', '添加 PDF 或图片后即可开始导出。')
            return
        options = self.get_options()
        try:
            image_assets = validate_options(options)
        except (ValueError, OSError) as exc:
            self.show_message('请检查水印', str(exc), warning=True)
            return
        if not self.folder_edit.text().strip():
            self.show_message('请选择保存位置', '设置一个输出文件夹后即可开始导出。')
            return
        try:
            for source in sources:
                if Path(source).suffix.lower() == '.pdf':
                    selected_pages(options.pages, page_count(source))
        except Exception as exc:
            self.show_message('请检查页码', f'{Path(source).name}\n{exc}', warning=True)
            return
        self.last_outputs, self.last_errors = [], []
        self.progress_bar.setValue(0)
        self.set_busy(True)
        self.status.setText('正在准备导出…')
        self.worker = ExportWorker(sources, self.folder_edit.text().strip(), options, image_assets)
        self.worker.progress.connect(self.on_progress)
        self.worker.result.connect(self.on_result)
        self.worker.completed.connect(self.on_completed)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.start()

    def on_progress(self, value, text):
        self.progress_bar.setValue(value)
        self.status.setText('正在导出  ·  ' + text)

    def on_result(self, source, status):
        for index in range(self.file_list.count()):
            item = self.file_list.item(index)
            info = item.data(Qt.ItemDataRole.UserRole)
            if info['path'] == source:
                info['status'] = status
                item.setData(Qt.ItemDataRole.UserRole, info)
                self.update_item(item)
                break

    def on_completed(self, outputs, errors, cancelled):
        self.last_outputs, self.last_errors = outputs, errors
        prefix = '已取消' if cancelled else '导出完成'
        self.pending_summary = (prefix, outputs, errors, cancelled)

    def on_worker_finished(self):
        worker = self.worker
        self.worker = None
        worker.deleteLater()
        self.set_busy(False)
        if not self.pending_summary:
            return
        prefix, outputs, errors, cancelled = self.pending_summary
        self.pending_summary = None
        if not cancelled:
            self.progress_bar.setValue(100)
        total_size = sum(Path(path).stat().st_size for path in outputs if Path(path).exists()) / (1024 * 1024)
        self.status.setText(f'{prefix}  ·  成功 {len(outputs)} 个，失败 {len(errors)} 个  ·  共 {total_size:.2f} MB  ·  原文件已保留。')
        if errors:
            self.show_message(prefix, f'成功 {len(outputs)} 个，失败 {len(errors)} 个。\n\n' + '\n'.join(errors), warning=True)
        elif not cancelled:
            self.show_message('导出完成', f'已生成 {len(outputs)} 个文件。\n\n保存位置：\n{self.folder_edit.text()}')

    def cancel_export(self):
        if self.worker:
            self.worker.cancel_event.set()
            self.cancel_button.setEnabled(False)
            self.status.setText('正在取消；已完成的文件会保留。')

    def show_message(self, title, text, warning=False):
        if self.interactive:
            box = QMessageBox(self)
            box.setWindowTitle(title)
            box.setIcon(QMessageBox.Icon.Warning if warning else QMessageBox.Icon.Information)
            box.setText(text if len(text) < 1000 else text[:1000] + '\n…')
            if len(text) >= 1000:
                box.setDetailedText(text)
            box.addButton('确定', QMessageBox.ButtonRole.AcceptRole)
            box.exec()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not self.worker:
            event.acceptProposedAction()

    def dropEvent(self, event):
        if self.worker:
            return
        paths = []
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.is_dir():
                paths.extend(str(child) for child in sorted(path.iterdir()) if child.is_file() and child.suffix.lower() in SUPPORTED)
            elif path.is_file():
                paths.append(str(path))
        self.add_files(paths)
        event.acceptProposedAction()

    def closeEvent(self, event):
        if self.worker:
            self.cancel_export()
            self.show_message('正在结束导出', '已请求取消，请等待当前页面处理结束后再关闭窗口。')
            event.ignore()
            return
        self.save_timer.stop()
        self.preview_timer.stop()
        self.save_settings()
        self.canvas.show_message('')
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName('WatermarkStudio')
    app.setApplicationVersion(APP_VERSION)
    configure_appearance(app)
    configure_language(app)
    incoming = [arg for arg in sys.argv[1:] if Path(arg).is_file()]
    try:
        instance = SingleInstance(app)
        if not instance.acquire(incoming):
            return 0
    except Exception as exc:
        QMessageBox.critical(None, '无法启动水印工坊', str(exc))
        return 1
    smoke = '--smoke-test' in sys.argv
    smoke_context = None
    if smoke:
        import tempfile
        smoke_context = tempfile.TemporaryDirectory(prefix='watermark-exe-qa-')
        smoke_folder = Path(smoke_context.name)
        window = MainWindow(settings=QSettings(str(smoke_folder/'settings.ini'), QSettings.Format.IniFormat),
                            interactive=False, cache_dir=smoke_folder/'cache')
    else:
        window = MainWindow()
    instance.activation_requested.connect(window.activate_existing)
    window.show()
    if smoke:
        # Also tests the bundled EXE's rendering pipeline without dialogs.
        import tempfile
        from PIL import Image
        from engine import export_file
        def check_bundle():
            try:
                folder = smoke_folder/'samples'
                folder.mkdir()
                source = folder / 'sample.png'
                Image.new('RGB', (640, 480), 'white').save(source)
                window.add_files([str(source)])
                logo_source = folder/'transparent-logo.png'
                logo = Image.new('RGBA', (120, 80))
                from PIL import ImageDraw
                ImageDraw.Draw(logo).rounded_rectangle((10,10,110,70),radius=12,fill=(108,92,231,180))
                logo.save(logo_source)
                window.add_watermark_images([str(logo_source),str(logo_source)])
                window.text_enabled.setChecked(False)
                window.image_geometry_changed(window.image_marks[0].uid,.7,.3,.3)
                window.refresh_preview()
                assert len(window.canvas.overlays) == 2
                assert APP_VERSION in window.windowTitle()
                assert app.applicationVersion() == APP_VERSION
                output = export_file(source, folder / 'output', window.get_options())
                assert output.exists() and window.preview_image is not None
                import pymupdf as fitz
                pdf_source = folder / 'sample.pdf'
                with fitz.open() as doc:
                    for page_index in range(2):
                        page = doc.new_page(width=300, height=200)
                        page.insert_text((20, 30), f'Bundle rendering test {page_index+1}')
                        page.draw_rect(fitz.Rect(80,60,220,150),color=None,fill=(.4,.3,.8),fill_opacity=.6)
                    doc.save(pdf_source)
                picker_errors = []
                def choose_pdf_page():
                    picker = app.activeModalWidget()
                    try:
                        assert isinstance(picker,PdfWatermarkDialog)
                        picker.page_spin.setValue(2)
                        picker.grab().save(str(Path(sys.executable).parent/'smoke-pdf-page-picker.png'))
                    except Exception as exc:
                        picker_errors.append(str(exc))
                    finally:
                        if isinstance(picker,PdfWatermarkDialog):
                            picker.accept() if not picker_errors else picker.reject()
                QTimer.singleShot(150,choose_pdf_page)
                window.add_watermark_images([str(pdf_source)])
                assert not picker_errors and '第 2 页' in window.image_marks[0].name
                window.refresh_preview()
                pdf_output = export_file(pdf_source, folder / 'output', window.get_options())
                with fitz.open(pdf_output) as doc:
                    assert len(doc) == 2
                    for page in doc:
                        assert len(page.get_images()) == 1
                        assert page.get_images()[0][1] == 0 and not page.get_text().strip()
                window.grab().save(str(Path(sys.executable).parent / 'smoke-preview.png'))
                dialog = QColorDialog(QColor(window.color), window)
                dialog.setWindowTitle('选择水印文字颜色')
                dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog)
                dialog.show()
                app.processEvents()
                assert dialog.palette().color(QPalette.ColorRole.Window).lightness() > 200
                dialog.grab().save(str(Path(sys.executable).parent / 'smoke-color-dialog.png'))
                dialog.reject()
                menu = window.text_edit.createStandardContextMenu()
                menu_text = '\n'.join(action.text() for action in menu.actions())
                assert ('撤销' in menu_text or '撤消' in menu_text) and '粘贴' in menu_text and '全选' in menu_text
                assert 'Undo' not in menu_text and 'Paste' not in menu_text
                menu.show()
                app.processEvents()
                menu.grab().save(str(Path(sys.executable).parent / 'smoke-context-menu.png'))
                menu.close()
                (Path(sys.executable).parent / 'smoke-result.txt').write_text('PASS', encoding='utf-8')
                app.exit(0)
            except Exception:
                import traceback
                (Path(sys.executable).parent / 'smoke-result.txt').write_text(traceback.format_exc(), encoding='utf-8')
                app.exit(1)
        QTimer.singleShot(500, check_bundle)
    else:
        if incoming:
            QTimer.singleShot(100, lambda: window.add_files(incoming))
    try:
        return app.exec()
    finally:
        instance.close()
        window.canvas.show_message('')
        if smoke_context:
            window.save_timer.stop()
            window.preview_timer.stop()
            smoke_context.cleanup()


if __name__ == '__main__':
    sys.exit(main())
