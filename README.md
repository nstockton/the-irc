# The IRC

A minimalistic, accessible, cross-platform graphical IRC client for TheIRC.net.

[![License: MPL 2.0](https://img.shields.io/badge/License-MPL_2.0-brightgreen.svg)](https://opensource.org/licenses/MPL-2.0)

## Features

- **Minimalistic design** with a clean, high-contrast interface
- Built with **screen reader accessibility** in mind
- **Speech output** support (toggleable globally or per individual tab)
- Sound notifications for mentions and incoming private messages
- Support for modern **IRCv3** features:
  - echo-message
  - labeled-response
  - CHATHISTORY
  - BATCH
  - message-tags
  - server-time
- SASL PLAIN authentication + optional server password
- Secure TLS/SSL connections (with optional certificate verification)
- Nickname completion in channel tabs (`Ctrl+\`)
- Per-tab and global speech control with persistent settings
- System tray support (press `Escape` to hide the main window)
- Cross-platform (Windows, macOS, Linux)

## Installation

### Windows

Pre-built binaries are available on the [Releases page](https://github.com/nstockton/the-irc/releases/latest).

### macOS and Linux

This project is designed to be run using [uv](https://docs.astral.sh/uv/).

1. Install `uv` (if you don't already have it):

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. Run the client directly from the Git repository:

   ```bash
   uvx --from git+https://github.com/nstockton/the-irc.git theirc
   ```

## Getting Started

1. Launch **The IRC**.
2. Go to **Server > Connect...**
3. The default server (`irc.theirc.net:6697`) is pre-filled.
4. Enter your nickname and authentication details.
5. Click **Connect** and start chatting!

New private messages and channels you join will automatically open as tabs.

## Keyboard Shortcuts

| Shortcut                  | Action                                      |
|---------------------------|---------------------------------------------|
| `Ctrl + W` / `Ctrl + F4`  | Close current tab                           |
| `F3`                      | Open list of extracted URLs   |
| `F5`                      | Enable speech output globally               |
| `F6`                      | Disable speech output globally              |
| `Ctrl + F5`               | Enable speech for the current tab only      |
| `Ctrl + F6`               | Disable speech for the current tab only     |
| `F7`                      | Lower notification sound volume             |
| `F8`                      | Raise notification sound volume             |
| `Escape`                  | Hide main window (minimize to tray)         |
| `Ctrl + \` (in channels)  | Nickname completion / cycle through matches |

## Slash Commands

| Command              | Description                              |
|----------------------|------------------------------------------|
| `/join #channel`     | Join a channel                           |
| `/part [#channel]`   | Leave the current (or specified) channel |
| `/query nick`        | Open a private query with a user         |
| `/me action text`    | Send a CTCP ACTION message               |
| `/quit`              | Disconnect and exit                      |
| Any other `/command` | Sent as a raw IRC command                |

## Development

This project uses [uv](https://docs.astral.sh/uv/) for dependency management and [prek](https://github.com/j178/prek) for fast pre-commit hooks.

### Setting up a development environment

```bash
git clone https://github.com/nstockton/the-irc.git
cd the-irc

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# Install the pinned version of uv and sync dependencies
pip install --upgrade --require-hashes --requirement requirements-uv.txt
uv sync --frozen

# Install pre-commit and pre-push hooks
prek install -t pre-commit
prek install -t pre-push
```

## License

This project is licensed under the **Mozilla Public License 2.0**.

Copyright (C) 2026 Nick Stockton

See the [LICENSE](LICENSE) file for the full license text.
