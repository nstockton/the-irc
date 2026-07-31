# Copyright (C) 2026 Nick Stockton
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Manage and play sounds."""

# Future Modules:
from __future__ import annotations

# Built-in Modules:
import logging
import threading
from array import array
from collections.abc import Generator
from contextlib import closing, suppress
from pathlib import Path
from typing import Any, Final, TypeAlias, cast

# Third-party Modules:
import miniaudio
from knickknacks.numbers import clamp


# Constants:
UINT8_MIN: Final[int] = 0
UINT8_MAX: Final[int] = 0xFF
INT16_MIN: Final[int] = -0x8000
INT16_MAX: Final[int] = 0x7FFF
INT32_MIN: Final[int] = -0x80000000
INT32_MAX: Final[int] = 0x7FFFFFFF
DEFAULT_VOLUME: Final[float] = 1.0
FramesType: TypeAlias = bytes | array[Any]
PlaybackCallbackGeneratorType: TypeAlias = Generator[FramesType, int, None]


# Globals:
logger: Final[logging.Logger] = logging.getLogger(__name__)


def scale_uint8(arr: array[int], volume: float) -> array[int]:
	"""
	Scale an unsigned 8-bit integer audio array by the given volume factor.

	If the volume is exactly 1.0, the original array is returned unchanged
	to avoid unnecessary processing. Otherwise, each sample is shifted
	around the 128 midpoint, scaled, and clamped to the valid uint8 range.

	Note:
		The array is modified in place.

	Args:
		arr: The input audio array containing uint8 samples.
		volume: The volume scaling factor to apply.

	Returns:
		The original array with volume-adjusted samples.
	"""
	if volume != 1:
		mv = memoryview(arr)
		for i in range(len(mv)):
			mv[i] = round(clamp((mv[i] - 128) * volume + 128, UINT8_MIN, UINT8_MAX))
	return arr


def scale_int16(arr: array[int], volume: float) -> array[int]:
	"""
	Scale a signed 16-bit integer audio array by the given volume factor.

	If the volume is exactly 1.0, the original array is returned unchanged.
	Otherwise, samples are multiplied by the volume and clamped to the
	valid int16 range.

	Note:
		The array is modified in place.

	Args:
		arr: The input audio array containing int16 samples.
		volume: The volume scaling factor to apply.

	Returns:
		The original array with volume-adjusted samples.
	"""
	if volume != 1:
		mv = memoryview(arr)
		for i in range(len(mv)):
			mv[i] = round(clamp(mv[i] * volume, INT16_MIN, INT16_MAX))
	return arr


def scale_int32(arr: array[int], volume: float) -> array[int]:
	"""
	Scale a signed 32-bit integer audio array by the given volume factor.

	If the volume is exactly 1.0, the original array is returned unchanged.
	Otherwise, samples are multiplied by the volume and clamped to the
	valid int32 range.

	Note:
		The array is modified in place.

	Args:
		arr: The input audio array containing int32 samples.
		volume: The volume scaling factor to apply.

	Returns:
		The original array with volume-adjusted samples.
	"""
	if volume != 1:
		mv = memoryview(arr)
		for i in range(len(mv)):
			mv[i] = round(clamp(mv[i] * volume, INT32_MIN, INT32_MAX))
	return arr


def scale_float32(arr: array[float], volume: float) -> array[float]:
	"""
	Scale a 32-bit floating-point audio array by the given volume factor.

	If the volume is exactly 1.0, the original array is returned unchanged.
	Otherwise, samples are multiplied by the volume and clamped to the
	normalized range of -1.0 to 1.0.

	Note:
		The array is modified in place.

	Args:
		arr: The input audio array containing float32 samples.
		volume: The volume scaling factor to apply.

	Returns:
		The original array with volume-adjusted samples.
	"""
	if volume != 1:
		mv = cast(memoryview[float], memoryview(arr))
		for i in range(len(mv)):
			mv[i] = clamp(mv[i] * volume, -1.0, 1.0)
	return arr


def _volume_scaled_stream(
	inner: PlaybackCallbackGeneratorType, volume: float
) -> PlaybackCallbackGeneratorType:
	"""
	Internal generator wrapper that applies volume scaling to audio chunks.

	It receives frame-count requests via .send(), forwards them to the inner
	miniaudio generator, receives raw chunks, scales them according to their
	typecode (uint8, int16, int32, or float32), and yields the result.

	Args:
		inner: The original generator returned by miniaudio.stream_file.
		volume: Volume scaling factor to apply to each audio chunk.

	Yields:
		Volume-scaled audio data chunks (as array objects).
	"""
	sent: int = yield b""  # Accept the first framecount from miniaudio.
	with closing(inner), suppress(StopIteration):
		while True:
			# Forward the requested frame count to retrieve the next audio chunk.
			chunk = inner.send(sent)
			if isinstance(chunk, array):
				typecode = chunk.typecode
				if typecode == "B":
					chunk = scale_uint8(chunk, volume)
				elif typecode == "h":
					chunk = scale_int16(chunk, volume)
				elif chunk.itemsize == 4 and typecode in {"i", "l"}:
					chunk = scale_int32(chunk, volume)
				elif typecode == "f":
					chunk = scale_float32(chunk, volume)
			sent = yield chunk


def stream_file(
	*args: Any, volume: float | None = None, **kwargs: Any
) -> tuple[PlaybackCallbackGeneratorType, threading.Event]:
	"""
	Create a generator that streams audio from a file with optional volume scaling.

	This function wraps miniaudio.stream_file. When volume differs from 1.0,
	it delegates to an internal scaling generator. The returned generator
	is primed (via next()) so that the first send() call from the caller
	provides the desired frame count, matching miniaudio's generator protocol.

	Args:
		*args: Positional arguments passed directly to miniaudio.stream_file.
		volume: Volume scaling factor (1.0 disables scaling).
		**kwargs: Keyword arguments passed directly to miniaudio.stream_file.

	Returns:
		A tuple of (stream_generator, finished_event) where
			stream_generator is a primed generator that yields volume-scaled
			audio chunks (as array objects) when sent frame counts via .send(),
			and finished_event is a threading.Event that is set when the audio
			stream finishes (or is closed).
	"""
	if volume is None:
		volume = DEFAULT_VOLUME
	# miniaudio.stream_file returns a primed generator.
	inner: PlaybackCallbackGeneratorType = miniaudio.stream_file(*args, **kwargs)
	if volume != 1:
		# Wrap inner generator to yield scaled audio chunks.
		inner = _volume_scaled_stream(inner, volume)
		# Prime the wrapped generator.
		next(inner)
	finished = threading.Event()
	# Wrap inner generator to call finished.set after iteration stops.
	wrapped = miniaudio.stream_with_callbacks(inner, end_callback=finished.set)
	# Prime the wrapped generator.
	next(wrapped)
	return wrapped, finished


def _play_sound(filepath: Path, *args: Any, volume: float | None = None, **kwargs: Any) -> None:
	"""
	Play the specified audio file using miniaudio.

	This private helper function blocks the calling thread until playback finishes.
	It is designed to be executed inside a daemon thread. Any MiniaudioError is silently suppressed.

	Args:
		filepath: The resolved path to the audio file to play.
		*args: Additional positional arguments passed through to miniaudio.PlaybackDevice.
		volume: The volume scaling factor to apply.
		**kwargs: Additional keyword arguments passed through to miniaudio.PlaybackDevice.
	"""
	with suppress(miniaudio.MiniaudioError):
		stream, finished = stream_file(filepath, volume=volume)
		with miniaudio.PlaybackDevice(*args, **kwargs) as device:
			device.start(stream)
			# Keep the thread alive until playback finishes
			finished.wait()


def play_sound(filename: str | Path, *args: Any, volume: float | None = None, **kwargs: Any) -> None:
	"""
	Play a sound file asynchronously in a daemon thread.

	The function resolves the given path and immediately returns if the file does not exist.
	Playback occurs in a background daemon thread so it does not block the calling code.

	Args:
		filename: Path to the audio file as a string or Path object.
		*args: Additional positional arguments passed through to the playback device.
		volume: The volume to use when playing the sound (0.0 to 1.0).
		**kwargs: Additional keyword arguments passed through to the playback device.
	"""
	if volume is not None and volume <= 0:
		# No point trying to play a sound if no volume.
		return
	filepath = Path(filename).resolve()
	if not filepath.is_file():
		logger.debug(f"Audio file {filepath} does not exist.")
		return
	# Run in daemon thread so it doesn't block the GUI.
	threading.Thread(
		target=_play_sound, args=(filepath, *args), kwargs={"volume": volume, **kwargs}, daemon=True
	).start()


def get_audio_devices() -> dict[Any, str]:
	"""
	Retrieve available audio playback devices from all enabled backends.

	The function queries each enabled miniaudio backend, collects playback devices,
	and builds a mapping of device ID to a human-readable string that includes
	the device name and backend name.

	Returns:
		Dictionary mapping device IDs to strings in the format "name (backend)".
	"""
	results: dict[Any, str] = {}
	for backend in miniaudio.get_enabled_backends():
		with suppress(miniaudio.MiniaudioError):
			device = miniaudio.Devices([backend])
			for playback in device.get_playbacks():
				playback_id = playback.get("id")
				if playback_id is not None:
					results[playback_id] = f"{playback.get('name', 'Unknown')} ({device.backend})"
	return results
