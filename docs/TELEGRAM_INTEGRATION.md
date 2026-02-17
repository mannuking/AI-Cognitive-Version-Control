# CVC Telegram Integration — Remote Mobile Access

> **Status:** Planning / Pre-Implementation  
> **Date:** February 17, 2026  
> **Target:** Demo-ready by February 18, 2026 (AI Summit)

---

## Overview

The CVC Telegram Integration transforms any Telegram client (phone, tablet, desktop) into a full remote control interface for the CVC AI Coding Agent. Users can send coding tasks, receive streaming AI responses, and operate the **Time Machine** — all from their mobile phone while the CVC agent runs on their PC.

```
┌─────────────────┐     Long Polling      ┌──────────────────┐
│   Your Phone    │◄────────────────────►  │  Telegram API    │
│   (Telegram)    │                        │  (Cloud)         │
└─────────────────┘                        └────────┬─────────┘
                                                    │
                                                    │ getUpdates
                                                    ▼
                                           ┌──────────────────┐
                                           │  CVC Telegram    │
                                           │  Bridge          │
                                           │  (on your PC)    │
                                           │                  │
                                           │  python-telegram │
                                           │  -bot + asyncio  │
                                           └────────┬─────────┘
                                                    │
                                                    │ Direct Python call
                                                    ▼
                                           ┌──────────────────┐
                                           │  CVC AgentSession│
                                           │  .run_turn()     │
                                           │                  │
                                           │  Time Machine    │
                                           │  Tool Execution  │
                                           │  LLM Streaming   │
                                           └──────────────────┘
```

---

## Why Telegram (Not a Mobile App or WhatsApp)

### Mobile App — Rejected

| Factor | Issue |
|---|---|
| App Store approval | Apple takes weeks; Play Store 1–3 days |
| Two codebases | iOS + Android (or Flutter/React Native) |
| User adoption | Nobody installs an unknown app |
| Networking | Complex WebSocket/tunnel from phone to PC |
| Time to build | Weeks to months |

### WhatsApp — Rejected

| Factor | Issue |
|---|---|
| Official API | Requires Meta Business API — paid, slow approval |
| Unofficial libs | `whatsapp-web.js`, `Baileys` — high ban risk |
| Bot UX | No inline keyboards, no topics/threads |
| Python support | No mature official Python SDK |

### Telegram — Selected

| Factor | Advantage |
|---|---|
| Bot API | Free, official, no approval needed |
| Setup time | 2 minutes via @BotFather |
| Rich UI | Inline keyboards, buttons, Markdown, file sharing, topics |
| Ban risk | Zero — official API |
| Networking | Long polling — works behind NAT, no public IP needed |
| Python lib | `python-telegram-bot` v22+ — mature, fully async |
| User base | 950M+ monthly active users |

---

## Competitive Landscape (2026)

Existing tools that provide remote Telegram access to CLI coding agents:

| Project | Approach | Notes |
|---|---|---|
| **ductor** | Runs Claude Code / Codex CLI as subprocess, routes via Telegram | Pure Python, ~8k lines. Cron jobs, memory, webhooks. MIT. |
| **CCBot / ccmux** | Operates on tmux — reads terminal output, sends keystrokes | Can switch desktop ↔ Telegram mid-conversation. Python. |
| **claude-code-telegram** | Uses Claude Agent SDK directly, session persistence | 314 stars, inline approve/reject buttons. Python + Poetry. |
| **CCPA Telegram** | Minimalist bridge with `python-telegram-bot` long polling | No ports exposed, no static IP. Simplest approach. |
| **Telegram-Claude** | TypeScript + Effect, Claude Agent SDK | Each Telegram chat = one Claude session. |
| **whatsapp-claude-agent** | Same concept but for WhatsApp | Session persistence, model switching. |
| **Roo Code Telegram** | Monitors Roo Code task files, forwards to Telegram | 1600 lines Python, approve/reject buttons, TTS support. |

### CVC's Unique Advantage

All the tools above wrap *external* CLI binaries as subprocesses or scrape terminal output. **CVC is different** — the agent is pure Python with a clean async API:

- `AgentSession.run_turn(user_input)` can be called directly
- No subprocess spawning, no tmux, no screen scraping
- Full access to streaming events, tool calls, and Time Machine operations
- The Telegram bridge is a first-class citizen, not a hack

---

## Technical Design

### Dependencies

```
python-telegram-bot>=22.0    # Async Telegram Bot API
```

