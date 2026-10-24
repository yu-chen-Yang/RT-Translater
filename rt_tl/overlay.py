"""Always-on-top, click-through-ish transparent subtitle overlay.

Shows two rows: the last *committed* (finalized, no longer changing) utterance
dimmed above, and the *live* in-progress utterance below it, which keeps
getting replaced/corrected as more audio comes in until it's committed too.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QLabel, QMenu, QSystemTrayIcon, QVBoxLayout, QWidget


def _make_tray_icon() -> QIcon:
    """Draws a small round icon at runtime instead of shipping an image asset."""
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#2d7dfa"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(2, 2, size - 4, size - 4)
    painter.setPen(QColor("white"))
    font = QFont("Microsoft YaHei UI", 26, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "译")
    painter.end()
    return QIcon(pixmap)


class SubtitleOverlay(QWidget):
    live_updated = pyqtSignal(str, str)    # (original_text, translated_text)
    committed = pyqtSignal(str, str)       # (original_text, translated_text)
    live_cleared = pyqtSignal()
    all_cleared = pyqtSignal()

    def __init__(
        self,
        max_lines: int = 1,  # unused, kept for config/CLI backward compatibility
        font_size: int = 20,
        opacity: float = 0.85,
        width: int = 900,
        bottom_margin: int = 80,
    ):
        super().__init__()
        self._bottom_margin = bottom_margin
        self._committed_html: str | None = None
        self._live_html: str | None = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput  # click/hover passes through to the window below
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setWindowOpacity(opacity)

        self._margin_h = 32  # left+right contents margins below
        self._margin_v = 20  # top+bottom contents margins below
        self._width = width

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        self._label = QLabel("")
        self._label.setWordWrap(True)
        self._label.setFixedWidth(width - self._margin_h)
        self._label.setFont(QFont("Microsoft YaHei UI", font_size))
        self._label.setStyleSheet(
            "color: white; background-color: rgba(0, 0, 0, 160); border-radius: 8px; padding: 6px;"
        )
        self._label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self._label)

        self.resize(width, 160)
        self._reposition()

        self.live_updated.connect(self._on_live_updated)
        self.committed.connect(self._on_committed)
        self.live_cleared.connect(self._on_live_cleared)
        self.all_cleared.connect(self._on_all_cleared)

        # Set by run_overlay_app() so main.py can add more actions (e.g. a
        # translation-direction toggle) to the tray menu after the pipeline exists.
        self.tray: QSystemTrayIcon | None = None
        self.tray_menu: QMenu | None = None

    def _reposition(self) -> None:
        """Keeps the box horizontally centered and anchored to a fixed distance
        from the bottom of the screen, so it grows/shrinks upward as text changes."""
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.x() + (screen.width() - self.width()) // 2
        y = screen.y() + screen.height() - self._bottom_margin - self.height()
        self.move(x, y)

    @staticmethod
    def _format(original: str, translated: str, dim: bool) -> str:
        return f"<span style='color:#cccccc;'>{original}</span><br><b>{translated}</b>"

    def _render(self) -> None:
        parts = [p for p in (self._committed_html, self._live_html) if p]
        self._label.setText("<br><br>".join(parts))

        # Compute the exact height the wrapped rich text needs at the fixed label
        # width, then resize the top-level window to match - adjustSize() alone is
        # unreliable on frameless/always-on-top windows.
        self._label.adjustSize()
        needed_height = self._label.heightForWidth(self._label.width()) + self._margin_v
        self.resize(self._width, max(needed_height, 60))
        self._reposition()

    def _on_live_updated(self, original: str, translated: str) -> None:
        self._live_html = self._format(original, translated, dim=False)
        self._render()

    def _on_committed(self, original: str, translated: str) -> None:
        self._committed_html = self._format(original, translated, dim=True)
        self._live_html = None
        self._render()

    def _on_live_cleared(self) -> None:
        self._live_html = None
        self._render()

    def _on_all_cleared(self) -> None:
        self._committed_html = None
        self._live_html = None
        self._render()

    def push_live(self, original: str, translated: str) -> None:
        """Thread-safe: update the in-progress (still-correctable) line."""
        self.live_updated.emit(original, translated)

    def commit_live(self, original: str, translated: str) -> None:
        """Thread-safe: finalize the current utterance into the stable history line."""
        self.committed.emit(original, translated)

    def clear_live(self) -> None:
        """Thread-safe: drop the in-progress line without committing anything (e.g. it was silence)."""
        self.live_cleared.emit()

    def clear_all(self) -> None:
        """Thread-safe: drop both lines (e.g. right after switching translation direction)."""
        self.all_cleared.emit()


def run_overlay_app(overlay_ready_callback=None, **overlay_kwargs):
    """Creates the QApplication + overlay + a system tray icon (for quitting
    without touching Task Manager), invokes the callback with the overlay
    instance once it's shown, then blocks running the Qt event loop."""
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)  # the overlay has no titlebar/close button; only the tray quits it

    overlay = SubtitleOverlay(**overlay_kwargs)
    overlay.show()

    tray = QSystemTrayIcon(_make_tray_icon(), app)
    tray.setToolTip("RT-TL Live Subtitle Translator")
    menu = QMenu()
    overlay.tray = tray
    overlay.tray_menu = menu

    if overlay_ready_callback:
        overlay_ready_callback(overlay)

    menu.addSeparator()
    quit_action = menu.addAction("Quit")
    quit_action.triggered.connect(app.quit)
    tray.setContextMenu(menu)
    tray.show()

    app.exec()
