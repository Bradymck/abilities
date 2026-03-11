import datetime
import json
import random
import re
from typing import Optional

import requests

from src.agent.capability import MatchingCapability
from src.agent.capability_worker import CapabilityWorker
from src.main import AgentWorker

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
    "Are you a good witch, or a bad witch... or something in between?",
    "Black hat, white hat, or grey hat?",
    "Jedi, Sith, or that guy who just wants to sell droids?",
    "Lawful good, chaotic evil, or 'I just work here'?",
    "Superman, Lex Luthor, or the bartender who serves them both?",
    "Builder, breaker, or the one watching from the balcony with popcorn?",
    "The hero, the villain, or the bystander who profits from both?",
    "Order, chaos, or the one who plays both sides?",
]

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

    #{{register_capability}}

    def call(self, worker: AgentWorker):
        self.worker = worker
        self.capability_worker = CapabilityWorker(self)

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

            # Try clipboard
            clipboard_addr = None
            try:
                result = await self.capability_worker.exec_local_command(
                    "pbpaste 2>/dev/null || xclip -selection clipboard -o 2>/dev/null || echo ''"
                )
                if result and result.get("data"):
                    match = re.search(r"0x[a-fA-F0-9]{40}", result["data"])
                    if match:
                        clipboard_addr = match.group(0)
            except Exception:
                pass

            if clipboard_addr:
                short = f"{clipboard_addr[:6]}...{clipboard_addr[-4:]}"
                confirm = await self.capability_worker.run_io_loop(
                    f"I found an address in your clipboard: {short}. Should I check this one?"
                )
                if confirm and confirm.strip().lower() in {
                    "yes", "yeah", "yep", "sure", "check it", "go ahead", "do it",
                }:
                    self.saved_address = clipboard_addr
                    await self.capability_worker.speak("Checking that wallet now.")
                    result = check_wallet_balances(clipboard_addr)
                    await self.capability_worker.speak(result)

                    eth_check = await self.capability_worker.run_io_loop(
                        "Want me to check the same address on Ethereum mainnet too?"
                    )
                    if eth_check and eth_check.strip().lower() in {"yes", "yeah", "yep", "sure"}:
                        eth_result = check_wallet_balances(clipboard_addr, "ethereum")
                        await self.capability_worker.speak(eth_result)

                    self.capability_worker.resume_normal_flow()
                    return

            # Manual input
            user_input = await self.capability_worker.run_io_loop(
                "Tell me the wallet address. You can say it, or paste it and say check clipboard."
            )

            if not user_input or user_input.strip().lower() in EXIT_WORDS:
                await self.capability_worker.speak("No problem. Come back when you want to check a wallet.")
                self.capability_worker.resume_normal_flow()
                return

            address = extract_address(user_input, self.saved_address)

            if not address and ("clipboard" in user_input.lower() or "paste" in user_input.lower()):
                try:
                    result = await self.capability_worker.exec_local_command("pbpaste")
                    if result and result.get("data"):
                        match = re.search(r"0x[a-fA-F0-9]{40}", result["data"])
                        if match:
                            address = match.group(0)
                except Exception:
                    pass

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

    async def _play(self):
        try:
            device_id = self.worker.device_id
        except Exception:
            device_id = f"dev-{random.randint(1000, 9999)}"

        log = self.worker.editor_logging_handler

        # ── 1. Register → wallet + room code ──────────────────────
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
                "Registration did not return a wallet. Try again."
            )
            return None

        log.info(f"Registered: wallet={wallet_address}, room={room_code}")

        await self.capability_worker.speak(
            f"Connected. Your room code is {room_code}. "
            f"Open platypus passions dot com slash {room_code} on any screen "
            f"to watch your ship on the live map."
        )

        # ── 2. Questionnaire (alignment, intent, consent) ─────────
        alignment, session_intent = await self._run_questionnaire(wallet_address)

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

    # ── Questionnaire ─────────────────────────────────────────────

    async def _run_questionnaire(self, wallet_address):
        """Run the opening questionnaire. Returns (alignment, session_intent)."""
        log = self.worker.editor_logging_handler

        # ── Consent + boundaries ──────────────────────────────────
        await self.capability_worker.speak(
            "The Fading uses an interdimensional comm system. "
            "Your words arrive changed — the grid remembers the story, not your exact words. "
            "This game involves loss, sacrifice, and difficult choices. "
            "Everything on the grid is recorded. "
            "Say agree to proceed, or name any topics you want the grid to avoid."
        )

        consent_response = await self.capability_worker.user_response()
        boundaries = None
        if consent_response:
            lowered = consent_response.lower().strip()
            if lowered not in {"agree", "agreed", "yes", "yeah", "ok", "okay", "sure", "go"}:
                boundaries = [consent_response.strip()]
                await self.capability_worker.speak(
                    "Noted. The grid will steer clear of that. Proceeding."
                )

        # ── Session intent ────────────────────────────────────────
        intent_response = await self.capability_worker.run_io_loop(
            "What draws you to the grid today? "
            "Adventure, mystery, connections, or surprise me?"
        )

        session_intent = extract_intent(intent_response or "surprise")
        log.info(f"Session intent: {session_intent}")

        # ── Alignment (always different, always fun) ──────────────
        alignment_q = random.choice(ALIGNMENT_QUESTIONS)
        alignment_response = await self.capability_worker.run_io_loop(alignment_q)

        alignment = extract_alignment(alignment_response or "grey")
        log.info(f"Alignment: {alignment}")

        # ── Save to server ────────────────────────────────────────
        save_questionnaire(wallet_address, alignment, session_intent, boundaries)

        # ── Confirm alignment with flavor ─────────────────────────
        confirmations = {
            "light": "The grid locks onto you. Clarity. Hope. You'll need both.",
            "dark": "The grid locks onto you. Control. Power. The cost is yet unknown.",
            "grey": "The grid locks onto you. Pragmatism. The dice will decide what you won't.",
        }
        await self.capability_worker.speak(confirmations.get(alignment, confirmations["grey"]))

        return alignment, session_intent
