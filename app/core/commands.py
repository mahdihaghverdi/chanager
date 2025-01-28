from enum import StrEnum, auto


class Commands(StrEnum):
    health_check = auto()
    list = auto()
    cpu = auto()
    memory = auto()
    profile = auto()
    processes = auto()
