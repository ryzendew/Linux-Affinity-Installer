"""The installer's own look, reused.

The manager sits beside AffinityOnLinux and drives it, so the two looking like
different applications would misrepresent how they relate. Its widgets and all
three of its themes are therefore used directly -- from the installer itself,
loaded by aol.py, not from a copy.

There used to be a copy: aol_ui.py, 1,410 lines lifted verbatim with
ast.get_source_segment, because the manager could not rely on a checkout being
importable. It is gone. A copy of somebody else's stylesheets can go stale
without a word, and the only thing that would have told you is a screenshot.

The theme methods apply their stylesheet by calling self.setStyleSheet() with a
literal, so there is no getter to call, and constructing the installer's window
to reach one is not an option here -- it starts timers and background work the
moment it exists. They are instead called unbound against a small recorder,
which gets the genuine text with no side effects. Verified byte for byte
against the copy before it was deleted: mattscreative 9392, dark 9207, light
9207, identical in all three.
"""

from __future__ import annotations

import functools
import os

from PyQt6.QtCore import Qt

from . import aol, settings

THEMES = ("mattscreative", "dark", "light")
DISPLAY_NAMES = {"mattscreative": "Mattscreative", "dark": "Dark", "light": "Light"}
DEFAULT_THEME = "mattscreative"
_APPLY_METHODS = {
    "mattscreative": "_apply_mattscreative_theme",
    "dark": "_apply_dark_theme",
    "light": "_apply_light_theme",
}

_stylesheet_cache: dict[str, str] = {}

# The installer's own widgets. Resolved on use rather than at import, so that
# a manager whose installer cannot be found still starts and can say so.
def log_widget_class():
    return aol.module().ZoomableTextEdit


def spinner_class():
    return aol.module().ProgressSpinner


class _Recorder:
    """Stands in for the installer's window while a copied theme method runs.

    Captures the stylesheet instead of applying it, and resolves the sibling
    methods some of them call -- the dialog stylesheets are composed from each
    other -- off the installer's own class. Unbound methods are plain functions,
    so binding one to the recorder works exactly as binding the copy did."""

    def __init__(self):
        self.css = ""

    def setStyleSheet(self, value):
        self.css = value or ""

    def __getattr__(self, name):
        try:
            target = getattr(aol.cls(), name, None)
        except aol.NotAvailable:
            raise AttributeError(name)
        if target is None or not callable(target):
            raise AttributeError(name)
        return functools.partial(target, self)


def _installer_stylesheet(theme: str) -> str:
    """The stylesheet the installer would apply for this theme."""
    try:
        method = getattr(aol.cls(), _APPLY_METHODS.get(theme, ""), None)
    except aol.NotAvailable:
        return ""
    if method is None:
        return ""
    try:
        recorder = _Recorder()
        method(recorder)
        return recorder.css
    except Exception:
        # A theme that will not render is not worth taking the window down for;
        # the fallback below is plain but works.
        return ""


