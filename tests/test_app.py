"""Testes de compatibilidade com a infraestrutura gráfica do Tkinter."""
import tkinter as tk

from app import Application

def test_does_not_shadow_tkinter_option_encoder():
    """Regressão: Tk.configure precisa de Misc._options(self, options)."""
    assert Application._options is tk.Misc._options

def test_app_has_distinct_export_settings_method():
    assert callable(Application._export_options)
