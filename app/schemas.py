from pydantic import BaseModel, Field


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    username: str
    password: str


class ModuleConfigBase(BaseModel):
    enabled: bool
    duration_seconds: int = Field(ge=1, le=300)
    sort_order: int
    settings: dict = Field(default_factory=dict)


class ModuleConfigUpdate(ModuleConfigBase):
    pass


class ModuleConfigResponse(ModuleConfigBase):
    id: int
    key: str
    name: str

    class Config:
        from_attributes = True


class ManualTextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=64)
    seconds: int = Field(default=8, ge=1, le=120)


class DrawRequest(BaseModel):
    pixels: list[list[int]]
    seconds: int = Field(default=8, ge=1, le=120)


class BrightnessRequest(BaseModel):
    brightness: int = Field(ge=0, le=255)
