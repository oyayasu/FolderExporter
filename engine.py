"""Exportar pastas principais de documentos PSD/PSB sem alterar o original."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable
import re
import threading
import uuid

from PIL import Image

class ExportError(RuntimeError):
    pass

@dataclass(frozen=True)
class Folder:
    order: int
    name: str
    layer: Any
    visible: bool

@dataclass(frozen=True)
class Options:
    naming: str = "name"   # name, number, number_name, name_number, prefix
    format: str = "PNG"     # PNG, WEBP, TIFF, JPEG
    crop: bool = False
    scale: int = 100
    quality: int = 90
    matte: str = "white"
    white_background: bool = False  # opção explícita para PNG/WebP/TIFF
    prefix: str = "imagem"

@dataclass(frozen=True)
class ExportResult:
    created: tuple[Path, ...]
    failures: tuple[tuple[str, str], ...]
    cancelled: bool

INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
EXT = {"PNG": ".png", "WEBP": ".webp", "TIFF": ".tif", "JPEG": ".jpg"}

def safe_stem(name: str) -> str:
    stem = INVALID.sub("_", str(name)).strip().rstrip(" .")
    if not stem:
        stem = "sem_nome"
    if stem.split(".", 1)[0].upper() in RESERVED:
        stem = "_" + stem
    return stem[:110].rstrip(" .") or "sem_nome"

def load_psd(path: Path) -> Any:
    try:
        from psd_tools import PSDImage
        return PSDImage.open(str(path))
    except Exception as exc:
        raise ExportError(f"Could not open PSD/PSB: {exc}") from exc

def load_project(path: Path) -> Any:
    """Apenas lê o arquivo de origem. Nunca chama save() no PSD/CLIP."""
    path = Path(path)
    if path.suffix.lower() == ".clip":
        from clip_support import open_clip
        return open_clip(path)
    if path.suffix.lower() in (".psd", ".psb"):
        return load_psd(path)
    raise ExportError("Unsupported source format. Use PSD, PSB or CLIP.")

def list_top_level_groups(psd: Any) -> list[Folder]:
    if getattr(psd, "is_clip", False):
        from clip_support import top_groups
        return [
            Folder(i, name, index, visible)
            for i, (index, name, visible) in enumerate(top_groups(psd))
        ]
    # psd-tools itera de BAIXO para CIMA; Clip Studio/Photoshop mostram de CIMA para BAIXO.
    # A primeira pasta na interface precisa ser o arquivo 001.
    return [
        Folder(i, str(layer.name), layer, bool(getattr(layer, "visible", True)))
        for i, layer in enumerate(reversed(psd))
        if getattr(layer, "kind", "") in {"group", "artboard"}
    ]

def stem_for(folder: Folder, index: int, total: int, options: Options) -> str:
    number = str(index).zfill(max(3, len(str(total))))
    name = safe_stem(folder.name)
    if options.naming == "name":
        return name
    if options.naming == "number":
        return number
    if options.naming == "number_name":
        return safe_stem(f"{number} - {name}")
    if options.naming == "name_number":
        return safe_stem(f"{name} - {number}")
    if options.naming == "prefix":
        return safe_stem(f"{safe_stem(options.prefix)} - {number}")
    raise ExportError("Invalid filename format.")

def next_available_path(destination: Path, stem: str, ext: str, used: set[str]) -> Path:
    number = 1
    while True:
        name = f"{stem}{'' if number == 1 else ' - ' + str(number)}{ext}"
        candidate = destination / name
        key = name.casefold()
        if key not in used and not candidate.exists():
            used.add(key)
            return candidate
        number += 1

def build_export_plan(folders: Iterable[Folder], destination: Path, options: Options) -> list[tuple[Folder, Path]]:
    selected = list(folders)
    if options.format.upper() not in EXT:
        raise ExportError("Unsupported output format.")
    used: set[str] = set()
    return [
        (folder, next_available_path(destination, stem_for(folder, i, len(selected), options), EXT[options.format.upper()], used))
        for i, folder in enumerate(selected, 1)
    ]

def render_group(psd: Any, group: Any, crop: bool) -> Image.Image:
    if getattr(psd, "is_clip", False):
        from clip_support import render_folder
        return render_folder(psd, int(group), crop)
    width, height = int(psd.width), int(psd.height)
    if width <= 0 or height <= 0:
        raise ExportError("Invalid document dimensions.")
    # Render selected group in isolation at full-canvas coordinates. This works for
    # nested groups and does not depend on their parents' visibility.
    if hasattr(group, "composite"):
        source = group.composite(viewport=(0, 0, width, height),
                                 force=True, alpha=0.0, color=1.0)
        if source is None:
            raise ExportError("Unable to render this drawing folder.")
        image = source.convert("RGBA")
        if image is not source:
            source.close()
        if crop:
            bounds = image.getchannel("A").getbbox()
            if bounds:
                result = image.crop(bounds)
                image.close()
                return result
        return image
    was_visible = bool(group.visible)
    try:
        group.visible = True  # somente em memória
        def layer_filter(layer: Any) -> bool:
            current = layer
            while current is not None and current is not group:
                if not getattr(current, "visible", True):
                    return False
                current = getattr(current, "parent", None)
            return current is group
        result = psd.composite(
            viewport=(0, 0, width, height), alpha=0.0, color=1.0,
            layer_filter=layer_filter, ignore_preview=True
        )
    finally:
        group.visible = was_visible
    if result is None:
        raise ExportError("Unable to render this folder.")
    image = result.convert("RGBA")
    if image is not result:
        result.close()
    if crop:
        bbox = image.getchannel("A").getbbox()
        if bbox:
            cropped = image.crop(bbox)
            image.close()
            image = cropped
    return image

def prepare_image(image: Image.Image, options: Options) -> Image.Image:
    if not 10 <= options.scale <= 400:
        raise ExportError("Scale must be between 10% and 400%.")
    if options.scale != 100:
        size = (max(1, round(image.width * options.scale / 100)),
                max(1, round(image.height * options.scale / 100)))
        scaled = image.resize(size, Image.Resampling.LANCZOS)
        image.close()
        image = scaled
    if options.format.upper() == "JPEG":
        color = (0, 0, 0) if options.matte == "black" else (255, 255, 255)
        background = Image.new("RGB", image.size, color)
        background.paste(image, mask=image.getchannel("A"))
        image.close()
        image = background
    elif options.white_background:
        # Branco opcional: PNG/WebP/TIFF ficam opacos; se desmarcado, preservam alfa.
        background = Image.new("RGBA", image.size, (255, 255, 255, 255))
        background.alpha_composite(image)
        image.close()
        image = background
    return image

def save_image(image: Image.Image, path: Path, options: Options) -> None:
    fmt = options.format.upper()
    kw: dict[str, Any] = {}
    if fmt == "PNG":
        kw = {"compress_level": 6}
    elif fmt == "JPEG":
        kw = {"quality": options.quality, "subsampling": 0}
    elif fmt == "WEBP":
        kw = {"quality": options.quality, "method": 4}
    elif fmt == "TIFF":
        kw = {"compression": "tiff_deflate"}
    image.save(path, format=fmt, **kw)

def export_groups(
    psd: Any, folders: Iterable[Folder], destination: Path, options: Options = Options(),
    progress: Callable[[int, int, str, str], None] | None = None,
    cancel: threading.Event | None = None,
) -> ExportResult:
    dest = Path(destination)
    if not dest.is_dir():
        raise ExportError("Choose an existing destination folder.")
    selected = list(folders)
    if not selected:
        raise ExportError("Select at least one drawing folder.")
    plan = build_export_plan(selected, dest, options)
    created: list[Path] = []
    failures: list[tuple[str, str]] = []
    cancelled = False
    for index, (folder, initial_target) in enumerate(plan, 1):
        if cancel is not None and cancel.is_set():
            cancelled = True
            break
        tmp = dest / f".folderexporter-{uuid.uuid4().hex}{EXT[options.format.upper()]}"
        created_target: Path | None = None
        try:
            image = prepare_image(render_group(psd, folder.layer, options.crop), options)
            try:
                save_image(image, tmp, options)
            finally:
                image.close()
            # Exclusivo: nunca sobrescreve arquivos, mesmo criados durante a exportação.
            target = initial_target
            counter = 2
            while True:
                try:
                    with target.open("xb") as out, tmp.open("rb") as source:
                        created_target = target
                        while True:
                            data = source.read(1024 * 1024)
                            if not data:
                                break
                            out.write(data)
                    break
                except FileExistsError:
                    target = dest / f"{initial_target.stem} - {counter}{initial_target.suffix}"
                    counter += 1
            created.append(target)
            if progress:
                progress(index, len(plan), folder.name, target.name)
        except Exception as exc:
            if created_target is not None:
                try:
                    created_target.unlink(missing_ok=True)
                except OSError:
                    pass
            failures.append((folder.name, str(exc)))
            if progress:
                progress(index, len(plan), folder.name, f"ERRO: {exc}")
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
    return ExportResult(tuple(created), tuple(failures), cancelled)
