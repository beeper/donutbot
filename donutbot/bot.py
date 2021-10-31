from math import floor
import random
from typing import Dict, FrozenSet, List, NamedTuple, NewType, Set, Union

from maubot import MessageEvent, Plugin # type: ignore
from maubot.handlers import command # type: ignore
from mautrix.types import RoomID, StateEvent

class SimpleMember(NamedTuple):
    display_name: str
    mxid: str

Donut = NewType("Donut", Set[FrozenSet[SimpleMember]])

def _str_to_int(s: str) -> Union[int, None]:
    try:
        return int(s)
    except(ValueError):
        return None

class DonutBot(Plugin):
    members: Dict[RoomID, List[SimpleMember]] = dict()
    current_donuts: Dict[RoomID, Donut] = dict()
    last_donuts: Dict[RoomID, Donut] = dict()

    async def update_members(self, evt: MessageEvent) -> List[SimpleMember]:
        room_id = evt.room_id
        self.members[room_id] = []
        new_members = await evt.client.get_members(room_id)
        def state_event_to_simple_member(s: StateEvent) -> SimpleMember:
            return SimpleMember(display_name=s.content.displayname, mxid=s.state_key) # type: ignore
        self.members[room_id] = [state_event_to_simple_member(s) for s in new_members if s.state_key != evt.client.mxid]
        return self.members[room_id]

    @command.new(name="donut", require_subcommand=True)
    async def base_command(self):
        pass

    @base_command.subcommand(help="List members in THE DONUT")
    async def list(self, evt: MessageEvent) -> None:
        await self.update_members(evt)
        members = self.members.get(evt.room_id)
        if members:
            await evt.respond("Members in THE DONUT:\n" + _format_members(members))
        else:
            await evt.respond("No members found in THE DONUT")

    @base_command.subcommand(help="Start a new DONUT")
    async def new(self, evt: MessageEvent) -> None:
        room_id = evt.room_id
        current_donut = self.current_donuts.get(room_id)
        last_donut = self.last_donuts.get(room_id)
        if current_donut:
            self.last_donuts[room_id] = current_donut

    @base_command.subcommand(help="Generate a sample DONUT")
    @command.argument("group_size", required=False, parser=_str_to_int)
    async def sample(self, evt: MessageEvent, group_size: Union[int, None] = None) -> None:
        group_size = group_size if group_size != None else 2
        # pyright gets it right, but mypy thinks group_size is optional here, so ignore
        d = _generate_donut(await self.update_members(evt), group_size) # type: ignore
        await evt.respond(_format_donut(d))

    @base_command.subcommand(help="Test overlap")
    @command.argument("group_size", required=False, parser=_str_to_int)
    async def overlap(self, evt: MessageEvent, group_size: Union[int, None] = None) -> None:
        group_size = group_size if group_size != None else 2
        # pyright gets it right, but mypy thinks group_size is optional here, so ignore
        d1 = _generate_donut(await self.update_members(evt), group_size) # type: ignore
        d2 = _generate_donut(await self.update_members(evt), group_size) # type: ignore
        overlap = _are_donuts_overlapping(d1, d2)
        await evt.respond(_format_donut(d1))
        await evt.respond(_format_donut(d2))
        await evt.respond(str(overlap))

def _generate_donut(member_list: List[SimpleMember], group_size: int) -> Donut:
    random_list = member_list.copy()
    random.shuffle(random_list)
    donut: Donut = Donut(set())
    while len(random_list) > 0:
        group: Set[SimpleMember] = set()
        for _ in range(min(group_size, len(random_list))):
            group.add(random_list.pop())
        if 0 < len(random_list) <= floor(group_size/2):
            group.update(random_list)
            random_list.clear()
        donut.add(frozenset(group))
    return donut

def _are_donuts_overlapping(d1: Donut, d2: Donut) -> bool:
    for group in d1:
        if group in d2:
            return True
    return False

def _format_donut(donut: Donut) -> str:
    s: str = ""
    for group in donut:
        s = s + " - "
        s = s + ", ".join([(m.display_name if m.display_name else m.mxid) for m in group])
        s = s + "\n"
    return s

def _format_members(member_list: List[SimpleMember]) -> str:
    s: str = ""
    for m in member_list:
        s = s + " - " + (m.display_name if m.display_name else m.mxid) + "\n"
    return s