# Widgets the installer has no need for and therefore does not style, written
# against the same palette so a table does not look bolted onto the theme.
# Horizontal scrollbars are here for that reason: the theme styles vertical
# ones only, because nothing in the installer ever scrolls sideways, and a
# table under it otherwise gets the unstyled default -- a white bar.
_SUPPLEMENT = {
    "mattscreative": """
        QScrollBar:horizontal { background-color: #120B1F; height: 10px;
            border-radius: 5px; margin: 0; }
        QScrollBar::handle:horizontal { background-color: #3a2a5e;
            border-radius: 5px; min-width: 30px; }
        QScrollBar::handle:horizontal:hover { background-color: #4a3a6e; }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
        QScrollBar::add-page, QScrollBar::sub-page { background: none; }
    
        QTreeWidget, QTreeView { background-color: #1A1128; color: #E6E0EE;
            border: 1px solid #2E1F47; border-radius: 8px; }
        QTreeWidget::item { padding: 7px 4px; }
        QTreeWidget::item:selected { background-color: #04BEEF; color: #120B1F; }
        QHeaderView::section { background-color: #241736; color: #B8A9C9;
            border: 0; padding: 7px; }
        QLineEdit { background-color: #1A1128; color: #E6E0EE;
            border: 1px solid #2E1F47; border-radius: 6px; padding: 7px; }
        QCheckBox { color: #E6E0EE; }
        QLabel#cautionText { color: #F5A623; }
        QPushButton#actionButton[class="primary"]:disabled {
            background-color: #241736; color: #6A5E7C;
            border: 1px solid #2E1F47; }
    """,
    "dark": """
        QScrollBar:horizontal { background-color: #1a1a1a; height: 10px;
            border-radius: 5px; margin: 0; }
        QScrollBar::handle:horizontal { background-color: #3d3d3d;
            border-radius: 5px; min-width: 30px; }
        QScrollBar::handle:horizontal:hover { background-color: #4d4d4d; }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
        QScrollBar::add-page, QScrollBar::sub-page { background: none; }
    
        QTreeWidget, QTreeView { background-color: #1a1a1a; color: #e6e6e6;
            border: 1px solid #333; border-radius: 8px; }
        QTreeWidget::item { padding: 7px 4px; }
        QTreeWidget::item:selected { background-color: #0078d4; color: #fff; }
        QHeaderView::section { background-color: #262626; color: #cfcfcf;
            border: 0; padding: 7px; }
        QLineEdit { background-color: #1a1a1a; color: #e6e6e6;
            border: 1px solid #3c3c3c; border-radius: 6px; padding: 7px; }
        QLabel#cautionText { color: #E8B339; }
        QPushButton#actionButton[class="primary"]:disabled {
            background-color: #2a2a2a; color: #777;
            border: 1px solid #3a3a3a; }
    """,
    "light": """
        QScrollBar:horizontal { background-color: #f5f5f7; height: 10px;
            border-radius: 5px; margin: 0; }
        QScrollBar::handle:horizontal { background-color: #d0d0d0;
            border-radius: 5px; min-width: 30px; }
        QScrollBar::handle:horizontal:hover { background-color: #c0c0c0; }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
        QScrollBar::add-page, QScrollBar::sub-page { background: none; }
    
        QTreeWidget, QTreeView { background-color: #ffffff; color: #1c1c1c;
            border: 1px solid #d0d0d0; border-radius: 8px; }
        QTreeWidget::item { padding: 7px 4px; }
        QTreeWidget::item:selected { background-color: #0078d4; color: #fff; }
        QHeaderView::section { background-color: #f0f0f0; color: #444;
            border: 0; padding: 7px; }
        QLineEdit { background-color: #ffffff; color: #1c1c1c;
            border: 1px solid #c8c8c8; border-radius: 6px; padding: 7px; }
        QLabel#cautionText { color: #8A5A00; }
        QPushButton#actionButton[class="primary"]:disabled {
            background-color: #e8e8e8; color: #9a9a9a;
            border: 1px solid #d0d0d0; }
    """,
}

FALLBACK_STYLESHEET = """
QWidget { background: #120B1F; color: #E6E0EE;
          font-family: 'Segoe UI', 'Noto Sans', sans-serif; font-size: 13px; }
QPushButton#actionButton, QPushButton { background: #241736; border: 1px solid #2E1F47;
          border-radius: 8px; padding: 9px 15px; color: #E6E0EE; }
QPushButton:hover:enabled { background: #2E1F47; }
QPushButton:disabled { color: #6A5E7C; }
QFrame#buttonCard, QFrame#statusCard { background: #1A1128;
          border: 1px solid #2E1F47; border-radius: 10px; }
QLabel#sectionTitle, QLabel#titleLabel { font-size: 16px; font-weight: 600; }
QLabel#descriptionLabel, QLabel#statusText { color: #B8A9C9; }
QLabel#cautionText { color: #F5A623; }
"""


