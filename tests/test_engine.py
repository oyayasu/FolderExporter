from pathlib import Path
from threading import Event

from PIL import Image, ImageDraw
import pytest

from engine import (
    Folder, Options, build_export_plan, export_groups, list_top_level_groups, safe_stem
)

class Group:
    kind = "group"
    parent = None
    def __init__(self, name, color=(200, 30, 70, 255), visible=True, fail=False):
        self.name = name
        self.color = color
        self.visible = visible
        self.fail = fail

class PSD(list):
    width = 40
    height = 30
    def composite(self, viewport=None, layer_filter=None, alpha=None, color=None, ignore_preview=False):
        assert viewport == (0, 0, 40, 30)
        assert alpha == 0.0
        assert ignore_preview
        selected = [layer for layer in self if layer_filter(layer)]
        assert len(selected) == 1
        group = selected[0]
        assert group.visible
        if group.fail:
            raise RuntimeError("Falha simulada")
        image = Image.new("RGBA", (40, 30), (0, 0, 0, 0))
        ImageDraw.Draw(image).rectangle((4, 5, 13, 15), fill=group.color)
        return image

def test_valid_filenames():
    assert safe_stem("work #2") == "work #2"
    assert safe_stem("CON") == "_CON"
    assert safe_stem("a/b:c?") == "a_b_c_"
    assert safe_stem("  ") == "sem_nome"
    assert safe_stem("日本語") == "日本語"

def test_detect_top_groups_even_hidden():
    groups = list_top_level_groups(PSD([Group("A"), Group("B", visible=False)]))
    assert len(groups) == 2
    assert groups[1].visible is False

def test_duplicate_folders_and_existing_file(tmp_path):
    groups = list_top_level_groups(PSD([Group("work"), Group("work"), Group("work")]))
    plan = build_export_plan(groups, tmp_path, Options())
    assert [p.name for _, p in plan] == ["work.png", "work - 2.png", "work - 3.png"]
    (tmp_path / "work.png").write_bytes(b"original")
    plan = build_export_plan(groups, tmp_path, Options())
    assert [p.name for _, p in plan] == ["work - 2.png", "work - 3.png", "work - 4.png"]

@pytest.mark.parametrize("format,ext", [("PNG", ".png"), ("WEBP", ".webp"), ("TIFF", ".tif"), ("JPEG", ".jpg")])
def test_formats_and_transparency(tmp_path, format, ext):
    psd = PSD([Group("art")])
    result = export_groups(psd, list_top_level_groups(psd), tmp_path, Options(format=format))
    assert len(result.created) == 1 and not result.failures
    assert result.created[0].suffix == ext
    with Image.open(result.created[0]) as im:
        assert im.size == (40, 30)
        if format != "JPEG":
            assert im.convert("RGBA").getpixel((0, 0))[3] == 0
        else:
            assert im.mode == "RGB"
            assert all(channel >= 245 for channel in im.getpixel((0, 0)))  # JPEG é com perdas

def test_hidden_restore_and_isolation(tmp_path):
    first = Group("A")
    hidden = Group("B", color=(10, 210, 100, 255), visible=False)
    psd = PSD([first, hidden])
    result = export_groups(psd, list_top_level_groups(psd), tmp_path)
    assert len(result.created) == 2
    assert hidden.visible is False
    with Image.open(tmp_path / "B.png") as image:
        assert image.getpixel((5, 6)) == (10, 210, 100, 255)

def test_crop_and_scale(tmp_path):
    psd = PSD([Group("crop")])
    result = export_groups(psd, list_top_level_groups(psd), tmp_path, Options(crop=True, scale=200))
    assert not result.failures
    with Image.open(result.created[0]) as im:
        assert im.size == (20, 22)

def test_selected_and_cancel(tmp_path):
    psd = PSD([Group("A"), Group("B")])
    cancel = Event()
    def progress(*_):
        cancel.set()
    result = export_groups(psd, list_top_level_groups(psd), tmp_path,
                           progress=progress, cancel=cancel)
    assert result.cancelled and len(result.created) == 1

def test_failure_isolated_and_original_preserved(tmp_path):
    psd = PSD([Group("bad", fail=True), Group("ok")])
    old = tmp_path / "ok.png"
    old.write_bytes(b"keep")
    result = export_groups(psd, list_top_level_groups(psd), tmp_path)
    assert len(result.failures) == 1
    assert [p.name for p in result.created] == ["ok - 2.png"]
    assert old.read_bytes() == b"keep"
    assert not list(tmp_path.glob(".folderexporter-*"))

def test_numbering_and_prefix(tmp_path):
    psd = PSD([Group("aa"), Group("bb")])
    groups = list_top_level_groups(psd)
    opts = Options(naming="prefix", prefix="sprite")
    assert [p.name for _, p in build_export_plan(groups, tmp_path, opts)] == [
        "sprite - 001.png", "sprite - 002.png"]
