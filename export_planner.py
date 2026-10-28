"""Chapter-aware export planning. Never changes source documents."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
import re
import threading
import uuid

from PIL import Image
from engine import (Options, ExportResult, ExportError, EXT, safe_stem,
                    prepare_image, save_image, render_group)


@dataclass
class Node:
    key: str
    name: str
    ref: object
    visible: bool
    children: list["Node"] = field(default_factory=list)


@dataclass(frozen=True)
class Drawing:
    key: str
    name: str
    ref: object
    chapter: tuple[str, ...] = ()
    sequence: int = 1


@dataclass(frozen=True)
class Naming:
    mode: str = "Format"
    kind: str = "Name and Index"
    custom: str = "Drawing"
    where: str = "after"
    start: int = 1
    padding: int = 3
    separator: str = " - "
    reset: bool = True
    addition: str = ""
    search: str = ""
    replacement: str = ""


@dataclass(frozen=True)
class ExportTask:
    drawing: Drawing
    path: Path


def folder_tree(document) -> list[Node]:
    """Both PSD and CLIP layer collections are bottom-to-top."""
    if getattr(document, "is_clip", False):
        reader = document.file
        def walk(parent=-1, prefix=""):
            result = []
            for index in reversed(reader.children(parent)):
                layer = reader.layers[index]
                if not layer.is_group:
                    continue
                key = f"{prefix}/{index}"
                result.append(Node(key, str(layer.name), index, bool(layer.visible),
                                   walk(index, key)))
            return result
        return walk()

    def walk(container, prefix=""):
        result = []
        for index in range(len(container) - 1, -1, -1):
            layer = container[index]
            kind = getattr(layer, "kind", "")
            group = getattr(layer, "is_group", None)
            is_group = bool(group()) if callable(group) else kind in ("group", "artboard")
            if not is_group:
                continue
            key = f"{prefix}/{index}"
            result.append(Node(key, str(layer.name), layer, bool(layer.visible),
                               walk(layer, key)))
        return result
    return walk(document)


def parse_keywords(value: str) -> tuple[str, ...]:
    return tuple(part.strip().casefold()
                 for part in re.split(r"[,;\n]+", value)
                 if part.strip())


def is_organizer(node: Node, keywords: str) -> bool:
    return any(term in node.name.casefold() for term in parse_keywords(keywords))


def discover_drawings(tree: list[Node], keywords: str = "chapter, section",
                      separate: bool = True) -> list[Drawing]:
    drawings: list[Drawing] = []
    def scan(nodes, chapter):
        for node in nodes:
            if is_organizer(node, keywords):
                # Organization folders are not drawn. Search inside recursively.
                next_chapter = chapter + (node.name,) if separate else ()
                scan(node.children, next_chapter)
            else:
                drawings.append(Drawing(node.key, node.name, node.ref, chapter))
    scan(tree, ())
    return drawings


def drawing_name(drawing: Drawing, naming: Naming, sequence: int) -> str:
    original = safe_stem(drawing.name)
    if naming.mode == "Add Text":
        name = naming.addition + original if naming.where == "before" else original + naming.addition
    elif naming.mode == "Replace Text":
        name = original.replace(naming.search, naming.replacement) if naming.search else original
    elif naming.mode == "Format":
        if naming.kind == "Name Only":
            name = original
        else:
            if naming.kind == "Name and Date":
                suffix = date.today().strftime("%Y-%m-%d")
            elif naming.kind == "Name and Counter":
                suffix = str(sequence).zfill(max(5, naming.padding))
            else:
                suffix = str(sequence).zfill(naming.padding)
            stem = naming.custom if naming.custom else original
            name = (suffix + naming.separator + stem) if naming.where == "before" else (stem + naming.separator + suffix)
    else:
        raise ExportError(f"Unknown naming mode: {naming.mode}")
    return safe_stem(name)


def _free_file(folder: Path, name: str, extension: str, taken: set[str]) -> Path:
    suffix = 1
    while True:
        candidate = folder / (name + (f" - {suffix}" if suffix > 1 else "") + extension)
        norm = str(candidate).casefold()
        if norm not in taken and not candidate.exists():
            taken.add(norm)
            return candidate
        suffix += 1


def make_plan(drawings: list[Drawing], selected: set[str], destination: Path,
              naming: Naming, output: Options, separate: bool = True) -> list[ExportTask]:
    if output.format.upper() not in EXT:
        raise ExportError("Unsupported format")
    if not 0 <= naming.start <= 1000000000 or not 0 <= naming.padding <= 10:
        raise ExportError("Invalid starting number or padding.")
    tasks = []
    reserved: set[str] = set()
    counts: dict[tuple[str, ...], int] = {}
    for drawing in drawings:
        if drawing.key not in selected:
            continue
        chapter = drawing.chapter if separate else ()
        counts[chapter] = counts.get(chapter, 0) + 1
        number = (counts[chapter] if naming.reset else len(tasks) + 1) - 1 + naming.start
        file_name = drawing_name(drawing, naming, number)
        folder = Path(destination)
        for segment in chapter:
            folder /= safe_stem(segment)
        path = _free_file(folder, file_name, EXT[output.format.upper()], reserved)
        tasks.append(ExportTask(drawing, path))
    return tasks


def export_plan(document, tasks: list[ExportTask], output: Options,
                progress=None, cancel: threading.Event | None = None) -> ExportResult:
    created, failures = [], []
    cancelled = False
    for i, task in enumerate(tasks, 1):
        if cancel is not None and cancel.is_set():
            cancelled = True
            break
        target = task.path
        temporary = None
        claimed = None
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            image = prepare_image(render_group(document, task.drawing.ref, output.crop), output)
            try:
                temporary = target.parent / f".folderexporter-{uuid.uuid4().hex}{target.suffix}"
                save_image(image, temporary, output)
            finally:
                image.close()
            # Exclusive creation. Existing exports and projects are NEVER overwritten.
            stem = target.stem
            number = 2
            while True:
                try:
                    with target.open("xb") as dest, temporary.open("rb") as src:
                        claimed = target
                        while block := src.read(1024 * 1024):
                            dest.write(block)
                    break
                except FileExistsError:
                    target = task.path.with_name(f"{stem} - {number}{task.path.suffix}")
                    number += 1
            created.append(target)
            if progress:
                progress(i, len(tasks), target.name, "")
        except Exception as exc:
            if claimed is not None:
                try:
                    claimed.unlink(missing_ok=True)
                except OSError:
                    pass
            failures.append((task.drawing.name, str(exc)))
            if progress:
                progress(i, len(tasks), task.drawing.name, str(exc))
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
    return ExportResult(tuple(created), tuple(failures), cancelled)
