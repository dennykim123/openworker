# MeowWorker

**Built on [OpenWorker](https://openworker.com)** · [Subscription connections](#chatgpt-claude-and-gemini-subscription-bridge) · [Issues](https://github.com/dennykim123/meowworker/issues)

> **Your AI coworker that gets things done.**

**MeowWorker is an independent product built from the open-source OpenWorker project.** It is not affiliated with OpenWorker, OpenAI, Anthropic, or Google. Its ChatGPT, Claude, and Gemini subscription providers are not part of the upstream OpenWorker release or update channel.

It runs on your machine and doesn't lock you into any model: bring your own API key for OpenAI, Anthropic, Google, or an open-weight provider, or run fully local with Ollama. Your data leaves your machine only through the model and integrations *you* choose.

## ChatGPT, Claude, and Gemini subscription bridge

MeowWorker adds **ChatGPT subscription access through Codex**, **Claude subscription access through Claude Code**, and **Google AI Pro/Ultra access through Gemini CLI**. It is not an official OpenWorker, OpenAI, Anthropic, or Google release.

- No OpenAI, Anthropic, or Google API key is required for these three providers.
- MeowWorker does not read token files or copy OAuth tokens. It delegates model turns to the locally installed `codex`, `claude`, or `gemini` executable.
- Codex runs in ephemeral, read-only mode. Claude Code runs with built-in tools, MCP, project settings, and session persistence disabled. Gemini CLI runs in an empty temporary workspace with plan-mode approvals.
- Model requests still leave your Mac for the selected provider, and normal subscription limits and terms apply.
- The OpenWorker agent remains responsible for its own tools and approval prompts; the subscription subprocesses do not operate tools themselves.

Requirements:

For ChatGPT, use a plan with Codex access and make sure `codex login status` reports `Logged in using ChatGPT` rather than an API key.

For Claude, install Claude Code and sign in with a Claude.ai Pro, Max, Team, or Enterprise account. `claude auth status` must report `authMethod: claude.ai` and `apiProvider: firstParty`.

For Gemini, install the official Gemini CLI and sign in with the Google account attached to Google AI Pro or Ultra. The bridge removes API-key and Vertex AI environment overrides from this runtime so this provider cannot silently bill an API key.

After launching MeowWorker, open **Models** and choose a subscription card. One click starts the official runtime's browser sign-in, then the card updates automatically when the login succeeds. No terminal command or token copy is required. If the runtime is missing, the same screen links to its official installer.

> **Claude distribution note:** Anthropic's current [authentication and credential-use policy](https://code.claude.com/docs/en/legal-and-compliance#authentication-and-credential-use) directs third-party products to API-key authentication and says third-party developers may not offer Claude.ai login or route Free, Pro, or Max credentials for users. The Claude subscription path in MeowWorker is therefore an experimental local integration, not an Anthropic-endorsed distribution path. Use an Anthropic API key for a public, organizational, or policy-cleared deployment.

> **Gemini distribution note:** Google's current [Gemini CLI FAQ](https://geminicli.com/docs/resources/faq/#why-cant-i-use-third-party-software-like-claude-code-openclaw-or-opencode-with-gemini-cli) says third-party software must not piggyback on Gemini CLI OAuth and directs third-party coding agents to Google AI Studio or Vertex AI API keys. The Gemini subscription path is therefore an experimental local integration, not a Google-endorsed distribution path. Use the existing Gemini API-key provider for a public, organizational, or policy-cleared deployment.

[![How OpenWorker works](docs/assets/how-it-works.png)](https://openworker.com)

## Installation status

MeowWorker does not yet publish a signed, notarized installer. The official OpenWorker download does **not** include these subscription connections. For now, use [Run from source](#run-from-source) or inspect the reproducible GitHub Actions build artifacts.

## How it works

1. Tell MeowWorker the outcome you want - "prepare a customer brief," "untangle my calendar," "draft a report," "check where the release stands across Jira and GitHub."
2. It breaks the task into steps and works across your desktop, files, and connected apps.
3. Before anything consequential - sending a message, changing a calendar, running a command - it checks in and you approve or redirect.
4. You get the finished deliverable, not a to-do list.

Under the hood:

```text
┌────────────────────────────────────────────────┐
│                 MeowWorker app                  │  native shell + GUI
├────────────────────────────────────────────────┤
│           local agent server (Python)          │  engine · tools · connectors - built on aisuite
├───────────────┬────────────────┬───────────────┤
│  your files   │   your tools   │  your model   │  everything runs with your keys,
│  & terminal   │ 25+ connectors │  any provider │  on your machine
└───────────────┴────────────────┴───────────────┘
```

## What it can do

- **Produce real deliverables** - documents, spreadsheets, reports, and web pages land as files you can open and share.
- **Work from Slack** - mention `@OpenWorker` in a channel; a session opens on your desktop, the work happens with your tools, and the answer comes back as a thread reply.
- **Use your everyday tools** - 25+ integrations including GitHub, Slack, Jira, Notion, Linear, HubSpot, Outlook, monday.com, Gmail, and Google Calendar, plus your **terminal and local files**. Any tool reachable over [MCP](https://modelcontextprotocol.io/) plugs in too, with per-tool control.
- **Run on a schedule** - automations for recurring work: a morning brief, a weekly report, a standing watch over a channel. Runs land in the app with full transcripts.
- **Ask before acting** - writes, sends, and shell commands are approval-gated. Unattended runs park their asks in an inbox instead of acting on their own.

## Bring your own model

Model access is yours: pick a provider and switch anytime. MeowWorker supports:

**ChatGPT subscription through Codex · Claude subscription through Claude Code · Gemini subscription through Gemini CLI · OpenAI API · Anthropic API · Google Gemini API · Inkling (Thinking Machines) · GLM (Z.ai) · DeepSeek · Kimi (Moonshot) · Qwen · MiniMax · Mistral · Grok (xAI)** - plus open-weight models via **Together** and **Fireworks**, and fully local models via **Ollama**.

A curated model list marks what we've verified for tool-calling work. Adding any model string works at your own risk.

## Privacy

MeowWorker is local-first. Everything lives on your machine: the agent loop, your conversations, connector tokens, and model keys - all in the app's local secret store. The optional upstream OpenWorker Cloud service brokers OAuth handshakes for connectors. You can always use the app without signing in by using manually created credentials or API keys.

## Run from source

Prerequisites: Python 3.10+, Node 20+, and (for the desktop shell) the Rust toolchain via [rustup](https://rustup.rs/).

```shell
git clone https://github.com/dennykim123/meowworker
cd meowworker

# 1. One-time bootstrap - creates the Python venv at .venv
#    (on Windows, run from Git Bash or WSL)
bash packaging/setup_dev_env.sh

# 2. Start the local agent server
.venv/bin/openworker-server --cwd ~/some/project --port 8765
#    (Windows: .venv\Scripts\openworker-server.exe)

# 3. In a second terminal, start the UI
cd surfaces/gui
npm install
npm run dev        # browser UI on the Vite dev port
```

To run the full desktop app instead of the browser UI, replace step 3 with `npm run tauri dev` (from `surfaces/gui/`) - the Tauri shell launches the window and supervises the server itself.

Tests: `.venv/bin/pytest` (server), `npm test` and `npm run e2e` in `surfaces/gui` (GUI unit + hermetic end-to-end). Desktop bundles are built with `packaging/build_dmg.sh` / `packaging/build_windows.ps1`.

## Repository layout

| Directory | What's in it |
|---|---|
| `coworker/` | Python backend - agent engine, model providers, connectors, MCP client, memory, automations |
| `surfaces/gui/` | Desktop app - React UI + Tauri shell that supervises the server |
| `stt/` | Speech-to-text sidecar (Rust) for voice input |
| `packaging/` | Installer builds (macOS DMG, Windows), auto-update manifest, dev bootstrap |
| `docs/` | Design specs and decision logs |
| `tests/` | Backend test suite |

## Built on aisuite

The upstream OpenWorker engine is built on [**aisuite**](https://github.com/andrewyng/aisuite), a lightweight Python library providing a unified chat-completions API across LLM providers and an agents layer with tools, toolkits, and MCP support. MeowWorker retains that architecture.

OpenWorker was originally developed inside the aisuite repository before moving to its own home here; thanks to the aisuite contributors whose work it builds on.

## Contributing

Contributions and bug reports for MeowWorker are welcome - open an [issue](https://github.com/dennykim123/meowworker/issues) or a pull request. For the original project, use the [upstream repository](https://github.com/andrewyng/openworker).
For any PR, please attach screenshots of what was broken and how it is fixed now.
Please note that we are actively developing based off a internal list and goal, so we may not approve PRs that add features that are already under-development or deviates from our vision.

## License

MIT - see [LICENSE](LICENSE).
