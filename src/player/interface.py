"""The stable Python player contract and immutable JSON-compatible values."""
from collections.abc import Mapping
from enum import Enum
from collections.abc import Sequence
from collections.abc import Iterator
from typing import Any
from .types import PlayerView, PlayerEvent, GameResult, Action, ActionOption

PROTOCOL_VERSION = 1


class FrozenMap(Mapping[str, Any]):
    """Read-only snapshot supporting both mapping and attribute access."""
    __slots__ = ("__data",)
    __data: dict[str, Any]

    def __init__(self, values: Mapping[str, Any]) -> None:
        object.__setattr__(self, "_FrozenMap__data", {k: freeze(v) for k, v in values.items()})

    def __getitem__(self, key: str) -> Any:
        return self.__data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.__data)

    def __len__(self) -> int:
        return len(self.__data)

    def __getattr__(self, key: str) -> Any:
        try:
            return self[key]
        except KeyError as error:
            raise AttributeError(key) from error

    def __setattr__(self, key: str, value: Any) -> None:
        raise TypeError("Snapshots are read-only")


def freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return FrozenMap(value)
    if isinstance(value, (tuple, list)):
        return tuple(freeze(v) for v in value)
    if isinstance(value, Enum):
        return value.value
    return value


def thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: thaw(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [thaw(v) for v in value]
    if isinstance(value, Enum):
        return value.value
    return value


class Player:
    """One instance per seat. Only choose_action must be overridden.

    Return one offered action, or fill the documented fields of a constrained
    action (Trade, Counter or Discard). The engine owns validation and rules.
    on_event completes before the next choice and never returns an action.
    """
    protocol_version = PROTOCOL_VERSION

    def on_game_start(self, view: PlayerView) -> None:
        pass

    def on_event(self, event: PlayerEvent) -> None:
        pass

    def choose_action(self, view: PlayerView, options: Sequence[ActionOption]) -> Action:
        raise NotImplementedError

    def on_game_end(self, result: GameResult) -> None:
        pass
