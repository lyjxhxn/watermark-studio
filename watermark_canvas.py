"""Interactive image overlays over a cached raster page preview."""
from dataclasses import replace
import math
import weakref

from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsObject, QGraphicsItem
from shiboken6 import isValid

from image_watermarks import image_geometry, rotated_size


class ResizeHandle:
    """Logical corner; the view draws and hit-tests handles in its foreground."""
    def __init__(self, owner, corner):
        self._owner_ref, self.corner = weakref.ref(owner), corner

    @property
    def owner(self):
        return self._owner_ref()

    def scenePos(self):
        points = [QPointF(),QPointF(self.owner.width,0),QPointF(self.owner.width,self.owner.height),QPointF(0,self.owner.height)]
        return self.owner.mapToScene(points[self.corner])


class ImageOverlay(QGraphicsObject):
    def __init__(self, canvas, model, image):
        super().__init__()
        self._canvas_ref = weakref.ref(canvas)
        self.model, self.image = model, image
        self.editable = True
        self.width = self.height = 1
        self.drag_offset = None
        self.handles = [ResizeHandle(self, index) for index in range(4)]
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.sync(model, image)

    @property
    def canvas(self):
        return self._canvas_ref()

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
        self.setTransformOriginPoint(self.width/2,self.height/2)
        self.setRotation(self.model.rotation)
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
        if self.canvas is not None and isValid(self.canvas) and isValid(self.canvas.viewport()):
            self.canvas.viewport().update()

    def notify_geometry(self):
        self.canvas.viewport().update()
        page = self.canvas.sceneRect()
        self.model = replace(self.model,
            center_x=min(1,max(0,(self.x() + self.width / 2) / page.width())),
            center_y=min(1,max(0,(self.y() + self.height / 2) / page.height())),
            width_ratio=min(1,max(1e-8,self.width / page.width())), rotation=self.rotation())
        self.canvas.geometry_changed.emit(self.model.uid, self.model.center_x, self.model.center_y, self.model.width_ratio, self.model.rotation)

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
            bound_width,bound_height = rotated_size(self.width,self.height,self.model.rotation)
            center_x=min(max(target.x()+self.width/2,bound_width/2),page.width()-bound_width/2)
            center_y=min(max(target.y()+self.height/2,bound_height/2),page.height()-bound_height/2)
            self.setPos(center_x-self.width/2,center_y-self.height/2)
            self.notify_geometry()
            event.accept()

    def mouseReleaseEvent(self, event):
        self.drag_offset = None
        self.setCursor(Qt.CursorShape.OpenHandCursor if self.editable else Qt.CursorShape.ArrowCursor)
        event.accept()

    def begin_resize(self, corner):
        points = [handle.scenePos() for handle in self.handles]
        self.anchor = points[(corner + 2) % 4]
        self.resize_signs = [(-1, -1), (1, -1), (1, 1), (-1, 1)][corner]
        angle = math.radians(self.model.rotation)
        self.resize_u = QPointF(math.cos(angle),math.sin(angle))
        self.resize_v = QPointF(-math.sin(angle),math.cos(angle))

    def resize_to(self, point):
        page = self.canvas.sceneRect()
        sx, sy = self.resize_signs
        aspect = self.image.height() / self.image.width()
        vector = point - self.anchor
        u,v = self.resize_u,self.resize_v
        local_x = QPointF.dotProduct(vector,u)
        local_y = QPointF.dotProduct(vector,v)
        projected_width = (local_x*sx + local_y*sy*aspect) / (1 + aspect*aspect)
        max_width = float('inf')
        for direction in [u*sx,v*(sy*aspect),u*sx+v*(sy*aspect)]:
            for coordinate,delta,limit in [(self.anchor.x(),direction.x(),page.width()),
                                           (self.anchor.y(),direction.y(),page.height())]:
                if delta > 1e-10:
                    max_width=min(max_width,(limit-coordinate)/delta)
                elif delta < -1e-10:
                    max_width=min(max_width,-coordinate/delta)
        max_width=min(page.width(),max(0.0001,max_width))
        minimum = min(page.width() * 0.01, max_width)
        width = max(minimum, min(projected_width, max_width))
        height = width * aspect
        center=self.anchor+(u*(sx*width)+v*(sy*height))/2
        self.set_rect(QRectF(center.x()-width/2,center.y()-height/2,width,height))
        self.notify_geometry()

    def begin_rotate(self,point):
        self.rotation_origin=self.mapToScene(QPointF(self.width/2,self.height/2))
        vector=point-self.rotation_origin
        self.rotation_pointer_start=math.degrees(math.atan2(vector.y(),vector.x()))
        # Keep the original requested size while dragging through angles that
        # require fitting, so a full turn cannot progressively shrink the image.
        page=self.canvas.sceneRect()
        self.rotation_model_start=replace(self.model,
            center_x=self.rotation_origin.x()/page.width(),center_y=self.rotation_origin.y()/page.height(),
            width_ratio=self.width/page.width())

    def rotate_to(self,point,snap=False):
        vector=point-self.rotation_origin
        if math.hypot(vector.x(),vector.y()) < 1e-8:
            return
        pointer_angle=math.degrees(math.atan2(vector.y(),vector.x()))
        angle=self.rotation_model_start.rotation+pointer_angle-self.rotation_pointer_start
        if snap:
            angle=round(angle/15)*15
        angle=(angle+180)%360-180
        self.sync(replace(self.rotation_model_start,rotation=angle),self.image)
        self.notify_geometry()


