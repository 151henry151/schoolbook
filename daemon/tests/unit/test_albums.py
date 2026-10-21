# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Schoolbook contributors

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from test_runtime_video import ScriptSearch, _live, _runtime, _store

from schoolbookd.content.albums import AlbumError, AlbumResolver
from schoolbookd.content.catalog import CharterReviewer, VideoCatalog
from schoolbookd.content.vetting import VideoCandidate

TITLE = 'Ugly is Beautiful'
ARTIST = 'Oliver Tree'
IDS = ['jbmM-_6O6DE', '-fszyzqIiF8', 'U1vGosMScjM']
NAMES = ['Me, Myself & I', '1993 (feat. Little Ricky ZR3)', 'Cash Machine']


class Music:
    def __init__(self) -> None:
        self.results = [{'title': TITLE, 'artists': [{'name': ARTIST}], 'type': 'Album',
                         'browseId': 'release', 'isExplicit': True}]
        self.album = {'title': TITLE, 'artists': [{'name': ARTIST}], 'audioPlaylistId': 'OLAKrelease',
                      'trackCount': 3, 'tracks': [
                          {'title': name, 'videoId': video_id, 'artists': [{'name': ARTIST}],
                           'isAvailable': True} for name, video_id in zip(NAMES, IDS, strict=True)]}
        self.selected = ''

    def search(self, query, **kwargs):
        assert kwargs['filter'] == 'albums'
        return self.results

    def get_album(self, album_id):
        self.selected = album_id
        return deepcopy(self.album)


def videos(ids):
    # Data API order must not determine playback order.
    return [VideoCandidate(video_id, 'API title', 'oliver', 'Oliver Tree - Topic', '', 180,
                           True, False, False, False, 'en') for video_id in reversed(ids)]


def test_album_preserves_release_order_and_catalogue_titles():
    album = AlbumResolver(videos, Music()).resolve(TITLE.upper(), ARTIST.lower())
    assert [v.video_id for v in album.tracks] == IDS
    assert [v.title for v in album.tracks] == NAMES


@pytest.mark.parametrize('field,value', [('title', 'Ugly is Beautiful Deluxe'),
                                         ('artists', [{'name': 'Someone Else'}]),
                                         ('type', 'Single')])
def test_no_fuzzy_match_or_edition_substitution(field, value):
    music = Music()
    music.results[0][field] = value
    with pytest.raises(AlbumError, match='No exact'):
        AlbumResolver(videos, music).resolve(TITLE, ARTIST)
    assert music.selected == ''


def test_prefers_clean_release_with_same_title_and_artist():
    music = Music()
    music.results.append({**music.results[0], 'browseId': 'clean', 'isExplicit': False})
    AlbumResolver(videos, music).resolve(TITLE, ARTIST)
    assert music.selected == 'clean'


@pytest.mark.parametrize('failure', ['unavailable', 'missing', 'narrator', 'age', 'embed', 'count'])
def test_rejects_incomplete_or_unverified_album(failure):
    music = Music()
    if failure == 'unavailable':
        music.album['tracks'][1]['isAvailable'] = False
    if failure == 'count':
        music.album['trackCount'] = 4

    def details(ids):
        result = videos(ids)
        if failure == 'missing':
            return result[:-1]
        fields = {'narrator': {'channel_title': 'Album reviews'}, 'age': {'age_restricted': True},
                  'embed': {'embeddable': False}}.get(failure, {})
        result[1] = replace(result[1], **fields)
        return result

    with pytest.raises(AlbumError):
        AlbumResolver(details, music).resolve(TITLE, ARTIST)


def setup_album(tmp_path):
    store = _store(tmp_path)
    catalog = VideoCatalog(store, ScriptSearch([]), CharterReviewer(), CharterReviewer(),
                           albums=AlbumResolver(videos, Music()))
    runtime = _runtime(store, catalog)
    return store, catalog, runtime, _live(store)


def test_album_queues_all_tracks_in_order_and_records_actual_plays(tmp_path: Path):
    store, catalog, runtime, live = setup_album(tmp_path)
    result = runtime.run_tool(live, 'find_album', {'title': TITLE, 'artist': ARTIST})
    assert result['album_id'] == 'release'
    assert live.playing_video is None  # Lookup alone never starts playback.
    assert store.familiar_songs('kid') == []
    first = runtime.run_tool(live, 'play_album', {'album_id': 'release'})
    assert first == {'playing': IDS[0], 'audio_only': True, 'track_count': 3}
    assert live.song_queue == IDS[1:]
    runtime.song_started(live, IDS[0])
    assert store.familiar_songs('kid') == IDS[:1]
    assert runtime.next_song(live)['playing'] == IDS[1]
    assert runtime.next_song(live)['playing'] == IDS[2]
    assert runtime.next_song(live) is None


def test_blocked_album_never_approves_other_tracks(tmp_path: Path):
    store, catalog, runtime, live = setup_album(tmp_path)
    store.block_channel('oliver')
    assert 'error' in catalog.find_album(TITLE, ARTIST)
    assert store.video(IDS[0]) is None
    assert catalog.album_tracks('release') == []


def test_play_album_rechecks_parent_blocks_and_requires_lookup(tmp_path: Path):
    store, catalog, runtime, live = setup_album(tmp_path)
    assert 'error' in runtime.run_tool(live, 'play_album', {'album_id': 'invented'})
    catalog.find_album(TITLE, ARTIST)
    store.block_video(IDS[1])
    assert 'error' in runtime.run_tool(live, 'play_album', {'album_id': 'release'})
    assert live.playing_video is None
    assert live.song_queue == []


def test_failed_service_does_not_fall_back_to_search(tmp_path: Path):
    store, catalog, runtime, live = setup_album(tmp_path)

    def unavailable(*args):
        raise ConnectionError('offline')

    catalog.albums.music.search = unavailable
    assert 'error' in catalog.find_album(TITLE, ARTIST)
    assert catalog.album_tracks('release') == []
    assert live.playing_video is None
