# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

import pytest

from schoolbookd.content.replays import specific_video_request


@pytest.mark.parametrize('child_text,latest,allowed', [
    ('Show me a video about horses', True, False),
    ('Show me a video about horses again', True, False),
    ('Show me another video about horses', True, False),
    ('Show me something from SciShow Kids', True, False),
    ('Show me that video again', True, True),
    ('Show me that video again', False, False),
    ('Play the last video', True, True),
    ('Play the same video', True, True),
    ('Please replay it', True, True),
    ('Replay the snake video from yesterday', True, False),
    ('I do not want the same video', True, False),
    ('Please play How Horses Became Our Friends', False, True),
    ('Show me a different video from How Horses Became Our Friends', True, False),
])
def test_only_a_specific_video_request_permits_a_replay(child_text, latest, allowed):
    assert specific_video_request(child_text, child_text, 'How Horses Became Our Friends | Animal Facts',
                                  latest=latest) is allowed


def test_a_fabricated_or_stale_request_does_not_authorize_a_repeat():
    assert not specific_video_request('Show me that video again', 'Show me a video about horses',
                                      'Horse facts', latest=True)
    assert not specific_video_request('Show me snakes', 'Show me snakes', 'Snakes', latest=True)
    assert specific_video_request('Play the video called Snakes', 'Play the video called Snakes',
                                  'Snakes', latest=False)


def test_a_title_answer_or_confirmation_of_a_specific_video_is_allowed():
    title = 'How Horses Became Our Friends'
    assert specific_video_request(title, title, title, latest=False)
    assert specific_video_request('Yes please', 'Yes please', title, latest=False,
                                  tutor_question='Would you like to watch How Horses Became Our Friends?')
    assert not specific_video_request('Yes', 'Yes', title, latest=True,
                                      tutor_question='Would you like a video about horses?')
    assert not specific_video_request('Yes', 'Yes', title, latest=True,
                                      tutor_question='How Horses Became Our Friends teaches history.')


def test_topic_and_channel_phrases_are_not_title_permissions():
    assert not specific_video_request('Show me a video about horses', 'Show me a video about horses',
                                      'A Video About Horses', latest=True)
    assert not specific_video_request('I want National Geographic Kids', 'I want National Geographic Kids',
                                      'Inside a Volcano | National Geographic Kids', latest=True)