# Rules that are the same whichever theme is worn.
#
# cardCaption: the line under each of Back up / Clone / Snapshots. As a plain
# descriptionLabel it picked up the installer theme's label background and sat
# on a darker band inside the card, which read as a text field.
#
# QPushButton:disabled: the installer styles only its own named buttons for
# the disabled state, and its themes set a text colour that overrides Qt's
# own greying -- so every plain button in every dialog here looked exactly
# the same switched off as on. Verify on an unfinished backup was "a button
# that does nothing".
_COMMON = """
QLabel#cardCaption { background: transparent; border: none; }
QPushButton:disabled { color: rgba(140, 140, 140, 120); }
"""

# Checkboxes. Under Fusion, the installer's two dark themes draw an unticked
# box in the background colour -- no box at all, just the label -- so the
# tick that arms Remove read as a sentence rather than a control. A visible
# box in every theme, filled with a white tick when ticked. The tick is an SVG
# because a stylesheet can only draw an image from a file; it is written to
# the cache, and without it a ticked box is still unmistakably filled.
_CHECK_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" '
    'viewBox="0 0 16 16"><path d="M3.2 8.4l3 3 6.6-7" fill="none" '
    'stroke="#FFFFFF" stroke-width="2.2" stroke-linecap="round" '
    'stroke-linejoin="round"/></svg>')


def _check_image() -> str:
    try:
        base = os.environ.get("XDG_CACHE_HOME", "").strip() or \
            os.path.join(os.path.expanduser("~"), ".cache")
        path = os.path.join(base, "AffinityOnLinux", "manager-ui", "check.svg")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path) as f:
                current = f.read()
        except OSError:
            current = ""
        if current != _CHECK_SVG:
            with open(path, "w") as f:
                f.write(_CHECK_SVG)
        return path
    except OSError:
        return ""


def _checkbox_rules() -> str:
    image = _check_image()
    tick = f' image: url("{image}");' if image else ""
    # The same box for the tick column of a list -- the removal list, Clean,
    # Copy settings' drive letters -- which a view draws itself, not as a
    # QCheckBox, and which was just as invisible.
    rules = []
    for widget in ("QCheckBox", "QTreeView", "QListView"):
        rules.append(f"""
{widget}::indicator {{ width: 16px; height: 16px; border-radius: 3px;
                       border: 2px solid rgb(150, 150, 165);
                       background: transparent; }}
{widget}::indicator:hover {{ border-color: rgb(200, 200, 215); }}
{widget}::indicator:checked {{ background: #7C5CD6; border-color: #7C5CD6;{tick} }}
{widget}::indicator:indeterminate {{ background: rgba(124, 92, 214, 0.45);
                                     border-color: #7C5CD6; }}
{widget}::indicator:disabled {{ border-color: rgba(140, 140, 140, 90); }}
{widget}::indicator:checked:disabled {{ background: rgba(124, 92, 214, 0.4);
                                        border-color: rgba(124, 92, 214, 0.4); }}""")
    return "\nQCheckBox { spacing: 8px; }" + "".join(rules) + "\n"


def current_theme() -> str:
    theme = settings.get("theme", DEFAULT_THEME)
    return theme if theme in THEMES else DEFAULT_THEME


def set_theme(theme: str) -> None:
    if theme in THEMES:
        settings.set("theme", theme)


def next_theme(theme: str | None = None) -> str:
    theme = theme or current_theme()
    return THEMES[(THEMES.index(theme) + 1) % len(THEMES)]


def stylesheet(theme: str | None = None) -> str:
    theme = theme or current_theme()
    if theme not in _stylesheet_cache:
        base = _installer_stylesheet(theme) or FALLBACK_STYLESHEET
        _stylesheet_cache[theme] = (base + _SUPPLEMENT.get(theme, "") + _COMMON
                                    + _checkbox_rules())
    return _stylesheet_cache[theme]


def apply(widget, theme: str | None = None) -> None:
    widget.setStyleSheet(stylesheet(theme))
    widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
