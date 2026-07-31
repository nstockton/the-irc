# Copyright (C) 2026 Nick Stockton
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Shared type definitions."""

# Future Modules:
from __future__ import annotations

# Built-in Modules:
import socket
from collections.abc import Callable, Generator, Iterable
from typing import Any, Protocol, TypeAlias, runtime_checkable

# Third-party Modules:
from knickknacks.typedef import Self


BatchFuncCallType: TypeAlias = tuple[tuple[Any, ...], dict[str, Any]]
SocketWrapperType: TypeAlias = Callable[[socket.socket], socket.socket]


@runtime_checkable
class FactoryType(Protocol):
	"""Socket factories."""

	bind_address: Any | None
	family: int
	wrapper: SocketWrapperType

	def __init__(
		self,
		bind_address: Any = None,
		wrapper: SocketWrapperType = ...,
		ipv6: bool = False,
	) -> None: ...

	def connect(self, server_address: Any) -> socket.socket: ...

	def __call__(self, server_address: Any) -> socket.socket: ...


@runtime_checkable
class NickMaskType(Protocol):
	"""A nickmask (the source of an Event)."""

	@classmethod
	def from_params(cls: type[Self], nick: str, user: str, host: str) -> Self: ...

	@property
	def nick(self) -> str: ...

	@property
	def userhost(self) -> str | None: ...

	@property
	def host(self) -> str | None: ...

	@property
	def user(self) -> str | None: ...

	@classmethod
	def from_group(cls: type[Self], group: str) -> Self | None: ...


@runtime_checkable
class IRCEventType(Protocol):
	"""Protocol for irc.client.Event with the attributes we access."""

	type: str
	target: str
	source: NickMaskType
	arguments: list[str]
	tags: list[dict[str, Any]]


@runtime_checkable
class ChannelType(Protocol):
	"""A class for keeping information about an IRC channel."""

	user_modes: str

	def __init__(self) -> None: ...

	def users(self) -> Iterable[str]: ...

	def opers(self) -> Iterable[str]: ...

	def voiced(self) -> Iterable[str]: ...

	def owners(self) -> Iterable[str]: ...

	def halfops(self) -> Iterable[str]: ...

	def admins(self) -> Iterable[str]: ...

	def has_user(self, nick: str) -> bool: ...

	def is_oper(self, nick: str) -> bool: ...

	def is_voiced(self, nick: str) -> bool: ...

	def is_owner(self, nick: str) -> bool: ...

	def is_halfop(self, nick: str) -> bool: ...

	def is_admin(self, nick: str) -> bool: ...

	def add_user(self, nick: str) -> None: ...

	@property
	def user_dicts(self) -> Generator[dict[str, Any], None, None]: ...

	def remove_user(self, nick: str) -> None: ...

	def change_nick(self, before: str, after: str) -> None: ...

	def set_userdetails(self, nick: str, details: Any) -> None: ...

	def set_mode(self, mode: str, value: str | None = None) -> None: ...

	def clear_mode(self, mode: str, value: str | None = None) -> None: ...

	def has_mode(self, mode: str) -> bool: ...

	def is_moderated(self) -> bool: ...

	def is_secret(self) -> bool: ...

	def is_protected(self) -> bool: ...

	def has_topic_lock(self) -> bool: ...

	def is_invite_only(self) -> bool: ...

	def has_allow_external_messages(self) -> bool: ...

	def has_limit(self) -> bool: ...

	def limit(self) -> str | None: ...

	def has_key(self) -> bool: ...


@runtime_checkable
class IRCServerConnectionType(Protocol):
	"""Protocol for irc.client.ServerConnection methods we use."""

	connected: bool
	handlers: dict[str, Callable[..., Any]]
	server: str

	def cap(self, subcommand: str, *args: Any) -> None: ...

	def join(self, channel: str, key: str = "") -> None: ...

	def part(self, channels: str | Iterable[str], message: str = "") -> None: ...

	def send_items(self, *items: Any) -> None: ...

	def quit(self, message: str = "") -> None: ...

	def disconnect(self, message: str = "") -> None: ...

	def get_server_name(self) -> str: ...

	def get_nickname(self) -> str: ...

	def whois(self, nick: str) -> None: ...

	def is_connected(self) -> bool: ...

	def nick(self, new_nick: str) -> None: ...

	def send_raw(self, raw: str) -> None: ...


@runtime_checkable
class WXNotebookType(Protocol):
	"""Protocol for wx.Notebook methods/properties we use."""

	def GetCurrentPage(self) -> Any | None: ...

	def GetPageText(self, idx: int) -> str: ...

	def GetSelection(self) -> int: ...

	def GetPageCount(self) -> int: ...

	def GetPage(self, idx: int) -> Any: ...

	def FindPage(self, page: Any) -> int: ...

	def SetSelection(self, idx: int) -> None: ...

	def AddPage(self, page: Any, text: str) -> None: ...

	def DeletePage(self, idx: int) -> None: ...


@runtime_checkable
class WXListCtrlType(Protocol):
	"""Protocol for wx.ListCtrl methods we use."""

	def GetFirstSelected(self) -> int: ...

	def GetItemText(self, idx: int) -> str: ...

	def GetItemCount(self) -> int: ...

	def InsertItem(self, idx: int, text: str) -> int: ...

	def DeleteAllItems(self) -> None: ...

	def Select(self, idx: int) -> None: ...

	def Focus(self, idx: int) -> None: ...

	def SetItemTextColour(self, idx: int, colour: Any) -> None: ...

	def SetItemBackgroundColour(self, idx: int, colour: Any) -> None: ...

	def Freeze(self) -> None: ...

	def Thaw(self) -> None: ...


__all__: list[str] = [
	"BatchFuncCallType",
	"ChannelType",
	"FactoryType",
	"IRCEventType",
	"IRCServerConnectionType",
	"NickMaskType",
	"Self",
	"SocketWrapperType",
	"WXListCtrlType",
	"WXNotebookType",
]
