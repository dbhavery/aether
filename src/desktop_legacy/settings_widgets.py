"""Reusable widget factory functions for the settings UI — neumorphic theme."""

from PySide6.QtCore import Qt, QTime
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSlider,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
)

from src.desktop.theme import (
    ACCENT,
    BG_RECESSED,
    BG_VOID,
    EDGE_BRIGHT,
    EDGE_DARK,
    EDGE_FAINT,
    EDGE_MID,
    EDGE_SUBTLE,
    GRAD_BTN_PRIMARY,
    GRAD_ELEMENT,
    GRAD_GHOST,
    GRAD_INPUT,
    GRAD_RAISED,
    R_SM,
    R_XL,
    TEXT_FAINT,
    TEXT_MUTED,
    TEXT_PRIMARY,
)

COLORS = {
    "bg": BG_VOID,
    "card": "#232323",  # BG_RAISED
    "input": "#2b2b2b",  # BG_ELEMENT
    "accent": ACCENT,
    "text": TEXT_PRIMARY,
    "text_dim": TEXT_MUTED,
    "border": EDGE_BRIGHT,
    "border_dark": EDGE_DARK,
}


def format_slider_value(raw: int, decimals: int) -> str:
    """Format a slider int value to the display string."""
    if decimals == 0:
        return str(raw)
    scale = 10**decimals
    return f"{raw / scale:.{decimals}f}"


def create_section(parent_layout: QVBoxLayout, title: str) -> QGroupBox:
    """Create a neumorphic raised section group box and add it to the parent layout.

    Uses GRAD_RAISED background, 2px/1px bezel, R_XL radius.
    Title is 14px (fs_section), uppercase, semibold, letter-spacing 2px.
    """
    group = QGroupBox(title)
    group.setStyleSheet(f"""
        QGroupBox {{
            background: {GRAD_RAISED};
            border-top: 2px solid {EDGE_BRIGHT};
            border-left: 2px solid {EDGE_MID};
            border-bottom: 1px solid {EDGE_FAINT};
            border-right: 1px solid {EDGE_FAINT};
            border-radius: {R_XL}px;
            margin-top: 12px;
            padding-top: 24px;
            font-weight: 600;
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 2px;
            color: {COLORS["text"]};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 6px;
        }}
    """)
    parent_layout.addWidget(group)
    return group


def labeled_slider(
    parent_layout: QVBoxLayout,
    label: str,
    min_val: int,
    max_val: int,
    default: int,
    decimals: int = 0,
) -> QSlider:
    """Create a labeled horizontal slider with a live value display."""
    row = QHBoxLayout()
    lbl = QLabel(label)
    lbl.setStyleSheet(f"color: {COLORS['text']}; background: transparent;")
    lbl.setFixedWidth(200)
    row.addWidget(lbl)

    slider = QSlider(Qt.Orientation.Horizontal)
    slider.setMinimum(min_val)
    slider.setMaximum(max_val)
    slider.setValue(default)
    row.addWidget(slider, 1)

    val_label = QLabel(format_slider_value(default, decimals))
    val_label.setFixedWidth(50)
    val_label.setAlignment(Qt.AlignmentFlag.AlignRight)
    val_label.setStyleSheet(f"color: {TEXT_MUTED}; background: transparent;")
    row.addWidget(val_label)

    slider.setProperty("decimals", decimals)
    slider.setProperty("value_label", val_label)
    slider.valueChanged.connect(lambda v: val_label.setText(format_slider_value(v, decimals)))

    parent_layout.addLayout(row)
    return slider


def labeled_spinbox(
    parent_layout: QVBoxLayout,
    label: str,
    min_val: int,
    max_val: int,
    default: int,
) -> QSpinBox:
    """Create a labeled spin box with recessed neumorphic styling."""
    row = QHBoxLayout()
    lbl = QLabel(label)
    lbl.setStyleSheet(f"color: {COLORS['text']}; background: transparent;")
    lbl.setFixedWidth(200)
    row.addWidget(lbl)

    spin = QSpinBox()
    spin.setMinimum(min_val)
    spin.setMaximum(max_val)
    spin.setValue(default)
    spin.setStyleSheet(
        f"QSpinBox {{ background: {GRAD_INPUT}; color: {COLORS['text']}; "
        f"border-top: 1px solid {EDGE_DARK}; border-left: 1px solid {EDGE_DARK}; "
        f"border-bottom: 1px solid {EDGE_SUBTLE}; border-right: 1px solid {EDGE_SUBTLE}; "
        f"border-radius: {R_SM}px; padding: 4px; }}"
    )
    row.addWidget(spin, 1)

    parent_layout.addLayout(row)
    return spin


