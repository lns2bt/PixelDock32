from app.config import Settings


class LEDMapper:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.width = settings.panel_columns
        self.height = settings.panel_rows

    def map_components(self, x: int, y: int) -> dict:
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            raise ValueError("coordinate out of range")

        panel_x = x // self.settings.panel_width
        local_x = x % self.settings.panel_width
        local_y = y % self.settings.panel_height

        if self.settings.data_starts_right:
            panel_index = (self.settings.chain_panels - 1) - panel_x
        else:
            panel_index = panel_x

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
            "local_x": local_x,
            "local_y": local_y,
            "serpentine_flipped": serpentine_flipped,
            "pixel_in_panel": pixel_in_panel,
            "index": index,
        }

    def xy_to_index(self, x: int, y: int) -> int:
        return int(self.map_components(x, y)["index"])
