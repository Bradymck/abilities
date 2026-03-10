# ARI Obsidian Notes

Voice-powered access to your Obsidian vault. Search, read, create, and manage notes entirely through conversation.

## Features
- **Search** notes by content or title
- **Read** any note aloud with LLM-powered voice summarization
- **Create** new notes via voice dictation
- **List** vault folders and contents
- **Recent** — see what was recently updated
- **Sync** vault context on demand

## Usage
Say any of these phrases:
- "Check my notes" / "My notes"
- "Search notes about [topic]"
- "Read my note about [topic]"
- "Create a note called [title]"
- "Take a note"
- "What did I write about [topic]?"
- "What's been updated recently?"
- "Sync Obsidian"

## How It Works
1. Voice input is classified by the LLM into an intent (search/read/create/list/recent/sync)
2. `obsidian-cli` and shell commands operate on the vault
3. Note contents are summarized by the LLM for natural voice output
4. Follow-up loop lets you chain operations without re-triggering

## Requirements
- Local Obsidian vault at `~/Documents/Main (ARI)/`
- `obsidian-cli` installed (`brew install yakitrak/yakitrak/obsidian-cli`)
- Default vault set (`obsidian-cli set-default "Main (ARI)"`)

## Author
@SentientARI

## License
MIT