def labeled_line_edit(parent_layout: QVBoxLayout, label: str, default: str) -> QLineEdit:
    """Create a labeled text input with recessed neumorphic styling."""
    row = QHBoxLayout()
    lbl = QLabel(label)
    lbl.setStyleSheet(f"color: {COLORS['text']}; background: transparent;")
    lbl.setFixedWidth(200)
    row.addWidget(lbl)

    edit = QLineEdit(default)
    edit.setStyleSheet(
        f"QLineEdit {{ background: {GRAD_INPUT}; color: {COLORS['text']}; "
        f"border-top: 1px solid {EDGE_DARK}; border-left: 1px solid {EDGE_DARK}; "
        f"border-bottom: 1px solid {EDGE_SUBTLE}; border-right: 1px solid {EDGE_SUBTLE}; "
        f"border-radius: {R_SM}px; padding: 4px; }}"
    )
    row.addWidget(edit, 1)

    parent_layout.addLayout(row)
    return edit


def labeled_checkbox(parent_layout: QVBoxLayout, label: str, default: bool) -> QCheckBox:
    """Create a labeled checkbox."""
    cb = QCheckBox(label)
    cb.setChecked(default)
    cb.setStyleSheet(f"QCheckBox {{ color: {COLORS['text']}; background: transparent; spacing: 8px; }}")
    parent_layout.addWidget(cb)
    return cb


def labeled_combo(parent_layout: QVBoxLayout, label: str, items: list[str]) -> QComboBox:
    """Create a labeled combo box with recessed neumorphic styling."""
    row = QHBoxLayout()
    lbl = QLabel(label)
    lbl.setStyleSheet(f"color: {COLORS['text']}; background: transparent;")
    lbl.setFixedWidth(200)
    row.addWidget(lbl)

    combo = QComboBox()
    combo.addItems(items)
    combo.setStyleSheet(
        f"QComboBox {{ background: {GRAD_INPUT}; color: {COLORS['text']}; "
        f"border-top: 1px solid {EDGE_DARK}; border-left: 1px solid {EDGE_DARK}; "
        f"border-bottom: 1px solid {EDGE_SUBTLE}; border-right: 1px solid {EDGE_SUBTLE}; "
        f"border-radius: {R_SM}px; padding: 4px; }}"
    )
    row.addWidget(combo, 1)

    parent_layout.addLayout(row)
    return combo


def labeled_time_edit(parent_layout: QVBoxLayout, label: str, default: QTime) -> QTimeEdit:
    """Create a labeled time picker with recessed neumorphic styling."""
    row = QHBoxLayout()
    lbl = QLabel(label)
    lbl.setStyleSheet(f"color: {COLORS['text']}; background: transparent;")
    lbl.setFixedWidth(200)
    row.addWidget(lbl)

    te = QTimeEdit(default)
    te.setDisplayFormat("hh:mm AP")
    te.setStyleSheet(
        f"QTimeEdit {{ background: {GRAD_INPUT}; color: {COLORS['text']}; "
        f"border-top: 1px solid {EDGE_DARK}; border-left: 1px solid {EDGE_DARK}; "
        f"border-bottom: 1px solid {EDGE_SUBTLE}; border-right: 1px solid {EDGE_SUBTLE}; "
        f"border-radius: {R_SM}px; padding: 4px; }}"
    )
    row.addWidget(te, 1)

    parent_layout.addLayout(row)
    return te


def dialog_qss() -> str:
    """Return the main settings dialog stylesheet — neumorphic depth."""
    return f"""
        QDialog {{
            background-color: {BG_VOID};
            color: {COLORS["text"]};
        }}
        QLabel {{
            background: transparent;
        }}
        QSlider::groove:horizontal {{
            height: 6px;
            background: {BG_RECESSED};
            border-top: 1px solid {EDGE_DARK};
            border-left: 1px solid {EDGE_DARK};
            border-bottom: 1px solid {EDGE_SUBTLE};
            border-right: 1px solid {EDGE_SUBTLE};
            border-radius: 3px;
        }}
        QSlider::handle:horizontal {{
            background: {GRAD_ELEMENT};
            width: 14px;
            height: 14px;
            margin: -4px 0;
            border-top: 2px solid {EDGE_BRIGHT};
            border-left: 2px solid {EDGE_MID};
            border-bottom: 1px solid {EDGE_FAINT};
            border-right: 1px solid {EDGE_FAINT};
            border-radius: 7px;
        }}
    """


def button_qss(primary: bool = True) -> str:
    """Return the push button stylesheet — neumorphic raised."""
    bg = GRAD_BTN_PRIMARY if primary else GRAD_GHOST
    hover_bg = GRAD_ELEMENT
    return f"""
        QPushButton {{
            background: {bg};
            color: {COLORS["text"]};
            border-top: 2px solid {EDGE_BRIGHT};
            border-left: 2px solid {EDGE_MID};
            border-bottom: 1px solid {EDGE_FAINT};
            border-right: 1px solid {EDGE_FAINT};
            border-radius: {R_SM}px;
            padding: 8px 24px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background: {hover_bg};
        }}
        QPushButton:pressed {{
            border-top: 1px solid {EDGE_DARK};
            border-left: 1px solid {EDGE_DARK};
            border-bottom: 2px solid {EDGE_BRIGHT};
            border-right: 2px solid {EDGE_MID};
        }}
        QPushButton:disabled {{
            background: {COLORS["input"]};
            color: {TEXT_FAINT};
            border: 1px solid {EDGE_DARK};
        }}
    """
