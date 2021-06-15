# -*- coding: utf-8 -*-
import re
import os
import sys
import html
import json
import pickle
import random
import requests
from time import perf_counter
from http.cookiejar import Cookie
from .decoder import decode_audio_url


class VkontakteTrack:
    def __init__(self, main):
        self.main = main

        self.id = None
        self.owner = None
        self.album = None
        self.access = None
        
        self._url = None
        self.title = None
        self.author = None
        self.cover = None
        self.duration = None

        self.codec = 'mp3'

    @property
    def url(self):
        if self._url is None:
            audios = self.main.get_audio(self.id)
            if audios:
                self._url = audios[0]
        return self._url

    def add(self, data=[]):
        check = data[13].split("/")
        self.id = '_'.join((str(data[1]), str(data[0]), check[2], check[5]))
        self._url = data[2] if data[2] else None
        self.title = html.unescape(data[3]) if data[3] else None
        self.author = html.unescape(data[4]) if data[4] else None
        self.cover = data[14].split(',')[-1] if data[14] else self.main.urls['icon']
        self.duration = None or int(data[5])
        self.owner = str(data[19][0]) if data[19] else None
        self.album = str(data[19][1]) if data[19] else None
        self.access = str(data[19][2]) if data[19] else None


class VkontakteAlbum:
    def __init__(self, main):
        self.main = main

        self.type = None
        self.owner = None
        self.album = None
        self.access = None
        self.official = None
        self.title = None
        self.description = None
        self.author = None
        self.listens = None
        self.update = None
        self.count = None
        self.cover = None

        self.tracks = []

    @property
    def duration(self):
        return sum([t.duration for t in self.tracks])

    def add(self, data={}):
        if data:
            self.type = data.get('type')
            self.owner = data.get('ownerId')
            self.album = data.get('id')
            self.access = data.get('accessHash')
            self.official = data.get('isOfficial')
            self.title = html.unescape(data.get('title'))
            self.description = data.get('description')
            self.author = html.unescape(data.get('authorName'))
            self.listens = int(data.get('listens'))
            # self.update = int(data.get('infoLine1').split()[0])
            self.count = int(data.get('totalCount'))
            self.cover = data.get('coverUrl')

            for track in data['list']:
                check = track[13].split("/")
                if check[2] and check[5]:
                    vkt = VkontakteTrack(self.main)
                    vkt.add(track)
                    self.tracks.append(vkt)

