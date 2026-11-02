"""Select exactly one page from a multipage PDF watermark source."""
from pathlib import Path
import pymupdf as fitz
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QPushButton, QDialogButtonBox


class PdfWatermarkDialog(QDialog):
    def __init__(self, source, parent=None):
        super().__init__(parent)
        self.source = str(source)
        self.setWindowTitle('选择 PDF 水印页面')
        self.resize(620, 570)
        with fitz.open(source) as document:
            if document.needs_pass:
                raise ValueError('此 PDF 需要密码，请先解密后再添加。')
            self.page_count = len(document)
        if not self.page_count:
            raise ValueError('此 PDF 没有可用页面。')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20,20,20,18)
        name = QLabel(Path(source).name)
        name.setWordWrap(True)
        layout.addWidget(name)
        navigation = QHBoxLayout()
        previous = QPushButton('上一页')
        following = QPushButton('下一页')
        navigation.addWidget(previous)
        navigation.addStretch()
        navigation.addWidget(QLabel('选择第'))
        self.page_spin = QSpinBox()
        self.page_spin.setRange(1,self.page_count)
        self.page_spin.setMinimumWidth(90)
        navigation.addWidget(self.page_spin)
        navigation.addWidget(QLabel(f'页 / 共 {self.page_count} 页'))
        navigation.addStretch()
        navigation.addWidget(following)
        layout.addLayout(navigation)
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(400,340)
        self.preview_label.setStyleSheet('background: #e9edf4; border-radius: 8px; padding: 10px;')
        layout.addWidget(self.preview_label,1)
        self.hint = QLabel('所选页面将作为一个水印添加，可移动、缩放、旋转并调整透明度。')
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        buttons = QDialogButtonBox()
        self.add_button = buttons.addButton('添加此页',QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton('取消',QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        previous.clicked.connect(lambda: self.page_spin.setValue(self.page_spin.value()-1))
        following.clicked.connect(lambda: self.page_spin.setValue(self.page_spin.value()+1))
        def update():
            previous.setEnabled(self.page_spin.value()>1)
            following.setEnabled(self.page_spin.value()<self.page_count)
            self.update_preview()
        self.page_spin.valueChanged.connect(update)
        update()

    @property
    def selected_page_index(self):
        return self.page_spin.value()-1

    def update_preview(self):
        try:
            with fitz.open(self.source) as document:
                page = document[self.selected_page_index]
                scale = min(1.5, 800/max(page.rect.width,page.rect.height))
                pix = page.get_pixmap(matrix=fitz.Matrix(scale,scale),colorspace=fitz.csRGB,alpha=False)
                image = QImage(pix.samples,pix.width,pix.height,pix.stride,QImage.Format.Format_RGB888).copy()
            self.page_pixmap = QPixmap.fromImage(image)
            self.fit_preview()
            self.add_button.setEnabled(True)
        except Exception as exc:
            self.page_pixmap = None
            self.preview_label.setText('无法预览此页：' + str(exc))
            self.add_button.setEnabled(False)

    def fit_preview(self):
        if getattr(self,'page_pixmap',None) is not None:
            self.preview_label.setPixmap(self.page_pixmap.scaled(
                max(1,self.preview_label.width()-24),max(1,self.preview_label.height()-24),
                Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.fit_preview()
