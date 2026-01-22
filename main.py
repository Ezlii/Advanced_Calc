# main.py
import sys
import math
from dataclasses import dataclass

from PySide6.QtCore import Qt, QSize, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QKeySequence, QPainter, QPen, QPixmap, QIcon, QColor, QAction
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QToolButton, QTabBar, QStackedWidget, QLineEdit, QLabel,
    QGridLayout, QPushButton, QFrame, QSizePolicy,
    QDialog, QDialogButtonBox, QColorDialog, QMenu
)



def make_gray_close_icon(size: int = 12) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(Qt.lightGray)
    pen.setWidth(2)
    p.setPen(pen)
    margin = 2
    p.drawLine(margin, margin, size - margin, size - margin)
    p.drawLine(size - margin, margin, margin, size - margin)
    p.end()
    return QIcon(pm)


@dataclass
class Theme:
    window_bg: str = "#101318"
    panel_bg: str = "#171a20"
    topbar_bg: str = "#1f232a"
    control_bg: str = "#2a2f38"
    control_hover: str = "#343a46"
    border: str = "#3a4250"
    text: str = "#d7dde7"
    text_strong: str = "#ffffff"


class SettingsDialog(QDialog):
    def __init__(self, theme: Theme, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Einstellungen")
        self.setModal(True)
        self.theme = theme

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        self.lbl_info = QLabel("Farben anpassen:")
        root.addWidget(self.lbl_info)

        row = QHBoxLayout()
        self.btn_bg = QPushButton("Fenster-Hintergrund…")
        self.btn_fg = QPushButton("Schriftfarbe…")
        row.addWidget(self.btn_bg)
        row.addWidget(self.btn_fg)
        root.addLayout(row)

        self.btn_bg.clicked.connect(self.pick_bg)
        self.btn_fg.clicked.connect(self.pick_fg)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def pick_bg(self):
        col = QColorDialog.getColor(QColor(self.theme.window_bg), self, "Fenster-Hintergrund wählen")
        if col.isValid():
            self.theme.window_bg = col.name()
            self._notify()

    def pick_fg(self):
        col = QColorDialog.getColor(QColor(self.theme.text), self, "Schriftfarbe wählen")
        if col.isValid():
            self.theme.text = col.name()
            self._notify()

    def _notify(self):
        if isinstance(self.parent(), MainWindow):
            self.parent().apply_theme()


class DrawerMenu(QFrame):
    def __init__(self, on_select_mode, parent=None):
        super().__init__(parent)
        self.on_select_mode = on_select_mode
        self.setObjectName("DrawerMenu")
        self.setFixedWidth(260)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        title = QLabel("Menü")
        title.setObjectName("DrawerTitle")
        lay.addWidget(title)

        def mk_item(label: str):
            btn = QPushButton(label)
            btn.setObjectName("DrawerItem")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda: self.on_select_mode(label))
            return btn

        lay.addWidget(mk_item("Standard"))
        lay.addWidget(mk_item("Scientific"))
        lay.addWidget(mk_item("Plot"))
        lay.addStretch(1)

        footer = QLabel("Advanced Calculator")
        footer.setObjectName("DrawerFooter")
        lay.addWidget(footer)


