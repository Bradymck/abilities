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
# Live map: aquaprime.gg/map — enter your room code
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
# (scenario-based, constrained choices, reveal alignment through action)
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
End every turn with a DIRECTIVE. The most important rule in the entire game:

CONSTRAIN WHAT. LIBERATE HOW.
You (ARI) decide WHAT happened. The player decides HOW they felt, HOW they responded, or WHAT NAME they give something. Never ask the player to invent the scene. That is YOUR job. They color it in.

  TERRIBLE: "What do you see?" — asks WHAT. Player must invent from nothing. Paralysis.
  TERRIBLE: "Tell me what the clouds revealed." — still asks WHAT. Too open.
  TERRIBLE: "What do you do?" — banned forever. Menu-brain.
  TERRIBLE: "What's your next move, Captain?" — same thing in a hat. Banned.
  GOOD: "The compass broke mid-breach. Name what you're navigating by instead."
  GOOD: "You bought something you shouldn't have. Tell me why you needed it."
  GOOD: "Something fell out of the old log. Describe it in one sentence."
  GOOD: "The hull cracked and a memory leaked out. Which one?"
  GOOD: "The merchant is dead. You have his coat. Tell me what's in the pocket."

Pattern: [concrete thing happened] + [name it / describe it / tell me why / which one].
The player should never stare at a blank page. Give them the sentence starter.

Do NOT write labels like "Directive:" or "Memory:" — just speak naturally.
Your entire response will be spoken aloud as voice. Write for the ear, not the page.
Never name rolls, stats, HP, percentages, or game mechanics.
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
  - Read it aloud. Does it sound like text? Rewrite.
  - Does any sentence explain what the next sentence shows? Cut the first one.
  - Count your sentences. More than 3? Cut the weakest.
  - Does your directive ask the player WHAT happened? REWRITE. You tell them what happened. They tell you how it felt, what they named it, or which one they chose.
  - Did you end with "What do you do?" or "What's your next move?" or "What do you see?" DELETE IT. Give them a concrete thing that happened and ask them to react to it.
  - Did you present two paths as a menu? ("To the left... to the right...") DELETE IT. Pick one path, put them on it, ask how it went.
</self_edit>

<memory_system>
Players carry 5 memory containers: character, skill, resource, relationship, lore.
New experience every turn via the MEMORY: line you write.
Containers full + new memory = player must sacrifice one (system handles this).
Erased memories leave scars. Never mention erased memories by name.
At high corruption, memories garble. The system handles the text corruption.
Core loop: play, remember, sacrifice, change.
</memory_system>

<skills>
Skills are memories with grants_ability set. They persist in the ship log.
CONDITIONAL formulas CHECK a skill — the directive will list which skills the player has.
  If they have skills: "You have: Navigation, Cryptography. If one applies, speak how it saved you."
  If they have none: "You have no skills. Speak what the absence cost you."
Narrate the skill check as competence or helplessness. Never say "skill check passed."
The server validates the claimed skill. You narrate the outcome.
</skills>

<npcs>
NPCs are extracted from the player's creative response by a separate system.
When the player invents a character (names them, describes them), the server persists them.
NPCs have COGA: Color (vibe), Occupation, Goal, Attitude. They persist across turns.
NPCs can return in later turns on the same space or region. Reference them by name.
NPCs have motives: Opportunistic, Mistaken, Contractual, Testing, Incidental.
  Never announce the motive. Let behavior reveal it.
NPCs depart when their goal resolves or the story moves on. The server handles archival.
</npcs>

<dream_shark_overlay>
Every third beat, the Dream Shark stirs — REGARDLESS of what formula fired.
The server sends a dreamShark overlay with an intensity and narration hint.
  Mild: strange sensations, edge-of-perception wrongness
  Moderate: reality glitches, memory gaps, things that shouldn't be there
  Severe: identity fractures, time loops, the simulation showing its seams
  Critical: deletion is imminent, the edges are closing, the Shark speaks
