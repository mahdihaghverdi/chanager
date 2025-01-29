from uuid import UUID

from pydantic import BaseModel


class RegisterIn(BaseModel):
    ip: str
    port: int
    name: str | None = None


class RegisterOut(BaseModel):
    id: UUID


class ClientOut(BaseModel):
    id: UUID
    name: str


class ClientListOut(BaseModel):
    clients: list[ClientOut]