Single new dependency. Everything else is already in CVC.

### File Structure

```
cvc/
  telegram_bridge.py         # Main Telegram bot module (~400 lines)
```

### CLI Command

```bash
cvc telegram                           # Start with default workspace (cwd)
cvc telegram --workspace /path/to/project
cvc telegram --provider anthropic --model claude-sonnet-4-20250514
```

### Core Components

#### 1. TelegramBridge (Main Class)

```python
class TelegramBridge:
    """Bridges Telegram messages to CVC AgentSession."""
    
    def __init__(self, bot_token: str, allowed_users: list[int], workspace: Path):
        self.bot_token = bot_token
        self.allowed_users = allowed_users
        self.workspace = workspace
        self.sessions: dict[int, AgentSession] = {}  # chat_id → session
```

**Responsibilities:**
- Manages `python-telegram-bot` Application with long polling
- Creates one `AgentSession` per Telegram chat
- Routes messages to `AgentSession.run_turn()`
- Formats and sends responses back (with chunking for 4096-char limit)
- Handles inline keyboard callbacks for Time Machine operations

#### 2. Message Handler

```python
async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process incoming Telegram text messages."""
    user_id = update.effective_user.id
    if user_id not in self.allowed_users:
        return  # Silently ignore unauthorized users
    
    chat_id = update.effective_chat.id
    user_input = update.message.text
    
    # Get or create session
    session = await self._get_or_create_session(chat_id)
    
    # Send "typing" indicator
    await context.bot.send_chat_action(chat_id, ChatAction.TYPING)
    
    # Run the agent turn (captures output instead of printing to terminal)
    response = await session.run_turn(user_input)
    
    # Send response (chunked if needed)
    await self._send_response(chat_id, response, context)
```

#### 3. Time Machine Inline Keyboard

```python
def _time_machine_keyboard() -> InlineKeyboardMarkup:
    """Build inline keyboard for Time Machine operations."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Status", callback_data="cvc_status"),
            InlineKeyboardButton("📜 Log", callback_data="cvc_log"),
        ],
        [
            InlineKeyboardButton("🌿 Branches", callback_data="cvc_branches"),
            InlineKeyboardButton("💾 Commit", callback_data="cvc_commit"),
        ],
        [
            InlineKeyboardButton("⏪ Restore", callback_data="cvc_restore"),
            InlineKeyboardButton("🔀 Merge", callback_data="cvc_merge"),
        ],
    ])
```

#### 4. Response Formatter

Telegram has a 4096-character message limit. The formatter:
- Splits long responses at natural boundaries (paragraph, code block)
- Converts Rich markup to Telegram-compatible Markdown/HTML
- Wraps code blocks in Telegram's ` ```language ` syntax
- Sends tool call summaries as collapsible sections

#### 5. Output Capture

Instead of printing to the terminal via Rich console, the Telegram bridge captures agent output:

```python
class TelegramOutputCapture:
    """Captures AgentSession output for Telegram delivery."""
    
    def __init__(self, chat_id: int, bot: Bot):
        self.chat_id = chat_id
        self.bot = bot
        self.buffer = []
    
    async def on_text_token(self, token: str):
        """Accumulate streaming tokens, flush periodically."""
        self.buffer.append(token)
        # Flush every ~500 chars or on sentence boundary
        if self._should_flush():
            await self._flush()
    
    async def on_tool_call(self, name: str, args: dict):
        """Send tool call notification."""
        await self.bot.send_message(
            self.chat_id,
            f"🔧 *{name}*: {_humanize_tool_args(name, args)}",
            parse_mode="Markdown",
        )
```

### Authentication & Security

```python
# Only these Telegram user IDs can interact with the bot
ALLOWED_USERS = [123456789]  # Set via env var or config

# Per-message auth check
if update.effective_user.id not in ALLOWED_USERS:
    return  # Silent ignore — don't reveal the bot exists
```

**Security model:**
- **User whitelist** — only authorized Telegram user IDs can interact
- **No ports exposed** — long polling means your PC connects outward to Telegram servers
- **No public IP** — works behind any NAT/firewall
- **Directory sandboxing** — agent operates only within the configured workspace
- **Same permissions as CLI** — no privilege escalation

### Configuration

Stored in CVC's global config (`~/.cvc/config.json`):

