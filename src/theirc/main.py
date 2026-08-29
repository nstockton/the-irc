# Copyright (C) 2026 Nick Stockton
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
A minimalistic, accessible, cross-platform graphical IRC client for TheIRC.net.

This module implements a screen-reader accessible IRC client
using wxPython for the GUI, jaraco/irc for the protocol handling, and
speechlight for speech output. It supports modern IRCv3 features
including echo-message, labeled-response, CHATHISTORY, BATCH, and SASL authentication.
"""

# Future Modules:
from __future__ import annotations

# Built-in Modules:
import argparse
import dataclasses
import functools
import logging
import operator
import re
import ssl
import sys
import threading
import webbrowser
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from contextlib import suppress
from enum import auto
from pathlib import Path
from typing import Any, Final

# Third-party Modules:
import irc.bot
import irc.client
import irc.connection
import irc.events
import jaraco.functools
import pystray
import wx
from knickknacks.backports import StrEnum
from knickknacks.numbers import clamp
from knickknacks.typedef import override
from PIL import Image
from speechlight import speech
from urlextract import URLExtract

# Local Modules:
from .config import Config
from .sound import play_sound
from .typedef import (
	BatchFuncCallType,
	ChannelType,
	FactoryType,
	IRCEventType,
	IRCServerConnectionType,
	NickMaskType,
	PySTrayIconType,
	SocketWrapperType,
	URLExtractType,
	WXListBoxType,
	WXNotebookType,
)
from .utils import get_data_path, reduce_or


# Constants:
CONFIG_NAME: Final[str] = "config"
DEFAULT_SOUND_VOLUME: Final[int] = 50
SOUND_DIR: Final[Path] = get_data_path("sounds")
INCOMING_QUERY_CREATED_SOUND: Final[Path] = SOUND_DIR / "incoming_query_created.wav"
MENTIONED_SOUND: Final[Path] = SOUND_DIR / "mentioned.wav"
VOLUME_DOWN_SOUND: Final[Path] = SOUND_DIR / "volume_down.wav"
VOLUME_UP_SOUND: Final[Path] = SOUND_DIR / "volume_up.wav"
STATUS_TAB_NAME: Final[str] = "$status"
# Never open a query tab for these.
STATUS_LIKE_TARGETS: Final[frozenset[str]] = frozenset({STATUS_TAB_NAME, "*", "auth"})
PRIVILEGES: Final[dict[str, tuple[int, str]]] = {
	"owner": (5, "is_owner"),
	"admin": (4, "is_admin"),
	"operator": (3, "is_oper"),
	"half-operator": (2, "is_halfop"),
	"voice": (1, "is_voiced"),
}
WX_NOT_FOUND: Final[int] = wx.NOT_FOUND
UINT32_MAX: Final[int] = 0xFFFFFFFF
WORDS_REGEX: Final[re.Pattern[str]] = re.compile(r"(\s+|[.\u3002!\uff01?\uff1f;\uff1b:\uff1a,\u3001\uff0c]+)")
UTF8_CONTINUATION_MASK: Final[int] = 0xC0
UTF8_CONTINUATION_PREFIX: Final[int] = 0x80
NO_MORE: Final[str] = "NO MORE"  # Return this when IRCClient should stop handling an event.
WINDOW_TITLE: Final[str] = "The IRC"
DEFAULT_HOST: Final[str] = "irc.theirc.net"
DEFAULT_PORT: Final[int] = 6697
DEFAULT_CLIENT_ID: Final[str] = "computer"
DEFAULT_CONNECT_FACTORY: Final[FactoryType] = irc.connection.Factory()
DEFAULT_HISTORY_LENGTH: Final[int] = 1000  # CHATHISTORY request size
NUMERIC_MESSAGES: Final[dict[str, str]] = {
	# Due to the way jaraco/irc handles IRC events, if a name is associated with a numeric value in the
	# codes.txt file of jaraco/irc, that name must be used instead.
	"400": "Unknown error",
	"nosuchnick": "No such nick",  # 401
	"nosuchserver": "No such server",  # 402
	"nosuchchannel": "No such channel",  # 403
	"cannotsendtochan": "Cannot send to channel",  # 404
	"toomanychannels": "Too many channels",  # 405
	"wasnosuchnick": "Was no such nick",  # 406
	"toomanytargets": "Too many targets",  # 407
	"408": "No such service",
	"noorigin": "No origin",  # 409
	"invalidcapcmd": "Invalid CAP command",  # 410
	"norecipient": "No recipient",  # 411
	"notexttosend": "No text to send",  # 412
	"notoplevel": "No toplevel",  # 413
	"wildtoplevel": "Wild toplevel",  # 414
	"415": "Bad mask",
	"416": "Too many matches",
	"417": "Input line was too long",
	"unknowncommand": "Unknown command",  # 421
	"nomotd": "No MOTD",  # 422
	"noadmininfo": "No admin info",  # 423
	"fileerror": "File error",  # 424
	"nonicknamegiven": "No nickname given",  # 431
	"erroneusnickname": "Erroneous nickname",  # 432
	"nickcollision": "Nick collision",  # 436
	"unavailresource": "Resource temporarily unavailable",  # 437
	"usernotinchannel": "User not in channel",  # 441
	"notonchannel": "Not on channel",  # 442
	"useronchannel": "User already on channel",  # 443
	"nologin": "No login",  # 444
	"summondisabled": "SUMMON has been disabled",  # 445
	"usersdisabled": "USERS has been disabled",  # 446
	"notregistered": "Not registered yet",  # 451
	"needmoreparams": "Need more params for command",  # 461
	"alreadyregistered": "You may not reregister",  # 462
	"nopermforhost": "No permission for host",  # 463
	"passwdmismatch": "Password mismatch",  # 464
	"yourebannedcreep": "You are banned from this server",  # 465
	"youwillbebanned": "You will be banned",  # 466
	"keyset": "Channel key already set",  # 467
	"channelisfull": "Channel is full",  # 471
	"unknownmode": "Unknown mode",  # 472
	"inviteonlychan": "Invite-only channel",  # 473
	"bannedfromchan": "Banned from channel",  # 474
	"badchannelkey": "Bad channel key",  # 475
	"badchanmask": "Bad channel mask",  # 476
	"nochanmodes": "Channel does not support modes",  # 477
	"banlistfull": "Ban list is full",  # 478
	"cannotknock": "Cannot knock on channel",  # 480
	"noprivileges": "Permission denied - no privileges",  # 481
	"chanoprivsneeded": "Channel operator privileges needed",  # 482
	"cantkillserver": "You can't kill a server",  # 483
	"restricted": "Restricted",  # 484
	"uniqopprivsneeded": "Unique operator privileges needed",  # 485
	"nooperhost": "No O:line for your host",  # 491
	"noservicehost": "No service host",  # 492
	"umodeunknownflag": "Unknown user mode flag",  # 501
	"usersdontmatch": "Cannot change mode for other users",  # 502
	"524": "Help topic not found",
	"525": "Invalid channel key",
	"691": "STARTTLS failed",
	"696": "Invalid mode parameter",
	"723": "Insufficient privileges",
	"nicklocked": "Nickname is locked",  # 902
	"saslfail": "SASL authentication failed",  # 904
	"sasltoolong": "SASL message too long",  # 905
	"saslaborted": "SASL authentication aborted",  # 906
	"saslalready": "SASL authentication already in progress",  # 907
}


# Globals:
logger: Final[logging.Logger] = logging.getLogger(__name__)
url_extractor: Final[URLExtractType] = URLExtract()

# Update cached TLD list if older than 7 days.
url_extractor.update_when_older(7)


def get_numeric_name(numeric: str) -> str:
	"""
	Convert an IRC numeric code or name into its canonical event name.

	Accepts either a raw numeric string (e.g. "401" or " 433 ") or a
	friendly name (e.g. "nosuchnick"). Digit strings are zero-padded to
	three digits and looked up in ``irc.events.numeric``. If the input is
	already a recognized name in ``irc.events.codes``, it is returned unchanged.

	Args:
		numeric: A string containing either a numeric reply code or an IRC event name.

	Returns:
		The canonical event name (e.g. ``"nosuchnick"``)
		or the original padded numeric string if no friendly name is known.

	Raises:
		ValueError: If the input is neither a valid numeric code nor a recognized event name.
	"""
	numeric = numeric.strip().lower()
	if numeric.isdigit():
		numeric = f"{int(numeric):03d}"  # 0-pad to 3 digits.
		return str(irc.events.numeric.get(numeric, numeric))
	if numeric in irc.events.codes:
		# Numeric is already a valid name.
		return numeric
	raise ValueError(f"Numeric name not found: {numeric!r}")


def is_status_like(target: str) -> bool:
	"""
	Tests if a target is status-like and thus prevented from opening a query tab.

	Args:
		target: the target to test.

	Returns:
		True if target is status-like, False otherwise.
	"""
	if not target or target.casefold() in STATUS_LIKE_TARGETS:
		return True
	# Server names look like hostnames and are not channels.
	return not irc.client.is_channel(target) and "." in target


def extract_tags(tags: Sequence[Mapping[str, Any]]) -> dict[str, str]:
	"""
	Extract IRCv3 message tags into a simple key-value dictionary.

	Duplicate keys are logged as warnings and the last value wins.

	Args:
		tags: A sequence of tag dictionaries (as provided by the irc library).

	Returns:
		A dictionary mapping tag keys to their string values (empty string for missing/None values).
	"""
	result: dict[str, str] = {}
	for d in tags:
		if isinstance(d, Mapping):
			key = d.get("key")
			if not isinstance(key, str):
				logger.warning("Item in tags list contains missing or invalid key")
				continue
			value = d.get("value") or ""  # Missing or None values must be empty strings.
			if not isinstance(value, str):
				logger.warning("Item in tags list contains invalid value")
				continue
			if key in result:
				logger.debug(f"Duplicate tag key '{key}'; overwriting with new value")
			result[key] = value
	return result


def split_cap_params(arguments: Sequence[str]) -> tuple[str, bool, list[str]]:
	"""
	Split a CAP command's argument list into subcommand, continuation flag, and tokens.

	Handles both `CAP * LS :caps` and multiline `CAP * LS * :caps` forms.
	The leading `*` continuation marker (if present) is not treated as a capability.

	Args:
		arguments: event.arguments from a CAP event (subcommand first).

	Returns:
		A tuple containing subcommand, more_coming, and tokens.
	"""
	if not arguments:
		return "", False, []
	cmd, *rest = arguments
	more_coming = bool(rest and rest[0] == "*")
	if more_coming:
		rest = rest[1:]
	tokens = " ".join(rest).split()
	return cmd, more_coming, tokens


class DualAuthConnection(irc.client.ServerConnection):  # type: ignore[no-any-unimported, misc]
	"""
	Custom IRC server connection supporting both server password and SASL authentication.

	The jaraco/irc library passes the server password positionally as the 4th argument
	to connect(). We name the parameter `server_password` (instead of `password`) to
	distinguish it from the separate `sasl_password` while remaining fully compatible
	with SingleServerIRCBot, @save_method_args, and automatic reconnection logic.
	"""

	connected: bool
	handlers: dict[str, Callable[..., Any]]

	@jaraco.functools.save_method_args
	def connect(  # NOQA: PLR0913, PLR0917
		self,
		server: str,
		port: int,
		nickname: str,
		server_password: str | None = None,  # Name was originally 'password'.
		username: str | None = None,
		ircname: str | None = None,
		connect_factory: FactoryType = DEFAULT_CONNECT_FACTORY,
		sasl_login: str | None = None,
		sasl_password: str | None = None,
	) -> IRCServerConnectionType:
		"""
		Establish a connection to an IRC server with optional dual authentication.

		Args:
			server: Hostname or IP address of the IRC server.
			port: TCP port number (commonly 6667 or 6697 for TLS).
			nickname: Desired nickname on the server.
			server_password: Optional server password (sent via PASS command).
			username: Optional username (defaults to nickname).
			ircname: Optional "real name" / GECOS field (defaults to nickname).
			connect_factory: Factory used to create the socket (allows TLS wrapper injection).
			sasl_login: Account name for SASL PLAIN authentication.
			sasl_password: Account password for SASL PLAIN authentication.

		Returns:
			The connected server connection instance (self).

		Raises:
			irc.client.ServerConnectionError: If the socket connection fails.
		"""
		irc.client.log.debug(f"connect(server={server!r}, port={port!r}, nickname={nickname!r}, ...)")
		if self.connected:
			self.disconnect("Changing servers")
		self.buffer = self.buffer_class()
		self.handlers = {}
		self.real_server_name = ""
		self.real_nickname = nickname
		self.server = server
		self.port = port
		self.server_address = (server, port)
		self.nickname = nickname
		self.username = username or nickname
		self.ircname = ircname or nickname
		self.server_password = server_password
		self.connect_factory = connect_factory
		self.sasl_login = sasl_login
		self.password = sasl_password  # Used internally by SASL state machine.
		try:
			self.socket = self.connect_factory(self.server_address)
		except OSError as e:
			raise irc.client.ServerConnectionError(f"Couldn't connect to socket: {e}") from e
		self.connected = True
		self.reactor._on_connect(self.socket)  # NOQA: SLF001
		if self.server_password:
			self.pass_(self.server_password)
		if self.sasl_login and self.password:
			# Note that the SASL-related stuff is defined internally in irc.client.ServerConnection.
			# Do *not* use the library's _sasl_cap_ls/_sasl_cap_req steps. Those issue a separate
			# `CAP REQ sasl` which races with IRCClient.on_cap's combined REQ, triggering AUTHENTICATE twice.
			self._sasl_step = None
			self._sasl_offered = False
			self._sasl_auth_started = False
			for i in ["cap", "authenticate", "saslsuccess", "saslfail"]:
				self.add_global_handler(i, self._sasl_state_machine, -42)
			self._sasl_step = self._sasl_wait_caps
		# In the original connect function, CAP LS was
		# Inside the SASL initialization code above. We move it outside the block so
		# The code can be used to initiate IRCv3 features when SASL is not used.
		# CAP LS 302 so servers advertise capability values (e.g. sasl=PLAIN).
		self.cap("LS", "302")
		self.nick(self.nickname)
		self.user(self.username, self.ircname)
		return self

	def _sasl_wait_caps(self, event: IRCEventType) -> None:
		"""
		SASL state-machine step that does not send CAP REQ.

		IRCClient.on_cap issues one combined CAP REQ (including sasl when configured).
		This step only watches LS/ACK/NAK so AUTHENTICATE PLAIN is started exactly once.

		Args:
			event: The event from IRCClient.on_cap.
		"""
		if event.type != "cap" or not event.arguments:
			return
		cmd, more_coming, tokens = split_cap_params(event.arguments)
		cmd = cmd.upper()
		names = {
			token.split("=", maxsplit=1)[0].lower() for token in tokens if token and not token.startswith("-")
		}
		failed: IRCEventType
		if cmd == "LS":
			if "sasl" in names:
				self._sasl_offered = True
			if not more_coming and not self._sasl_offered:
				failed = irc.client.Event("login_failed", event.target, ["server does not support sasl"])
				self._handle_event(failed)
				# Do not CAP END here: IRCClient.on_cap still needs to REQ any
				# non-SASL caps and will end negotiation after that ACK/NAK.
			return
		if cmd == "ACK":
			if "sasl" in names and not self._sasl_auth_started:
				self._sasl_auth_started = True
				self.send_items("AUTHENTICATE", "PLAIN")
				self._sasl_step = self._sasl_auth_plain
			return
		if cmd == "NAK" and (not names or "sasl" in names):
			failed = irc.client.Event("login_failed", event.target, ["server refused sasl protocol"])
			self._handle_event(failed)
			self._sasl_end()


# Tell the library to use the dual-auth connection class.
irc.client.Reactor.connection_class = DualAuthConnection


class StoppableExponentialBackoff(irc.bot.ExponentialBackoff):  # type: ignore[no-any-unimported, misc]
	"""
	Exponential backoff reconnection strategy that can be explicitly stopped.

	Used by IRCClient to allow clean shutdown without further reconnection attempts.
	"""

	def __init__(self, *args: Any, **kwargs: Any) -> None:
		"""Initialize the backoff timer with stop support."""
		super().__init__(*args, **kwargs)
		self._finished: threading.Event = threading.Event()

	def stop(self) -> None:
		"""Signal that no further reconnection attempts should be made."""
		self._finished.set()

	@override
	def run(self, *args: Any, **kwargs: Any) -> None:
		"""Run the backoff loop unless a stop has been requested."""
		if not self._finished.is_set():
			super().run(*args, **kwargs)

	@override
	def check(self) -> None:
		"""
		Do not reconnect if stop has been requested.

		The parent check calls jump_server if not connected,
		so a timer scheduled before stop could otherwise reconnect after quit/disconnect.
		"""
		if self._finished.is_set():
			self._check_scheduled = False
			return
		super().check()


class BatchTypeEnum(StrEnum):
	"""Supported IRC message batch types."""

	UNKNOWN = auto()
	CHATHISTORY = auto()
	LABELED_RESPONSE = auto()


@dataclasses.dataclass(frozen=True, slots=True)
class BatchInfo:
	"""Holds information about a message batch."""

	id: str
	"""The batch ID."""
	tags: dict[str, str] = dataclasses.field(default_factory=dict)
	"""The IRCv3 tags at the start of the batch."""
	type: BatchTypeEnum = BatchTypeEnum.UNKNOWN
	"""The type of message batch."""
	params: tuple[str, ...] = dataclasses.field(default_factory=tuple)
	"""Any additional parameters from the server."""


@dataclasses.dataclass(slots=True)
class MessageInfo:
	"""Holds information about a message."""

	text: str
	"""The text of the message."""
	target: str
	"""The target channel or nickname."""
	sender: str
	"""The nickname of the message sender."""
	history_target: str | None = None
	"""When set, contains the target channel or nickname for a history batch."""
	is_notice: bool = False
	"""True if message is notice."""
	is_action: bool = False
	"""True for CTCP ACTION messages."""
	is_mentioned: bool = False
	"""True if the user was mentioned in the text."""
	is_local_echo: bool = False
	"""True if the text is locally echoed input from the user."""
	is_batch_start: bool = False
	"""True for first message of a batch."""

	@property
	def is_channel(self) -> bool:
		"""True if message target is a channel, False otherwise."""
		return bool(irc.client.is_channel(self.target))

	@property
	def folded_text(self) -> str:
		"""The case-folded message text."""
		return self.text.casefold()

	@property
	def folded_target(self) -> str:
		"""The case-folded target."""
		return self.target.casefold()

	@property
	def folded_sender(self) -> str:
		"""The case-folded sender."""
		return self.sender.casefold()

	@property
	def folded_history_target(self) -> str:
		"""The case-folded history target."""
		return self.history_target.casefold() if self.history_target is not None else ""

	@property
	def formatted_text(self) -> str:
		"""The formatted message string."""
		if not self.sender:
			return self.text
		if self.is_action:
			return f"* {self.sender} {self.text}"
		return f"<{self.sender}> {self.text}"


class IRCClient(irc.bot.SingleServerIRCBot):  # type: ignore[no-any-unimported, misc] # NOQA: PLR0904
	"""
	Main IRC client logic built on SingleServerIRCBot.

	Handles connection lifecycle, IRCv3 capabilities (echo-message, labeled-response,
	chathistory, etc.), message routing, nick collision recovery, and integration
	with the wxPython GUI.
	"""

	channels: dict[str, ChannelType]
	connection: IRCServerConnectionType

	def __init__(  # NOQA: PLR0913
		self,
		*,
		gui: Any,
		server: str,
		port: int,
		nickname: str,
		server_password: str | None = None,
		sasl_login: str | None = None,
		sasl_password: str | None = None,
		client_id: str | None = None,
		use_tls: bool = False,
		verify_ssl: bool = True,
	) -> None:
		"""
		Initialize the IRC client and prepare the connection factory.

		Args:
			gui: Reference to the MainFrame instance for GUI callbacks.
			server: IRC server hostname.
			port: Server port.
			nickname: Desired nickname.
			server_password: Optional PASS password.
			sasl_login: SASL account name.
			sasl_password: SASL account password.
			client_id: The client ID (device name).
			use_tls: Whether to use TLS/SSL.
			verify_ssl: Whether to verify the server certificate (ignored if use_tls=False).
		"""
		self.gui: Any = gui
		self._is_reactor_stopped: threading.Event = threading.Event()
		self._cap_end_sent: bool = False
		self._pending_ls_caps: set[str] = set()
		self._desired_caps: set[str] = {
			"echo-message",
			"message-tags",
			"server-time",
			"batch",
			"labeled-response",
			"draft/chathistory",
			"chathistory",
		}
		if sasl_password:
			# We need to include sasl so on_cap sends one combined CAP REQ,
			# otherwise its separate REQ breaks the state machine's ACK check.
			self._desired_caps.add("sasl")
			if not sasl_login:
				sasl_login = nickname
			if client_id:
				sasl_login += f"@{client_id}"
		self._our_nick_mask: NickMaskType = irc.client.NickMask()
		self.feature_list: dict[str, str] = {}
		self.batches: dict[str, Any] = {}
		self.listed_channels: list[tuple[str, str, str]] = []
		self._shutdown_callback: Callable[[], None] | None = None
		self._list_callback: Callable[[Sequence[tuple[str, str, str]]], None] | None = None
		# Nick collision handling
		self._base_nickname: str = nickname
		self._sasl_deferred_nick_collision: bool = False
		self._nick_attempt: int = 0
		# IRCv3 capability flags
		self.echo_message_enabled: bool = False
		self.chathistory_enabled: bool = False
		self.labeled_response_enabled: bool = False
		# For labeled-response echo correlation (preferred, exact match).
		self._label_counter: int = -1
		self._our_labels: set[str] = set()
		# Fallback text-based tracking for servers without labeled-response.
		self._pending_echo_counts: defaultdict[str, int] = defaultdict(int)
		# Register generic handlers for supported numeric events.
		for code in NUMERIC_MESSAGES:
			method_name = f"on_{get_numeric_name(code)}"
			if not hasattr(self, method_name):
				setattr(self, method_name, self._on_generic_numeric)
		# TLS setup.
		connect_factory: FactoryType
		if use_tls:
			context: ssl.SSLContext = ssl.create_default_context()
			if not verify_ssl:
				context.check_hostname = False
				context.verify_mode = ssl.CERT_NONE
				logger.debug("Using lenient TLS context (no certificate verification)")
			wrapper: SocketWrapperType = functools.partial(context.wrap_socket, server_hostname=server)
			connect_factory = irc.connection.Factory(wrapper=wrapper)
		else:
			connect_factory = irc.connection.Factory()
		# Initialize parent classes.
		super().__init__(
			server_list=[(server, port, server_password)],
			nickname=nickname,
			realname=nickname,
			recon=StoppableExponentialBackoff(),
			connect_factory=connect_factory,
			sasl_login=sasl_login,
			sasl_password=sasl_password,
		)

	@property
	def is_sasl_in_progress(self) -> bool:
		"""True if SASL negotiation is currently in progress, False otherwise."""
		return bool(getattr(self.connection, "_sasl_step", None))

	def _maybe_cap_end(self) -> None:
		"""Send CAP END unless SASL still owns the remainder of negotiation."""
		if self._cap_end_sent:
			return
		sasl_offered = bool(getattr(self.connection, "_sasl_offered", False))
		# When SASL was advertised, DualAuthConnection._sasl_end sends CAP END on 903/fail.
		if "sasl" in self._desired_caps:
			if sasl_offered:
				return
			# Drop the waiting SASL handlers so they cannot END a second time.
			conn = self.connection
			conn._sasl_step = None  # NOQA: SLF001
			for name in ["cap", "authenticate", "saslsuccess", "saslfail"]:
				with suppress(Exception):
					conn.remove_global_handler(name, conn._sasl_state_machine)  # NOQA: SLF001
		self._cap_end_sent = True
		self.connection.cap("END")

	def on_login_failed(self, connection: IRCServerConnectionType, event: IRCEventType) -> None:
		"""
		Handle SASL unavailable or refused.

		Registration still continues unauthenticated; surface the failure on the status tab.

		Args:
			connection: The active server connection.
			event: The login_failed event.
		"""
		self.log_system_message(f"Login failed: {' '.join(event.arguments) or 'unknown reason'}")

	def log_system_message(self, msg: str) -> None:
		"""
		Append a system/status message to the status tab in the GUI thread.

		Args:
			msg: The message text.
		"""
		wx.CallAfter(self.gui.log_system_message, msg)

	def _on_generic_numeric(self, connection: IRCServerConnectionType, event: IRCEventType) -> None:
		"""
		Generic handler for numeric events.

		Args:
			connection: The active server connection.
			event: The event to handle.
		"""
		msg = NUMERIC_MESSAGES.get(event.type, f"Numeric reply {event.type}")
		info: str = event.arguments[-1] if event.arguments else ""
		self.log_system_message(f"{msg}: {info!r} ({event.type}).")

	def _update_our_nick_mask(self, nick_mask: NickMaskType) -> None:
		if nick_mask == self._our_nick_mask:
			return
		if nick_mask.nick == self.connection.get_nickname() and nick_mask.userhost is not None:
			self._our_nick_mask = nick_mask
			logger.debug(f"Updated nick mask: {nick_mask}")

	@override
	def _connect(self) -> None:
		"""Reset session flags and establish the socket."""
		self._cap_end_sent = False
		self._pending_ls_caps.clear()
		self.echo_message_enabled = False
		self.chathistory_enabled = False
		self.labeled_response_enabled = False
		self._our_labels.clear()
		self._pending_echo_counts.clear()
		self.feature_list.clear()
		self.batches.clear()
		super()._connect()

	@override
	def start(self) -> None:
		"""Run the IRC reactor until stop_reactor is called."""
		self._is_reactor_stopped.clear()
		self._connect()
		while not self._is_reactor_stopped.is_set():
			self.reactor.process_once(timeout=0.2)

	def stop_reactor(self) -> None:
		"""Stop reconnection attempts and request the reactor loop to exit."""
		self.recon.stop()
		self._is_reactor_stopped.set()

	def on_whoisuser(self, connection: IRCServerConnectionType, event: IRCEventType) -> None:
		"""
		Handle RPL_WHOISUSER (311) replies.

		Used to capture our own full hostmask (nick!user@host) for accurate
		byte-length calculations when splitting long messages.

		Args:
			connection: The active server connection.
			event: The whoisuser event.
		"""
		if len(event.arguments) < 3:
			return
		nick_mask: NickMaskType = irc.client.NickMask.from_params(*event.arguments[:3])
		self._update_our_nick_mask(nick_mask)

	def on_welcome(self, connection: IRCServerConnectionType, event: IRCEventType) -> None:
		"""
		Handle successful registration (RPL_WELCOME / 001).

		Args:
			connection: The active server connection.
			event: The welcome event.
		"""
		logger.debug("Server sent welcome (001) - fully connected!")
		self.log_system_message(f"Successfully connected to {connection.get_server_name()!r}.")
		wx.CallAfter(self.gui.update_server_menu_state)
		# Reset nick collision state now that registration (including any SASL)
		# has completed and the server has assigned our final nickname.
		self._sasl_deferred_nick_collision = False
		self._base_nickname = connection.get_nickname()
		self._nick_attempt = 0

	def on_featurelist(self, connection: IRCServerConnectionType, event: IRCEventType) -> None:
		"""
		Handle RPL_ISUPPORT (005) replies.

		Args:
			connection: The active server connection.
			event: The featurelist event.
		"""
		if not event.arguments:
			return
		for item in event.arguments[:-1]:
			if "=" in item:
				key, value = item.casefold().split("=", maxsplit=1)
			else:
				key = item.casefold()
				value = ""
			self.feature_list[key.strip()] = value.strip()

	def on_cap(self, connection: IRCServerConnectionType, event: IRCEventType) -> None:  # NOQA: PLR0912
		"""
		Process CAP LS/ACK/NAK replies and enable corresponding feature flags.

		Args:
			connection: The active server connection.
			event: The CAP event.
		"""
		if not event.arguments:
			return
		cmd, more_coming, caps_list = split_cap_params(event.arguments)
		cmd = cmd.upper()
		server_caps: set[str] = self._parse_capabilities(caps_list)
		if cmd == "LS":
			self._pending_ls_caps.update(server_caps)
			if more_coming:
				return
			to_request: list[str] = sorted(self._desired_caps.intersection(self._pending_ls_caps))
			self._pending_ls_caps.clear()
			if to_request:
				self.connection.cap("REQ", *to_request)
				return
			# Server advertised CAP but none of the caps we want. Still must END
			# or registration never completes.
			self._maybe_cap_end()
			return
		if cmd == "ACK":
			if "echo-message" in server_caps:
				self.echo_message_enabled = True
				logger.debug("[CAP] echo-message enabled")
			if "message-tags" in server_caps:
				logger.debug("[CAP] message-tags enabled")
			if "server-time" in server_caps:
				logger.debug("[CAP] server-time enabled")
			if "batch" in server_caps:
				logger.debug("[CAP] batch enabled")
			if "labeled-response" in server_caps:
				self.labeled_response_enabled = True
				logger.debug("[CAP] labeled-response enabled")
			if {"draft/chathistory", "chathistory"}.intersection(server_caps):
				self.chathistory_enabled = True
				logger.debug("[CAP] chathistory enabled")
		elif cmd == "NAK":
			logger.debug(f"[CAP] Server rejected: {caps_list!r}")
		else:
			logger.debug(f"[CAP] Server sent an unsupported CAP command: {cmd!r}")
			return
		self._maybe_cap_end()

	@staticmethod
	def _parse_capabilities(caps: Iterable[str]) -> set[str]:
		"""
		Parse raw capability strings from CAP LS or CAP ACK.

		Strips any values after `=` and ignores disabled capabilities (starting with `-`)
		and the CAP LS continuation marker `*`.

		Args:
			caps: An iterable of capabilities to parse.

		Returns:
			The available server capabilities.
		"""
		result: set[str] = set()
		for cap in caps:
			if not cap or cap == "*" or cap.startswith("-"):
				continue
			name = cap.split("=", maxsplit=1)[0]
			if name and name != "*":
				result.add(name)
		return result

	def on_disconnect(self, connection: IRCServerConnectionType, event: IRCEventType) -> None:
		"""
		Handle unexpected or requested disconnection from the server.

		Args:
			connection: The server connection that was closed.
			event: The disconnect event.
		"""
		self.log_system_message("Disconnected from IRC server.")
		wx.CallAfter(self.gui.close_all_non_status_tabs)
		wx.CallAfter(self.gui.update_server_menu_state)
		if self._shutdown_callback is not None:
			wx.CallAfter(self._shutdown_callback)
			self._shutdown_callback = None

	def get_nick_privs(self, channel_name: str, nick: str) -> tuple[str, ...]:
		"""
		Return the privilege names the given nick holds in the specified channel.

		Args:
			channel_name: The channel to inspect.
			nick: The nickname whose privileges are requested.

		Returns:
			Tuple of privilege names (e.g. ("owner", "operator")) sorted by descending rank.
		"""
		if channel_name not in self.channels:
			return ()
		ch = self.channels[channel_name]
		privs = [k for k, v in PRIVILEGES.items() if getattr(ch, v[1])(nick)]
		# Sort by descending rank so the highest privilege appears first.
		privs.sort(key=lambda k: PRIVILEGES[k][0], reverse=True)
		return tuple(privs)

	def on_join(self, connection: IRCServerConnectionType, event: IRCEventType) -> None:
		"""
		Handle JOIN events for both our own joins and other users.

		Args:
			connection: The active server connection.
			event: The JOIN event.
		"""
		self._update_our_nick_mask(event.source)
		target: str = event.target
		source_nick: str = event.source.nick
		our_nick: str = connection.get_nickname()
		if source_nick == our_nick:
			wx.CallAfter(self.gui.create_tab, target, auto_focus=True, update_nick_list=True)
		else:
			wx.CallAfter(self.gui.update_nick_list, target)

	def on_part(self, connection: IRCServerConnectionType, event: IRCEventType) -> None:
		"""
		Handle PART events.

		Args:
			connection: The active server connection.
			event: The PART event.
		"""
		target: str = event.target
		source_nick: str = event.source.nick
		our_nick: str = connection.get_nickname()
		if source_nick == our_nick:
			wx.CallAfter(self.gui.close_tab, target)
		else:
			wx.CallAfter(self.gui.update_nick_list, target)

	def on_quit(self, connection: IRCServerConnectionType, event: IRCEventType) -> None:
		"""
		Handle QUIT events.

		Args:
			connection: The active server connection.
			event: The QUIT event.
		"""
		source_nick: str = event.source.nick
		our_nick: str = connection.get_nickname()
		if source_nick == our_nick:
			wx.CallAfter(self.gui.close_all_non_status_tabs)
		else:
			for target in list(self.channels.keys()):
				# Slightly wasteful to be updating the nick list of every channel in the GUI,
				# but sadly the parent class already Removed the nick from every channel in
				# self.channels when its internal `_on_quic` method was called.
				wx.CallAfter(self.gui.update_nick_list, target)

	def on_nick(self, connection: IRCServerConnectionType, event: IRCEventType) -> None:
		"""
		Handle NICK change events.

		Args:
			connection: The active server connection.
			event: The NICK event.
		"""
		old_nick: str = event.source.nick
		new_nick: str = event.target
		nick_mask: NickMaskType
		nick_mask = irc.client.NickMask.from_params(new_nick, event.source.user, event.source.host)
		self._update_our_nick_mask(nick_mask)
		for target in list(self.channels.keys()):
			if self.channels[target].has_user(new_nick):
				wx.CallAfter(self.gui.update_nick_list, target)
		# Follow the remote party when they change nick so the query tab stays attached.
		if old_nick and old_nick != new_nick and old_nick != connection.get_nickname():
			wx.CallAfter(self.gui.rename_tab, old_nick, new_nick)

	def on_namreply(self, connection: IRCServerConnectionType, event: IRCEventType) -> None:
		"""
		Handle RPL_NAMREPLY (353) to populate the nick list.

		Args:
			connection: The active server connection.
			event: The NAMREPLY event.
		"""
		if len(event.arguments) < 3:
			return
		target: str = event.arguments[1]
		wx.CallAfter(self.gui.update_nick_list, target)

	def on_kick(self, connection: IRCServerConnectionType, event: IRCEventType) -> None:
		"""
		Handle KICK events.

		Args:
			connection: The active server connection.
			event: The KICK event.
		"""
		channel: str = event.target
		kicked: str = event.arguments[0]
		our_nick: str = connection.get_nickname()
		if kicked == our_nick:
			self.log_system_message(f"You were kicked from {channel}")
			wx.CallAfter(self.gui.close_tab, channel)
		else:
			wx.CallAfter(self.gui.update_nick_list, channel)

	def on_topic(self, connection: IRCServerConnectionType, event: IRCEventType) -> None:
		"""
		Handle TOPIC change events.

		Args:
			connection: The active server connection.
			event: The TOPIC event.
		"""
		channel = event.target
		topic = event.arguments[0] if event.arguments else ""
		self.log_system_message(f"Topic for {channel}: {topic}")

	def on_currenttopic(self, connection: IRCServerConnectionType, event: IRCEventType) -> None:  # RPL_TOPIC
		"""
		Handle RPL_TOPIC (332).

		Args:
			connection: The active server connection.
			event: The RPL_TOPIC event.
		"""
		# The library moves the recipient nick into event.target, so arguments should be [channel, topic].
		if len(event.arguments) >= 2:
			channel, *topic = event.arguments
			self.log_system_message(f"Topic for {channel}: {' '.join(topic)}")

	def on_mode(self, connection: IRCServerConnectionType, event: IRCEventType) -> None:
		"""
		Handle MODE changes that may affect channel privileges.

		Args:
			connection: The active server connection.
			event: The MODE event.
		"""
		channel_name: str = event.target
		if not irc.client.is_channel(channel_name) or channel_name not in self.channels:
			return
		wx.CallAfter(self.gui.update_nick_list, channel_name)

	def on_batch(self, connection: IRCServerConnectionType, event: IRCEventType) -> None:
		"""
		Handle supported BATCH start (+) and end (-) markers.

		Args:
			connection: The active server connection.
			event: The BATCH event.
		"""
		if not event.target:
			return
		batch_id: str = event.target[1:]
		if event.target.startswith("+"):
			logger.debug(f"[BATCH] Started batch {batch_id}")
			batch_type: BatchTypeEnum = BatchTypeEnum.UNKNOWN
			with suppress(Exception):
				batch_type = BatchTypeEnum(event.arguments[0].lower().replace("-", "_"))
			batch = self.batches.setdefault(batch_id, {})
			batch["info"] = BatchInfo(
				batch_id, tags=extract_tags(event.tags), type=batch_type, params=tuple(event.arguments[1:])
			)
			batch["func_calls"] = []
		elif event.target.startswith("-"):
			logger.debug(f"[BATCH] finished batch {batch_id}")
			batch = self.batches.pop(batch_id, None)
			if batch is None:
				return
			batch_info: BatchInfo = batch["info"]
			func_calls: list[BatchFuncCallType] = batch["func_calls"]
			for args, kwargs in func_calls:
				self._handle_message(*args, batch_info=batch_info, **kwargs)

	def add_batch_func_call(self, batch_id: str, /, *args: Any, **kwargs: Any) -> None:
		"""
		Queue a message handler call to be executed when the named batch finishes.

		Args:
			batch_id: Identifier of the batch to attach the call to.
			*args: Positional arguments for _handle_message.
			**kwargs: Keyword arguments for _handle_message.
		"""
		func_call: BatchFuncCallType = (args, kwargs)
		batch = self.batches.get(batch_id)
		if batch is None:
			logger.warning(f"Batch ID {batch_id} doesn't exist: {func_call!r}")
			return
		func_calls: list[BatchFuncCallType] = batch["func_calls"]
		func_calls.append(func_call)

	def _handle_message(
		self,
		connection: IRCServerConnectionType,
		event: IRCEventType,
		message_info: MessageInfo,
		*,
		batch_info: BatchInfo | None = None,
	) -> None:
		"""
		Core message dispatcher for PRIVMSG, NOTICE, and ACTION.

		Performs echo suppression, labeled-response correlation, batch queuing,
		and GUI delivery. Private messages are routed to a query tab named after
		the remote party.

		Args:
			connection: The active server connection.
			event: The message event.
			message_info: A MessageInfo object.
			batch_info: A BatchInfo object or None.
		"""
		self._update_our_nick_mask(event.source)
		tags: dict[str, str] = extract_tags(event.tags)
		batch_id: str = tags.get("batch", "")
		if batch_info is None and batch_id:
			batch = self.batches.get(batch_id)
			if batch is not None and not batch["func_calls"]:  # Existing empty batch.
				message_info.is_batch_start = True
			self.add_batch_func_call(batch_id, connection, event, message_info)
			return
		folded_our_nick: str = connection.get_nickname().casefold()
		if batch_info is not None and batch_info.type is BatchTypeEnum.CHATHISTORY and batch_info.params:
			message_info.history_target = batch_info.params[0]
		if self.echo_message_enabled and message_info.history_target is None:
			# Suppress server echoes unless message is part of a history batch.
			label: str = tags.get("label", "")
			matched_label: bool = bool(self.labeled_response_enabled and label and label in self._our_labels)
			is_source_us: bool = message_info.folded_sender == folded_our_nick
			has_pending: bool = self._pending_echo_counts.get(message_info.text, 0) > 0
			if matched_label or (is_source_us and has_pending):
				self._our_labels.discard(label)
				if has_pending:
					self._pending_echo_counts[message_info.text] -= 1
					if self._pending_echo_counts[message_info.text] == 0:
						del self._pending_echo_counts[message_info.text]
				return
		if is_status_like(message_info.target):
			# Registration and server-wide notices belong on the status tab.
			message_info.target = STATUS_TAB_NAME
		elif message_info.folded_target == folded_our_nick:
			# Message is an incoming private message to us.
			# The query tab should be named after the person who sent us the direct message, not us.
			message_info.target = message_info.sender
		message_info.is_mentioned = bool(
			not message_info.history_target
			and message_info.target != STATUS_TAB_NAME
			and re.search(rf"\b{re.escape(folded_our_nick)}\b", message_info.folded_text)
		)
		wx.CallAfter(self.gui.append_to_output, message_info)

	def on_action(self, connection: IRCServerConnectionType, event: IRCEventType) -> None:
		"""
		Handle CTCP ACTION messages.

		Args:
			connection: The active server connection.
			event: The ACTION event.
		"""
		message_info = MessageInfo(
			text="".join(event.arguments[:1]), target=event.target, sender=event.source.nick, is_action=True
		)
		self._handle_message(connection, event, message_info)

	def on_privmsg(self, connection: IRCServerConnectionType, event: IRCEventType) -> None:
		"""
		Handle incoming private messages.

		Args:
			connection: The active server connection.
			event: The PRIVMSG event.
		"""
		message_info = MessageInfo(
			text="".join(event.arguments[:1]), target=event.target, sender=event.source.nick
		)
		self._handle_message(connection, event, message_info)

	def on_privnotice(self, connection: IRCServerConnectionType, event: IRCEventType) -> None:
		"""
		Handle private NOTICEs.

		Args:
			connection: The active server connection.
			event: The NOTICE event.
		"""
		message_info = MessageInfo(
			text="".join(event.arguments[:1]), target=event.target, sender=event.source.nick, is_notice=True
		)
		self._handle_message(connection, event, message_info)

	def on_pubmsg(self, connection: IRCServerConnectionType, event: IRCEventType) -> None:
		"""
		Handle public channel messages.

		Args:
			connection: The active server connection.
			event: The PRIVMSG event on a channel.
		"""
		message_info = MessageInfo(
			text="".join(event.arguments[:1]), target=event.target, sender=event.source.nick
		)
		self._handle_message(connection, event, message_info)

	def on_pubnotice(self, connection: IRCServerConnectionType, event: IRCEventType) -> None:
		"""
		Handle public channel NOTICEs.

		Args:
			connection: The active server connection.
			event: The NOTICE event on a channel.
		"""
		message_info = MessageInfo(
			text="".join(event.arguments[:1]), target=event.target, sender=event.source.nick, is_notice=True
		)
		self._handle_message(connection, event, message_info)

	def request_channel_list(self, callback: Callable[[Sequence[tuple[str, str, str]]], None]) -> None:
		"""
		Request a fresh LIST of channels from the server.

		Thread-safe: the LIST command is sent from the IRC reactor thread.

		Args:
			callback: Function to call with the completed list of (channel, user_count, topic) tuples.
		"""
		self._list_callback = callback
		self.listed_channels.clear()
		self._run_in_irc_thread(self.connection.send_raw, "LIST")

	def join(self, channel: str, key: str = "") -> None:
		"""Thread-safe JOIN."""
		if key:
			self._run_in_irc_thread(self.connection.join, channel, key)
		else:
			self._run_in_irc_thread(self.connection.join, channel)

	def part(self, channel: str, message: str = "") -> None:
		"""Thread-safe PART."""
		if message:
			self._run_in_irc_thread(self.connection.part, channel, message)
		else:
			self._run_in_irc_thread(self.connection.part, channel)

	def send_raw(self, raw: str) -> None:
		"""Thread-safe raw command send."""
		self._run_in_irc_thread(self.connection.send_raw, raw)

	def disconnect(self, message: str = "") -> None:
		"""Thread-safe disconnect."""
		self._run_in_irc_thread(self.connection.disconnect, message)

	def on_list(self, connection: IRCServerConnectionType, event: IRCEventType) -> None:
		"""
		Accumulate entries from RPL_LIST (322).

		Args:
			connection: The active server connection.
			event: The LIST entry event.
		"""
		if len(event.arguments) >= 2:
			channel, users, *topic = event.arguments
			self.listed_channels.append((channel, users, " ".join(topic)))

	def on_listend(self, connection: IRCServerConnectionType, event: IRCEventType) -> None:
		"""
		Handle end of LIST (RPL_LISTEND / 323) and invoke the registered callback.

		Args:
			connection: The active server connection.
			event: The LISTEND event.
		"""
		if self._list_callback is not None:
			wx.CallAfter(self._list_callback, tuple(self.listed_channels))
			self._list_callback = None
			self.listed_channels.clear()

	def _calculate_max_body_length(self, message_info: MessageInfo) -> int:
		"""
		Calculate the maximum length of a UTF-8-encoded message body that will fit in a single IRC command.

		Note:
			Although the client does not transmit a source prefix, this method
			deliberately subtracts the length of our current nick!user@host mask.
			IRC servers enforce the 512-byte limit on the *constructed*
			line they will relay or echo (i.e. after prepending ":nick!user@host ").
			Budgeting for the prefix prevents the server from rejecting the message with
			417 (input line too long).
			Additionally, per the IRCv3 message-tags specification, the tag portion of a message
			(from the leading '@' through the trailing space) has its own separate
			limit of 8191 bytes. The traditional 512-byte limit applies only to the
			rest of the message (prefix + command + parameters + CRLF).
			Because of this separation, we intentionally do *not* subtract the
			length of a potential `label=` tag from the body budget in this method.
			See: https://ircv3.net/specs/extensions/message-tags.html

		Args:
			message_info: The associated MessageInfo object.

		Returns:
			Maximum number of bytes available for the message payload.
		"""
		nick_mask_len: int = len(str(self._our_nick_mask)) or 118  # (32-char-nick!20-char-user@64-char-host).
		overhead: int = nick_mask_len + len(bytes(f": PRIVMSG {message_info.target} :\r\n", "utf-8"))
		if message_info.is_action:
			overhead += len("\x01ACTION \x01")
		return 512 - overhead - 10  # Safety margin.

	def _split_text_bytes(self, message_info: MessageInfo) -> list[str]:
		"""
		Split a potentially long message into chunks that each fit within IRC line limits.

		Prefers splitting on word boundaries; falls back to hard UTF-8 byte cuts for very long words.

		Args:
			message_info: The associated MessageInfo object.

		Returns:
			List of message chunks, each guaranteed to fit in a single IRC command.
		"""
		max_bytes: int = self._calculate_max_body_length(message_info)
		if len(bytes(message_info.text, "utf-8")) <= max_bytes:
			return [message_info.text]
		chunks: list[str] = []
		current: str = ""
		# Split on whitespace and some punctuation for nicer breaks.
		words: list[str] = WORDS_REGEX.split(message_info.text)
		for word in words:
			if not word:
				continue
			test: str = current + word
			if len(bytes(test, "utf-8")) <= max_bytes:
				# We'll still be under the limit after appending the word.
				current = test
				continue
			if current:
				# The chunk is full since Appending the word would grow the chunk past the limit.
				chunks.append(current)
			current = word
			# If even a single word is too long, hard-split it by bytes.
			# Find the largest prefix that fits in max_bytes without breaking UTF-8.
			while len(encoded := bytes(current, "utf-8")) > max_bytes:
				# Take up to max_bytes bytes, but back up to a valid UTF-8 boundary.
				cut: int = max_bytes
				while cut > 0 and (encoded[cut] & UTF8_CONTINUATION_MASK) == UTF8_CONTINUATION_PREFIX:
					# Back up to start of a character.
					cut -= 1
				if cut == 0:
					# We cannot split this character without breaking UTF-8.
					# Since max_bytes is always large in practice, we can safely.
					# include it. If this ever triggers, the chunk will be slightly
					# too long and may get a 417 from the server.
					chunks.append(current)
					current = ""
					break
				chunks.append(str(encoded[:cut], "utf-8", errors="ignore"))
				current = str(encoded[cut:], "utf-8", errors="ignore")
		if current:
			chunks.append(current)
		return chunks

	def _next_label(self) -> str:
		"""
		Generate the next unique labeled-response label (32-bit counter, hex formatted).

		Returns:
			The next label.
		"""
		self._label_counter = (self._label_counter + 1) & UINT32_MAX
		return f"label-{self._label_counter:08x}"

	def _run_in_irc_thread(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
		"""
		Schedule *func* to run on the IRC reactor thread.

		The jaraco/irc Reactor is thread-safe for state mutations and its
		scheduler, but ServerConnection I/O methods are not safe to call
		concurrently from the GUI thread.  All outbound commands therefore
		go through this helper which uses the reactor's scheduler to
		execute the call in the next process cycle of the reactor thread.

		Args:
			func: Callable to invoke (typically a bound method on self.connection).
			*args: Positional arguments for *func*.
			**kwargs: Keyword arguments for *func*.
		"""
		if not getattr(self, "connection", None) or not self.connection.is_connected():
			return

		def wrapper() -> None:
			try:
				func(*args, **kwargs)
			except Exception:
				logger.exception("Error executing command in IRC reactor thread")

		# execute_after(0) queues the callable for the next run_pending()
		# which happens inside the reactor thread's process_once loop.
		self.connection.reactor.scheduler.execute_after(0, wrapper)

	def send_privmsg(self, message_info: MessageInfo) -> None:
		"""
		Send a PRIVMSG (or CTCP ACTION) to a target, splitting long text as needed.

		Thread-safe: the actual send is performed on the IRC reactor thread.

		Args:
			message_info: The associated MessageInfo object.
		"""
		self._run_in_irc_thread(self._send_privmsg_impl, message_info)

	def _send_privmsg_impl(self, message_info: MessageInfo) -> None:
		"""Internal implementation of send_privmsg (must run on reactor thread)."""
		if not self.connection.is_connected() or not message_info.text:
			return
		chunks: list[str] = self._split_text_bytes(message_info)
		for chunk in chunks:
			tags: list[str] = []
			if self.echo_message_enabled:
				self._pending_echo_counts[chunk] += 1
				if self.labeled_response_enabled:
					label: str = self._next_label()
					self._our_labels.add(label)
					tags.append(f"label={label}")
			# Note that `send_items` filters out empty strings.
			self.connection.send_items(
				f"@{';'.join(tags)}" if tags else "",
				"PRIVMSG",
				message_info.target,
				f":\x01ACTION {chunk}\x01" if message_info.is_action else f":{chunk}",
			)

	def quit_with_callback(self, callback: Callable[[], None], *args: Any, **kwargs: Any) -> None:
		"""
		Send QUIT and register a one-shot callback to be called after disconnect.

		Args:
			callback: The callback to be called after disconnect.
			*args: Positional arguments forwarded to self.quit.
			**kwargs: Keyword arguments forwarded to self.quit.
		"""
		self._shutdown_callback = callback
		self.quit(*args, **kwargs)

	def quit(self, *args: Any, **kwargs: Any) -> None:
		"""
		Stop the reconnection backoff timer and send a QUIT to the server.

		Thread-safe: the actual QUIT is performed on the IRC reactor thread.

		Args:
			*args: Positional arguments forwarded to the underlying quit method.
			**kwargs: Keyword arguments forwarded to the underlying quit method.
		"""
		self.recon.stop()
		self._run_in_irc_thread(self.connection.quit, *args, **kwargs)

	def on_nicknameinuse(self, connection: IRCServerConnectionType, event: IRCEventType) -> None:
		"""
		Handle ERR_NICKNAMEINUSE (433) by appending an incrementing suffix.

		Args:
			connection: The active server connection.
			event: The error event.
		"""
		# Always pick an alternate nick immediately.
		# After SASL we still try to reclaim the original nick (account-owned nicks, ghost sessions, etc).
		if self.is_sasl_in_progress:
			self._sasl_deferred_nick_collision = True
		self._nick_attempt += 1
		new_nick: str = f"{self._base_nickname}_{self._nick_attempt}"
		self.log_system_message(f"Nickname in use, trying {new_nick}...")
		connection.nick(new_nick)

	def on_saslsuccess(self, connection: IRCServerConnectionType, event: IRCEventType) -> None:
		"""
		Handle RPL_SASLSUCCESS (903).

		Args:
			connection: The active server connection.
			event: The success event.
		"""
		self.log_system_message(f"Successfully logged in as {connection.get_nickname()!r}.")
		# If we deferred a nick collision during SASL registration, try to reclaim
		# our desired nickname now that we are authenticated.
		if self._sasl_deferred_nick_collision:
			self._sasl_deferred_nick_collision = False
			desired = self._base_nickname
			current = connection.get_nickname()
			if current != desired:
				self.log_system_message(f"Attempting to regain desired nickname {desired} after SASL login.")
				self._nick_attempt = 0
				connection.nick(desired)


class TabPanel(wx.Panel):  # type: ignore[no-any-unimported, misc]
	"""A single chat tab (channel or query) containing output area, input field, and optional nick list."""

	def __init__(self, parent: Any, tab_name: str, main_frame: MainFrame) -> None:
		"""
		Create a new chat tab panel.

		Args:
			parent: The wx.Notebook that will contain this panel.
			tab_name: The name of the tab (channel or nickname).
			main_frame: Reference to the MainFrame for sending messages and speech control.
		"""
		super().__init__(parent)
		self.tab_name: str = tab_name
		self.is_channel: bool = irc.client.is_channel(tab_name)
		self.main_frame: MainFrame = main_frame
		self.received_initial_history: bool = False
		self._completion_state: dict[str, Any] | None = None
		self.speech_enabled: bool = True
		main_sizer = wx.BoxSizer(wx.VERTICAL)
		output_label = wx.StaticText(self, label=f"Output {tab_name}:")
		main_sizer.Add(output_label, 0, wx.ALL, 5)
		self.output = wx.TextCtrl(
			self,
			style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH | wx.TE_AUTO_URL,
		)
		self.output.SetBackgroundColour(wx.BLACK)
		self.output.SetForegroundColour(wx.WHITE)
		self.output.SetName(output_label.GetLabel())
		input_label = wx.StaticText(self, label="Input:")
		self.input = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
		self.input.Bind(wx.EVT_TEXT_ENTER, self.on_input_enter)
		self.input.Bind(wx.EVT_KEY_DOWN, self.on_input_key_down)
		self.input.SetName(input_label.GetLabel())
		if self.is_channel:
			nick_list_label = wx.StaticText(self, label="Members:")
			# Use wx.ListBox instead of wx.ListCtrl for proper AT-SPI / Orca support on Linux.
			self.nick_list: WXListBoxType | None = wx.ListBox(self, style=wx.LB_SINGLE)
			self.nick_list.SetBackgroundColour(wx.BLACK)
			self.nick_list.SetForegroundColour(wx.WHITE)
			self.nick_list.SetName(nick_list_label.GetLabel())
			self.nick_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_query)
			self.nick_list.Bind(wx.EVT_CHAR_HOOK, self.on_nick_list_key)
			nick_sizer = wx.BoxSizer(wx.VERTICAL)
			nick_sizer.Add(nick_list_label, 0, wx.ALL, 5)
			nick_sizer.Add(self.nick_list, 1, wx.EXPAND)
			chat_area = wx.BoxSizer(wx.HORIZONTAL)
			chat_area.Add(self.output, 5, wx.EXPAND | wx.RIGHT, 8)
			chat_area.Add(nick_sizer, 1, wx.EXPAND)
			main_sizer.Add(chat_area, 1, wx.EXPAND | wx.ALL, 5)
		else:
			self.nick_list = None
			main_sizer.Add(self.output, 1, wx.EXPAND | wx.ALL, 5)
		main_sizer.Add(input_label, 0, wx.ALL, 5)
		main_sizer.Add(self.input, 0, wx.EXPAND | wx.ALL, 5)
		self.SetSizer(main_sizer)

	def on_input_enter(self, event: Any) -> None:
		"""
		Send the contents of the input field when the user presses Enter.

		Args:
			event: The text-enter event.
		"""
		text: str = self.input.GetValue().strip()
		if text:
			self.main_frame.handle_input_entered(self.tab_name, text)
			self.input.Clear()

	def on_query(self, event: Any) -> None:
		"""
		Open a private query tab for the currently selected nickname.

		Args:
			event: The listbox activation event (double-click or Enter).
		"""
		if not self.nick_list:
			return
		idx: int = self.nick_list.GetSelection()
		if idx == WX_NOT_FOUND:
			return
		nick: str = self.nick_list.GetString(idx)
		if nick:
			self.main_frame.create_tab(nick.split(maxsplit=1)[0], auto_focus=True)

	def on_nick_list_key(self, event: Any) -> None:
		"""
		Treat Return/Enter in the nick list the same as double-click (open query).

		Args:
			event: The key event.
		"""
		wx_port_id = self.main_frame.wx_port_id
		# GTK already treats enter on wx.ListBox items the same as double click.
		if wx_port_id != wx.PORT_GTK:
			code: int = event.GetKeyCode()
			# Orca makes use of the numpad enter key.
			non_unix: set[int] = {wx.PORT_MSW, wx.PORT_MAC, wx.PORT_COCOA}
			if code == wx.WXK_RETURN or (code == wx.WXK_NUMPAD_ENTER and wx_port_id in non_unix):
				self.on_query(None)
				return  # Consume the event.
		event.Skip()

	def on_input_key_down(self, event: Any) -> None:
		r"""
		Handle Ctrl+\ (Control+Backslash) for nick name completion in channel tabs.

		Each press cycles through matching nicks (or all nicks if no prefix).
		Repeated presses replace the previously inserted nick with the next one.
		"""
		if event.GetModifiers() == wx.MOD_CONTROL and event.GetKeyCode() == ord("\\"):
			if self.is_channel:
				self._do_name_completion()
			return  # Consume the event (do not insert backslash).
		event.Skip()

	def _do_name_completion(self) -> None:
		r"""
		Perform nick completion / cycling.

		If text before cursor is a non-empty prefix (no whitespace immediately before it),
		only nicks starting with that prefix (case-insensitive) are cycled.
		If cursor is after whitespace or at the beginning of the line (no prefix),
		all nicks in the channel are cycled.
		Each Ctrl+\ replaces the previously inserted nick with the next match.
		"""
		if not self.is_channel:
			return
		mf = self.main_frame
		if not mf.is_connected:
			return
		ch = mf.client.channels.get(self.tab_name)
		if ch is None:
			return
		all_nicks: list[str] = sorted(ch.users(), key=str.casefold)
		if not all_nicks:
			wx.Bell()
			return
		text: str = self.input.GetValue()
		pos: int = self.input.GetInsertionPoint()
		# Find start of current word (stop at whitespace or beginning of line).
		start: int = pos
		while start > 0 and not text[start - 1].isspace():
			start -= 1
		current_word: str = text[start:pos]
		continuing = False
		matches: list[str] = []
		index: int = 0
		if self._completion_state is not None:
			state = self._completion_state
			if (
				state.get("channel") == self.tab_name
				and state.get("start") == start
				and current_word == state["matches"][state["index"]]
			):
				continuing = True
				matches = state["matches"]
				index = (state["index"] + 1) % len(matches)
		if not continuing:
			if current_word:
				# Prefix mode: only nicks starting with the typed prefix.
				pfold = current_word.casefold()
				matches = [n for n in all_nicks if n.casefold().startswith(pfold)]
				if not matches:
					wx.Bell()
					self._completion_state = None
					return
			else:
				# No prefix (whitespace or beginning of line before cursor): cycle ALL nicks.
				matches = all_nicks
			index = 0
		replacement: str = matches[index]
		self.input.Replace(start, pos, replacement)
		speech.output(replacement, interrupt=True)
		new_pos: int = start + len(replacement)
		self.input.SetInsertionPoint(new_pos)
		self._completion_state = {
			"channel": self.tab_name,
			"matches": matches,
			"index": index,
			"start": start,
		}

	def append_text(self, text: str) -> None:
		"""
		Append a line of text to the output control.

		Args:
			text: The text to append (may contain newlines).
		"""
		at_bottom: bool = self.output.GetInsertionPoint() >= self.output.GetLastPosition() - 1
		self.output.AppendText(("\n" if self.output.GetLastPosition() else "") + text)
		if at_bottom:
			self.output.SetInsertionPointEnd()

	def clear_text(self) -> None:
		"""Clear text from the output control."""
		self.output.Clear()


class MainFrame(wx.Frame):  # type: ignore[no-any-unimported, misc] # NOQA: PLR0904
	"""Top-level wxPython window containing the notebook of chat tabs and the application menu."""

	def __init__(self) -> None:
		"""Create the main application window and initialize speech state persistence."""
		super().__init__(None, title=WINDOW_TITLE, size=(1000, 700))
		self.wx_port_id: int = wx.PlatformInformation.Get().GetPortId()
		self._client: IRCClient | None = None
		self.irc_thread: threading.Thread | None = None
		self._is_shutdown_finished: bool = False
		self.global_speech_enabled: bool = True
		self.speech_states: dict[str, dict[str, bool]] = {}  # {server_key: {folded_tab_name: enabled}}
		self._load_speech_states()
		self._sound_volume: float = DEFAULT_SOUND_VOLUME / 100.0
		self._load_sound_volume()
		self.notebook: WXNotebookType = wx.Notebook(self)
		sizer = wx.BoxSizer(wx.VERTICAL)
		sizer.Add(self.notebook, 1, wx.EXPAND)
		self.SetSizer(sizer)
		self.SetMenuBar(self.create_menubar())
		# Accelerators.
		self._speech_enable_globally_id = wx.NewIdRef()
		self._speech_disable_globally_id = wx.NewIdRef()
		self._speech_enable_current_tab_id = wx.NewIdRef()
		self._speech_disable_current_tab_id = wx.NewIdRef()
		self._lower_volume_id = wx.NewIdRef()
		self._raise_volume_id = wx.NewIdRef()
		self._minimize_to_tray_id = wx.NewIdRef()
		self._extract_urls_id = wx.NewIdRef()
		accel = wx.AcceleratorTable(
			[
				(wx.ACCEL_CTRL, ord("W"), wx.ID_CLOSE),
				(wx.ACCEL_CTRL, wx.WXK_F4, wx.ID_CLOSE),
				(wx.ACCEL_NORMAL, wx.WXK_F3, self._extract_urls_id),
				(wx.ACCEL_NORMAL, wx.WXK_F5, self._speech_enable_globally_id),
				(wx.ACCEL_NORMAL, wx.WXK_F6, self._speech_disable_globally_id),
				(wx.ACCEL_CTRL, wx.WXK_F5, self._speech_enable_current_tab_id),
				(wx.ACCEL_CTRL, wx.WXK_F6, self._speech_disable_current_tab_id),
				(wx.ACCEL_NORMAL, wx.WXK_F7, self._lower_volume_id),
				(wx.ACCEL_NORMAL, wx.WXK_F8, self._raise_volume_id),
				(wx.ACCEL_NORMAL, wx.WXK_ESCAPE, self._minimize_to_tray_id),
			]
		)
		self.SetAcceleratorTable(accel)
		self.Bind(wx.EVT_MENU, self.on_close_tab, id=wx.ID_CLOSE)
		self.Bind(wx.EVT_MENU, self.on_extract_urls, id=self._extract_urls_id)
		self.Bind(wx.EVT_MENU, self.enable_speech_globally, id=self._speech_enable_globally_id)
		self.Bind(wx.EVT_MENU, self.disable_speech_globally, id=self._speech_disable_globally_id)
		self.Bind(wx.EVT_MENU, self.enable_speech_for_current_tab, id=self._speech_enable_current_tab_id)
		self.Bind(wx.EVT_MENU, self.disable_speech_for_current_tab, id=self._speech_disable_current_tab_id)
		self.Bind(wx.EVT_MENU, self.lower_sound_volume, id=self._lower_volume_id)
		self.Bind(wx.EVT_MENU, self.raise_sound_volume, id=self._raise_volume_id)
		self.Bind(wx.EVT_MENU, self.minimize_to_tray, id=self._minimize_to_tray_id)
		self.notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self._on_tab_changed)
		self.Bind(wx.EVT_CLOSE, self.on_exit)
		self.Show()
		self.create_tab(STATUS_TAB_NAME, auto_focus=True)
		self._update_window_title()
		self.update_server_menu_state()
		self.tray_icon: TrayIcon | None = TrayIcon(self)

	@property
	def client(self) -> IRCClient:
		"""
		The currently used IRCClient instance.

		Raises:
			RuntimeError: If instance hasn't been created yet.
		"""
		if self._client is None:
			raise RuntimeError("IRCClient instance not created yet.")
		return self._client

	@property
	def is_connected(self) -> bool:
		"""True if self.client is connected, False otherwise."""
		return self._client is not None and self._client.connection.is_connected()

	def create_menubar(self) -> Any:
		"""
		Build the application menu bar (File, Server).

		Returns:
			The menu bar.
		"""
		menubar = wx.MenuBar()
		file_menu = wx.Menu()
		exit_item = file_menu.Append(wx.ID_EXIT, "&Exit\tAlt-F4", "Exit program")
		self.Bind(wx.EVT_MENU, self.on_exit, exit_item)
		menubar.Append(file_menu, "&File")
		server_menu = wx.Menu()
		self.connect_item = server_menu.Append(wx.ID_ANY, "&Connect...")
		self.Bind(wx.EVT_MENU, self.on_connect, self.connect_item)
		self.disconnect_item = server_menu.Append(wx.ID_ANY, "&Disconnect")
		self.Bind(wx.EVT_MENU, self.on_disconnect_menu, self.disconnect_item)
		list_item = server_menu.Append(wx.ID_ANY, "&List Channels...")
		self.Bind(wx.EVT_MENU, self.on_list_channels, list_item)
		menubar.Append(server_menu, "&Server")
		return menubar

	def on_close_tab(self, event: Any) -> None:
		"""
		Close the currently selected tab (with special handling for the status tab and channels).

		Args:
			event: The menu/accelerator event.
		"""
		panel: TabPanel | None = self.current_tab
		if panel is None:
			return
		tab_name: str = panel.tab_name
		if tab_name.casefold() == STATUS_TAB_NAME:
			return  # Status tab must never be closed.
		if irc.client.is_channel(tab_name) and self.is_connected:
			self.client.part(tab_name)
		else:
			self.close_tab(tab_name)

	def create_tab(
		self, tab_name: str, *, auto_focus: bool = False, update_nick_list: bool = False
	) -> TabPanel:
		"""
		Create a new chat tab or return the existing one.

		Automatically requests CHATHISTORY for channels and queries when the capability is available.

		Args:
			tab_name: Name of the tab (channel or nickname).
			auto_focus: If True, switch to the new tab immediately.
			update_nick_list: If True and the tab is a channel, populate the nick list.

		Returns:
			The TabPanel instance for the requested tab.
		"""
		folded_tab_name = tab_name.casefold()
		panel = self.get_tab(tab_name)
		if panel is None:
			panel = TabPanel(self.notebook, tab_name, self)
			self.notebook.AddPage(panel, tab_name)
			self._update_window_title()
			server_key = self._get_current_server_key(tab_name)
			server_speech = self.speech_states.get(server_key, {})
			if folded_tab_name in server_speech:
				panel.speech_enabled = server_speech[folded_tab_name]
			else:
				if server_key not in self.speech_states:
					self.speech_states[server_key] = {}
				self.speech_states[server_key][folded_tab_name] = panel.speech_enabled
			if folded_tab_name != STATUS_TAB_NAME and self.is_connected and self.client.chathistory_enabled:
				# We intentionally request chat history for both channels and private messages.
				# This should still be fine even if the server only supports chat history for channels.
				logger.debug(f"Requesting CHATHISTORY for tab: {tab_name}")
				num_lines_str = (
					self.client.feature_list.get("chathistory")
					or self.client.feature_list.get("draft/chathistory")
					or ""
				)
				num_lines = int(num_lines_str) if num_lines_str.isdigit() else DEFAULT_HISTORY_LENGTH
				self.client.send_raw(f"CHATHISTORY LATEST {tab_name} * {num_lines}")
		if auto_focus:
			self.select_tab(panel)
		if update_nick_list:
			self.update_nick_list(tab_name)
		return panel

	def rename_tab(self, old_name: str, new_name: str) -> None:
		"""
		Rename a query tab after a remote NICK change.

		If a tab for new_name already exists, merge the old tab's transcript into it.

		Args:
			old_name: Previous nickname (current tab title).
			new_name: New nickname.
		"""
		if not old_name or not new_name:
			return
		if old_name.casefold() == new_name.casefold():
			return
		if old_name.casefold() == STATUS_TAB_NAME or irc.client.is_channel(old_name):
			return
		panel = self.get_tab(old_name)
		if panel is None:
			return
		existing = self.get_tab(new_name)
		if existing is not None and existing is not panel:
			old_text: str = panel.output.GetValue()
			existing.append_text(f"*** {old_name} is now known as {new_name}")
			if old_text:
				existing.append_text(old_text)
			self.close_tab(old_name)
			self._migrate_speech_state(old_name, new_name)
			return
		panel.tab_name = new_name
		panel.is_channel = irc.client.is_channel(new_name)
		panel.output.SetName(f"Output {new_name}:")
		idx = self.get_tab_index(panel)
		if idx != WX_NOT_FOUND:
			self.notebook.SetPageText(idx, new_name)
		self._migrate_speech_state(old_name, new_name)
		self._update_window_title()

	def _migrate_speech_state(self, old_name: str, new_name: str) -> None:
		"""
		Move a per-tab speech preference from old_name to new_name.

		Args:
			old_name: Previous nickname.
			new_name: New nickname.
		"""
		old_fold = old_name.casefold()
		new_fold = new_name.casefold()
		if old_fold == new_fold:
			return
		changed = False
		for tabs in self.speech_states.values():
			if old_fold in tabs:
				tabs[new_fold] = tabs.pop(old_fold)
				changed = True
		if changed:
			self._save_speech_states()

	def close_tab(self, tab_name: str) -> None:
		"""
		Remove a tab from the notebook (the status tab is protected).

		Args:
			tab_name: Name of the tab to close.
		"""
		if tab_name.casefold() == STATUS_TAB_NAME:
			# Status tab must never be closed
			return
		idx = self.get_tab_index(tab_name)
		if idx != WX_NOT_FOUND:
			self.notebook.DeletePage(idx)
		self._update_window_title()

	def close_all_non_status_tabs(self) -> None:
		"""Close every tab except the mandatory status tab."""
		for panel in self.tabs:
			idx = self.get_tab_index(panel)
			if idx == WX_NOT_FOUND:
				continue
			if self.notebook.GetPageText(idx).casefold() != STATUS_TAB_NAME:
				self.notebook.DeletePage(idx)
		self._update_window_title()

	@property
	def tabs(self) -> tuple[TabPanel, ...]:
		"""Return a tuple of all currently open TabPanel instances."""
		return tuple(self.notebook.GetPage(i) for i in range(self.notebook.GetPageCount()))

	@property
	def current_tab(self) -> TabPanel | None:
		"""Return the TabPanel that is currently visible, or None if no tabs exist."""
		return self.notebook.GetCurrentPage()

	@property
	def current_tab_name(self) -> str:
		"""Return the name of the currently visible tab, or empty string if none."""
		idx = self.notebook.GetSelection()
		return self.notebook.GetPageText(idx) if idx != WX_NOT_FOUND else ""

	def get_tab(self, tab_name: str) -> TabPanel | None:
		"""
		Look up a tab by its name (case-insensitive).

		Args:
			tab_name: Name of the tab to find.

		Returns:
			The matching TabPanel or None.
		"""
		if tab_name:
			idx = self.get_tab_index(tab_name)
			if idx != WX_NOT_FOUND:
				panel: TabPanel = self.notebook.GetPage(idx)
				return panel
		return None

	def get_tab_index(self, item: str | TabPanel, *, case_sensitive: bool = False) -> int:
		"""
		Return the notebook page index of a tab, or WX_NOT_FOUND.

		Args:
			item: Either a tab name string or a TabPanel instance.
			case_sensitive: Whether to perform a case-sensitive name match.

		Returns:
			Zero-based page index or WX_NOT_FOUND (-1).
		"""
		if isinstance(item, TabPanel):
			return self.notebook.FindPage(item)
		tab_name = item if case_sensitive else item.casefold()
		for idx in range(self.notebook.GetPageCount()):
			page_text = (
				self.notebook.GetPageText(idx)
				if case_sensitive
				else self.notebook.GetPageText(idx).casefold()
			)
			if page_text == tab_name:
				return idx
		return WX_NOT_FOUND

	def tab_exists(self, item: str | TabPanel, **kwargs: Any) -> bool:
		"""
		Check whether a tab with the given name or panel already exists.

		Args:
			item: Tab name or TabPanel instance.
			**kwargs: Passed through to get_tab_index (e.g. case_sensitive).

		Returns:
			True if the tab exists, False otherwise.
		"""
		return self.get_tab_index(item, **kwargs) != WX_NOT_FOUND

	def select_tab(self, item: str | TabPanel | int) -> None:
		"""
		Switch the notebook to the specified tab and focus its input field.

		Args:
			item: Tab name, TabPanel instance, or integer page index.
		"""
		idx = item if isinstance(item, int) else self.get_tab_index(item)
		# Valid indices for a wx.Notebook range from 0 to GetPageCount() - 1 (inclusive).
		if not (0 <= idx < self.notebook.GetPageCount()):
			logger.warning(f"{idx} not in range 0-{self.notebook.GetPageCount()}")
			return
		self.notebook.SetSelection(idx)
		panel = item if isinstance(item, TabPanel) else self.notebook.GetPage(idx)
		panel.input.SetFocus()

	def append_to_output(self, message_info: MessageInfo) -> None:
		"""
		Append a message to the specified tab's output area (creating the tab if necessary).

		Respects CHATHISTORY suppression rules and triggers speech output for live messages.

		Args:
			message_info: The associated MessageInfo object.
		"""
		if (
			message_info.history_target is not None
			and message_info.folded_history_target != message_info.folded_target
		):
			logger.warning(
				f"Tab name {message_info.target!r} and history target {message_info.history_target!r} differ."
			)
		panel: TabPanel | None = self.get_tab(message_info.target)
		if panel is None:
			panel = self.create_tab(message_info.target)
			self.play_notification_sound(INCOMING_QUERY_CREATED_SOUND)
		if message_info.history_target is not None:  # History text.
			# Clear the output on the *first* history message we receive for this tab.
			# This prevents duplication with any offline messages the server may have
			# already pushed as live PRIVMSG/NOTICE before the CHATHISTORY batch arrived.
			# Subsequent history messages (e.g. for paging) leave existing content intact.
			# Visual flicker is possible but preferred over permanent duplicates.
			if not panel.received_initial_history:
				panel.received_initial_history = True
				panel.clear_text()
		else:  # Live text.
			is_current_tab: bool = (
				self.IsActive() and message_info.folded_target == self.current_tab_name.casefold()
			)
			if not message_info.is_local_echo and self.global_speech_enabled and panel.speech_enabled:
				# Note that by design, history messages will *not* be automatically spoken, but live messages,
				# including those sent before initial history will be spoken.
				preamble: str = f"{message_info.target if message_info.is_channel else 'Private'}: "
				speech.output(
					f"{'' if is_current_tab else preamble}{message_info.formatted_text}", interrupt=False
				)
			is_hidden: bool = not self.IsShown()
			if (
				message_info.is_mentioned
				and message_info.target != STATUS_TAB_NAME
				and (not is_current_tab or is_hidden)
			):
				# User was mentioned outside of the status tab.
				self.play_notification_sound(MENTIONED_SOUND)
				if is_hidden:
					# Window is hidden in the system tray; send a desktop notification.
					self.show_tray_notification(
						message_info.formatted_text, f"Mentioned in {message_info.target}"
					)
		panel.append_text(message_info.formatted_text)

	def update_nick_list(self, tab_name: str) -> None:
		"""
		Refresh the member list for a channel tab.

		Args:
			tab_name: Name of the channel whose nick list should be updated.
		"""
		panel = self.get_tab(tab_name)
		if panel is None or not panel.is_channel:
			return
		if not self.is_connected or tab_name not in self.client.channels:
			return
		ch = self.client.channels[tab_name]
		items = []
		for nick in ch.users():
			privs = self.client.get_nick_privs(tab_name, nick)
			display = f"{nick} ({', '.join(privs)})" if privs else nick
			highest = max((PRIVILEGES[p][0] for p in privs), default=0)
			items.append((display, (-highest, nick.lower())))
		items.sort(key=operator.itemgetter(1))
		if panel.nick_list is None:
			return
		panel.nick_list.Freeze()
		try:
			panel.nick_list.Clear()
			if items:
				panel.nick_list.AppendItems([display for display, _ in items])
				panel.nick_list.SetSelection(0)
		finally:
			panel.nick_list.Thaw()

	def _update_window_title(self) -> None:
		"""Update the window title to reflect the current tab and total tab count."""
		total: int = self.notebook.GetPageCount()
		current: str = self.current_tab_name or "No tab"
		self.SetTitle(f"{WINDOW_TITLE} - {current} ({total} tab{'' if total == 1 else 's'})")

	def _on_tab_changed(self, event: Any) -> None:
		"""
		Update window title and focus the input field when the user switches tabs.

		This ensures that tabs created in the background (e.g. incoming private
		messages / queries via append_to_output) receive input focus when the
		user later activates them with the mouse or keyboard navigation.

		Note:
			Setting focus should only be done if running on Windows as other platforms might
			annoyingly trigger this event when normal keyboard navigation is used to change the selected tab.

		Args:
			event: The notebook page-changed event.
		"""
		self._update_window_title()
		panel: TabPanel | None = self.current_tab
		if panel is not None and sys.platform == "win32":
			panel.input.SetFocus()
		event.Skip()

	def _get_current_server_key(self, tab_name: str) -> str:
		"""
		Return a stable key identifying the currently connected server (or __global__).

		Used for per-server speech state persistence.

		Args:
			tab_name: The name of a tab (used when checking if status tab).

		Returns:
			Lower-cased server hostname or the literal string "__global__".
		"""
		if not self.is_connected or tab_name.casefold() == STATUS_TAB_NAME:
			return "__global__"
		return self.client.connection.server.casefold()

	def _load_speech_states(self) -> None:
		"""Load per-tab speech enable/disable preferences from the JSON config file."""
		with Config(CONFIG_NAME) as cfg:
			self.speech_states.clear()
			self.speech_states.update(cfg.get("speech_states", {}))

	def _save_speech_states(self) -> None:
		"""Persist the current speech_states dictionary to the JSON config file."""
		with Config(CONFIG_NAME) as cfg:
			speech_states = cfg.setdefault("speech_states", {})
			speech_states.clear()
			speech_states.update(self.speech_states)

	def _load_sound_volume(self) -> None:
		"""Load global sound volume (0-100) from config and convert to float."""
		with Config(CONFIG_NAME) as cfg:
			vol = cfg.setdefault("sound_volume", DEFAULT_SOUND_VOLUME)
			self._sound_volume = clamp(vol, 0.0, 100.0) / 100.0

	def _save_sound_volume(self) -> None:
		"""Persist current sound volume (as integer 0-100)."""
		with Config(CONFIG_NAME) as cfg:
			cfg["sound_volume"] = round(self._sound_volume * 100)

	def enable_speech_globally(self, event: Any | None = None) -> None:
		"""Enable speech output for all tabs (menu/accelerator handler)."""
		self._set_speech_globally(enabled=True)

	def disable_speech_globally(self, event: Any | None = None) -> None:
		"""Disable speech output for all tabs (menu/accelerator handler)."""
		self._set_speech_globally(enabled=False)

	def _set_speech_globally(self, *, enabled: bool) -> None:
		"""
		Internal helper to toggle global speech and announce the change.

		Args:
			enabled: Desired global speech state.
		"""
		if self.global_speech_enabled is enabled:
			return
		self.global_speech_enabled = enabled
		state: str = "enabled" if enabled else "disabled"
		speech.output(f"Speech globally {state}", interrupt=True)

	def enable_speech_for_current_tab(self, event: Any | None = None) -> None:
		"""Enable speech for the currently visible tab only."""
		self._set_speech_for_current_tab(enabled=True)

	def disable_speech_for_current_tab(self, event: Any | None = None) -> None:
		"""Disable speech for the currently visible tab only."""
		self._set_speech_for_current_tab(enabled=False)

	def _set_speech_for_current_tab(self, *, enabled: bool) -> None:
		"""
		Toggle speech for the active tab and persist the choice.

		Args:
			enabled: Desired speech state for the current tab.
		"""
		panel: TabPanel | None = self.current_tab
		if panel is None:
			return
		tab_name: str = panel.tab_name
		if panel.speech_enabled is enabled:
			return
		panel.speech_enabled = enabled
		server_key: str = self._get_current_server_key(tab_name)
		if server_key not in self.speech_states:
			self.speech_states[server_key] = {}
		self.speech_states[server_key][tab_name.casefold()] = enabled
		state: str = "enabled" if enabled else "disabled"
		speech.output(f"{tab_name} speech {state}", interrupt=True)
		self._save_speech_states()

	def lower_sound_volume(self, event: Any | None = None) -> None:
		"""Lower global sound volume by 5%."""
		self._adjust_sound_volume(-5)
		self.play_notification_sound(VOLUME_DOWN_SOUND)

	def raise_sound_volume(self, event: Any | None = None) -> None:
		"""Raise global sound volume by 5%."""
		self._adjust_sound_volume(+5)
		self.play_notification_sound(VOLUME_UP_SOUND)

	def _adjust_sound_volume(self, delta: int) -> None:
		"""
		Adjust volume, persist, and announce.

		Args:
			delta: The percentage to adjust by.
		"""
		new_vol = clamp(round(self._sound_volume * 100) + delta, 0, 100)
		self._sound_volume = new_vol / 100.0
		self._save_sound_volume()
		speech.output(f"Volume {int(new_vol)} percent", interrupt=True)

	def play_notification_sound(self, sound_path: Path | str) -> None:
		"""
		Play a notification sound at the current global volume level.

		Use this instead of calling play_sound directly to respect the user's volume setting.

		Args:
			sound_path: The path to the sound file to play.
		"""
		play_sound(sound_path, volume=self._sound_volume)

	def show_tray_notification(self, message: str, title: str | None = None) -> None:
		"""
		Show a system tray notification if the platform supports it.

		Args:
			message: Notification body.
			title: Notification title.
		"""
		if self.tray_icon is None:
			return
		self.tray_icon.notify(message, title)

	def _send_message(self, message_info: MessageInfo) -> None:
		"""
		Send a locally originated message and display it in the target tab.

		The message will be recorded for echo suppression.

		Args:
			message_info: The associated MessageInfo object.
		"""
		if not self.is_connected:
			return
		message_info.is_local_echo = True
		self.append_to_output(message_info)
		# Pass a copy of message_info to the client thread to guard against possible race conditions.
		message_info_copy = dataclasses.replace(message_info)
		self.client.send_privmsg(message_info_copy)

	def handle_input_entered(self, tab_name: str, text: str) -> None:
		"""
		Entry point for user-typed messages; routes commands or sends as PRIVMSG.

		Args:
			tab_name: The tab from which the message originated.
			text: Raw text entered by the user.
		"""
		if not self.is_connected:
			return
		text = text.strip()
		if not text:
			return
		if text.startswith("/"):
			self.user_command(tab_name, text)
			return
		if tab_name.casefold() == STATUS_TAB_NAME:
			self.log_system_message("Cannot send messages on the status tab.")
			return
		message_info = MessageInfo(
			text=text, target=tab_name, sender=self.client.connection.get_nickname(), is_action=False
		)
		self._send_message(message_info)

	def user_command(self, tab_name: str, text: str) -> None:  # NOQA: PLR0912
		"""
		Interpret and execute client-side slash commands.

		Args:
			tab_name: The tab in which the command was typed.
			text: The full command line including the leading slash.
		"""
		if not self.is_connected:
			return
		parts: list[str] = text[1:].split(maxsplit=1)
		cmd: str = parts[0].upper()
		args: str = parts[1].strip() if len(parts) >= 2 else ""
		if cmd == "QUIT":
			self.client.quit(args or "Client exiting")
			return
		if cmd in {"JOIN", "J"}:
			join_parts: list[str] = args.split(maxsplit=1)  # Channel, key.
			if join_parts and irc.client.is_channel(join_parts[0]):
				self.client.join(*join_parts)
			else:
				self.log_system_message("Usage: /join #channel [key]")
		elif cmd in {"PART", "LEAVE", "P"}:
			channel: str = args or tab_name
			if channel and irc.client.is_channel(channel):
				self.client.part(channel)
			else:
				self.log_system_message("Usage: /part [#channel]")
		elif cmd in {"QUERY", "Q"}:
			if args and not irc.client.is_channel(args):
				nick: str = args.split(maxsplit=1)[0]
				self.create_tab(nick, auto_focus=True)
			else:
				self.log_system_message("Usage: /query <nick>")
		elif cmd == "ME":
			if tab_name.casefold() == STATUS_TAB_NAME:
				self.log_system_message("Cannot send an action on the status tab.")
			elif args:
				message_info = MessageInfo(
					text=args, target=tab_name, sender=self.client.connection.get_nickname(), is_action=True
				)
				self._send_message(message_info)
			else:
				self.log_system_message("Usage: /me <action>")
		else:
			self.client.send_raw(text[1:])

	def log_system_message(self, msg: str) -> None:
		"""
		Append a system/status message to the status tab.

		Args:
			msg: The message text (will be prefixed with "*** ").
		"""
		if self.tab_exists(STATUS_TAB_NAME):
			message_info = MessageInfo(text=f"*** {msg}", target=STATUS_TAB_NAME, sender="")
			self.append_to_output(message_info)

	def on_exit(self, event: Any) -> None:
		"""
		Cleanly shut down the IRC connection and close the application.

		Args:
			event: The menu/accelerator/close event.
		"""
		if self._is_shutdown_finished:
			if event is not None and hasattr(event, "Skip"):
				event.Skip()
			return
		if self.is_connected:
			self.client.quit_with_callback(self._finish_shutdown, "Client exiting")
			# Safety net: force shutdown after 5 seconds if callback never fires.
			wx.CallLater(5000, self._finish_shutdown)
			# Keep the window alive until QUIT completes (or the timer fires).
			if event is not None and hasattr(event, "Veto"):
				event.Veto()
			return
		self._finish_shutdown()

	def _finish_shutdown(self) -> None:
		"""Join the IRC thread (if running), clean up tray icon, and destroy the wx frame."""
		if self._is_shutdown_finished:
			return
		self._is_shutdown_finished = True
		if self.tray_icon is not None:
			with suppress(Exception):
				self.tray_icon.stop()
			self.tray_icon = None
		if self._client is not None:
			with suppress(Exception):
				self._client.stop_reactor()
		if self.irc_thread and self.irc_thread.is_alive():
			self.irc_thread.join(timeout=1.5)
		self.Destroy()
		wx.GetApp().ExitMainLoop()

	def on_connect(self, event: Any) -> None:
		"""
		Show the connect dialog, persist settings, and start a new IRCClient thread.

		Args:
			event: The menu event.
		"""
		dlg: ConnectDialog = ConnectDialog(self)
		if dlg.ShowModal() == wx.ID_OK:
			data: dict[str, Any] = dlg.get_data()
			if not data["server"]:
				wx.MessageBox("Server hostname is required.", "Error", wx.OK | wx.ICON_ERROR)
				return
			if not data["nickname"]:
				wx.MessageBox("Nickname is required.", "Error", wx.OK | wx.ICON_ERROR)
				return
			with Config(CONFIG_NAME) as cfg:
				cfg.update(data)
			if self._client is not None:
				# Always stop the previous client's reactor thread before disconnect.
				with suppress(Exception):
					self._client.stop_reactor()
				if self.is_connected:
					with suppress(Exception):
						self._client.disconnect()
				if self.irc_thread is not None and self.irc_thread.is_alive():
					self.irc_thread.join(timeout=1.5)
			self._client = IRCClient(
				gui=self,
				server=data["server"],
				port=int(data["port"]),
				nickname=data["nickname"],
				server_password=data.get("server_password"),
				sasl_login=data.get("sasl_login"),
				sasl_password=data.get("sasl_password"),
				client_id=data.get("client_id"),
				use_tls=data["use_tls"],
				verify_ssl=data.get("verify_ssl", True),
			)
			self.irc_thread = threading.Thread(target=self.client.start, daemon=True)
			self.irc_thread.start()
			self.update_server_menu_state()
			self.log_system_message("Connecting...")

	def on_disconnect_menu(self, event: Any) -> None:
		"""
		Disconnect from the current server via the menu.

		Args:
			event: The menu event.
		"""
		if self.is_connected:
			self.client.quit("Client exiting")
			# Stay in a disconnecting state until on_disconnect updates the menu.
			self.connect_item.Enable(enable=False)
			self.disconnect_item.Enable(enable=False)
			return
		self.update_server_menu_state()

	def update_server_menu_state(self) -> None:
		"""Enable/disable Connect and Disconnect menu items according to connection state."""
		connected: bool = self.is_connected
		self.connect_item.Enable(not connected)
		self.disconnect_item.Enable(connected)

	def on_list_channels(self, event: Any) -> None:
		"""
		Open the channel list dialog (requires an active connection).

		Args:
			event: The menu event.
		"""
		if not self.is_connected:
			wx.MessageBox("Not connected to a server.", "Error", wx.OK | wx.ICON_ERROR)
			return
		dlg: ListChannelsDialog = ListChannelsDialog(self, self.client)
		if dlg.ShowModal() == wx.ID_OK:
			channel: str | None = dlg.get_selected_channel()
			if channel:
				self.client.join(channel)

	def minimize_to_tray(self, event: Any | None = None) -> None:
		"""
		Hide the main window, effectively minimizing it to the system tray (or equivalent).

		Called via the Escape accelerator. The tray icon (created at startup) remains
		visible and provides restore/quit functionality.
		"""
		if self.IsShown():
			self.Hide()

	def on_extract_urls(self, event: Any | None = None) -> None:
		"""
		Extract URLs from the current tab's output and show the URL list dialog.

		Args:
			event: The accelerator/menu event (unused).
		"""
		panel: TabPanel | None = self.current_tab
		if panel is None:
			return
		text: str = panel.output.GetValue()
		# Extract URLs and remove oldest duplicates while preserving order.
		urls: list[str] = list(reversed(dict.fromkeys(reversed(url_extractor.find_urls(text)))))
		if not urls:
			wx.MessageBox("No URLs found in the current tab.", "URLs", wx.OK | wx.ICON_INFORMATION)
			return
		dlg = UrlListDialog(self, urls)
		dlg.ShowModal()
		dlg.Destroy()


class ConnectDialog(wx.Dialog):  # type: ignore[no-any-unimported, misc]
	"""Modal dialog for entering server connection details and credentials."""

	def __init__(self, parent: Any) -> None:
		"""
		Build the connect dialog and pre-populate fields from saved configuration.

		Args:
			parent: The parent window (MainFrame).
		"""
		super().__init__(parent, title="Connect to IRC Server", size=(440, 460))
		fields: list[tuple[str, str, str, int]] = [
			("Server hostname:", "server", DEFAULT_HOST, 0),
			("Port:", "port", str(DEFAULT_PORT), 0),
			("Nickname:", "nickname", "", 0),
			("Account username (leave empty to use Nickname):", "sasl_login", "", 0),
			("Account password:", "sasl_password", "", wx.TE_PASSWORD),
			("Server password:", "server_password", "", wx.TE_PASSWORD),
			("Device name (SASL client ID):", "client_id", DEFAULT_CLIENT_ID, 0),
		]
		with Config(CONFIG_NAME) as cfg:
			sizer = wx.BoxSizer(wx.VERTICAL)
			self.controls: dict[str, Any] = {}
			for label_text, key, default, *style in fields:
				sizer.Add(wx.StaticText(self, label=label_text), 0, wx.ALL, 5)
				ctrl = wx.TextCtrl(self, value=str(cfg.get(key, default)), style=reduce_or(style))
				sizer.Add(ctrl, 0, wx.EXPAND | wx.ALL, 5)
				self.controls[key] = ctrl
			self.controls["server"].SetFocus()
			self.tls_cb = wx.CheckBox(self, label="Use TLS / SSL")
			self.tls_cb.SetValue(cfg.get("use_tls", True))
			sizer.Add(self.tls_cb, 0, wx.ALL, 10)
			self.verify_cb = wx.CheckBox(self, label="Verify SSL certificate (recommended)")
			self.verify_cb.SetValue(cfg.get("verify_ssl", True))
			sizer.Add(self.verify_cb, 0, wx.ALL, 10)
			btn_sizer = wx.StdDialogButtonSizer()
			connect_btn = wx.Button(self, wx.ID_OK, "Connect")
			connect_btn.SetDefault()
			btn_sizer.AddButton(connect_btn)
			btn_sizer.AddButton(wx.Button(self, wx.ID_CANCEL, "Cancel"))
			btn_sizer.Realize()
			sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 5)
			self.SetSizer(sizer)

	def get_data(self) -> dict[str, Any]:
		"""
		Collect current dialog values into a dictionary suitable for saving and IRCClient construction.

		Returns:
			Connection configuration dictionary.
		"""
		try:
			port: int = int(self.controls["port"].GetValue().strip() or DEFAULT_PORT)
		except ValueError:
			port = DEFAULT_PORT
		data: dict[str, Any] = {
			"server": self.controls["server"].GetValue().strip(),
			"port": port,
			"nickname": self.controls["nickname"].GetValue().split("@", maxsplit=1)[0].strip(),
			"sasl_login": self.controls["sasl_login"].GetValue().split("@", maxsplit=1)[0].strip(),
			"sasl_password": self.controls["sasl_password"].GetValue().strip(),
			"server_password": self.controls["server_password"].GetValue().strip(),
			"client_id": self.controls["client_id"].GetValue().replace("@", "").strip(),
			"use_tls": self.tls_cb.GetValue(),
			"verify_ssl": self.verify_cb.GetValue(),
		}
		return data


class ListChannelsDialog(wx.Dialog):  # type: ignore[no-any-unimported, misc]
	"""Modal dialog that fetches and displays the server's channel list."""

	def __init__(self, parent: Any, client: IRCClient) -> None:
		"""
		Create the channel list dialog and immediately request the LIST.

		Args:
			parent: The parent window.
			client: Reference to the active IRCClient (must be connected).
		"""
		super().__init__(parent, title="List Channels", size=(650, 500))
		self._client: IRCClient = client
		sizer = wx.BoxSizer(wx.VERTICAL)
		label = wx.StaticText(self, label="Available channels:")
		sizer.Add(label, 0, wx.ALL, 5)
		# Use wx.ListBox instead of wx.ListCtrl for proper AT-SPI / Orca support on Linux.
		self.channel_list: WXListBoxType = wx.ListBox(self, style=wx.LB_SINGLE)
		self.channel_list.SetBackgroundColour(wx.BLACK)
		self.channel_list.SetForegroundColour(wx.WHITE)
		self.channel_list.SetName(label.GetLabel())
		self.channel_list.Bind(wx.EVT_LISTBOX_DCLICK, lambda evt: self.EndModal(wx.ID_OK))
		sizer.Add(self.channel_list, 1, wx.EXPAND | wx.ALL, 5)
		self.fetch_channels()
		btn_sizer = wx.StdDialogButtonSizer()
		join_btn = wx.Button(self, wx.ID_OK, "&Join")
		join_btn.SetDefault()
		cancel_btn = wx.Button(self, wx.ID_CANCEL, "Cancel")
		btn_sizer.AddButton(join_btn)
		btn_sizer.AddButton(cancel_btn)
		btn_sizer.Realize()
		sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 5)
		self.SetSizer(sizer)

	def fetch_channels(self) -> None:
		"""Ask the IRC client to request a fresh channel list."""
		self._client.request_channel_list(self.populate_choice)

	def populate_choice(self, channels: Sequence[tuple[str, str, str]]) -> None:
		"""
		Fill the list box with the received channel data.

		Args:
			channels: Sequence of (channel_name, user_count, topic) tuples.
		"""
		self.channel_list.Clear()
		if not channels:
			return
		lines = [f"{ch[0]} ({ch[1]} users) - {ch[2][:60]}" for ch in channels]
		self.channel_list.AppendItems(lines)
		self.channel_list.SetSelection(0)

	def get_selected_channel(self) -> str | None:
		"""
		Return the channel name of the currently selected row.

		Returns:
			Channel name string or None if nothing is selected.
		"""
		idx: int = self.channel_list.GetSelection()
		if idx == WX_NOT_FOUND:
			return None
		full: str = self.channel_list.GetString(idx)
		return full.split(maxsplit=1)[0]


