from dataclasses import dataclass


ColorFrame = list[list[tuple[int, int, int] | None]]


@dataclass
class ModulePayload:
    text: str
    frame: list[list[int]] | None = None
    color_frame: ColorFrame | None = None


class ModuleBase:
    key: str = "base"

    async def render(self, settings: dict, cache: dict) -> ModulePayload:
        raise NotImplementedError
