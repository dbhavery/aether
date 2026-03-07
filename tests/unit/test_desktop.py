"""Module 07 tests — verify desktop theme and chat view logic."""

from src.desktop.theme import (
    ACCENT,
    BG,
    BG_VOID,
    BORDER,
    CARDS,
    USER_COLOR,
    EDGE_BRIGHT,
    EDGE_DARK,
    EDGE_FAINT,
    EDGE_HIGHLIGHT,
    EDGE_MID,
    EDGE_SHADOW,
    EDGE_SUBTLE,
    INPUTS,
    ASSISTANT_COLOR,
    R_SM,
    R_XL,
    TEXT_FAINT,
    TEXT_GHOST,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    card_qss,
    input_qss,
    mode_button_qss,
    send_button_qss,
)


class TestTheme:
    def test_color_constants_are_hex(self):
        for color in [BG, CARDS, INPUTS, ACCENT, ASSISTANT_COLOR, USER_COLOR]:
            assert color.startswith("#")
            assert len(color) == 7

    def test_legacy_aliases_point_to_new_tokens(self):
        """Legacy aliases map to the new design-system depth tokens."""
        assert BG == BG_VOID  # v13: "#282828"
        assert BG == "#282828"
        assert CARDS == "#343434"  # BG_RAISED
        assert INPUTS == "#3A3A3A"  # BG_ELEMENT
        assert BORDER == "#4E4E4E"  # EDGE_MID

    def test_legacy_edge_aliases(self):
        """EDGE_HIGHLIGHT and EDGE_SHADOW map to EDGE_BRIGHT and EDGE_DARK."""
        assert EDGE_HIGHLIGHT == EDGE_BRIGHT  # "#585858"
        assert EDGE_HIGHLIGHT == "#585858"
        assert EDGE_SHADOW == EDGE_DARK  # "#141414"
        assert EDGE_SHADOW == "#141414"

    def test_accent_colors_v13(self):
        assert ACCENT == "#1976D2"
        assert ASSISTANT_COLOR == "#690069"
        assert USER_COLOR == "#007058"

    def test_neumorphic_depth_tokens_exist(self):
        from src.desktop.theme import (
            BG_ACCENT_BG,
            BG_DEEP,
            BG_ELEMENT,
            BG_HIGHLIGHT,
            BG_PIT,
            BG_RAISED,
            BG_RECESSED,
            BG_SURFACE,
            BG_VOID,
        )

        assert BG_PIT == "#0A0A0A"
        assert BG_VOID == "#282828"
        assert BG_RECESSED == "#141414"
        assert BG_DEEP == "#1A1A1A"
        assert BG_SURFACE == "#2E2E2E"
        assert BG_RAISED == "#343434"
        assert BG_ELEMENT == "#3A3A3A"
        assert BG_HIGHLIGHT == "#444444"
        assert BG_ACCENT_BG == "#4E4E4E"

    def test_edge_tokens_full_set(self):
        assert EDGE_BRIGHT == "#585858"
        assert EDGE_MID == "#4E4E4E"
        assert EDGE_SUBTLE == "#4E4E4E"
        assert EDGE_FAINT == "#343434"
        assert EDGE_DARK == "#141414"
        from src.desktop.theme import EDGE_DARKER

        assert EDGE_DARKER == "#0A0A0A"

    def test_text_hierarchy_five_levels(self):
        assert TEXT_PRIMARY == "#FFFFFF"
        assert TEXT_SECONDARY == "#B0B0B8"
        assert TEXT_MUTED == "#888888"
        assert TEXT_FAINT == "#666666"
        assert TEXT_GHOST == "#444444"

    def test_border_radius_constants(self):
        from src.desktop.theme import R_FULL, R_LG, R_MD

        assert R_XL == 18
        assert R_LG == 14
        assert R_MD == 10
        assert R_SM == 8
        assert R_FULL == 999

    def test_gradient_stop_tokens(self):
        from src.desktop.theme import (
            GS_DEEP,
            GS_ELEMENT,
            GS_HIGHLIGHT,
            GS_PIT,
            GS_RAISED,
            GS_RECESSED,
            GS_SURFACE,
            GS_VOID,
        )

        assert GS_PIT == "#0C0C0C"
        assert GS_VOID == "#2A2A2A"
        assert GS_RECESSED == "#161616"
        assert GS_DEEP == "#1C1C1C"
        assert GS_SURFACE == "#303030"
        assert GS_RAISED == "#363636"
        assert GS_ELEMENT == "#3E3E3E"
        assert GS_HIGHLIGHT == "#464646"

    def test_status_colors_exist(self):
        from src.desktop.theme import COLOR_ERROR, COLOR_SUCCESS, COLOR_WARNING

        assert COLOR_ERROR == "#EF4444"
        assert COLOR_SUCCESS == "#22C55E"
        assert COLOR_WARNING == "#EAB308"

    def test_input_qss_has_recessed_well(self):
        """Input QSS should use GRAD_INPUT background and recessed bezel."""
        qss = input_qss()
        assert "QLineEdit" in qss
        assert EDGE_DARK in qss  # recessed top border
        assert EDGE_SUBTLE in qss  # recessed bottom border
        assert f"border-radius: {R_SM}px" in qss

    def test_send_button_qss_has_gradient(self):
        """Send button QSS should use gradient background."""
        qss = send_button_qss()
        assert "QPushButton" in qss
        assert "qlineargradient" in qss
        assert f"border-radius: {R_SM}px" in qss

    def test_mode_button_qss_active_and_inactive(self):
        active = mode_button_qss(active=True)
        inactive = mode_button_qss(active=False)
        assert "QPushButton" in active
        assert "QPushButton" in inactive
        assert active != inactive
        assert f"border-radius: {R_SM}px" in active
        assert f"border-radius: {R_SM}px" in inactive

    def test_card_qss_has_gradient_and_bezel(self):
        qss = card_qss()
        assert "QFrame" in qss
        assert "qlineargradient" in qss
        assert EDGE_BRIGHT in qss  # raised top
        assert EDGE_MID in qss  # raised left
        assert EDGE_FAINT in qss  # raised bottom/right
        assert f"border-radius: {R_XL}px" in qss

    def test_global_qss_has_montserrat_font(self):
        from src.desktop.theme import GLOBAL_QSS

        assert '"Montserrat"' in GLOBAL_QSS
        assert '"Segoe UI"' in GLOBAL_QSS
        assert "font-size: 15px" in GLOBAL_QSS

    def test_gradient_recipes_exist(self):
        from src.desktop.theme import (
            GRAD_BAR,
            GRAD_BTN_PRIMARY,
            GRAD_ELEMENT,
            GRAD_GHOST,
            GRAD_INPUT,
            GRAD_RAISED,
            GRAD_RECESSED,
        )

        for grad in [GRAD_RAISED, GRAD_RECESSED, GRAD_INPUT, GRAD_ELEMENT, GRAD_BTN_PRIMARY, GRAD_GHOST, GRAD_BAR]:
            assert grad.startswith("qlineargradient(")
            assert "x1:0, y1:0, x2:1, y2:1" in grad
