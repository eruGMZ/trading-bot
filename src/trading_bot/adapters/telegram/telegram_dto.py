"""Pydantic DTOs for Telegram Bot API boundary payloads."""

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class TelegramChatDTO(BaseModel):
    """Telegram chat DTO."""

    model_config = ConfigDict(extra="ignore")

    id: int
    type: str | None = None
    title: str | None = None
    username: str | None = None


class TelegramUserDTO(BaseModel):
    """Telegram user DTO."""

    model_config = ConfigDict(extra="ignore")

    id: int
    is_bot: bool | None = None
    first_name: str | None = None
    username: str | None = None


class TelegramMessageDTO(BaseModel):
    """Telegram message DTO."""

    model_config = ConfigDict(extra="ignore")

    message_id: int
    chat: TelegramChatDTO
    text: str | None = None
    date: int | None = None
    from_user: TelegramUserDTO | None = Field(default=None, alias="from")


class TelegramUpdateDTO(BaseModel):
    """Telegram update DTO received from getUpdates."""

    model_config = ConfigDict(extra="ignore")

    update_id: int
    message: TelegramMessageDTO | None = None


class TelegramResponseDTO(BaseModel, Generic[T]):
    """Generic envelope DTO for Telegram Bot API responses."""

    model_config = ConfigDict(extra="ignore")

    ok: bool
    result: T | None = None
    description: str | None = None
    error_code: int | None = None