class Vkontakte:
    urls = {
        'icon': 'https://mykroma.ru/media/wysiwyg/icons/icon-vkontakte.png',
        'audios': 'https://m.vk.com/audio',
    }
    RE_M3U8_TO_MP3 = re.compile(r'/[0-9a-f]+(/audios)?/([0-9a-f]+)/index.m3u8')
    RE_URL = re.compile(r'^(?:https?://)?(?:m[.])?vk[.]com/(?:.*?[?]?.*?audio_playlist|music/(?:playlist|album)/|audios)(?P<owner>-?[\d]+)(?:_(?P<album>[\da-zA-Z]+)(?:(?:_|.*access_hash=|.*back_hash=)(?P<access>[\da-zA-Z]+))?)?')

    def __init__(self, path='/Users/sever-in/Documents/Server/data/tokens/vkontakte.0' if sys.platform == 'win32' else '/home/seva/Server/data/tokens/vkontakte.0'):
        self.path = path
        self.token = open(self.path, "r", encoding="utf-8").read()
        self.session = None
        self.user = 634553063
        self.sid = None
        self.key = None
        self.auth()

    def auth(self, reboot=False):
        
        session = requests.Session()
        if os.path.isfile('cookies'):
            if reboot == False:
                with open('cookies', 'rb') as f:
                    session.cookies.update(pickle.load(f))
            else:
                os.remove('cookies')
        
        if not os.path.isfile('cookies'):
            login, password = self.token.split("\n")
        
            response = session.get('https://vk.com/')
            params = {
                'act': 'login',
                'role': 'al_frame',
                '_origin': 'https://vk.com',
                'utf8': '1',
                'email': login,
                'pass': password,
                'lg_h': re.search(r'lg_h=(?P<lg_h>[a-z0-9]+)', response.text).groups()[0]
            }
            res = session.post('https://login.vk.com/', params)
            # print(res.text)
            while 'onLoginReCaptcha' in res.text:
                self.sid = str(random.random())[2:16]
                self.key = input(f'\nhttps://api.vk.com/captcha.php?sid={self.sid}\nEnter captcha code: ')
                params.update({
                        'captcha_sid': self.sid,
                        'captcha_key': self.key
                    })
                res = session.post('https://login.vk.com/', params)
            with open('cookies', 'wb') as f:
                pickle.dump(session.cookies, f)

        self.session = session

        return True

    def get_album(self, *ids):

        albums = list()

        for owner, album, access in ids:
            vka = VkontakteAlbum(self)

            offset = 0

            while True:
                if self.session:
                    request = self.session.post(
                        'https://m.vk.com/audio',
                        data={
                            'act': 'load_section',
                            'owner_id': owner,
                            'playlist_id': album if album else -1,
                            'offset': offset,
                            'type': 'playlist',
                            'access_hash': access,
                            'is_loading_all': 1
                        },
                        allow_redirects=False
                    )
                    if request.text:
                        response = request.json()

                        vka.add(data=response['data'][0])
                        albums.append(vka)

                        if response['data'][0]['hasMore']:
                            offset += 2000
                        
                        else:
                            break
                    elif not self.auth():
                        break
                elif not self.auth():
                    break
        return albums

    def get_audio(self, *ids):

        audios = list()

        for group in [ids[i:i+10] for i in range(0, len(ids), 10)]:
            while True:
                if self.session:
                    request = self.session.post(
                        'https://m.vk.com/audio',
                        data={
                            'act': 'reload_audio',
                            'ids': ','.join(group)
                        }
                    )
                    if request.text:
                        response = request.json()

                        for audio in response['data'][0]:
                            len(audio)
                            url = audio[2]

                            if 'audio_api_unavailable' in url:
                                url = decode_audio_url(url, self.user)

                            if 'm3u8' in url:
                                url = self.RE_M3U8_TO_MP3.sub(r'\1/\2.mp3', url)

                            audios.append(url)
                        break
                    elif not self.auth():
                        break
                elif not self.auth():
                    break
        return audios

    def get_item(self, url: str, options={}):

        r = self.RE_URL.match(url)

        if r:
            i = r.groups()
            albums = self.get_album(i)
            if albums:
                return albums[0]

    def search(self, string, options={}):

        album = options.get('album')
        track = options.get('track')

        albums = list()
        tracks = list()

        while True:
            if self.session:
                request = self.session.post(
                    'https://vk.com/al_audio.php',
                    data={
                        'al': 1,
                        'act': 'section',
                        'claim': 0,
                        'is_layer': 0,
                        'owner_id': self.user,
                        'section': 'search',
                        'q': string
                    }
                )
                response = json.loads(request.text[4:])
                data = response['payload'][1][1]
                if data != '"Pw--"':
                    if album <= 5:
                        for a in data['playlists'][:album]:
                            vka = VkontakteAlbum(self)
                            vka.add(a)
                            albums.append(vka)
                    else:
                        while True:
                            if self.session:
                                album_request = self.session.post(
                                    'https://vk.com/al_audio.php',
                                    data={
                                        'al': 1,
                                        'act': 'load_catalog_section',
                                        'section_id': data['blockIds'][1] if data['blockIds'][0][21] == 'm' and data['blockIds'][1][21] == '2' else data['blockIds'][0],
                                    }
                                )
                                album_response = json.loads(album_request.text[4:])
                                album_data = album_response['payload'][1][1]
                                if album_data != '"Pw--"':
                                    if album_data['playlists']:
                                        for a in album_data['playlists'][:album-len(albums)]:
                                            vka = VkontakteAlbum(self)
                                            vka.add(a)
                                            albums.append(vka)

                                    if album_data['nextFrom'] and len(albums) < album:
                                        while True:
                                            if self.session:
                                                album_request = self.session.post(
                                                    'https://vk.com/al_audio.php',
                                                    data={
                                                        'al': 1,
                                                        'act': 'load_catalog_section',
                                                        'section_id': album_data['blockIds'][0],
                                                        'start_from': album_data['nextFrom']
                                                    }
                                                )
                                                
                                                album_response = json.loads(album_request.text.replace('<!--', ''))
                                                album_data = album_response['payload'][1][1]

                                                break
                                            elif not self.auth():
                                                break
                                    else:
                                        break
                            elif not self.auth():
                                break

                while True:
                    if data != '"Pw--"':
                        if data['playlist']:
                            if data['playlist']['list']:
                                for tr in data['playlist']['list'][:track-len(tracks)]:
                                    check = tr[13].split("/")
                                    if check[2] and check[5]:
                                        vkt = VkontakteTrack(self)
                                        vkt.add(tr)
                                        tracks.append(vkt)
                        else:
                            break

                        if data['nextFrom'] and len(tracks) < track:
                            while True:
                                if self.session:
                                    request = self.session.post(
                                        'https://vk.com/al_audio.php',
                                        data={
                                            'al': 1,
                                            'act': 'load_catalog_section',
                                            'section_id': data['sectionId'],
                                            'start_from': data['nextFrom']
                                        }
                                    )
                                    response = json.loads(request.text[4:])
                                    data = response['payload'][1][1]
                                    break
                                elif not self.auth():
                                    break
                        else:
                            break
                
            elif not self.auth():
                break
            break

        return {'albums': albums, 'tracks': tracks}

# url = 'https://m.vk.com/audios211315708'

# vk = Vkontakte()
# a = vk.get_item(url)
# print(a.tracks)
# vk.search(string='porter robinson', options={'album': 5, 'track': 30})
# vk.search(string='flicker', options={'album': 3, 'track': 3})
# vk.search(string='hidden cirizen', options={'album': 7, 'track': 3})
# vk.search(string='time to wake up', options={'album': 10, 'track': 3})
# vk.search(string='bad liar', options={'album': 8, 'track': 3})
# vk.search(string='bad apple', options={'album': 2, 'track': 3})