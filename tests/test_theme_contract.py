"""驗證深淺模式設定及 UI 接線契約。"""
import os
import ast

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_FILE = os.path.join(PROJECT_ROOT, "main.pyw")
with open(MAIN_FILE, "r", encoding="utf-8") as f:
    SOURCE = f.read()


def test_dark_theme_is_the_legacy_default():
    assert '"theme": "dark"' in SOURCE


def test_dark_and_light_palettes_and_validation_exist():
    assert '"dark": {' in SOURCE
    assert '"light": {' in SOURCE
    assert 'theme not in THEME_PALETTES' in SOURCE
    assert 'isinstance(value, str)' in SOURCE


def test_config_updates_preserve_other_preferences():
    assert "current_config.update(config)" in SOURCE
    assert 'save_config({"theme": theme})' in SOURCE
    assert 'save_config({"copy_to_clipboard": self.copy_to_clipboard})' in SOURCE


def test_theme_updates_main_and_open_dialogs():
    assert "def apply_theme(self, theme):" in SOURCE
    assert "self.settings_dialog" in SOURCE
    assert "self.help_dialog" in SOURCE
    assert "self._draw_mic_button" in SOURCE


def test_settings_has_two_theme_choices():
    assert 'text="深色"' in SOURCE
    assert 'text="淺色"' in SOURCE
    assert "self.app.set_theme" in SOURCE


def test_set_theme_rejects_unhashable_values():
    tree = ast.parse(SOURCE)
    app_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "VoiceInputApp")
    setter = next(node for node in app_class.body if isinstance(node, ast.FunctionDef) and node.name == "set_theme")
    namespace = {"THEME_PALETTES": {"dark": {}, "light": {}}, "save_config": lambda config: None}
    exec(compile(ast.Module(body=[setter], type_ignores=[]), MAIN_FILE, "exec"), namespace)

    assert namespace["set_theme"](object(), []) is False


def test_card_ui_tracks_active_mic_and_registers_theme_roles():
    assert "self.theme = app.theme" in SOURCE
    assert "self._theme_bindings = {}" in SOURCE
    assert "self.app.ui = self" in SOURCE
    assert "def _register_theme_widget(self, window, widget, bg_role=None, fg_role=None):" in SOURCE


def test_theme_apply_updates_registered_widgets_and_mic_without_resetting_active_state():
    assert "def apply_theme(self, theme):" in SOURCE
    assert "self.root.after(0," in SOURCE
    assert "_theme_bindings" in SOURCE
    assert "active=self._mic_active" in SOURCE


def test_queue_uses_theme_roles_instead_of_stale_color_values():
    tree = ast.parse(SOURCE)
    messages = [node.args[0] for node in ast.walk(tree)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "put" and node.args
                and isinstance(node.args[0], ast.Tuple) and len(node.args[0].elts) == 3]
    assert messages
    assert all(isinstance(message.elts[2], ast.Constant) and message.elts[2].value
               in {"accent", "muted", "success", "warning", "error"} for message in messages)
    assert 'palette[color_role]' in SOURCE


def test_rounded_button_hover_resolves_current_palette():
    assert "def _hover_config(" in SOURCE
    assert "palette = self.palette" in SOURCE
    assert "<Enter>" in SOURCE and "<Leave>" in SOURCE
