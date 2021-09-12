#>._python_.<#
import sys
import re
import json
import asyncio
from time import perf_counter, sleep
import random
from datetime import datetime, timedelta
import threading
import struct

#>._discord_.<#
import discord
from discord import player
from discord.ext import commands, tasks
from discord import NotFound, VoiceChannel

#>._others_.<#
from .vkontakte import Vkontakte, VkontakteAlbum, VkontakteTrack
from .youtube import YouTube, YouTubeAlbum, YouTubeTrack


class Player(threading.Thread):
    DELAY = 0.02

    def __init__(self, client):
        threading.Thread.__init__(self)
        self.daemon = True

        self.client = client
        self.music = self.client.client.get_cog('Music')
        self.session = self.music.sessions[self.client.guild.id]
        
        # self.client.encoder = opus.Encoder()

        self._source = None

        self._index = 0
        self._stand = 0
        self._stamp = 0
        self._of = 0
        self._to = 0
        self._mix = False
        self._loop = False

        self._items = list()
        self._queue = list()

        self._filters = dict()

        self._state = threading.Event()
        self._lock = threading.Lock()
        self.status = False
        self._stop = False
    

    def run(self):
        self.loops = 0
        self._start = perf_counter()

        # getattr lookup speed ups
        play_audio = self.client.send_audio_packet
        self._speak(True)

        while not self._stop:
            # are we paused?
            if not self._state.is_set() or self._source is None:
                # wait until we aren't
                self._state.wait()
                continue
            # are we disconnected from voice?
            if not self.client._connected.is_set():
                # wait until we are connected
                self.client._connected.wait()
                # reset our internal data
                self.loops = 0
                self._start = perf_counter()

            self.loops += 1
            data = self._source.read()
            if not data:
                music = self.client.client.get_cog('Music')
                session = music.sessions[self.client.guild.id]
                self.status = False
                if self.loop:
                    self.loops = 0
                    self._stamp = 0
                    self.play()
                    asyncio.run_coroutine_threadsafe(music.i_update(session), self.client.client.loop)
                else:
                    # if self._index+1 < len(self._queue):
                    self.index += 1
                    self.loops = 0
                    self._stamp = 0
                    self._of = 0
                    if self._index < len(self._queue):
                        self.play()
                        asyncio.run_coroutine_threadsafe(music.i_update(session), self.client.client.loop)
                    else:
                        self._state.clear()
                        self._speak(False)
                        asyncio.run_coroutine_threadsafe(music.i_update(session), self.client.client.loop)
                        self._state.wait()
            # print(data)

            play_audio(data, encode=not self._source.is_opus())
            next_time = self._start + self.DELAY * self.loops
            delay = max(0, self.DELAY + (next_time - perf_counter()))
            sleep(delay)

    def after(self):
        pass

    def stop(self):
        self._state.clear()
        self._speak(False)
        self._stop = True

    def pause(self):
        self._stamp += self.loops*self.DELAY
        self.loops = 0
        self._state.clear()
        self._speak(False)

    def resume(self):
        self.loops = 0
        self._start = perf_counter()
        self._state.set()
        self._speak(True)


    def is_playing(self):
        return self._state.is_set() and self.status

    def is_paused(self):
        return not self._state.is_set()

    def _set_source(self, source):
        with self._lock:
            self.pause()
            self.source = source
            self.resume()

    def _speak(self, speaking):
        asyncio.run_coroutine_threadsafe(self.client.ws.speak(speaking), self.client.loop)

    @property
    def of(self):
        return self._of
    
    @of.setter
    def of(self, seconds: int):
        self._of = seconds
        self.play()

    @property
    def to(self):
        return self._to
    
    @to.setter
    def to(self, seconds: int):
        self._to = seconds
        self.play()

    @property
    def source(self):
        return self._source
    
    @source.setter
    def source(self):
        pass

    @property
    def track(self):
        if len(self._queue) > self._index:
            item = self._items[self._queue[self._index][0]]
            if isinstance(item, (VkontakteTrack, YouTubeTrack)):
                return item

            if isinstance(item, (VkontakteAlbum, YouTubeAlbum)):
                return item.tracks[self._queue[self._index][1]]
        return

    @property
    def index(self):
        return self._index

    @index.setter
    def index(self, digit: int):
        self._index = min(max(digit, 0), len(self._queue))
        self._stand = max(self._index, self._stand)
        self._of = 0
        self._to = 0
        self._stamp = 0
        self.play()
        asyncio.run_coroutine_threadsafe(self.music.q_update(self.session), self.client.client.loop)


    @property
    def timestamp(self):
        # timestamp = self.loops*(self.DELAY*((self._filters.get('asetrate') or 48000)/48000))+self.stamp

        return self.loops*self.DELAY+self._stamp+self._of

    def play(self):
        if self.track:
            if self.track.url:
                session = self.music.sessions[self.client.guild.id]
                # if self.index is not None:
                #     self._resumed.clear()

                #     start = self.timestamp if self.s == None else max(self.timestamp, self.s)
                #     end = self.track.duration if self.e == None else min(self.track.duration, self.e)

                #     self._filters = self.filters

                codec = self.track.codec
                # codec = '' if self._filters else self.track.codec
                if codec == 'opus':
                    self._stamp = -(self._of%10)
                # else:
                #     self.stamp = start

                source = discord.FFmpegOpusAudio(executable='windows/ffmpeg' if sys.platform == 'win32' else 'linux/ffmpeg',
                    source=self.track.url,
                    codec=codec,
                    before_options=f'{"-http_persistent false " if codec == "m3u8" else ""}-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -ss {self._of+self._stamp+.1}',
                    options='-vn'
                    # options=f'-vn -filter:a {self.options}' if self._filters else '-vn'
                )
                self._source = source
                self.loops = 0
                self._start = perf_counter()
                self._state.set()
                self.status = True
            else:
                self._source = None
        else:
            self._source = None


    # @property
    # def options(self):
    #     if self._filters:
    #         l = []
    #         for f, v in self._filters.items():
    #             if isinstance(v, dict):
    #                 items = list(v.items())
    #                 l.append(':'.join([f'{f}={items[0][0]}={items[0][1]}']+[f'{i[0]}={i[1]}' for i in items[1:] if i[1] is not None]))
    #             elif v is not None:
    #                 l.append(f'{f}={v}')
    #         return '"'+','.join(l)+'"'
    #     else:
    #         return ''



    @property
    def total(self):
        duration = 0
        for item in self._items:
            if isinstance(item, (VkontakteTrack, YouTubeTrack)):
                duration+=int(item.duration)
            if isinstance(item, (VkontakteAlbum, YouTubeAlbum)):
                duration+=sum([int(track.duration) for track in item.tracks])
        return duration


    @property
    def loop(self):
        return self._loop
    
    @loop.setter
    def loop(self, arg: bool):
        self.loop = arg

    @property
    def mix(self):
        return self._mix
    
    @mix.setter
    def mix(self, arg: bool):
        if self._mix != arg:
            self._mix = arg
            if arg:
                self._queue = self._queue[:self._stand+1]+random.sample(self._queue[self._stand+1:], len(self._queue[self._stand+1:]))
            else:
                self._queue = self._queue[:self._stand+1]+sorted(self._queue[self._stand+1:])
            asyncio.run_coroutine_threadsafe(self.music.q_update(self.session), self.client.client.loop)


    @property
    def queue(self):
        items = list()
        for index in self._queue:
            item = self._items[index[0]]
            if isinstance(item, (VkontakteTrack, YouTubeTrack)):
                items.append(item)

            if isinstance(item, (VkontakteAlbum, YouTubeAlbum)):
                items.append(item.tracks[index[1]])
        return items

    @queue.setter
    def queue(self, items):
        if not isinstance(items, (list, tuple)):
            items = [items]
        for item in items:
            if isinstance(item, (VkontakteTrack, YouTubeTrack)):
                self._items.append(item)
                if self._mix:
                    self._queue.insert(random.randint(self._index, len(self._queue)), (self._items.index(item), 0))
                else:
                    self._queue.append((self._items.index(item), 0))

            if isinstance(item, (VkontakteAlbum, YouTubeAlbum)):
                self._items.append(item)
                if self._mix:
                    [self._queue.insert(random.randint(self._index, len(self._queue)), (self._items.index(item), i)) for i in range(len(item.tracks))]
                else:
                    self._queue.extend([(self._items.index(item), i) for i in range(len(item.tracks))])
        asyncio.run_coroutine_threadsafe(self.music.q_update(self.session), self.client.client.loop)



