"""Design system — Aether dark neumorphic theme.

Token-accurate port of the Aether Design System master spec.
145-degree lighting angle throughout (top-left to bottom-right diagonal).

QSS portability notes:
- CSS multi-layer box-shadow -> darker bg + border trick
- CSS ::before/::after -> not available, skipped
- CSS inset shadows -> darker background + inverted border colors
- CSS linear-gradient -> qlineargradient(x1:0, y1:0, x2:1, y2:1, ...) for 145deg
- CSS rgba() -> hex approximations for edge tokens (avoids Qt bugs)
"""

# ── Background Depth Scale (9 levels) ──────────────────────────────
# v13 palette — deeper, warmer tones
BG_PIT = "#0A0A0A"  # Deepest recess (v13 input pattern)
BG_VOID = "#282828"  # App background (v13 darkest card bg)
BG_RECESSED = "#141414"  # Input backgrounds, wells (v13 recessed pattern)
BG_DEEP = "#1A1A1A"  # Secondary surfaces / deep wells (v13)
BG_SURFACE = "#2E2E2E"  # Card body, primary surface (v13 mid gradient)
BG_RAISED = "#343434"  # Elevated areas (v13 gradient stop)
BG_ELEMENT = "#3A3A3A"  # Buttons, interactive (v13 page bg top)
BG_HIGHLIGHT = "#444444"  # Brightest raised surface
BG_ACCENT_BG = "#4E4E4E"  # Pill/badge peaks

# ── Gradient Stop Tokens ───────────────────────────────────────────
GS_PIT = "#0C0C0C"
GS_VOID = "#2A2A2A"
GS_RECESSED = "#161616"
GS_DEEP = "#1C1C1C"
GS_SURFACE = "#303030"
GS_RAISED = "#363636"
GS_ELEMENT = "#3E3E3E"
GS_HIGHLIGHT = "#464646"

# ── Edge Tokens (hex approximations for QSS compatibility) ─────────
EDGE_BRIGHT = "#585858"  # Top edge of raised — light catches here
EDGE_MID = "#4E4E4E"  # Left edge of raised
EDGE_SUBTLE = "#4E4E4E"  # Recessed borders, visible outline
EDGE_FAINT = "#343434"  # Subtle separators
EDGE_DARK = "#141414"  # Top of recessed — shadow falls here
EDGE_DARKER = "#0A0A0A"  # Deep recess top

# ── Legacy Aliases (backwards compatibility) ───────────────────────
BG = BG_VOID
CARDS = BG_RAISED
INPUTS = BG_ELEMENT
BORDER = EDGE_MID

# Legacy edge aliases used by existing imports
EDGE_HIGHLIGHT = EDGE_BRIGHT
EDGE_SHADOW = EDGE_DARK

# ── Text Hierarchy (5 levels) ──────────────────────────────────────
TEXT_PRIMARY = "#FFFFFF"  # v13 pure white
TEXT_SECONDARY = "#B0B0B8"  # v13 light gray with slight blue
TEXT_MUTED = "#888888"
TEXT_FAINT = "#666666"
TEXT_GHOST = "#444444"

# ── Project Accent Colors ─────────────────────────────────────────
ACCENT = "#1976D2"  # v13 blue
ASSISTANT_COLOR = "#690069"  # v13 deep purple
USER_COLOR = "#007058"  # v13 teal
COLOR_ERROR = "#EF4444"  # v13 red
COLOR_SUCCESS = "#22C55E"  # v13 green
COLOR_WARNING = "#EAB308"  # v13 yellow

# ── Border Radius ─────────────────────────────────────────────────
R_XL = 18  # Cards, modals
R_LG = 14
R_MD = 10  # Wells, dropdowns
R_SM = 8  # Buttons, inputs
R_FULL = 999  # Pills


# ── Gradient Helpers ───────────────────────────────────────────────
def _grad145(*stops: tuple[float, str]) -> str:
    """Build QSS qlineargradient at 145deg with multiple stops.

    The 145deg CSS angle maps approximately to QSS x1:0, y1:0, x2:1, y2:1
    (top-left to bottom-right diagonal).
    """
    stop_str = ", ".join(f"stop:{pos} {color}" for pos, color in stops)
    return f"qlineargradient(x1:0, y1:0, x2:1, y2:1, {stop_str})"


