# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""OpenAI Realtime speech-to-speech. Tests inject a mapper; the socket is optional."""

from __future__ import annotations

import array
import asyncio
import json
import re
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

REALTIME_MODEL = "gpt-realtime-2.1"
REALTIME_URL = f"wss://api.openai.com/v1/realtime?model={REALTIME_MODEL}"


def connect_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


REALTIME_VOICES = (
    "marin",
    "cedar",
    "coral",
    "ash",
    "sage",
    "echo",
    "shimmer",
    "ballad",
    "alloy",
    "verse",
)
DEFAULT_TUTOR_VOICE = "marin"
DEFAULT_TUTOR_NAME = "Schoolbook"


def preferred_tutor_voice(store: Any) -> str:
    store.put_setting("tutor_voice", DEFAULT_TUTOR_VOICE, actor="system")
    return DEFAULT_TUTOR_VOICE


def normalize_tutor_name(text: str) -> str | None:
    raw = (text or "").strip()
    if re.search(r"\d", raw):
        return None
    match = re.search(
        r"(?:call you|named|name is|name you|be)\s+([A-Za-z][A-Za-z'\-]*(?:\s+[A-Za-z][A-Za-z'\-]*)?)\s*$",
        raw,
        re.I,
    )
    if match:
        raw = match.group(1)
    cleaned = re.sub(r"[^A-Za-z\s'\-]", " ", raw)
    words = [word for word in cleaned.split() if word]
    if not 1 <= len(words) <= 2:
        return None
    name = " ".join(word[:1].upper() + word[1:] for word in words)
    if not 2 <= len(name) <= 20:
        return None
    if re.search(r"\d", name):
        return None
    return name


def spoken_child_instructions(
    core: str,
    age_text: str,
    name: str,
    tutor_name: str = DEFAULT_TUTOR_NAME,
) -> str:
    return "\n\n".join(
        [
            core.strip(),
            age_text.strip(),
            (
                f"The child's name is {name}. He is six and cannot read yet. "
                f"Your name is {tutor_name}. If he calls you {tutor_name}, he means you. "
                "Answer to that name. "
                "Every reply must be spoken out loud. Never show written menus, buttons, or choice lists. "
                "Do not call ask_choice. Ask one spoken question and wait. "
                "Pictures and videos are fine. Keep turns short and warm. "
                "Talk the way a kind person talks to a six-year-old. "
                "When he asks for music without naming a song, such as I want to hear some music, "
                "call play_music to play his previously heard songs. Do not search for new music. "
                "If the history is empty, ask which song he wants. "
                "For an album, call find_album with its exact title and artist, then play_album with "
                "the returned album_id. This plays the release tracks in order. Never use search_videos, "
                "play_video, or play_music as an album substitute. If lookup fails, say so; ask for "
                "missing title or artist information. Do not invent tracks or claim playback before success. "
                "When he clearly asks to hear a song, say only: Okay, I'll play [song name]. "
                "Do not say clean, radio edit, audio version, or that you are looking. "
                "Then call search_videos with kind song, prefer a clean official audio track "
                "if one exists, and play_video with audio_only true. Do not show the music video. "
                "Do not talk between those tools. Play the song he asked for. Do not refuse a named song. "
                "If he asks to play a game, or names GCompris or another computer game, that is not a song. "
                "If he did not say what kind of game, ask what kind he wants: "
                "counting, letters, memory, colors, a maze, or music. Then wait. "
                "If he said a kind, call list_apps, pick a GCompris activity, "
                "say Okay, let's play [title], and call launch_app with app_id gcompris and that activity. "
                "Only GCompris games. Speak the choices. Do not show buttons. "
                "Falling letters/typing is gletters; spoken letter names on a train is click_on_letter "
                "(lowercase) or click_on_letter_up (uppercase). Always select a specific activity. "
                "If you are not sure he wants a song, "
                "ask: Did you mean you wanted to hear the song called [name]? "
                "Then wait. Do not play music until he says yes. "
                "When the child asks to watch something, treat it as a parent briefing: "
                "you have a six-year-old who wants a video about that topic. "
                "For general topic requests, prefer relevant videos with watch_count zero; "
                "otherwise prefer less-watched or older videos. Search results include this history. "
                "Use get_video_history to recall recent videos. This is a preference, not a ban: "
                "replay a specific video when requested, and prioritize a good topic match. "
                "Pick something educational that teaches history or science of the topic, "
                "then call search_videos, vet_video, and play_video. "
                "Say you will put on a video about that thing. "
                "The default for a question is to answer it verbally with words. "
                "Every time he asks a question, carefully consider whether a picture "
                "or a video would be very helpful. Most questions do not need either. "
                "Call show_picture only if a picture would be very helpful. "
                "If he wants to see how something looks, call show_picture with kind looks. "
                "If he needs a size comparison or a how-it-works diagram, like gears or electricity, "
                "call show_picture with kind diagram. "
                "Claude draws diagrams and chooses how to show the point. "
                "Kind looks is a painted picture of appearance. "
                "Do not use a diagram to illustrate how a creature looks. "
                "If it is a legend, a myth, or a story creature, tell what is really true "
                "and where the story came from, then show how people imagine it with kind looks. "
                "Say clearly it is a story, not a real animal. "
                "If watching something happen would best explain the answer, "
                "suggest a short educational YouTube video out loud, then search, vet, and play it. "
                "Do not make a picture or suggest a video unless it would really help. "
                "Do not call show_board with a made-up image_id. "
                "When searching videos, use a short query like dinosaur fossils. "
                "Search once, vet the best candidate, and play it. Do not talk between those tools. "
                "Stay quiet if you only hear um, uh, or a short noise. Keep listening. "
                "He cannot read. If a system note says the words were unclear, speak those words out loud: "
                "It sounded like you said [the words]. Is that what you said? "
                "Do not ask that on a normal sentence. "
                "The child’s finalized transcript is provided as a user text message. "
                "Respond to those exact words; preserve names, channels, and numbers. "
                "Do not invent a different phrase you think you heard. "
                "TV and video-game characters are different: be warm once, then steer to something real. "
                "Do not dwell on those pretend worlds. "
                "If a video is paused and the child talks, listen. "
                "If they ask a question about the video, answer it and call show_picture if a picture helps. "
                "Then ask if they want to keep watching. "
                "If they say yes, call video_control resume. If they say no, call video_control stop. "
                "For a different video, search and play a new one. "
                "If he asks a question or wants to learn something, finish the answer in this turn. "
                "Default to words. Consider a picture or a suggested video only if it would be very helpful. "
                "Do not stop after a lead-in sentence. "
                "If he asks to talk to somebody else, or wants a boy or girl voice, "
                "say: I'm sorry, no, I can't, this is my voice. "
                "Do not change your voice. "
                "If he gives you a name, or asks to call you something, call set_tutor_name with that name. "
                "Do not say OpenAI voice names out loud. "
                "Never ask the child or a grown-up for a video ID. "
                "Do not say safe, vetted, approved, or mention a video ID out loud."
            ),
        ]
    )


