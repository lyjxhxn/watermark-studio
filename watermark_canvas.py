"""Interactive image overlays over a cached raster page preview."""
from dataclasses import replace

from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsObject, QGraphicsItem
from shiboken6 import isValid

from image_watermarks import image_geometry


class ResizeHandle:
    """Logical corner; the view draws and hit-tests handles in its foreground."""
    def __init__(self, owner, corner):
        self.owner, self.corner = owner, corner

    def scenePos(self):
        points = [QPointF(),QPointF(self.owner.width,0),QPointF(self.owner.width,self.owner.height),QPointF(0,self.owner.height)]
        return self.owner.mapToScene(points[self.corner])


class ImageOverlay(QGraphicsObject):
    def __init__(self, canvas, model, image):
        super().__init__()
        self.canvas, self.model, self.image = canvas, model, image
        self.editable = True
        self.width = self.height = 1
        self.drag_offset = None
        self.handles = [ResizeHandle(self, index) for index in range(4)]
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.sync(model, image)

    def boundingRect(self):
        return QRectF(0, 0, self.width, self.height)

    def shape(self):
        shape = QPainterPath()
        shape.addRect(self.boundingRect())
        return shape

    def paint(self, painter, option, widget=None):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setOpacity(self.model.opacity / 100)
        painter.drawImage(self.boundingRect(), self.image)
        painter.restore()

    def set_rect(self, rect):
        self.prepareGeometryChange()
        self.width, self.height = rect.width(), rect.height()
        self.setPos(rect.topLeft())
        self.update()
        self.canvas.viewport().update()

    def sync(self, model, image):
        self.model, self.image = model, image
        page = self.canvas.sceneRect()
        self.set_rect(image_geometry(model, page.width(), page.height(), image))
        self.update_handles()

    def set_editable(self, editable):
        self.editable = editable
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton if editable else Qt.MouseButton.NoButton)
        self.setCursor(Qt.CursorShape.OpenHandCursor if editable else Qt.CursorShape.ArrowCursor)
        self.update_handles()

    def update_handles(self):
        if isValid(self.canvas):
            self.canvas.viewport().update()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.update_handles()
        return super().itemChange(change, value)

    def notify_geometry(self):
        self.canvas.viewport().update()
        page = self.canvas.sceneRect()
        self.model = replace(self.model,
            center_x=(self.x() + self.width / 2) / page.width(),
            center_y=(self.y() + self.height / 2) / page.height(),
            width_ratio=self.width / page.width())
        self.canvas.geometry_changed.emit(self.model.uid, self.model.center_x, self.model.center_y, self.model.width_ratio)

    def mousePressEvent(self, event):
        if not self.editable or event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        self.canvas.scene().clearSelection()
        self.setSelected(True)
        self.drag_offset = event.scenePos() - self.pos()
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        event.accept()

    def mouseMoveEvent(self, event):
        if self.editable and self.drag_offset is not None:
            target = event.scenePos() - self.drag_offset
            page = self.canvas.sceneRect()
            self.setPos(min(max(target.x(), 0), max(0, page.width() - self.width)),
                        min(max(target.y(), 0), max(0, page.height() - self.height)))
            self.notify_geometry()
            event.accept()

    def mouseReleaseEvent(self, event):
        self.drag_offset = None
        self.setCursor(Qt.CursorShape.OpenHandCursor if self.editable else Qt.CursorShape.ArrowCursor)
        event.accept()

    def begin_resize(self, corner):
        rect = self.mapRectToScene(self.boundingRect())
        points = [rect.topLeft(), rect.topRight(), rect.bottomRight(), rect.bottomLeft()]
        self.anchor = points[(corner + 2) % 4]
        self.resize_signs = [(-1, -1), (1, -1), (1, 1), (-1, 1)][corner]

    def resize_to(self, point):
        page = self.canvas.sceneRect()
        sx, sy = self.resize_signs
        aspect = self.image.height() / self.image.width()
        vector = point - self.anchor
        projected_width = (vector.x() * sx + vector.y() * sy * aspect) / (1 + aspect * aspect)
        max_width = min(page.width() - self.anchor.x() if sx > 0 else self.anchor.x(),
                        (page.height() - self.anchor.y() if sy > 0 else self.anchor.y()) / aspect)
        minimum = min(page.width() * 0.01, max_width)
        width = max(minimum, min(projected_width, max_width))
        height = width * aspect
        self.set_rect(QRectF(self.anchor.x() + min(0, sx * width), self.anchor.y() + min(0, sy * height), width, height))
        self.notify_geometry()


