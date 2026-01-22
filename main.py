# main.py
import sys
import math
import re
from dataclasses import dataclass

from PySide6.QtCore import Qt, QSize, QPropertyAnimation, QEasingCurve, QEvent
from PySide6.QtGui import QKeySequence, QPainter, QPen, QPixmap, QIcon, QColor, QAction
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QToolButton, QTabBar, QStackedWidget, QLabel,
    QGridLayout, QPushButton, QFrame, QSizePolicy,
    QDialog, QDialogButtonBox, QColorDialog, QMenu
)
from PySide6.QtWebEngineWidgets import QWebEngineView


# ---------------- MathQuill HTML ----------------
HTML = r"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />

  <!-- Prototype via CDN (Internet required). Later we can vendor these files for offline. -->
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/mathquill/build/mathquill.css">
  <script src="https://cdn.jsdelivr.net/npm/jquery@3.7.1/dist/jquery.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/mathquill/build/mathquill.min.js"></script>

  <style>
    body {
      margin: 0;
      padding: 0;
      background: transparent;
      font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial;
    }

    /* "Input field" look */
    .wrap {
      border: 1px solid #2b313c;
      border-radius: 10px;
      padding: 10px 12px;
      background: #0c0f14;
      color: #ffffff;
    }

    #mathbox {
      min-height: 30px;
      font-size: 22px;
      color: #ffffff;
    }

    .mq-editable-field {
      border: none !important;
      box-shadow: none !important;
      background: transparent !important;
    }

    .mq-cursor {
      border-left: 2px solid #ffffff !important;
    }
  </style>
</head>

<body>
  <div class="wrap">
    <span id="mathbox"></span>
  </div>

  <script>
    const MQ = MathQuill.getInterface(2);

    window.mq = MQ.MathField(document.getElementById('mathbox'), {
      spaceBehavesLikeTab: true
    });

    window.mq_getLatex = function() { return window.mq.latex(); };

    window.mq_setLatex = function(s) {
      window.mq.latex(s || "");
      window.mq.focus();
      return true;
    };

    window.mq_writeLatex = function(s) {
      window.mq.write(s || "");
      window.mq.focus();
      return true;
    };

    window.mq_cmd = function(s) {
      // cmd inserts control sequence (like "sqrt", "frac")
      window.mq.cmd(s || "");
      window.mq.focus();
      return true;
    };

    window.mq_keystroke = function(k) {
      window.mq.keystroke(k || "");
      window.mq.focus();
      return true;
    };

    window.mq_clear = function() {
      window.mq.latex("");
      window.mq.focus();
      return true;
    };

    window.mq_focus = function() {
      window.mq.focus();
      return true;
    };

    window.mq.focus();
  </script>