```json
{
    "telegram": {
        "bot_token": "1234567890:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        "allowed_users": [123456789],
        "workspace": "/home/user/projects/my-app",
        "send_tool_calls": true,
        "stream_responses": true,
        "auto_commit": true
    }
}
```

Or via environment variables:

```bash
export CVC_TELEGRAM_BOT_TOKEN="your-token-here"
export CVC_TELEGRAM_ALLOWED_USERS="123456789,987654321"
```

---

## Telegram Bot Commands

### Slash Commands (in Telegram)

| Command | Description |
|---|---|
| `/start` | Welcome message + setup instructions |
| `/status` | Show CVC branch, HEAD, and branch list |
| `/log` | Show commit history for active branch |
| `/branches` | List all branches |
| `/commit <msg>` | Create a manual cognitive commit |
| `/branch <name>` | Create and switch to a new branch |
| `/restore <hash>` | Restore context to a previous commit |
| `/merge <source>` | Merge source branch into active branch |
| `/timemachine` | Show Time Machine inline keyboard |
| `/cost` | Show session cost summary |
| `/help` | Show all available commands |
| `/stop` | Gracefully stop the agent session |

### Natural Language

Any non-command message is forwarded directly to the CVC agent as a coding task:

```
You: Create a REST API with FastAPI that has user authentication
Bot: 🔧 write_file: src/main.py
     🔧 write_file: src/auth.py
     🔧 bash: `pip install fastapi uvicorn`
     
     I've created a FastAPI application with JWT-based authentication...
     [full response with code]
```

### Inline Keyboard Interactions

The Time Machine keyboard provides tap-to-execute buttons:

```
┌──────────┬──────────┐
│ 📊 Status│ 📜 Log   │
├──────────┼──────────┤
│ 🌿 Branch│ 💾 Commit│
├──────────┼──────────┤
│ ⏪ Restore│ 🔀 Merge │
└──────────┴──────────┘
```

When "Restore" is tapped, a second keyboard appears with recent commits:

```
Which commit to restore?
┌────────────────────────────┐
│ a1b2c3d — Added auth layer │
│ e4f5g6h — Initial API      │
│ ❌ Cancel                   │
└────────────────────────────┘
```

---

## Setup Guide

### Step 1: Create a Telegram Bot (2 minutes)

1. Open Telegram on your phone
2. Search for `@BotFather`
3. Send `/newbot`
4. Choose a name: `CVC Agent`
5. Choose a username: `my_cvc_agent_bot`
6. Copy the bot token: `1234567890:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`

### Step 2: Get Your Telegram User ID

1. Search for `@userinfobot` on Telegram
2. Send `/start`
3. It replies with your user ID (e.g., `123456789`)

### Step 3: Configure CVC

```bash
cvc setup --telegram
# Or manually:
export CVC_TELEGRAM_BOT_TOKEN="your-token-here"
export CVC_TELEGRAM_ALLOWED_USERS="123456789"
```

### Step 4: Start the Bridge

```bash
cvc telegram
```

Output:
```
╭── Meena ─────────────────── v1.4.81 ──╮
│                                        │
│  CVC Telegram Bridge                   │
│  Bot: @my_cvc_agent_bot               │
│  Workspace: /home/user/my-project      │
│  Allowed users: 1                      │
│  Status: Polling...                    │
│                                        │
╰────────────────────────────────────────╯
```

### Step 5: Chat from Your Phone

Open your bot in Telegram and start coding!

---

## Implementation Plan

### Phase 1: Core Bridge (Demo-Ready) — February 18, 2026

- [ ] `cvc/telegram_bridge.py` — TelegramBridge class
- [ ] Message handler → `AgentSession.run_turn()` pipeline
- [ ] Output capture (replace Rich console with Telegram messages)
- [ ] Response chunking (4096-char limit)
- [ ] User whitelist authentication
- [ ] `/start`, `/help`, `/status`, `/log`, `/stop` commands
- [ ] Time Machine inline keyboard
- [ ] `cvc telegram` CLI command
- [ ] Bot token configuration via env var or config file

### Phase 2: Enhanced UX — February 20, 2026

- [ ] Streaming responses (edit message in-place as tokens arrive)
- [ ] Tool call notifications with inline details
- [ ] `/restore` with interactive commit picker (inline keyboard)
- [ ] `/branch` with branch list keyboard
- [ ] File sharing (send edited files as Telegram documents)
- [ ] Image support (send screenshots to agent via Telegram photos)
- [ ] Voice message transcription → agent input
- [ ] Session persistence across bot restarts
- [ ] Multi-workspace support (switch projects via command)

