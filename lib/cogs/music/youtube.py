# -*- coding: utf-8 -*-
import requests
from time import perf_counter
import json
import re
import urllib
import codecs
import sys
from datetime import datetime
from .jsinterp import JSInterpreter


# class YouTubeStream:
#     def __init__(self, main):
#         self.main = main

#         self.id = None
#         self._url = None
#         # self.data = None
#         self.author = None
#         # self.tags = None
#         self.title = None
#         # self.description = None
#         # self.cover = None
#         # self.duration = None
#         # self.status = None
#         # self.viev = None
#         # self.like = None
#         # self.dislike = None
#         # self.comment = None
#         self.codec = 'm3u8'



class YouTubeTrack:
    def __init__(self, main):
        self.main = main
        
        self.kind = None
        self.etag = None
        self.id = None
        self.date = None
        self.channel = None
        self.title = None
        self.description = None
        self.cover = None
        self.author = None
        self.tags = None
        self.live = None
        self.language = None
        self.duration = None
        self.stream = None
        self.status = None
        self.view = None
        self.like = None
        self.dislike = None
        self.favorite = None
        self.comment = None
        self.start = None
        self.end = None
        self.schedule = None
        self.active = None

        self._url = None
        self.codec = None

    @property
    def url(self):
        audios = self.main.get_audio(self.id)
        if self._url is None and audios:
            self._url, self.codec = self.main.get_audio(self.id)[0]
        return self._url

    def add(self, data={}):

        if 'kind' in data:
            self.kind = data['kind']
        if 'etag' in data:
            self.etag = data['etag']
        if 'id' in data:
            self.id = data['id']
        if 'snippet' in data:
            snippet = data['snippet']
            if 'publishedAt' in snippet:
                self.date = datetime.strptime(snippet['publishedAt'],"%Y-%m-%dT%H:%M:%SZ")
            if 'channelId' in snippet:
                self.channel = snippet['channelId']
            if 'title' in snippet:
                self.title = snippet['title']
            if 'description' in snippet:
                self.description = snippet['description']
            if 'thumbnails' in snippet:
                thumbnails = snippet['thumbnails']
                if 'maxres' in thumbnails:
                    self.cover = thumbnails['maxres']['url']
                elif 'standard' in thumbnails:
                    self.cover = thumbnails['standard']['url']
                elif 'high' in thumbnails:
                    self.cover = thumbnails['high']['url']
                elif 'medium' in thumbnails:
                    self.cover = thumbnails['medium']['url']
                elif 'default' in thumbnails:
                    self.cover = thumbnails['default']['url']
            if 'channelTitle' in snippet:
                self.author = snippet['channelTitle']
            if 'tags' in snippet:
                self.tags = snippet['tags']
            if 'liveBroadcastContent' in snippet:
                self.live = True if snippet['liveBroadcastContent'] == 'live' else False
            if 'defaultLanguage' in snippet:
                self.language = snippet['defaultLanguage']
            elif 'defaultAudioLanguage' in snippet:
                self.language = snippet['defaultAudioLanguage']
        if 'contentDetails' in data:
            contentDetails = data['contentDetails']
            if 'duration' in contentDetails:
                self.duration = self._duration(contentDetails['duration'])
        if 'status' in data:
            status = data['status']
            if 'uploadStatus' in status:
                self.stream = True if status['uploadStatus'] == 'processed' else False
            if 'privacyStatus' in status:
                self.status = status['privacyStatus']
        if 'statistics' in data:
            statistics = data['statistics']
            if 'viewCount' in statistics:
                self.view = statistics['viewCount']
            if 'likeCount' in statistics:
                self.like = statistics['likeCount']
            if 'dislikeCount' in statistics:
                self.dislike = statistics['dislikeCount']
            if 'favoriteCount' in statistics:
                self.favorite = statistics['favoriteCount']
            if 'commentCount' in statistics:
                self.comment = statistics['commentCount']
        if 'player' in data:
            pass
        if 'liveStreamingDetails' in data:
            liveStreamingDetails = data['liveStreamingDetails']
            if 'actualStartTime' in liveStreamingDetails:
                self.start = datetime.strptime(liveStreamingDetails['actualStartTime'],"%Y-%m-%dT%H:%M:%SZ")
            if 'actualEndTime' in liveStreamingDetails:
                self.end = datetime.strptime(liveStreamingDetails['actualEndTime'],"%Y-%m-%dT%H:%M:%SZ")
            if 'scheduledStartTime' in liveStreamingDetails:
                self.schedule = datetime.strptime(liveStreamingDetails['scheduledStartTime'],"%Y-%m-%dT%H:%M:%SZ")
            if 'concurrentViewers' in liveStreamingDetails:
                self.active = liveStreamingDetails['concurrentViewers']

    def _duration(self, text):
        r = re.match(r'^P(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$', text)
        duration = 0
        if r:
            g = r.groups()
            for n in range(len(g)):
                if g[n]:
                    c = int(g[n])
                    if n == 0:
                        duration+=31536000*c
                    if n == 1:
                        duration+=2629743*c
                    if n == 2:
                        duration+=86400*c
                    if n == 3:
                        duration+=3600*c
                    if n == 4:
                        duration+=60*c
                    if n == 5:
                        duration+=c
        return duration
    


