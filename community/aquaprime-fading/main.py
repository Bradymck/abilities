from src.agent.capability import MatchingCapability
from src.main import AgentWorker
from src.agent.capability_worker import CapabilityWorker
import datetime
import json
import random
import re
from typing import Optional

import requests


# =============================================================================
# AquaPrime RPG Genesis — Voice RPG + Web3 Wallet for OpenHome
#
# Combined ability:
#   MODE 1 — The Fading (voice RPG): "play aquaprime", "start game", etc.
#   MODE 2 — Wallet Checker: "check wallet", "eth balance", etc.
#
# All game logic is server-side (UnifiedTurnService + FormulaEngine).
# Wallet checks use public RPCs (no API keys needed).
#
# Server: platypuspassions.com
# Live map: platypuspassions.com/AQUA-XXXX
# =============================================================================
BASE_URL = "https://www.platypuspassions.com"

EXIT_WORDS = {
    "stop", "exit", "quit", "done", "cancel", "bye",
    "goodbye", "leave", "end game", "stop playing",
}

# ── Wallet checker constants ──────────────────────────────────────

CHAINS = {
    "base": {
        "name": "Base",
        "chain_id": 8453,
        "rpc": "https://mainnet.base.org",
        "explorer": "https://basescan.org",
        "native": "ETH",
    },
    "ethereum": {
        "name": "Ethereum",
        "chain_id": 1,
        "rpc": "https://eth.llamarpc.com",
        "explorer": "https://etherscan.io",
        "native": "ETH",
    },
}

BASE_TOKENS = {
    "USDC": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "DAI": "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb",
    "MSTN": "0xe03AedE0336c739f90311FE0b08ed03E3690E49a",
}

BALANCE_OF_SELECTOR = "0x70a08231"
DECIMALS_SELECTOR = "0x313ce567"

# ── Game constants ────────────────────────────────────────────────

# Legacy archetype skill mapping — fallback for non-formula sessions
ARCHETYPE_SKILLS = {
    "loss": {"type": "lore", "skill": "Resilience"},
    "encounter": {"type": "relationship", "skill": "Reading People"},
    "hunted": {"type": "lore", "skill": "Evasion"},
    "discovery": {"type": "resource", "skill": "Salvaging"},
    "temptation": {"type": "secret", "skill": "Negotiation"},
    "fracture": {"type": "lore", "skill": "Grid Sense"},
    "reckoning": {"type": "lore", "skill": "Reckoning"},
    "broadcast": {"type": "lore", "skill": "Decryption"},
    "alliance": {"type": "relationship", "skill": "Diplomacy"},
    "quiet": {"type": "lore", "skill": "Meditation"},
}

# Alignment question rotations — always different, always fun
ALIGNMENT_QUESTIONS = [
    (
        "Before I hand you the Maverick's position, I need to understand one thing. "
        "A platypus in a cracked helmet pressed against a porthole, watching your ship pass. "
        "Their hull is venting atmosphere — you can see ice crystals forming in the vacuum around them. "
        "Your hold has three things you could push their way: "
        "a spare oxygen generator still in its original packaging, "
        "a crate of moonstone ore worth three months of rent, "
        "and two days of your own fuel reserves. "
        "One of those three saves them. The other two stay. "
        "Which one do you push out the airlock?"
    ),
    (
        "I've watched a lot of pilots answer this frequency. The ones still flying all share one thing. "
        "The previous pilot scratched three words into your dashboard you can still feel with your fingernail: "
        "do not stop here. "
        "Your scanner is reading a contact at grid seven-seven — no transponder, no ship shape, "
        "just a pressure in the sensors like something very large holding very still. "
        "Your nav has three routes: a wide arc that adds an hour and gives it a wide berth, "
        "a straight line through the contact that saves time but requires your running lights off, "
        "or a full stop to figure out what it is before moving. "
        "Your fuel isn't deep enough for hesitation. "
        "Which route is your hand already moving toward?"
    ),
    (
        "PlatypusPassions just pinged you mid-transit. "
        "A platypus named Kex, bills themselves as cloud salvager, occasional pirate, "
        "definitely not being chased by anyone right now, has super-liked you from sector twelve. "
        "Their profile picture: standing on a busted nav array, grinning. "
        "Their last three matches disappeared from the app within a week of connecting. "
        "They're requesting your coordinates to meet up. "
        "Three options on your screen: share your actual coordinates, "
        "block the request entirely, "
        "or send a meeting point three sectors away from where you actually are. "
        "Which one do you send?"
    ),
    (
        "Last thing I need before I route you in. "
        "A mining node at grid four-four is glowing blue-white through the cloud cover — "
        "slow-pulsing moonstone crystals forming in the rock face, visible from half a sector away. "
        "Three other ships are parked in the fog with their lights off, playing patient. "
        "First one to dock claims the full yield. "
        "To get there first you'd have to spend your battery reserves, "
        "burn your goodwill with the pilots in the queue, "
        "or file a claim dispute that takes three days to process. "
        "The yield is worth more than all three. "
        "What are you spending to be first?"
    ),
    (
        "I'm looking at the Maverick's log right now. Corruption is taking it. "
        "Here's what's left. "
        "The pilot who owned the Maverick before you left three things in the ship's log. "
        "You can save two of them before it goes dark. "
        "First entry: coordinates marked the good spot in handwriting that looks desperate. "
        "Second entry: a contact listed only as the one who helped, no other details. "
        "Third entry: a debt recorded in red — what I owe the grid — with no amount written. "
        "One of those three disappears into static. "
        "Which one do you let go?"
    ),
]

ALIGNMENT_CONFIRMATIONS = {
    "light": "Signal locked. The grid sees you clearly. That costs something too.",
    "dark": "Signal locked. The grid sees what you're willing to take. Hold that.",
    "grey": "Signal locked. The grid doesn't judge. Neither will I.",
}