### Phase 3: Production Features — Future

- [ ] Multi-user support (each user gets isolated session)
- [ ] Rate limiting and abuse prevention
- [ ] Webhook mode (for VPS deployment)
- [ ] Telegram Mini App for rich UI (file browser, diff viewer)
- [ ] CI/CD webhook integration (agent responds to build failures)
- [ ] Scheduled tasks (cron-like agent jobs)
- [ ] End-to-end encryption layer
- [ ] Voice-activated mode (speech-to-text → agent → text-to-speech)

---

## Key Technical Decisions

### Long Polling vs Webhook

**Decision: Long Polling**

| Factor | Long Polling | Webhook |
|---|---|---|
| Setup | Zero — works immediately | Needs public IP, domain, SSL cert |
| NAT/Firewall | Works behind any NAT | Must be publicly accessible |
| Latency | ~1-2s (polling interval) | Near-instant |
| Scaling | Fine for single user | Better for high-volume bots |
| Demo-ready | Yes | No |

Long polling is perfect for a personal-use developer tool. Switch to webhooks later if deploying to a VPS.

### Direct Import vs Subprocess

**Decision: Direct Python Import**

| Factor | Direct Import | Subprocess |
|---|---|---|
| Performance | Native, zero overhead | Process spawn overhead |
| Streaming | Full access to streaming events | Must parse stdout |
| Error handling | Python exceptions | Exit codes + stderr parsing |
| Integration depth | Full access to AgentSession, Engine, DB | Text-only interface |
| Complexity | Simple — just call `run_turn()` | Complex — PTY, pipes, encoding |

CVC's pure Python architecture makes direct import the obvious choice. This is a major advantage over tools like ductor/ccmux that must wrap external CLI binaries.

### Response Delivery: Full vs Streaming

**Decision: Streaming (edit-in-place)**

Telegram's `editMessageText` API allows updating a message in real-time. The bot:
1. Sends an initial "Thinking..." message
2. Edits it every ~500ms with accumulated tokens
3. Sends the final complete response

This gives users real-time feedback, similar to watching the CLI stream.

**Rate limit consideration:** Telegram allows ~30 message edits per second per chat. Batching tokens every 500ms stays well within limits.

---

## Environment & Compatibility

| Requirement | Details |
|---|---|
| Python | 3.10+ (same as CVC) |
| OS | Windows, macOS, Linux |
| Network | Outbound HTTPS to `api.telegram.org` (port 443) |
| Firewall | No inbound ports needed |
| Dependencies | `python-telegram-bot>=22.0` |
| Telegram client | Any — iOS, Android, Desktop, Web |

---

## Demo Script (AI Summit — February 18, 2026)

### 1. Setup (30 seconds)
```
"I've created a Telegram bot and configured CVC with one command."
$ cvc telegram
→ Bot starts, shows "Polling..."
```

### 2. Basic Coding (2 minutes)
```
[Pick up phone, open Telegram]
"Build a FastAPI app with JWT auth and a /users endpoint"
→ Show agent running tools, writing files on the laptop screen
→ Show response appearing on phone
```

### 3. Time Machine (1 minute)
```
[Tap ⏪ Restore button on phone]
→ Show commit list with inline keyboard
→ Tap a previous commit
→ "Context restored to commit a1b2c3d"
→ "Now I'm back in time, from my phone"
```

### 4. Key Message
```
"This is CVC — the first version control system for AI conversations.
 And now you can operate it from anywhere.
 Your sofa, your commute, your phone.
 Full coding agent. Full Time Machine. Zero setup."
```

---

## References

- [python-telegram-bot docs](https://docs.python-telegram-bot.org/en/v22.4/)
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [ductor — CLI agent via Telegram](https://github.com/PleasePrompto/ductor)
- [CCBot — tmux-based Claude Code remote](https://github.com/six-ddc/ccmux)
- [claude-code-telegram](https://github.com/RichardAtCT/claude-code-telegram)
- [CCPA Telegram (Medium)](https://medium.com/@amirilovic/how-to-use-claude-code-from-your-phone-with-a-telegram-bot-dde2ac8783d0)
- [WhatsApp Claude Agent](https://github.com/dsebastien/whatsapp-claude-agent)
- [Roo Code Telegram Enhancement](https://github.com/RooCodeInc/Roo-Code/issues/11146)
