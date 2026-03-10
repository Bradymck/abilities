import json
import requests
from src.agent.capability import MatchingCapability
from src.main import AgentWorker
from src.agent.capability_worker import CapabilityWorker

# Vault API — served by canvas-bridge.js, exposed via cloudflare tunnel
VAULT_CONFIG_FILE = "ari_vault_config.json"
DEFAULT_VAULT_URL = "https://glow-rebel-terms-sara.trycloudflare.com"
DEFAULT_VAULT_KEY = "57e914d0d00609be8ff10411291dc2833c4cdb37a44a526adb28443ec0406682"

EXIT_WORDS = [
    "done", "exit", "stop", "quit", "bye", "goodbye",
    "nothing else", "all good", "nope", "no thanks",
    "i'm good", "that's all", "that's it", "never mind",
]
CANCEL_WORDS = ["never mind", "cancel", "forget it", "skip"]


class ObsidianNotes(MatchingCapability):
    worker: AgentWorker = None
    capability_worker: CapabilityWorker = None
    history: list = []
    vault_url: str = ""
    vault_key: str = ""

    def call(self, worker: AgentWorker):
        self.worker = worker
        self.capability_worker = CapabilityWorker(self.worker)
        self.history = []
        self.worker.session_tasks.create(self.run())

    def log(self, msg):
        self.worker.editor_logging_handler.info(f"[obsidian] {msg}")

    def log_err(self, msg):
        self.worker.editor_logging_handler.error(f"[obsidian] {msg}")

    # ── Vault config ──────────────────────────────────────────────

    async def load_vault_config(self) -> bool:
        """Load vault API URL and key. Try file storage first, fall back to defaults."""
        try:
            if await self.capability_worker.check_if_file_exists(VAULT_CONFIG_FILE, False):
                raw = await self.capability_worker.read_file(VAULT_CONFIG_FILE, False)
                config = json.loads(raw)
                self.vault_url = config.get("url", "").rstrip("/")
                self.vault_key = config.get("key", "")
                if self.vault_url and self.vault_key:
                    self.log(f"Vault API loaded from storage: {self.vault_url[:40]}...")
                    return True
        except Exception as e:
            self.log(f"File storage read failed, using defaults: {e}")
        self.vault_url = DEFAULT_VAULT_URL
        self.vault_key = DEFAULT_VAULT_KEY
        self.log(f"Using default vault config: {self.vault_url[:40]}...")
        return True

    # ── Vault API calls ──────────────────────────────────────────

    def vault_get(self, endpoint, params=None):
        """Make authenticated GET request to vault API."""
        url = f"{self.vault_url}{endpoint}"
        p = params or {}
        p["key"] = self.vault_key
        try:
            resp = requests.get(url, params=p, timeout=10)
            if resp.status_code == 200:
                return resp.json()
            self.log_err(f"Vault API {resp.status_code}: {resp.text[:100]}")
            return None
        except Exception as e:
            self.log_err(f"Vault API error: {e}")
            return None

    def vault_post(self, endpoint, data):
        """Make authenticated POST request to vault API."""
        url = f"{self.vault_url}{endpoint}"
        try:
            resp = requests.post(
                url, json=data, params={"key": self.vault_key}, timeout=10
            )
            if resp.status_code == 200:
                return resp.json()
            self.log_err(f"Vault POST {resp.status_code}: {resp.text[:100]}")
            return None
        except Exception as e:
            self.log_err(f"Vault POST error: {e}")
            return None

    def search_notes(self, query):
        """Search vault notes by content and title."""
        data = self.vault_get("/vault/search", {"q": query})
        return data.get("results", []) if data else []

    def read_note(self, note_path):
        """Read a specific note's content."""
        data = self.vault_get("/vault/read", {"path": note_path})
        return data.get("content", "") if data else ""

    def list_folders(self):
        """List top-level vault folders."""
        data = self.vault_get("/vault/list")
        return data.get("folders", []) if data else []

    def list_notes(self, folder):
        """List notes in a folder."""
        data = self.vault_get("/vault/list", {"folder": folder})
        return data.get("notes", []) if data else []

    def get_recent(self, count=5):
        """Get recently modified notes."""
        data = self.vault_get("/vault/recent", {"count": str(count)})
        return data.get("results", []) if data else []

    def create_note(self, title, content, folder="inbox"):
        """Create a new note in the vault."""
        result = self.vault_post("/vault/create", {
            "title": title, "content": content, "folder": folder
        })
        return result is not None

    # ── LLM helpers ──────────────────────────────────────────────

    def classify_intent(self, user_input):
        """Classify what the user wants to do with their notes."""
        prompt = (
            "You are an intent classifier for a voice note app. "
            "Classify the input into ONE intent. Return ONLY valid JSON.\n\n"
            "Intents: search, read, create, list, recent, chat\n"
            "Extract: query, title, folder, content (if applicable)\n"
            'Return: {"intent":"...","query":"...","title":"...","folder":"...","content":"..."}\n\n'
            f"User: {user_input}"
        )
        raw = self.capability_worker.text_to_text_response(prompt)
        clean = raw.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            return {"intent": "chat", "query": user_input}

    def summarize(self, content, name):
        """Create a voice-friendly summary of note content."""
        prompt = (
            "Summarize this note for voice output. 2-3 sentences max. "
            "Skip YAML frontmatter and formatting. Focus on key points.\n\n"
            f"Note: {name}\nContent:\n{content[:2000]}"
        )
        return self.capability_worker.text_to_text_response(prompt)

    # ── Intent handlers ──────────────────────────────────────────

    async def handle_search(self, data):
        query = data.get("query", "").strip()
        if not query:
            query = await self.capability_worker.run_io_loop(
                "What would you like to search for?"
            )
            if not query or any(w in query.lower() for w in CANCEL_WORDS):
                return "No problem."

        await self.capability_worker.speak("Searching your vault.")
        self.log(f"Search: {query}")
        results = self.search_notes(query)

        if not results:
            return f"No notes found matching {query}."

        if len(results) == 1:
            content = self.read_note(results[0]["path"])
            if content:
                summary = self.summarize(content, results[0]["path"])
                return f"Found one note: {results[0]['path'].split('/')[-1]}. {summary}"
            return f"Found {results[0]['path'].split('/')[-1]} but couldn't read it."

        names = [r["path"].split("/")[-1] for r in results[:4]]
        listing = ", ".join(names)
        extra = f" and {len(results) - 4} more" if len(results) > 4 else ""
        return f"Found {len(results)} notes. Top results: {listing}{extra}. Want me to read one?"

    async def handle_read(self, data):
        title = data.get("title", "").strip() or data.get("query", "").strip()
        if not title:
            title = await self.capability_worker.run_io_loop(
                "Which note should I read?"
            )
            if not title or any(w in title.lower() for w in CANCEL_WORDS):
                return "No problem."

        await self.capability_worker.speak("Pulling that up.")
        results = self.search_notes(title)
        if not results:
            return f"Couldn't find a note matching {title}."

        content = self.read_note(results[0]["path"])
        if not content:
            return f"Found it but couldn't read the contents."

        name = results[0]["path"].split("/")[-1]
        summary = self.summarize(content, name)
        return f"Here's {name}: {summary}"

    async def handle_create(self, data):
        title = data.get("title", "").strip()
        content = data.get("content", "").strip()
        folder = data.get("folder", "").strip() or "inbox"

        if not title:
            title = await self.capability_worker.run_io_loop(
                "What should I call this note?"
            )
            if not title or any(w in title.lower() for w in CANCEL_WORDS):
                return "Cancelled."
            clean = self.capability_worker.text_to_text_response(
                f"Extract a clean note title from this. Return ONLY the title: {title}"
            ).strip()
            if clean:
                title = clean

        if not content:
            content = await self.capability_worker.run_io_loop(
                f"Got it, '{title}'. What should it say?"
            )
            if not content or any(w in content.lower() for w in CANCEL_WORDS):
                return "Cancelled."

        confirmed = await self.capability_worker.run_confirmation_loop(
            f"Create '{title}' in {folder}?"
        )
        if not confirmed:
            return "Cancelled."

        await self.capability_worker.speak("Creating that note.")
        success = self.create_note(title, content, folder)
        return f"Done, '{title}' saved in {folder}." if success else "Something went wrong creating the note."

    async def handle_list(self, data):
        folder = data.get("folder", "").strip()
        if folder:
            notes = self.list_notes(folder)
            if notes:
                listing = ", ".join(notes[:8])
                return f"In {folder}: {listing}."
            return f"No notes found in {folder}."

        folders = self.list_folders()
        if folders:
            listing = ", ".join(
                f"{f['name']} with {f['noteCount']} notes" for f in folders if f["noteCount"] > 0
            )
            return f"Your vault has: {listing}. Want to look inside any folder?"
        return "Your vault appears empty."

    async def handle_recent(self, data):
        await self.capability_worker.speak("Checking recent notes.")
        notes = self.get_recent(5)
        if not notes:
            return "No recent notes found."
        listing = ", ".join(
            f"{n['path'].split('/')[-1]} ({n['modified']})" for n in notes
        )
        return f"Recently updated: {listing}. Want me to read one?"

    # ── Main loop ────────────────────────────────────────────────

    async def run(self):
        try:
            # Load vault API config
            if not await self.load_vault_config():
                await self.capability_worker.speak(
                    "I can't connect to your vault right now. "
                    "The vault bridge might be offline. Try again later."
                )
                self.capability_worker.resume_normal_flow()
                return

            # Get trigger context
            trigger_context = ""
            try:
                msgs = self.worker.agent_memory.full_message_history
                if msgs:
                    for msg in reversed(msgs[-5:]):
                        if hasattr(msg, "content"):
                            trigger_context = str(msg.content)
                            break
                        elif isinstance(msg, dict) and msg.get("content"):
                            trigger_context = msg["content"]
                            break
            except Exception:
                pass

            if trigger_context:
                self.log(f"Trigger: {trigger_context[:100]}")
                intent_data = self.classify_intent(trigger_context)
            else:
                intent_data = {"intent": "chat"}

            intent = intent_data.get("intent", "chat")
            self.log(f"Intent: {intent}")

            # Route to handler
            handlers = {
                "search": self.handle_search,
                "read": self.handle_read,
                "create": self.handle_create,
                "list": self.handle_list,
                "recent": self.handle_recent,
            }

            if intent in handlers:
                response = await handlers[intent](intent_data)
            else:
                response = (
                    "I can search your notes, read one, create a new note, "
                    "or show recent changes. What would you like?"
                )

            if response:
                await self.capability_worker.speak(response)

            # Follow-up loop
            idle = 0
            while True:
                user_input = await self.capability_worker.user_response()
                if not user_input or not user_input.strip():
                    idle += 1
                    if idle >= 2:
                        await self.capability_worker.speak(
                            "I'll hand you back. Say 'my notes' anytime."
                        )
                        break
                    continue

                idle = 0
                if any(w in user_input.lower() for w in EXIT_WORDS):
                    break

                follow = self.classify_intent(user_input)
                fi = follow.get("intent", "chat")
                self.log(f"Follow-up: {fi}")

                if fi in handlers:
                    resp = await handlers[fi](follow)
                else:
                    resp = "I can search, read, or create notes. Say 'done' to go back."
                if resp:
                    await self.capability_worker.speak(resp)

        except Exception as e:
            self.log_err(f"Error: {e}")
            await self.capability_worker.speak(
                "Hit an error with your notes. Handing you back."
            )

        self.capability_worker.resume_normal_flow()
