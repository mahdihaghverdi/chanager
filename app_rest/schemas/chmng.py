from uuid import UUID

from pydantic import BaseModel, ConfigDict


class RegisterIn(BaseModel):
    ip: str
    port: int
    name: str | None = None


class RegisterOut(BaseModel):
    id: UUID


class ClientOut(BaseModel):
    id: UUID
    name: str

    model_config = ConfigDict(from_attributes=True)


class ClientListOut(BaseModel):
    clients: list[ClientOut]
