"""Flow layout — wraps child widgets onto new rows when width runs out.

Vendored from the Qt for Python "Flow Layout" example (BSD-3-Clause):
https://doc.qt.io/qtforpython-6/examples/example_widgets_layouts_flowlayout.html

Why it exists here (v3.9 UI hardening, Batch UI-1): a QHBoxLayout's minimum
width is the SUM of its children's minimums, so the 9-button toolbar row
forced ~1242px and the 8-slot combo row ~1338px into the window's
minimumSizeHint (UI recon 2026-06-10, B2/B3). A FlowLayout's minimumSize()
is the size of the LARGEST SINGLE child — rows wrap instead of clipping.

Target location in the repo: core/flow_layout.py
"""

from PySide6.QtCore import QMargins, QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QSizePolicy, QStyle


class FlowLayout(QLayout):
    """A layout that arranges children left-to-right, wrapping to new rows.

    Supports heightForWidth so parent QVBoxLayouts grow the row's frame
    vertically when a wrap happens instead of clipping horizontally.
    """

    def __init__(self, parent=None, margin=0, h_spacing=-1, v_spacing=-1):
        super().__init__(parent)
        self._items = []
        self._h_space = h_spacing
        self._v_space = v_spacing
        self.setContentsMargins(QMargins(margin, margin, margin, margin))

    def __del__(self):
        while self.count():
            self.takeAt(0)

    # ---- QLayout mandatory interface -------------------------------------

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    # ---- sizing ------------------------------------------------------------

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        # The whole point: minimum = largest single child, not the sum.
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    # ---- spacing helpers (mirrors the official example) ---------------------

    def horizontalSpacing(self):
        if self._h_space >= 0:
            return self._h_space
        return self._smart_spacing(QStyle.PM_LayoutHorizontalSpacing)

    def verticalSpacing(self):
        if self._v_space >= 0:
            return self._v_space
        return self._smart_spacing(QStyle.PM_LayoutVerticalSpacing)

    def _smart_spacing(self, pixel_metric):
        parent = self.parent()
        if parent is None:
            return -1
        if parent.isWidgetType():
            return parent.style().pixelMetric(pixel_metric, None, parent)
        return parent.spacing()

    # ---- the layout pass -----------------------------------------------------

    def _do_layout(self, rect, test_only):
        m = self.contentsMargins()
        effective = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x = effective.x()
        y = effective.y()
        line_height = 0

        for item in self._items:
            widget = item.widget()
            space_x = self.horizontalSpacing()
            space_y = self.verticalSpacing()
            if widget is not None:
                if space_x == -1:
                    space_x = widget.style().layoutSpacing(
                        QSizePolicy.PushButton, QSizePolicy.PushButton,
                        Qt.Horizontal,
                    )
                if space_y == -1:
                    space_y = widget.style().layoutSpacing(
                        QSizePolicy.PushButton, QSizePolicy.PushButton,
                        Qt.Vertical,
                    )

            hint = item.sizeHint()
            next_x = x + hint.width() + space_x
            if next_x - space_x > effective.right() and line_height > 0:
                # Wrap to the next row.
                x = effective.x()
                y = y + line_height + space_y
                next_x = x + hint.width() + space_x
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))

            x = next_x
            line_height = max(line_height, hint.height())

        return y + line_height - rect.y() + m.bottom()
