import asyncio
import random
from attr import dataclass
from datetime import date
from logging import warn, info
from math import floor
from typing import Dict, FrozenSet, Iterable, List, NamedTuple, NewType, Optional, Set, Union, Any, Tuple

from maubot import MessageEvent, Plugin
from maubot.handlers import command
from mautrix.errors.request import MNotFound
from mautrix.types.event.encrypted import EncryptionAlgorithm
from mautrix.types.event.type import EventType
from mautrix.types.primitive import RoomID, UserID
from mautrix.types.users import Member
from mautrix.types.event.state import RoomEncryptionStateEventContent, StateEventContent
from mautrix.types.util.serializable_attrs import SerializableAttrs
from mautrix.types.util.obj import Obj, Lst

class SimpleMember(NamedTuple):
    display_name: str
    mxid: str

Donut = NewType("Donut", Set[FrozenSet[SimpleMember]])

donut_state_event = EventType.find("net.hyperflux.donutbot.donut_state",
                                        t_class=EventType.Class.STATE)

@dataclass
class DonutStateEventContent(SerializableAttrs):
    last_donut: Donut
    current_donut: Donut

def _str_to_int(s: str) -> Union[int, None]:
    try:
        return int(s)
    except(ValueError):
        return None

class DonutBot(Plugin):
    proposed_donuts: Dict[RoomID, Donut] = dict()

    #### Getting and setting Matrix room state ####

    async def get_members(self, evt: MessageEvent) -> List[SimpleMember]:
        room_id = evt.room_id
        new_members = (await evt.client.get_joined_members(room_id)).items()
        def item_to_simple_member(i: Tuple[UserID, Member]) -> SimpleMember:
            return SimpleMember(display_name=i[1].displayname, mxid=i[0]) # type: ignore
        simple_members = [item_to_simple_member(i) for i in new_members if i[0] != evt.client.mxid]
        return simple_members

    async def get_donut_state(self, room_id: RoomID) -> Union[StateEventContent, None]:
        try:
            return await self.client.get_state_event(room_id, donut_state_event)
        except MNotFound:
            return None

    async def get_last_donut(self, room_id: RoomID) -> Optional[Donut]:
        donut_state = await self.get_donut_state(room_id)
        if (donut_state and isinstance(donut_state, Obj)):
            last_donut = donut_state.get("last_donut")
            if last_donut:
                return _json_to_donut(last_donut)
        return None

    async def get_current_donut(self, room_id: RoomID) -> Optional[Donut]:
        donut_state = await self.get_donut_state(room_id)
        if (donut_state and isinstance(donut_state, Obj)):
            current_donut = donut_state.get("current_donut")
            if current_donut:
                return _json_to_donut(current_donut)
        return None

    async def set_current_donut(self, donut: Donut, room_id: RoomID):
        donut_state = await self.get_donut_state(room_id)
        if not donut_state:
            donut_state = Obj()
        old_donut = await self.get_current_donut(room_id)
        if old_donut:
            donut_state["last_donut"] = _donut_to_json(old_donut)
        donut_state["current_donut"] = _donut_to_json(donut)
        await self.client.send_state_event(room_id=room_id, 
                                           event_type=donut_state_event, 
                                           content=donut_state)

    async def invite_users_to_donut(self, donut: Donut):
        await asyncio.gather(*(self.create_donut_room(group) for group in donut))

    async def create_donut_room(self, group: Iterable[SimpleMember]):
        invitees = [UserID(m.mxid) for m in group]
        room_name = "DONUT! {}".format(date.today().strftime("%B %d, %Y"))
        initial_state: List[Dict[str, Any]] = [{
            "content": {"history_visibility": "invited"}, 
            "type": "m.room.history_visibility",
            "state_key": "",
        }]
        new_room_id = await self.client.create_room(
            name=room_name, 
            invitees=invitees, 
            initial_state=initial_state, # type: ignore
        )
        # Ensure the bot is in the room
        await self.client.join_room(new_room_id)
        await self.client.send_text(
            new_room_id,
            "Welcome to DONUT! Please use this room to coordinate a friendly chat and "
            "the consumption of doughnuts!!!",
        )
        info(f"Users {invitees} invited to room {new_room_id}")
        await self.client.send_state_event(
            new_room_id,
            EventType.ROOM_ENCRYPTION,
            RoomEncryptionStateEventContent(EncryptionAlgorithm.MEGOLM_V1),
        )

    #### Bot Commands ####

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
        await evt.respond(_format_donut(new_donut, "New PROPOSED DONUT: (`!donut confirm` to confirm)"))

    @base_command.subcommand(help="Confirm new DONUT")
    async def confirm(self, evt: MessageEvent) -> None:
        room_id = evt.room_id
        proposed_donut = self.proposed_donuts.get(room_id)
        if (proposed_donut):
            try:
                await self.set_current_donut(proposed_donut, room_id)
                info("New DONUT saved for room_id: " + room_id);
            except Exception as e:
                await evt.respond("Error saving state: " + str(e))
                warn("Error saving DONUT for room_id " + room_id, e);
                return
            await evt.respond(_format_donut(proposed_donut, "Newly proposed DONUT created!"))
            try:
                await self.invite_users_to_donut(proposed_donut)
                info("Everyone invited for DONUT in room_id: " + room_id);
            except Exception as e:
                await evt.respond("Error inviting everyone to DONUT: " + str(e))
                warn("Error inviting everyone to DONUT for room_id " + room_id, e);
                return
            await evt.respond(_format_donut(proposed_donut, "Everyone invited to DONUT rooms!"))
            self.proposed_donuts.pop(room_id)
        else:
            await evt.respond("No DONUT currently proposed. Use `!donut new` to make a new one")

    @base_command.subcommand(help="View the current DONUT")
    async def current(self, evt: MessageEvent) -> None:
        d = await self.get_current_donut(evt.room_id)
        if d:
            await evt.respond(_format_donut(d))
        else:
            await evt.respond("No DONUT in progress. Use `!donut new` to make a new one")

    @base_command.subcommand(help="View the previous DONUT")
    async def previous(self, evt: MessageEvent) -> None:
        d = await self.get_last_donut(evt.room_id)
        if d:
            await evt.respond(_format_donut(d))
        else:
            await evt.respond("No previous DONUT. Use `!donut new` to make a new one")

    @base_command.subcommand(help="Generate a sample DONUT")
    @command.argument("group_size", required=False, parser=_str_to_int)
    async def sample(self, evt: MessageEvent, group_size: Union[int, None] = None) -> None:
        group_size = group_size if group_size != None else 2
        d = _generate_donut(await self.get_members(evt), group_size)
        await evt.respond(_format_donut(d))

def _json_to_donut(jsonDonut: Lst) -> Donut:
    newDonut = Donut(set())
    for jsonGroup in jsonDonut:
        newGroup: Set[SimpleMember] = set()
        for jsonMember in jsonGroup:
            newMember = SimpleMember(jsonMember.display_name, jsonMember.mxid)
            newGroup.add(newMember)
        newDonut.add(frozenset(newGroup))
    return newDonut

def _donut_to_json(donut: Donut) -> Lst:
    newJsonDonut: List[List[Obj]] = list()
    for group in donut:
        newJsonGroup: List[Obj] = list()
        for member in group:
            newJsonMember = Obj()
            newJsonMember["display_name"] = member.display_name
            newJsonMember["mxid"] = member.mxid
            newJsonGroup.append(newJsonMember)
        newJsonDonut.append(newJsonGroup)
    return Lst(newJsonDonut)

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