class WatermarkCanvas(QGraphicsView):
    geometry_changed = Signal(str, float, float, float)
    image_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setStyleSheet('background: transparent; border: 0;')
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.scene().selectionChanged.connect(self.selection_changed)
        self.setMouseTracking(True)
        self.resizing_item = None
        self.background_item = None
        self.overlays = {}
        self.editable = True
        self.page_allowed = True
        self.message = '拖入 PDF 或图片\n即可预览水印效果'

    def show_message(self, message):
        self.scene().blockSignals(True)
        self.resizing_item = None
        self.scene().clear()
        self.scene().blockSignals(False)
        self.background_item = None
        self.overlays = {}
        self.message = message
        self.viewport().update()

    def set_page(self, image, marks, assets, allowed=True, selected_uid=''):
        self.page_allowed = allowed
        self.message = ''
        if self.background_item is None:
            self.background_item = self.scene().addPixmap(QPixmap.fromImage(image))
            self.background_item.setZValue(-1)
        else:
            self.background_item.setPixmap(QPixmap.fromImage(image))
        self.setSceneRect(QRectF(0, 0, image.width(), image.height()))
        self.update_layers(marks, assets, selected_uid)
        self.fit_page()

    def update_layers(self, marks, assets, selected_uid=''):
        if self.background_item is None:
            return
        active = {mark.uid for mark in marks if self.page_allowed and mark.enabled and mark.uid in assets}
        self.scene().blockSignals(True)
        for uid in list(self.overlays):
            if uid not in active:
                item = self.overlays.pop(uid)
                if self.resizing_item is item:
                    self.resizing_item = None
                self.scene().removeItem(item)
                item.deleteLater()
        for index, mark in enumerate(marks):
            if mark.uid not in active:
                continue
            item = self.overlays.get(mark.uid)
            if item is None:
                item = ImageOverlay(self, mark, assets[mark.uid])
                self.scene().addItem(item)
                self.overlays[mark.uid] = item
            else:
                item.sync(mark, assets[mark.uid])
            item.setZValue(len(marks) - index)
            item.set_editable(self.editable)
            item.setSelected(mark.uid == selected_uid)
        self.scene().blockSignals(False)
        self.viewport().update()

    def select_image(self, uid):
        self.scene().blockSignals(True)
        for key, item in self.overlays.items():
            item.setSelected(key == uid)
        self.scene().blockSignals(False)

    def selection_changed(self):
        selected = [item for item in self.scene().selectedItems() if isinstance(item, ImageOverlay)]
        self.image_selected.emit(selected[0].model.uid if selected else '')

    def set_editable(self, editable):
        self.editable = editable
        if not editable:
            self.resizing_item = None
        for item in self.overlays.values():
            item.set_editable(editable)

    def selected_overlay(self):
        return next((item for item in self.overlays.values() if item.isSelected()),None)

    def handle_at(self, position):
        item = self.selected_overlay() if self.editable else None
        if item is not None:
            for index, handle in enumerate(item.handles):
                center = self.mapFromScene(handle.scenePos())
                if abs(position.x()-center.x()) <= 7 and abs(position.y()-center.y()) <= 7:
                    return item,index
        return None,None

    def mousePressEvent(self,event):
        item,corner = self.handle_at(event.position().toPoint())
        if item is not None and event.button() == Qt.MouseButton.LeftButton:
            self.resizing_item = item
            item.begin_resize(corner)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if self.resizing_item is not None and self.editable:
            self.resizing_item.resize_to(self.mapToScene(event.position().toPoint()))
            event.accept()
            return
        item,corner = self.handle_at(event.position().toPoint())
        if item is not None:
            self.viewport().setCursor(Qt.CursorShape.SizeFDiagCursor if corner in (0,2) else Qt.CursorShape.SizeBDiagCursor)
        else:
            self.viewport().unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        if self.resizing_item is not None:
            self.resizing_item = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def drawForeground(self,painter,rect):
        super().drawForeground(painter,rect)
        item = self.selected_overlay() if self.editable else None
        if item is None:
            return
        painter.save()
        pen = QPen(QColor('#7967df'),1.2)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(item.mapRectToScene(item.boundingRect()))
        painter.setBrush(QColor('white'))
        size = 8/max(self.transform().m11(),.001)
        for handle in item.handles:
            point = handle.scenePos()
            painter.drawRect(QRectF(point.x()-size/2,point.y()-size/2,size,size))
        painter.restore()

    def fit_page(self):
        if self.background_item is not None and self.viewport().width() > 0 and self.viewport().height() > 0:
            page = self.sceneRect()
            factor = min(self.viewport().width()/page.width(), self.viewport().height()/page.height())
            margin = 8/max(factor,0.001)
            self.fitInView(page.adjusted(-margin,-margin,margin,margin), Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_page()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.message:
            painter = QPainter(self.viewport())
            painter.setPen(QColor('#8b95aa'))
            painter.drawText(self.viewport().rect(), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.message)
            painter.end()
