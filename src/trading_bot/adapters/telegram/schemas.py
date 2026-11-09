"""Pydantic schemas for Telegram Bot API boundary payloads."""

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class TelegramChat(BaseModel):
    """Telegram chat model."""

    model_config = ConfigDict(extra="ignore")

    id: int
    type: str | None = None
    title: str | None = None
    username: str | None = None


class TelegramUser(BaseModel):
    """Telegram user model."""

    model_config = ConfigDict(extra="ignore")

    id: int
    is_bot: bool | None = None
    first_name: str | None = None
    username: str | None = None


class TelegramMessage(BaseModel):
    """Telegram message object."""

    model_config = ConfigDict(extra="ignore")

    message_id: int
    chat: TelegramChat
    text: str | None = None
    date: int | None = None
    from_user: TelegramUser | None = Field(default=None, alias="from")


class TelegramUpdate(BaseModel):
    """Telegram update object received from getUpdates."""

    model_config = ConfigDict(extra="ignore")

    update_id: int
    message: TelegramMessage | None = None


class TelegramResponse(BaseModel, Generic[T]):
    """Generic envelope for Telegram Bot API responses."""

    model_config = ConfigDict(extra="ignore")

    ok: bool
    result: T | None = None
    description: str | None = None
    error_code: int | None = None
