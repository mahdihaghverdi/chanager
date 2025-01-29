from uuid import UUID

from pydantic import BaseModel


class RegisterIn(BaseModel):
    ip: str
    port: int
    name: str | None = None


class RegisterOut(BaseModel):
    id: UUID
