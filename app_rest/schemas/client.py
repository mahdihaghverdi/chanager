from pydantic import BaseModel


class CPUOut(BaseModel):
    cpu_percents: list[float]


class MemoryOut(BaseModel):
    total: str
    available: str
    usage: float
