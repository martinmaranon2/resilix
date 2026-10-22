# Entire Graph & Entire Brain Setup Guide

This guide explains how CrisisOS / AlpineGuard teammates can set up and use **Entire Graph** and **Entire Brain** in their local environments, connect Brain MCP to Antigravity, merge the shared configuration into feature branches, and share session checkpoints across the team.

---

## 1. Local Installation

If you already have the `entire` CLI installed, verify it with `entire --version`. Otherwise:

### Step 1.1: Install Entire CLI
```bash
# Via Homebrew (macOS / Linux)
brew install entire-io/tap/entire

# Or via official install script
curl -fsSL https://raw.githubusercontent.com/entire-io/cli/main/install.sh | sh
```

### Step 1.2: Install Graph and Brain Plugins
```bash
entire plugin install brain
entire plugin install graph
```

Verify installed plugins:
```bash
entire plugin list
```
The plugins will be located in your local plugin directory (e.g., `~/.local/share/entire/plugins/bin/entire-brain` and `~/.local/share/entire/plugins/bin/entire-graph`).

---

## 2. Connect Brain MCP to Antigravity

> **Important**: Never commit or share hardcoded machine absolute paths. Each teammate's installation path differs depending on OS and Homebrew architecture.

### Step 2.1: Generate Your Local MCP Configuration
Run the following command in your terminal to print the exact MCP configuration for your machine:
```bash
entire-brain mcp --print-config
```
*(If `entire-brain` is not directly on your PATH, use `~/.local/share/entire/plugins/bin/entire-brain mcp --print-config`)*

### Step 2.2: Add to Antigravity
The command outputs a configuration JSON snippet similar to:
```json
{
  "mcpServers": {
    "entire-brain": {
      "command": "/path/to/your/entire-brain",
      "args": ["mcp"]
    }
  }
}
```

Add the `entire-brain` entry to your Antigravity MCP configuration:
- In Antigravity Settings: Open **Settings -> MCP Servers -> Add Server**
- Or in your Antigravity configuration file (`~/.gemini/antigravity-cli/mcp_config.json` or project MCP config).

Restart or reload your agent session. The agent will now have access to Brain tools (`brain_brief`, `brain_query`, `brain_context`, `brain_impact`, `brain_search_graph`, `brain_code`, etc.).

---

## 3. Verify Graph and Brain

Run the verification suite from the repository root:

```bash
# 1. Check Entire CLI status and hooked agents (Antigravity & Codex)
entire status

# 2. Check Brain index status
entire brain status

# If the repository is not indexed yet, index it:
entire brain index

# 3. Test Brain task orientation
entire brain brief "CrisisOS data architecture" --json

# 4. Verify Graph AST indexing and code symbol search
entire graph search "SwissDataService"
entire graph doctor
```

---

## 4. Merging Configuration into Your Feature Branch

Once this configuration PR is merged into `main`, update your existing branch:

```bash
# 1. Fetch latest changes from remotes
git fetch origin
git fetch github

# 2. Switch to your active feature branch
git checkout feat/<your-branch-name>

# 3. Merge main into your branch
git merge origin/main

# 4. Verify that configuration files are present
ls -la .entire/
cat AGENTS.md
```

Your feature branch will now inherit the shared `.entire/agent-guide.md`, `.entire/graph-agent.md`, `.entire/settings.json`, and agent activation rules without affecting any of your ongoing feature code.

---

## 5. Cross-Branch Session & Memory Sharing

Entire automatically captures coding sessions, intent, and architectural checkpoints stored as Git references under `refs/entire/*`.

### Step 5.1: Fetch Teammate Checkpoints
To access sessions and memories created by other teammates across branches:
```bash
git fetch origin "refs/entire/*:refs/entire/*"
```

### Step 5.2: Push Your Checkpoints
When you complete a task or milestone, push your captured checkpoints to the remote:
```bash
git push origin "refs/entire/*:refs/entire/*"
```

### Step 5.3: Inspecting Captured Knowledge
```bash
# List all checkpoints captured across branches
entire checkpoint list

# View the details of a specific checkpoint
entire checkpoint show <checkpoint-id>

# Compare semantic code changes across checkpoints
entire graph checkpoint <checkpoint-id>

# Query shared architectural memories and durable facts
entire brain recall "architecture"
entire brain entities history
```

---

## Shared Repository Files Overview

- **`AGENTS.md`**: Team coding guidelines + Entire agent guide activation hook.
- **`CLAUDE.md`**: Claude Code activation hook.
- **`.entire/agent-guide.md`**: Canonical workflow instructions for Brain (context/memory) and Graph (AST code queries).
- **`.entire/graph-agent.md`**: Fallback pointer to the main agent guide.
- **`.entire/settings.json`**: Repository settings enabling Entire tracking and `git-refs` checkpoints.
- **`.codex/hooks.json`**: Codex agent lifecycle hooks for session recording.
- **`.agents/hooks.json`**: Antigravity agent lifecycle hooks for session recording.
