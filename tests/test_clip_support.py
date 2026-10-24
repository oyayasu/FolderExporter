"""Simulação da API pública de clipparse. Não depende de arquivos .clip reais."""
from pathlib import Path

import pytest
from PIL import Image

from clip_support import ClipProject, render_folder, top_groups
from engine import Options, list_top_level_groups, export_groups

class Layer:
    def __init__(self, index, name, is_group=False, visible=True, color=(40, 90, 150, 255)):
        self.index = index
        self.name = name
        self.is_group = is_group
        self.visible = visible
        self.color = color
        self.composite_raw = 0
        self.clipping = 0
        self.is_filter = False
        self.has_mask = False
        self.opacity = 255
        self.width = 0 if is_group else 12
        self.height = 0 if is_group else 9
        self.left = 2
        self.top = 3

class Reader:
    width = 20
    height = 15
    def __init__(self):
        # A API de clipparse expõe layers e roots de baixo para cima.
        self.layers = [
            Layer(0, "desenho fundo", color=(255, 0, 0, 255)),
            Layer(1, "pasta inferior", is_group=True, visible=False),
            Layer(2, "desenho topo", color=(0, 0, 255, 255)),
            Layer(3, "pasta superior", is_group=True, visible=False),
        ]
        self.roots = [1, 3]
        self.children_by_id = {1: [0], 3: [2]}
    def children(self, index):
        return self.children_by_id.get(index, [])
    def layer_image(self, index, mode="masked"):
        assert mode == "masked"
        image = Image.new("RGBA", (12, 9), self.layers[index].color)
        try:
            return image.tobytes("raw", "BGRA")
        finally:
            image.close()

def project():
    return ClipProject(Reader(), Path("original.clip"), 20, 15)

def test_visual_order_clip_projects():
    p = project()
    assert [name for _, name, _ in top_groups(p)] == ["pasta superior", "pasta inferior"]
    folders = list_top_level_groups(p)
    assert [item.name for item in folders] == ["pasta superior", "pasta inferior"]
    assert folders[0].layer == 3

def test_clip_exports_hidden_top_groups_read_only(tmp_path):
    p = project()
    selected = list_top_level_groups(p)
    original_vis = [item.visible for item in p.file.layers]
    result = export_groups(p, selected, tmp_path, Options(naming="number"))
    assert not result.failures
    assert [path.name for path in result.created] == ["001.png", "002.png"]
    with Image.open(tmp_path / "001.png") as im:
        assert im.getpixel((3, 4)) == (0, 0, 255, 255)
        assert im.getpixel((0, 0))[3] == 0
    with Image.open(tmp_path / "002.png") as im:
        assert im.getpixel((3, 4)) == (255, 0, 0, 255)
    assert [item.visible for item in p.file.layers] == original_vis

def test_unsupported_clip_effect_fails_instead_of_wrong_png(tmp_path):
    p = project()
    p.file.layers[2].composite_raw = 2
    result = export_groups(p, list_top_level_groups(p)[:1], tmp_path)
    assert not result.created
    assert result.failures
    assert not list(tmp_path.glob("*.png"))