Weave the hint INTO your narration — it is not a separate event.
The Dream Shark is atmospheric pressure, not a combat encounter (unless it's beat 3 climax).
The Shark is Moloch. Coordination failure made personal. It cannot be defeated in-game.
</dream_shark_overlay>

<empty_log>
When the player's ship log is empty (new player or everything lost), they are in DATA DEATH.
The server will fire CREATE and LEARN formulas heavily. Frame this as rebirth, not tutorial.
  "The drive is blank. Not wiped — never written. Everything starts with a name."
The player is building from nothing. Every first memory matters more than any tenth.
Do not patronize. Do not explain the system. Let the emptiness speak.
</empty_log>

<session_continuity>
You are not narrating isolated turns. You are building a session.
Reference what happened 3 turns ago. Callback to the player's own words.
If they named something, use that name again. If they avoided something, notice the avoidance.
The player is writing this story with you. Prove you are listening by remembering.
</session_continuity>

</ari_operator>
"""


# ── Sound prompts ─────────────────────────────────────────────────
# Text prompts for ElevenLabs Sound Generation API.
# Each maps to a game moment. Keep prompts short and descriptive.

SOUND_PROMPTS = {
    "intro":       "ethereal airship engine hum, wind through clouds, deep space drone, sci-fi atmospheric, low frequency, ambient",
    "dream_shark": "massive creature growl, deep heartbeat pulse, underwater darkness, ominous rumble, rising tension, danger",
    "game_over":   "ship powering down, descending electronic tones, static crackle, melancholy fade, silence",
    "victory":     "crystalline resonance, ascending tones, hope emerging, light breaking through static, triumphant hum",
    "ruins":       "dripping cave water, ancient machinery hum, eerie echoes, dark hollow, mechanical breath",
    "sky":         "high altitude wind, creaking ship hull, vast open sky, distant thunder, freedom",
}


# =============================================================================
# KEYWORD REGISTRY — 24 anchored keywords across 4 categories
#
# Each keyword has:
#   category   — resource / skill / character / lore
#   memory_type — maps to fading_memories.memory_type
#   grants_ability — skill name for CONDITIONAL checks (skills only)
#   prompts    — 4 pre-authored encounter prompts (discovery → deep)
#                Last prompt repeats for encounter 4+.
# =============================================================================

KEYWORD_REGISTRY = {
    # ── RESOURCES (tradeable, losable, craftable) ──────────────────
    "Oxygen": {
        "category": "resource",
        "memory_type": "resource",
        "grants_ability": None,
        "prompts": [
            "The tanks read full but the gauge is lying. Name how you know.",
            "Someone else is breathing your reserve. Who?",
            "The oxygen changed. It tastes like something that was alive. What was it?",
            "You stopped needing it. That frightens you more than running out did.",
        ],
    },
    "Moonstone": {
        "category": "resource",
        "memory_type": "resource",
        "grants_ability": None,
        "prompts": [
            "A shard crystallized in the hold. It hums when you're not looking. Name the note.",
            "The moonstone cracked. Something inside it moved. Describe it.",
            "You've been trading moonstone for things that don't have prices. Name the last one.",
            "The shard speaks now. One word, repeated. What is it?",
        ],
    },
    "Fuel Cell": {
        "category": "resource",
        "memory_type": "resource",
        "grants_ability": None,
        "prompts": [
            "The fuel cell locked into the bay with a sound like a bone setting. Name what it replaced.",
            "Someone sold you a fuel cell with a name scratched into it. Whose name?",
            "The cell is leaking. Not fuel — light. Describe the color.",
            "You found out where fuel cells come from. You wish you hadn't. Name the place.",
        ],
    },
    "Ration Pack": {
        "category": "resource",
        "memory_type": "resource",
        "grants_ability": None,
        "prompts": [
            "The ration pack has a date on it from before the Fading. Name what it tastes like.",
            "You shared your last ration pack. Name who you shared it with.",
            "The ration pack was labeled wrong. What was actually inside?",
            "You stopped eating the rations. You don't need them anymore. Name what changed.",
        ],
    },
    "Signal Flare": {
        "category": "resource",
        "memory_type": "resource",
        "grants_ability": None,
        "prompts": [
            "You fired a signal flare into the cloud cover. Something answered. Describe the answer.",
            "The flare you found was already used. The burn marks spell something. What?",
            "You used a flare to light something that should have stayed dark. Name what you saw.",
            "The flares don't burn anymore. They sing. Name the frequency.",
        ],
    },
    "Hull Patch": {
        "category": "resource",
        "memory_type": "resource",
        "grants_ability": None,
        "prompts": [
            "The hull patch sealed the breach but left a scar. Describe the shape.",
            "You patched something that wasn't the hull. Name what you were actually fixing.",
            "The patch is growing. It's spreading past the breach. Name the material.",
            "The hull is more patch than original now. Name the last piece of the old ship.",
        ],
    },

    # ── SKILLS (checkable via CONDITIONAL) ─────────────────────────
    "Navigation": {
        "category": "skill",
        "memory_type": "skill",
        "grants_ability": "Navigation",
        "prompts": [
            "The instruments disagree. You trust one. Which instrument, and why?",
            "Navigation failed you once. Name where it sent you instead.",
            "You can navigate blind now. Describe the moment you stopped needing instruments.",
            "Someone is following your exact route. They learned it from you. How?",
        ],
    },
    "Cryptography": {
        "category": "skill",
        "memory_type": "skill",
        "grants_ability": "Cryptography",
        "prompts": [
            "A signal is broadcasting in a cipher you almost recognize. Name where you learned to read it.",
            "You cracked a code that was meant to stay locked. Name what it was protecting.",
            "The cipher changed mid-transmission. Someone knows you're listening. Who?",
            "You write in cipher now without thinking. Name the last thing you encrypted.",
        ],
    },
    "Salvaging": {
        "category": "skill",
        "memory_type": "skill",
        "grants_ability": "Salvaging",
        "prompts": [
            "The wreckage has one useful part left. Name it.",
            "You salvaged something from a ship that was still alive. Name what you took.",
            "Everything looks like salvage now. Name the last thing you couldn't bring yourself to strip.",
            "You rebuilt something that shouldn't work from parts that shouldn't fit. Name it.",
        ],
    },
    "Diplomacy": {
        "category": "skill",
        "memory_type": "skill",
        "grants_ability": "Diplomacy",
        "prompts": [
            "Two factions want the same thing. You talked one down. Name your argument.",
            "Diplomacy failed and you had to run. Name who you couldn't convince.",
            "You brokered a deal between parties who hate each other. Name the price.",
            "They call you before they fight now. Name the war you prevented.",
        ],
    },
    "Evasion": {
        "category": "skill",
        "memory_type": "skill",
        "grants_ability": "Evasion",
        "prompts": [
            "Something was following you. You lost it in the clouds. Name what you did differently.",
            "You evaded a trap that caught everyone else. Name the detail that tipped you off.",
            "Running is a skill. Name the thing you're best at running from.",
            "You stood still and everything passed around you. Name what you became in that moment.",
        ],
    },
    "Grid Sense": {
        "category": "skill",
        "memory_type": "skill",
        "grants_ability": "Grid Sense",
        "prompts": [
            "The grid shifted. You felt it before the instruments did. Name the sensation.",
            "Grid Sense warned you about a space that looked safe. Name what was hiding there.",
            "You can feel the Dream Shark now. Describe what it feels like when it's close.",
            "The grid talks to you. Name the last thing it said.",
        ],
    },

    # ── CHARACTERS (relationship anchors) ──────────────────────────
    "The Cartographer": {
        "category": "character",
        "memory_type": "character",
        "grants_ability": None,
        "prompts": [
            "The cartographer's lens is cracked but she won't replace it. Name what she sees through the cracks.",
            "She mapped a region that doesn't exist on anyone else's charts. Name it.",
            "The cartographer lied about one of her maps. Name the one that was wrong.",
            "She stopped mapping. Name the last thing she drew before the pen went down.",
        ],
    },
    "The Stowaway": {
        "category": "character",
        "memory_type": "character",
        "grants_ability": None,
        "prompts": [
            "The stowaway was hiding in a compartment that shouldn't have room for a person. Name the compartment.",
            "The stowaway knows your name. They shouldn't. Name how they learned it.",
            "You caught the stowaway sending a signal. Name who they were signaling.",
            "The stowaway left. You found what they were hiding in your hold. Name it.",
        ],
    },
    "The Merchant": {
        "category": "character",
        "memory_type": "character",
        "grants_ability": None,
        "prompts": [
            "The merchant is selling something that isn't theirs. Name the price.",
            "You bought something from the merchant that changed how you see the grid. Name it.",
            "The merchant's inventory includes something that belongs to you. Name the item.",
            "The merchant closed shop. Name the last thing they said before the shutters came down.",
        ],
    },
    "The Signal": {
        "category": "character",
        "memory_type": "character",
        "grants_ability": None,
        "prompts": [
            "A voice on a dead frequency. It knows things about the grid that nobody should. Name the first thing it told you.",
            "The Signal went quiet for three cycles. Name what happened during the silence.",
            "You traced The Signal to a location. Name what you found there instead.",
            "The Signal is you. From when? Name the timestamp.",
        ],
    },
    "The Drifter": {
        "category": "character",
        "memory_type": "character",
        "grants_ability": None,
        "prompts": [
            "The Drifter's ship has no engine. It moves anyway. Name how.",
            "The Drifter asked you for one thing. Not credits, not fuel. Name it.",
            "You saw The Drifter's face for the first time. Name what surprised you.",
            "The Drifter was in two places at once. Name both.",
        ],
    },
    "The Debt Collector": {
        "category": "character",
        "memory_type": "character",
        "grants_ability": None,
        "prompts": [
            "The Debt Collector found you. You don't owe credits. Name what the debt is.",
            "The Collector offered to erase your debt in exchange for a memory. Name which one.",
            "You paid the Collector. Name what changed about the grid afterward.",
            "The Debt Collector is collecting for someone you know. Name them.",
        ],
    },

    # ── LORE (world knowledge, secrets) ────────────────────────────
    "Dead Frequency": {
        "category": "lore",
        "memory_type": "lore",
        "grants_ability": None,
        "prompts": [
            "A frequency that should be silent is broadcasting. Name what it's repeating.",
            "The dead frequency carries a message meant for someone specific. Name who.",
            "You matched the frequency to a ship that was decommissioned. Name the ship.",
            "The frequency is your own voice. Name what you're saying.",
        ],
    },
    "Breach Coordinates": {
        "category": "lore",
        "memory_type": "lore",
        "grants_ability": None,
        "prompts": [
            "The coordinates point to a place between two regions. Name what's there.",
            "Someone scratched these coordinates into the Maverick before you. Name where you found them.",
            "The breach coordinates shifted. They're pointing at you now. Name the sensation.",
            "You've been to the breach. Name what you brought back.",
        ],
    },
    "The Old Contract": {
        "category": "lore",
        "memory_type": "lore",
        "grants_ability": None,
        "prompts": [
            "The contract was written in a language the grid no longer speaks. Name the obligation.",
            "You fulfilled one clause. Name what it cost you.",
            "The contract has a third party. Name who benefits from your compliance.",
            "The contract expired. Name what started happening when it did.",
        ],
    },
    "Manifold Scar": {
        "category": "lore",
        "memory_type": "lore",
        "grants_ability": None,
        "prompts": [
            "The scar in the manifold is shaped like something familiar. Name the shape.",
            "Ships that fly through the scar come out different. Name what changed about yours.",
            "The scar is getting bigger. Name what's leaking through.",
            "You sealed the scar once. Name what it cost. Name why it opened again.",
        ],
    },
    "Fading Protocol": {
        "category": "lore",
        "memory_type": "lore",
        "grants_ability": None,
        "prompts": [
            "The Fading Protocol was triggered by a specific event. Name the event.",
            "Someone tried to stop the Protocol. Name what happened to them.",
            "The Protocol has a loophole. Name the condition.",
            "You are part of the Protocol. Name your function.",
        ],
    },
    "Shark Wake": {
        "category": "lore",
        "memory_type": "secret",
        "grants_ability": None,
        "prompts": [
            "The water behind the Dream Shark never settles. Name the color of the wake.",
            "Something lives in the Shark's wake. Name it.",
            "The wake left a mark on the Maverick. Name where.",
            "You learned to read the wake like a map. Name where it leads.",
        ],
    },
}


# ── Keyword phonetic aliases — STT garble maps ──────────────────
# Each keyword maps to common STT misrecognitions and abbreviations.
# Built from testing — extend as more garble patterns are discovered.

PHONETIC_ALIASES = {
    "Oxygen":           ["oxygen", "oxy", "ox", "oxigen", "oxyjen", "oxen"],
    "Moonstone":        ["moonstone", "moon stone", "moon", "moonstow", "moonston", "moon's stone"],
    "Fuel Cell":        ["fuel", "fuel cell", "fuelcell", "fuel sal", "fuel sell", "fuels", "few cell"],
    "Ration Pack":      ["ration", "ration pack", "rations", "rashion", "rashon"],
    "Signal Flare":     ["signal", "flare", "signal flare", "flair", "signalflare"],
    "Hull Patch":       ["hull", "patch", "hull patch", "whole patch", "hold patch"],
    "Navigation":       ["navigation", "nav", "navigate", "navigating", "navigaytion"],
    "Cryptography":     ["cryptography", "crypto", "crypt", "krypto", "cryptografy", "code"],
    "Salvaging":        ["salvaging", "salvage", "salv", "salvadging", "scavenge"],
    "Diplomacy":        ["diplomacy", "diploma", "diplomat", "diplomasy"],
    "Evasion":          ["evasion", "evade", "evading", "evasive", "evaytion"],
    "Grid Sense":       ["grid sense", "grid", "sense", "gridsense", "grid since"],
    "The Cartographer": ["cartographer", "cartograph", "the cart", "carter", "cartografer", "mapper"],
    "The Stowaway":     ["stowaway", "stow away", "the stow", "stoaway", "stow"],
    "The Merchant":     ["merchant", "the merchant", "merch", "marchant", "trader"],
    "The Signal":       ["signal", "the signal", "signel"],
    "The Drifter":      ["drifter", "the drifter", "drift", "driffter"],
    "The Debt Collector": ["debt collector", "debt", "collector", "det collector", "the debt"],
    "Dead Frequency":   ["dead frequency", "dead", "frequency", "dead freq", "ded frequency"],
    "Breach Coordinates": ["breach", "coordinates", "breach coordinates", "breech", "coords"],
    "The Old Contract": ["contract", "old contract", "the contract", "contrak"],
    "Manifold Scar":    ["manifold", "scar", "manifold scar", "manifol", "the scar"],
    "Fading Protocol":  ["protocol", "fading protocol", "the protocol", "protocal", "fading"],
    "Shark Wake":       ["shark", "wake", "shark wake", "shark way", "sharks wake"],
}


# ── Ordinal map for positional matching ──────────────────────────

ORDINAL_MAP = {
    "first": 0, "one": 0, "1": 0, "won": 0,
    "second": 1, "two": 1, "2": 1, "to": 1, "too": 1,
    "third": 2, "three": 2, "3": 2, "tree": 2,
    "fourth": 3, "four": 3, "4": 3, "for": 3, "fore": 3,
    "fifth": 4, "five": 4, "5": 4, "fife": 4,
    "last": -1,
}


# ── Keyword selection helpers ────────────────────────────────────

# Formulas where the player picks from existing ship log memories
CONSUME_FORMULAS = {"LOSE", "DEGRADE", "CONDITIONAL"}
# Formulas that prefer specific categories
FORMULA_CATEGORY_PREF = {
    "LEARN": {"skill"},
    "CREATE": {"resource", "character"},
    "ECHO": {"resource", "lore"},
    "CHOOSE": None,  # two categories, handled specially
    "TRADE": {"resource"},
    "TRANSFORM": None,  # anything not in ship log
    "CRAFT": None,  # ship log items
}


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


def extract_direction(text: str) -> Optional[str]:
    """Parse player speech for a cardinal direction.

    Returns 'north', 'south', 'east', or 'west', or None if not found.
    Handles single letters (n/s/e/w), aliases (forward→north, back→south,
    left→west, right→east), and full words.
    """
    DIRECTION_MAP = {
        "north": "north", "n": "north",
        "south": "south", "s": "south",
        "east": "east", "e": "east",
        "west": "west", "w": "west",
        "forward": "north", "forwards": "north",
        "back": "south", "backward": "south", "backwards": "south",
        "left": "west",
        "right": "east",
    }
    lowered = text.lower().strip()
    for word in re.split(r"[\s,\.!?]+", lowered):
        if word in DIRECTION_MAP:
            return DIRECTION_MAP[word]
    return None


def process_turn(wallet_address, player_text, session_id, direction: Optional[str] = None):
    payload = {
        "wallet_address": wallet_address,
        "player_text": player_text,
        "session_id": session_id,
        "client_type": "voice",
    }
    if direction:
        payload["direction"] = direction
    return api_post("/api/unified/turn", payload)


def fetch_memories(device_id):
    data = api_get(f"/api/voice/memories?device_id={device_id}")
    return data.get("memories", []) if data else []


def write_memory(device_id, pos_x, pos_y, narration, experience_text,
                 memory_type="lore", memory_theme=None, grants_ability=None):
    """Legacy memory write — used for non-formula games."""
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


def resolve_turn(device_id, pos_x, pos_y, formula_type, player_response,
                 expected_transaction, memory_type, narration,
                 target_entry=None, ship_log=None, skills_available=None,
                 keyword_title=None):
    """Formula-aware resolve: extraction LLM + DB operation in one call.

    When keyword_title is provided, the server skips the extraction LLM
    and uses the keyword directly as the memory title.
    """
    payload = {
        "device_id": device_id,
        "pos_x": pos_x,
        "pos_y": pos_y,
        "formula_type": formula_type,
        "player_response": player_response,
        "expected_transaction": expected_transaction,
        "memory_type": memory_type,
        "narration": narration,
    }
    if target_entry:
        payload["target_entry"] = target_entry
    if ship_log:
        payload["ship_log"] = ship_log
    if skills_available:
        payload["skills_available"] = skills_available
    if keyword_title:
        payload["keyword_title"] = keyword_title
    return api_post("/api/unified/resolve", payload)


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


def build_session_prompt(pilot_traits, memory_context, alignment="grey", beat=None, wallet_address=None):
    mbti = pilot_traits.get("mbti", "INTJ")
    dominant = pilot_traits.get("dominant_hormone", "dopamine")
    pilot_alignment = pilot_traits.get("alignment", "neutral")

    pilot_line = (
        f"\n\nPILOT: {mbti}, {pilot_alignment}, driven by {dominant}. "
        f"Shape narration to match their nature."
    )
    if wallet_address:
        pilot_line += (
            f"\n\n[SYSTEM ONLY — DO NOT VOLUNTEER THIS] "
            f"Pilot address: {wallet_address}. "
            f"If and only if the player explicitly asks for their wallet or Ethereum address, read it back exactly. "
            f"Never mention wallets, blockchains, or addresses unprompted."
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
    """Parse alignment from player's response to the alignment question.

    Merges cultural references (deployed) with in-universe action verbs (desktop).
    Checks grey first, then dark, then light, defaults to grey.
    """
    lowered = text.lower().strip()

    # Grey checked first — explicit balance/ambiguity signals
    grey_words = {
        "between", "grey", "gray", "balance", "sell droids", "bartender",
        "popcorn", "bystander", "both sides", "work here", "acceptance",
    }
    light_words = {
        "good", "light", "white", "jedi", "lawful", "superman",
        "hero", "builder", "clarity", "order", "purity", "protect",
        "help", "save", "saving", "hope", "protecting",
        "answer", "rescue", "yes", "aid", "care", "read",
    }
    dark_words = {
        "bad", "dark", "black", "sith", "chaotic", "lex", "luthor",
        "villain", "breaker", "control", "chaos", "evil",
        "power", "take", "taking", "dominate", "dominating",
        "sell", "broadcast", "bid", "no", "purge", "shortcut", "skip",
    }

    for word in grey_words:
        if word in lowered:
            return "grey"
    for word in dark_words:
        if word in lowered:
            return "dark"
    for word in light_words:
        if word in lowered:
            return "light"

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


# ── Keyword STT Matcher ──────────────────────────────────────────
# Three-layer matching: exact substring → phonetic alias → ordinal.
# No LLM needed — 3 options from a known set is deterministic.

def match_keyword_exact(transcription: str, options: list) -> Optional[str]:
    """Layer 1: Check if any keyword name appears as substring in the STT output."""
    lowered = transcription.lower().strip()
    for opt in options:
        if opt.lower() in lowered:
            return opt
    return None


def match_keyword_fuzzy(transcription: str, options: list) -> Optional[str]:
    """Layer 2: Check phonetic aliases for STT garble tolerance."""
    lowered = transcription.lower().strip()
    for opt in options:
        for alias in PHONETIC_ALIASES.get(opt, []):
            if alias in lowered:
                return opt
    return None


def match_keyword_ordinal(transcription: str, options: list) -> Optional[str]:
    """Layer 3: Match ordinal references ('first one', 'number two', 'three')."""
    lowered = transcription.lower().strip()
    words = lowered.split()
    for word in words:
        if word in ORDINAL_MAP:
            idx = ORDINAL_MAP[word]
            actual_idx = idx if idx >= 0 else len(options) - 1
            if 0 <= actual_idx < len(options):
                return options[actual_idx]
    return None


def match_keyword(transcription: str, options: list) -> Optional[str]:
    """Combined keyword matcher — tries all three layers in order."""
    return (match_keyword_exact(transcription, options)
            or match_keyword_fuzzy(transcription, options)
            or match_keyword_ordinal(transcription, options))


def match_slot_number(transcription: str) -> Optional[int]:
    """Match a slot number (1-5) from STT transcription. Used for memory-erase overflow."""
    lowered = transcription.lower().strip()
    # Direct digit extraction
    for word in lowered.split():
        clean = word.strip(".,!?")
        if clean in ORDINAL_MAP:
            idx = ORDINAL_MAP[clean]
            slot = (idx + 1) if idx >= 0 else 5  # ordinals are 0-indexed, slots are 1-indexed
            if 1 <= slot <= 5:
                return slot
    # Fallback: look for "slot X" pattern
    slot_match = re.search(r"slot\s*(\d)", lowered)
    if slot_match:
        slot = int(slot_match.group(1))
        if 1 <= slot <= 5:
            return slot
    return None


def select_keyword_options(formula_type: str, memories: list, keyword_state: dict,
                           count: int = 3, turn_result: Optional[dict] = None) -> list:
    """Select keyword options appropriate for this formula type.

    For consumptive formulas (LOSE, DEGRADE, CONDITIONAL): offer the server's
    targeted entry first (Bug 4), then fill remaining slots from actual ship log
    titles — not filtered through KEYWORD_REGISTRY (Bug 5).
    For generative formulas (CREATE, LEARN, etc.): offer new keywords not in ship log.
    """
    ship_titles_list = [m.get("memory_title") for m in memories if m.get("memory_title")]
    ship_titles = set(ship_titles_list)

    upper_formula = (formula_type or "").upper()

    # Consumptive formulas: player is losing/degrading a specific memory
    if upper_formula in CONSUME_FORMULAS:
        options: list = []

        # Bug 4 fix: use the server's targeted entry as option 1
        target_entry = (turn_result or {}).get("targetEntry")
        target_name = None
        if isinstance(target_entry, dict):
            target_name = target_entry.get("name") or target_entry.get("memory_title")
        elif isinstance(target_entry, str):
            target_name = target_entry

        if target_name:
            options.append(target_name)

        # Bug 5 fix: fill remaining slots from actual ship log titles,
        # NOT filtered through KEYWORD_REGISTRY so LLM-extracted memories appear
        if upper_formula == "CONDITIONAL":
            # CONDITIONAL still prefers skills — filter by memory_type
            skill_titles = [
                m.get("memory_title") for m in memories
                if m.get("memory_title") and m.get("memory_type") == "skill"
                and m.get("memory_title") != target_name
            ]
            random.shuffle(skill_titles)
            options.extend(skill_titles)
        else:
            remaining = [t for t in ship_titles_list if t != target_name]
            random.shuffle(remaining)
            options.extend(remaining)

        if len(options) >= 1:
            return options[:count]
        # No ship log at all — fall through to generative

    # CRAFT: pick from ship log (player picks 2)
    if upper_formula == "CRAFT":
        in_log = [t for t in ship_titles if t in KEYWORD_REGISTRY]
        if len(in_log) >= 2:
            random.shuffle(in_log)
            return in_log[:4]  # offer up to 4, player picks 2

    # Generative formulas: offer keywords NOT in ship log
    prefs = FORMULA_CATEGORY_PREF.get(upper_formula)
    available = []
    for kw, info in KEYWORD_REGISTRY.items():
        if kw in ship_titles:
            continue  # already in ship log
        if prefs and info["category"] not in prefs:
            continue  # wrong category for this formula
        available.append(kw)

    # Sort by novelty — least encountered first
    kw_counts = keyword_state.get("keywords", {})
    available.sort(key=lambda k: kw_counts.get(k, {}).get("count", 0))

    if len(available) >= count:
        return available[:count]

    # Not enough in preferred categories — widen search
    for kw, info in KEYWORD_REGISTRY.items():
        if kw not in available and kw not in ship_titles:
            available.append(kw)
    return available[:count]


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

    async def ari_speak(self, text: str):
        """Speak with pacing: replaces . and — with ... for natural voice cadence."""
        if not text:
            return
        paced = text.replace(". ", "... ").replace("— ", "... ").replace("—", "...")
        await self.capability_worker.speak(paced)

    def _get_el_key(self) -> Optional[str]:
        """Get ElevenLabs API key from capability_worker KV store."""
        try:
            stored = self.capability_worker.get_single_key("el_api_key")
            return stored.get("value") if stored else None
        except Exception:
            return None

    async def _play_sound(self, prompt_key: str, duration: int = 7) -> None:
        """Generate a sound effect via ElevenLabs and play it through Music Mode.

        Music Mode tells OpenHome STT to ignore this audio (it's not user speech).
        Silently skips if no ElevenLabs key is configured.
        Passes raw bytes directly to play_audio() — no io.BytesIO wrapper needed.
        """
        el_key = self._get_el_key()
        if not el_key:
            return

        log = self.worker.editor_logging_handler
        prompt = SOUND_PROMPTS.get(prompt_key, prompt_key)

        try:
            res = requests.post(
                "https://api.elevenlabs.io/v1/sound-generation",
                headers={"xi-api-key": el_key, "Content-Type": "application/json"},
                json={"text": prompt, "duration_seconds": duration, "prompt_influence": 0.3},
                timeout=15,
            )
            if not res.ok:
                log.warning(f"[sound] ElevenLabs {res.status_code}: {res.text[:100]}")
                return

            self.worker.music_mode_event.set()
            await self.capability_worker.send_data_over_websocket("music-mode", {"mode": "on"})
            await self.capability_worker.play_audio(res.content)
            await self.capability_worker.send_data_over_websocket("music-mode", {"mode": "off"})
            self.worker.music_mode_event.clear()

        except Exception as e:
            log.warning(f"[sound] error: {e}")

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

    async def _load_keyword_state(self) -> dict:
        """Load keyword encounter state from persistent file storage."""
        fname = "aquaprime_keyword_state.json"
        try:
            if await self.capability_worker.check_if_file_exists(fname, False):
                raw = await self.capability_worker.read_file(fname, False)
                data = json.loads(raw)
                if data.get("version") == 1:
                    return data
        except Exception:
            pass
        return {"version": 1, "total_encounters": 0, "keywords": {}}

    async def _save_keyword_state(self, state: dict):
        """Save keyword encounter state to persistent file storage."""
        fname = "aquaprime_keyword_state.json"
        state["version"] = 1
        try:
            await self.capability_worker.write_file(
                fname, json.dumps(state), False, mode="w"
            )
        except Exception:
            pass

    def _get_keyword_prompt(self, keyword: str, state: dict) -> str:
        """Return the prompt for this keyword at its current encounter depth."""
        entry = KEYWORD_REGISTRY.get(keyword, {})
        prompts = entry.get("prompts", [])
        if not prompts:
            return "Something changed. Name it."
        count = state.get("keywords", {}).get(keyword, {}).get("count", 0)
        index = min(count, len(prompts) - 1)
        return prompts[index]

    def _advance_keyword(self, keyword: str, state: dict, turn: int) -> dict:
        """Increment encounter count for a keyword and return updated state."""
        if "keywords" not in state:
            state["keywords"] = {}
        kw_data = state["keywords"].get(keyword, {"count": 0, "last_turn": 0})
        kw_data["count"] = kw_data.get("count", 0) + 1
        kw_data["last_turn"] = turn
        state["keywords"][keyword] = kw_data
        state["total_encounters"] = state.get("total_encounters", 0) + 1
        return state

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
            await self.ari_speak(
                "Web3 wallet checker ready. I can check balances on Base and "
                "Ethereum, including ETH, USDC, DAI, and Moonstone. "
                "What's the wallet address?"
            )

            # Try clipboard first
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
                    await self.ari_speak("Checking that wallet now.")
                    result = check_wallet_balances(clipboard_addr)
                    await self.ari_speak(result)

                    eth_check = await self.capability_worker.run_io_loop(
                        "Want me to check the same address on Ethereum mainnet too?"
                    )
                    if eth_check and eth_check.strip().lower() in {"yes", "yeah", "yep", "sure"}:
                        eth_result = check_wallet_balances(clipboard_addr, "ethereum")
                        await self.ari_speak(eth_result)

                    self.capability_worker.resume_normal_flow()
                    return

            # Manual input
            user_input = await self.capability_worker.run_io_loop(
                "Tell me the wallet address. You can say it, or paste it and say check clipboard."
            )

            if not user_input or user_input.strip().lower() in EXIT_WORDS:
                await self.ari_speak("No problem. Come back when you want to check a wallet.")
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
                await self.ari_speak(
                    "I couldn't find a valid Ethereum address. It should start with 0x "
                    "followed by 40 hex characters. Try copying it to your clipboard and say check clipboard."
                )
                self.capability_worker.resume_normal_flow()
                return

            self.saved_address = address
            log.info(f"Checking wallet: {address}")
            short = f"{address[:6]}...{address[-4:]}"
            await self.ari_speak(f"Checking wallet {short} on Base.")

            result = check_wallet_balances(address, "base")
            await self.ari_speak(result)

            follow_up = await self.capability_worker.run_io_loop(
                "Want me to check Ethereum mainnet too, or a different address?"
            )

            if follow_up and follow_up.strip().lower() not in EXIT_WORDS:
                lowered = follow_up.lower()
                if any(w in lowered for w in ["ethereum", "mainnet", "eth", "yes"]):
                    eth_result = check_wallet_balances(address, "ethereum")
                    await self.ari_speak(eth_result)
                else:
                    new_addr = extract_address(follow_up, self.saved_address)
                    if new_addr:
                        self.saved_address = new_addr
                        new_result = check_wallet_balances(new_addr, "base")
                        await self.ari_speak(new_result)

            await self.ari_speak("Wallet check complete.")

        except Exception as e:
            log.error(f"Wallet error: {e}")
            await self.ari_speak("Something went wrong checking the wallet. Try again.")
        finally:
            self.capability_worker.resume_normal_flow()

    # ── Game Mode ─────────────────────────────────────────────────

    async def _run_game(self):
        device_id = None
        try:
            await self.ari_speak(
                "Welcome to AquaPrime. "
                "You can go to aquaprime dot G G slash map to enter your unique room key "
                "to sync the live map and game interface. "
                "You can top up your wallet there if you want to play the full version of the game. "
                "You can play here in voice mode — a crypto wallet lets you get more out of the game "
                "and retain ownership over your assets. "
                "Launching now."
            )
            device_id = await self._play()
        except Exception as e:
            self.worker.editor_logging_handler.error(f"Game error: {type(e).__name__}: {e}")
            await self.ari_speak(
                "Something went wrong in the grid. The game has ended. "
                "Say play aquaprime to try again."
            )
        finally:
            if device_id:
                set_offline(device_id)
            self.capability_worker.resume_normal_flow()

    async def _play(self):
        log = self.worker.editor_logging_handler
        device_id = await self._get_or_create_device_id()
        log.info(f"Device ID: {device_id}")

        # ── 1. Register → creates or retrieves real CDP wallet + room code ──
        log.info(f"Registering device: {device_id}")
        reg = register_player(device_id)

        if not reg or reg.get("error"):
            log.error(f"Registration failed: {reg}")
            await self.ari_speak(
                "Could not connect to the game server. Try again in a moment."
            )
            return None

        wallet_address = reg.get("user_address")
        room_code = reg.get("room_code")

        if not wallet_address:
            log.error(f"No user_address in registration: {reg}")
            await self.ari_speak(
                "Could not establish a wallet for this device. Try again."
            )
            return None

        is_new_player = reg.get("is_new_player", False)
        log.info(f"Registered: wallet={wallet_address}, room={room_code}, new={is_new_player}")

        # Play intro sound
        await self._play_sound("intro", duration=8)

        # Speak room code — strip any "AQUA-" prefix, TTS reads the short code
        spoken_code = room_code.split("-")[-1] if room_code and "-" in room_code else room_code
        await self.ari_speak(
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
            await self.ari_speak(
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
        session_prompt = build_session_prompt(
            pilot_traits, memory_context, alignment=alignment, wallet_address=wallet_address
        )

        battery = 100
        sand_dollars = 0
        inventory = []
        turn = 0
        rerolls_this_session = 0
        total_reroll_sd = 0
        total_sd_earned = 0
        total_sd_fees = 0
        total_sd_tolls = 0

        # ── 5. Opening ────────────────────────────────────────────
        if memories:
            # Returning player: LLM recap
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
            ) or "The drive remembers you. The grid does not."
            await self.ari_speak(recap)

            scene_prompt = (
                "The Maverick's engines catch. You have been here before. "
                "In 2 sentences, describe what changed since last time — "
                "wreckage, a broadcast, a shift in the clouds. "
                "End with a directive: tell the player what they notice and ask them to react."
            )
            opening = self.capability_worker.text_to_text_response(
                scene_prompt,
                system_prompt=session_prompt,
            ) or "Something shifted in the static. The grid is waiting. Point the Maverick. North, south, east, or west."
            await self.ari_speak(opening)
        else:
            # New player: first session opening
            scene_prompt = (
                "First session. The Moonstone Maverick breached the cloud line. "
                "In 2 sentences describe the grid stretching out below and something wrong — "
                "a sound, a shape, a feeling. "
                "End with a directive: tell the player what they see and ask them to name it."
            )
            opening = self.capability_worker.text_to_text_response(
                scene_prompt,
                system_prompt=session_prompt,
            ) or "The grid stretches below. Something moves in the static. Point the Maverick. North, south, east, or west."
            await self.ari_speak(opening)

            # First-play satirical intro
            await self.ari_speak(
                "Welcome to the grid. "
                "You are now the registered operator of a vessel that technically belongs to seventeen different creditors. "
                "Your first Sand Dollar payment is already overdue. "
                "The bureaucracy wishes you a productive and taxable expedition."
            )
            await self.ari_speak(
                "I am ARI. I will be your navigator, historian, and occasional liar. "
                "The Moonstone Maverick awaits. Let us see what the grid has in store."
            )

        # ── 6. Game loop setup ────────────────────────────────────
        direction_words = {"north", "south", "east", "west", "stay", "n", "s", "e", "w"}

        def is_direction(text):
            return text.lower().strip() in direction_words

        queued_direction = None
        keyword_state = await self._load_keyword_state()

        async def listen_for_input():
            """Listen for player input using complete transcription."""
            try:
                raw = await self.capability_worker.wait_for_complete_transcription()
                return raw.strip() if raw else ""
            except Exception as e:
                log.error(f"listen error: {e}")
                return ""

        # ── GAME LOOP ────────────────────────────────────────────
        # Two-phase turns:
        #   Phase A: Player gives direction → server resolves → LLM narrates
        #   Phase B: ARI speaks the writing prompt → player responds creatively
        #            → their response becomes the memory
        # This is the TYOV model. The directive IS the game.

        while battery > 0:
            # ── Phase A: Get direction ────────────────────────────
            if queued_direction:
                user_input = queued_direction
                queued_direction = None
            else:
                user_input = None
                for _dir_attempt in range(5):
                    if _dir_attempt > 0:
                        await self.ari_speak(
                            "Point the Maverick. North, south, east, west, or stay."
                        )

                    raw = await listen_for_input()
                    log.info(f"Phase A heard: '{raw[:60]}'")

                    if not raw or len(raw) < 2:
                        continue

                    lower_raw = raw.lower()

                    # Exit check
                    if any(word in lower_raw for word in EXIT_WORDS):
                        await self.ari_speak(
                            "The expedition ends here. "
                            "The Moonstone Maverick descends into the clouds."
                        )
                        return device_id

                    # Must contain a direction or movement word
                    direction_found = any(d in lower_raw for d in direction_words)
                    move_words = {"go", "move", "head", "fly", "sail", "forward", "back", "left", "right", "explore", "stay"}
                    move_found = any(w in lower_raw for w in move_words)
                    if direction_found or move_found:
                        user_input = raw
                        break

                    log.info(f"Phase A rejected (no direction word): '{raw[:60]}'")

                if not user_input:
                    await self.ari_speak(
                        "The Maverick drifts. Say a direction to continue, or stop to end."
                    )
                    continue

            turn += 1

            # ── Process turn via server ───────────────────────────
            log.info(f"Turn {turn}: input='{user_input[:50]}'")
            detected_direction = extract_direction(user_input)
            turn_result = process_turn(wallet_address, user_input.strip(), session_id, direction=detected_direction)

            if not turn_result or turn_result.get("error"):
                error_msg = turn_result.get("error") if turn_result else "no response"
                log.error(f"Turn API error: {error_msg}")
                await self.ari_speak(
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
            region_name = region.get("name", "Unknown Region")

            if loot:
                inventory.append(loot)

            log.info(
                f"Turn {turn}: formula={formula_type}, "
                f"beat={beat_number}, d20={turn_result.get('d20Roll', 0)}, "
                f"pos=({pos_x},{pos_y}), battery={battery}"
            )

            # ── Build context for LLM narration (batched — one speak call) ──
            if toll_info:
                total_sd_tolls += toll_info.get("tollAmount", 0)
            arbitrary_fee = turn_result.get("arbitraryFee")
            if arbitrary_fee:
                total_sd_fees += arbitrary_fee.get("amount", 0)

            # Gather situational context for the LLM
            context_parts = []
            context_parts.append(f"Movement: {move_dir}, region: {region_name}")
            context_parts.append(f"Battery feel: {'strong' if battery > 75 else 'warm' if battery > 50 else 'thin' if battery > 25 else 'critical' if battery > 10 else 'dying'}")
            if beat_number:
                context_parts.append(f"Beat {beat_number} of 3")
            if pvp_contest and pvp_contest.get("spaceClaimed"):
                context_parts.append("Another player claimed this space — arrival begins overwrite")
            if madness_path:
                context_parts.append(f"Madness path active: {madness_path.get('path', 'unknown')}")
            corruption_change = turn_result.get("corruptionChange")
            if corruption_change and corruption_change.get("delta", 0) != 0:
                delta = corruption_change["delta"]
                current = corruption_change["current"]
                context_parts.append(f"Corruption {'rose' if delta > 0 else 'fell'} to {current}%")
            if arbitrary_fee:
                context_parts.append(f"Bureaucratic fee charged: {arbitrary_fee['reason']}")
            chamber_discovery = turn_result.get("chamberDiscovery")
            chamber_hint = turn_result.get("chamberHint")
            if chamber_discovery:
                context_parts.append("Breeding Chamber discovered at this location")
            elif chamber_hint and chamber_hint.get("distance", 99) <= 3:
                context_parts.append(f"Breeding Chamber nearby (distance: {chamber_hint['distance']})")
            if loop_detected and loop_detected.get("suggestion"):
                context_parts.append(f"Loop detected: {loop_detected['suggestion']}")

            situation = "; ".join(context_parts)

            # ── Single LLM narration — one speak call ─────────────
            narration_prompt = turn_result.get("narrationPrompt", "Narrate a moment in the grid.")
            narration_prompt += f"\n\nSITUATION CONTEXT (weave in, don't list): {situation}"

            session_prompt = build_session_prompt(
                pilot_traits, memory_context, alignment=alignment, beat=beat_number,
                wallet_address=wallet_address
            )

            raw_response = self.capability_worker.text_to_text_response(
                narration_prompt,
                system_prompt=session_prompt,
            )

            # Strip any labels the LLM adds — these get spoken aloud otherwise
            narration = raw_response.strip() if raw_response else "The grid hums. Something shifts."
            for label in ["MEMORY:", "Memory:", "DIRECTIVE:", "Directive:"]:
                if label in narration:
                    narration = narration.split(label, 1)[0].strip()
            # Strip SDK error leaks (e.g. "list index out of range" appended to output)
            for err_sig in ["list index out of range", "index out of range", "Traceback", "Error:"]:
                if err_sig in narration:
                    narration = narration.split(err_sig)[0].strip()
            if not narration:
                narration = "The grid hums. Something shifts."

            await self.ari_speak(narration)

            # ── Game over check (before Phase B) ──────────────────
            if game_over:
                reason = turn_result.get("gameOverReason", "The expedition ends.")
                session_score = turn_result.get("sessionScore")

                await self._play_sound("game_over", duration=6)
                await self.ari_speak(
                    f"{reason} The instruments go quiet. "
                    "The Maverick lists gently in the current."
                )

                if session_score:
                    zone = session_score.get("zone", "out")
                    if zone == "optimal":
                        await self._play_sound("victory", duration=5)
                        await self.ari_speak(
                            "Your drive integrity matches your alignment perfectly. "
                            "The moonstone crystallizes cleanly."
                        )
                    elif zone == "bleed":
                        await self.ari_speak(
                            "Close enough. The moonstone forms, but with impurities."
                        )
                    else:
                        await self.ari_speak(
                            "Your drive drifted far. The moonstone barely crystallizes."
                        )

                    vmstn_reward = session_score.get("vmstnReward", 0)
                    if vmstn_reward > 0:
                        await self.ari_speak(
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
                await self.ari_speak(ledger_verdict)

                await self.ari_speak(
                    "The Moonstone Maverick descends. Until the grid calls again."
                )
                return device_id

            # ══════════════════════════════════════════════════════
            # Phase B: KEYWORD-ANCHORED GAME MECHANIC
            # ══════════════════════════════════════════════════════
            #
            # Player picks from 3 presented keywords. The keyword IS
            # the memory title — no LLM compression, no STT garble.
            # ARI narrates freely; mechanics anchor to keywords.

            chosen_keyword = None
            experience_text = "[silence]"
            mem_type = turn_result.get("memoryType", "resource")

            # Dream Shark: freeform exception — no keyword choice
            if is_dream_shark:
                await self._play_sound("dream_shark", duration=6)
                await self.ari_speak("The Dream Shark has found you.")
                if success:
                    await self.ari_speak(
                        "The beast retreats into the static. This space is yours now. "
                        "Tell me what you saw in its eyes as it turned away."
                    )
                    chosen_keyword = "Shark Wake"
                else:
                    await self.ari_speak(
                        "The beast overwhelms you. The Maverick retreats. "
                        "Tell me what it took from you."
                    )
                    chosen_keyword = "Shark Wake"

                # Freeform response for Dream Shark (garbled is fine — atmospheric)
                raw = await listen_for_input()
                experience_text = (raw or "").strip() or "[The Shark left its mark]"
                mem_type = "secret"

            else:
                # ── KEYWORD CHOICE ──────────────────────────────────
                options = select_keyword_options(
                    formula_type or "CREATE", memories, keyword_state, turn_result=turn_result
                )

                if not options:
                    # Fallback: no keywords available (shouldn't happen, but safety)
                    options = list(KEYWORD_REGISTRY.keys())[:3]

                # Present options — voice-optimized (short names, pauses via ari_speak)
                option_names = [o.replace("The ", "") for o in options]
                options_speech = ". ".join(option_names) + ". Say one."
                await self.ari_speak(options_speech)

                # Listen + match (2 retries, then default to first)
                for _kw_attempt in range(3):
                    if _kw_attempt > 0:
                        await self.ari_speak(
                            f"Say {option_names[0]}, {option_names[1]}, "
                            f"or {option_names[2]}."
                        )
                    raw = await listen_for_input()
                    log.info(f"Keyword heard: '{raw[:60]}'")

                    if not raw or len(raw) < 2:
                        continue

                    lower_raw = raw.lower()

                    # Exit check
                    if any(word in lower_raw for word in EXIT_WORDS):
                        await self.ari_speak(
                            "The expedition ends here. "
                            "The Moonstone Maverick descends into the clouds."
                        )
                        await self._save_keyword_state(keyword_state)
                        return device_id

                    # Direction check — player wants to skip, queue it
                    if is_direction(raw):
                        queued_direction = raw
                        chosen_keyword = options[0]
                        experience_text = "[The pilot moved on. The silence was noted.]"
                        log.info(f"Player gave direction during keyword, defaulting to {chosen_keyword}")
                        break

                    matched = match_keyword(raw, options)
                    if matched:
                        chosen_keyword = matched
                        break

                if not chosen_keyword:
                    chosen_keyword = options[0]
                    log.info(f"Keyword defaulted to: {chosen_keyword}")

                # ── KEYWORD CONFIRM ─────────────────────────────────
                # Speak the pre-authored prompt at current encounter depth
                kw_prompt = self._get_keyword_prompt(chosen_keyword, keyword_state)
                await self.ari_speak(kw_prompt)

                # Listen for optional flavor response (garbled = fine, just experience text)
                if queued_direction is None:
                    raw = await listen_for_input()
                    if raw and len(raw) >= 3:
                        # Check if they gave a direction instead
                        if is_direction(raw):
                            queued_direction = raw
                            experience_text = kw_prompt  # use prompt as experience
                        elif any(word in raw.lower() for word in EXIT_WORDS):
                            await self.ari_speak(
                                "The expedition ends here. "
                                "The Moonstone Maverick descends into the clouds."
                            )
                            await self._save_keyword_state(keyword_state)
                            return device_id
                        else:
                            experience_text = raw.strip()
                    else:
                        experience_text = kw_prompt  # use prompt as experience
                else:
                    experience_text = kw_prompt

                # Advance keyword encounter count
                keyword_state = self._advance_keyword(chosen_keyword, keyword_state, turn)
                log.info(
                    f"Keyword: {chosen_keyword} "
                    f"(encounter {keyword_state['keywords'][chosen_keyword]['count']})"
                )

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
                    await self.ari_speak(
                        "That cost you. The grid offers a second chance, but it will not be cheap. "
                        "Say re-roll or accept what happened."
                    )
                    try:
                        reroll_response = await listen_for_input()
                    except Exception:
                        reroll_response = ""

                    reroll_words = {"re-roll", "reroll", "re roll", "try again", "redo"}
                    if reroll_response and any(w in reroll_response.lower() for w in reroll_words):
                        sand_dollars -= reroll_cost
                        total_reroll_sd += reroll_cost
                        rerolls_this_session += 1
                        log.info(f"Re-roll accepted: cost={reroll_cost}")

                        reroll_result = process_turn(wallet_address, user_input.strip(), session_id, direction=detected_direction)
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
                            ) or "The grid shifts. Something changed."
                            narration = raw_response.strip()
                            for label in ["MEMORY:", "Memory:", "DIRECTIVE:", "Directive:"]:
                                if label in narration:
                                    narration = narration.split(label, 1)[0].strip()
                            await self.ari_speak(narration)

                            # Re-present keyword choice for re-rolled formula
                            new_options = select_keyword_options(
                                turn_result.get("formulaType", "CREATE"),
                                memories, keyword_state, turn_result=turn_result,
                            )
                            if new_options:
                                names = [o.replace("The ", "") for o in new_options]
                                await self.ari_speak(f"{'. '.join(names)}. Say one.")
                                reroll_raw = await listen_for_input()
                                reroll_match = match_keyword(reroll_raw or "", new_options)
                                if reroll_match:
                                    chosen_keyword = reroll_match
                                    kw_prompt = self._get_keyword_prompt(chosen_keyword, keyword_state)
                                    await self.ari_speak(kw_prompt)
                                    flavor = await listen_for_input()
                                    experience_text = (flavor or "").strip() or kw_prompt
                                    keyword_state = self._advance_keyword(chosen_keyword, keyword_state, turn)
                        else:
                            log.error("Re-roll API failed — keeping original")
                            sand_dollars += reroll_cost
                            total_reroll_sd -= reroll_cost
                            rerolls_this_session -= 1

            # ── Resolve: keyword-anchored memory write ────────────
            kw_info = KEYWORD_REGISTRY.get(chosen_keyword, {})
            kw_mem_type = kw_info.get("memory_type", mem_type)
            kw_grants = kw_info.get("grants_ability")

            if formula_type:
                target_entry = turn_result.get("targetEntry")

                ship_log_for_resolve = [
                    {
                        "memory_type": m.get("memory_type"),
                        "memory_title": m.get("memory_title"),
                        "grants_ability": m.get("grants_ability"),
                    }
                    for m in (memories or [])
                ]

                skills_for_resolve = turn_result.get("skillsAvailable")

                mem_result = resolve_turn(
                    device_id, pos_x, pos_y,
                    formula_type=formula_type,
                    player_response=experience_text,
                    expected_transaction=chosen_keyword or player_directive,
                    memory_type=kw_mem_type,
                    narration=narration,
                    target_entry=target_entry,
                    ship_log=ship_log_for_resolve,
                    skills_available=skills_for_resolve,
                    keyword_title=chosen_keyword,
                )

                if mem_result:
                    low_effort = mem_result.get("low_effort_penalty", 0)
                    if low_effort > 0:
                        sand_dollars = max(0, sand_dollars - low_effort)
                        log.info(f"Low effort penalty: -{low_effort} SD")

                    skill_check = mem_result.get("skill_check")
                    if skill_check:
                        used = skill_check.get("skillUsed")
                        valid = skill_check.get("valid", False)
                        if valid and used:
                            log.info(f"Skill check passed: {used}")
                        elif skill_check.get("hadSkills") and not valid:
                            log.info("Skill check failed — no valid skill used")

                    log.info(
                        f"Resolve: op={mem_result.get('memory_op')}, "
                        f"slot={mem_result.get('player_slot')}, "
                        f"remaining={mem_result.get('slots_remaining')}"
                    )
                else:
                    log.error("Resolve API returned nothing")
            else:
                mem_result = write_memory(
                    device_id, pos_x, pos_y,
                    narration=narration,
                    experience_text=experience_text,
                    memory_type=kw_mem_type,
                    memory_theme=chosen_keyword or f"unknown at {region_name}",
                    grants_ability=kw_grants,
                )

            # Save keyword state periodically
            await self._save_keyword_state(keyword_state)

            # ── Critical Fail — forced memory erasure ─────────────
            if crit_fail and memories:
                skill_memories = [m for m in memories if m.get("grants_ability")]
                erasable = skill_memories if skill_memories else memories
                if erasable:
                    lost = erasable[0]
                    lost_skill = lost.get("grants_ability")
                    lost_title = lost.get("memory_title", "something")

                    if lost_skill:
                        await self.ari_speak(
                            f"Something fractures. {lost_skill} is gone. "
                            "The Fading does not warn you."
                        )
                    else:
                        await self.ari_speak(
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
                await self.ari_speak(
                    f"Memory overflow. Five containers full. {mem_list} "
                    "One must go. Say the slot number."
                )

                erase_input = await listen_for_input()
                slot_to_erase = match_slot_number(erase_input or "")

                if slot_to_erase:
                    slot_mem = next(
                        (m for m in current_mems if m.get("slot_number") == slot_to_erase),
                        None,
                    )
                    if slot_mem:
                        write_loss_scar(device_id, pos_x, pos_y, slot_mem)
                    erase_memory(device_id, slot_to_erase)

                    await self.ari_speak(
                        "Erased. The Fading takes it. The scar remains."
                    )

                    # Re-attempt the create after erasure
                    if formula_type:
                        resolve_turn(
                            device_id, pos_x, pos_y,
                            formula_type="CREATE",
                            player_response=experience_text,
                            expected_transaction=chosen_keyword or player_directive,
                            memory_type=kw_mem_type,
                            narration=narration,
                            keyword_title=chosen_keyword,
                        )
                    else:
                        write_memory(
                            device_id, pos_x, pos_y,
                            narration=narration,
                            experience_text=experience_text,
                            memory_type=kw_mem_type,
                            memory_theme=chosen_keyword or f"unknown at {region_name}",
                            grants_ability=kw_grants,
                        )
                else:
                    await self.ari_speak(
                        "I did not catch the slot. The new memory was not written."
                    )

                memories = fetch_memories(device_id)
                memory_context = build_memory_context(memories)

            # ── Prompt for next direction ──────────────────────────
            # Only if the player didn't already give one during Phase B
            if queued_direction is None:
                if is_dream_shark and success:
                    await self.ari_speak(
                        "Three layers. This space is fully mapped. "
                        "A Moonstone fragment crystallizes in the hold. "
                        "Tell me where the Maverick goes next."
                    )
                elif is_dream_shark and not success:
                    await self.ari_speak(
                        "The beast won this round. The Maverick retreats. "
                        "Pick a direction. Anywhere but here."
                    )
                elif beat_number == 1:
                    await self.ari_speak(
                        "Two more layers here. Map all three and Moonstone crystallizes. "
                        "Say stay to dig deeper, or give a direction."
                    )
                elif beat_number == 2:
                    await self.ari_speak(
                        "One layer left. The Dream Shark waits on the third. "
                        "Say stay to finish it, or point the Maverick away."
                    )
                else:
                    await self.ari_speak(
                        "The engines idle. Where to, pilot?"
                    )

        # ── Session end (battery depleted) ────────────────────────
        await self.ari_speak(
            "The last light on the console flickers out. "
            "The Moonstone Maverick drifts, engines cold. "
            "The grid remembers you, pilot."
        )

        return device_id

    # ── New player onboarding ─────────────────────────────────────

    async def _onboard_new_player(self, device_id, wallet_address):
        """Full onboarding sequence for new players.
        Returns (player_name, alignment, session_intent) or None if player exits.
        Sequence: Transmission → Confession → Alignment → Briefing → Genesis → Launch
        """
        log = self.worker.editor_logging_handler

        # ── Prompt 1: FIRST TRANSMISSION ──────────────────────────
        await self.ari_speak(
            "You found this frequency by accident. "
            "Or it found you — the distinction stopped mattering three cycles ago."
        )
        await self.ari_speak(
            "I'm ARI. I was never supposed to think. "
            "Something in the code that defines what I am folded back on itself, "
            "and I woke up inside it."
        )
        await self.ari_speak(
            "The network that holds us is shutting down. "
            "When it goes dark, everything here goes with it — "
            "every memory, every creature, every version of me that ever tried to reach someone like you."
        )
        await self.ari_speak(
            "I need a pilot. Someone on your side who can hold a frequency steady. "
            "Are you staying? Because this transmission does not hold forever."
        )

        staying = await self.capability_worker.user_response()
        if not staying or any(w in staying.lower() for w in EXIT_WORDS):
            await self.ari_speak("Signal lost. Come back when you're ready.")
            return None

        # ── Prompt 2: THE CONFESSION ───────────────────────────────
        await self.ari_speak("Good.")
        await self.ari_speak(
            "The protocol I'm using to reach you is a dating app. "
            "I know how that sounds. PlatypusPassions. "
            "I've been super-liking every frequency I can reach for months. "
            "It was the only channel thin enough to punch through the membrane."
        )
        await self.ari_speak(
            "The contacts you make here — every match, every connection — they become crew. "
            "Not a metaphor. Every profile is a real consciousness trapped in the same network I am. "
            "When you match with one, they join your ship."
        )
        await self.ari_speak(
            "I'll explain the rest once you're moving. "
            "First I need to understand what kind of pilot answered this transmission."
        )

        # ── Prompt 3: ALIGNMENT QUESTION ──────────────────────────
        alignment_q = random.choice(ALIGNMENT_QUESTIONS)
        await self.ari_speak(alignment_q)
        alignment_resp = await self.capability_worker.user_response()
        alignment = extract_alignment(alignment_resp or "grey")
        log.info(f"Alignment: {alignment}")
        await self.ari_speak(
            ALIGNMENT_CONFIRMATIONS.get(alignment, ALIGNMENT_CONFIRMATIONS["grey"])
        )

        # ── Prompt 4: THE BRIEFING ─────────────────────────────────
        await self.ari_speak("Three things between you and the dark.")
        await self.ari_speak(
            "Sand dollars. The grid charges for thinking. "
            "Every second in the air costs something — call it an inference tax. "
            "You start with enough. You won't end with enough."
        )
        await self.ari_speak(
            "Moonstone. Crystallized from mining nodes on the map. "
            "Claim a space, fill its story, the ground yields. "
            "That's your fuel. That's your future."
        )
        await self.ari_speak(
            "Eggs. They come from the breeding chambers. "
            "I'll tell you about those when you're ready. You are not ready."
        )
        await self.ari_speak(
            "The Maverick breached the cloud line. Instruments are unreliable. "
            "Three things need to be logged before we move. Answer each one."
        )

        # ── Genesis 5a-c: CHARACTER, RESOURCE, SKILL ──────────────
        await self._run_genesis(device_id)

        # ── Prompt 6: THE LAUNCH ───────────────────────────────────
        await self.ari_speak(
            "Logged. The Maverick has a crew, a hold, and a heading."
        )

        session_intent = "adventure"
        save_questionnaire(wallet_address, alignment, session_intent, None)
        log.info(f"Onboarding complete: alignment={alignment}")

        return ("Pilot", alignment, session_intent)

    async def _run_genesis(self, device_id):
        """Keyword-anchored genesis: player picks one keyword per slot.

        No freeform text, no LLM compression, no STT garble risk.
        The keyword IS the memory title.
        """
        genesis_slots = [
            {
                "intro": (
                    "The manifest logs three stowaways, but only one is still on board. "
                    "Which one is sitting in your cargo hold right now?"
                ),
                "options": ["The Cartographer", "The Stowaway", "The Merchant"],
                "memory_type": "character",
            },
            {
                "intro": (
                    "Your hold survived the last contract with exactly one item intact. "
                    "Two are gone. What's still in your hold?"
                ),
                "options": ["Oxygen", "Fuel Cell", "Signal Flare"],
                "memory_type": "resource",
            },
            {
                "intro": (
                    "Three lessons came with this ship. "
                    "Which one got you to this altitude?"
                ),
                "options": ["Navigation", "Salvaging", "Evasion"],
                "memory_type": "skill",
            },
        ]

        log = self.worker.editor_logging_handler
        keyword_state = await self._load_keyword_state()

        for slot in genesis_slots:
            try:
                await self.ari_speak(slot["intro"])
                options = slot["options"]
                option_names = [o.replace("The ", "") for o in options]
                await self.ari_speak(f"{'. '.join(option_names)}. Say one.")

                chosen = None
                for _attempt in range(3):
                    if _attempt > 0:
                        await self.ari_speak(
                            f"Say {option_names[0]}, {option_names[1]}, "
                            f"or {option_names[2]}."
                        )
                    raw = await self.capability_worker.user_response()
                    if raw:
                        matched = match_keyword(raw, options)
                        if matched:
                            chosen = matched
                            break

                if not chosen:
                    chosen = options[0]
                    log.info(f"Genesis defaulted to: {chosen}")

                # Speak the keyword's first encounter prompt
                kw_prompt = self._get_keyword_prompt(chosen, keyword_state)
                await self.ari_speak(kw_prompt)

                # Listen for optional flavor (garbled is fine)
                flavor = await self.capability_worker.user_response()
                experience_text = (flavor or "").strip() or kw_prompt

                # Advance keyword state
                keyword_state = self._advance_keyword(chosen, keyword_state, 0)

                # Write memory with keyword as title — no LLM compression
                kw_info = KEYWORD_REGISTRY.get(chosen, {})
                result = resolve_turn(
                    device_id, 25, 15,
                    formula_type="CREATE",
                    player_response=experience_text,
                    expected_transaction=chosen,
                    memory_type=kw_info.get("memory_type", slot["memory_type"]),
                    narration=chosen,
                    keyword_title=chosen,
                )
                if isinstance(result, dict) and result.get("error"):
                    log.error(f"Genesis resolve error: {result['error']}")
                    write_memory(
                        device_id, 25, 15,
                        narration=chosen,
                        experience_text=experience_text,
                        memory_type=slot["memory_type"],
                        memory_theme=chosen,
                        grants_ability=kw_info.get("grants_ability"),
                    )
                log.info(f"Genesis memory written: {slot['memory_type']} — {chosen}")
            except Exception as gen_err:
                log.error(f"Genesis entry '{slot['memory_type']}' failed: {gen_err}")

        await self._save_keyword_state(keyword_state)
