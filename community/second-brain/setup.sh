#!/bin/bash
# Second Brain — Quick Setup
# Creates PARA folders, initializes 12 Problems, imports n8n workflows

set -euo pipefail

VAULT_PATH="${OBSIDIAN_VAULT:-$HOME/Documents/Main (ARI)}"
N8N_WORKFLOWS_DIR="${N8N_WORKFLOWS:-$HOME/.openclaw/n8n/workflows}"

echo "[setup] Setting up Second Brain in: $VAULT_PATH"

# 1. Create PARA folders
for folder in Projects Areas Resources Archive inbox; do
    mkdir -p "$VAULT_PATH/$folder"
    echo "  Created $folder/"
done

# Reviews folder for weekly reviews
mkdir -p "$VAULT_PATH/Areas/reviews"
echo "  Created Areas/reviews/"

# 2. Initialize 12 Favorite Problems file
PROBLEMS_FILE="$VAULT_PATH/Areas/twelve-problems.md"
if [ ! -f "$PROBLEMS_FILE" ]; then
    cat > "$PROBLEMS_FILE" << 'PROBLEMS'
---
updated: $(date +%Y-%m-%d)
---

# My 12 Favorite Problems

1.
2.
3.
PROBLEMS
    echo "  Created Areas/twelve-problems.md (fill in your problems!)"
else
    echo "  twelve-problems.md already exists, skipping"
fi

# 3. Check vault API key
VAULT_KEY=$(security find-generic-password -a "openclaw" -s "vault-api-key" -w 2>/dev/null || echo "")
if [ -z "$VAULT_KEY" ]; then
    VAULT_KEY=$(openssl rand -hex 32)
    security add-generic-password -a "openclaw" -s "vault-api-key" -w "$VAULT_KEY" -U
    echo "  Generated and stored vault API key in Keychain"
else
    echo "  Vault API key already in Keychain"
fi

# 4. Import n8n workflows (if n8n is running)
if docker ps 2>/dev/null | grep -q ari-n8n; then
    for wf in basb-inbox-processor basb-distill basb-weekly-review; do
        WF_FILE="$N8N_WORKFLOWS_DIR/$wf.json"
        if [ -f "$WF_FILE" ]; then
            docker exec -i ari-n8n n8n import:workflow --input=/dev/stdin < "$WF_FILE" 2>/dev/null
            echo "  Imported n8n workflow: $wf"
        fi
    done
else
    echo "  n8n not running — import workflows manually later"
fi

# 5. Check dependencies
echo ""
echo "[setup] Checking dependencies..."
command -v cloudflared >/dev/null && echo "  cloudflared: OK" || echo "  cloudflared: MISSING (brew install cloudflared)"
command -v ollama >/dev/null && echo "  ollama: OK" || echo "  ollama: MISSING (brew install ollama)"
command -v node >/dev/null && echo "  node: OK ($(node -v))" || echo "  node: MISSING"

echo ""
echo "[setup] Done! Next steps:"
echo "  1. Fill in your 12 Favorite Problems in: $PROBLEMS_FILE"
echo "  2. Start canvas-bridge: cd ~/.openclaw/canvas && node canvas-bridge.js"
echo "  3. Start tunnel: cloudflared tunnel --url http://localhost:3779"
echo "  4. Upload second-brain.zip to OpenHome dashboard"
echo "  5. Talk to your agent: 'Hey, capture this thought...'"
