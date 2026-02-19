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
