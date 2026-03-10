import json
import requests
from src.agent.capability import MatchingCapability
from src.main import AgentWorker
from src.agent.capability_worker import CapabilityWorker

# Vault API — served by canvas-bridge.js, exposed via cloudflare tunnel
VAULT_CONFIG_FILE = "second_brain_config.json"
DEFAULT_VAULT_URL = "https://glow-rebel-terms-sara.trycloudflare.com"
DEFAULT_VAULT_KEY = "57e914d0d00609be8ff10411291dc2833c4cdb37a44a526adb28443ec0406682"

EXIT_WORDS = [
    "done", "exit", "stop", "quit", "bye", "goodbye",
    "nothing else", "all good", "nope", "no thanks",
    "i'm good", "that's all", "that's it", "never mind",
]
CANCEL_WORDS = ["never mind", "cancel", "forget it", "skip"]


class SecondBrain(MatchingCapability):
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
        self.worker.editor_logging_handler.info(f"[second-brain] {msg}")

    def log_err(self, msg):
        self.worker.editor_logging_handler.error(f"[second-brain] {msg}")

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
                    self.log(f"Vault loaded from storage: {self.vault_url[:40]}...")
                    return True
        except Exception as e:
            self.log(f"File storage read failed, using defaults: {e}")
        self.vault_url = DEFAULT_VAULT_URL
        self.vault_key = DEFAULT_VAULT_KEY
        self.log(f"Using default vault: {self.vault_url[:40]}...")
        return True

    # ── Vault API calls ──────────────────────────────────────────

    def vault_get(self, endpoint, params=None):
        url = f"{self.vault_url}{endpoint}"
        p = params or {}
        p["key"] = self.vault_key
        try:
            resp = requests.get(url, params=p, timeout=15)
            if resp.status_code == 200:
                return resp.json()
            self.log_err(f"GET {endpoint} -> {resp.status_code}")
            return None
        except Exception as e:
            self.log_err(f"GET {endpoint} error: {e}")
            return None

    def vault_post(self, endpoint, data):
        url = f"{self.vault_url}{endpoint}"
        try:
            resp = requests.post(
                url, json=data, params={"key": self.vault_key}, timeout=15
            )
            if resp.status_code == 200:
                return resp.json()
            self.log_err(f"POST {endpoint} -> {resp.status_code}")
            return None
        except Exception as e:
            self.log_err(f"POST {endpoint} error: {e}")
            return None

    # ── Intent classification ─────────────────────────────────────

    def classify_intent(self, user_input):
        prompt = (
            "You are an intent classifier for a Second Brain voice assistant. "
            "Classify the input into ONE intent. Return ONLY valid JSON.\n\n"
            "Intents:\n"
            "- capture: user wants to save a thought, idea, or note\n"
            "- search: user wants to find notes about a topic\n"
            "- read: user wants to hear a specific note\n"
            "- organize: user wants to sort/file their inbox notes\n"
            "- distill: user wants to summarize or get key takeaways from a note\n"
            "- express: user wants to create something new from existing notes\n"
            "- review: user wants a weekly review or status update\n"
            "- problems: user wants to see or add to their 12 favorite problems\n"
            "- status: user wants vault statistics\n"
            "- chat: general conversation about notes\n\n"
            "Extract relevant fields: query, title, folder, content, problem\n"
            'Return: {"intent":"...","query":"...","title":"...","folder":"...","content":"...","problem":"..."}\n\n'
            f"User: {user_input}"
        )
        raw = self.capability_worker.text_to_text_response(prompt)
        clean = raw.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            return {"intent": "chat", "query": user_input}

    def summarize_for_voice(self, content, name):
        prompt = (
            "Summarize this note for voice output. 2-3 sentences max. "
            "Focus on the most important insights.\n\n"
            f"Note: {name}\nContent:\n{content[:2000]}"
        )
        return self.capability_worker.text_to_text_response(prompt)

    # ── Intent handlers ──────────────────────────────────────────

    async def handle_capture(self, data):
        """CODE: Capture — save a thought to inbox."""
        title = data.get("title", "").strip()
        content = data.get("content", "").strip()

        if not title and not content:
            raw = await self.capability_worker.run_io_loop(
                "What would you like to capture?"
            )
            if not raw or any(w in raw.lower() for w in CANCEL_WORDS):
                return "No problem."
            # Use LLM to extract title and content from speech
            extract = self.capability_worker.text_to_text_response(
                f"Extract a short title (3-6 words) and the full content from this voice input. "
                f'Return JSON: {{"title":"...","content":"..."}}\n\nInput: {raw}'
            )
            try:
                parsed = json.loads(extract.replace("```json", "").replace("```", "").strip())
                title = parsed.get("title", raw[:50])
                content = parsed.get("content", raw)
            except json.JSONDecodeError:
                title = raw[:50]
                content = raw

        if not title:
            title = content[:50] if content else "untitled"
        if not content:
            content = title

        # Add timestamp
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        full_content = f"---\ncreated: {timestamp}\nsource: voice\nsummarization_layer: 0\n---\n\n{content}"

        result = self.vault_post("/vault/create", {
            "title": title, "content": full_content, "folder": "inbox"
        })
        if result:
            return f"Captured '{title}' in your inbox. It'll be organized automatically."
        return "Something went wrong saving that. Try again?"

    async def handle_search(self, data):
        """CODE: Organize — find notes using smart surface retrieval."""
        query = data.get("query", "").strip()
        if not query:
            query = await self.capability_worker.run_io_loop(
                "What would you like to search for?"
            )
            if not query or any(w in query.lower() for w in CANCEL_WORDS):
                return "No problem."

        await self.capability_worker.speak("Searching your second brain.")
        self.log(f"Surface search: {query}")
        results = self.vault_get("/vault/surface", {"q": query, "limit": "5"})

        if not results or not results.get("results"):
            return f"Nothing found about {query} in your vault."

        hits = results["results"]
        if len(hits) == 1:
            r = hits[0]
            summary = r.get("executive_summary") or r.get("preview", "")[:200]
            return f"Found one note: {r['name']}. {summary}"

        names = [r["name"] for r in hits[:4]]
        listing = ", ".join(names)
        extra = f" and {len(hits) - 4} more" if len(hits) > 4 else ""
        top = hits[0]
        top_summary = top.get("executive_summary") or top.get("preview", "")[:150]
        return (
            f"Found {len(hits)} notes about {query}. "
            f"Top result: {top['name']}. {top_summary}. "
            f"Others: {listing}{extra}. Want me to read one?"
        )

    async def handle_read(self, data):
        """Read a specific note aloud."""
        title = data.get("title", "").strip() or data.get("query", "").strip()
        if not title:
            title = await self.capability_worker.run_io_loop(
                "Which note should I read?"
            )
            if not title or any(w in title.lower() for w in CANCEL_WORDS):
                return "No problem."

        await self.capability_worker.speak("Pulling that up.")
        results = self.vault_get("/vault/surface", {"q": title, "limit": "1"})
        if not results or not results.get("results"):
            return f"Couldn't find a note matching {title}."

        note = results["results"][0]
        content_data = self.vault_get("/vault/read", {"path": note["path"]})
        if not content_data or not content_data.get("content"):
            return "Found it but couldn't read the contents."

        summary = self.summarize_for_voice(content_data["content"], note["name"])
        return f"Here's {note['name']}: {summary}"

    async def handle_organize(self, data):
        """CODE: Organize — process inbox notes into PARA folders."""
        await self.capability_worker.speak("Checking your inbox.")
        inbox = self.vault_get("/vault/inbox")
        if not inbox or not inbox.get("notes"):
            return "Your inbox is empty. Nothing to organize."

        notes = inbox["notes"]
        count = len(notes)
        await self.capability_worker.speak(
            f"You have {count} note{'s' if count != 1 else ''} in your inbox. Let me organize them."
        )

        organized = 0
        for note in notes[:5]:  # Max 5 per session
            # Use LLM to classify
            prompt = (
                "Classify this note into a PARA category. Return ONLY valid JSON.\n"
                "Categories: Projects (active goals with deadlines), "
                "Areas (ongoing responsibilities), "
                "Resources (reference material), "
                "Archive (completed/inactive)\n\n"
                f"Title: {note['name']}\nPreview: {note['preview'][:300]}\n\n"
                '{"category":"...","tags":["..."]}'
            )
            raw = self.capability_worker.text_to_text_response(prompt)
            try:
                parsed = json.loads(raw.replace("```json", "").replace("```", "").strip())
                category = parsed.get("category", "Resources")
                tags = parsed.get("tags", [])
            except json.JSONDecodeError:
                category = "Resources"
                tags = []

            if category not in ["Projects", "Areas", "Resources", "Archive"]:
                category = "Resources"

            result = self.vault_post("/vault/organize", {
                "notePath": note["path"],
                "targetFolder": category,
                "tags": tags
            })
            if result:
                organized += 1

        remaining = count - organized
        msg = f"Organized {organized} note{'s' if organized != 1 else ''}."
        if remaining > 0:
            msg += f" {remaining} still in inbox for next time."
        return msg

    async def handle_distill(self, data):
        """CODE: Distill — apply progressive summarization to a note."""
        title = data.get("title", "").strip() or data.get("query", "").strip()
        if not title:
            title = await self.capability_worker.run_io_loop(
                "Which note should I distill?"
            )
            if not title or any(w in title.lower() for w in CANCEL_WORDS):
                return "No problem."

        await self.capability_worker.speak("Analyzing that note.")
        results = self.vault_get("/vault/surface", {"q": title, "limit": "1"})
        if not results or not results.get("results"):
            return f"Couldn't find a note matching {title}."

        note = results["results"][0]
        content_data = self.vault_get("/vault/read", {"path": note["path"]})
        if not content_data or not content_data.get("content"):
            return "Found it but couldn't read the contents."

        content = content_data["content"]
        # Use LLM for progressive summarization
        prompt = (
            "Apply progressive summarization to this note. Return ONLY valid JSON.\n"
            "1. Identify 3-5 bold-worthy key passages (most important sentences)\n"
            "2. Write a 1-2 sentence executive summary capturing the core insight\n\n"
            f"Note: {note['name']}\nContent:\n{content[:3000]}\n\n"
            '{"bold_passages":["..."],"executive_summary":"..."}'
        )
        raw = self.capability_worker.text_to_text_response(prompt)
        try:
            parsed = json.loads(raw.replace("```json", "").replace("```", "").strip())
            bold = parsed.get("bold_passages", [])
            summary = parsed.get("executive_summary", "")
        except json.JSONDecodeError:
            return "Had trouble analyzing that note. Try again?"

        result = self.vault_post("/vault/distill", {
            "notePath": note["path"],
            "bold_passages": bold,
            "executive_summary": summary
        })
        if result:
            layer = result.get("layer", 1)
            return (
                f"Distilled {note['name']} to layer {layer}. "
                f"Summary: {summary}"
            )
        return "Something went wrong distilling that note."

    async def handle_express(self, data):
        """CODE: Express — combine related notes into new output."""
        topic = data.get("query", "").strip()
        if not topic:
            topic = await self.capability_worker.run_io_loop(
                "What topic should I draft about from your notes?"
            )
            if not topic or any(w in topic.lower() for w in CANCEL_WORDS):
                return "No problem."

        await self.capability_worker.speak(f"Gathering your notes about {topic}.")
        results = self.vault_get("/vault/surface", {"q": topic, "limit": "5"})
        if not results or not results.get("results"):
            return f"No notes found about {topic} to draw from."

        # Gather content from top notes
        sources = []
        for r in results["results"][:3]:
            content_data = self.vault_get("/vault/read", {"path": r["path"]})
            if content_data and content_data.get("content"):
                sources.append(f"## {r['name']}\n{content_data['content'][:800]}")

        if not sources:
            return "Found notes but couldn't read them."

        combined = "\n\n".join(sources)
        prompt = (
            f"Using these notes as source material, draft a concise piece about '{topic}'. "
            "Synthesize the key ideas into a coherent 2-3 paragraph draft. "
            "Reference which notes the ideas come from.\n\n"
            f"Source notes:\n{combined}"
        )
        draft = self.capability_worker.text_to_text_response(prompt)

        # Save the draft
        from datetime import datetime
        title = f"Draft - {topic}"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        full_content = (
            f"---\ncreated: {timestamp}\nsource: second-brain-express\n"
            f"topic: {topic}\nsummarization_layer: 3\n---\n\n{draft}"
        )
        self.vault_post("/vault/create", {
            "title": title, "content": full_content, "folder": "Projects"
        })

        # Speak a summary
        voice_summary = self.summarize_for_voice(draft, title)
        return f"I drafted something about {topic} and saved it in Projects. Here's the gist: {voice_summary}"

    async def handle_review(self, data):
        """Weekly review — what's new, what needs attention."""
        await self.capability_worker.speak("Running your weekly review.")

        # Get metadata
        metadata = self.vault_get("/vault/metadata")
        recent = self.vault_get("/vault/recent", {"count": "10"})
        problems = self.vault_get("/vault/problems")
        inbox = self.vault_get("/vault/inbox")

        parts = []
        if metadata:
            total = metadata.get("total_notes", 0)
            summarized = metadata.get("summarized_notes", 0)
            parts.append(f"Your vault has {total} notes, {summarized} distilled.")

        if inbox and inbox.get("notes"):
            parts.append(f"{len(inbox['notes'])} notes waiting in your inbox.")

        if recent and recent.get("results"):
            names = [r["path"].split("/")[-1] for r in recent["results"][:5]]
            parts.append(f"Recent activity: {', '.join(names)}.")

        if problems and problems.get("problems"):
            parts.append(f"You're tracking {len(problems['problems'])} favorite problems.")

        if not parts:
            return "Couldn't pull your review data. The vault might be offline."

        return " ".join(parts)

    async def handle_problems(self, data):
        """List or add to 12 Favorite Problems."""
        problem_text = data.get("problem", "").strip()

        if problem_text:
            # Adding a new problem
            result = self.vault_post("/vault/problems", {"problem": problem_text})
            if result:
                count = result.get("count", 0)
                return f"Added to your favorite problems. You now have {count} of 12."
            return "Couldn't save that problem. Try again?"

        # Listing problems
        problems = self.vault_get("/vault/problems")
        if not problems or not problems.get("problems"):
            return (
                "You don't have any favorite problems yet. "
                "These are the big questions that drive your thinking. "
                "Want to add one?"
            )

        plist = problems["problems"]
        if len(plist) <= 3:
            listing = ". ".join(f"{i+1}, {p}" for i, p in enumerate(plist))
            return f"Your favorite problems: {listing}."

        # Summarize if many
        listing = ". ".join(f"{i+1}, {p[:60]}" for i, p in enumerate(plist[:5]))
        extra = f" Plus {len(plist) - 5} more." if len(plist) > 5 else ""
        return f"Your top problems: {listing}.{extra}"

    async def handle_status(self, data):
        """Vault status overview."""
        metadata = self.vault_get("/vault/metadata")
        if not metadata:
            return "Can't reach your vault right now. Is the bridge running?"

        total = metadata.get("total_notes", 0)
        summarized = metadata.get("summarized_notes", 0)
        folders = metadata.get("folders", {})

        parts = [f"Your second brain has {total} notes."]
        for name, info in folders.items():
            count = info.get("count", 0)
            if count > 0:
                parts.append(f"{name}: {count}")
        if summarized > 0:
            parts.append(f"{summarized} notes have been distilled.")
        else:
            parts.append("No notes distilled yet.")

        return " ".join(parts)

    # ── Main loop ────────────────────────────────────────────────

    async def run(self):
        try:
            if not await self.load_vault_config():
                await self.capability_worker.speak(
                    "Can't connect to your vault right now. Try again later."
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

            handlers = {
                "capture": self.handle_capture,
                "search": self.handle_search,
                "read": self.handle_read,
                "organize": self.handle_organize,
                "distill": self.handle_distill,
                "express": self.handle_express,
                "review": self.handle_review,
                "problems": self.handle_problems,
                "status": self.handle_status,
            }

            if intent in handlers:
                response = await handlers[intent](intent_data)
            else:
                response = (
                    "I'm your second brain assistant. I can capture ideas, "
                    "search your notes, organize your inbox, distill key insights, "
                    "or create new drafts from your knowledge. What would you like?"
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
                            "I'll hand you back. Say 'second brain' anytime."
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
                    resp = (
                        "I can capture, search, organize, distill, or express. "
                        "Say 'done' to go back."
                    )
                if resp:
                    await self.capability_worker.speak(resp)

        except Exception as e:
            self.log_err(f"Error: {e}")
            await self.capability_worker.speak(
                "Hit an error with your second brain. Handing you back."
            )

        self.capability_worker.resume_normal_flow()
