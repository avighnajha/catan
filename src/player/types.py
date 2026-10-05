"""Public SDK schemas. No simulator, web, or third-party imports.

Snapshot protocols describe read-only attribute access. Action TypedDicts
describe wire fields: use key access for statically typed action narrowing.
These annotations do not change runtime validation or construct game objects.
"""
from collections.abc import Mapping
from typing import Any, Literal, Protocol, TypedDict, TypeAlias

PlayerId: TypeAlias = Literal['P1', 'P2', 'P3', 'P4']
TileId: TypeAlias = str
VertexId: TypeAlias = str
EdgeId: TypeAlias = str
PortId: TypeAlias = str
Resource: TypeAlias = Literal['WOOD', 'BRICK', 'SHEEP', 'WHEAT', 'ORE']
DevelopmentCard: TypeAlias = Literal['KNIGHT', 'ROAD_BUILDING', 'YEAR_OF_PLENTY', 'MONOPOLY', 'VICTORY_POINT']
BuildingType: TypeAlias = Literal['SETTLEMENT', 'CITY']
PortType: TypeAlias = Literal['THREE_TO_ONE', 'TWO_TO_ONE_WOOD', 'TWO_TO_ONE_BRICK', 'TWO_TO_ONE_SHEEP', 'TWO_TO_ONE_WHEAT', 'TWO_TO_ONE_ORE']
ResourceCounts: TypeAlias = Mapping[Resource, int]
GamePhase: TypeAlias = Literal['SETUP_FIRST', 'SETUP_SECOND', 'NORMAL_PLAY', 'GAME_OVER']
DecisionPhase: TypeAlias = Literal['SETUP_SETTLEMENT', 'SETUP_ROAD', 'PRE_ROLL', 'PLAYING', 'DISCARD', 'ROBBER', 'FREE_ROAD', 'PLENTY', 'MONOPOLY', 'TRADE_RESPONSE', 'TRADE_SELECT', 'GAME_OVER']
ResultStatus: TypeAlias = Literal['completed', 'stopped', 'player_failed', 'failed']


class Snapshot(Protocol):
    """Shared mapping access; named properties below give precise attribute types."""
    def __getitem__(self, key: str) -> Any: ...
    def get(self, key: str, default: Any = None) -> Any: ...


class Tile(Snapshot, Protocol):
    @property
    def resource(self) -> Resource | None: ...
    @property
    def number(self) -> int | None: ...
    @property
    def has_robber(self) -> bool: ...
    @property
    def vertices(self) -> tuple[VertexId, ...]: ...
    @property
    def edges(self) -> tuple[EdgeId, ...]: ...


class Vertex(Snapshot, Protocol):
    @property
    def x(self) -> float: ...
    @property
    def y(self) -> float: ...
    @property
    def neighbors(self) -> tuple[VertexId, ...]: ...
    @property
    def edges(self) -> tuple[EdgeId, ...]: ...
    @property
    def tiles(self) -> tuple[TileId, ...]: ...
    @property
    def port(self) -> PortId | None: ...
    @property
    def owner(self) -> PlayerId | None: ...
    @property
    def building(self) -> BuildingType | None: ...


class Edge(Snapshot, Protocol):
    @property
    def vertices(self) -> tuple[VertexId, VertexId]: ...
    @property
    def owner(self) -> PlayerId | None: ...


class Port(Snapshot, Protocol):
    @property
    def type(self) -> PortType: ...
    @property
    def vertices(self) -> tuple[VertexId, VertexId]: ...


class Board(Snapshot, Protocol):
    @property
    def tiles(self) -> Mapping[TileId, Tile]: ...
    @property
    def vertices(self) -> Mapping[VertexId, Vertex]: ...
    @property
    def edges(self) -> Mapping[EdgeId, Edge]: ...
    @property
    def ports(self) -> Mapping[PortId, Port]: ...
    @property
    def robber_tile(self) -> TileId: ...