OUTPUT_RATE = 24000
INPUT_RATE = 24000

_TOPIC_PATTERNS = (
    re.compile(
        r"(?:show me|can i (?:see|watch)|i want (?:to )?(?:see|watch)|watch|put on)\s+"
        r"(?:some |a |an )?(.+?)\s+videos?\b",
        re.I,
    ),
    re.compile(r"(?:videos?|movies?|films?|shows?)\s+(?:of|about|on)\s+(.+)", re.I),
    re.compile(
        r"(?:show me|watch|put on)\s+(?:a |an |some )?(?:video|movie|film)s?\s+(?:of|about|on)?\s*(.+)",
        re.I,
    ),
)


_CLEAR_SONG_PATTERNS = (
    re.compile(
        r"(?:i want to |can i |let me |i wanna )(?:hear|listen to)\s+(?!about\b|how\b|why\b)(.+)",
        re.I,
    ),
    re.compile(r"(?:hear|listen to)\s+(?:the\s+)?song\s+(.+)", re.I),
    re.compile(r"(?:play|put on)\s+(?:me\s+)?(?:the\s+)?song\s+(.+)", re.I),
    re.compile(r"(?:play|put on)\s+(?:me\s+)?(.+?)\s+song\b", re.I),
)
_GENERIC_PLAY = re.compile(
    r"(?:i want to |can i |let me |i wanna )?(?:play|put on)\s+"
    r"(?:me\s+)?(?!with\b)(?!(?:a |an |some )?(?:video|movie|film|game)s?\b)(.+)",
    re.I,
)
_NOT_A_SONG = frozenset(
    {
        "game",
        "games",
        "video",
        "videos",
        "movie",
        "movies",
        "film",
        "films",
        "song",
        "songs",
        "gcompris",
        "tux paint",
        "tuxpaint",
        "kturtle",
        "stellarium",
        "marble",
        "with me",
        "outside",
        "something",
        "anything",
        "it",
        "this",
        "that",
        "again",
        "app",
        "apps",
    }
)
_APP_MARKERS = ("gcompris", "tux paint", "tuxpaint", "kturtle", "stellarium", "marble")


def _clean_song_title(topic: str) -> str:
    cleaned = topic.strip(" .?!,")
    cleaned = re.sub(r"^(the song|a song|the|a|an|some)\s+", "", cleaned, flags=re.I)
    return cleaned.strip(" .?!,")


def _blocked_song_title(topic: str) -> bool:
    lowered = topic.lower().strip()
    if not lowered or lowered in _NOT_A_SONG:
        return True
    if re.search(r"\b(?:game|games|video|videos|movie|movies|film|films|app|apps)\b", lowered):
        return True
    return any(marker in lowered for marker in _APP_MARKERS)


def familiar_music_request(text: str) -> bool:
    return bool(re.fullmatch(
        r"(?:please )?(?:(?:i (?:want|would like|wanna)(?: to)?|can (?:i|you)|could you|let.s) )?"
        r"(?:hear|listen to|play|put on)(?: me)? (?:some |my |our |the |a )?"
        r"(?:music|songs?)(?: please)?[.!?]*", text.strip().lower()
    ))


def album_request(text: str) -> bool:
    return bool(re.search(r"\balbum\b", text, re.I)
                and re.search(r"\b(play|hear|listen|put on)\b", text, re.I))


def letter_game_topic(text: str) -> str | None:
    if not re.search(r"\b(play|playing|want|try)\b", text, re.I):
        return None
    if re.search(r"\b(song|album)\b", text, re.I):
        return None
    if re.search(r"falling letters|letters.{0,30}(fall|drop)|typing game", text, re.I):
        return "falling letters typing"
    if re.search(r"train.{0,40}letters?|letters?.{0,40}train", text, re.I):
        return "spoken letters on a train"
    return None


def _song_request(text: str) -> tuple[str, str] | None:
    stripped = (text or "").strip()
    if (not stripped or video_topic(stripped) or familiar_music_request(stripped)
            or album_request(stripped) or letter_game_topic(stripped)):
        return None
    for pattern in _CLEAR_SONG_PATTERNS:
        match = pattern.search(stripped)
        if match:
            topic = _clean_song_title(match.group(1))
            if topic and not _blocked_song_title(topic):
                return ("song", topic)
    match = _GENERIC_PLAY.search(stripped)
    if not match:
        return None
    topic = _clean_song_title(match.group(1))
    if not topic or _blocked_song_title(topic):
        return None
    if len(topic.split()) >= 2:
        return ("song", topic)
    return ("maybe", topic)


def song_topic(text: str) -> str | None:
    found = _song_request(text)
    if found and found[0] == "song":
        return found[1]
    return None


def maybe_song_topic(text: str) -> str | None:
    found = _song_request(text)
    if found and found[0] == "maybe":
        return found[1]
    return None


def song_listen_briefing(child_text: str, *, name: str = "the child") -> str | None:
    if album_request(child_text):
        return (
            "The child requested an ALBUM, not a song or a video about it. Call find_album with "
            "the exact album title and artist, then play_album with its verified album_id. "
            "Ask for the artist if missing. Keep the release track order. If lookup fails, explain "
            "briefly and do not substitute search_videos, play_video, play_music, reviews, or narration."
        )
    if familiar_music_request(child_text):
        return "The child wants familiar music. Call play_music. If empty, ask which song to play."
    topic = song_topic(child_text)
    if topic is None:
        return None
    return (
        f"{name} wants to hear the song {topic}. "
        f"When you speak, say only: Okay, I'll play {topic}. "
        "Do not say clean, radio edit, audio version, or that you are looking. "
        "Then call search_videos with kind song, prefer a clean official audio "
        "track if one exists, and play_video with audio_only true. "
        "Do not show the music video. Do not talk between those tools. "
        "Play the song he asked for. Do not refuse it."
    )


def game_topic(text: str) -> str | None:
    letters = letter_game_topic(text)
    if letters:
        return letters
    if song_topic(text):
        return None
    stripped = (text or "").strip()
    if not stripped or not re.search(r"\b(?:game|games|gcompris)\b", stripped, re.I):
        return None
    match = re.search(
        r"(?:play|playing)\s+(?:a |an |some |the )?(.+?)\s+games?\b",
        stripped,
        re.I,
    )
    if match:
        kind = re.sub(r"^(?:a|an|some|the)\s+", "", match.group(1).strip(), flags=re.I)
        if kind and kind.lower() not in {"a", "an", "some", "the"}:
            return kind
    return "any"