class WatermarkCanvas(QGraphicsView):
    geometry_changed = Signal(str, float, float, float, float)
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
        self.rotating_item = None
        self.background_item = None
        self.overlays = {}
        self.editable = True
        self.page_allowed = True
        self.message = '拖入 PDF 或图片\n即可预览水印效果'

    def show_message(self, message):
        self.scene().blockSignals(True)
        self.resizing_item = None
        self.rotating_item = None
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
                if self.rotating_item is item:
                    self.rotating_item = None
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
        self.viewport().update()

    def selection_changed(self):
        self.viewport().update()
        selected = [item for item in self.scene().selectedItems() if isinstance(item, ImageOverlay)]
        self.image_selected.emit(selected[0].model.uid if selected else '')

    def set_editable(self, editable):
        self.editable = editable
        if not editable:
            self.resizing_item = None
            self.rotating_item = None
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

    def rotation_handle_points(self,item):
        top=item.mapToScene(QPointF(item.width/2,0))
        center=item.mapToScene(QPointF(item.width/2,item.height/2))
        outward=top-center
        length=max(math.hypot(outward.x(),outward.y()),1e-8)
        point=top+outward*(28/max(self.transform().m11(),.001)/length)
        screen=self.mapFromScene(point)
        x=min(max(screen.x(),10),max(10,self.viewport().width()-10))
        y=min(max(screen.y(),10),max(10,self.viewport().height()-10))
        return top,self.mapToScene(x,y)

    def rotation_handle_at(self,position):
        item=self.selected_overlay() if self.editable else None
        if item is not None:
            _,point=self.rotation_handle_points(item)
            screen=self.mapFromScene(point)
            if math.hypot(position.x()-screen.x(),position.y()-screen.y()) <= 10:
                return item
        return None

    def mousePressEvent(self,event):
        item=self.rotation_handle_at(event.position().toPoint())
        if item is not None and event.button() == Qt.MouseButton.LeftButton:
            self.rotating_item=item
            item.begin_rotate(self.mapToScene(event.position().toPoint()))
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        item,corner = self.handle_at(event.position().toPoint())
        if item is not None and event.button() == Qt.MouseButton.LeftButton:
            self.resizing_item = item
            item.begin_resize(corner)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if self.rotating_item is not None and self.editable:
            self.rotating_item.rotate_to(self.mapToScene(event.position().toPoint()),
                                         bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier))
            event.accept()
            return
        if self.resizing_item is not None and self.editable:
            self.resizing_item.resize_to(self.mapToScene(event.position().toPoint()))
            event.accept()
            return
        rotation_item=self.rotation_handle_at(event.position().toPoint())
        if rotation_item is not None:
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            self.setToolTip('拖动圆形手柄旋转；按住 Shift 每 15° 吸附。')
            event.accept()
            return
        self.setToolTip('')
        item,corner = self.handle_at(event.position().toPoint())
        if item is not None:
            diagonal=(item.model.rotation+(45 if corner in (0,2) else -45))%180
            cursors=[Qt.CursorShape.SizeHorCursor,Qt.CursorShape.SizeFDiagCursor,Qt.CursorShape.SizeVerCursor,Qt.CursorShape.SizeBDiagCursor]
            self.viewport().setCursor(cursors[round(diagonal/45)%4])
        else:
            self.viewport().unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        if self.rotating_item is not None:
            self.rotating_item=None
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
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
        painter.drawPolygon(QPolygonF([handle.scenePos() for handle in item.handles]))
        painter.setBrush(QColor('white'))
        size = 8/max(self.transform().m11(),.001)
        for handle in item.handles:
            point = handle.scenePos()
            painter.drawRect(QRectF(point.x()-size/2,point.y()-size/2,size,size))
        top,point=self.rotation_handle_points(item)
        painter.drawLine(top,point)
        radius=7/max(self.transform().m11(),.001)
        painter.setBrush(QColor('#7967df'))
        painter.drawEllipse(point,radius,radius)
        painter.setPen(QPen(QColor('white'),1.2/max(self.transform().m11(),.001)))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        arc_radius=radius*.55
        painter.drawArc(QRectF(point.x()-arc_radius,point.y()-arc_radius,arc_radius*2,arc_radius*2),35*16,285*16)
        painter.drawLine(point+QPointF(arc_radius*.8,-arc_radius*.6),point+QPointF(arc_radius*.8,-arc_radius*1.2))
        painter.drawLine(point+QPointF(arc_radius*.8,-arc_radius*.6),point+QPointF(arc_radius*.2,-arc_radius*.6))
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
