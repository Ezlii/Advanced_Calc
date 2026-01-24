# main.py
import sys
import math
import re
import json
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QPropertyAnimation, QEasingCurve, QObject, Slot, QEvent
from PySide6.QtGui import (
    QKeySequence, QPainter, QPen, QPixmap, QIcon, QColor, QAction, QShortcut
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QToolButton, QTabBar, QStackedWidget, QLabel,
    QGridLayout, QPushButton, QFrame, QSizePolicy,
    QDialog, QDialogButtonBox, QColorDialog, QMenu, QComboBox
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtCore import QUrl


# ---------------- MathQuill INPUT HTML ----------------
HTML_INPUT = r"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />

  <link rel="stylesheet" href="mathquill.css">
  <script src="jquery.min.js"></script>
  <script src="mathquill.min.js"></script>

  <style>
    body { margin:0; padding:0; background:transparent; font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial; }
    .wrap {
      border: 1px solid #2b313c;
      border-radius: 10px;
      padding: 10px 12px;
      background: #0c0f14;
      color: #ffffff;
    }
    #mathbox { min-height: 30px; font-size: 22px; color:#ffffff; }
    .mq-editable-field { border:none !important; box-shadow:none !important; background:transparent !important; }
    .mq-cursor { border-left: 2px solid #ffffff !important; }
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


# ---------------- HISTORY HTML (MathJax + clickable) ----------------
HTML_HISTORY = r"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <style>
    body { margin:0; padding:0; background:transparent; font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial; }
    .wrap {
      background: #0f1217;
      border: 1px solid #2b313c;
      border-radius: 12px;
      padding: 10px;
      height: 100vh;
      box-sizing: border-box;
      overflow: auto;
    }

    .entry {
      border: 1px solid #2b313c;
      border-radius: 10px;
      background: #0c0f14;
      padding: 10px 12px;
      margin-bottom: 10px;
      cursor: pointer;
      user-select: none;
    }
    .entry:hover { background: #121826; }

    .expr { color:#ffffff; font-weight:600; font-size: 16px; }
    .res  { margin-top: 6px; color:#d7dde7; font-size: 16px; }
    .hint { color:#9aa4b2; font-size: 14px; padding: 8px 4px; }

    /* MathJax */
    mjx-container { color: #ffffff !important; }
  </style>

  <!-- QWebChannel (Qt) -->
  <script src="qrc:///qtwebchannel/qwebchannel.js"></script>

  <!-- MathJax (CDN) -->
  <script>
    window.MathJax = {
      tex: { inlineMath: [['\\(','\\)'], ['$', '$']] },
      svg: { fontCache: 'global' }
    };
  </script>
  <script defer src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js"></script>
</head>
<body>
  <div class="wrap" id="wrap">
    <div class="hint" id="hint">History...</div>
    <div id="list"></div>
  </div>

  <script>
    let bridge = null;

    new QWebChannel(qt.webChannelTransport, function(channel) {
      bridge = channel.objects.bridge;
    });

    function escapeHtml(s) {
      return (s || "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;")
                      .replaceAll('"',"&quot;").replaceAll("'","&#039;");
    }

    function addEntry(latex, resultText) {
      const hint = document.getElementById("hint");
      if (hint) hint.style.display = "none";

      const list = document.getElementById("list");

      // IMPORTANT: latex should be inserted into MathJax delimiters
      const latexEsc = escapeHtml(latex || "");
      const resEsc = escapeHtml(resultText || "");

      const div = document.createElement("div");
      div.className = "entry";
      div.setAttribute("data-latex", latex || "");

      div.innerHTML = `
        <div class="expr">\\(${latexEsc}\\)</div>
        <div class="res">= ${resEsc}</div>
      `;

      div.addEventListener("click", () => {
        const ltx = div.getAttribute("data-latex") || "";
        if (bridge && bridge.setFromHistory) {
          bridge.setFromHistory(ltx);
        }
      });

      // prepend: newest on top
      if (list.firstChild) list.insertBefore(div, list.firstChild);
      else list.appendChild(div);

      // typeset this entry only
      if (window.MathJax && MathJax.typesetPromise) {
        MathJax.typesetPromise([div]).catch(()=>{});
      }
    }

    window.history_addEntry = addEntry;
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


@dataclass
class AppSettings:
    number_format: str = "Normal"   # "Normal", "SCI", "ENG"
    angle_unit: str = "RAD"         # "RAD" oder "DEG"




class SettingsDialog(QDialog):
    def __init__(self, theme: Theme, settings: AppSettings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Einstellungen")
        self.setModal(True)

        self.theme = theme
        self.settings = settings

        root = QVBoxLayout(self)
        root.setContentsMargins(15, 15, 15, 15)
        root.setSpacing(10)

        root.addWidget(QLabel("Farben anpassen:"))

        row = QHBoxLayout()
        self.btn_bg = QPushButton("Fenster-Hintergrund…")
        self.btn_fg = QPushButton("Schriftfarbe…")
        row.addWidget(self.btn_bg)
        row.addWidget(self.btn_fg)
        root.addLayout(row)

        root.addWidget(QLabel("Zahlenformat:"))

        # WICHTIG: erst erstellen...
        self.cmb_format = QComboBox()
        self.cmb_format.addItems(["Normal", "SCI", "ENG"])
        root.addWidget(self.cmb_format)

        root.addWidget(QLabel("Winkelmodus (sin/cos/tan):"))

        self.cmb_angle = QComboBox()
        self.cmb_angle.addItems(["RAD", "DEG"])
        root.addWidget(self.cmb_angle)

        # aktuellen Wert setzen
        idx2 = self.cmb_angle.findText(self.settings.angle_unit)
        if idx2 >= 0:
            self.cmb_angle.setCurrentIndex(idx2)

        self.cmb_angle.currentTextChanged.connect(self.on_angle_changed)


        # ...dann aktuellen Wert setzen
        idx = self.cmb_format.findText(self.settings.number_format)
        if idx >= 0:
            self.cmb_format.setCurrentIndex(idx)

        self.cmb_format.currentTextChanged.connect(self.on_format_changed)

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

    def on_format_changed(self, text: str):
        self.settings.number_format = text
        if isinstance(self.parent(), MainWindow):
            self.parent().apply_settings()

    def on_angle_changed(self, text: str):
        self.settings.angle_unit = text
        if isinstance(self.parent(), MainWindow):
            self.parent().apply_settings()



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
    if not expr:
        return ""

    s = expr.replace(" ", "")
    s = s.replace(r"\left", "").replace(r"\right", "")
    s = s.replace(r"\cdot", "*")
    s = s.replace(r"\bmod", "%")

    s = s.replace(r"\pi", "pi")
    s = s.replace(r"\tau", "tau")
    s = s.replace(r"\phi", "phi")

    s = s.replace(r"\sin", "sin")
    s = s.replace(r"\cos", "cos")
    s = s.replace(r"\tan", "tan")
    # inverse trig: \sin^{-1}(x) -> asin(x) usw.
    s = s.replace(r"sin^{-1}", "asin")
    s = s.replace(r"cos^{-1}", "acos")
    s = s.replace(r"tan^{-1}", "atan")

    s = s.replace(r"\ln", "ln")

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
                    return text[brace_pos + 1: i], i
            i += 1
        return text[brace_pos + 1:], len(text) - 1

    def extract_paren(text: str, paren_pos: int):
        assert text[paren_pos] == "("
        depth = 0
        i = paren_pos
        while i < len(text):
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
                if depth == 0:
                    return text[paren_pos + 1: i], i
            i += 1
        return text[paren_pos + 1:], len(text) - 1

    # ABS: |...|
    while True:
        a = s.find("|")
        if a == -1:
            break
        b = s.find("|", a + 1)
        if b == -1:
            break
        inner = s[a + 1:b]
        inner_py = latex_to_python(inner)
        s = s[:a] + f"abs({inner_py})" + s[b + 1:]

    # \sqrt[IDX]{RAD}
    while True:
        m = re.search(r"\\sqrt\[(.*?)\]\{", s)
        if not m:
            break
        idx_str = m.group(1)
        start = m.start()
        brace_pos = m.end() - 1
        rad, end_rad = extract_brace(s, brace_pos)
        idx_py = latex_to_python(idx_str)
        rad_py = latex_to_python(rad)
        s = s[:start] + f"root(({idx_py}),({rad_py}))" + s[end_rad + 1:]

    # \sqrt{...}
    while True:
        m = re.search(r"\\sqrt\{", s)
        if not m:
            break
        start = m.start()
        inner, end = extract_brace(s, m.end() - 1)
        inner_py = latex_to_python(inner)
        s = s[:start] + f"sqrt({inner_py})" + s[end + 1:]

    # \frac{...}{...}
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
        s = s[:start] + f"(({num_py})/({den_py}))" + s[end_den + 1:]

    # log base: \log_{b}(x) -> log(x, b)
    while True:
        m = re.search(r"\\log_\{", s)
        if not m:
            break
        start = m.start()
        base, end_base = extract_brace(s, m.end() - 1)
        if end_base + 1 >= len(s) or s[end_base + 1] != "(":
            break
        arg, end_arg = extract_paren(s, end_base + 1)
        base_py = latex_to_python(base)
        arg_py = latex_to_python(arg)
        s = s[:start] + f"log(({arg_py}),({base_py}))" + s[end_arg + 1:]

    # plain \log(...) -> log10(...)
    s = s.replace(r"\log", "log10")

    # exponents
    while True:
        m = re.search(r"\^\{", s)
        if not m:
            break
        inner, end = extract_brace(s, m.start() + 1)
        inner_py = latex_to_python(inner)
        s = s[:m.start()] + f"**({inner_py})" + s[end + 1:]

    s = re.sub(r"\^([0-9]+)", r"**(\1)", s)
    s = re.sub(r"\^([a-zA-Z]+)", r"**(\1)", s)

    # factorial
    s = re.sub(r"([0-9]+)!", r"fact(\1)", s)
    s = re.sub(r"([a-zA-Z_][a-zA-Z0-9_]*)!", r"fact(\1)", s)
    s = re.sub(r"(\))!", r"fact\1", s)

    return s


def safe_eval(expr: str, ans_value, angle_unit: str = "RAD"):
    def root(n, x):
        return x ** (1 / n)

    def to_rad(x):
        return math.radians(x) if angle_unit == "DEG" else x

    def from_rad(x):
        return math.degrees(x) if angle_unit == "DEG" else x

    # trig angepasst
    def sin_(x): return math.sin(to_rad(x))
    def cos_(x): return math.cos(to_rad(x))
    def tan_(x): return math.tan(to_rad(x))

    def asin_(x): return from_rad(math.asin(x))
    def acos_(x): return from_rad(math.acos(x))
    def atan_(x): return from_rad(math.atan(x))

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

        # trig (RAD/DEG)
        "sin": sin_,
        "cos": cos_,
        "tan": tan_,
        "asin": asin_,
        "acos": acos_,
        "atan": atan_,

        "ln": math.log,
        "log10": math.log10,
        "log": math.log,  # log(x, base)
        "abs": abs,
        "round": round,
        "fact": lambda n: math.factorial(int(n)),
        "Ans": ans_value if ans_value is not None else 0,
    }
    return eval(expr, env, {})


def format_number(value, mode: str) -> str:
    if isinstance(value, str):
        return value

    # bool ist auch int in Python -> aussortieren
    if isinstance(value, bool):
        return str(value)

    # ints: nur Normal direkt, sonst als float formatieren
    if isinstance(value, int):
        if mode == "Normal":
            return str(value)
        x = float(value)
    else:
        try:
            x = float(value)
        except Exception:
            return str(value)

    if mode == "SCI":
        return f"{x:.10e}"

    if mode == "ENG":
        if x == 0.0:
            return "0"
        sign = -1.0 if x < 0 else 1.0
        ax = abs(x)
        exp = int(math.floor(math.log10(ax)))
        eng_exp = exp - (exp % 3)
        mant = sign * (ax / (10 ** eng_exp))
        mant_str = f"{mant:.10f}".rstrip("0").rstrip(".")
        return f"{mant_str}e{eng_exp}"

    # Normal
    return f"{x:.12g}"




# ---------------- Calculator Page (Input + History + Buttons) ----------------
class CalculatorPage(QWidget):
    class HistoryBridge(QObject):
        def __init__(self, parent_page: "CalculatorPage"):
            super().__init__()
            self.page = parent_page

        @Slot(str)
        def setFromHistory(self, latex: str):
            self.page.mq_set(latex)
            self.page.focus_mathfield()

    def __init__(self, title="Calculator"):
        super().__init__()
        self.title = title
        self.ans_value = None

        # 2nd toggle state
        self.second_mode = False
        self.btn_trig = {}
        self.btn_second = None

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # Display frame (Input + History)
        display_frame = QFrame()
        display_frame.setObjectName("DisplayFrame")
        display_layout = QVBoxLayout(display_frame)
        display_layout.setContentsMargins(12, 12, 12, 12)
        display_layout.setSpacing(3)

        # --- Input bar (MathQuill) ---
        self.web = QWebEngineView()
        self.web.setObjectName("MathField")
        self.web.setFocusPolicy(Qt.StrongFocus)
        self.web.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.web.setMinimumHeight(70)
        self.web.setMaximumHeight(90)

        base_dir = Path(__file__).resolve().parent / "assets" / "web"
        self.web.setHtml(HTML_INPUT, baseUrl=QUrl.fromLocalFile(str(base_dir) + "/"))
        self.web.loadFinished.connect(lambda _ok: self.focus_mathfield())
        display_layout.addWidget(self.web)

        # --- History (WebView for MathJax + click) ---
        self.history_web = QWebEngineView()
        self.history_web.setObjectName("HistoryWeb")
        self.history_web.setFocusPolicy(Qt.NoFocus)  # clicks go through JS anyway
        self.history_web.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.bridge = CalculatorPage.HistoryBridge(self)
        self.channel = QWebChannel(self.history_web.page())
        self.channel.registerObject("bridge", self.bridge)
        self.history_web.page().setWebChannel(self.channel)

        


        # load history html
        self.history_web.setHtml(HTML_HISTORY, baseUrl=QUrl("about:blank"))
        display_layout.addWidget(self.history_web, 1)


        # --- Input WebView: echten Hintergrund transparent machen ---
        self.web.setAttribute(Qt.WA_TranslucentBackground, True)
        self.web.page().setBackgroundColor(Qt.transparent)

        # --- History WebView: Hintergrund auf dunkel setzen (damit nix weiß aufblitzt) ---
        self.history_web.setAttribute(Qt.WA_TranslucentBackground, True)
        self.history_web.page().setBackgroundColor(QColor("#0f1217"))

        root.addWidget(display_frame, 1)

        # separator
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
        ["2nd", "C",  "⌫",  "(",   ")",   "a/b"],   # <- a/b statt ÷
        ["7",   "8",  "9",  "×",   "x²",  "xʸ"],
        ["4",   "5",  "6",  "−",   "√",   "x√y"],
        ["1",   "2",  "3",  "+",   "sin", "cos"],
        ["0",   ".",  "±",  "=",   "tan", "Ans"],
        ["1/x", "|x|","mod","ln",  "log", "logᵧ(x)"],
        ["Konst","π", "e",  "10^x","!",   "÷"],     # <- ÷ ins leere Feld
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

                if label == "":
                    btn.setEnabled(False)

                elif label == "2nd":
                    self.btn_second = btn
                    btn.clicked.connect(self.toggle_second)

                elif label == "C":
                    btn.clicked.connect(self.on_clear)
                elif label == "⌫":
                    btn.clicked.connect(self.on_backspace)
                elif label == "=":
                    btn.clicked.connect(self.on_equals)
                    btn.setDefault(True)

                elif label == "÷":
                    btn.clicked.connect(lambda _=False: self.mq_write("/"))
                elif label == "×":
                    btn.clicked.connect(lambda _=False: self.mq_write(r"\cdot"))
                elif label == "−":
                    btn.clicked.connect(lambda _=False: self.mq_write("-"))
                elif label == "√":
                    btn.clicked.connect(lambda _=False: self.mq_cmd_and_keys("sqrt"))
                elif label == "x√y":
                    btn.clicked.connect(lambda _=False: self.mq_write_and_keys(r"\sqrt[]{}", "Left"))
                elif label == "xʸ":
                    btn.clicked.connect(lambda _=False: self.mq_write(r"^{}"))
                elif label == "10^x":
                    btn.clicked.connect(lambda _=False: self.mq_write_and_keys("10^{}", "Left"))
                elif label == "x²":
                    btn.clicked.connect(lambda _=False: self.mq_write("^2"))
                elif label == "a/b":
                    btn.clicked.connect(lambda _=False: self.mq_cmd_and_keys("frac", "Up"))
                elif label == "sin":
                    self.btn_trig["sin"] = btn
                    btn.clicked.connect(lambda _=False: self.on_trig("sin"))
                elif label == "cos":
                    self.btn_trig["cos"] = btn
                    btn.clicked.connect(lambda _=False: self.on_trig("cos"))
                elif label == "tan":
                    self.btn_trig["tan"] = btn
                    btn.clicked.connect(lambda _=False: self.on_trig("tan"))
                elif label == "ln":
                    btn.clicked.connect(lambda _=False: self.mq_write(r"\ln\left(\right)"))
                elif label == "log":
                    btn.clicked.connect(lambda _=False: self.mq_write(r"\log\left(\right)"))
                elif label == "logᵧ(x)":
                    btn.clicked.connect(lambda _=False: self.mq_write_and_keys(r"\log_{}\left(\right)", "Left"))
                elif label == "!":
                    btn.clicked.connect(lambda _=False: self.mq_write("!"))
                elif label == "±":
                    btn.clicked.connect(lambda _=False: self.mq_write("-"))
                elif label == "Ans":
                    btn.clicked.connect(lambda _=False: self.mq_write("Ans"))
                elif label == "Konst":
                    btn.clicked.connect(self.open_constants_menu)
                elif label == "π":
                    btn.clicked.connect(lambda _=False: self.mq_write(r"\pi"))
                elif label == "e":
                    btn.clicked.connect(lambda _=False: self.mq_write("e"))
                elif label == "|x|":
                    btn.clicked.connect(lambda _=False: self.mq_write_and_keys(r"\left|\right|", "Left"))
                elif label == "mod":
                    btn.clicked.connect(lambda _=False: self.mq_write(r"\bmod"))
                elif label == "1/x":
                    btn.clicked.connect(self.insert_reciprocal)

                else:
                    btn.clicked.connect(lambda _=False, t=label: self.mq_write(t))

                self.grid.addWidget(btn, r, c)
                self.buttons.append(btn)

        for rr in range(self.rows):
            self.grid.setRowStretch(rr, 1)
        for cc in range(self.cols):
            self.grid.setColumnStretch(cc, 1)

        root.addWidget(self.btn_area, 1)

        self.refresh_second_ui()

    # ----- Fokus helper -----
    def focus_mathfield(self):
        self.web.setFocus(Qt.OtherFocusReason)
        self.web.page().runJavaScript("mq_focus();")

    # ----- MathQuill bridge helpers -----
    def mq_write(self, latex: str):
        self.web.page().runJavaScript(f"mq_writeLatex({latex!r})")

    def mq_set(self, latex: str):
        self.web.page().runJavaScript(f"mq_setLatex({latex!r})")

    def mq_write_and_keys(self, latex: str, *keys: str):
        js = [f"mq_writeLatex({latex!r});"]
        for k in keys:
            js.append(f"mq_keystroke({k!r});")
        js.append("mq_focus();")
        self.web.page().runJavaScript("".join(js))

    def mq_cmd_and_keys(self, cmd: str, *keys: str):
        js = [f"mq_cmd({cmd!r});"]
        for k in keys:
            js.append(f"mq_keystroke({k!r});")
        js.append("mq_focus();")
        self.web.page().runJavaScript("".join(js))

    def mq_clear(self):
        self.web.page().runJavaScript("mq_clear()")

    def mq_backspace(self):
        self.web.page().runJavaScript("mq_keystroke('Backspace')")

    def mq_get_latex(self, callback):
        self.web.page().runJavaScript("mq_getLatex()", callback)

    # ----- History -----
    def append_history(self, latex: str, result_text: str):
        # Call JS function to prepend entry and render via MathJax
        # Use JSON to escape safely.
        ltx = latex or ""
        res = result_text or ""
        js = f"window.history_addEntry({json.dumps(ltx)}, {json.dumps(res)});"
        self.history_web.page().runJavaScript(js)

    # ----- 2nd logic -----
    def toggle_second(self):
        self.second_mode = not self.second_mode
        self.refresh_second_ui()
        self.focus_mathfield()

    def refresh_second_ui(self):
        if "sin" in self.btn_trig:
            self.btn_trig["sin"].setText("sin⁻¹" if self.second_mode else "sin")
        if "cos" in self.btn_trig:
            self.btn_trig["cos"].setText("cos⁻¹" if self.second_mode else "cos")
        if "tan" in self.btn_trig:
            self.btn_trig["tan"].setText("tan⁻¹" if self.second_mode else "tan")
        if self.btn_second:
            self.btn_second.setText("2nd✓" if self.second_mode else "2nd")

    def on_trig(self, kind: str):
        if self.second_mode:
            if kind == "sin":
                self.mq_write(r"\sin^{-1}\left(\right)")
            elif kind == "cos":
                self.mq_write(r"\cos^{-1}\left(\right)")
            elif kind == "tan":
                self.mq_write(r"\tan^{-1}\left(\right)")
        else:
            if kind == "sin":
                self.mq_write(r"\sin\left(\right)")
            elif kind == "cos":
                self.mq_write(r"\cos\left(\right)")
            elif kind == "tan":
                self.mq_write(r"\tan\left(\right)")
        self.focus_mathfield()

    def insert_reciprocal(self):
        js = [
            "mq_cmd('frac');",
            "mq_writeLatex('1');",
            "mq_keystroke('Down');",
            "mq_focus();"
        ]
        self.web.page().runJavaScript("".join(js))

    # ----- UI actions -----
    def open_constants_menu(self):
        btn = self.sender()
        if isinstance(btn, QPushButton):
            self.const_menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    def clear_input(self):
        self.mq_clear()
        self.focus_mathfield()

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
        self.focus_mathfield()

    def on_backspace(self):
        self.mq_backspace()
        self.focus_mathfield()

    def on_equals(self):
        def got(latex):
            latex = latex or ""
            py_expr = latex_to_python(latex)
            if not py_expr.strip():
                return
            try:
                angle = "RAD"
                mw = self.window()
                if isinstance(mw, MainWindow):
                    angle = mw.settings.angle_unit

                res = safe_eval(py_expr, self.ans_value, angle_unit=angle)
                self.ans_value = res
                mode = "Normal"
                mw = self.window()
                if isinstance(mw, MainWindow):
                    mode = mw.settings.number_format
                self.append_history(latex, format_number(res, mode))
            except Exception as e:
                self.append_history(latex, f"Fehler: {e}")
            finally:
                self.focus_mathfield()

        self.mq_get_latex(got)


# ---------------- Main Window (tabs + drawer) ----------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.theme = Theme()
        self.settings = AppSettings()
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

        self._enter_filter = MainWindow._GlobalEnterFilter(self)
        QApplication.instance().installEventFilter(self._enter_filter)


        # ESC global
        self.sc_esc = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self.sc_esc.setContext(Qt.ApplicationShortcut)
        self.sc_esc.activated.connect(self._esc_clear_current)


        self.add_tab()
        self.apply_theme()

    class _GlobalEnterFilter(QObject):
        def __init__(self, win: "MainWindow"):
            super().__init__(win)
            self.win = win

        def eventFilter(self, obj, event):
            # 1) ShortcutOverride: nur abfangen, damit Qt nix anderes damit macht
            if event.type() == QEvent.ShortcutOverride:
                if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                    if event.modifiers() & Qt.ShiftModifier:
                        return False
                    return True  # nur blocken, NICHT auslösen

            # 2) KeyPress: hier genau 1x auslösen
            if event.type() == QEvent.KeyPress:
                if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                    if event.modifiers() & Qt.ShiftModifier:
                        return False
                    if event.isAutoRepeat():           # wichtig gegen key-repeat
                        return True
                    if not self.win.isActiveWindow():
                        return False
                    self.win._enter_equals()
                    return True

            return False



    def _esc_clear_current(self):
        w = self.stack.currentWidget()
        if isinstance(w, CalculatorPage):
            w.clear_input()

    def _enter_equals(self):
        w = self.stack.currentWidget()
        if isinstance(w, CalculatorPage):
            w.on_equals()


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
        page.focus_mathfield()

    def _apply_close_button(self, tab_index: int):
        btn = QToolButton()
        btn.setIcon(self.close_icon)
        btn.setAutoRaise(True)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip("Tab schließen")
        btn.setFixedSize(15, 15)
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

        w = self.stack.currentWidget()
        if isinstance(w, CalculatorPage):
            w.focus_mathfield()

    def on_tab_changed(self, index: int):
        if 0 <= index < self.stack.count():
            self.stack.setCurrentIndex(index)
            w = self.stack.currentWidget()
            if isinstance(w, CalculatorPage):
                w.focus_mathfield()

    # ---------- Menu / Mode ----------
    def switch_mode(self, mode_name: str):
        w = self.stack.currentWidget()
        if isinstance(w, CalculatorPage):
            w.append_history(f"Modus: {mode_name}", "(Platzhalter)")
            w.focus_mathfield()
        if self.drawer_open:
            self.toggle_drawer()

    # ---------- Settings ----------
    def open_settings(self):
        dlg = SettingsDialog(self.theme, self.settings, parent=self)
        dlg.exec()

    def apply_settings(self):
        # Wenn du später noch UI/Pages aktiv aktualisieren willst, kannst du hier iterieren.
        # Für jetzt reicht es, dass es existiert (damit kein AttributeError kommt).
        pass



    # ---------- Keyboard ----------
    def keyPressEvent(self, event):
        if event.matches(QKeySequence.AddTab):
            self.add_tab()
            return
        super().keyPressEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon("assets/app_icon2.png"))

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