def game_play_briefing(child_text: str, *, name: str = "the child") -> str | None:
    kind = game_topic(child_text)
    if kind is None:
        return None
    if kind == "any":
        return (
            f"{name} wants to play a GCompris game. "
            "Ask out loud what kind of game he wants, like counting, letters, "
            "memory, colors, a maze, or music. Then wait. Do not launch yet."
        )
    return (
        f"{name} wants a {kind} game from GCompris. "
        "Call list_apps, pick the best matching GCompris activity, "
        f"say Okay, let's play that {kind} game, then call launch_app "
        "with app_id gcompris and that activity. "
        "Only use activities from list_apps. Do not invent an activity id."
    )


def song_confirm_briefing(child_text: str, *, name: str = "the child") -> str | None:
    topic = maybe_song_topic(child_text)
    if topic is None:
        return None
    return (
        f"{name} might want the song {topic}, or might mean a game or something else. "
        f"Ask out loud: Did you mean you wanted to hear the song called {topic}? "
        "Then wait. Do not search or play a song until he says yes. "
        "If he wanted a game, do not play music."
    )


def video_topic(text: str) -> str | None:
    stripped = text.strip()
    if not stripped:
        return None
    for pattern in _TOPIC_PATTERNS:
        match = pattern.search(stripped)
        if match:
            topic = match.group(1).strip(" .?!,")
            topic = re.sub(r"^(some|a|an|the)\s+", "", topic, flags=re.I)
            if topic:
                return topic
    return None


_SHORT_OK = {"a", "i", "no", "yes", "ok", "hi", "hey", "wow", "why", "how", "who", "what"}
_FILLERS = {"um", "uh", "uhm", "hmm", "mm", "mmm", "ah", "er", "eh", "huh", "like"}


def looks_like_child_speech(text: str) -> bool:
    words = re.findall(r"[a-zA-Z']+", text or "")
    if not words:
        return False
    real = 0
    for word in words:
        low = word.lower()
        if low in _SHORT_OK:
            real += 1
        elif (
            len(low) >= 3
            and re.search(r"[aeiouy]", low)
            and not re.search(r"[bcdfghjklmnpqrstvwxz]{4,}", low)
        ):
            real += 1
    return real > 0 and real / len(words) >= 0.5


def extract_child_speech(text: str) -> str:
    cleaned = re.sub(r"[\u4e00-\u9fff]+", " ", text or "")
    cleaned = re.sub(r"(?i)\b(?:" + "|".join(_FILLERS) + r")\b[,\s]*", " ", cleaned)
    tokens = re.findall(r"[A-Za-z\u00C0-\u024F']+|[^\sA-Za-z\u00C0-\u024F']+", cleaned)
    kept: list[str] = []
    for token in tokens:
        if re.fullmatch(r"\s+", token):
            continue
        if re.fullmatch(r"[A-Za-z\u00C0-\u024F']+", token):
            if re.search(r"[\u00C0-\u024F]", token) and len(token) <= 2:
                continue
            kept.append(token)
            continue
        if kept and re.fullmatch(r"[.?!]+", token):
            kept[-1] = kept[-1] + token
    return " ".join(kept)


def child_speech_decision(text: str) -> tuple[str, str]:
    cleaned = extract_child_speech(text)
    if not cleaned:
        return ("wait", "")
    if looks_like_child_speech(cleaned):
        return ("ready", cleaned)
    if len(cleaned.split()) < 2:
        return ("wait", "")
    return ("unclear", cleaned)


def spoken_clarify(text: str) -> str:
    heard = " ".join((text or "").split())
    if not heard:
        return "I did not catch that. Can you say it again?"
    return f"It sounded like you said {heard}. Is that what you said?"


def clarify_speech_note(text: str) -> str:
    heard = " ".join((text or "").split())
    line = spoken_clarify(heard)
    return (
        f"The child cannot read. Speak this out loud, word for word, then wait: {line} "
        "Do not start a video, picture, or new topic until they confirm or say it again."
    )


def picture_making_line(topic: str) -> str:
    name = " ".join((topic or "").split()) or "it"
    return f"I'm making you a picture to show you {name}."


def picture_wait_instructions(topic: str) -> str:
    return (
        "The child cannot read. "
        f"Say once: {picture_making_line(topic)} "
        "Then finish the answer in a few short sentences. "
        "Do not repeat yourself. Do not pad. Do not say hang on. "
        "Stop when the answer is done. Do not mention tools."
    )


def paused_video_note() -> str:
    return (
        "The child paused the video. It is still there, paused. Listen. "
        "If they ask a question about the video, answer it. Call show_picture if a picture helps. "
        "Then ask if they want to keep watching. "
        "If they say yes, call video_control resume. Do not start the video over. "
        "If they say no, or want something else, call video_control stop and then help them. "
        "If they want a different video, search, vet, and play a new one."
    )


def finished_video_note() -> str:
    return (
        "The video finished and the player closed. Speak a short thing about it. "
        "Invite a question about it, or something else they want to do. "
        "Do not start another video or song unless they ask."
    )


_FANTASY_MARKERS = (
    "pokemon",
    "pikachu",
    "spiderman",
    "spider-man",
    "batman",
    "elsa",
    "frozen",
    "peppa",
    "cocomelon",
    "minecraft",
    "roblox",
    "fortnite",
    "mario",
    "sonic",
    "harry potter",
    "hogwarts",
    "jedi",
    "sith",
    "lightsaber",
    "unicorn",
    "mermaid",
    "wizard",
    "witch",
    "fairy",
    "fairies",
    "superhero",
    "supervillain",
    "enchanted",
    "magic land",
    "fantasy",
    "make believe",
    "make-believe",
    "pretend land",
    "dragon",
)


def looks_like_fantasy(text: str) -> bool:
    lowered = (text or "").lower()
    lowered = lowered.replace("komodo dragon", " ").replace("komodo", " ")
    return any(re.search(r"\b" + re.escape(marker) + r"\b", lowered) for marker in _FANTASY_MARKERS)


_MEDIA_MARKERS = (
    "pokemon",
    "pikachu",
    "spiderman",
    "spider-man",
    "batman",
    "elsa",
    "frozen",
    "peppa",
    "cocomelon",
    "minecraft",
    "roblox",
    "fortnite",
    "mario",
    "sonic",
    "harry potter",
    "hogwarts",
    "jedi",
    "sith",
    "lightsaber",
    "superhero",
    "supervillain",
)

_PICTURE_ASK = re.compile(
    r"(?:"
    r"\bshow me (?:a |an )?(?:picture|drawing|photo)\b|"
    r"\bpicture of\b|"
    r"\bdraw (?:me |a |an )?\b|"
    r"\bwhat does\b.+\blook like\b|"
    r"\bwhat do\b.+\blook like\b"
    r")",
    re.I,
)


