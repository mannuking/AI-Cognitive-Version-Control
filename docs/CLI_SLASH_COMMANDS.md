# CVC CLI Agent — Slash Commands Reference (v1.4.81)

This is a source-of-truth list of slash commands supported by the CVC interactive agent (`cvc agent`).

## Total Slash Commands

- **31 total slash commands** (including aliases)
- **28 primary commands** + **3 exit aliases** (`/exit`, `/quit`, `/q`)

## Full Command List

| # | Command | Description |
|---|---|---|
| 1 | `/help` | Show command help |
| 2 | `/status` | Show CVC status (branch, HEAD, context, provider/model) |
| 3 | `/log` | Show CVC commit history |
| 4 | `/commit <msg>` | Create a cognitive checkpoint |
| 5 | `/branch <name>` | Create and switch to a branch |
| 6 | `/checkout <name>` | Switch to an existing branch |
| 7 | `/branches` | List all branches |
| 8 | `/merge <source>` | Merge source branch into current branch |
| 9 | `/restore <hash>` | Restore to a previous commit |
| 10 | `/search <query>` | Search CVC commit/context history |
| 11 | `/files [pattern]` | List workspace files (optional filter) |
| 12 | `/summary` | Show codebase structure summary |
| 13 | `/diff [file]` | Show recent diffs or a specific file diff |
| 14 | `/continue` | Continue AI response from last point |
| 15 | `/model [name]` | Switch model interactively or by name |
| 16 | `/provider` | Switch LLM provider interactively |
| 17 | `/undo` | Undo last file change |
| 18 | `/web <query>` | Web search for docs/errors |
| 19 | `/git` | Git status (default) |
| 20 | `/cost` | Show session cost summary |
| 21 | `/analytics` | Show detailed session/usage analytics |
| 22 | `/image <path> [prompt]` | Attach image file (optionally send prompt inline) |
| 23 | `/paste [prompt]` | Attach clipboard image (optionally send prompt inline) |
| 24 | `/memory` | Show persistent memory from past sessions |
| 25 | `/serve` | Start CVC proxy in a new terminal |
| 26 | `/init` | Initialize CVC in current workspace |
| 27 | `/compact` | Compact/summarize conversation |
| 28 | `/clear` | Clear current conversation (keep CVC state) |
| 29 | `/exit` | Exit agent |
| 30 | `/quit` | Exit agent |
| 31 | `/q` | Exit agent (short alias) |

## `/git` Subcommands

`/git` has built-in subcommands:

- `/git` → status
- `/git commit <msg>`
- `/git log`
- `/git diff`

## Notes for Website Documentation

- Source parser: `cvc/agent/chat.py` (`handle_slash_command`)
- Help rendering: `cvc/agent/renderer.py` (`print_help`)
- The parser supports **31** commands including aliases.
- Tab-completion list currently includes a subset (not all parser commands), but the full supported set is the table above.
