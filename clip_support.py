"""Leitura experimental e SOMENTE LEITURA de pastas CLIP STUDIO (.clip).

A renderização é intencionalmente conservadora: mistura normal e camadas raster.
Recusamos recursos não implementados em vez de salvar PNGs incorretos.
Nenhum ClipWriter é importado, e nenhum arquivo CLIP é gravado.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

@dataclass
class ClipProject:
    file: Any
    path: Path
    width: int
    height: int
    is_clip: bool = True

def open_clip(path: Path) -> ClipProject:
    try:
        import clipparse
        reader = clipparse.ClipFile()
        if not reader.load(str(path)):
            raise ValueError(getattr(reader, "error", "O leitor CLIP rejeitou o arquivo."))
        width, height = int(reader.width), int(reader.height)
        if width <= 0 or height <= 0:
            raise ValueError("Dimensões inválidas do CLIP.")
        return ClipProject(reader, Path(path), width, height)
    except Exception as exc:
        raise ValueError(f"Não foi possível ler o arquivo .clip: {exc}") from exc

def top_groups(project: ClipProject) -> list[tuple[int, str, bool]]:
    reader = project.file
    # clipparse expõe roots de BAIXO para CIMA. A interface do CSP é de cima para baixo.
    return [
        (index, str(reader.layers[index].name), bool(reader.layers[index].visible))
        for index in reversed(reader.roots)
        if reader.layers[index].is_group
    ]

def _apply_opacity(image: Image.Image, opacity: int) -> None:
    opacity = max(0, min(255, int(opacity)))
    if opacity == 255:
        return
    alpha = image.getchannel("A").point(lambda value: (value * opacity + 127) // 255)
    image.putalpha(alpha)
    alpha.close()

def render_folder(project: ClipProject, folder_index: int, crop: bool = False) -> Image.Image:
    """Renderiza um grupo isolado com mistura normal; não toca o arquivo original."""
    reader = project.file
    if not reader.layers[folder_index].is_group:
        raise ValueError("A seleção não é uma pasta.")
    width, height = project.width, project.height

    def compose_group(index: int, force_visible: bool = False) -> Image.Image:
        layer = reader.layers[index]
        if not force_visible and not layer.visible:
            return Image.new("RGBA", (width, height))
        if layer.is_filter:
            raise ValueError("Esta pasta possui camada de ajuste não suportada no CLIP direto; use PSD.")
        if layer.clipping:
            raise ValueError("Esta pasta possui recorte por camada não suportado no CLIP direto; use PSD.")
        if layer.is_group:
            if layer.has_mask:
                raise ValueError("Máscara de pasta não suportada no CLIP direto; use PSD.")
            if layer.composite_raw not in (0, 30):
                raise ValueError("Modo de mesclagem de pasta não suportado no CLIP direto; use PSD.")
            result = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            for child_index in reader.children(index):
                child_image = compose_group(child_index)
                result.alpha_composite(child_image)
                child_image.close()
        else:
            if layer.composite_raw != 0:
                raise ValueError("Esta pasta usa um modo de mesclagem não suportado no CLIP direto; use PSD.")
            if layer.width <= 0 or layer.height <= 0:
                raise ValueError("Camada sem pixels rasterizáveis no CLIP direto; use PSD.")
            data = reader.layer_image(index, "masked")
            expected = int(layer.width) * int(layer.height) * 4
            if len(data) != expected:
                raise ValueError("Pixels não disponíveis nessa camada CLIP; use PSD.")
            piece = Image.frombytes("RGBA", (int(layer.width), int(layer.height)), data, "raw", "BGRA")
            result = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            result.paste(piece, (int(layer.left), int(layer.top)))
            piece.close()
        _apply_opacity(result, int(layer.opacity))
        return result

    image = compose_group(folder_index, force_visible=True)
    if crop:
        box = image.getchannel("A").getbbox()
        if box:
            cropped = image.crop(box)
            image.close()
            return cropped
    return image
