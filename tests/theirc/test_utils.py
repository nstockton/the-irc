# Copyright (C) 2026 Nick Stockton
# SPDX-License-Identifier: MPL-2.0
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Future Modules:
from __future__ import annotations

# Built-in Modules:
from pathlib import Path
from unittest import TestCase, mock

# The IRC Modules:
from theirc import utils


class TestUtils(TestCase):
	@mock.patch("theirc.utils.is_frozen")
	def test_get_data_path(self, mock_is_frozen: mock.Mock) -> None:
		subdirectory: tuple[str, ...] = ("level1", "level2")
		frozen_output = Path(utils.__file__).parent.joinpath(utils.DATA_DIRECTORY, *subdirectory).resolve()
		not_frozen_output = (
			Path(utils.__file__).parent.parent.joinpath(utils.DATA_DIRECTORY, *subdirectory).resolve()
		)
		mock_is_frozen.return_value = True
		self.assertEqual(utils.get_data_path(*subdirectory), frozen_output)
		mock_is_frozen.return_value = False
		self.assertEqual(utils.get_data_path(*subdirectory), not_frozen_output)

	def test_reduce_or(self) -> None:
		self.assertEqual(utils.reduce_or([]), 0)
		self.assertEqual(utils.reduce_or([], initial=4), 4)
		self.assertEqual(utils.reduce_or([2, 16, 32]), 50)
