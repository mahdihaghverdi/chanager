from enum import StrEnum, auto


class Commands(StrEnum):
    list = auto()
    cpu = auto()
    memory = auto()
    profile = auto()
    processes = auto()
    restart = auto()