class Music(commands.Cog):
    def __init__(self, api):
        self.api = api
        self.vk = Vkontakte(path='data/tokens/vkontakte')
        self.yt = YouTube(path='data/tokens/youtube')
        self.sessions = dict()
        self.commands = {
            r'^(?:s!|\s*)?(?:j|join|войти)(?:\s+(?P<id>.+))?\s*$': self.connect,
            r'^(?:s!|\s*)?(?:l|leave|выйти)\s*$': self.disconnect,

            r'^(?:s!|\s*)?(?:h|help|помощь)\s*$': self.help,

            r'^(?:s!|\s*)?(?:(?:(?:p|play|играть)\s+)?(?P<url>(?:https?://).+[^\s]?))|(?:p|play|играть)\s+(?P<name>.+)\s*$': self.play,
            r'^(?:s!|\s*)?(?:[+]|resume|возобновить)\s*$': self.resume,
            r'^(?:s!|\s*)?(?:[-]|pause|пауза)\s*$': self.pause,

            r'^(?:s!|\s*)?(?:[=]|index|skip|пропустить)\s+(?P<count>[-]?\d+)\s*$': self.index,
            r'^(?:s!|\s*)?(?P<next>[>]+)(?:\s+(?P<count>[-]?\d+))?\s*$': self.next,
            r'^(?:s!|\s*)?(?P<back>[<]+)(?:\s+(?P<count>[-]?\d+))?\s*$': self.back,

            # r'^(?:s!|\s*)?(?:r|re)\s*$': self.re,
            r'^(?:s!|\s*)?(?:q|queue|очередь)\s*$': self.queue,
            r'^(?:s!|\s*)?(?:s|search|искать|поиск)\s+(?P<search>.+)$': self.search,
            r'^(?:s!|\s*)?(?:(?:choice|выбрать)\s+)?(?P<number>[-]?\d+)\s*$': self.choice,
            r'^(?:s!|\s*)?(?::|set|поставить)\s+(?:(?:(?P<shour>\d+)[.:])?(?:(?P<sminute>\d+)[.:]))?(?P<ssecond>\d+)(?:\s+(?:(?:(?P<ehour>\d+)[.:])?(?:(?P<eminute>\d+)[.:]))?(?P<esecond>\d+))?\s*$': self.set,
            
            # r'^(?:s!|\s*)?(?:f|filter|фильтр)\s+(?P<filter>\w+)(?:\s+(?P<name>[_a-zA-Z]+))?(?:\s+(?P<value>[-]?(?:\d+(?:[.]\d*)?)|(?:\d*[.]\d+)))\s*$': self.filter,


            # r'^(?:s!|\s*)?(?:n|nightcore|быстро)\s*$': self.nightcore,
            # r'^(?:s!|\s*)?(?:v|vaporwave|slowed|медленно)\s*$': self.vaporwave,
            # r'^(?:s!|\s*)?(?:d|default|обычно)\s*$': self.default,
            # r'^(?:s!|\s*)?8[dD]\s*$': self.sd,
        }
        self.language = 'gb'
        self.languages = {
            'ru': {
                'interface': ('позиция', 'создано', 'очередь', 'элементы', 'продолжительность', 'прошло', 'остались'),
            },
            'gb': {
                'interface': ('position', 'created', 'queue', 'items', 'duration', 'passed', 'left'),
            },
            'ua': {
                'interface': ('позиція', 'створено', 'чергу', 'елементи', 'тривалість', 'пройшло', 'залишилися'),
            },
            'pt': {
                'interface': ('posição', 'criada', 'fila', 'os elementos', 'duração', 'passado', 'fiquei'),
            },
        }

        self.interface = {}
        self.emojis = ['🔀', '⏪', '⏯️', '⏩', '🔁', '🌐']
        self.embed = {"state": ['▶️', "⏸"], "loop": ["🔁", "🔂"], "mix": ["🔃", "🔀"]}
        
        self.auth.start()
        self.task.start()

    @tasks.loop(hours=24)
    async def auth(self):
        self.vk.auth(reboot=True)

    @tasks.loop(seconds=1)
    async def task(self):
        if self.sessions:
            for id, session in self.sessions.items():
                if 'client' in session:
                    client = session['client']
                    if client._player:
                        if 'interface' in session:
                            interface = session['interface']
                            if client._player.is_playing() and 'output' in interface:
                                await self.i_update(session)
                        else:
                            await self.i_update(session)
    
    def i_args(self, session: dict):
        
        args = dict()

        if 'interface' not in session:
            session['interface'] = dict()
        interface = session['interface']
        player = session['client']._player
            
        if 'r' not in interface:
            interface['r'] = random.randint(0, 128)
        else:
            interface['r'] = min(interface['r']+random.randint(0, 16), 255) if interface['r'] < 255 else random.randint(0, 128)

        if 'g' not in interface:
            interface['g'] = random.randint(0, 128)
        else:
            interface['g'] = min(interface['g']+random.randint(0, 16), 255) if interface['g'] < 255 else random.randint(0, 128)

        if 'b' not in interface:
            interface['b'] = random.randint(0, 128)
        else:
            interface['b'] = min(interface['b']+random.randint(0, 16), 255) if interface['b'] < 255 else random.randint(0, 128)


        language = self.languages[self.language]['interface']
        if player:
            description = f'`{language[0]} :` **{player._index if player.track else 0}**\n`{language[1]} :` **{player._stand if player.track else 0}**\n`{language[2]} :` **{len(player._queue)}**\n`{language[3]} :` **{len(player._items)}**\n`{language[4]} :` **{timedelta(seconds=player.total)}**\n`{language[5]} :` **{timedelta(seconds=int(player.client.timestamp/48000))}**\n:flag_{self.language}:'
        
            a = self.embed["mix"][int(player._mix)]
            b = self.embed["state"][int(player.is_playing())]
            c = self.embed["loop"][int(player._loop)]

            content = f'{a}{b}{c}'

            embed = discord.Embed(title=f'{player.track.title if player.track else "None"}', description=description, color=int('%02x%02x%02x' % (interface['r'], interface['g'], interface['b']), 16), timestamp=datetime.utcnow())

            if player.track:
                if player.track.duration:
                    timestamp = '`'+'▬'*int(24*(player.timestamp/player.track.duration))+'🔘'+'▬'*int(24-24*(player.timestamp/player.track.duration))+'`'
                    embed.add_field(name=f'__{timedelta(seconds=int(player.timestamp))}__ / __{timedelta(seconds=player.track.duration-int(player.timestamp))}__', value=timestamp, inline=False)
                else:
                    timestamp = '`'+'▬'*48+'🔘`'
                    embed.add_field(name=f'__{timedelta(seconds=int((datetime.now()-player.track.start).total_seconds()-10800))}__ / __{timedelta(seconds=0)}__', value=timestamp, inline=False)
            else:
                timestamp = '`'+'▬'*48+'🔘`'
                embed.add_field(name=f'__{timedelta(seconds=0)}__ / __{timedelta(seconds=0)}__', value=timestamp, inline=False)


            if player.track:
                embed.set_author(name=f'{player.track.author if player.track else "None"}', icon_url=player.track.main.urls['icon'] if player.track else None)
                embed.set_footer(text=timedelta(seconds=player.track.duration if player.track else 0))
                embed.set_thumbnail(url=player.track.cover)
        else:
            content = 'None'
            embed = None
        args['content'] = content
        args['embed'] = embed
        return args
    
    async def i_update(self, session):
        if 'interface' not in session:
            session['interface'] = dict()
        interface = session['interface']

        args = self.i_args(session)

        if 'output' in interface:
            try:
                await interface['output'].edit(content=args['content'], embed=args['embed'])
            except NotFound:
                pass

        else:
            try:
                interface['output'] = await session['channel'].send(content=args['content'], embed=args['embed'])
                for emoji in self.emojis:
                    await interface['output'].add_reaction(emoji)
            except NotFound:
                pass

    async def connect(self, message, channel=None):

        if message.author.voice or channel:
            if message.guild.id not in self.sessions:
                self.sessions[message.guild.id] = dict({'guild': message.guild})
            session = self.sessions[message.guild.id]

            if 'client' not in session:
                if channel is not None:
                    if isinstance(channel, VoiceChannel):
                        session['client'] = await channel.connect()
                    else:
                        try:
                            int(channel)
                        except ValueError:
                            return 'id канала должен состоять из цифр!'
                        voice = session['guild'].get_channel(int(channel))
                        if voice:
                            session['client'] = await voice.connect()
                        else:
                            return 'канал не найден!'
                else:
                    session['client'] = await message.author.voice.channel.connect()
                client = session['client']
                client._player = Player(client)
                client._player.start()
                session['channel'] = message.channel
                return True
            else:
                client = session['client']
                if channel is not None:
                    if isinstance(channel, VoiceChannel):
                        await client.move_to(channel)
                    else:
                        try:
                            int(channel)
                        except ValueError:
                            return 'id канала должен состоять из цифр!'
                        voice = session['guild'].get_channel(int(channel))
                        if voice:
                            await client.move_to(voice)
                            return True
                        else:
                            return 'канал не найден!'
                else:
                    return 'бот уже подкючен!'
        else:
            return 'вас нет в голосовом канале!'
                
    async def disconnect(self, message):
        if message.guild.id in self.sessions:
            session = self.sessions[message.guild.id]
            if 'client' in session:
                client = session.pop('client')
                player = client._player
                if player:
                    player.stop()
                await client.disconnect(force=True)
                if 'interface' in session:
                    interface = session.pop('interface')
                    await interface['output'].delete()
                return True
            else:
                return 'бот не подключен!'
        else:
            return 'сессия не создана!'
        
    async def play(self, message, url: str, name: str):
        if message.author.voice:
            if url:
                item = self.vk.get_item(url) or self.yt.get_item(url)
            elif name:
                yts = self.yt.search(name, {'album': 0, 'track': 1})['tracks']
                if yts:
                    item = yts[0]
                else:
                    vks = self.vk.search(name, {'album': 0, 'track': 1})['tracks']
                    if vks:
                        item = vks[0]
                    else:
                        item = None
            if item:
                if message.guild.id not in self.sessions:
                    self.sessions[message.guild.id] = dict({'guild': message.guild})
                session = self.sessions[message.guild.id]
                if 'client' not in session:
                    await self.connect(message=message)
                session['client']._player.queue = item

                if not session['client']._player.status:
                    session['client']._player.play()
                return True
            else:
                return 'ничего не найдено!'

    async def pause(self, message):
        if message.author.voice:
            if message.guild.id in self.sessions:
                session = self.sessions[message.guild.id]
                if 'client' in session:
                    client = session['client']
                    player = client._player
                    player.pause()
                    await self.i_update(session)
                    return True
                return 'бот не подключен!'
            return 'сессия не создана!'
        return 'вас нет в голосовом канале!'
        
    async def resume(self, message):
        if message.author.voice:
            if message.guild.id in self.sessions:
                session = self.sessions[message.guild.id]
                if 'client' in session:
                    client = session['client']
                    player = client._player
                    player.resume()
                    await self.i_update(session)
                    return True
                return 'бот не подключен!'
            return 'сессия не создана!'
        return 'вас нет в голосовом канале!'
        
    async def index(self, message, count: int):
        if message.author.voice:
            if message.guild.id in self.sessions:
                session = self.sessions[message.guild.id]
                if 'client' in session:
                    client = session['client']
                    player = client._player
                    player.index = int(count)
                    await self.i_update(session)
                    return True
                return 'бот не подключен!'
            return 'сессия не создана!'
        return 'вас нет в голосовом канале!'

    async def next(self, message, command: str, count: int):
        if message.author.voice:
            if message.guild.id in self.sessions:
                session = self.sessions[message.guild.id]
                if 'client' in session:
                    client = session['client']
                    player = client._player
                    player.index += abs(len(command)*(int(count) if count else 1))
                    await self.i_update(session)
                    return True
                return 'бот не подключен!'
            return 'сессия не создана!'
        return 'вас нет в голосовом канале!'


    async def back(self, message, command: str, count: int):
        if message.author.voice:
            if message.guild.id in self.sessions:
                session = self.sessions[message.guild.id]
                if 'client' in session:
                    client = session['client']
                    player = client._player
                    player.index -= abs(len(command)*(int(count) if count else 1))
                    await self.i_update(session)
                    return True
                return 'бот не подключен!'
            return 'сессия не создана!'
        return 'вас нет в голосовом канале!'

    def q_args(self, member):
        args = dict()
        if member.guild.id in self.sessions:
            session = self.sessions[member.guild.id]
            if 'client' in session:
                client = session['client']
                player = client._player
                if 'users' in session:
                    if member.id in session['users']:
                        user = session['users'][member.id]
                        queue = user['queue']


                        embed = discord.Embed(title=f'Page: `{queue["page"]}/{len(player._queue)//9}`', description='', color=0x69cf03, timestamp=datetime.utcnow())
                        page = player.queue[queue['page']*9:queue['page']*9+9]
                        for index in range(len(page)):
                            item = page[index]
                            embed.add_field(name=f'`{queue["page"]*9+index}`'+item.author, value='**`'+item.title+'`**' if player._index == queue['page']*9+index else item.title)

                        args['embed'] = embed
                        return args
    
    async def q_update(self, session):

        if 'users' in session:
            users = session['users']
            for id, user in users.items():
                if 'queue' in user:
                    queue = user['queue']
                    if 'guild' in session:
                        guild = session['guild']
                        member = guild.get_member(id)
                        args = self.q_args(member)

                        if 'output' in queue:
                            try:
                                await queue['output'].edit(embed=args['embed'])
                            except NotFound:
                                pass
                        else:
                            if 'input' in queue:
                                try:
                                    queue['output'] = await queue['input'].channel.send(embed=args['embed'])
                                    await queue['output'].add_reaction('⬅️')
                                    await queue['output'].add_reaction('➡️')
                                    await queue['output'].add_reaction('⏹️')
                                except NotFound:
                                    pass

    async def queue(self, message):
        if message.guild.id in self.sessions:
            session = self.sessions[message.guild.id]

            if 'client' in session:
                client = session['client']
                player = client._player

                if 'users' not in session:
                    session['users'] = dict()
                users = session['users']

                if message.author.id not in users:
                    users[message.author.id] = dict()
                user = users[message.author.id]

                if 'queue' not in user:
                    user['queue'] = dict()
                queue = user['queue']

                if 'output' in queue:
                    await queue['output'].delete()
                    del queue['output']

                queue['page'] = int(player.index//9)
                queue['input'] = message
                await self.q_update(session)

                return True
            else:
                return 'бот не подключен!'
        else:
            return 'сессия не создана!'

    def s_args(self, member):
        args = dict()
        session = self.sessions[member.guild.id]
        user = session['users'][member.id]
        search = user['search']
        vks = search['vkontakte']
        yts = search['youtube']

        embed = discord.Embed(title=f'🔎 __**`{search["string"]}`**__', description='')
        if vks['albums']:
            embed.add_field(
                name=f'`Type`**:** __**VkontakteAlbum**__',
                value='\n'.join([('**'+str(i)+'**' if i in search['choice'] else str(i))+f'. [{vks["albums"][i].title}](https://vk.com/music/album/{vks["albums"][i].owner}_{vks["albums"][i].album}_{vks["albums"][i].access}) | `{timedelta(seconds=vks["albums"][i].duration)}`' for i in range(len(vks["albums"]))]),
                inline=False
            )
        if vks['tracks']:
            embed.add_field(
                name=f'`Type`**:** __**VkontakteTrack**__',
                value='\n'.join([('**'+str(i+len(vks["albums"]))+'**' if i+len(vks["albums"]) in search['choice'] else str(i+len(vks["albums"])))+f'. [{vks["tracks"][i].title}]({vks["tracks"][i].url.split("m3u8")[0]}m3u8) | `{timedelta(seconds=vks["tracks"][i].duration)}`' for i in range(len(vks["tracks"]))]),
                inline=False
            )
        if yts['albums']:
            embed.add_field(
                name=f'`Type`**:** __**YouTubeAlbum**__',
                value='\n'.join([('**'+str(i+len(vks["albums"])+len(vks["tracks"]))+'**' if i+len(vks["albums"])+len(vks["tracks"]) in search['choice'] else str(i+len(vks["albums"])+len(vks["tracks"])))+f'. [{yts["albums"][i].title}](https://www.youtube.com/playlist={yts["albums"][i].id}) | `{timedelta(seconds=yts["albums"][i].duration)}`' for i in range(len(yts["albums"]))]),
                inline=False
            )
        if yts['tracks']:
            embed.add_field(
                name=f'`Type`**:** __**YouTubeTrack**__',
                value='\n'.join([('**'+str(i+len(vks["albums"])+len(vks["tracks"])+len(yts["albums"]))+'**' if i+len(vks["albums"])+len(vks["tracks"])+len(yts["albums"]) in search['choice'] else str(i+len(vks["albums"])+len(vks["tracks"])+len(yts["albums"])))+f'. [{yts["tracks"][i].title}](https://www.youtube.com/watch?v={yts["tracks"][i].id}) | `{timedelta(seconds=yts["tracks"][i].duration)}`' for i in range(len(yts["tracks"]))]),
                inline=False
            )
        embed.set_author(name=member.name, icon_url=member.avatar_url)
        embed.set_footer(text='Time: {:.3}'.format(search['time']), icon_url=self.api.user.avatar_url)
        args['embed'] = embed
        return args
    
    async def s_update(self, member):
        if member.guild.id in self.sessions:
            session = self.sessions[member.guild.id]
            if 'users' in session:
                users = session['users']
                if member.id in users:
                    user = users[member.id]
                    if 'search' in user:
                        search = user['search']
                        args = self.s_args(member)
                        if 'output' in search:
                            try:
                                await search['output'].edit(embed=args['embed'])
                            except NotFound:
                                pass
                        else:
                            if 'input' in search:
                                try:
                                    search['output'] = await search['input'].channel.send(embed=args['embed'])
                                    await search['output'].add_reaction('⏹️')
                                except NotFound:
                                    pass

    async def search(self, message, string: str):

        if message.guild.id not in self.sessions:
            self.sessions[message.guild.id] = dict({'guild': message.guild})
        session = self.sessions[message.guild.id]

        if 'users' not in session:
            session['users'] = dict()
        if message.author.id not in session['users']:
            session['users'][message.author.id] = dict()
        user = session['users'][message.author.id]

        if 'search' in user:
            await user['search']['output'].delete()
        else:
            user['search'] = dict()

        search = user['search']
        
        search['input'] = message
        search['string'] = string
        time = perf_counter()
        search['youtube'] = self.yt.search(string, {'album': 1, 'track': 4})
        search['vkontakte'] = self.vk.search(string, {'album': 1, 'track': 4})
        search['time'] = perf_counter()-time
        search['choice'] = list()
        await self.s_update(message.author)
        return True

    async def choice(self, message, number: int):
        if message.guild.id not in self.sessions:
            self.sessions[message.guild.id] = dict({'guild': message.guild})
        session = self.sessions[message.guild.id]
        if 'users' in session:
            users = session['users']
            if message.author.id in users:
                user = users[message.author.id]
                if 'search' in user:
                    search = user['search']
                    for digit in number:
                        choice = min(max(int(digit), 0), search['vkontakte']['count']+search['youtube']['count']-1)
                        if choice in search['choice']:
                            search['choice'].remove(choice)
                        else:
                            search['choice'].append(choice)
                    await self.s_update(message.author)
                if 'client' in session:
                    client = session['client']
                    player = client._player
                    if 'queue' in user:
                        queue = user['queue']
                        queue['page'] = max(min(int(number), len(player._queue)//9), 0)
                        await self.q_update(session)
                return True

    async def set(self, message, fhour:int, fminute:int, fsecond:int, thour:int, tminute:int, tsecond:int):
        if message.author.voice:
            if message.guild.id in self.sessions:
                session = self.sessions[message.guild.id]
                if 'client' in session:
                    client = session['client']
                    player = client._player

                    of = 0
                    to = 0

                    if fsecond:
                        of+=int(fsecond)
                    if fminute:
                        of+=60*int(fminute)
                    if fhour:
                        of+=3600*int(fhour)

                    if tsecond:
                        to+=int(tsecond)
                    if tminute:
                        to+=60*int(tminute)
                    if thour:
                        to+=3600*int(thour)

                    player._of = min(of, player.track.duration)
                    player._to = min(to, player.track.duration)
                    # player._stamp = 0
                    # player.loops = 0
                    player.play()
                    await self.i_update(session)
                    return True
                # else:
                #     return 'точка начала должна быть меньше чем точка конца'
                else:
                    return 'бот не подключен!'
            else:
                return 'сессия не создана!'
        return 'вас нет в голосовом канале!'
    
    async def help(self, message):
        if message.author.voice:
            if message.guild.id not in self.sessions:
                self.sessions[message.guild.id] = dict({'guild': message.guild})
            session = self.sessions[message.guild.id]
            if 'users' not in session:
                session['users'] = dict()
            users = session['users']

            content = open('help.txt', 'r', encoding='utf-8').read()
            output = await message.channel.send(content=content)
            try:
                await output.add_reaction('⏹️')
            except NotFound:
                pass

            if message.author.id not in users:
                users[message.author.id] = dict()
            user = users[message.author.id]
            if 'help' not in user:
                user['help'] = dict()
            help = user['help']
            if 'output' in help:
                try:
                    await help['output'].delete()
                except NotFound:
                    pass

            help['output'] = output
            return True


    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.id == self.api.user.id:
            if before.channel is not None:
                if before.channel.guild.id in self.sessions:
                    session = self.sessions[before.channel.guild.id]
                    if 'client' in session:
                        client = session['client']
                        player = client._player
                        if after.channel == None:
                            if player:
                                player.stop()
                            await client.disconnect(force=True)
                            del session['client']
                            if 'interface' in session:
                                await session['interface']['output'].delete()
                                del session['interface']
                        else:
                            player._stamp += player.loops*player.DELAY
                            self.loops = 0
                            # self._start = perf_counter()

    # @commands.Cog.listener()
    # async def on_voice_server_update(self, data):
    #     print(data)

    # @commands.Cog.listener()
    # async def on_ready(self):
    #     pass

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.author.bot:
            status = []
            for line in str(message.content).split('\n'):
                for r in self.commands:
                    command = re.match(r, line)
                    if command:
                        state = await self.commands[r](message, *command.groups())
                        if state is True:
                            status.append(True)
                        else:
                            status.append(False)
                            if isinstance(state, str):
                                await message.channel.send(state)
                        break
            if any(status):
                await message.delete(delay=.1)

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.guild.id in self.sessions:
            session = self.sessions[message.guild.id]
            if 'interface' in session:
                interface = session['interface']
                if 'output' in interface:
                    if message.id == interface['output'].id:
                        if 'client' in session:
                            del interface['output']
                            await self.i_update(session)

    def lang(self):
        lang = list(self.languages.keys())
        self.language = lang[lang.index(self.language)+1 if lang.index(self.language)+1 <= len(lang)-1 else 0]

    async def payload(self, payload):
        if payload.user_id != self.api.user.id:
            if payload.guild_id not in self.sessions:
                self.sessions[payload.guild_id] = dict({'guild': self.api.get_guild(payload.guild_id)})
            session = self.sessions[payload.guild_id]
            
            if 'interface' in session:
                interface = session['interface']
                if 'output' in interface:
                    if payload.message_id == interface['output'].id:
                        if 'client' in session:
                            client = session['client']
                            player = client._player
                            if payload.emoji.name == '🔀':
                                player.mix = not player._mix
                            if payload.emoji.name == '⏪':
                                player.index -= 1
                            if payload.emoji.name == '⏯️':
                                player.pause() if player._state.is_set() else player.resume()
                            if payload.emoji.name == '⏩':
                                player.index += 1
                            if payload.emoji.name == '🔁':
                                player._loop = not player._loop
                            if payload.emoji.name == '🌐':
                                self.lang()
                            await self.i_update(session)

            if 'users' in session:
                if payload.user_id in session['users']:
                    user = session['users'][payload.user_id]
                    
                    if 'help' in user:
                        help = user['help']
                        if 'output' in help:
                            if payload.message_id == help['output'].id:
                                if payload.emoji.name == '⏹️':
                                    await user['help']['output'].delete()
                                    del user['help']

                    if 'search' in user:
                        search = user['search']
                        if 'output' in search:
                            if payload.message_id == search['output'].id:
                                if payload.emoji.name == '⏹️':
                                    items = search['vkontakte']['albums']+search['vkontakte']['tracks']+search['youtube']['albums']+search['youtube']['tracks']
                                    item = [items[i] for i in search['choice']]

                                    if item:
                                        if 'client' not in session:
                                            await self.connect(search['output'], payload.member.voice.channel)
                                        client = session['client']
                                        player = client._player

                                        player.queue = item

                                        if not player.status:
                                            player.play()
                                        await self.i_update(session)
                                    await search['output'].delete()
                                    del user['search']

                    if 'queue' in user:
                        queue = user['queue']
                        if 'output' in queue:
                            if payload.message_id == queue['output'].id:
                                if 'client' in session:
                                    client = session['client']
                                    player = client._player

                                    if payload.emoji.name == '⬅️':
                                        queue['page'] = max(queue['page']-1, 0)
                                        await self.q_update(session)

                                    if payload.emoji.name == '➡️':
                                        queue['page'] = min(queue['page']+1, len(player._queue)//9)
                                        await self.q_update(session)

                                if payload.emoji.name == '⏹️':
                                    await queue['output'].delete()
                                    del user['queue']

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        await self.payload(payload)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        guild = self.api.get_guild(payload.guild_id)
        payload.member = guild.get_member(payload.user_id)
        await self.payload(payload)


def setup(bot):
    bot.add_cog(Music(bot))
