from pydantic import BaseModel, Field


class DebugPatternRequest(BaseModel):
    pattern: str = Field(pattern="^(pixel_walk|stripes|panel_walk|border)$")
    seconds: int = Field(default=20, ge=1, le=300)
    interval_ms: int = Field(default=250, ge=50, le=2000)
