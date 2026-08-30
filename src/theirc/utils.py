# Copyright (C) 2026 Nick Stockton
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Utility functions."""

# Future Modules:
from __future__ import annotations

# Built-in Modules:
import functools
import operator
import re
from collections.abc import Iterable
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Final

# Third-party Modules:
from knickknacks.platforms import get_directory_path, is_frozen
from knickknacks.typedef import RePatternType


# Constants:
DATA_DIRECTORY: Final[str] = "theirc_data"
# RFC 2812 nick characters.
NICK_INITIAL_CHAR_CLASS = r"\x41-\x7d"
NICK_SUBSEQUENT_CHAR_CLASS = r"\x2d\x30-\x39\x41-\x7d"
RFC2812_NICK_REGEX: Final[RePatternType] = re.compile(
	rf"^[{NICK_INITIAL_CHAR_CLASS}][{NICK_SUBSEQUENT_CHAR_CLASS}]*$", flags=re.ASCII
)

# Globals:
__version__: str = "0.0.0"
if not TYPE_CHECKING:
	with suppress(ImportError):
		from ._version import __version__  # NOQA: F401


def get_data_path(*args: str | Path) -> Path:
	"""
	Retrieves the path of the data directory.

	Args:
		*args: Positional arguments to be passed to Path.joinpath after the data path.

	Returns:
		The path.
	"""
	path = Path(get_directory_path())
	if not is_frozen():
		path = path.parent
	return path.joinpath(DATA_DIRECTORY, *args).resolve()


def reduce_or(items: Iterable[int], *, initial: int = 0) -> int:
	"""
	Reduce an iterable of integers by repeatedly applying the bitwise OR operator (|).

	Args:
		items: The iterable of integers to reduce.
		initial: The initial value to place before the items (acts as default when items is empty).

	Returns:
		The result of combining the initial value with all integers in the iterable using bitwise OR.
	"""
	return functools.reduce(operator.or_, items, initial)


def is_nick(nick: str) -> bool:
	"""
	Tests if a nickname is valid according to RFC2812.

	Args:
		nick: The nick to validate.

	Returns:
		True if the nickname was valid, False otherwise.
	"""
	return RFC2812_NICK_REGEX.fullmatch(nick) is not None


def is_mentioned_nick(nick: str, text: str) -> bool:
	"""
	Tests if a nickname is mentioned in text.

	Args:
		nick: a nickname.
		text: Some text.

	Returns:
		True if nick is mentioned inside text, False otherwise.
	"""
	if not nick or not text:
		return False
	escaped: str = re.escape(nick)
	char_class: str = NICK_SUBSEQUENT_CHAR_CLASS
	return re.search(rf"(?:^|[^{char_class}]){escaped}(?:[^{char_class}]|$)", text) is not None