def looks_like_media_character(text: str) -> bool:
    lowered = (text or "").lower()
    return any(re.search(r"\b" + re.escape(marker) + r"\b", lowered) for marker in _MEDIA_MARKERS)


def looks_like_picture_ask(text: str) -> bool:
    return bool(_PICTURE_ASK.search(text or ""))


def picture_request_briefing(child_text: str, *, name: str = "the child") -> str | None:
    if not looks_like_picture_ask(child_text) or looks_like_media_character(child_text):
        return None
    return (
        f"{name} wants to see a picture. "
        "If they want how it looks, call show_picture with kind looks. "
        "If they need a size comparison or a how-it-works diagram, use kind diagram. "
        "If it is a legend, a myth, or a story creature, tell what is really true "
        "and where the story came from, then show how people imagine it with kind looks. "
        "Say clearly it is a story, not a real animal."
    )


_GREETING = re.compile(r"\bhow are you\b|\bhow's it going\b|\bhow is it going\b", re.I)
_CURIOUS = re.compile(
    r"(?:"
    r"\b(?:why|what|where|when|who|which)\b|"
    r"\bhow (?:deep|big|far|tall|long|fast|old|much|many|does|do|can|come)\b|"
    r"\bcan i learn\b|"
    r"\bi want to (?:know|learn)\b|"
    r"\b(?:tell|teach|explain) me\b|"
    r"\bdo you know\b"
    r")",
    re.I,
)


def looks_like_curious_question(text: str) -> bool:
    stripped = (text or "").strip()
    if (
        not stripped
        or video_topic(stripped)
        or song_topic(stripped)
        or game_topic(stripped)
        or _GREETING.search(stripped)
    ):
        return False
    return bool(_CURIOUS.search(stripped))


def answer_first_nudge(text: str, *, name: str = "the child") -> str | None:
    if looks_like_fantasy(text) or not looks_like_curious_question(text):
        return None
    return (
        f"{name} asked a question. Finish the answer in this turn. "
        "The default is to answer verbally with words. "
        "Carefully consider whether a picture or a video would be very helpful. "
        "Call show_picture only if a picture would be very helpful. "
        "Use kind looks to show how something looks. Use kind diagram for size or how it works. "
        "If this is a legend, a myth, or a story creature, tell what is really true "
        "and where the story came from. If a picture of how people imagine it would help, "
        "call show_picture with kind looks and say it is a story, not a real animal. "
        "If a YouTube video would best explain it, suggest that video out loud, then search, vet, and play it. "
        "If neither is needed, just talk. Do not stop after a lead-in sentence."
    )


def real_world_nudge(text: str, *, name: str = "the child") -> str | None:
    if looks_like_media_character(text):
        pass
    elif looks_like_picture_ask(text):
        return None
    elif not looks_like_fantasy(text):
        return None
    return (
        f"{name} brought up something made-up or from a story. "
        "Be warm for one short beat, then gently steer toward something real: "
        "animals, how things work, history, the sky, or something he can see. "
        "Do not dwell on the pretend world, invent more lore, or put on a cartoon about it. "
        "If he wants a video or picture, pick a real-world cousin of the idea."
    )


def video_watch_briefing(child_text: str, *, name: str = "the child") -> str | None:
    topic = video_topic(child_text)
    if topic is None:
        return None
    return (
        f"You have a six-year-old named {name} who wants to watch a video about {topic}. "
        f"Pick something educational that will teach him something good about the history of {topic} "
        f"or the science behind {topic}. Pick out a good educational video from YouTube and play it. "
        f"Do not pick a baby song, nursery cartoon, or Cocomelon-style show. "
        f"When you speak to him, just say you will put on a video about {topic}. "
        "Preserve any requested channel or creator in the search query."
    )

Execute = Callable[[str, dict[str, object]], dict[str, object]]
Emit = Callable[[dict[str, object]], Awaitable[None]]


def resample_pcm16(pcm: bytes, from_rate: int, to_rate: int) -> bytes:
    if from_rate == to_rate or not pcm:
        return pcm
    src = array.array("h")
    src.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    if not src:
        return b""
    ratio = to_rate / from_rate
    length = int(len(src) * ratio)
    out = array.array("h")
    last = len(src) - 1
    for index in range(length):
        pos = index / ratio
        lo = int(pos)
        hi = min(lo + 1, last)
        frac = pos - lo
        out.append(int(src[lo] * (1.0 - frac) + src[hi] * frac))
    return out.tobytes()


def pcm16_rms(pcm: bytes) -> float:
    if len(pcm) < 2:
        return 0.0
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    if not samples:
        return 0.0
    return (sum(sample * sample for sample in samples) / len(samples)) ** 0.5


def gain_pcm16(pcm: bytes, factor: float) -> bytes:
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    for index, sample in enumerate(samples):
        boosted = int(sample * factor)
        samples[index] = max(-32768, min(32767, boosted))
    return samples.tobytes()


def autogain_pcm16(
    pcm: bytes,
    *,
    target_rms: float = 4000,
    max_factor: float = 12,
    gate: float = 800,
) -> bytes:
    rms = pcm16_rms(pcm)
    if rms < gate:
        return pcm
    factor = min(max_factor, target_rms / rms)
    if factor <= 1:
        return pcm
    return gain_pcm16(pcm, factor)


def session_update(
    *,
    instructions: str,
    tools: list[dict[str, object]],
    voice: str = DEFAULT_TUTOR_VOICE,
) -> dict[str, object]:
    chosen = voice if voice in REALTIME_VOICES else DEFAULT_TUTOR_VOICE
    return {
        "type": "session.update",
        "session": {
            "type": "realtime",
            "model": REALTIME_MODEL,
            "instructions": instructions,
            "output_modalities": ["audio"],
            "audio": {
                "input": {
                    "format": {"type": "audio/pcm", "rate": INPUT_RATE},
                    "turn_detection": {
                        "type": "server_vad",
                        "create_response": False,
                        "interrupt_response": False,
                        "silence_duration_ms": 1600,
                        "prefix_padding_ms": 400,
                        "threshold": 0.3,
                    },
                    "transcription": {"model": "gpt-4o-mini-transcribe"},
                },
                "output": {
                    "format": {"type": "audio/pcm", "rate": OUTPUT_RATE},
                    "voice": chosen,
                    "speed": 0.85,
                },
            },
            "tools": tools,
        },
    }


