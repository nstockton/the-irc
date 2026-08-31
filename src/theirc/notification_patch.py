# Copyright (C) 2026 Nick Stockton
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
Notifications patch.

This module implements two platform-specific notification fixes.
On Linux, intercept pystray's D-Bus Notify call and replace an empty app_name with
the supplied application name.
On Windows, call SetCurrentProcessExplicitAppUserModelID so Windows toast notifications
are attributed to the desired AppUserModelID.

Configuration is idempotent; the pystray wrapper is installed once, and
later calls only update the active identity.
"""

# Future Modules:
from __future__ import annotations

# Built-in Modules:
import ctypes
import sys
import threading
from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final


GLib: Any | None = None
notify_dbus: Any | None = None
if not TYPE_CHECKING and sys.platform not in {"win32", "darwin"}:
	with suppress(Exception):
		from gi.repository import GLib
	with suppress(Exception):
		from pystray._util import notify_dbus  # NOQA: PLC2701
	if notify_dbus is not None and GLib is None:
		GLib = getattr(notify_dbus, "GLib", None)


# Constants:
NOTIFY_PATCH_LOCK: Final[threading.RLock] = threading.RLock()
NOTIFY_VARIANT_TYPE: Final[str] = "(susssasa{sv}i)"
S_OK: Final[int] = 0


@dataclass(slots=True)
class _PatchState:
	"""Mutable patch state."""

	app_name: str = ""
	windows_app_id: str = ""
	pystray_notify_original: Any | None = None
	wrapper_installed: bool = False


# Globals:
patch_state: _PatchState = _PatchState()
get_aumid: Any | None = None
ole32: Any | None = None
set_aumid: Any | None = None
if sys.platform == "win32":
	with NOTIFY_PATCH_LOCK:
		with suppress(Exception):
			get_aumid = ctypes.windll.shell32.GetCurrentProcessExplicitAppUserModelID
			get_aumid.argtypes = (ctypes.POINTER(ctypes.c_wchar_p),)
			get_aumid.restype = ctypes.c_long
		with suppress(Exception):
			ole32 = ctypes.windll.ole32
			ole32.CoTaskMemFree.argtypes = (ctypes.c_void_p,)
			ole32.CoTaskMemFree.restype = None
		with suppress(Exception):
			set_aumid = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
			set_aumid.argtypes = (ctypes.c_wchar_p,)
			set_aumid.restype = ctypes.c_long


def _variant_with_app_name(variant: Any, app_name: str) -> Any:
	"""
	Replace blank app_name in a Notify variant.

	Child 0 is rewritten as a Variant. Other children are reused so
	hints are not unpacked and re-packed.

	Returns:
		The variant.
	"""
	if GLib is None or variant is None or not app_name:
		return variant
	with suppress(Exception):
		if getattr(variant, "get_type_string", lambda: "")() != NOTIFY_VARIANT_TYPE:
			return variant
		if variant.n_children() < 8:
			return variant
		if variant.get_child_value(0).unpack():
			return variant
		children = [GLib.Variant("s", app_name)]
		children.extend(variant.get_child_value(index) for index in range(1, variant.n_children()))
		return GLib.Variant.new_tuple(*children)
	return variant


def _configure_pystray(app_name: str) -> bool:
	"""
	Install the pystray wrapper once and publish app_name.

	Caller holds the lock.

	Args:
		app_name: The application name shown by the desktop notification daemon.

	Returns:
		True if the pystray D-Bus notifier was patched, False otherwise.
	"""
	patch_state.app_name = app_name
	if patch_state.wrapper_installed:
		return True
	if notify_dbus is None or GLib is None:
		return False
	original = patch_state.pystray_notify_original
	if original is None:
		original = notify_dbus.Notifier.notify
		patch_state.pystray_notify_original = original

	def notify(self: Any, title: str, message: str, icon: str, *args: Any, **kwargs: Any) -> Any:
		# Serialize the instance monkey-patch so overlapping notify calls
		# cannot restore a stale call_sync.
		with NOTIFY_PATCH_LOCK:
			real_call_sync = self._notify.call_sync
			current_name = patch_state.app_name

			def call_sync(method: str, variant: Any, *call_args: Any, **call_kwargs: Any) -> Any:
				if method == "Notify":
					variant = _variant_with_app_name(variant, current_name)
				return real_call_sync(method, variant, *call_args, **call_kwargs)

			self._notify.call_sync = call_sync
			try:
				return original(self, title, message, icon, *args, **kwargs)
			finally:
				self._notify.call_sync = real_call_sync

	notify_dbus.Notifier.notify = notify
	patch_state.wrapper_installed = True
	return True


def configure_pystray_notification_app_name(app_name: str) -> bool:
	"""
	Make pystray desktop notifications identify as app_name on Linux.

	pystray hardcodes an empty D-Bus app_name, which notification daemons
	display as unknown. This wraps the notifier so an empty name is replaced.
	Safe to call repeatedly; the wrapper is installed once and subsequent calls
	only update the active application name.

	Args:
		app_name: The application name shown by the desktop notification daemon.

	Returns:
		True if the pystray D-Bus notifier was patched, False otherwise.
	"""
	app_name = app_name.strip()
	if not app_name or notify_dbus is None or GLib is None:
		return False
	with NOTIFY_PATCH_LOCK:
		return _configure_pystray(app_name)


def _current_windows_aumid() -> str | None:
	"""
	Get the process-explicit AppUserModelID.

	Returns:
		the AppUserModelID or None if unset/unavailable.
	"""
	if get_aumid is None:
		return None
	value = ctypes.c_wchar_p()
	allocated = False
	try:
		if int(get_aumid(ctypes.byref(value))) != S_OK:
			return None
		allocated = True
	except (OSError, ValueError, TypeError):
		return None
	else:
		return value.value or ""
	finally:
		if allocated and value and ole32 is not None:
			ole32.CoTaskMemFree(ctypes.cast(value, ctypes.c_void_p))


def set_windows_app_user_model_id(app_id: str) -> bool:
	"""
	Set the Windows AppUserModelID for labeling toast notifications.

	Safe to call repeatedly with the same identifier; the Win32 setter is
	invoked only when the live process-explicit ID is not already app_id.

	Args:
		app_id: an identifier.

	Returns:
		True if the AppUserModelID was set, False otherwise.
	"""
	app_id = app_id.strip()
	if app_id and sys.platform == "win32":
		with NOTIFY_PATCH_LOCK:
			with suppress(Exception):
				current = _current_windows_aumid()
				if current == app_id:
					patch_state.windows_app_id = app_id
					return True
			with suppress(Exception):
				# The API is LPCWSTR; HRESULT S_OK == 0. restype is c_long so
				# ctypes does not raise on a failed HRESULT.
				if set_aumid is not None and int(set_aumid(app_id)) == S_OK:
					patch_state.windows_app_id = app_id
					return True
	return False


def configure_notification_identity(app_name: str, windows_app_id: str) -> bool:
	"""
	Identify this process to desktop notification systems.

	The patch remains in effect for the rest of the process lifetime.

	Args:
		app_name: Visible application name for D-Bus notifications.
		windows_app_id: Windows AppUserModelID for toast attribution.

	Returns:
		True if patching occurred, False otherwise.
	"""
	status: list[bool] = [
		configure_pystray_notification_app_name(app_name),  # Platforms with D-BUS.
		set_windows_app_user_model_id(windows_app_id),  # Windows.
	]
	return any(status)
