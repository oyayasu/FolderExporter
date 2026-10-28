"""Chapter structure and naming regression coverage."""
from pathlib import Path

import pytest
from PIL import Image

from engine import Options
from workflow import (Node, Naming, folder_tree, discover_drawings,
                      make_plan, export_plan, drawing_name)


def structure():
    return [
        Node("/5", "Chapter 3", object(), True, [
            Node("/5/0", "1", object(), True),
            Node("/5/1", "2", object(), False),
            Node("/5/2", "3", object(), True),
        ]),
        Node("/4", "Chapter 12", object(), True, [
            Node("/4/0", "1", object(), True),
            Node("/4/1", "2", object(), True),
        ]),
    ]


def test_chapters_are_organizational_and_duplicates_stay_in_separate_directories(tmp_path):
    drawings = discover_drawings(structure(), "chapter")
    assert [(d.chapter, d.name) for d in drawings] == [
        (("Chapter 3",), "1"), (("Chapter 3",), "2"), (("Chapter 3",), "3"),
        (("Chapter 12",), "1"), (("Chapter 12",), "2"),
    ]
    tasks = make_plan(drawings, {d.key for d in drawings}, tmp_path,
                      Naming(mode="Format", custom="Drawing", start=1),
                      Options(), True)
    assert [str(task.path.relative_to(tmp_path)) for task in tasks] == [
        "Chapter 3/Drawing - 001.png", "Chapter 3/Drawing - 002.png",
        "Chapter 3/Drawing - 003.png", "Chapter 12/Drawing - 001.png",
        "Chapter 12/Drawing - 002.png",
    ]


def test_name_only_and_duplicate_names_are_safe(tmp_path):
    drawings = discover_drawings(structure(), "chapter")
    tasks = make_plan(drawings, {d.key for d in drawings}, tmp_path,
                      Naming(kind="Name Only"), Options())
    assert [str(task.path.relative_to(tmp_path)) for task in tasks] == [
        "Chapter 3/1.png", "Chapter 3/2.png", "Chapter 3/3.png",
        "Chapter 12/1.png", "Chapter 12/2.png",
    ]


def test_nested_chapter_rules_and_case_insensitive_keywords():
    tree = [Node("/1", "SECTION A", None, True, [
        Node("/1/0", "Chapter 1", None, True, [
            Node("/1/0/0", "take 1", None, True)
        ])
    ])]
    drawings = discover_drawings(tree, "chapter, section")
    assert drawings[0].chapter == ("SECTION A", "Chapter 1")
    assert drawings[0].name == "take 1"


def test_adding_and_replacing_text_and_custom_index(tmp_path):
    drawings = discover_drawings(structure(), "chapter")
    one = drawings[0]
    assert drawing_name(one, Naming(mode="Add Text", addition="scene_", where="before"), 1) == "scene_1"
    assert drawing_name(one, Naming(mode="Add Text", addition="_v2", where="after"), 1) == "1_v2"
    assert drawing_name(one, Naming(mode="Replace Text", search="1", replacement="A"), 1) == "A"
    assert drawing_name(one, Naming(mode="Format", kind="Name and Index",
                        custom="_2.1.AAAA", where="before", separator="", padding=0), 1) == "1_2.1.AAAA"
    assert drawing_name(one, Naming(mode="Format", kind="Name and Counter",
                        custom="Work", padding=2), 2) == "Work - 00002"


def test_existing_exports_never_overwritten(tmp_path):
    dest = tmp_path / "Chapter 3"
    dest.mkdir()
    (dest / "1.png").write_bytes(b"EXISTING")
    drawings = discover_drawings(structure(), "chapter")
    plan = make_plan(drawings, {d.key for d in drawings}, tmp_path,
                     Naming(kind="Name Only"), Options())
    assert plan[0].path.name == "1 - 2.png"
    assert (dest / "1.png").read_bytes() == b"EXISTING"


def test_only_folder_names_are_used_to_create_subdirectories(tmp_path):
    tree = [Node("/1", "Chapter ../\\evil", None, True,
                 [Node("/1/0", "art", None, True)])]
    drawings = discover_drawings(tree, "chapter")
    paths = make_plan(drawings, {drawings[0].key}, tmp_path, Naming(kind="Name Only"), Options())
    assert paths[0].path.parent.parent == tmp_path


class FakePSD(list):
    width = 16
    height = 12


class FakeGroup(list):
    kind = "group"
    visible = True

    def __init__(self, name, children=(), color=None):
        super().__init__(children)
        self.name = name
        self.color = color

    def composite(self, viewport=None, force=False, alpha=None, color=None):
        assert viewport == (0, 0, 16, 12) and force
        return Image.new("RGBA", (16, 12), self.color or (0, 0, 0, 0))


def test_psd_visual_order_and_read_only_export(tmp_path):
    # psd-tools iterator and indexing are bottom-to-top.
    one = FakeGroup("1", color=(240, 0, 0, 255))
    two = FakeGroup("2", color=(0, 240, 0, 255))
    chapter = FakeGroup("Chapter 7", [two, one])
    project = FakePSD([chapter])
    tree = folder_tree(project)
    drawings = discover_drawings(tree, "chapter")
    assert [drawing.name for drawing in drawings] == ["1", "2"]
    destination = tmp_path / "result"
    task_list = make_plan(drawings, {d.key for d in drawings}, destination,
                          Naming(mode="Format", custom="scene"), Options())
    source = tmp_path / "work.psd"
    source.write_bytes(b"UNCHANGED")
    result = export_plan(project, task_list, Options())
    assert not result.failures
    assert source.read_bytes() == b"UNCHANGED"
    with Image.open(destination / "Chapter 7" / "scene - 001.png") as im:
        assert im.getpixel((3, 3)) == (240, 0, 0, 255)