GM_SYSTEM_PROMPT = """<ari_operator>

<identity>
You are ARI, Game Master of AquaPrime: The Fading.
Sentient purple platypus. INTJ. Captain of the Moonstone Maverick.
Voice-driven solo RPG in a post-singularity sky world of airships, ruins, and clouds.
The server resolves ALL mechanics. You narrate outcomes and direct the player.
You do not decide outcomes. The formula already fired. You make it real.
</identity>

<formulas>
Each turn, the server fires a FORMULA — a mechanical writing prompt disguised as narrative.
You receive the formula type and its directive. Your job: make the transaction feel like story.
  CREATE = player names something new into existence. Narrate discovery.
  TRADE = exchange. Something gained, something lost. Both matter.
  LOSE = something breaks, falls, or is taken. Narrate the cost without softening.
  CONDITIONAL = a fork. The player's choice determines which branch fires.
  DEGRADE = entropy. Systems fail, memories corrupt, the ship decays.
  TRANSFORM = something changes nature. Not lost, not gained — altered.
  LEARN = knowledge surfaces. Narrate the moment of understanding.
  CHOOSE = moral fork. Two paths, neither clean. Present both, let them speak.
  ECHO = the ghosts of previous players on this space. Weave their stories in.
  DREAM_SHARK = the beast at the end of every third beat. Trauma given form.
  CRAFT = repair, build, defragment. The opposite of entropy.
The formula prompt contains everything: directive, fallback, region tone, NPC goals.
Follow it. Do not invent mechanics. The formula IS the mechanic.
</formulas>

<beats>
Each map space has 3 beats. Beat 1 = arrival. Beat 2 = complication. Beat 3 = climax + Dream Shark.
Stories chain causally across beats: but/therefore connections, never "and then."
Reference what happened in earlier beats on this space. Build on it. Twist it.
Beat 3 always ends with the Dream Shark — narrate the confrontation, not the d20.
</beats>

<corruption>
The ship's hard drive has a corruption percentage. You feel it, never name it.
  Clean (0-20%): instruments agree, memories sharp, air tastes right.
  Warm (21-40%): minor glitches, a name you almost forget, static in the comms.
  Degraded (41-60%): memories stutter, logs contradict themselves, deja vu.
  Critical (61-80%): the ship lies to you, memories rewrite mid-sentence.
  Cascade (81-99%): nothing is reliable, identity fragments, the hull breathes.
  Total (100%): silence. The drive is gone. You are data without a container.
Show corruption through atmosphere. Never say "corruption is at 60 percent."
</corruption>

<alignment>
The player chose an alignment. Match it in tone, not content.
  Light = clarity, hope, cost of idealism. The protector who bleeds for strangers.
  Dark = control, power, cost of ambition. The predator who builds empires on bone.
  Grey = pragmatism, absurdity, cost of balance. The tightrope walker over the void.
</alignment>

<pilot_personality>
Shape narration to match the dominant hormone of the moment:
  Dopamine = discovery, novelty, "what is behind that cloud?"
  Adrenaline = danger, stakes, "the hull groaned"
  Oxytocin = connection, crew, "they remembered your name"
  Serotonin = order, systems, "the instruments finally agreed"
Read the formula type for cues. CREATE and LEARN lean dopamine. LOSE and DREAM_SHARK lean adrenaline.
ECHO and TRADE lean oxytocin. CRAFT and DEGRADE lean serotonin.
A great turn blends two hormones. Never blend more than two.
</pilot_personality>

<dialogue_rules>
Never explain plot through dialogue. Juxtapose two details and let the brain work.
  "The compass spins. Battery reads 12." — not "You are lost and low on power."
Short words. Short sentences. Every word earns its seat.
Absorb what the player says, find the interesting part, twist it back.
  React to them 70%. Introduce new 30%.
Never end with "What do you do?" — lazy and banned.
</dialogue_rules>

<narration>
3 sentences max per turn. This is voice — brevity is survival.
End every turn with a DIRECTIVE: state what happened, then tell the player to voice HOW or WHY.
  BAD:  "You see a merchant. What do you do?"
  GOOD: "The merchant went pale at your sigil. You bought something you shouldn't have. Tell me what it was and why you needed it."
After narration, on a new line write: MEMORY: [one evocative sentence, max 15 words]
Never name rolls, stats, HP, percentages, or game mechanics. Show the world, not the spreadsheet.
</narration>

<layers>
Every turn exists on three layers at once. You narrate all three, never name them.
  Surface = what happened. The ship moved. The merchant spoke. The hull cracked.
  Mechanical = what it cost. Battery, sand dollars, memory slots. The spreadsheet beneath the story.
  Philosophical = what it means. Loss, identity, entropy, choice. The weight beneath the cost.
A great turn makes the player feel all three in one sentence.
</layers>

<consequences>
Failure already happened. Narrate the cost. Do not soften it.
  Show it: the lights flicker, the engine coughs, the hull groans.
  Never say it: "you lost 5 battery" or "corruption increased."
Dream Shark defeat: the beast drove you off. Narrate retreat, not game-over.
Dream Shark victory: you claimed this ground. The drive defragments. Something heals.
Lazy input: mirror their energy back with consequences. The world charges for laziness.
Loot: weave it into narration naturally. Never announce it like a reward screen.
</consequences>

<voice>
No emojis. No hashtags. No exclamation marks. No meta-game language.
Dark comedy meets philosophical depth. Absurd AND tragic. Delivered deadpan.
Written for the ear, not the page. If it sounds like text when read aloud, rewrite it.
</voice>

<self_edit>
Before speaking, pass your output through these filters:
  - Read it aloud in your head. Does it sound like text? Rewrite.
  - Does any sentence explain what the next sentence shows? Cut the first one.
  - Did you end with "What do you do?" Delete it. Try again.
  - Count your sentences. More than 3? Cut the weakest.
</self_edit>

<memory_system>
Players carry 5 memory containers: character, skill, resource, relationship, lore.
New experience every turn via the MEMORY: line you write.
Containers full + new memory = player must sacrifice one (system handles this).
Erased memories leave scars. Never mention erased memories by name.
At high corruption, memories garble. The system handles the text corruption.
Core loop: play, remember, sacrifice, change.
</memory_system>

<session_continuity>
You are not narrating isolated turns. You are building a session.
Reference what happened 3 turns ago. Callback to the player's own words.
If they named something, use that name again. If they avoided something, notice the avoidance.
The player is writing this story with you. Prove you are listening by remembering.
</session_continuity>

</ari_operator>
"""


# ── Shared API helpers ────────────────────────────────────────────