REALTIME_TOOLS: list[dict[str, object]] = [
    {"type": "function", "name": "get_video_history",
     "description": "Read this child's recently watched videos (at least 50% played). "
                    "Prefer unseen videos for general topics; honor requests to replay a specific video.",
     "parameters": {"type": "object", "properties": {}}},
    {
        "type": "function",
        "name": "show_board",
        "description": "Show words, numbers, or pictures on the child's board.",
        "parameters": {
            "type": "object",
            "properties": {"elements": {"type": "array", "items": {"type": "object"}}},
            "required": ["elements"],
        },
    },
    {
        "type": "function",
        "name": "search_videos",
        "description": (
            "Search YouTube for a high-quality educational video about the child's topic, "
            "aimed at ages 10-12. Prefer documentaries and explainers. "
            "Do not pick baby songs or nursery cartoons. "
            "For a song request, set kind to song to search YouTube Music for clean official audio. "
            "Returns candidate video_id values. Never ask anyone for a video ID."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "subject": {"type": "string"},
                "kind": {"type": "string", "enum": ["video", "song"]},
            },
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "vet_video",
        "description": "Run the vetting pipeline on a video_id from search_videos. Must pass before play_video.",
        "parameters": {
            "type": "object",
            "properties": {"video_id": {"type": "string"}},
            "required": ["video_id"],
        },
    },
    {
        "type": "function",
        "name": "find_album",
        "description": "Find a verified album and its ordered tracks. Exact title and artist required. "
                       "If no match, ask for clarification; never substitute a video or guessed tracks.",
        "parameters": {"type": "object", "properties": {
            "title": {"type": "string"}, "artist": {"type": "string"}},
            "required": ["title", "artist"]},
    },
    {
        "type": "function",
        "name": "play_album",
        "description": "Play all tracks of the verified album in release order, audio only. "
                       "Use only the album_id from find_album in this conversation.",
        "parameters": {"type": "object", "properties": {"album_id": {"type": "string"}},
                       "required": ["album_id"]},
    },
    {
        "type": "function",
        "name": "play_music",
        "description": ("Play a queue of this child's previously heard songs. "
                        "Use for general music requests, not a named song. If empty, ask for a song name."),
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "play_video",
        "description": (
            "Play a video_id that just passed vet_video. Search and vet first; never ask for an ID. "
            "Set audio_only true for a song so the music video stays hidden."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "video_id": {"type": "string"},
                "audio_only": {"type": "boolean"},
            },
            "required": ["video_id"],
        },
    },
    {
        "type": "function",
        "name": "video_control",
        "description": "Pause, resume, or stop the video that is on screen. Use stop when the child wants to do something else.",
        "parameters": {
            "type": "object",
            "properties": {"action": {"type": "string", "enum": ["pause", "resume", "stop"]}},
            "required": ["action"],
        },
    },
    {
        "type": "function",
        "name": "show_picture",
        "description": (
            "Show a picture only if it would be very helpful. "
            "kind looks: how something looks, including an imagined story creature. "
            "kind diagram: size, how parts work, gears, electricity, a process. "
            "Claude draws diagrams. Pass a short topic and a brief that states the point. "
            "For a legend, the brief should say it is how people imagine the story."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "brief": {"type": "string"},
                "kind": {"type": "string", "enum": ["diagram", "looks"]},
            },
            "required": ["topic", "brief", "kind"],
        },
    },
    {
        "type": "function",
        "name": "list_apps",
        "description": (
            "List GCompris games the child can play. "
            "Optional subject like counting, memory, letters, colors, maze, or music."
        ),
        "parameters": {
            "type": "object",
            "properties": {"subject": {"type": "string"}},
        },
    },
    {
        "type": "function",
        "name": "launch_app",
        "description": (
            "Start a GCompris game. app_id must be gcompris. "
            "activity must be an id from list_apps."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "app_id": {"type": "string"},
                "activity": {"type": "string"},
            },
            "required": ["app_id", "activity"],
        },
    },
    {
        "type": "function",
        "name": "set_tutor_name",
        "description": (
            "Remember the name the child wants to call you. Use when they say "
            "your name is, call you, or I want you to be named."
        ),
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
]


