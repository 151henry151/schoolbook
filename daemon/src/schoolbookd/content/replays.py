# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

"""Conservative permission for a specifically requested watched video."""

import re


def normalized(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.casefold()))


def specific_video_request(
    quote: str, child_text: str, title: str, *, latest: bool, tutor_question: str = "",
) -> bool:
    """Require the child's actual request, not a model-generated replay explanation.

    A title or an explicit reference to the last video permits that one replay.
    Ambiguous requests should be clarified rather than silently repeating a topic.
    """
    request = normalized(quote)
    if not request or request != normalized(child_text):
        return False
    if request in {"yes", "yes please", "yeah", "yep", "okay", "ok", "sure"}:
        question = normalized(tutor_question)
        if not re.search(r"\b(do you want|would you like|shall i|should i|did you mean)\b", question):
            return False
        request = question
    if re.search(r"\b(new|different|another|not|don t|dont|never)\b", request):
        return False
    named = bool(re.search(r"\b(called|named|titled)\b", request))
    if not named and re.search(r"\b(?:videos?|shows?) (?:about|on)\b", request):
        return False
    # Match a full title or the title before a descriptive pipe suffix. A topic
    # word alone (e.g. 'horses') is not a request for one particular video.
    for part in (title, title.split("|", 1)[0]):
        name = normalized(part)
        if not name or f" {name} " not in f" {request} ":
            continue
        significant = set(name.split()) - {
            "a", "the", "for", "kids", "video", "about", "of", "and", "facts", "learn", "fun", "all",
        }
        if len(significant) >= 2:
            return True
        if named:
            return True
    if latest and re.search(r"\b(play|watch|show|see|want|replay|rewatch)\b", request):
        return bool(re.search(
            r"\b(?:replay|rewatch)(?: it| that| the video)?$|\b(same|last|previous) (?:one|video)\b|"
            r"\b(?:it|that|that one|that video|the video) again\b",
            request,
        ))
    return False