class CalculatorPage(QWidget):
    """
    Eingabe + Output + Button-Grid.
    ESC löscht Eingabe (wenn dieser Tab aktiv ist).
    Buttons wachsen, bleiben quadratisch, berühren sich (0 spacing).
    """
    def __init__(self, title="Calculator"):
        super().__init__()
        self.title = title
        self.ans_value = None

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # Display
        self.input = QLineEdit()
        self.input.setPlaceholderText("Berechnung eingeben… (z.B. 2*(3+4))")
        self.input.setClearButtonEnabled(True)
        self.input.returnPressed.connect(self.on_equals)

        self.preview = QLabel("Output/Preview erscheint hier…")
        self.preview.setWordWrap(True)
        self.preview.setTextInteractionFlags(Qt.TextSelectableByMouse)

        display_frame = QFrame()
        display_frame.setObjectName("DisplayFrame")
        display_layout = QVBoxLayout(display_frame)
        display_layout.setContentsMargins(12, 12, 12, 12)
        display_layout.setSpacing(8)
        display_layout.addWidget(self.input)
        display_layout.addWidget(self.preview)
        root.addWidget(display_frame, 0)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        root.addWidget(line)

        # Buttons
        self.btn_area = QWidget()
        self.btn_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.grid = QGridLayout(self.btn_area)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(0)
        self.grid.setVerticalSpacing(0)

        self.buttons = []

        # --------- Erweiterter Button-Plan (mehr Buttons, kleiner) ----------
        # 6x6 = 36 Buttons
        layout_labels = [
            ["C",   "⌫", "(",   ")",   "a/b", "÷"],
            ["7",   "8", "9",   "×",   "xʸ",  "10^x"],
            ["4",   "5", "6",   "−",   "√",   "x√y"],
            ["1",   "2", "3",   "+",   "sin", "cos"],
            ["0",   ".", "±",   "=",   "tan", "Ans"],
            ["Konst","π", "e",  "ln",  "log", "!"],
        ]
        self.rows = len(layout_labels)
        self.cols = len(layout_labels[0])

        def insert_text(t: str):
            mapping = {
                "÷": "/",
                "×": "*",
                "−": "-",
                "xʸ": "**",
                "π": "pi",
                "e": "e",
                "a/b": "/",
            }
            self.input.insert(mapping.get(t, t))

        # Konstanten-Menü
        self.const_menu = QMenu(self)
        const_items = [
            ("π (pi)", "pi"),
            ("e", "e"),
            ("τ (tau)", "tau"),
            ("φ (phi)", "phi"),
            ("c (Licht)", "c"),
            ("g (Erde)", "g"),
        ]
        for title, token in const_items:
            act = QAction(title, self)
            act.triggered.connect(lambda _=False, tok=token: self.input.insert(tok))
            self.const_menu.addAction(act)

        def make_btn(label: str) -> QPushButton:
            btn = QPushButton(label)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            return btn

        for r, row in enumerate(layout_labels):
            for c, label in enumerate(row):
                btn = make_btn(label)

                if label == "C":
                    btn.clicked.connect(self.on_clear)
                elif label == "⌫":
                    btn.clicked.connect(self.on_backspace)
                elif label == "=":
                    btn.clicked.connect(self.on_equals)
                    btn.setDefault(True)
                elif label == "√":
                    btn.clicked.connect(lambda _=False: self.input.insert("sqrt("))
                elif label == "x√y":
                    # x-te Wurzel: root(x, y) = y**(1/x)
                    btn.clicked.connect(lambda _=False: self.input.insert("root("))
                elif label == "10^x":
                    btn.clicked.connect(lambda _=False: self.input.insert("10**("))
                elif label == "sin":
                    btn.clicked.connect(lambda _=False: self.input.insert("sin("))
                elif label == "cos":
                    btn.clicked.connect(lambda _=False: self.input.insert("cos("))
                elif label == "tan":
                    btn.clicked.connect(lambda _=False: self.input.insert("tan("))
                elif label == "ln":
                    btn.clicked.connect(lambda _=False: self.input.insert("ln("))
                elif label == "log":
                    btn.clicked.connect(lambda _=False: self.input.insert("log10("))
                elif label == "!":
                    # factorial(n)
                    btn.clicked.connect(lambda _=False: self.input.insert("fact("))
                elif label == "±":
                    btn.clicked.connect(self.on_toggle_sign)
                elif label == "Ans":
                    btn.clicked.connect(lambda _=False: self.input.insert("Ans"))
                elif label == "Konst":
                    btn.clicked.connect(self.open_constants_menu)
                else:
                    btn.clicked.connect(lambda _=False, t=label: insert_text(t))

                self.grid.addWidget(btn, r, c)
                self.buttons.append(btn)

        for r in range(self.rows):
            self.grid.setRowStretch(r, 1)
        for c in range(self.cols):
            self.grid.setColumnStretch(c, 1)

        root.addWidget(self.btn_area, 1)

    def open_constants_menu(self):
        # Menü direkt am Button anzeigen
        btn = self.sender()
        if isinstance(btn, QPushButton):
            self.const_menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def clear_input(self):
        self.input.clear()

    def resizeEvent(self, event):
        super().resizeEvent(event)

        w = self.btn_area.width()
        h = self.btn_area.height()
        if w <= 0 or h <= 0:
            return

        cell_w = w // self.cols
        cell_h = h // self.rows

        min_w = 36   # min Breite pro Button
        min_h = 26   # min Höhe pro Button (DEIN Limit)

        for b in self.buttons:
            b.setMinimumSize(min_w, min_h)

        # Optional: wenn genug Platz, Buttons größer machen
        # (setMinimumSize alleine reicht meistens; das hier macht’s "snappier")
        target_w = max(min_w, cell_w)
        target_h = max(min_h, cell_h)
        for b in self.buttons:
            b.resize(target_w, target_h)

    # ---- Logik ----
    def on_clear(self):
        self.input.clear()
        self.preview.setText("")

    def on_backspace(self):
        t = self.input.text()
        self.input.setText(t[:-1])

    def on_toggle_sign(self):
        t = self.input.text().strip()
        if not t:
            return
        self.input.setText(t[1:] if t.startswith("-") else "-" + t)

    def on_equals(self):
        expr = self.input.text().strip()
        if not expr:
            return

        def root(x, y):
            return y ** (1 / x)

        safe_env = {
            "__builtins__": {},

            # Konstanten
            "pi": math.pi,
            "e": math.e,
            "tau": math.tau,
            "phi": (1 + 5 ** 0.5) / 2,
            "c": 299_792_458,      # m/s
            "g": 9.80665,         # m/s^2

            # Grundfunktionen
            "sqrt": math.sqrt,
            "root": root,
            "abs": abs,
            "round": round,

            # Trig / Log
            "sin": math.sin,
            "cos": math.cos,
            "tan": math.tan,
            "ln": math.log,
            "log10": math.log10,

            # Weitere
            "fact": lambda n: math.factorial(int(n)),

            # Speicher
            "Ans": self.ans_value if self.ans_value is not None else 0,
        }

        try:
            result = eval(expr, safe_env, {})
            self.ans_value = result
            self.preview.setText(str(result))
        except Exception as e:
            self.preview.setText(f"Fehler: {e}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.theme = Theme()
        self.close_icon = make_gray_close_icon(12)

        self.setWindowTitle(" ")
        self.resize(980, 720)

        self.setMinimumHeight(420)

        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # --- Top bar ---
        topbar = QWidget()
        topbar.setObjectName("TopBar")
        topbar_layout = QHBoxLayout(topbar)
        topbar_layout.setContentsMargins(10, 8, 10, 8)
        topbar_layout.setSpacing(8)

        self.btn_menu = QToolButton()
        self.btn_menu.setText("≡")
        self.btn_menu.setToolTip("Menü")
        self.btn_menu.setFixedSize(QSize(38, 32))
        self.btn_menu.clicked.connect(self.toggle_drawer)

        self.tabbar = QTabBar(movable=True)
        self.tabbar.setExpanding(False)
        self.tabbar.setDocumentMode(True)
        self.tabbar.setTabsClosable(True)
        self.tabbar.tabCloseRequested.connect(self.close_tab)
        self.tabbar.currentChanged.connect(self.on_tab_changed)

        self.btn_addtab = QToolButton()
        self.btn_addtab.setText("+")
        self.btn_addtab.setToolTip("Neuer Tab")
        self.btn_addtab.setFixedSize(QSize(32, 32))
        self.btn_addtab.clicked.connect(self.add_tab)

        self.btn_settings = QToolButton()
        self.btn_settings.setText("⚙")
        self.btn_settings.setToolTip("Einstellungen")
        self.btn_settings.setFixedSize(QSize(38, 32))
        self.btn_settings.clicked.connect(self.open_settings)

        topbar_layout.addWidget(self.btn_menu, 0, Qt.AlignLeft)
        topbar_layout.addWidget(self.tabbar, 1)
        topbar_layout.addWidget(self.btn_addtab, 0, Qt.AlignVCenter)
        topbar_layout.addWidget(self.btn_settings, 0, Qt.AlignRight)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Plain)

        # --- Body: Drawer links + Content rechts ---
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self.drawer = DrawerMenu(self.switch_mode, parent=body)

        self.drawer.setMaximumWidth(0)
        self.drawer.setVisible(False)
        self.drawer_open = False

        self.drawer_anim = QPropertyAnimation(self.drawer, b"maximumWidth", self)
        self.drawer_anim.setDuration(180)
        self.drawer_anim.setEasingCurve(QEasingCurve.OutCubic)

        self.stack = QStackedWidget()

        body_layout.addWidget(self.drawer, 0)
        body_layout.addWidget(self.stack, 1)

        outer.addWidget(topbar)
        outer.addWidget(sep)
        outer.addWidget(body, 1)

        self.add_tab()
        self.apply_theme()

    def apply_theme(self):
        t = self.theme
        self.setStyleSheet(f"""
            QWidget {{
                background: {t.window_bg};
                color: {t.text};
            }}

            #TopBar {{
                background: {t.topbar_bg};
            }}

            QToolButton {{
                background: {t.control_bg};
                color: {t.text_strong};
                border: 1px solid {t.border};
                border-radius: 8px;
                font-size: 16px;
            }}
            QToolButton:hover {{
                background: {t.control_hover};
            }}

            QTabBar::tab {{
                background: {t.control_bg};
                color: {t.text};
                border: 1px solid {t.border};
                padding: 6px 10px;
                margin-right: 6px;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                min-width: 110px;
            }}
            QTabBar::tab:selected {{
                background: {t.border};
                color: {t.text_strong};
            }}
            QTabBar::close-button {{
                width: 14px;
                height: 14px;
            }}

            #DrawerMenu {{
                background: {t.panel_bg};
                border-right: 1px solid #2b313c;
            }}
            #DrawerTitle {{
                color: {t.text_strong};
                font-size: 18px;
                padding: 4px 2px;
                background: transparent;
            }}
            #DrawerItem {{
                text-align: left;
                padding: 10px 10px;
                border-radius: 10px;
                background: #222733;
                color: {t.text};
                border: 1px solid #2f3746;
            }}
            #DrawerItem:hover {{
                background: #2f3746;
                color: {t.text_strong};
            }}
            #DrawerFooter {{
                color: #9aa4b2;
                padding-top: 6px;
                background: transparent;
            }}

            #DisplayFrame {{
                background: #0f1217;
                border: 1px solid #2b313c;
                border-radius: 12px;
            }}

            QLineEdit {{
                font-size: 18px;
                padding: 10px;
                background: #0c0f14;
                border: 1px solid #2b313c;
                border-radius: 10px;
                color: {t.text_strong};
            }}
            QLabel {{
                font-size: 14px;
                background: transparent;
            }}

            QPushButton {{
                font-size: 14px;        /* kleiner damit mehr Buttons gut passen */
                border-radius: 0px;
                border: 1px solid #1a1f27;
                background: #141922;
            }}
            QPushButton:hover {{
                background: #1b2230;
            }}
            QPushButton:pressed {{
                background: #202a3a;
            }}
        """)



    def toggle_drawer(self):
        self.drawer_anim.stop()

        if self.drawer_open:
            self.drawer_anim.setStartValue(self.drawer.maximumWidth())
            self.drawer_anim.setEndValue(0)
            self.drawer_open = False

            def hide_after():
                self.drawer.setVisible(False)
                self.drawer_anim.finished.disconnect(hide_after)

            self.drawer_anim.finished.connect(hide_after)
            self.drawer_anim.start()
        else:
            self.drawer.setVisible(True)
            self.drawer_anim.setStartValue(self.drawer.maximumWidth())
            self.drawer_anim.setEndValue(260)
            self.drawer_open = True
            self.drawer_anim.start()

    def add_tab(self):
        page = CalculatorPage(title="Calculator")
        idx = self.stack.addWidget(page)

        tab_index = self.tabbar.addTab(f"Tab {idx + 1}")
        self.tabbar.setCurrentIndex(tab_index)
        self.stack.setCurrentIndex(idx)

        self._apply_close_button(tab_index)

    def _apply_close_button(self, tab_index: int):
        btn = QToolButton()
        btn.setIcon(self.close_icon)
        btn.setAutoRaise(True)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip("Tab schließen")
        btn.setFixedSize(18, 18)
        btn.clicked.connect(self.close_tab_from_button)
        self.tabbar.setTabButton(tab_index, QTabBar.RightSide, btn)

    def close_tab_from_button(self):
        sender = self.sender()
        if not sender:
            return
        for i in range(self.tabbar.count()):
            if self.tabbar.tabButton(i, QTabBar.RightSide) is sender:
                self.close_tab(i)
                return

    def close_tab(self, tab_index: int):
        if self.tabbar.count() <= 1:
            return
        w = self.stack.widget(tab_index)
        self.stack.removeWidget(w)
        w.deleteLater()
        self.tabbar.removeTab(tab_index)
        self._rebuild_tabs()

    def _rebuild_tabs(self):
        count = self.stack.count()

        while self.tabbar.count() > count:
            self.tabbar.removeTab(self.tabbar.count() - 1)
        while self.tabbar.count() < count:
            self.tabbar.addTab("Tab")

        for i in range(count):
            self.tabbar.setTabText(i, f"Tab {i + 1}")
            self._apply_close_button(i)

        cur = min(self.tabbar.currentIndex(), count - 1)
        self.tabbar.setCurrentIndex(cur)
        self.stack.setCurrentIndex(cur)

    def on_tab_changed(self, index: int):
        if 0 <= index < self.stack.count():
            self.stack.setCurrentIndex(index)

    def switch_mode(self, mode_name: str):
        w = self.stack.currentWidget()
        if isinstance(w, CalculatorPage):
            w.preview.setText(f"Modus gewechselt: {mode_name} (Platzhalter)")
        if self.drawer_open:
            self.toggle_drawer()

    def open_settings(self):
        dlg = SettingsDialog(self.theme, parent=self)
        dlg.exec()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            w = self.stack.currentWidget()
            if isinstance(w, CalculatorPage):
                w.clear_input()
                return
        if event.matches(QKeySequence.AddTab):
            self.add_tab()
            return
        super().keyPressEvent(event)


def main():
    app = QApplication(sys.argv)

    app.setWindowIcon(QIcon("assets/app_icon2.png"))  # ← WICHTIG

    win = MainWindow()
    win.show()
    sys.exit(app.exec())



if __name__ == "__main__":
    main()