class UrlListDialog(wx.Dialog):  # type: ignore[no-any-unimported, misc]
	"""Modal dialog listing extracted URLs with Open and Copy to Clipboard actions."""

	def __init__(self, parent: Any, urls: Sequence[str]) -> None:
		"""
		Build the URL list dialog.

		Args:
			parent: The parent window (MainFrame).
			urls: Sequence of URL strings to display.
		"""
		super().__init__(parent, title="URLs", size=(650, 400))
		sizer = wx.BoxSizer(wx.VERTICAL)
		label = wx.StaticText(self, label="Extracted URLs:")
		sizer.Add(label, 0, wx.ALL, 5)
		# Use wx.ListBox instead of wx.ListCtrl for proper AT-SPI / Orca support on Linux.
		self.url_list: WXListBoxType = wx.ListBox(self, style=wx.LB_SINGLE)
		self.url_list.SetBackgroundColour(wx.BLACK)
		self.url_list.SetForegroundColour(wx.WHITE)
		self.url_list.SetName(label.GetLabel())
		self.url_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_open)
		sizer.Add(self.url_list, 1, wx.EXPAND | wx.ALL, 5)
		if urls:
			self.url_list.AppendItems(list(urls))
			self.url_list.SetSelection(0)
		btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
		self.open_btn = wx.Button(self, wx.ID_OK, "&Open")
		self.open_btn.SetDefault()
		self.open_btn.Bind(wx.EVT_BUTTON, self.on_open)
		self.copy_btn = wx.Button(self, wx.ID_ANY, "&Copy to Clipboard")
		self.copy_btn.Bind(wx.EVT_BUTTON, self.on_copy)
		cancel_btn = wx.Button(self, wx.ID_CANCEL, "Cancel")
		btn_sizer.Add(self.open_btn, 0, wx.ALL, 5)
		btn_sizer.Add(self.copy_btn, 0, wx.ALL, 5)
		btn_sizer.Add(cancel_btn, 0, wx.ALL, 5)
		sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
		self.SetSizer(sizer)
		self.url_list.SetFocus()

	def get_selected_url(self) -> str | None:
		"""
		Return the currently selected URL string, or None if nothing is selected.

		Returns:
			The selected URL or None.
		"""
		idx: int = self.url_list.GetSelection()
		if idx == WX_NOT_FOUND:
			return None
		return self.url_list.GetString(idx)

	def on_open(self, event: Any | None = None) -> None:
		"""
		Open the selected URL in the system default web browser (cross-platform).

		Triggered by the Open button, Enter on the button, or Enter/double-click
		on a list item.
		"""
		url = self.get_selected_url()
		if not url:
			wx.Bell()
			return
		# Ensure the URL has a scheme so the system browser can open it.
		if not url.lower().startswith(("http://", "https://")):
			url = f"https://{url}"
		webbrowser.open(url)
		self.EndModal(wx.ID_OK)

	def on_copy(self, event: Any | None = None) -> None:
		"""
		Copy the selected URL to the system clipboard (cross-platform via wx).

		The dialog stays open so the user can open or copy additional URLs.
		"""
		url = self.get_selected_url()
		if not url:
			wx.Bell()
			return
		if wx.TheClipboard.Open():
			try:
				wx.TheClipboard.SetData(wx.TextDataObject(url))
			finally:
				wx.TheClipboard.Close()
			speech.output("Copied to clipboard", interrupt=True)
		else:
			wx.Bell()


