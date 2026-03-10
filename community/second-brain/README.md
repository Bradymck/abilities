# Second Brain - OpenHome Voice Ability

A voice-first knowledge management system based on Tiago Forte's Building a Second Brain (BASB) methodology. Capture, organize, distill, and express your knowledge — all by voice.

## What It Does

| Command | Example | Action |
|---------|---------|--------|
| **Capture** | "Save this thought about..." | Creates note in inbox |
| **Search** | "What do I know about..." | Smart search across vault |
| **Read** | "Read my note on..." | Reads note aloud |
| **Organize** | "Organize my inbox" | Auto-classifies notes into PARA folders |
| **Distill** | "Summarize my note on..." | Progressive summarization (bold → highlight → summary) |
| **Express** | "Draft something about..." | Combines notes into new output |
| **Review** | "Weekly review" | Status overview + themes |
| **Problems** | "My favorite problems" | 12 Favorite Problems list |
| **Status** | "How's my second brain?" | Vault stats |

## Architecture

```
OpenHome (voice) ──→ Cloudflare Tunnel ──→ Canvas Bridge (localhost:3779)
                                               │
                                          Obsidian Vault
                                               │
                                          n8n Workflows
                                          (auto-organize, distill, review)
```

## Requirements

- [Obsidian](https://obsidian.md) with a vault using PARA folders
- [Node.js](https://nodejs.org) 18+
- [n8n](https://n8n.io) (Docker recommended)
- [Cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)
- [Ollama](https://ollama.ai) with `deepseek-r1:1.5b` (for n8n workflows)
- [OpenHome](https://openhome.com) account

## Quick Setup

```bash
# Run the setup script
bash setup.sh
```

Or manually:

1. **Create PARA folders** in your Obsidian vault:
   ```
   mkdir -p Projects Areas Resources Archive inbox
   ```

2. **Start the vault API** (canvas-bridge.js on port 3779)

3. **Start a Cloudflare tunnel**:
   ```bash
   cloudflared tunnel --url http://localhost:3779
   ```

4. **Import n8n workflows** from the `workflows/` directory

5. **Upload the ability** to OpenHome dashboard

6. **Update `main.py`** with your tunnel URL and vault API key

## BASB Methodology

This ability implements five core BASB concepts:

- **PARA**: Projects, Areas, Resources, Archive — your organizational system
- **Progressive Summarization**: 5 layers from raw notes to executive summaries
- **CODE**: Capture → Organize → Distill → Express
- **12 Favorite Problems**: Big questions that guide what you capture
- **Weekly Review**: Regular reflection connecting notes to problems
