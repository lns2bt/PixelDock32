from app.config import Settings


class LEDMapper:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.width = settings.panel_columns
        self.height = settings.panel_rows

    def _normalize_rotation(self, value: int) -> int:
        rotation = int(value) % 360
        if rotation not in (0, 90, 180, 270):
            raise ValueError("panel rotation must be one of 0, 90, 180, 270")
        return rotation

    def _resolve_panel_config(self, panel_x: int) -> tuple[int, int]:
        panel_count = max(self.settings.chain_panels, 1)

        panel_order = list(self.settings.panel_order)
        if len(panel_order) != panel_count:
            panel_order = list(range(panel_count))

        panel_rotations = list(self.settings.panel_rotations)
        if len(panel_rotations) < panel_count:
            panel_rotations = panel_rotations + [0] * (panel_count - len(panel_rotations))
        elif len(panel_rotations) > panel_count:
            panel_rotations = panel_rotations[:panel_count]

        physical_index = panel_count - 1 - panel_x if self.settings.data_starts_right else panel_x
        panel_index = int(panel_order[physical_index])
        if panel_index < 0 or panel_index >= panel_count:
            panel_index = physical_index

        rotation = self._normalize_rotation(panel_rotations[panel_index])
        return panel_index, rotation

    def _rotate_local(self, local_x: int, local_y: int, rotation: int) -> tuple[int, int]:
        panel_w = self.settings.panel_width
        panel_h = self.settings.panel_height
        if rotation == 0:
            return local_x, local_y
        if rotation == 90:
            return panel_w - 1 - local_y, local_x
        if rotation == 180:
            return panel_w - 1 - local_x, panel_h - 1 - local_y
        return local_y, panel_h - 1 - local_x

    def map_components(self, x: int, y: int) -> dict:
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            raise ValueError("coordinate out of range")

        panel_x = x // self.settings.panel_width
        local_x = x % self.settings.panel_width
        local_y = y % self.settings.panel_height

        panel_index, panel_rotation = self._resolve_panel_config(panel_x)
        local_x, local_y = self._rotate_local(local_x, local_y, panel_rotation)

        serpentine_flipped = bool(self.settings.serpentine and (local_y % 2 == 1))
        if serpentine_flipped:
            local_x = self.settings.panel_width - 1 - local_x

        pixel_in_panel = local_y * self.settings.panel_width + local_x
        index = self.settings.first_pixel_offset + panel_index * (
            self.settings.panel_width * self.settings.panel_height
        ) + pixel_in_panel

        return {
            "x": x,
            "y": y,
            "panel_x": panel_x,
            "panel_index": panel_index,
            "panel_rotation": panel_rotation,
            "local_x": local_x,
            "local_y": local_y,
            "serpentine_flipped": serpentine_flipped,
            "pixel_in_panel": pixel_in_panel,
            "index": index,
        }

    def xy_to_index(self, x: int, y: int) -> int:
        return int(self.map_components(x, y)["index"])
