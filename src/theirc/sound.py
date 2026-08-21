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
MAX_CONCURRENT_PLAYERS: Final[int] = 1
PLAYERS_LOCK: Final[threading.Lock] = threading.Lock()
FramesType: TypeAlias = bytes | array[Any]
PlaybackCallbackGeneratorType: TypeAlias = Generator[FramesType, int, None]


# Globals:
logger: Final[logging.Logger] = logging.getLogger(__name__)
_players: list[SoundPlayer] = []


class SoundPlayer(threading.Thread):
	"""
	Long-lived audio playback thread that owns a single miniaudio device.

	A SoundPlayer instance creates a stereo FLOAT32 PlaybackDevice at 44100 Hz
	and runs an infinite generator that either streams the currently assigned
	audio or yields silence. New sounds are started by replacing the active
	stream under a lock; the previous stream is closed safely from the audio
	callback thread. The thread is started as a daemon and remains alive for
	the lifetime of the process.
	"""

	def __init__(self) -> None:
		"""Initialize the constructor."""
		super().__init__(name="sound-player", daemon=True)
		self._lock = threading.Lock()
		self._stream: PlaybackCallbackGeneratorType | None = None
		self._finished = threading.Event()
		self._device: Any | None = None
		try:
			self._device = miniaudio.PlaybackDevice(
				output_format=miniaudio.SampleFormat.FLOAT32,
				nchannels=2,
				sample_rate=44100,
				buffersize_msec=20,
			)
		except miniaudio.MiniaudioError:
			logger.exception("Failed to create playback device.")
		self.start()

	def play(self, filepath: Path, volume: float | None = None) -> None:
		"""
		Start (or replace) playback of the given audio file.

		Opens a volume-scaled stream for the file and installs it as the
		active generator. If a previous stream is still running it will be
		closed by the audio callback after the current chunk is produced.
		Errors from miniaudio are silently ignored so that a missing or
		unsupported file does not raise.

		Args:
			filepath: Absolute or relative path to the audio file to play.
			volume: Optional volume scaling factor (defaults to 1.0). Values
				<= 0 are treated as silence by the caller.
		"""
		try:
			stream, finished = stream_file(
				str(filepath),
				volume=volume,
				output_format=miniaudio.SampleFormat.FLOAT32,
				nchannels=2,
				sample_rate=44100,
			)
		except miniaudio.MiniaudioError:
			return
		with self._lock:
			self._stream = stream
			self._finished = finished

	def run(self) -> None:
		"""
		Main loop of the playback thread.

		Creates an infinite generator that the PlaybackDevice drives. The
		generator yields silence while no stream is active or after a stream
		has finished, and otherwise forwards frame-count requests to the
		current stream. Short final chunks are zero-padded so the device
		always receives the exact number of frames it requested. The thread
		blocks forever on an Event after the device is started, keeping the
		player alive until process exit.
		"""
		if self._device is None:
			return

		def gen() -> PlaybackCallbackGeneratorType:
			nframes = yield b""
			silence = array("f", [0.0] * (nframes * 2))
			while True:
				with self._lock:
					stream = self._stream
					finished = self._finished
				if stream is None or finished.is_set():
					nframes = yield silence
					if len(silence) != nframes * 2:
						silence = array("f", [0.0] * (nframes * 2))
					continue
				try:
					chunk = stream.send(nframes)
				except (StopIteration, Exception) as e:
					with self._lock:
						if self._stream is stream:
							self._stream = None
					finished.set()
					nframes = yield silence
					if not isinstance(e, StopIteration):
						with suppress(Exception):
							stream.close()
						logger.exception("Error while streaming audio")
					continue
				# Pad a short final chunk so the device always
				# receives the exact number of frames it requested.
				if isinstance(chunk, array) and chunk.typecode == "f":
					expected = nframes * 2
					if len(chunk) < expected:
						padded = array("f", [0.0] * expected)
						padded[: len(chunk)] = chunk
						chunk = padded
				# If this stream was replaced while we were producing the
				# chunk, close the old generator now (same thread, safe).
				with self._lock, suppress(Exception):
					if self._stream is not stream:
						stream.close()
				# stream_file was asked for FLOAT32, so this should already be correct.
				nframes = yield chunk

		g = gen()
		next(g)
		self._device.start(g)
		threading.Event().wait()  # Keep thread alive for process lifetime.


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


def play_sound(filename: str | Path, *, volume: float | None = None) -> None:
	"""
	Play a sound file asynchronously in a daemon thread.

	The function resolves the given path and immediately returns if the file does not exist.

	Args:
		filename: Path to the audio file as a string or Path object.
		volume: The volume to use when playing the sound (0.0 to 1.0).
	"""
	if volume is not None and volume <= 0:
		# No point trying to play a sound if no volume.
		return
	filepath = Path(filename).resolve()
	if not filepath.is_file():
		logger.debug(f"Audio file {filepath} does not exist.")
		return
	with PLAYERS_LOCK:
		while len(_players) < MAX_CONCURRENT_PLAYERS:
			_players.append(SoundPlayer())  # Starts a new thread.
	_players[0].play(filepath, volume=volume)


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
