import sys, os
from PyQt5.QtWidgets import QApplication, QLabel
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt

SCALE = 2.0  # Change size: 1.0 = original, 2.0 = double, etc.

script_dir = os.path.dirname(os.path.abspath(__file__))
img_path = os.path.join(script_dir, "pikachu.png")

app = QApplication(sys.argv)

label = QLabel()
label.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
label.setAttribute(Qt.WA_TranslucentBackground)  # True per-pixel transparency, no touching pixels

pixmap = QPixmap(img_path)
if SCALE != 1.0:
    pixmap = pixmap.scaled(
        int(pixmap.width() * SCALE),
        int(pixmap.height() * SCALE),
        Qt.KeepAspectRatio,
        Qt.SmoothTransformation
    )

label.setPixmap(pixmap)
label.resize(pixmap.size())

# Start top-right corner
screen = app.primaryScreen().geometry()
label.move(screen.width() - pixmap.width() - 40, 40)
label.show()

# Dragging
_drag = {}
def mousePressEvent(e):
    if e.button() == Qt.LeftButton:
        _drag['pos'] = e.globalPos() - label.frameGeometry().topLeft()
def mouseMoveEvent(e):
    if e.buttons() == Qt.LeftButton and 'pos' in _drag:
        label.move(e.globalPos() - _drag['pos'])
def contextMenuEvent(e):
    from PyQt5.QtWidgets import QMenu
    menu = QMenu()
    menu.addAction("Close  ✕", app.quit)
    menu.exec_(e.globalPos())

label.mousePressEvent = mousePressEvent
label.mouseMoveEvent = mouseMoveEvent
label.contextMenuEvent = contextMenuEvent

sys.exit(app.exec_())
