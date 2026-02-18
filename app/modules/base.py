from dataclasses import dataclass, field


ColorFrame = list[list[tuple[int, int, int] | None]]


@dataclass
class ModulePayload:
    text: str
    frame: list[list[int]] | None = None
    color_frame: ColorFrame | None = None
    font_size: str = "normal"
    x_offset: int = 0
    y_offset: int = 0
    default_color: tuple[int, int, int] = (80, 80, 80)
    char_colors: list[tuple[int, int, int]] = field(default_factory=list)
    char_spacing: int = 1


class ModuleBase:
    key: str = "base"

    async def render(self, settings: dict, cache: dict) -> ModulePayload:
        raise NotImplementedError
