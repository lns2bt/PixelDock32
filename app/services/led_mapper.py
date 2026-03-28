from itertools import permutations, product

from app.config import Settings


class LEDMapper:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.width = settings.panel_columns
        self.height = settings.panel_rows
        self._runtime_overrides: dict[str, object] = {}
        # Mapping is static for the runtime config; precompute for the hot render path.
        self._rebuild_xy_index_table()

    def _rebuild_xy_index_table(self) -> None:
        self._xy_index_table = [
            [self._compute_index(x, y) for x in range(self.width)]
            for y in range(self.height)
        ]

    def _effective(self, key: str):
        if key in self._runtime_overrides:
            return self._runtime_overrides[key]
        return getattr(self.settings, key)

    def _effective_panel_count(self) -> int:
        return max(int(self._effective("chain_panels")), 1)

    def apply_runtime_overrides(
        self,
        *,
        first_pixel_offset: int,
        data_starts_right: bool,
        serpentine: bool,
        panel_order: list[int],
        panel_rotations: list[int],
    ) -> dict:
        panel_count = self._effective_panel_count()
        if len(panel_order) != panel_count:
            raise ValueError(f"panel_order length must be exactly {panel_count}")
        if len(set(panel_order)) != panel_count:
            raise ValueError("panel_order entries must be unique")
        if any(item < 0 or item >= panel_count for item in panel_order):
            raise ValueError(f"panel_order entries must be in range 0..{panel_count - 1}")

        normalized_rotations = [self._normalize_rotation(value) for value in panel_rotations]
        if len(normalized_rotations) != panel_count:
            raise ValueError(f"panel_rotations length must be exactly {panel_count}")

        self._runtime_overrides = {
            "first_pixel_offset": int(first_pixel_offset),
            "data_starts_right": bool(data_starts_right),
            "serpentine": bool(serpentine),
            "panel_order": [int(item) for item in panel_order],
            "panel_rotations": normalized_rotations,
        }
        self._rebuild_xy_index_table()
        return self.get_runtime_mapping_snapshot()

    def clear_runtime_overrides(self) -> dict:
        self._runtime_overrides = {}
        self._rebuild_xy_index_table()
        return self.get_runtime_mapping_snapshot()

    def get_runtime_mapping_snapshot(self) -> dict:
        panel_count = self._effective_panel_count()
        active = bool(self._runtime_overrides)
        panel_order = list(self._effective("panel_order"))
        panel_rotations = list(self._effective("panel_rotations"))
        if len(panel_order) != panel_count:
            panel_order = list(range(panel_count))
        if len(panel_rotations) < panel_count:
            panel_rotations = panel_rotations + [0] * (panel_count - len(panel_rotations))
        elif len(panel_rotations) > panel_count:
            panel_rotations = panel_rotations[:panel_count]
        return {
            "active": active,
            "first_pixel_offset": int(self._effective("first_pixel_offset")),
            "data_starts_right": bool(self._effective("data_starts_right")),
            "serpentine": bool(self._effective("serpentine")),
            "panel_order": [int(item) for item in panel_order],
            "panel_rotations": [self._normalize_rotation(value) for value in panel_rotations],
            "panel_count": panel_count,
            "panel_width": int(self._effective("panel_width")),
            "panel_height": int(self._effective("panel_height")),
            "panel_columns": int(self._effective("panel_columns")),
            "panel_rows": int(self._effective("panel_rows")),
            "led_count": int(self._effective("led_count")),
            "source": "runtime_override" if active else "settings",
        }

    def _normalize_rotation(self, value: int) -> int:
        rotation = int(value) % 360
        if rotation not in (0, 90, 180, 270):
            raise ValueError("panel rotation must be one of 0, 90, 180, 270")
        return rotation

    def _resolve_panel_config(self, panel_x: int) -> tuple[int, int]:
        panel_count = self._effective_panel_count()

        panel_order = list(self._effective("panel_order"))
        if len(panel_order) != panel_count:
            panel_order = list(range(panel_count))

        panel_rotations = list(self._effective("panel_rotations"))
        if len(panel_rotations) < panel_count:
            panel_rotations = panel_rotations + [0] * (panel_count - len(panel_rotations))
        elif len(panel_rotations) > panel_count:
            panel_rotations = panel_rotations[:panel_count]

        physical_index = panel_count - 1 - panel_x if self._effective("data_starts_right") else panel_x
        panel_index = int(panel_order[physical_index])
        if panel_index < 0 or panel_index >= panel_count:
            panel_index = physical_index

        rotation = self._normalize_rotation(panel_rotations[panel_index])
        return panel_index, rotation

    def _rotate_local(self, local_x: int, local_y: int, rotation: int) -> tuple[int, int]:
        panel_w = int(self._effective("panel_width"))
        panel_h = int(self._effective("panel_height"))
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

        panel_width = int(self._effective("panel_width"))
        panel_height = int(self._effective("panel_height"))
        first_pixel_offset = int(self._effective("first_pixel_offset"))
        serpentine = bool(self._effective("serpentine"))

        panel_x = x // panel_width
        local_x = x % panel_width
        local_y = y % panel_height

        panel_index, panel_rotation = self._resolve_panel_config(panel_x)
        local_x, local_y = self._rotate_local(local_x, local_y, panel_rotation)

        serpentine_flipped = bool(serpentine and (local_y % 2 == 1))
        if serpentine_flipped:
            local_x = panel_width - 1 - local_x

        pixel_in_panel = local_y * panel_width + local_x
        index = first_pixel_offset + panel_index * (
            panel_width * panel_height
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

    def _compute_index(self, x: int, y: int) -> int:
        return int(self.map_components(x, y)["index"])

    def xy_to_index(self, x: int, y: int) -> int:
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            raise ValueError("coordinate out of range")
        return self._xy_index_table[y][x]

    def _map_index_with_overrides(
        self,
        *,
        x: int,
        y: int,
        first_pixel_offset: int,
        data_starts_right: bool,
        serpentine: bool,
        panel_order: list[int],
        panel_rotations: list[int],
    ) -> int:
        panel_width = int(self.settings.panel_width)
        panel_height = int(self.settings.panel_height)
        panel_count = max(int(self.settings.chain_panels), 1)

        panel_x = x // panel_width
        local_x = x % panel_width
        local_y = y % panel_height

        physical_index = panel_count - 1 - panel_x if data_starts_right else panel_x
        panel_index = int(panel_order[physical_index])
        panel_rotation = self._normalize_rotation(panel_rotations[panel_index])

        local_x, local_y = self._rotate_local(local_x, local_y, panel_rotation)
        if serpentine and (local_y % 2 == 1):
            local_x = panel_width - 1 - local_x

        pixel_in_panel = local_y * panel_width + local_x
        return int(first_pixel_offset) + panel_index * (panel_width * panel_height) + pixel_in_panel

    def infer_runtime_overrides(self, observations: list[dict], max_solutions: int = 8) -> dict:
        panel_count = self._effective_panel_count()
        if panel_count > 6:
            raise ValueError("mapping inference supports up to 6 panels")

        current_mapping = self.get_runtime_mapping_snapshot()
        logical_targets: list[dict] = []
        for item in observations:
            logical_x = int(item["logical_x"])
            logical_y = int(item["logical_y"])
            observed_x = int(item["observed_x"])
            observed_y = int(item["observed_y"])
            logical_index = int(self.map_components(logical_x, logical_y)["index"])
            logical_targets.append(
                {
                    "logical_x": logical_x,
                    "logical_y": logical_y,
                    "observed_x": observed_x,
                    "observed_y": observed_y,
                    "logical_index": logical_index,
                }
            )

        matches: list[dict] = []
        all_orders = list(permutations(range(panel_count)))
        all_rotations = list(product((0, 90, 180, 270), repeat=panel_count))

        for data_starts_right in (False, True):
            for serpentine in (False, True):
                for panel_order in all_orders:
                    for panel_rotations in all_rotations:
                        offset_guess: int | None = None
                        valid = True
                        for obs in logical_targets:
                            base_index = self._map_index_with_overrides(
                                x=obs["observed_x"],
                                y=obs["observed_y"],
                                first_pixel_offset=0,
                                data_starts_right=data_starts_right,
                                serpentine=serpentine,
                                panel_order=list(panel_order),
                                panel_rotations=list(panel_rotations),
                            )
                            inferred_offset = int(obs["logical_index"]) - int(base_index)
                            if offset_guess is None:
                                offset_guess = inferred_offset
                            elif inferred_offset != offset_guess:
                                valid = False
                                break
                        if not valid or offset_guess is None:
                            continue
                        matches.append(
                            {
                                "first_pixel_offset": int(offset_guess),
                                "data_starts_right": bool(data_starts_right),
                                "serpentine": bool(serpentine),
                                "panel_order": [int(value) for value in panel_order],
                                "panel_rotations": [int(value) for value in panel_rotations],
                            }
                        )
                        if len(matches) >= max_solutions:
                            return {
                                "observation_count": len(logical_targets),
                                "solutions_found": len(matches),
                                "solutions": matches,
                                "current_mapping": current_mapping,
                            }

        return {
            "observation_count": len(logical_targets),
            "solutions_found": len(matches),
            "solutions": matches,
            "current_mapping": current_mapping,
        }
