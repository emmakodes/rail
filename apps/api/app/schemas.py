from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TodoCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class TodoRead(BaseModel):
    id: int
    title: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TodoTagRead(BaseModel):
    id: int
    label: str

    model_config = ConfigDict(from_attributes=True)


class TodoWithTagsRead(TodoRead):
    tags: list[TodoTagRead] = []


class TodoCursorPage(BaseModel):
    items: list[TodoRead]
    next_cursor: int | None
    has_more: bool


class TodoSerializationListItem(BaseModel):
    id: int
    title: str
    created_at: datetime


class TodoSerializationHeavyItem(BaseModel):
    id: int
    title: str
    created_at: datetime
    status: str
    priority: str
    category: str
    owner: str
    description: str
    note_01: str
    note_02: str
    note_03: str
    note_04: str
    note_05: str
    note_06: str
    note_07: str
    note_08: str
    note_09: str
    note_10: str
    note_11: str
    note_12: str
    note_13: str
    note_14: str
    note_15: str
    note_16: str
    note_17: str
    note_18: str
    note_19: str
    note_20: str
    note_21: str
    note_22: str
    note_23: str
    note_24: str
    note_25: str
    note_26: str
    note_27: str
    note_28: str
    note_29: str
    note_30: str
    note_31: str
    note_32: str
    note_33: str
    note_34: str
    note_35: str
    note_36: str
    note_37: str
    note_38: str
    note_39: str
    note_40: str
    note_41: str
    note_42: str