class YouTubeAlbum:
    def __init__(self, main):
        self.main = main

        self.id = None
        self.data = None
        self.author = None
        self.title = None
        self.description = None
        self.count = None
        self.cover = None
        self.status = None

        self.tracks = []

    @property
    def duration(self):
        return sum([t.duration for t in self.tracks])

    def add(self, data={}):
        self.id = data['id'],
        self.data = data['snippet'].get('publishedAt')
        self.author = data['snippet'].get('channelTitle')
        self.title = data['snippet'].get('title')
        self.description = data['snippet'].get('description')
        self.cover = data['snippet']['thumbnails'][list(data['snippet']['thumbnails'].keys())[-1]]['url']
        self.count = data['contentDetails'].get('itemCount')
        self.status = data['status'].get('privacyStatus')

        self.tracks = self._tracks()

    def _tracks(self):
        tracks = list()
        pageToken = None
        while True:
            params = {
                'key': self.main.token,
                'part': 'contentDetails',
                'playlistId': self.id,
                'maxResults': 999,
            }
            if pageToken:
                params['pageToken'] = pageToken
            
            request = self.main.session.get(self.main.urls['playlistItems'], params=params)
            response = request.json()
            pageToken = response.get('nextPageToken')

            if 'error' in response:
                break
            else:
                ids = list(item['contentDetails']['videoId'] for item in response['items'])
                tracks.extend(self.main.get_track(*ids))
            if not pageToken:
                return tracks