class OpponentState(Snapshot, Protocol):
    """Public state only: deliberately no resources or development_cards map."""
    @property
    def player_id(self) -> PlayerId: ...
    @property
    def resource_count(self) -> int: ...
    @property
    def development_card_count(self) -> int: ...
    @property
    def victory_points(self) -> int: ...
    @property
    def roads_remaining(self) -> int: ...
    @property
    def settlements_remaining(self) -> int: ...
    @property
    def cities_remaining(self) -> int: ...
    @property
    def knights_played(self) -> int: ...
    @property
    def has_longest_road(self) -> bool: ...
    @property
    def has_largest_army(self) -> bool: ...


class SelfState(OpponentState, Protocol):
    @property
    def resources(self) -> ResourceCounts: ...
    @property
    def development_cards(self) -> Mapping[DevelopmentCard, int]: ...
    @property
    def new_development_cards(self) -> Mapping[DevelopmentCard, int]: ...


class TurnState(Snapshot, Protocol):
    @property
    def number(self) -> int: ...
    @property
    def current_player(self) -> PlayerId: ...
    @property
    def game_phase(self) -> GamePhase: ...
    @property
    def phase(self) -> DecisionPhase: ...
    @property
    def dice(self) -> int | None: ...


class TradeResponse(Snapshot, Protocol):
    @property
    def player_id(self) -> PlayerId: ...
    @property
    def give(self) -> ResourceCounts: ...
    @property
    def receive(self) -> ResourceCounts: ...


class TradeState(Snapshot, Protocol):
    @property
    def proposer(self) -> PlayerId: ...
    @property
    def give(self) -> ResourceCounts: ...
    @property
    def receive(self) -> ResourceCounts: ...
    @property
    def recipients(self) -> tuple[PlayerId, ...]: ...
    @property
    def responses(self) -> tuple[TradeResponse, ...]: ...


class PlayerView(Snapshot, Protocol):
    @property
    def protocol_version(self) -> int: ...
    @property
    def game_id(self) -> str: ...
    @property
    def player_id(self) -> PlayerId: ...
    @property
    def decision_id(self) -> int: ...
    @property
    def self(self) -> SelfState: ...
    @property
    def opponents(self) -> tuple[OpponentState, ...]: ...
    @property
    def board(self) -> Board: ...
    @property
    def bank(self) -> ResourceCounts: ...
    @property
    def development_deck_count(self) -> int: ...
    @property
    def turn(self) -> TurnState: ...
    @property
    def trade(self) -> TradeState | None: ...


class PlaceSettlementAction(TypedDict):
    type: Literal['PLACE_SETTLEMENT']
    vertex: VertexId

class PlaceRoadAction(TypedDict):
    type: Literal['PLACE_ROAD']
    edge: EdgeId

class BuildSettlementAction(TypedDict):
    type: Literal['BUILD_SETTLEMENT']
    vertex: VertexId

class BuildCityAction(TypedDict):
    type: Literal['BUILD_CITY']
    vertex: VertexId

class BuildRoadAction(TypedDict):
    type: Literal['BUILD_ROAD']
    edge: EdgeId

class BuildFreeRoadAction(TypedDict):
    type: Literal['BUILD_FREE_ROAD']
    edge: EdgeId

class RollAction(TypedDict):
    type: Literal['ROLL']

class BuyDevelopmentCardAction(TypedDict):
    type: Literal['BUY_DEVELOPMENT_CARD']

class PlayDevelopmentCardAction(TypedDict):
    type: Literal['PLAY_DEVELOPMENT_CARD']
    card: DevelopmentCard

class MoveRobberAction(TypedDict):
    type: Literal['MOVE_ROBBER']
    tile: TileId
    victim: PlayerId | None

class TakeResourcesAction(TypedDict):
    type: Literal['TAKE_RESOURCES']
    resources: ResourceCounts

class TakeMonopolyAction(TypedDict):
    type: Literal['TAKE_MONOPOLY']
    resource: Resource

class BankTradeAction(TypedDict):
    type: Literal['BANK_TRADE']
    give_resource: Resource
    receive_resource: Resource
    ratio: int

class TradeTemplate(TypedDict):
    type: Literal['TRADE']

