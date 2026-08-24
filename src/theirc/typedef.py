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
from collections.abc import Callable, Generator, Iterable, Sequence
from collections.abc import Set as AbstractSet
from typing import Any, Literal, Protocol, TypeAlias, overload, runtime_checkable

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
	reactor: Any
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
class URLExtractType(Protocol):
	"""Protocol for URLExtract."""

	def __init__(
		self,
		extract_email: bool = False,
		cache_dns: bool = True,
		extract_localhost: bool = True,
		limit: int = ...,
		allow_mixed_case_hostname: bool = True,
		**kwargs: Any,
	) -> None: ...

	@overload
	def find_urls(
		self,
		text: str,
		only_unique: bool = ...,
		check_dns: bool = ...,
		get_indices: Literal[False] = ...,
		with_schema_only: bool = ...,
	) -> list[str]: ...

	@overload
	def find_urls(
		self,
		text: str,
		only_unique: bool = ...,
		check_dns: bool = ...,
		*,
		get_indices: Literal[True],
		with_schema_only: bool = ...,
	) -> list[tuple[str, tuple[int, int]]]: ...

	@overload
	def find_urls(
		self,
		text: str,
		only_unique: bool = ...,
		check_dns: bool = ...,
		get_indices: bool = ...,
		with_schema_only: bool = ...,
	) -> list[str | tuple[str, tuple[int, int]]]: ...

	@overload
	def gen_urls(
		self,
		text: str,
		check_dns: bool = ...,
		get_indices: Literal[False] = ...,
		with_schema_only: bool = ...,
	) -> Generator[str, None, None]: ...

	@overload
	def gen_urls(
		self,
		text: str,
		check_dns: bool = ...,
		*,
		get_indices: Literal[True],
		with_schema_only: bool = ...,
	) -> Generator[tuple[str, tuple[int, int]], None, None]: ...

	@overload
	def gen_urls(
		self,
		text: str,
		check_dns: bool = ...,
		get_indices: bool = ...,
		with_schema_only: bool = ...,
	) -> Generator[str | tuple[str, tuple[int, int]], None, None]: ...

	def has_urls(
		self,
		text: str,
		check_dns: bool = False,
		with_schema_only: bool = False,
	) -> bool: ...

	def update(self) -> bool: ...

	def update_when_older(self, days: int) -> bool: ...

	def add_enclosure(self, left_char: str, right_char: str) -> None: ...

	def remove_enclosure(self, left_char: str, right_char: str) -> None: ...

	def get_enclosures(self) -> set[tuple[str, str]]: ...

	def get_after_tld_chars(self) -> list[str]: ...

	def set_after_tld_chars(self, after_tld_chars: Iterable[str]) -> None: ...

	def get_stop_chars_left(self) -> set[str]: ...

	def set_stop_chars_left(self, stop_chars: AbstractSet[str]) -> None: ...

	def get_stop_chars_right(self) -> set[str]: ...

	def set_stop_chars_right(self, stop_chars: AbstractSet[str]) -> None: ...

	def get_stop_chars_left_from_scheme(self) -> set[str]: ...

	def set_stop_chars_left_from_scheme(self, stop_chars: AbstractSet[str]) -> None: ...

	def load_ignore_list(self, file_name: str) -> None: ...

	def load_permit_list(self, file_name: str) -> None: ...

	@property
	def ignore_list(self) -> set[str]: ...

	@ignore_list.setter
	def ignore_list(self, value: AbstractSet[str]) -> None: ...

	@property
	def permit_list(self) -> set[str]: ...

	@permit_list.setter
	def permit_list(self, value: AbstractSet[str]) -> None: ...

	@property
	def extract_email(self) -> bool: ...

	@extract_email.setter
	def extract_email(self, value: bool) -> None: ...

	@property
	def extract_localhost(self) -> bool: ...

	@extract_localhost.setter
	def extract_localhost(self, value: bool) -> None: ...

	@property
	def allow_mixed_case_hostname(self) -> bool: ...

	@allow_mixed_case_hostname.setter
	def allow_mixed_case_hostname(self, value: bool) -> None: ...

	@staticmethod
	def get_version() -> str: ...


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
class WXListBoxType(Protocol):
	"""Protocol for wx.ListBox methods we use."""

	def SetName(self, name: str) -> None: ...

	def Bind(
		self,
		event: Any,
		handler: Callable[..., Any],
		source: Any = None,
		id: int = -1,  # wx.ID_ANY  # NOQA: A002
		id2: int = -1,  # wx.ID_ANY
	) -> None: ...

	def GetString(self, n: int) -> str: ...

	def GetSelection(self) -> int: ...

	def AppendItems(self, items: Sequence[str]) -> int: ...

	def Clear(self) -> None: ...

	def SetSelection(self, n: int) -> None: ...

	def SetFocus(self) -> None: ...

	def SetForegroundColour(self, colour: Any) -> bool: ...

	def SetBackgroundColour(self, colour: Any) -> bool: ...

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
	"URLExtractType",
	"WXListBoxType",
	"WXNotebookType",
]