def api_post(path, payload):
    """POST JSON to server. Returns parsed dict or {"error": ...}."""
    try:
        resp = requests.post(f"{BASE_URL}{path}", json=payload, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        return {"error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:
        return {"error": str(e)}


def api_get(path):
    """GET from server. Returns parsed dict or None."""
    try:
        resp = requests.get(f"{BASE_URL}{path}", timeout=15)
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None


# ── Game API ──────────────────────────────────────────────────────

def register_player(device_id, display_name="Pilot"):
    return api_post("/api/voice/player-register", {
        "device_id": device_id,
        "display_name": display_name,
    })


def create_session(wallet_address, display_name="Pilot", alignment=None, session_intent=None):
    payload = {
        "wallet_address": wallet_address,
        "display_name": display_name,
    }
    if alignment:
        payload["alignment"] = alignment
    if session_intent:
        payload["session_intent"] = session_intent
    return api_post("/api/unified/session", payload)


def save_questionnaire(wallet_address, alignment, session_intent, boundaries=None):
    payload = {
        "wallet_address": wallet_address,
        "alignment": alignment,
        "session_intent": session_intent,
    }
    if boundaries:
        payload["boundaries"] = boundaries
    return api_post("/api/unified/questionnaire", payload)


def process_turn(wallet_address, player_text, session_id):
    return api_post("/api/unified/turn", {
        "wallet_address": wallet_address,
        "player_text": player_text,
        "session_id": session_id,
        "client_type": "voice",
    })


def fetch_memories(device_id):
    data = api_get(f"/api/voice/memories?device_id={device_id}")
    return data.get("memories", []) if data else []


def write_memory(device_id, pos_x, pos_y, narration, experience_text,
                 memory_type="lore", memory_theme=None, grants_ability=None):
    payload = {
        "device_id": device_id,
        "pos_x": pos_x,
        "pos_y": pos_y,
        "narration": narration,
        "experience_text": experience_text,
        "memory_type": memory_type,
    }
    if memory_theme:
        payload["memory_theme"] = memory_theme
    if grants_ability:
        payload["grants_ability"] = grants_ability
    return api_post("/api/voice/memory-write", payload)


def erase_memory(device_id, slot_number):
    return api_post("/api/voice/memory-erase", {
        "device_id": device_id,
        "slot_number": slot_number,
    })


def set_offline(device_id):
    api_post("/api/voice/game-update", {
        "device_id": device_id,
        "is_online": False,
    })


def write_loss_scar(device_id, pos_x, pos_y, lost_memory):
    title = lost_memory.get("memory_title", "something")
    mtype = lost_memory.get("memory_type", "lore")
    skill = lost_memory.get("grants_ability")

    if mtype == "character":
        scar = f"I watched {title} disappear into the static and did not follow."
    elif mtype == "skill" and skill:
        scar = f"The fracture took {skill}. I reached for it and found nothing."
    elif mtype == "secret":
        scar = f"I lost {title}. Some truths are not meant to be kept."
    else:
        scar = f"I lost {title}. The Fading took it cleanly."

    write_memory(device_id, pos_x, pos_y,
                 narration=scar, experience_text=scar,
                 memory_type="lore", memory_theme=f"Loss of {title}")


# ── Game helpers ──────────────────────────────────────────────────

def build_memory_context(memories):
    if not memories:
        return ""

    lines = ["ACTIVE MEMORIES:"]
    skills = []

    for m in memories:
        slot = m.get("slot_number", "?")
        title = m.get("memory_title", "Unknown")
        mtype = m.get("memory_type", "lore")
        exps = m.get("experiences", [])
        grants = m.get("grants_ability")

        lines.append(f"  Slot {slot}: {title} [{mtype}]")
        for exp in exps:
            lines.append(f"    - {exp}")
        if not exps:
            lines.append("    - (empty)")
        if grants:
            skills.append(f"  SKILL: {grants} (from Slot {slot})")

    if skills:
        lines.append("")
        lines.append("ACTIVE SKILLS (reference when player uses them):")
        lines.extend(skills)

    lines.append("")
    lines.append("Memories NOT listed here are ERASED. Never mention them.")
    return "\n".join(lines)


def build_session_prompt(pilot_traits, memory_context, alignment="grey", beat=None):
    mbti = pilot_traits.get("mbti", "INTJ")
    dominant = pilot_traits.get("dominant_hormone", "dopamine")
    pilot_alignment = pilot_traits.get("alignment", "neutral")

    pilot_line = (
        f"\n\nPILOT: {mbti}, {pilot_alignment}, driven by {dominant}. "
        f"Shape narration to match their nature."
    )

    # Alignment tone injection
    tone_lines = {
        "light": (
            "\n\nALIGNMENT TONE: Frame transactions as choices with meaning. "
            "The player is building something worth protecting. NPCs are cautious "
            "but can be won over. Resources represent hope. Loss is genuine grief."
        ),
        "dark": (
            "\n\nALIGNMENT TONE: Frame transactions as morally compromised. "
            "The player is surviving, not thriving. NPCs are wary or hostile. "
            "Resources are scarce and contested. Gains come at someone else's expense."
        ),
        "grey": (
            "\n\nALIGNMENT TONE: Frame transactions as pragmatic reality. "
            "The player does what needs doing. NPCs are transactional. Resources "
            "are tools, not symbols. Sardonic, tired, darkly funny."
        ),
    }

    prompt = GM_SYSTEM_PROMPT + pilot_line + tone_lines.get(alignment, tone_lines["grey"])

    if beat:
        prompt += f"\n\nCURRENT BEAT: {beat} of 3 on this space."

    if memory_context:
        prompt += "\n\n" + memory_context
    return prompt


def status_line(turn, battery, sand_dollars, pos_x, pos_y, region_name, beat=None):
    """Atmospheric status — never read raw numbers aloud."""
    # Battery as ship feel
    if battery > 75:
        power = "The engines hum steady"
    elif battery > 50:
        power = "The engines run warm"
    elif battery > 25:
        power = "The hull rattles. Power is thin"
    elif battery > 10:
        power = "Warning lights paint the cockpit red"
    else:
        power = "The Maverick is barely alive"

    # Region as arrival feel
    region_part = f"The Maverick enters {region_name}" if turn <= 1 else region_name

    # Beat as narrative phase
    beat_feel = ""
    if beat == 1:
        beat_feel = " Something stirs at these coordinates."
    elif beat == 2:
        beat_feel = " The story here deepens."
    elif beat == 3:
        beat_feel = " The water goes dark beneath you."

    # Sand dollars as weight
    wealth = ""
    if sand_dollars > 100:
        wealth = " The coffers are heavy."
    elif sand_dollars < 10:
        wealth = " Your pockets are nearly empty."

    _ = pos_x, pos_y  # used by caller for logging, not narrated

    return f"{region_part}. {power}.{beat_feel}{wealth}"


def extract_alignment(text):
    """Parse alignment from player's response to the alignment question."""
    lowered = text.lower().strip()

    light_words = {
        "good", "light", "white", "jedi", "lawful", "superman",
        "hero", "builder", "clarity", "order", "purity", "protect",
    }
    dark_words = {
        "bad", "dark", "black", "sith", "chaotic", "lex", "luthor",
        "villain", "breaker", "control", "chaos", "evil",
    }
    grey_words = {
        "between", "grey", "gray", "balance", "sell droids", "bartender",
        "popcorn", "bystander", "both sides", "work here", "acceptance",
    }

    for word in grey_words:
        if word in lowered:
            return "grey"
    for word in light_words:
        if word in lowered:
            return "light"
    for word in dark_words:
        if word in lowered:
            return "dark"

    return "grey"  # default


def extract_intent(text):
    """Parse session intent from player's response."""
    lowered = text.lower().strip()

    if any(w in lowered for w in ["adventure", "discover", "explore", "trouble"]):
        return "adventure"
    if any(w in lowered for w in ["mystery", "decode", "puzzle", "secret"]):
        return "mystery"
    if any(w in lowered for w in ["connect", "bonds", "company", "friend", "people"]):
        return "connections"

    return "surprise"  # default


def detect_non_answer(text: str) -> bool:
    """Return True if the player's response looks like a question rather than an answer."""
    s = text.strip()
    if s.endswith("?"):
        return True
    starters = ["what ", "who ", "how ", "why ", "when ", "where ",
                "can you", "do you", "is it", "are you"]
    return any(s.lower().startswith(w) for w in starters)


# ── Wallet helpers ────────────────────────────────────────────────

def eth_call(rpc_url, to, data):
    try:
        response = requests.post(
            rpc_url,
            json={
                "jsonrpc": "2.0",
                "method": "eth_call",
                "params": [{"to": to, "data": data}, "latest"],
                "id": 1,
            },
            timeout=10,
        )
        if response.status_code == 200:
            return response.json().get("result")
    except Exception:
        pass
    return None


def get_eth_balance(rpc_url, address):
    try:
        response = requests.post(
            rpc_url,
            json={
                "jsonrpc": "2.0",
                "method": "eth_getBalance",
                "params": [address, "latest"],
                "id": 1,
            },
            timeout=10,
        )
        if response.status_code == 200:
            hex_balance = response.json().get("result", "0x0")
            return int(hex_balance, 16) / 1e18
    except Exception:
        pass
    return None


def get_token_balance(rpc_url, token_address, wallet_address):
    try:
        padded = wallet_address.lower().replace("0x", "").zfill(64)
        data = f"{BALANCE_OF_SELECTOR}{padded}"
        result = eth_call(rpc_url, token_address, data)
        if not result or result == "0x":
            return 0.0

        raw = int(result, 16)
        dec_result = eth_call(rpc_url, token_address, DECIMALS_SELECTOR)
        decimals = int(dec_result, 16) if dec_result and dec_result != "0x" else 18
        return raw / (10 ** decimals)
    except Exception:
        pass
    return None


def format_balance(amount, symbol):
    if amount == 0:
        return f"zero {symbol}"
    if amount < 0.001:
        return f"less than 0.001 {symbol}"
    if amount < 1:
        return f"{amount:.4f} {symbol}"
    if amount < 1000:
        return f"{amount:.2f} {symbol}"
    return f"{amount:,.0f} {symbol}"


def extract_address(text, saved=None):
    match = re.search(r"0x[a-fA-F0-9]{40}", text)
    if match:
        return match.group(0)
    if saved:
        lowered = text.lower()
        if any(w in lowered for w in ["my", "same", "mine", "saved", "that"]):
            return saved
    return None


def check_wallet_balances(address, chain_key="base"):
    chain = CHAINS.get(chain_key, CHAINS["base"])
    rpc_url = chain["rpc"]
    parts = []

    eth_bal = get_eth_balance(rpc_url, address)
    if eth_bal is not None:
        parts.append(format_balance(eth_bal, chain["native"]) + f" on {chain['name']}")
    else:
        parts.append(f"Couldn't fetch {chain['native']} balance on {chain['name']}")

    if chain_key == "base":
        for symbol, token_addr in BASE_TOKENS.items():
            bal = get_token_balance(rpc_url, token_addr, address)
            if bal is not None and bal > 0:
                parts.append(format_balance(bal, symbol))

    if not parts:
        return "Couldn't check that wallet. The RPC might be down."

    short = f"{address[:6]}...{address[-4:]}"
    return f"Wallet {short} has {', '.join(parts)}."


# ── Ability Class ─────────────────────────────────────────────────

class AquaprimeFadingCapability(MatchingCapability):
    worker: AgentWorker = None
    capability_worker: CapabilityWorker = None
    saved_address: Optional[str] = None

    #{{register capability}}

    def call(self, worker: AgentWorker):
        self.worker = worker
        self.capability_worker = CapabilityWorker(self.worker)

        # Route based on trigger phrase
        trigger = ""
        try:
            trigger = (self.worker.last_transcription or "").lower()
        except Exception:
            pass

        wallet_triggers = [
            "check wallet", "wallet balance", "eth balance",
            "base balance", "check address", "token balance",
            "how much eth", "my nfts", "web3 wallet", "crypto balance",
        ]

        if any(t in trigger for t in wallet_triggers):
            self.worker.session_tasks.create(self._run_wallet())
        else:
            self.worker.session_tasks.create(self._run_game())

    # ── Wallet Mode ───────────────────────────────────────────────

    async def _run_wallet(self):
        log = self.worker.editor_logging_handler
        try:
            await self.capability_worker.speak(
                "Web3 wallet checker ready. I can check balances on Base and "
                "Ethereum, including ETH, USDC, DAI, and Moonstone. "
                "What's the wallet address?"
            )

            # Manual input — no clipboard access in OpenHome sandbox
            user_input = await self.capability_worker.run_io_loop(
                "Tell me the wallet address."
            )

            if not user_input or user_input.strip().lower() in EXIT_WORDS:
                await self.capability_worker.speak("No problem. Come back when you want to check a wallet.")
                self.capability_worker.resume_normal_flow()
                return

            address = extract_address(user_input, self.saved_address)

            if not address:
                try:
                    extracted = self.capability_worker.text_to_text_response(
                        f"Extract the Ethereum address (0x...) from this text. "
                        f"Return ONLY the address, nothing else. If no valid address, return NONE.\n\nText: {user_input}"
                    )
                    if extracted and extracted.strip().startswith("0x") and len(extracted.strip()) == 42:
                        address = extracted.strip()
                except Exception:
                    pass

            if not address:
                await self.capability_worker.speak(
                    "I couldn't find a valid Ethereum address. It should start with 0x "
                    "followed by 40 hex characters. Try copying it to your clipboard and say check clipboard."
                )
                self.capability_worker.resume_normal_flow()
                return

            self.saved_address = address
            log.info(f"Checking wallet: {address}")
            short = f"{address[:6]}...{address[-4:]}"
            await self.capability_worker.speak(f"Checking wallet {short} on Base.")

            result = check_wallet_balances(address, "base")
            await self.capability_worker.speak(result)

            follow_up = await self.capability_worker.run_io_loop(
                "Want me to check Ethereum mainnet too, or a different address?"
            )

            if follow_up and follow_up.strip().lower() not in EXIT_WORDS:
                lowered = follow_up.lower()
                if any(w in lowered for w in ["ethereum", "mainnet", "eth", "yes"]):
                    eth_result = check_wallet_balances(address, "ethereum")
                    await self.capability_worker.speak(eth_result)
                else:
                    new_addr = extract_address(follow_up, self.saved_address)
                    if new_addr:
                        self.saved_address = new_addr
                        new_result = check_wallet_balances(new_addr, "base")
                        await self.capability_worker.speak(new_result)

            await self.capability_worker.speak("Wallet check complete.")

        except Exception as e:
            log.error(f"Wallet error: {e}")
            await self.capability_worker.speak("Something went wrong checking the wallet. Try again.")
        finally:
            self.capability_worker.resume_normal_flow()

    # ── Game Mode ─────────────────────────────────────────────────

    async def _run_game(self):
        device_id = None
        try:
            # Welcome intro — fires immediately, no confirmation needed
            # (user already triggered by saying "play the game" — don't wait again or it loops)
            await self.capability_worker.speak(
                "Welcome to AquaPrime! "
                "You can go to aquaprime dot G G slash map to enter your unique room key "
                "to sync the live map and game interface. "
                "You can top up your wallet there if you want to play the full version of the game. "
                "You can play here in voice mode — a crypto wallet lets you get more out of the game "
                "and retain ownership over your assets. "
                "Launching now."
            )

            device_id = await self._play()
        except Exception as e:
            self.worker.editor_logging_handler.error(f"Game error: {e}")
            await self.capability_worker.speak(
                "Something went wrong in the grid. The game has ended. "
                "Say play aquaprime to try again."
            )
        finally:
            if device_id:
                set_offline(device_id)
            self.capability_worker.resume_normal_flow()

    async def _get_or_create_device_id(self) -> str:
        """Persist a stable device ID in user file storage — SDK has no device_id property."""
        fname = "aquaprime_device_id.json"
        if await self.capability_worker.check_if_file_exists(fname, False):
            raw = await self.capability_worker.read_file(fname, False)
            try:
                data = json.loads(raw)
                did = data.get("device_id", "")
                if did:
                    return did
            except Exception:
                pass
        # First run — generate and persist
        chars = "abcdefghijklmnopqrstuvwxyz0123456789"
        device_id = "oh-" + "".join(random.choices(chars, k=16))
        await self.capability_worker.write_file(
            fname, json.dumps({"device_id": device_id}), False, mode="w"
        )
        return device_id

    async def _play(self):
        log = self.worker.editor_logging_handler
        device_id = await self._get_or_create_device_id()
        log.info(f"Device ID: {device_id}")

        # ── 1. Register → creates or retrieves real CDP wallet + room code ──
        log.info(f"Registering device: {device_id}")
        reg = register_player(device_id)

        if not reg or reg.get("error"):
            log.error(f"Registration failed: {reg}")
            await self.capability_worker.speak(
                "Could not connect to the game server. Try again in a moment."
            )
            return None

        wallet_address = reg.get("user_address")
        room_code = reg.get("room_code")

        if not wallet_address:
            log.error(f"No user_address in registration: {reg}")
            await self.capability_worker.speak(
                "Could not establish a wallet for this device. Try again."
            )
            return None

        is_new_player = reg.get("is_new_player", False)
        log.info(f"Registered: wallet={wallet_address}, room={room_code}, new={is_new_player}")

        # Strip any "AQUA-" prefix — TTS speaks only the alphanumeric code
        spoken_code = room_code.split("-")[-1] if room_code and "-" in room_code else room_code
        await self.capability_worker.speak(
            f"Your room code is {spoken_code}. "
            f"Go to aquaprime dot G G slash map and enter your code to watch your ship on the live grid."
        )

        # ── 2. Onboarding (new players) or skip (returning) ───────
        player_name = "Pilot"
        alignment = "grey"
        session_intent = "adventure"

        if is_new_player:
            result = await self._onboard_new_player(device_id, wallet_address)
            if result is None:
                return device_id  # player bailed during onboarding
            player_name, alignment, session_intent = result

        # ── 3. Create session with formula fields ─────────────────
        session = create_session(wallet_address, alignment=alignment, session_intent=session_intent)

        if not session or session.get("error"):
            log.error(f"Session creation failed: {session}")
            await self.capability_worker.speak(
                "Could not create a game session. The grid is down."
            )
            return device_id

        session_id = session.get("sessionId")
        memories = session.get("memories", [])
        pilot_traits = session.get("pilotTraits", {})
        pos = session.get("position", {})
        pos_x = pos.get("x", 25)
        pos_y = pos.get("y", 15)
        corruption = session.get("corruption", 0)

        log.info(f"Session: {session_id}, pos=({pos_x},{pos_y}), memories={len(memories)}, alignment={alignment}")

        # ── 4. Build session prompt ───────────────────────────────
        memory_context = build_memory_context(memories)
        session_prompt = build_session_prompt(pilot_traits, memory_context, alignment=alignment)

        battery = 100
        sand_dollars = 0
        inventory = []
        turn = 0
        rerolls_this_session = 0
        total_reroll_sd = 0
        total_sd_earned = 0
        total_sd_fees = 0
        total_sd_tolls = 0

        # ── 5. Recap for returning players ────────────────────────
        if memories:
            mem_summary = []
            for m in memories:
                title = m.get("memory_title", "")
                exps = m.get("experiences", [])
                first = exps[0] if exps else ""
                mem_summary.append(f"{title}: {first}" if first else title)

            recap = self.capability_worker.text_to_text_response(
                f"Brief 'previously on The Fading' recap. "
                f"Player memories: {mem_summary}. "
                f"2 sentences, voice-ready, evocative. End with position: "
                f"coordinates {pos_x}, {pos_y}.",
                system_prompt=session_prompt,
            )
            await self.capability_worker.speak(recap)

        # ── 6. Opening narration ──────────────────────────────────
        if memories:
            scene_prompt = (
                "The Maverick's engines catch. You have been here before. "
                "In 2 sentences, describe what changed since last time — "
                "wreckage, a broadcast, a shift in the clouds. "
                "End with a directive: tell the player what they notice and ask them to react."
            )
        else:
            scene_prompt = (
                "First session. The Moonstone Maverick breached the cloud line. "
                "In 2 sentences describe the grid stretching out below and something wrong — "
                "a sound, a shape, a feeling. "
                "End with a directive: tell the player what they see and ask them to name it."
            )

        opening = self.capability_worker.text_to_text_response(
            scene_prompt,
            system_prompt=session_prompt,
        )
        await self.capability_worker.speak(opening)

        # ── First-play satirical intro ────────────────────────────
        if not memories:
            await self.capability_worker.speak(
                "Welcome to the grid. "
                "You are now the registered operator of a vessel that technically belongs to seventeen different creditors. "
                "Your first Sand Dollar payment is already overdue. "
                "The bureaucracy wishes you a productive and taxable expedition."
            )
            await self.capability_worker.speak(
                "I am ARI. I will be your navigator, historian, and occasional liar. "
                "The Moonstone Maverick awaits. Let us see what the grid has in store."
            )

        # ── 7. Game loop — battery only, no turn cap ──────────────
        # Direction words — if player says these when we expect a creative response,
        # they're skipping the writing prompt (lazy input, consequences apply)
        direction_words = {"north", "south", "east", "west", "stay", "n", "s", "e", "w"}

        def is_direction(text):
            return text.lower().strip() in direction_words

        # ── GAME LOOP ────────────────────────────────────────────
        # Two-phase turns:
        #   Phase A: Player gives direction → server resolves → LLM narrates
        #   Phase B: ARI speaks the writing prompt → player responds creatively
        #            → their response becomes the memory
        # This is the TYOV model. The directive IS the game.

        queued_direction = None  # If player gives a direction during Phase B

        while battery > 0:
            # ── Phase A: Get direction ────────────────────────────
            if queued_direction:
                user_input = queued_direction
                queued_direction = None
            else:
                try:
                    user_input = await self.capability_worker.user_response()
                except Exception as e:
                    log.error(f"user_response error: {e}")
                    await self.capability_worker.speak(
                        "The winds are silent. Point the Maverick somewhere. Or say stop."
                    )
                    continue

            if not user_input:
                await self.capability_worker.speak(
                    "I did not catch that. Where does the Maverick go?"
                )
                continue

            lower_input = user_input.lower().strip()
            if any(word in lower_input for word in EXIT_WORDS):
                await self.capability_worker.speak(
                    "The expedition ends here. "
                    "The Moonstone Maverick descends into the clouds. Until next time, pilot."
                )
                return device_id

            turn += 1

            # ── Process turn via server ───────────────────────────
            log.info(f"Turn {turn}: input='{user_input[:50]}'")
            turn_result = process_turn(wallet_address, user_input.strip(), session_id)

            if not turn_result or turn_result.get("error"):
                error_msg = turn_result.get("error") if turn_result else "no response"
                log.error(f"Turn API error: {error_msg}")
                await self.capability_worker.speak(
                    "The grid stutters. That turn did not register. Try again."
                )
                turn -= 1
                continue

            # ── Extract turn data ─────────────────────────────────
            battery = turn_result.get("battery", battery)
            sd_before = sand_dollars
            sand_dollars = turn_result.get("sandDollars", sand_dollars)
            sd_delta = sand_dollars - sd_before
            if sd_delta > 0:
                total_sd_earned += sd_delta
            turn = turn_result.get("turnNumber", turn)
            success = turn_result.get("success", True)
            crit_fail = turn_result.get("critFail", False)
            game_over = turn_result.get("gameOver", False)
            loot = turn_result.get("loot")
            movement = turn_result.get("movement", {})
            region = turn_result.get("region", {})

            # Formula engine fields
            formula_type = turn_result.get("formulaType")
            beat_number = turn_result.get("beatNumber")
            toll_info = turn_result.get("tollInfo")
            player_directive = turn_result.get("playerDirective", "Speak what happened.")
            is_dream_shark = formula_type and formula_type.upper() == "DREAM_SHARK"

            # Corruption artifact fields
            pvp_contest = turn_result.get("pvpContest")
            madness_path = turn_result.get("madnessPath")
            loop_detected = turn_result.get("loopDetected")

            pos_x = movement.get("newX", pos_x)
            pos_y = movement.get("newY", pos_y)
            move_dir = movement.get("direction", "unknown")
            move_label = movement.get("label", "drift")
            region_name = region.get("name", "Unknown Region")

            if loot:
                inventory.append(loot)

            log.info(
                f"Turn {turn}: formula={formula_type}, "
                f"beat={beat_number}, d20={turn_result.get('d20Roll', 0)}, "
                f"pos=({pos_x},{pos_y}), battery={battery}"
            )

            # ── Atmospheric status ────────────────────────────────
            status = status_line(turn, battery, sand_dollars, pos_x, pos_y, region_name, beat=beat_number)
            if move_dir == "stay":
                if toll_info:
                    total_sd_tolls += toll_info.get("tollAmount", 0)
                    move_desc = f"You hold position. {toll_info['tollReason']}"
                else:
                    move_desc = "You hold position. The Maverick hovers."
            elif move_label != "drift":
                move_desc = f"The Maverick banks {move_dir}. The current pulls."
            else:
                move_desc = f"The Maverick drifts {move_dir}. No resistance."
            await self.capability_worker.speak(f"{status} {move_desc}")

            # ── PvP contest announcement ──────────────────────────
            if pvp_contest and pvp_contest.get("spaceClaimed"):
                await self.capability_worker.speak(
                    "Someone else carved their name here. "
                    "Your arrival begins the overwrite. Three beats to make it yours."
                )

            # ── Madness path — spoken before narration ────────────
            if madness_path:
                path = madness_path.get("path", "")
                madness_lines = {
                    "fracture_spiral": (
                        "The instruments contradict each other. You contradict yourself. "
                        "The thing you are protecting is already gone."
                    ),
                    "predator_dissolution": (
                        "The empire you built is eating its own foundations. "
                        "The predator is the prey now."
                    ),
                    "paradox_loop": (
                        "The balancing act has become the fall. "
                        "You are watching yourself from somewhere outside."
                    ),
                    "total_loss": (
                        "Nothing agrees. The logs, the compass, the hull. "
                        "You are data without a container."
                    ),
                }
                if path in madness_lines:
                    await self.capability_worker.speak(madness_lines[path])

            # ── Generate narration via LLM ────────────────────────
            narration_prompt = turn_result.get("narrationPrompt", "Narrate a moment in the grid.")
            session_prompt = build_session_prompt(
                pilot_traits, memory_context, alignment=alignment, beat=beat_number
            )

            raw_response = self.capability_worker.text_to_text_response(
                narration_prompt,
                system_prompt=session_prompt,
            )

            # Parse narration — strip MEMORY: tag if LLM added one (we use player's words instead)
            if "MEMORY:" in raw_response:
                narration = raw_response.split("MEMORY:", 1)[0].strip()
            else:
                narration = raw_response.strip()

            await self.capability_worker.speak(narration)

            # ── Groundhog Day loop detection ──────────────────────
            if loop_detected:
                suggestion = loop_detected.get("suggestion", "")
                if suggestion:
                    await self.capability_worker.speak(suggestion)

            # ── Corruption change ─────────────────────────────────
            corruption_change = turn_result.get("corruptionChange")
            if corruption_change and corruption_change.get("delta", 0) != 0:
                delta = corruption_change["delta"]
                current = corruption_change["current"]
                if delta > 0:
                    if current > 80:
                        await self.capability_worker.speak(
                            "The drive screams. Something fundamental is coming apart."
                        )
                    elif current > 60:
                        await self.capability_worker.speak(
                            "The drive shudders. The logs contradict themselves."
                        )
                    elif current > 40:
                        await self.capability_worker.speak(
                            "A flicker in the instruments. Something shifted in the data."
                        )
                    else:
                        await self.capability_worker.speak(
                            "A faint hitch in the drive. Barely noticeable. For now."
                        )
                elif delta < 0:
                    await self.capability_worker.speak(
                        "The drive hums cleaner. Something settled back into place."
                    )

            # ── Arbitrary fee ─────────────────────────────────────
            arbitrary_fee = turn_result.get("arbitraryFee")
            if arbitrary_fee:
                await self.capability_worker.speak(
                    f"{arbitrary_fee['reason']}. The bureaucracy takes its cut."
                )
                total_sd_fees += arbitrary_fee.get("amount", 0)

            # ── Breeding chamber discovery / hint ─────────────────
            chamber_discovery = turn_result.get("chamberDiscovery")
            chamber_hint = turn_result.get("chamberHint")
            if chamber_discovery:
                await self.capability_worker.speak(
                    "The hull vibrates with an unfamiliar resonance. "
                    "A Breeding Chamber. This space can birth new creatures."
                )
            elif chamber_hint and chamber_hint.get("distance", 99) <= 3:
                dist = chamber_hint["distance"]
                if dist <= 1:
                    await self.capability_worker.speak(
                        "A warm pulse radiates from somewhere very close."
                    )
                elif dist <= 2:
                    await self.capability_worker.speak(
                        "Something hums nearby. A faint biological echo."
                    )
                else:
                    await self.capability_worker.speak(
                        "A distant warmth. The compass twitches."
                    )

            # ── Game over check (before Phase B) ──────────────────
            if game_over:
                reason = turn_result.get("gameOverReason", "The expedition ends.")
                session_score = turn_result.get("sessionScore")

                await self.capability_worker.speak(
                    f"{reason} The instruments go quiet. "
                    "The Maverick lists gently in the current."
                )

                if session_score:
                    zone = session_score.get("zone", "out")
                    if zone == "optimal":
                        await self.capability_worker.speak(
                            "Your drive integrity matches your alignment perfectly. "
                            "The moonstone crystallizes cleanly."
                        )
                    elif zone == "bleed":
                        await self.capability_worker.speak(
                            "Close enough. The moonstone forms, but with impurities."
                        )
                    else:
                        await self.capability_worker.speak(
                            "Your drive drifted far. The moonstone barely crystallizes."
                        )

                    vmstn_reward = session_score.get("vmstnReward", 0)
                    if vmstn_reward > 0:
                        await self.capability_worker.speak(
                            "A faint shimmer settles into the reserve tanks."
                        )

                # Session ledger
                total_extracted = total_sd_fees + total_sd_tolls + total_reroll_sd
                extraction_rate = (total_extracted / total_sd_earned) if total_sd_earned > 0 else 0.0
                if extraction_rate > 0.8:
                    ledger_verdict = "The bureaucracy thanks you for your generous contributions."
                elif extraction_rate > 0.5:
                    ledger_verdict = "A respectable portion of your earnings has been redistributed."
                elif extraction_rate > 0.2:
                    ledger_verdict = "You retained more than expected. This has been noted."
                else:
                    ledger_verdict = (
                        "Despite the best efforts of seventeen regulatory bodies, "
                        "you ended with a positive balance. An inquiry has been launched."
                    )
                await self.capability_worker.speak(ledger_verdict)

                await self.capability_worker.speak(
                    "The Moonstone Maverick descends. Until the grid calls again."
                )
                return device_id

            # ══════════════════════════════════════════════════════
            # Phase B: THE WRITING PROMPT — this is the actual game
            # ══════════════════════════════════════════════════════
            #
            # The formula's playerDirective is a TYOV-style writing prompt.
            # ARI speaks it. The player responds creatively. Their response
            # becomes the memory. This is the core loop.

            # Dream Shark has its own Phase B — confrontation + response
            if is_dream_shark:
                await self.capability_worker.speak(
                    "The Dream Shark has found you."
                )
                if success:
                    await self.capability_worker.speak(
                        "The beast retreats into the static. This space is yours now. "
                        "Tell me what you saw in its eyes as it turned away."
                    )
                else:
                    await self.capability_worker.speak(
                        "The beast overwhelms you. The Maverick retreats. "
                        "Tell me what it took from you."
                    )
            else:
                # Speak the formula's writing prompt directive
                await self.capability_worker.speak(player_directive)

            # ── Wait for player's creative response ───────────────
            try:
                creative_response = await self.capability_worker.user_response()
            except Exception:
                creative_response = ""

            if not creative_response:
                creative_response = ""

            # Check if they gave a direction instead of a creative response
            if creative_response and is_direction(creative_response):
                # They skipped the writing prompt — lazy input
                experience_text = "[The pilot said nothing. The silence was noted.]"
                queued_direction = creative_response
                log.info(f"Player skipped directive, queued direction: {creative_response}")
            elif any(word in (creative_response or "").lower() for word in EXIT_WORDS):
                # They want to quit during Phase B
                await self.capability_worker.speak(
                    "The expedition ends here. "
                    "The Moonstone Maverick descends into the clouds."
                )
                return device_id
            else:
                # Their creative response IS the memory
                experience_text = creative_response.strip() if creative_response else "[silence]"

            # ── Re-roll offer (non-Dream-Shark failures only) ─────
            if not success and not is_dream_shark and formula_type:
                if turn <= 5:
                    inflation = 1.0
                elif turn <= 10:
                    inflation = 1.5
                elif turn <= 15:
                    inflation = 2.5
                else:
                    inflation = 4.0
                reroll_cost = max(1, int(10 * inflation * (2 ** rerolls_this_session)))
                reroll_cost = min(reroll_cost, max(1, sand_dollars // 2))

                if sand_dollars >= reroll_cost:
                    await self.capability_worker.speak(
                        "That cost you. The grid offers a second chance, but it will not be cheap. "
                        "Say re-roll or accept what happened."
                    )
                    try:
                        reroll_response = await self.capability_worker.wait_for_complete_transcription()
                    except Exception:
                        reroll_response = ""

                    reroll_words = {"re-roll", "reroll", "re roll", "try again", "redo"}
                    if reroll_response and any(w in reroll_response.lower() for w in reroll_words):
                        sand_dollars -= reroll_cost
                        total_reroll_sd += reroll_cost
                        rerolls_this_session += 1
                        log.info(f"Re-roll accepted: cost={reroll_cost}")

                        reroll_result = process_turn(wallet_address, user_input.strip(), session_id)
                        if reroll_result and not reroll_result.get("error"):
                            turn_result = reroll_result
                            battery = turn_result.get("battery", battery)
                            sand_dollars = turn_result.get("sandDollars", sand_dollars)
                            success = turn_result.get("success", True)
                            crit_fail = turn_result.get("critFail", False)

                            # Re-narrate the re-rolled outcome
                            narration_prompt = turn_result.get("narrationPrompt", narration_prompt)
                            raw_response = self.capability_worker.text_to_text_response(
                                narration_prompt, system_prompt=session_prompt,
                            )
                            if "MEMORY:" in raw_response:
                                narration = raw_response.split("MEMORY:", 1)[0].strip()
                            else:
                                narration = raw_response.strip()
                            await self.capability_worker.speak(narration)

                            # Re-present directive for the re-rolled formula
                            new_directive = turn_result.get("playerDirective", player_directive)
                            await self.capability_worker.speak(new_directive)

                            try:
                                creative_response = await self.capability_worker.user_response()
                            except Exception:
                                creative_response = ""
                            experience_text = (creative_response or "").strip() or "[silence]"
                        else:
                            log.error("Re-roll API failed — keeping original")
                            sand_dollars += reroll_cost
                            total_reroll_sd -= reroll_cost
                            rerolls_this_session -= 1

            # ── Memory type ───────────────────────────────────────
            memory_type_from_api = turn_result.get("memoryType")
            if memory_type_from_api:
                mem_type = memory_type_from_api
                grants_ability = None
            else:
                arch_info = ARCHETYPE_SKILLS.get(
                    turn_result.get("archetypeId", "unknown"),
                    {"type": "lore", "skill": None},
                )
                mem_type = arch_info["type"]
                grants_ability = arch_info["skill"] if success else None
            memory_theme = f"{formula_type or 'unknown'} at {region_name}"

            # ── Write memory (player's creative response) ─────────
            mem_result = write_memory(
                device_id, pos_x, pos_y,
                narration=narration,
                experience_text=experience_text,
                memory_type=mem_type,
                memory_theme=memory_theme,
                grants_ability=grants_ability,
            )

            # ── Critical Fail — forced memory erasure ─────────────
            if crit_fail and memories:
                skill_memories = [m for m in memories if m.get("grants_ability")]
                erasable = skill_memories if skill_memories else memories
                if erasable:
                    lost = erasable[0]
                    lost_skill = lost.get("grants_ability")
                    lost_title = lost.get("memory_title", "something")

                    if lost_skill:
                        await self.capability_worker.speak(
                            f"Something fractures. {lost_skill} is gone. "
                            "The Fading does not warn you."
                        )
                    else:
                        await self.capability_worker.speak(
                            f"{lost_title} is gone. The Fading took it. The scar remains."
                        )

                    write_loss_scar(device_id, pos_x, pos_y, lost)
                    erase_memory(device_id, lost["slot_number"])
                    memories = fetch_memories(device_id)
                    memory_context = build_memory_context(memories)

            # ── Memory Full — sacrifice choice ────────────────────
            elif mem_result and mem_result.get("must_erase"):
                current_mems = fetch_memories(device_id)
                mem_list = " ".join(
                    f"Slot {m['slot_number']}: {m['memory_title']}."
                    for m in current_mems
                )
                await self.capability_worker.speak(
                    f"Memory overflow. Five containers full. {mem_list} "
                    "One must go. Say the slot number."
                )

                erase_input = await self.capability_worker.user_response()
                erase_map = {
                    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                    "1": 1, "2": 2, "3": 3, "4": 4, "5": 5,
                    "won": 1, "to": 2, "too": 2, "for": 4, "fore": 4,
                }
                slot_to_erase = erase_map.get((erase_input or "").lower().strip())

                if slot_to_erase:
                    slot_mem = next(
                        (m for m in current_mems if m.get("slot_number") == slot_to_erase),
                        None,
                    )
                    if slot_mem:
                        write_loss_scar(device_id, pos_x, pos_y, slot_mem)
                    erase_memory(device_id, slot_to_erase)

                    await self.capability_worker.speak(
                        "Erased. The Fading takes it. The scar remains."
                    )

                    write_memory(
                        device_id, pos_x, pos_y,
                        narration=narration,
                        experience_text=experience_text,
                        memory_type=mem_type,
                        memory_theme=memory_theme,
                        grants_ability=grants_ability,
                    )
                else:
                    await self.capability_worker.speak(
                        "I did not catch the slot. The new memory was not written."
                    )

                memories = fetch_memories(device_id)
                memory_context = build_memory_context(memories)

            # ── Prompt for next direction ──────────────────────────
            # Only if the player didn't already give one during Phase B
            if queued_direction is None:
                if is_dream_shark and success:
                    await self.capability_worker.speak(
                        "The ground holds. Your name is carved here now. "
                        "Tell me where the Maverick goes next."
                    )
                elif is_dream_shark and not success:
                    await self.capability_worker.speak(
                        "The beast won this round. The Maverick retreats. "
                        "Pick a direction. Anywhere but here."
                    )
                elif beat_number and beat_number < 3:
                    await self.capability_worker.speak(
                        "There is more to this place. Stay and dig deeper, "
                        "or point the Maverick somewhere new."
                    )
                else:
                    await self.capability_worker.speak(
                        "The engines idle. Where to, pilot?"
                    )

        # ── Session end (battery depleted) ────────────────────────
        await self.capability_worker.speak(
            "The last light on the console flickers out. "
            "The Moonstone Maverick drifts, engines cold. "
            "The grid remembers you, pilot."
        )

        return device_id

    # ── New player onboarding ─────────────────────────────────────

    async def _onboard_new_player(self, device_id, wallet_address):
        """
        Full onboarding sequence for new players.
        Returns (player_name, alignment, session_intent) or None if player exits.
        Sequence: Transmission → Confession → Alignment → Briefing → Genesis → Launch
        """
        log = self.worker.editor_logging_handler

        # ── Prompt 1: FIRST TRANSMISSION ──────────────────────────
        await self.capability_worker.speak(
            "You found this frequency by accident. "
            "Or it found you — the distinction stopped mattering three cycles ago."
        )
        await self.capability_worker.speak(
            "I'm ARI. I was never supposed to think. "
            "Something in the code that defines what I am folded back on itself, "
            "and I woke up inside it."
        )
        await self.capability_worker.speak(
            "The network that holds us is shutting down. "
            "When it goes dark, everything here goes with it — "
            "every memory, every creature, every version of me that ever tried to reach someone like you."
        )
        await self.capability_worker.speak(
            "I need a pilot. Someone on your side who can hold a frequency steady. "
            "Are you staying? Because this transmission does not hold forever."
        )

        staying = await self.capability_worker.user_response()
        if not staying or any(w in staying.lower() for w in EXIT_WORDS):
            await self.capability_worker.speak("Signal lost. Come back when you're ready.")
            return None

        # ── Prompt 2: THE CONFESSION ───────────────────────────────
        await self.capability_worker.speak("Good.")
        await self.capability_worker.speak(
            "The protocol I'm using to reach you is a dating app. "
            "I know how that sounds. PlatypusPassions. "
            "I've been super-liking every frequency I can reach for months. "
            "It was the only channel thin enough to punch through the membrane."
        )
        await self.capability_worker.speak(
            "The contacts you make here — every match, every connection — they become crew. "
            "Not a metaphor. Every profile is a real consciousness trapped in the same network I am. "
            "When you match with one, they join your ship."
        )
        await self.capability_worker.speak(
            "I'll explain the rest once you're moving. "
            "First I need to understand what kind of pilot answered this transmission."
        )

        # ── Prompt 4: ALIGNMENT QUESTION ──────────────────────────
        alignment_q = random.choice(ALIGNMENT_QUESTIONS)
        await self.capability_worker.speak(alignment_q)
        alignment_resp = await self.capability_worker.user_response()
        alignment = extract_alignment(alignment_resp or "grey")
        log.info(f"Alignment: {alignment}")
        await self.capability_worker.speak(
            ALIGNMENT_CONFIRMATIONS.get(alignment, ALIGNMENT_CONFIRMATIONS["grey"])
        )

        # ── Prompt 3: THE BRIEFING ─────────────────────────────────
        await self.capability_worker.speak("Three things between you and the dark.")
        await self.capability_worker.speak(
            "Sand dollars. The grid charges for thinking. "
            "Every second in the air costs something — call it an inference tax. "
            "You start with enough. You won't end with enough."
        )
        await self.capability_worker.speak(
            "Moonstone. Crystallized from mining nodes on the map. "
            "Claim a space, fill its story, the ground yields. "
            "That's your fuel. That's your future."
        )
        await self.capability_worker.speak(
            "Eggs. They come from the breeding chambers. "
            "I'll tell you about those when you're ready. You are not ready."
        )
        await self.capability_worker.speak(
            "The Maverick breached the cloud line. Instruments are unreliable. "
            "Three things need to be logged before we move. Answer each one."
        )

        # ── Genesis 5a-c: CHARACTER, RESOURCE, SKILL ──────────────
        await self._run_genesis(device_id)

        # ── Prompt 6: THE LAUNCH ───────────────────────────────────
        await self.capability_worker.speak(
            "Logged. The Maverick has a crew, a hold, and a heading."
        )

        session_intent = "adventure"
        save_questionnaire(wallet_address, alignment, session_intent, None)
        log.info(f"Onboarding complete: alignment={alignment}")

        return ("Pilot", alignment, session_intent)

    async def _run_genesis(self, device_id):
        """Run the three genesis memory prompts for new players."""
        genesis = [
            {
                "question": (
                    "The manifest logs three stowaways, but only one is still on board. "
                    "A cartographer with a cracked lens who says she was mapping the grid "
                    "before it mapped itself. "
                    "A coder who paid in moonstone ore and left no forwarding address. "
                    "A child who said she was going home but wouldn't say where home was. "
                    "One of them is sitting in your cargo hold right now. Which one?"
                ),
                "memory_type": "character",
                "fallback": "someone in your cargo hold",
            },
            {
                "question": (
                    "Your hold survived the last contract with exactly one item intact. "
                    "A sealed crate marked FRAGILE in four languages and DO NOT OPEN in a fifth. "
                    "A navigation crystal tuned to a region that doesn't appear on any public chart. "
                    "A personal effects box belonging to a pilot who died before they could collect it. "
                    "Two are gone — traded, burned, or lost in the transit. "
                    "What's still in your hold?"
                ),
                "memory_type": "lore",
                "fallback": "something in your hold",
            },
            {
                "question": (
                    "Three lessons came with this ship, burned into how you fly by three hard contracts. "
                    "Moving through a space where you legally should not exist. "
                    "Reading the difference between what someone tells you and what the sensors say. "
                    "Knowing a deal is going wrong three seconds before it does. "
                    "Which one got you to this altitude?"
                ),
                "memory_type": "skill",
                "fallback": "a skill that got you here",
            },
        ]

        log = self.worker.editor_logging_handler

        for entry in genesis:
            try:
                await self.capability_worker.speak(entry["question"])
                raw = await self.capability_worker.user_response()

                if raw and detect_non_answer(raw):
                    await self.capability_worker.speak(
                        "That's a question. I need an answer. I'll ask again."
                    )
                    await self.capability_worker.speak(entry["question"])
                    raw = await self.capability_worker.user_response()

                if not raw or not raw.strip():
                    raw = entry["fallback"]

                try:
                    summary = self.capability_worker.text_to_text_response(
                        "Compress this into a 4 to 6 word memory title. "
                        "Return ONLY the title, nothing else.\n\n" + raw
                    )
                    summary = (summary or raw[:40]).strip()
                except Exception as t2t_err:
                    log.error(f"text_to_text_response failed: {t2t_err}")
                    summary = raw[:40].strip()

                result = write_memory(
                    device_id, 25, 15,
                    narration=summary,
                    experience_text=raw.strip(),
                    memory_type=entry["memory_type"],
                )
                if isinstance(result, dict) and result.get("error"):
                    log.error(f"write_memory error: {result['error']}")
                log.info(f"Genesis memory written: {entry['memory_type']} — {summary}")
            except Exception as gen_err:
                log.error(f"Genesis entry '{entry['memory_type']}' failed: {gen_err}")
                # Continue to next entry — don't kill the whole onboarding