class TradeAction(TypedDict):
    type: Literal['TRADE']
    recipients: list[PlayerId] | tuple[PlayerId, ...]
    give: ResourceCounts
    receive: ResourceCounts

class CounterTemplate(TypedDict):
    type: Literal['COUNTER']

class CounterAction(TypedDict):
    type: Literal['COUNTER']
    give: ResourceCounts
    receive: ResourceCounts

class DiscardTemplate(TypedDict):
    type: Literal['DISCARD']
    count: int

class DiscardAction(TypedDict):
    type: Literal['DISCARD']
    resources: ResourceCounts

class AcceptAction(TypedDict):
    type: Literal['ACCEPT']

class RejectAction(TypedDict):
    type: Literal['REJECT']

class SelectTradeAction(TypedDict):
    type: Literal['SELECT_TRADE']
    response: int

class CancelTradeAction(TypedDict):
    type: Literal['CANCEL_TRADE']

class EndTurnAction(TypedDict):
    type: Literal['END_TURN']

ConcreteAction: TypeAlias = PlaceSettlementAction | PlaceRoadAction | BuildSettlementAction | BuildCityAction | BuildRoadAction | BuildFreeRoadAction | RollAction | BuyDevelopmentCardAction | PlayDevelopmentCardAction | MoveRobberAction | TakeResourcesAction | TakeMonopolyAction | BankTradeAction | AcceptAction | RejectAction | SelectTradeAction | CancelTradeAction | EndTurnAction
Action: TypeAlias = ConcreteAction | TradeAction | CounterAction | DiscardAction
ActionOption: TypeAlias = ConcreteAction | TradeTemplate | CounterTemplate | DiscardTemplate


class GameResult(Snapshot, Protocol):
    @property
    def status(self) -> ResultStatus: ...
    @property
    def reason(self) -> str: ...
    @property
    def winner(self) -> PlayerId | None: ...
    @property
    def turn_count(self) -> int: ...
    @property
    def decisions(self) -> int: ...
    @property
    def engine_version(self) -> str: ...
    @property
    def protocol_version(self) -> int: ...


class PlayerEvent(Snapshot, Protocol):
    @property
    def sequence(self) -> int: ...
    @property
    def type(self) -> str: ...
    @property
    def player_id(self) -> PlayerId | None: ...
    @property
    def turn_number(self) -> int: ...
    @property
    def data(self) -> Mapping[str, Any]: ...


class ResourcesProducedData(TypedDict):
    resources: ResourceCounts

class DiceRolledData(TypedDict):
    die1: int
    die2: int
    total: int

class TradeCompletedData(TypedDict):
    responder: PlayerId
    give: ResourceCounts
    receive: ResourceCounts

__all__ = ['PlayerId', 'TileId', 'VertexId', 'EdgeId', 'PortId', 'Resource', 'DevelopmentCard', 'BuildingType', 'PortType', 'ResourceCounts', 'GamePhase', 'DecisionPhase', 'ResultStatus', 'Snapshot', 'Tile', 'Vertex', 'Edge', 'Port', 'Board', 'OpponentState', 'SelfState', 'TurnState', 'TradeResponse', 'TradeState', 'PlayerView', 'PlaceSettlementAction', 'PlaceRoadAction', 'BuildSettlementAction', 'BuildCityAction', 'BuildRoadAction', 'BuildFreeRoadAction', 'RollAction', 'BuyDevelopmentCardAction', 'PlayDevelopmentCardAction', 'MoveRobberAction', 'TakeResourcesAction', 'TakeMonopolyAction', 'BankTradeAction', 'TradeTemplate', 'TradeAction', 'CounterTemplate', 'CounterAction', 'DiscardTemplate', 'DiscardAction', 'AcceptAction', 'RejectAction', 'SelectTradeAction', 'CancelTradeAction', 'EndTurnAction', 'ConcreteAction', 'Action', 'ActionOption', 'GameResult', 'PlayerEvent', 'ResourcesProducedData', 'DiceRolledData', 'TradeCompletedData']
