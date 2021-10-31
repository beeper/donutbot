from math import floor
import random
from typing import Dict, FrozenSet, List, NamedTuple, NewType, Set, Union, Optional

from maubot import MessageEvent, Plugin
from maubot.handlers import command, event
from mautrix.types import RoomID, StateEvent, EventType, GenericEvent

class SimpleMember(NamedTuple):
    display_name: str
    mxid: str

Donut = NewType("Donut", Set[FrozenSet[SimpleMember]])

old_donut_state_event = EventType.find("net.hyperflux.donutbot.old_donut",
                              t_class=EventType.Class.STATE)

def _str_to_int(s: str) -> Union[int, None]:
    try:
        return int(s)
    except(ValueError):
        return None

class DonutBot(Plugin):
    proposed_donuts: Dict[RoomID, Donut] = dict()

    async def get_members(self, evt: MessageEvent) -> List[SimpleMember]:
        room_id = evt.room_id
        new_members = await evt.client.get_members(room_id)
        def state_event_to_simple_member(s: StateEvent) -> SimpleMember:
            return SimpleMember(display_name=s.content.displayname, mxid=s.state_key) # type: ignore
        simple_members = [state_event_to_simple_member(s) for s in new_members if s.state_key != evt.client.mxid]
        return simple_members

    async def get_last_donut(self, room_id: RoomID) -> Optional[Donut]:
        return None

    @command.new(name="donut", require_subcommand=True)
    async def base_command(self):
        pass

    @base_command.subcommand(help="List members in THE DONUT")
    async def list(self, evt: MessageEvent) -> None:
        members = await self.get_members(evt)
        if members:
            await evt.respond("Members in THE DONUT:\n" + _format_members(members))
        else:
            await evt.respond("No members found in THE DONUT")

    @base_command.subcommand(help="Start a new DONUT")
    @command.argument("group_size", required=False, parser=_str_to_int)
    async def new(self, evt: MessageEvent, group_size: Union[int, None] = None) -> None:
        group_size = group_size if group_size != None else 2
        room_id = evt.room_id
        new_donut = _generate_donut(await self.get_members(evt), group_size)
        last_donut = await self.get_last_donut(room_id)
        if (last_donut):
            for _ in range(10):
                if _are_donuts_overlapping(last_donut, new_donut):
                    new_donut = _generate_donut(await self.get_members(evt), group_size)
                    break
        self.proposed_donuts[room_id] = new_donut
        await evt.respond(_format_donut(new_donut, "New PROPOSED Donut: (`!donut confirm` to confirm)"))

    @base_command.subcommand(help="Generate a sample DONUT")
    @command.argument("group_size", required=False, parser=_str_to_int)
    async def sample(self, evt: MessageEvent, group_size: Union[int, None] = None) -> None:
        group_size = group_size if group_size != None else 2
        d = _generate_donut(await self.get_members(evt), group_size)
        await evt.respond(_format_donut(d))

    @base_command.subcommand(help="Test overlap")
    @command.argument("group_size", required=False, parser=_str_to_int)
    async def overlap(self, evt: MessageEvent, group_size: Union[int, None] = None) -> None:
        group_size = group_size if group_size != None else 2
        members = await self.get_members(evt)
        d1 = _generate_donut(members, group_size)
        d2 = _generate_donut(members, group_size)
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

def _format_donut(donut: Donut, message: str = "") -> str:
    if len(message) > 0:
        message = message + "\n"
    for group in donut:
        message = message + " - "
        message = message + ", ".join([(m.display_name if m.display_name else m.mxid) for m in group])
        message = message + "\n"
    return message

def _format_members(member_list: List[SimpleMember]) -> str:
    s: str = ""
    for m in member_list:
        s = s + " - " + (m.display_name if m.display_name else m.mxid) + "\n"
    return s