class TrayIcon:
	"""
	System tray icon implemented with pystray.

	The icon runs in a background thread so it does not interfere with the wxPython main loop.
	"""

	def __init__(self, main_frame: MainFrame) -> None:
		"""
		Create the system tray icon.

		Args:
			main_frame: Reference to the MainFrame.
		"""
		self.main_frame = main_frame
		self._icon: PySTrayIconType | None = None
		self._thread: threading.Thread | None = None
		image = Image.new("RGBA", (64, 64), (70, 130, 180, 255))
		menu = pystray.Menu(
			pystray.MenuItem("Restore Window", self.on_restore, default=True),
			pystray.MenuItem("Exit", self.on_quit),
		)
		self._icon = pystray.Icon(
			name="the-irc",
			icon=image,
			title=WINDOW_TITLE,
			menu=menu,
		)
		self._thread = threading.Thread(target=self._icon.run, daemon=True)
		self._thread.start()

	def on_restore(self, icon: Any = None, item: Any = None) -> None:
		"""Restore the main window."""
		wx.CallAfter(self._do_restore)

	def _do_restore(self) -> None:
		if not self.main_frame.IsShown():
			self.main_frame.Show()
			self.main_frame.Raise()
			self.main_frame.SetFocus()
			panel: TabPanel | None = self.main_frame.current_tab
			if panel is not None:
				panel.input.SetFocus()

	def on_quit(self, icon: Any = None, item: Any = None) -> None:
		"""Quit the application."""
		wx.CallAfter(self.main_frame.on_exit, None)

	def notify(self, message: str, title: str | None = None) -> None:
		"""
		Display a system notification from the tray icon.

		Args:
			message: Notification body.
			title: Notification title.
		"""
		icon = self._icon
		if icon is None or not getattr(icon, "HAS_NOTIFICATION", False):
			return
		with suppress(Exception):
			icon.notify(message, title)

	def stop(self) -> None:
		"""Stop the tray icon (called during shutdown)."""
		if self._icon is not None:
			with suppress(Exception):
				self._icon.stop()
			self._icon = None


def run() -> None:  # pragma: no cover
	"""Entry point: parse command-line flags, configure logging, and launch the wxPython GUI."""
	parser: argparse.ArgumentParser = argparse.ArgumentParser(description=WINDOW_TITLE)
	verbosity_group: argparse._MutuallyExclusiveGroup = parser.add_mutually_exclusive_group(required=False)
	verbosity_group.add_argument("-d", "--debug", action="store_true", help="show debug messages")
	verbosity_group.add_argument("-q", "--quiet", action="store_true", help="only show warnings and errors")
	args: argparse.Namespace = parser.parse_args()
	log_level: int
	if args.debug:
		log_level = logging.DEBUG
	elif args.quiet:
		log_level = logging.WARNING
	else:
		log_level = logging.INFO
	logging.basicConfig(
		level=log_level,
		format="{levelname}: {message}",
		style="{",
	)
	logger.debug("IRC client starting.")
	app = wx.App(redirect=False)
	MainFrame()
	app.MainLoop()