class YouTube:
    
    urls = {
        # 'icon': 'https://d1fdloi71mui9q.cloudfront.net/KbJAKlKmQmS69RWTUiYP_1044d54c1228c422b88d4ea9d9121eb5',
        'icon': 'https://forpost-sz.ru/sites/default/files/doc/2018/02/13/2000px-youtube_social_white_circle_2017.svg1.png',
        'videos': 'https://www.googleapis.com/youtube/v3/videos',
        'search': 'https://www.googleapis.com/youtube/v3/search',
        'channels': 'https://www.googleapis.com/youtube/v3/channels',
        'playlists': 'https://www.googleapis.com/youtube/v3/playlists',
        'playlistItems': 'https://www.googleapis.com/youtube/v3/playlistItems',
        'activities': 'https://www.googleapis.com/youtube/v3/activities',
        'youtube': 'https://www.youtube.com/watch',
        'info': 'https://www.youtube.com/get_video_info',
        'embed': 'https://www.youtube.com/embed/%s',
    }
    RE_URL = re.compile(
        r'^(?:https?://)?(?:www[.])?(?:music[.]|m[.])?youtu(?:[.]be|be[.]com|bekids[.]com)/(?:playlist|(?:(?:watch[?]v=|v/)?(?P<track>[_\w-]+[^=?&])))[?&]?(?:list=(?P<album>[\w-]+[^&]))?'
    )
    YT_INITIAL_PLAYER_RESPONSE_RE = r'ytInitialPlayerResponse\s*=\s*({.+?})\s*;'
    YT_INITIAL_BOUNDARY_RE = r'(?:var\s+meta|</script|\n)'
    PLAYER_INFO_RE = (
    r'/(?P<id>[a-zA-Z0-9_-]{8,})/player_ias\.vflset(?:/[a-zA-Z]{2,3}_[a-zA-Z]{2,3})?/base\.(?P<ext>[a-z]+)$',
    r'\b(?P<id>vfl[a-zA-Z0-9_-]+)\b.*?\.(?P<ext>[a-z]+)$',
    )
    ASSETS_RE = (
        r'<script[^>]+\bsrc=("[^"]+")[^>]+\bname=["\']player_ias/base',
        r'"jsUrl"\s*:\s*("[^"]+")',
        r'"assets":.+?"js":\s*("[^"]+")'
    )
    JS_NAME_RE = (
        r'\b[cs]\s*&&\s*[adf]\.set\([^,]+\s*,\s*encodeURIComponent\s*\(\s*(?P<sig>[a-zA-Z0-9$]+)\(',
        r'\b[a-zA-Z0-9]+\s*&&\s*[a-zA-Z0-9]+\.set\([^,]+\s*,\s*encodeURIComponent\s*\(\s*(?P<sig>[a-zA-Z0-9$]+)\(',
        r'(?:\b|[^a-zA-Z0-9$])(?P<sig>[a-zA-Z0-9$]{2})\s*=\s*function\(\s*a\s*\)\s*{\s*a\s*=\s*a\.split\(\s*""\s*\)',
        r'(?P<sig>[a-zA-Z0-9$]+)\s*=\s*function\(\s*a\s*\)\s*{\s*a\s*=\s*a\.split\(\s*""\s*\)',
        # Obsolete patterns
        r'(["\'])signature\1\s*,\s*(?P<sig>[a-zA-Z0-9$]+)\(',
        r'\.sig\|\|(?P<sig>[a-zA-Z0-9$]+)\(',
        r'yt\.akamaized\.net/\)\s*\|\|\s*.*?\s*[cs]\s*&&\s*[adf]\.set\([^,]+\s*,\s*(?:encodeURIComponent\s*\()?\s*(?P<sig>[a-zA-Z0-9$]+)\(',
        r'\b[cs]\s*&&\s*[adf]\.set\([^,]+\s*,\s*(?P<sig>[a-zA-Z0-9$]+)\(',
        r'\b[a-zA-Z0-9]+\s*&&\s*[a-zA-Z0-9]+\.set\([^,]+\s*,\s*(?P<sig>[a-zA-Z0-9$]+)\(',
        r'\bc\s*&&\s*a\.set\([^,]+\s*,\s*\([^)]*\)\s*\(\s*(?P<sig>[a-zA-Z0-9$]+)\(',
        r'\bc\s*&&\s*[a-zA-Z0-9]+\.set\([^,]+\s*,\s*\([^)]*\)\s*\(\s*(?P<sig>[a-zA-Z0-9$]+)\(',
        r'\bc\s*&&\s*[a-zA-Z0-9]+\.set\([^,]+\s*,\s*\([^)]*\)\s*\(\s*(?P<sig>[a-zA-Z0-9$]+)\('
    )

    def __init__(self, path='/Users/sever-in/Documents/Server/data/tokens/youtube.0' if sys.platform == 'win32' else '/home/seva/Server/data/tokens/youtube.0'):
        self.path = path
        self.token = open(self.path, "r", encoding="utf-8").read()
        self.session = self.auth()
        self._player_cache = {}

    def auth(self):
        session = requests.Session()
        for key in self.urls:
            url = self.urls.get(key)
            session.get(url)
        return session





    def _parse_sig_js(self, jscode):
        funcname = self._search_regex(self.JS_NAME_RE,
            jscode, group='sig')

        jsi = JSInterpreter(jscode)
        initial_function = jsi.extract_function(funcname)
        return lambda s: initial_function([s])

    # @classmethod
    def _extract_player_info(self, player_url):
        for player_re in self.PLAYER_INFO_RE:
            id_m = re.search(player_re, player_url)
            if id_m:
                break
        else:
            pass
        return id_m.group('ext'), id_m.group('id')

    def _search_regex(self, pattern, string, flags=0, group=None, default=None):

        if isinstance(pattern, (str, str, type(re.compile('')))):
            mobj = re.search(pattern, string, flags)
        else:
            for p in pattern:
                mobj = re.search(p, string, flags)
                if mobj:
                    break

        if mobj:
            if group is None:
                return next(g for g in mobj.groups() if g is not None)
            else:
                return mobj.group(group)
        else:
            return default

    def _decrypt_signature(self, s, video_id, player_url, age_gate=False):

        if player_url is None:
            pass

        if player_url.startswith('//'):
            player_url = 'https:' + player_url
        elif not re.match(r'https?://', player_url):
            player_url = f'https://www.youtube.com{player_url}'
        try:
            player_id = (player_url, self._signature_cache_id(s))
            if player_id not in self._player_cache:
                func = self._extract_signature_function(
                    video_id, player_url, s
                )
                self._player_cache[player_id] = func
            func = self._player_cache[player_id]
            if None:
                self._print_sig_code(func, s)
            return func(s)
        except Exception as e:
            pass

    def _extract_signature_function(self, video_id, player_url, example_sig):
        player_type, player_id = self._extract_player_info(player_url)
        if player_type == 'js':
            code = urllib.request.urlopen(player_url).read().decode()
            res = self._parse_sig_js(code)
        else:
            assert False, 'Invalid player type %r' % player_type

        return res

    def _signature_cache_id(self, example_sig):
        return '.'.join(str(len(part)) for part in example_sig.split('.'))

    def _get_ytplayer_config(self, video_id, webpage):
        def uppercase_escape(s):
            unicode_escape = codecs.getdecoder('unicode_escape')
            return re.sub(
                r'\\U[0-9a-fA-F]{8}',
                lambda m: unicode_escape(m.group(0))[0],
                s)
        patterns = (
            r';ytplayer\.config\s*=\s*({.+?});ytplayer',
            r';ytplayer\.config\s*=\s*({.+?});',
        )
        config = self._search_regex(
            patterns, webpage, default=None)
        if config:
            return self._parse_json(
                uppercase_escape(config), video_id, fatal=False)


    def get_audio(self, *ids):
        
        # def _parse_qsl(qs, keep_blank_values=False, strict_parsing=False,
        #                encoding='utf-8', errors='replace'):

        #     pairs = [s2 for s1 in qs.split('&') for s2 in s1.split(';')]
        #     r = []
        #     for name_value in pairs:
        #         if not name_value and not strict_parsing:
        #             continue
        #         nv = name_value.split('=', 1)
        #         if len(nv) != 2:
        #             if strict_parsing:
        #                 raise ValueError('bad query field: %r' % (name_value,))
        #             # Handle case of a control-name with no equal sign
        #             if keep_blank_values:
        #                 nv.append('')
        #             else:
        #                 continue
        #         if len(nv[1]) or keep_blank_values:
        #             name = nv[0].replace('+', ' ')
        #             name = urllib.parse.unquote(
        #                 name, encoding=encoding, errors=errors)
        #             name = str(name)
        #             value = nv[1].replace('+', ' ')
        #             value = urllib.parse.unquote(
        #                 value, encoding=encoding, errors=errors)
        #             value = str(value)
        #             r.append((name, value))
        #     return r

        # def compat_parse_qs(qs, keep_blank_values=False, strict_parsing=False,
        #                     encoding='utf-8', errors='replace'):
        #     parsed_result = {}
        #     pairs = _parse_qsl(qs, keep_blank_values, strict_parsing,
        #                        encoding=encoding, errors=errors)
        #     for name, value in pairs:
        #         if name in parsed_result:
        #             parsed_result[name].append(value)
        #         else:
        #             parsed_result[name] = [value]
        #     return parsed_result

        audios = list()



        for i in ids:
            video_webpage = self.session.get(
                self.urls['youtube'],
                params={
                    'v': i,
                    'gl': 'US',
                    'hl': 'en',
                    'has_verified': '1',
                    'bpctr': '9999999999',
                }
            ).text

            player_response = {}
            # video_info = {}
            embed_webpage = None
            # ytplayer_config = None

            # if re.search(r'["\']status["\']\s*:\s*["\']LOGIN_REQUIRED', video_webpage) is not None:
            #     print(1)
            #     age_gate = True

            #     embed_webpage = self.session.get(self.urls['embed'] % i).text

            #     video_info_webpage = self.session.get(
            #         self.urls['info'],
            #         params={
            #             'video_id': i,
            #             'eurl': 'https://youtube.googleapis.com/v/' + i,
            #             'sts': self._search_regex(r'"sts"\s*:\s*(\d+)', embed_webpage, default=''),
            #         }
            #     ).text

            #     if video_info_webpage:

            #         video_info = compat_parse_qs(video_info_webpage)
            #         pl_response = video_info.get('player_response', [None])[0]
            #         player_response = json.loads(pl_response)

            # else:
            #     print(2)
            #     age_gate = False
            #     ytplayer_config = self._get_ytplayer_config(i, video_webpage)
            #     if ytplayer_config:
            #         args = ytplayer_config['args']
            #         if args.get('url_encoded_fmt_stream_map') or args.get('hlsvp'):

            #             video_info = dict((k, [v]) for k, v in args.items())

            #         if not player_response:
            #             player_response = args.get('player_response')

            # if not video_info and not player_response:
            #     print(3)
            player_response = json.loads(self._search_regex((r'%s\s*%s' % (self.YT_INITIAL_PLAYER_RESPONSE_RE, self.YT_INITIAL_BOUNDARY_RE), self.YT_INITIAL_PLAYER_RESPONSE_RE), video_webpage))
            # print(player_response.keys())
            # if player_response['streamingData']:
            if 'streamingData' in player_response:
                if 'hlsManifestUrl' in player_response['streamingData']:
                    if 'm3u8' in player_response['streamingData']['hlsManifestUrl']:
                        url = player_response['streamingData']['hlsManifestUrl']
                        audios.append((url, 'm3u8'))
                        continue

                if 'adaptiveFormats' in player_response['streamingData']:
                    format = player_response['streamingData']['adaptiveFormats'][-1]
                    if 'url' in format:
                        cipher = None
                        url = format['url']
                    elif 'signatureCipher' in format:
                        cipher = format['signatureCipher']
                        url_data = urllib.parse.parse_qs(cipher)
                        url = url_data.get('url')[0]
                        if cipher:
                            if 's' in url_data:

                                jsplayer_url_json = self._search_regex(self.ASSETS_RE, video_webpage)

                                if not jsplayer_url_json:
                                    if embed_webpage is None:
                                        embed_webpage = self.session.get(self.urls['embed'] % i).text
                                    jsplayer_url_json = self._search_regex(self.ASSETS_RE, embed_webpage)

                                player_url = json.loads(jsplayer_url_json)
                                if player_url is None:
                                    player_url_json = self._search_regex(r'ytplayer\.config.*?"url"\s*:\s*("[^"]+")', video_webpage)
                                    player_url = json.loads(player_url_json)


                        if 'sig' in url_data:
                            url += '&signature=' + url_data['sig'][0]
                        elif 's' in url_data:
                            encrypted_sig = url_data.get('s')[0]
                            signature = self._decrypt_signature(encrypted_sig, i, player_url)
                            sp = url_data.get('sp')[0] or 'signature'
                            url += f'&{sp}={signature}'

                        if 'ratebypass' not in url:
                            url += '&ratebypass=yes'
                    codec = format['mimeType'].split('"')[-2]
                    audios.append((url, codec))

        return audios


    def get_track(self, *ids):

        t = perf_counter()
        tracks = list()
        pageToken = None

        while True:
            params = {
                'key': self.token,
                'part': 'id,snippet,contentDetails,status,statistics,player,liveStreamingDetails',
                'id': ','.join(ids),
                'maxResults': 999,
            }
            if pageToken:
                params['pageToken'] = pageToken

            request = self.session.get(self.urls['videos'], params=params)
            response = request.json()
            pageToken = response.get('nextPageToken')

            if 'error' in response:
                break
            else:
                for item in response.get('items'):
                    ytt = YouTubeTrack(self)
                    ytt.add(item)
                    tracks.append(ytt)

            if not pageToken:
                return tracks

    def get_album(self, *ids):
        t = perf_counter()
        albums = list()
        for i in ids:
            params = {
                'key': self.token,
                'part': 'id,snippet,contentDetails,status',
                'id': i,
                'maxResults': 999,
            }
            request = self.session.get(self.urls['playlists'], params=params)
            response = request.json()
            if 'error' not in response:
                for item in response.get('items'):
                    yta = YouTubeAlbum(self)
                    yta.add(item)
                    albums.append(yta)
        return albums

    def get_item(self, url: str, options={}):
        r = self.RE_URL.match(url) 
        if r:
            g = r.groupdict()
            if g.get('album'):
                album = self.get_album(g.get('album'))
                if album:
                    return album[0]
            elif g.get('track'):
                track = self.get_track(g.get('track'))
                if track:
                    return track[0]

    def search(self, string: str, options={}):

        album = options.get('album')
        track = options.get('track')

        albums = list()
        tracks = list()

        if album:
            # pageToken = None
            params = {
                'key': self.token,
                'part': 'id',
                'type': 'playlist',
                'q': string,
                'maxResults': album,
            }
            
            request = self.session.get(self.urls['search'], params=params)
            response = request.json()
            # pageToken = response.get('nextPageToken')
            
            if 'error' not in response:
                ids = [i['id']['playlistId'] for i in response['items']]
                albums.extend(self.get_album(*ids))

        if track:
            # pageToken = None
            request = self.session.get(
                self.urls['search'],
                params={
                    'key': self.token,
                    'part': 'id',
                    'type': 'video',
                    'q': string,
                    'maxResults': track,
                }
            )
            response = request.json()
            # pageToken = response.get('nextPageToken')

            if 'error' not in response:
                ids = [i['id']['videoId'] for i in response['items']]
                tracks.extend(self.get_track(*ids))

        return {'albums': albums, 'tracks': tracks, 'count': sum([album.count for album in albums])+len(tracks)}

# url = 'https://www.youtube.com/watch?v=5qap5aO4i9A'

# yt = YouTube()
# a = yt.get_item('https://www.youtube.com/watch?v=QzEPz3na3Yg')
# print(a.url)
# print(a.codec)
# s = yt.search(string='porter robinson', options={'album': 1, 'track': 1})