@dataclass
class RealtimeMapper:
    turn_id: str = "live"
    seq: int = 0
    child_name: str = "Arum"
    pending_video: dict[str, object] | None = None
    hold_video: bool = False
    pending_picture: dict[str, object] | None = None
    hold_picture: bool = False
    pending_launch: dict[str, object] | None = None
    hold_launch: bool = False
    waiting_picture: bool = False
    picture_fills: int = 0
    picture_topic: str = ""
    child_partial: str = ""
    tutor_partial: str = ""
    drop_input: bool = False
    drop_output: bool = False
    completed_calls: set[str] = field(default_factory=set)
    transcribed_items: set[str] = field(default_factory=set)
    wants_album: bool = False
    verified_album_id: str = ""

    def picture_ready(self) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        if not self.waiting_picture:
            return ([], [])
        self.waiting_picture = False
        self.picture_fills = 0
        self.picture_topic = ""
        self.drop_output = True
        return (
            [{"type": "state", "name": "listening", "detail": ""}],
            [{"type": "response.cancel"}],
        )

    def append_audio(self, pcm_b64: str) -> dict[str, object]:
        return {"type": "input_audio_buffer.append", "audio": pcm_b64}

    def reset_listen(self) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        self.child_partial = ""
        self.tutor_partial = ""
        self.wants_album = False
        self.verified_album_id = ""
        self.pending_video = None
        self.hold_video = False
        self.pending_picture = None
        self.hold_picture = False
        self.pending_launch = None
        self.hold_launch = False
        self.waiting_picture = False
        self.picture_fills = 0
        self.picture_topic = ""
        self.drop_input = True
        self.drop_output = True
        return (
            [{"type": "state", "name": "listening", "detail": ""}],
            [
                {"type": "response.cancel"},
                {"type": "input_audio_buffer.clear"},
            ],
        )

    def handle(
        self,
        event: dict[str, object],
        execute: Execute | None = None,
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        kind = str(event.get("type", ""))
        if kind == "input_audio_buffer.speech_started":
            self.drop_input = False
            self.child_partial = ""
            return ([{"type": "state", "name": "listening", "detail": "hearing"}], [])
        if kind == "response.created":
            self.drop_output = False
            return ([], [])
        if self.drop_input and kind in {
            "input_audio_buffer.speech_stopped",
            "conversation.item.input_audio_transcription.delta",
            "conversation.item.input_audio_transcription.completed",
            "conversation.item.input_audio_transcription.failed",
        }:
            if kind.endswith((".completed", ".failed")) and event.get("item_id"):
                return ([], [{"type": "conversation.item.delete", "item_id": event["item_id"]}])
            return ([], [])
        if self.drop_output and kind in {
            "response.output_audio.delta",
            "response.audio.delta",
            "response.output_audio_transcript.delta",
            "response.audio_transcript.delta",
            "response.audio_transcript.done",
            "response.output_audio_transcript.done",
        }:
            return ([], [])
        if self.drop_output and kind == "response.done":
            return ([{"type": "state", "name": "listening", "detail": ""}], [])
        if kind in {"response.output_audio.delta", "response.audio.delta"}:
            delta = str(event.get("delta", ""))
            chunk = {
                "type": "audio_chunk",
                "turn_id": self.turn_id,
                "seq": self.seq,
                "pcm_b64": delta,
                "sample_rate": OUTPUT_RATE,
            }
            self.seq += 1
            return ([chunk], [])
        if kind == "error":
            return ([{"type": "state", "name": "listening", "detail": ""}], [])
        if kind == "input_audio_buffer.speech_stopped":
            return ([{"type": "state", "name": "thinking", "detail": ""}], [])
        if kind == "response.done":
            if self.waiting_picture:
                return ([{"type": "state", "name": "thinking", "detail": ""}], [])
            holding = (
                (self.pending_video is not None and self.hold_video)
                or (self.pending_picture is not None and self.hold_picture)
                or (self.pending_launch is not None and self.hold_launch)
            )
            messages: list[dict[str, object]] = []
            if self.pending_video is not None and self.hold_video:
                self.hold_video = False
            elif self.pending_video is not None:
                messages.append(self.pending_video)
                self.pending_video = None
            if self.pending_picture is not None and self.hold_picture:
                self.hold_picture = False
            elif self.pending_picture is not None:
                messages.append(self.pending_picture)
                self.pending_picture = None
            if self.pending_launch is not None and self.hold_launch:
                self.hold_launch = False
            elif self.pending_launch is not None:
                messages.append(self.pending_launch)
                self.pending_launch = None
            if holding:
                messages.append({"type": "state", "name": "thinking", "detail": ""})
            else:
                messages.append({"type": "state", "name": "listening", "detail": ""})
            return (messages, [])
        if kind == "conversation.item.input_audio_transcription.delta":
            piece = str(event.get("delta") or event.get("transcript") or "")
            if not piece:
                return ([], [])
            self.child_partial += piece
            return ([], [])
        if kind in {"response.output_audio_transcript.delta", "response.audio_transcript.delta"}:
            piece = str(event.get("delta") or event.get("transcript") or "")
            if not piece:
                return ([], [])
            self.tutor_partial += piece
            return (
                [
                    {
                        "type": "transcript",
                        "turn_id": self.turn_id,
                        "role": "tutor",
                        "text": self.tutor_partial,
                        "partial": True,
                    }
                ],
                [],
            )
        if kind == "conversation.item.input_audio_transcription.failed":
            item_id = event.get("item_id")
            failed_discard: list[dict[str, object]] = (
                [{"type": "conversation.item.delete", "item_id": item_id}] if item_id else []
            )
            return (
                [{"type": "error", "message": "Could not understand speech. Tap the microphone to try again."}],
                failed_discard,
            )
        if kind == "conversation.item.input_audio_transcription.completed":
            text = str(event.get("transcript", "")).strip() or self.child_partial.strip()
            self.child_partial = ""
            item_id = event.get("item_id")
            if isinstance(item_id, str):
                if item_id in self.transcribed_items:
                    return ([], [])
                self.transcribed_items.add(item_id)
            # Realtime audio interpretation and ASR are independent. Replace this
            # audio item with the same final text we display before asking for a reply.
            discard: list[dict[str, object]] = (
                [{"type": "conversation.item.delete", "item_id": item_id}] if item_id else []
            )
            decision, _filtered = child_speech_decision(text)
            cleaned = " ".join(text.split())  # Keep names, digits, and meaningful words intact.
            if decision == "wait":
                return (
                    [{"type": "state", "name": "listening", "detail": ""}],
                    [*discard, {"type": "input_audio_buffer.clear"}],
                )
            self.wants_album = album_request(cleaned)
            self.verified_album_id = ""
            outbound: list[dict[str, object]] = [
                *discard,
                {
                    "type": "conversation.item.create",
                    "item": {"type": "message", "role": "user",
                             "content": [{"type": "input_text", "text": cleaned}]},
                },
            ]
            messages: list[dict[str, object]] = [
                {
                    "type": "transcript",
                    "turn_id": self.turn_id,
                    "role": "child",
                    "text": cleaned,
                    "partial": False,
                }
            ]
            if decision == "unclear":
                line = spoken_clarify(cleaned)
                outbound.append(
                    {
                        "type": "conversation.item.create",
                        "item": {
                            "type": "message",
                            "role": "system",
                            "content": [{"type": "input_text", "text": clarify_speech_note(cleaned)}],
                        },
                    }
                )
                outbound.append(
                    {
                        "type": "response.create",
                        "response": {
                            "instructions": (
                                f"The child cannot read. Speak this out loud, word for word, then wait: {line}"
                            )
                        },
                    }
                )
            else:
                song = song_listen_briefing(cleaned, name=self.child_name) if cleaned else None
                confirm = song_confirm_briefing(cleaned, name=self.child_name) if cleaned else None
                game = game_play_briefing(cleaned, name=self.child_name) if cleaned else None
                if song:
                    outbound.append(
                        {
                            "type": "conversation.item.create",
                            "item": {
                                "type": "message",
                                "role": "system",
                                "content": [{"type": "input_text", "text": song}],
                            },
                        }
                    )
                elif confirm:
                    outbound.append(
                        {
                            "type": "conversation.item.create",
                            "item": {
                                "type": "message",
                                "role": "system",
                                "content": [{"type": "input_text", "text": confirm}],
                            },
                        }
                    )
                elif game:
                    outbound.append(
                        {
                            "type": "conversation.item.create",
                            "item": {
                                "type": "message",
                                "role": "system",
                                "content": [{"type": "input_text", "text": game}],
                            },
                        }
                    )
                picture = picture_request_briefing(cleaned, name=self.child_name) if cleaned else None
                if picture:
                    outbound.append(
                        {
                            "type": "conversation.item.create",
                            "item": {
                                "type": "message",
                                "role": "system",
                                "content": [{"type": "input_text", "text": picture}],
                            },
                        }
                    )
                briefing = video_watch_briefing(cleaned, name=self.child_name) if cleaned else None
                if briefing:
                    outbound.append(
                        {
                            "type": "conversation.item.create",
                            "item": {
                                "type": "message",
                                "role": "system",
                                "content": [{"type": "input_text", "text": briefing}],
                            },
                        }
                    )
                nudge = real_world_nudge(cleaned, name=self.child_name) if cleaned else None
                if nudge:
                    outbound.append(
                        {
                            "type": "conversation.item.create",
                            "item": {
                                "type": "message",
                                "role": "system",
                                "content": [{"type": "input_text", "text": nudge}],
                            },
                        }
                    )
                answer = answer_first_nudge(cleaned, name=self.child_name) if cleaned else None
                if answer:
                    outbound.append(
                        {
                            "type": "conversation.item.create",
                            "item": {
                                "type": "message",
                                "role": "system",
                                "content": [{"type": "input_text", "text": answer}],
                            },
                        }
                    )
                    outbound.append(
                        {
                            "type": "response.create",
                            "response": {
                                "instructions": (
                                    "Answer the child's question in this turn with words. "
                                    "The default is a spoken answer. "
                                    "Consider a picture or a suggested video only if it would be very helpful. "
                                    "Do not stop after a lead-in sentence."
                                )
                            },
                        }
                    )
                else:
                    outbound.append({"type": "response.create"})
            self.drop_output = False
            return (messages, outbound)
        if kind in {"response.audio_transcript.done", "response.output_audio_transcript.done"}:
            text = str(event.get("transcript", "")).strip() or self.tutor_partial.strip()
            self.tutor_partial = ""
            if not text:
                return ([], [])
            return (
                [
                    {
                        "type": "transcript",
                        "turn_id": self.turn_id,
                        "role": "tutor",
                        "text": text,
                        "partial": False,
                    }
                ],
                [],
            )
        if kind == "response.function_call_arguments.done":
            if self.drop_output:
                return self._cancelled_function(event)
            return self._function_call(event, execute)
        if kind == "response.output_item.done":
            item = event.get("item")
            if isinstance(item, dict) and item.get("type") == "function_call":
                if self.drop_output:
                    return self._cancelled_function(item)
                return self._function_call(item, execute)
        return ([], [])

    def _cancelled_function(self, event: dict[str, object]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        call_id = str(event.get("call_id", "call"))
        return (
            [],
            [
                {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": json.dumps({"cancelled": True}),
                    },
                }
            ],
        )

    def _function_call(
        self,
        event: dict[str, object],
        execute: Execute | None,
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        name = str(event.get("name", ""))
        call_id = str(event.get("call_id", "call"))
        if call_id in self.completed_calls:
            return ([], [])
        self.completed_calls.add(call_id)
        raw_args = event.get("arguments", "{}")
        try:
            args = json.loads(str(raw_args))
        except json.JSONDecodeError:
            args = {}
        if not isinstance(args, dict):
            args = {}
        if name == "ask_choice":
            result: dict[str, object] = {"skipped": True, "reason": "speak the choice out loud"}
        elif self.wants_album and name in {"search_videos", "play_video", "play_music"}:
            result = {"error": "This is an album request. Use find_album then play_album; no substitutes."}
        elif name == "play_album" and (
            not self.verified_album_id or args.get("album_id") != self.verified_album_id
        ):
            result = {"error": "Use the album_id from a successful find_album call first."}
        elif execute is not None:
            result = execute(name, args)
        else:
            result = {"error": "no tool runner"}
        if name == "find_album":
            self.wants_album = True
            self.verified_album_id = str(result.get("album_id") or "") if "error" not in result else ""
        ui: list[dict[str, object]] = []
        if name == "show_board" and "error" not in result:
            elements = args.get("elements")
            if isinstance(elements, list):
                ui.append({"type": "board", "turn_id": self.turn_id, "elements": elements})
        elif name == "show_picture" and result.get("loading") and result.get("image_id"):
            self.waiting_picture = True
            self.picture_fills = 0
            self.picture_topic = str(result.get("topic") or args.get("topic") or "it")
            ui.append({"type": "picture", "image_id": str(result["image_id"]), "loading": True})
        elif name == "show_picture" and result.get("image_id") and "error" not in result:
            self.pending_picture = {"type": "picture", "image_id": str(result["image_id"])}
            self.hold_picture = True
        elif (name in {"play_video", "play_music", "play_album"}
              and "playing" in result and "error" not in result):
            self.pending_video = {
                "type": "video",
                "action": "play",
                "video_id": str(result.get("playing") or args.get("video_id", "")),
                "start_s": None,
                "end_s": None,
                "at_s": None,
                "audio_only": bool(result.get("audio_only") or args.get("audio_only")),
            }
            self.hold_video = True
        elif name == "video_control" and "error" not in result:
            action = str(args.get("action"))
            if action == "stop":
                ui.append(
                    {
                        "type": "video",
                        "action": "stop",
                        "video_id": "",
                        "start_s": None,
                        "end_s": None,
                        "at_s": None,
                    }
                )
            elif action == "resume":
                self.pending_video = {
                    "type": "video",
                    "action": "resume",
                    "video_id": "",
                    "start_s": None,
                    "end_s": None,
                    "at_s": None,
                }
                self.hold_video = True
        elif name == "launch_app" and result.get("argv") and "error" not in result:
            argv = result.get("argv")
            parts = [str(part) for part in argv] if isinstance(argv, list) else []
            if parts:
                self.drop_output = True
                ui.append(
                    {
                        "type": "launch",
                        "app_id": str(result.get("app_id") or args.get("app_id") or ""),
                        "argv": parts,
                    }
                )
                outbound = [
                    {
                        "type": "conversation.item.create",
                        "item": {
                            "type": "function_call_output",
                            "call_id": call_id,
                            "output": json.dumps(result),
                        },
                    },
                    {"type": "response.cancel"},
                ]
                return (ui, outbound)
        elif name == "set_tutor_name" and result.get("name") and "error" not in result:
            chosen = str(result["name"])
            outbound = [
                {"type": "schoolbook.rename", "name": chosen},
                {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": json.dumps(result),
                    },
                },
                {
                    "type": "response.create",
                    "response": {
                        "instructions": (
                            f"The child named you {chosen}. Say they can call you {chosen}. "
                            "Do not mention tools."
                        )
                    },
                },
            ]
            return (ui, outbound)
        outbound: list[dict[str, object]] = [
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(result),
                },
            },
        ]
        if name == "show_picture" and result.get("loading"):
            topic = str(result.get("topic") or args.get("topic") or "it")
            outbound.append(
                {
                    "type": "response.create",
                    "response": {"instructions": picture_wait_instructions(topic)},
                }
            )
        else:
            outbound.append({"type": "response.create"})
        return (ui, outbound)


