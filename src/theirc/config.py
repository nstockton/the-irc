# Copyright (C) 2026 Nick Stockton
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
Thread-safe configuration management with atomic JSON persistence.

This module provides the `Config` class, which implements a
`collections.abc.MutableMapping` interface for storing and retrieving
configuration data in JSON files. It is designed to be safe for concurrent
use across multiple threads, with atomic writes to prevent corruption.
"""

# Future Modules:
from __future__ import annotations

# Built-in Modules:
import json
import os
import tempfile
import threading
from collections.abc import Iterator, MutableMapping
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Any, Final

# Local Modules:
from .typedef import Self
from .utils import get_data_path


# Constants:
DATA_DIRECTORY: Final[Path] = get_data_path()


# Globals:
locks: Final[dict[Path, Locker]] = {}
locks_lock: Final[threading.RLock] = threading.RLock()


class ConfigError(Exception):
	"""Base exception class for all configuration-related errors."""


def load(path: Path) -> dict[str, Any]:
	"""
	Loads configuration data from a JSON file.

	Args:
		path: The path to the configuration file.

	Returns:
		A dictionary containing the configuration data,
		or an empty dictionary if the file does not exist.

	Raises:
		ConfigError:
			If the file exists but is not a valid JSON file, contains a non-dictionary root object,
			or cannot be read.
	"""
	try:
		with path.open(encoding="utf-8") as f:
			data: dict[str, Any] = json.load(f)
		if isinstance(data, dict):
			return data
		raise ConfigError(f"JSON object not found in configuration file: {path}")
	except FileNotFoundError:
		return {}
	except OSError as e:
		if path.exists() and not path.is_file():
			raise ConfigError(f"Path exists but is not a file: {path}") from e
		raise ConfigError(f"Unable to load configuration from file: {path}") from e
	except json.JSONDecodeError as e:
		raise ConfigError(f"Corrupted JSON in configuration file: {path}") from e


def dump(config: dict[str, Any], path: Path) -> None:
	"""
	Dumps configuration data to JSON file atomically.

	The data is first written to a temporary file in the same directory,
	then atomically renamed to the final path using `Path.replace`.
	This guarantees that the configuration file is never left in a
	partially written or corrupted state if the process is killed during
	the write. Parent directories are created automatically if needed.

	Args:
		config: The configuration data to dump (must be JSON-serializable).
		path: The path to the configuration file.

	Raises:
		ConfigError:
			If the configuration cannot be written
			(e.g. permission error, non-serializable data, or path conflicts).
	"""
	config_dir: Path = path.parent
	if config_dir.exists() and not config_dir.is_dir():
		raise ConfigError(f"Configuration directory path exists but is not a directory: {config_dir}")
	tmp_path: Path | None = None
	newline: str = "\n"
	try:  # NOQA: PLW0717
		config_dir.mkdir(parents=True, exist_ok=True)
		with tempfile.NamedTemporaryFile(
			mode="w",
			encoding="utf-8",
			newline=newline,
			dir=config_dir,
			prefix=".",
			suffix=".tmp",
			delete=False,
		) as f:
			tmp_path = Path(f.name)
			json.dump(config, f, sort_keys=True, indent=2)
			f.write(newline)
			f.flush()
			os.fsync(f.fileno())  # Ensure data is on disk.
		tmp_path.replace(path)  # Atomic rename.
	except OSError as e:
		raise ConfigError(f"Unable to dump configuration to file: {path}") from e
	except (TypeError, ValueError) as e:
		raise ConfigError(f"Configuration data contains non-JSON-serializable values: {path}") from e
	finally:
		if tmp_path is not None and tmp_path.exists():
			tmp_path.unlink(missing_ok=True)


@dataclass(slots=True)
class Locker:
	"""Internal helper that tracks reference count, per-path lock, and shared configuration dict."""

	count: int = 0
	lock: threading.RLock = field(default_factory=threading.RLock)
	config: dict[str, Any] = field(default_factory=dict)


class Config(MutableMapping[str, Any]):
	"""
	Thread-safe configuration stored in a JSON file.

	Implements `collections.abc.MutableMapping`, so instances can be
	used like dictionaries (``config["key"]``, iteration, ``len()``, etc.).

	Multiple `Config` instances pointing to the same file share the
	same underlying data and are protected by internal locks. The class also
	acts as a context manager that automatically saves changes on clean exit.
	"""

	def __init__(self, name: str = "config", *, auto_save: bool = True) -> None:
		"""
		Initializes a new configuration instance.

		Args:
			name: The base filename of the configuration without extension.
			auto_save: If True, automatically save the database to disk when the context manager exits.
		"""
		super().__init__()
		self._name: str = Path(name).stem  # Use Path.stem for sanitization.
		self._path: Path = DATA_DIRECTORY / f"{self._name}.json"
		self._auto_save: bool = auto_save
		self._closed: bool = False
		with locks_lock:
			self._locker = locks.setdefault(self._path, Locker())
			self._locker.count += 1
			if self._locker.count == 1:
				try:
					self.reload()
				except Exception:
					self.close()
					raise

	@property
	def name(self) -> str:
		"""The sanitized name of the configuration (base filename without extension)."""
		return self._name

	@property
	def path(self) -> Path:
		"""The full path to the configuration JSON file."""
		return self._path

	def _check_closed(self) -> None:
		if self._closed:
			raise ConfigError(f"Cannot operate on a closed configuration: {self.path}")

	def reload(self) -> None:
		"""
		Reloads the configuration from disk, discarding any unsaved changes.

		This operation is thread-safe and acquires the internal per-path lock.
		"""
		with self._locker.lock:
			self._check_closed()
			new_config: dict[str, Any] = load(self.path)
			self._locker.config.clear()
			self._locker.config.update(new_config)

	def save(self) -> None:
		"""
		Saves the current configuration to disk atomically.

		This operation is thread-safe and acquires the internal per-path lock.
		"""
		with self._locker.lock:
			self._check_closed()
			dump(self._locker.config, self.path)

	def close(self) -> None:
		"""
		Closes this configuration instance and releases associated resources.

		Decrements the internal reference count. When the count reaches zero,
		the shared lock and cached data for the file are removed. This method
		is idempotent and thread-safe. It is automatically called by the
		context manager and `__del__`.
		"""
		with locks_lock:
			if not self._closed:
				with self._locker.lock:
					self._locker.count -= 1
					if not self._locker.count:
						locks.pop(self._path, None)
					self._closed = True

	def __repr__(self) -> str:
		return f"Config(name={self.name!r})"

	def __del__(self) -> None:
		"""Ensures the configuration is closed when the object is garbage collected."""
		self.close()

	def __enter__(self) -> Self:
		"""
		Enters the runtime context.

		Returns:
			The configuration instance.
		"""
		return self

	def __exit__(
		self,
		exc_type: type[BaseException] | None,
		exc_value: BaseException | None,
		exc_traceback: TracebackType | None,
	) -> None:
		"""
		Exits the runtime context.

		If no exception occurred, the configuration is automatically saved.
		The instance is always closed, even if an exception occurred.
		"""
		# Save configuration to disk if exited cleanly.
		try:
			if exc_type is None and self._auto_save:
				self.save()
		finally:
			self.close()

	def __getitem__(self, key: str) -> Any:
		with self._locker.lock:
			self._check_closed()
			return self._locker.config[key]

	def __setitem__(self, key: str, value: Any) -> None:
		with self._locker.lock:
			self._check_closed()
			self._locker.config[key] = value

	def __delitem__(self, key: str) -> None:
		with self._locker.lock:
			self._check_closed()
			del self._locker.config[key]

	def __iter__(self) -> Iterator[str]:
		with self._locker.lock:
			self._check_closed()
			return iter(list(self._locker.config))

	def __len__(self) -> int:
		with self._locker.lock:
			self._check_closed()
			return len(self._locker.config)
