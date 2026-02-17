from dataclasses import dataclass


@dataclass
class ModulePayload:
    text: str
    frame: list[list[int]] | None = None


class ModuleBase:
    key: str = "base"

    async def render(self, settings: dict, cache: dict) -> ModulePayload:
        raise NotImplementedError