</body>
</html>
"""


# ---------------- Helpers: Theme + icons ----------------
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

        root.addWidget(QLabel("Farben anpassen (wirkt sofort):"))

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


# ---------------- LaTeX -> Python (MVP) ----------------
def latex_to_python(expr: str) -> str:
    """
    MVP Converter: MathQuill LaTeX -> Python expression
    Supports: frac, sqrt, nth-root (sqrt[]{}), pi/tau/phi, sin/cos/tan/ln/log, cdot, exponents.
    """
    if not expr:
        return ""

    s = expr.replace(" ", "")
    s = s.replace(r"\left", "").replace(r"\right", "")
    s = s.replace(r"\cdot", "*")

    # constants
    s = s.replace(r"\pi", "pi")
    s = s.replace(r"\tau", "tau")
    s = s.replace(r"\phi", "phi")

    # functions (MathQuill often outputs \sin, \cos, \tan, \ln, \log)
    s = s.replace(r"\sin", "sin")
    s = s.replace(r"\cos", "cos")
    s = s.replace(r"\tan", "tan")
    s = s.replace(r"\ln", "ln")
    s = s.replace(r"\log", "log10")

    # Helper: {..} parsing
    def extract_brace(text: str, brace_pos: int):
        assert text[brace_pos] == "{"
        depth = 0
        i = brace_pos
        while i < len(text):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    return text[brace_pos + 1 : i], i
            i += 1
        return text[brace_pos + 1 :], len(text) - 1

    # Convert \sqrt[IDX]{RAD}
    while True:
        m = re.search(r"\\sqrt\[(.*?)\]\{", s)
        if not m:
            break
        idx_str = m.group(1)
        start = m.start()
        brace_pos = m.end() - 1  # points at '{'
        rad, end_rad = extract_brace(s, brace_pos)
        idx_py = latex_to_python(idx_str)
        rad_py = latex_to_python(rad)
        # nth root: root(n, x) = x**(1/n)
        s = s[:start] + f"root(({idx_py}),({rad_py}))" + s[end_rad + 1 :]

    # Convert \sqrt{...}
    while True:
        m = re.search(r"\\sqrt\{", s)
        if not m:
            break
        start = m.start()
        inner, end = extract_brace(s, m.end() - 1)
        inner_py = latex_to_python(inner)
        s = s[:start] + f"sqrt({inner_py})" + s[end + 1 :]

    # Convert \frac{...}{...}
    while True:
        m = re.search(r"\\frac\{", s)
        if not m:
            break
        start = m.start()
        num, end_num = extract_brace(s, m.end() - 1)
        if end_num + 1 >= len(s) or s[end_num + 1] != "{":
            break
        den, end_den = extract_brace(s, end_num + 1)
        num_py = latex_to_python(num)
        den_py = latex_to_python(den)
        s = s[:start] + f"(({num_py})/({den_py}))" + s[end_den + 1 :]

    # Exponents: ^{...} -> **(...)
    while True:
        m = re.search(r"\^\{", s)
        if not m:
            break
        inner, end = extract_brace(s, m.start() + 1)  # '{' at m.start()+1
        inner_py = latex_to_python(inner)
        s = s[:m.start()] + f"**({inner_py})" + s[end + 1 :]

    # Exponents: ^2 or ^x
    s = re.sub(r"\^([0-9]+)", r"**(\1)", s)
    s = re.sub(r"\^([a-zA-Z]+)", r"**(\1)", s)

    # Factorial "!" -> fact(...)
    # Simple pass: replace "n!" with fact(n) for plain numbers/identifiers/closing paren.
    # This is simplistic; good enough for MVP.
    s = re.sub(r"([0-9]+)!", r"fact(\1)", s)
    s = re.sub(r"([a-zA-Z_][a-zA-Z0-9_]*)!", r"fact(\1)", s)
    s = re.sub(r"(\))!", r"fact\1", s)  # rarely correct but keeps something

    return s


def safe_eval(expr: str, ans_value):
    def root(n, x):
        return x ** (1 / n)

    env = {
        "__builtins__": {},
        "pi": math.pi,
        "e": math.e,
        "tau": math.tau,
        "phi": (1 + 5 ** 0.5) / 2,
        "c": 299_792_458,
        "g": 9.80665,
        "sqrt": math.sqrt,
        "root": root,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "ln": math.log,
        "log10": math.log10,
        "abs": abs,
        "round": round,
        "fact": lambda n: math.factorial(int(n)),
        "Ans": ans_value if ans_value is not None else 0,
    }
    return eval(expr, env, {})


# ---------------- Calculator Page (MathQuill + Buttons) ----------------
class CalculatorPage(QWidget):
    """
    MathQuill 2D input in QWebEngineView + output label + 6x6 grid.
    ESC clears input (MainWindow handles).
    Buttons resize down in height until min_h.
    """
    def __init__(self, title="Calculator"):
        super().__init__()
        self.title = title
        self.ans_value = None

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # Display frame
        display_frame = QFrame()
        display_frame.setObjectName("DisplayFrame")
        display_layout = QVBoxLayout(display_frame)
        display_layout.setContentsMargins(12, 12, 12, 12)
        display_layout.setSpacing(8)

        self.web = QWebEngineView()
        self.web.setObjectName("MathField")
        self.web.setHtml(HTML)
        display_layout.addWidget(self.web)

        self.preview = QLabel("Output/Preview erscheint hier…")
        self.preview.setWordWrap(True)
        self.preview.setTextInteractionFlags(Qt.TextSelectableByMouse)
        display_layout.addWidget(self.preview)

        root.addWidget(display_frame, 0)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        root.addWidget(line)

        # Buttons grid area
        self.btn_area = QWidget()
        self.btn_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.grid = QGridLayout(self.btn_area)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(0)
        self.grid.setVerticalSpacing(0)

        self.buttons = []

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

        # constants menu
        self.const_menu = QMenu(self)
        const_items = [
            ("π (pi)", r"\pi"),
            ("e", "e"),
            ("τ (tau)", r"\tau"),
            ("φ (phi)", r"\phi"),
            ("c (Licht)", "c"),
            ("g (Erde)", "g"),
        ]
        for title, token in const_items:
            act = QAction(title, self)
            act.triggered.connect(lambda _=False, tok=token: self.mq_write(tok))
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
                elif label == "a/b":
                    btn.clicked.connect(lambda _=False: self.mq_write(r"\frac{}{}"))
                elif label == "÷":
                    btn.clicked.connect(lambda _=False: self.mq_write("/"))
                elif label == "×":
                    btn.clicked.connect(lambda _=False: self.mq_write(r"\cdot"))
                elif label == "−":
                    btn.clicked.connect(lambda _=False: self.mq_write("-"))
                elif label == "√":
                    btn.clicked.connect(lambda _=False: self.mq_write(r"\sqrt{}"))
                elif label == "x√y":
                    # nth root template: \sqrt[]{} (index + radicand)
                    btn.clicked.connect(lambda _=False: self.mq_write(r"\sqrt[]{}"))
                elif label == "xʸ":
                    btn.clicked.connect(lambda _=False: self.mq_write(r"^{}"))
                elif label == "10^x":
                    btn.clicked.connect(lambda _=False: self.mq_write(r"10^{}"))
                elif label == "sin":
                    btn.clicked.connect(lambda _=False: self.mq_write(r"\sin\left(\right)"))
                elif label == "cos":
                    btn.clicked.connect(lambda _=False: self.mq_write(r"\cos\left(\right)"))
                elif label == "tan":
                    btn.clicked.connect(lambda _=False: self.mq_write(r"\tan\left(\right)"))
                elif label == "ln":
                    btn.clicked.connect(lambda _=False: self.mq_write(r"\ln\left(\right)"))
                elif label == "log":
                    btn.clicked.connect(lambda _=False: self.mq_write(r"\log\left(\right)"))
                elif label == "!":
                    btn.clicked.connect(lambda _=False: self.mq_write("!"))
                elif label == "±":
                    # MVP: inserts "-" (real toggle is more complex)
                    btn.clicked.connect(lambda _=False: self.mq_write("-"))
                elif label == "Ans":
                    btn.clicked.connect(lambda _=False: self.mq_write("Ans"))
                elif label == "Konst":
                    btn.clicked.connect(self.open_constants_menu)
                elif label == "π":
                    btn.clicked.connect(lambda _=False: self.mq_write(r"\pi"))
                elif label == "e":
                    btn.clicked.connect(lambda _=False: self.mq_write("e"))
                else:
                    # digits, '.', '+', parentheses
                    btn.clicked.connect(lambda _=False, t=label: self.mq_write(t))

                self.grid.addWidget(btn, r, c)
                self.buttons.append(btn)

        for r in range(self.rows):
            self.grid.setRowStretch(r, 1)
        for c in range(self.cols):
            self.grid.setColumnStretch(c, 1)

        root.addWidget(self.btn_area, 1)

    # ----- MathQuill bridge helpers -----
    def mq_write(self, latex: str):
        # ensure focused and insert
        self.web.page().runJavaScript(f"mq_writeLatex({latex!r})")

    def mq_clear(self):
        self.web.page().runJavaScript("mq_clear()")

    def mq_backspace(self):
        self.web.page().runJavaScript("mq_keystroke('Backspace')")

    def mq_get_latex(self, callback):
        self.web.page().runJavaScript("mq_getLatex()", callback)

    # ----- UI actions -----
    def open_constants_menu(self):
        btn = self.sender()
        if isinstance(btn, QPushButton):
            self.const_menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def clear_input(self):
        self.mq_clear()

    def resizeEvent(self, event):
        super().resizeEvent(event)

        w = self.btn_area.width()
        h = self.btn_area.height()
        if w <= 0 or h <= 0:
            return

        cell_w = w // self.cols
        cell_h = h // self.rows

        min_w = 36
        min_h = 26

        for b in self.buttons:
            b.setMinimumSize(min_w, min_h)

        target_w = max(min_w, cell_w)
        target_h = max(min_h, cell_h)
        for b in self.buttons:
            b.resize(target_w, target_h)

    def on_clear(self):
        self.mq_clear()
        self.preview.setText("")

    def on_backspace(self):
        self.mq_backspace()

    def on_equals(self):
        def got(latex):
            latex = latex or ""
            py_expr = latex_to_python(latex)
            if not py_expr.strip():
                return
            try:
                res = safe_eval(py_expr, self.ans_value)
                self.ans_value = res
                self.preview.setText(str(res))
            except Exception as e:
                self.preview.setText(f"Fehler: {e}\n\nLaTeX: {latex}\nPython: {py_expr}")

        self.mq_get_latex(got)


# ---------------- Main Window (tabs + drawer) ----------------
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

        # --- Body ---
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

    # ---------- Theme ----------
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

            QLabel {{
                font-size: 14px;
                background: transparent;
            }}

            QPushButton {{
                font-size: 14px;
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

    # ---------- Drawer ----------
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

    # ---------- Tabs ----------
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

    # ---------- Menu / Mode ----------
    def switch_mode(self, mode_name: str):
        w = self.stack.currentWidget()
        if isinstance(w, CalculatorPage):
            w.preview.setText(f"Modus gewechselt: {mode_name} (Platzhalter)")
        if self.drawer_open:
            self.toggle_drawer()

    # ---------- Settings ----------
    def open_settings(self):
        dlg = SettingsDialog(self.theme, parent=self)
        dlg.exec()

    # ---------- ESC: clear current input ----------
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

    # your app icon (optional)
    app.setWindowIcon(QIcon("assets/app_icon2.png"))

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