# ── Gradient Recipes ───────────────────────────────────────────────
GRAD_RAISED = _grad145((0, BG_ELEMENT), (0.15, BG_RAISED), (0.7, BG_SURFACE), (1, GS_DEEP))
GRAD_RECESSED = _grad145((0, BG_VOID), (0.3, GS_VOID), (0.6, GS_RECESSED), (1, BG_DEEP))
GRAD_INPUT = _grad145((0, GS_PIT), (0.3, BG_RECESSED), (0.6, GS_RECESSED), (1, BG_DEEP))
GRAD_ELEMENT = _grad145((0, BG_HIGHLIGHT), (0.5, BG_ELEMENT), (1, GS_SURFACE))
GRAD_BTN_PRIMARY = _grad145((0, GS_HIGHLIGHT), (0.2, BG_HIGHLIGHT), (0.5, GS_ELEMENT), (0.8, BG_RAISED), (1, GS_RAISED))
GRAD_GHOST = _grad145((0, GS_RAISED), (0.5, GS_SURFACE), (1, GS_SURFACE))
GRAD_BAR = _grad145((0, BG_RAISED), (0.5, BG_SURFACE), (1, GS_DEEP))


# ── Global QSS ────────────────────────────────────────────────────
GLOBAL_QSS = f"""
QWidget {{
    background-color: {BG_VOID};
    color: {TEXT_PRIMARY};
    font-family: "Montserrat", "Segoe UI", sans-serif;
    font-size: 15px;
}}
QScrollBar:vertical {{
    background: {BG_VOID};
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {EDGE_BRIGHT};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
"""


# ── QSS Helper Functions ──────────────────────────────────────────
def input_qss() -> str:
    """Recessed well effect — GRAD_INPUT bg, inset bezel via border styling."""
    return f"""
    QLineEdit {{
        background: {GRAD_INPUT};
        color: {TEXT_PRIMARY};
        border-top: 1px solid {EDGE_DARK};
        border-left: 1px solid {EDGE_DARK};
        border-bottom: 1px solid {EDGE_SUBTLE};
        border-right: 1px solid {EDGE_SUBTLE};
        border-radius: {R_SM}px;
        padding: 10px 14px;
        font-size: 15px;
    }}
    QLineEdit:focus {{
        border-top: 1px solid {ACCENT};
        border-left: 1px solid {ACCENT};
        border-bottom: 1px solid {EDGE_SUBTLE};
        border-right: 1px solid {EDGE_SUBTLE};
    }}
    """


def send_button_qss() -> str:
    """Raised neumorphic button with accent color gradient."""
    return f"""
    QPushButton {{
        background: {_grad145((0, "#2196F3"), (0.5, "#1976D2"), (1, "#1565C0"))};
        color: {TEXT_PRIMARY};
        border-top: 2px solid #42A5F5;
        border-left: 2px solid #42A5F5;
        border-bottom: 1px solid #0D47A1;
        border-right: 1px solid #0D47A1;
        border-radius: {R_SM}px;
        padding: 10px 20px;
        font-size: 15px;
        font-weight: bold;
    }}
    QPushButton:hover {{
        background: {_grad145((0, "#42A5F5"), (0.5, "#2196F3"), (1, "#1976D2"))};
    }}
    QPushButton:pressed {{
        background: {_grad145((0, "#0D47A1"), (0.5, "#1565C0"), (1, "#1976D2"))};
        border-top: 1px solid #0D47A1;
        border-left: 1px solid #0D47A1;
        border-bottom: 2px solid #42A5F5;
        border-right: 2px solid #42A5F5;
    }}
    QPushButton:disabled {{
        background: {BG_ELEMENT};
        color: {TEXT_MUTED};
        border: 1px solid {EDGE_DARK};
    }}
    """


def mode_button_qss(active: bool = False) -> str:
    """Mode selector button — pressed when active, raised when inactive."""
    if active:
        return f"""
        QPushButton {{
            background: {_grad145((0, "#1565C0"), (0.5, "#1976D2"), (1, "#2196F3"))};
            color: {TEXT_PRIMARY};
            border-top: 1px solid {EDGE_DARK};
            border-left: 1px solid {EDGE_DARK};
            border-bottom: 2px solid #42A5F5;
            border-right: 2px solid #42A5F5;
            border-radius: {R_SM}px;
            padding: 6px 12px;
            font-size: 13px;
            font-weight: bold;
        }}
        """
    return f"""
    QPushButton {{
        background: {GRAD_ELEMENT};
        color: {TEXT_SECONDARY};
        border-top: 2px solid {EDGE_BRIGHT};
        border-left: 2px solid {EDGE_MID};
        border-bottom: 1px solid {EDGE_FAINT};
        border-right: 1px solid {EDGE_FAINT};
        border-radius: {R_SM}px;
        padding: 6px 12px;
        font-size: 13px;
    }}
    QPushButton:hover {{
        background: {GRAD_BTN_PRIMARY};
        color: {TEXT_PRIMARY};
    }}
    """


def card_qss() -> str:
    """Raised card with GRAD_RAISED background and 2px/1px bezel borders."""
    return f"""
    QFrame {{
        background: {GRAD_RAISED};
        border-top: 2px solid {EDGE_BRIGHT};
        border-left: 2px solid {EDGE_MID};
        border-bottom: 1px solid {EDGE_FAINT};
        border-right: 1px solid {EDGE_FAINT};
        border-radius: {R_XL}px;
    }}
    """