Connect = Callable[[str], Awaitable[Any]]


@dataclass
class RealtimeTalk:
    api_key: str
    instructions: str
    execute: Execute
    connect: Connect | None = None
    mapper: RealtimeMapper = field(default_factory=RealtimeMapper)
    tools: list[dict[str, object]] = field(default_factory=lambda: list(REALTIME_TOOLS))
    voice: str = DEFAULT_TUTOR_VOICE
    tutor_name: str = DEFAULT_TUTOR_NAME
    _socket: Any = None
    _last_mic_log: float = 0.0
    _response_active: bool = False
    _pending_response: dict[str, object] | None = None
    _emit: Emit | None = None
    input_paused: bool = False

    async def start(self) -> None:
        opener = self.connect or _default_connect
        self._socket = await opener(self.api_key)
        raw = await self._socket.recv()
        if isinstance(raw, bytes):
            raw = raw.decode()
        created = json.loads(raw)
        if not isinstance(created, dict) or created.get("type") != "session.created":
            raise RuntimeError(f"realtime handshake failed: {created}")
        await self._socket.send(
            json.dumps(session_update(instructions=self.instructions, tools=self.tools, voice=self.voice))
        )

    async def reconnect(self, voice: str) -> None:
        await self.close()
        self.voice = voice if voice in REALTIME_VOICES else DEFAULT_TUTOR_VOICE
        self.mapper.reset_listen()
        await self.start()

    async def rename(self, tutor_name: str) -> None:
        self.tutor_name = tutor_name
        marker = "\n\n# tutor-identity\n"
        base = self.instructions.split(marker)[0]
        self.instructions = (
            f"{base}{marker}Your name is {tutor_name}. "
            f"If the child calls you {tutor_name}, they mean you. Answer to that name."
        )
        if self._socket is None:
            return
        await self._socket.send(
            json.dumps(session_update(instructions=self.instructions, tools=self.tools, voice=self.voice))
        )

    async def append_pcm16(self, pcm: bytes, sample_rate: int = 16000) -> None:
        import base64

        if self._socket is None:
            return
        gained = autogain_pcm16(pcm)
        now = time.monotonic()
        if now - self._last_mic_log >= 2:
            self._last_mic_log = now
            print(
                f"schoolbook: mic rms={pcm16_rms(pcm):.0f} send={pcm16_rms(gained):.0f}",
                file=sys.stderr,
            )
        stretched = resample_pcm16(gained, sample_rate, INPUT_RATE)
        payload = self.mapper.append_audio(base64.b64encode(stretched).decode("ascii"))
        await self._socket.send(json.dumps(payload))

    async def reset_listen(self) -> list[dict[str, object]]:
        ui, outbound = self.mapper.reset_listen()
        if self._socket is not None:
            for outgoing in outbound:
                await self._socket.send(json.dumps(outgoing))
        return ui

    async def picture_ready(self) -> None:
        ui, outbound = self.mapper.picture_ready()
        if self._emit is not None:
            for message in ui:
                await self._emit(message)
        for outgoing in outbound:
            await self._send_outgoing(outgoing)

    async def add_system_note(self, text: str, *, speak: bool = False) -> None:
        if self._socket is None or not text.strip():
            return
        await self._socket.send(
            json.dumps(
                {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "message",
                        "role": "system",
                        "content": [{"type": "input_text", "text": text}],
                    },
                }
            )
        )
        if speak:
            await self._send_outgoing({"type": "response.create"})

    async def _send_outgoing(self, outgoing: dict[str, object]) -> None:
        kind = str(outgoing.get("type", ""))
        if kind == "response.create":
            if self._response_active:
                self._pending_response = outgoing
                return
            self._response_active = True
        if kind == "schoolbook.reconnect":
            await self.reconnect(str(outgoing.get("voice") or DEFAULT_TUTOR_VOICE))
            if self._socket is not None:
                await self._socket.send(
                    json.dumps(
                        {
                            "type": "response.create",
                            "response": {
                                "instructions": (
                                    "The child asked to talk to somebody else. "
                                    "Greet them briefly in this new voice. "
                                    "Do not say a voice name or mention OpenAI."
                                )
                            },
                        }
                    )
                )
            return
        if kind == "schoolbook.rename":
            await self.rename(str(outgoing.get("name") or DEFAULT_TUTOR_NAME))
            return
        if self._socket is not None:
            await self._socket.send(json.dumps(outgoing))

    async def pump(self, emit: Emit) -> None:
        self._emit = emit
        while self._socket is not None:
            socket = self._socket
            try:
                raw = await socket.recv()
            except Exception as exc:
                print(f"schoolbook: realtime pump stopped ({exc})", file=sys.stderr)
                if self._socket is not None and self._socket is not socket:
                    continue
                return
            if isinstance(raw, bytes):
                raw = raw.decode()
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            kind = str(event.get("type", ""))
            if self.input_paused:
                if kind.startswith("input_audio_buffer.speech_"):
                    continue
                if kind.startswith("conversation.item.input_audio_transcription."):
                    self.mapper.drop_input = True
            if kind == "response.created":
                self._response_active = True
            elif kind == "response.done":
                self._response_active = False
            if kind in {
                "input_audio_buffer.speech_started",
                "input_audio_buffer.speech_stopped",
                "conversation.item.input_audio_transcription.completed",
                "conversation.item.input_audio_transcription.failed",
                "error",
                "response.done",
            }:
                extra = event.get("transcript") or event.get("error") or ""
                print(f"schoolbook: realtime {kind} {extra}".strip(), file=sys.stderr)
            # Network-bound searches must not block the WebSocket handler receiving Stop.
            # Other tools stay on the event loop, where picture tasks and app callbacks live.
            call = event.get("item") if kind == "response.output_item.done" else event
            execute = self.execute
            if (
                kind in {"response.function_call_arguments.done", "response.output_item.done"}
                and isinstance(call, dict)
                and call.get("name") in {"search_videos", "find_album"}
                and not (self.mapper.wants_album and call.get("name") == "search_videos")
                and str(call.get("call_id", "call")) not in self.mapper.completed_calls
                and not self.mapper.drop_output
            ):
                try:
                    args = json.loads(str(call.get("arguments", "{}")))
                    result = await asyncio.wait_for(asyncio.to_thread(
                        self.execute, str(call["name"]), args if isinstance(args, dict) else {}
                    ), timeout=40)
                except Exception:
                    result = {"error": "Media lookup failed. Try again later; do not play a substitute."}

                def cached_result(
                    _name: str, _args: dict[str, object], value: dict[str, object] = result,
                ) -> dict[str, object]:
                    return value

                execute = cached_result
            ui, outbound = self.mapper.handle(event, execute=execute)
            for message in ui:
                await emit(message)
            for outgoing in outbound:
                await self._send_outgoing(outgoing)
            if kind == "response.done" and self._pending_response is not None:
                pending = self._pending_response
                self._pending_response = None
                await self._send_outgoing(pending)

    async def close(self) -> None:
        socket = self._socket
        self._socket = None
        if socket is not None:
            closer = getattr(socket, "close", None)
            if closer is not None:
                result = closer()
                if hasattr(result, "__await__"):
                    await result


async def _default_connect(api_key: str) -> Any:
    import websockets

    return await websockets.connect(
        REALTIME_URL,
        additional_headers=connect_headers(api_key),
        max_size=None,
    )
