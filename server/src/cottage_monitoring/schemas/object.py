from pydantic import BaseModel, ConfigDict, field_validator


class ObjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    house_id: str
    ga: str
    object_id: int | None
    name: str | None
    datatype: int
    units: str
    tags: list[str]
    comment: str
    schema_hash: str | None
    is_active: bool
    is_timeseries: bool

    @field_validator("tags", mode="before")
    @classmethod
    def parse_tags(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [t.strip() for t in v.split(",") if t.strip()]
        return v
