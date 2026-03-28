from pydantic import BaseModel, Field


class DebugPatternRequest(BaseModel):
    pattern: str = Field(pattern="^(pixel_walk|stripes|panel_walk|border)$")
    seconds: int = Field(default=20, ge=1, le=300)
    interval_ms: int = Field(default=250, ge=50, le=2000)


class GpioOutputTestRequest(BaseModel):
    gpio_pin: int = Field(ge=2, le=27)
    pulses: int = Field(default=3, ge=1, le=12)
    hold_ms: int = Field(default=220, ge=80, le=2000)


class GpioInputProbeRequest(BaseModel):
    gpio_pin: int = Field(ge=2, le=27)
    sample_ms: int = Field(default=1000, ge=250, le=10000)
    pull_up: bool = Field(default=True)


class LedSerialPingRequest(BaseModel):
    nonce: int | None = Field(default=None, ge=0, le=4294967295)


class MappingOverrideRequest(BaseModel):
    first_pixel_offset: int = Field(default=0, ge=-4096, le=4096)
    data_starts_right: bool = Field(default=True)
    serpentine: bool = Field(default=True)
    panel_order: list[int] = Field(min_length=1, max_length=16)
    panel_rotations: list[int] = Field(min_length=1, max_length=16)


class MappingObservation(BaseModel):
    logical_x: int = Field(ge=0, le=31)
    logical_y: int = Field(ge=0, le=7)
    observed_x: int = Field(ge=0, le=31)
    observed_y: int = Field(ge=0, le=7)


class MappingInferenceRequest(BaseModel):
    observations: list[MappingObservation] = Field(min_length=1, max_length=256)
    max_solutions: int = Field(default=8, ge=1, le=32)
