#>>>python<<<
import sys
import re
import json
import asyncio
from time import perf_counter, sleep
import random
from datetime import datetime, timedelta
import threading

#>>>discord<<<
import discord
from discord.ext import commands, tasks

#>>>others<<<
from .vkontakte import Vkontakte, VkontakteAlbum, VkontakteTrack
from .youtube import YouTube, YouTubeAlbum, YouTubeTrack



class Player(threading.Thread):
    DELAY = 0.02

    def __init__(self, client):
        threading.Thread.__init__(self)
        self.daemon = True

        self.source = None
        self.client = client

        self._index = None
        self._filters = {}
        self.filters = {}
        self.stamp = 0
        self.s = None
        self.e = None

        self.items = []
        self.queue = []
        self.songs = []

        self.mix = False
        self.loop = False

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
        self.embed = {"state": [":arrow_forward:", ":pause_button:"], "loop": [":repeat:", ":repeat_one:"], "mix": [":arrows_clockwise:", ":twisted_rightwards_arrows:"]}
        self.task.start()


        self._end = threading.Event()
        self._resumed = threading.Event()
        self._current_error = None
        self._connected = client._connected
        self._lock = threading.Lock()

    def run(self):
        self.loops = 0
        self._start = perf_counter()

        # getattr lookup speed ups
        play_audio = self.client.send_audio_packet
        self._speak(True)

        while not self._end.is_set():
            # are we paused?
            if not self._resumed.is_set():
                # wait until we aren't
                self._resumed.wait()
                continue

            # are we disconnected from voice?
            if not self._connected.is_set():
                # wait until we are connected
                self._connected.wait()
                # reset our internal data
                self.loops = 0
                self._start = perf_counter()

            self.loops += 1
            data = self.source.read()

            if not data:
                if self.loop:
                    self.loops = 0
                    self.stamp = 0
                    self.play()
                else:
                    if self.songs:
                        self.index = 1
                        self.loops = 0
                        self.stamp = 0
                        self.s = 0
                        self.play()
                    else:
                        self._resumed.clear()
                        self._speak(False)
                        self._resumed.wait()
                asyncio.run_coroutine_threadsafe(self.update(), self.client.client.loop)


            play_audio(data, encode=not self.source.is_opus())
            next_time = self._start + self.DELAY * self.loops
            delay = max(0, self.DELAY + (next_time - perf_counter()))
            sleep(delay)

    def after(self):
        pass

    def stop(self):
        self._end.set()
        self._resumed.set()
        self._speak(False)
        self.task.stop()
        for m in self.interface.values():
            asyncio.run_coroutine_threadsafe(m.delete(), self.client.client.loop)
        self.interface.clear()

    def pause(self, *, update_speaking=True):
        self._resumed.clear()
        if update_speaking:
            self._speak(False)
        self.stamp = self.timestamp

    def resume(self, *, update_speaking=True):
        self.loops = 0
        self._start = perf_counter()
        self._resumed.set()
        if update_speaking:
            self._speak(True)

    def change(self):
        if self.is_paused():
            self.resume()
        else:
            self.pause()


    def is_playing(self):
        return self._resumed.is_set() and not self._end.is_set()

    def is_paused(self):
        return not self._end.is_set() and not self._resumed.is_set()

    def _set_source(self, source):
        with self._lock:
            self.pause(update_speaking=False)
            self.source = source
            self.resume(update_speaking=False)

    def _speak(self, speaking):
        # try:
        asyncio.run_coroutine_threadsafe(self.client.ws.speak(speaking), self.client.loop)
        # except Exception as e:
        #     log.info("Speaking call in player failed: %s", e)


    @property
    def timestamp(self):
        # timestamp = self.loops*(self.DELAY*((self._filters.get('asetrate') or 48000)/48000))+self.stamp

        return self.loops*(self.DELAY*((self._filters.get('asetrate') or 48000)/48000))+self.stamp

    def play(self):
        with self._lock:
            if self.index is not None:
                self._resumed.clear()

                start = self.timestamp if self.s == None else max(self.timestamp, self.s)
                end = self.track.duration if self.e == None else min(self.track.duration, self.e)

                self._filters = self.filters

                codec = '' if self._filters else self.track.codec
                if codec == 'opus':
                    self.stamp = start//10*10
                else:
                    self.stamp = start

                source = discord.FFmpegOpusAudio(executable='lib/windows/ffmpeg' if sys.platform == 'win32' else 'lib/linux/ffmpeg',
                    source=self.track.url,
                    codec=codec,
                    before_options=f'-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -ss {start} -to {end}',
                    options=f'-vn -filter:a {self.options}' if self._filters else '-vn'
                )
                self.source = source
                self.loops = 0
                self._start = perf_counter()
                self._resumed.set()


    @property
    def options(self):
        if self._filters:
            l = []
            for f, v in self._filters.items():
                if isinstance(v, dict):
                    items = list(v.items())
                    l.append(':'.join([f'{f}={items[0][0]}={items[0][1]}']+[f'{i[0]}={i[1]}' for i in items[1:] if i[1] is not None]))
                elif v is not None:
                    l.append(f'{f}={v}')
            return '"'+','.join(l)+'"'
        else:
            return ''



    @property
    def track(self):
        if isinstance(self.index, int):
            return self.items[self.index]
        elif isinstance(self.index, tuple):
            return self.items[self.index[0]].tracks[self.index[1]]

    @property
    def total(self):
        duration = 0
        for item in self.items:
            if isinstance(item, (VkontakteTrack, YouTubeTrack)):
                duration+=int(item.duration)
            if isinstance(item, (VkontakteAlbum, YouTubeAlbum)):
                duration+=sum([int(track.duration) for track in item.tracks])
        return duration

    @property
    def count(self):
        count = len(self.queue) + len(self.songs)
        if self.index is not None and self.index not in self.queue: count+=1
        return count

    @property
    def index(self):
        return self._index

    @index.setter
    def index(self, count: float):
        index = self._index
        if self._index is not None:
            if self._index not in self.queue:
                 self.queue.append(self._index)

            if self._index in self.queue:
                count -= len(self.queue)-self.queue.index(self._index)
                if count >= 0:
                    count += 1


        number = min(max(-len(self.queue), count), len(self.songs))

        if number < 0:
            self._index = self.queue[number]

        if number > 0:
            if self.mix:
                self._index = self.songs.pop(random.randrange(len(self.songs)))
            else:
                self._index = self.songs.pop(number-1)

        self.stamp = 0
        self.loops = 0
        if self._index != index:
            self.s = None
            self.e = None
        
    def looping(self):
        self.loop = not self.loop

    def mixing(self):
        self.mix = not self.mix

    def add(self, item):
        if isinstance(item, (VkontakteTrack, YouTubeTrack)):
            self.items.append(item)
            self.songs.append(self.items.index(item))
            return True

        if isinstance(item, (VkontakteAlbum, YouTubeAlbum)):
            self.items.append(item)
            self.songs.extend((self.items.index(item), i) for i in range(len(item.tracks)))
            return True

    async def update(self, message=False):
        pos = len(self.queue) if self.index in self.queue else len(self.queue)+1
        p = self.queue.index(self.index)+1 if self.index in self.queue else pos
        
        interface = self.languages[self.language]['interface']

        description = f'`{interface[0]} :` **{p}**\n`{interface[1]} :` **{pos}**\n`{interface[2]} :` **{self.count}**\n`{interface[3]} :` **{len(self.items)}**\n`{interface[4]} :` **{timedelta(seconds=self.total)}**\n`{interface[5]} :` **{timedelta(seconds=int(self.client.timestamp/48000))}**\n:flag_{self.language}:'

        music = discord.Embed(title=f"{self.track.title}", description=description, color=0x0369cf, timestamp=datetime.utcnow())
        music.set_author(name=self.track.author, icon_url=self.track.main.urls['icon'])
        music.set_footer(text=timedelta(seconds=self.track.duration))
        music.set_thumbnail(url=self.track.cover)
        a = self.embed["mix"][int(self.mix)]
        b = self.embed["state"][int(self.is_playing())]
        c = self.embed["loop"][int(self.loop)]
        if not self.interface and message:
            self.interface['player'] = await message.channel.send(content=f"{a}{b}{c}", embed=music)
            self.interface['track'] = await message.channel.send(content=f"track")

            for e in self.emojis:
                if self.interface['player']:
                    await self.interface['player'].add_reaction(e)
        else:
            await self.interface['player'].edit(content=f'{a}{b}{c}', embed=music)

    def lang(self):
        lang = list(self.languages.keys())
        self.language = lang[lang.index(self.language)+1 if lang.index(self.language)+1 <= len(lang)-1 else 0]

    async def reload(self, message):
        self.task.stop()
        for m in self.interface.values():
            await m.delete()
        self.interface.clear()
        await self.update(message)
        self.task.start()

    async def buttons(self, payload):
        
        if payload.message_id == self.interface['player'].id:
            if payload.emoji.name in self.emojis:
                if payload.emoji.name == '🔀':
                    self.mixing()
                    await self.update()
                if payload.emoji.name == '⏪':
                    self.index = -1
                    self.play()
                    await self.update()
                if payload.emoji.name == '⏯️':
                    self.change()
                    await self.update()
                if payload.emoji.name == '⏩':
                    self.index = 1
                    self.play()
                    await self.update()
                if payload.emoji.name == '🔁':
                    self.looping()
                    await self.update()
                if payload.emoji.name == '🌐':
                    self.lang()
                    await self.update()
    
    @tasks.loop(seconds=1)
    async def task(self):
        if self.is_playing():
            total = self.track.duration
            timestamp = '`'+'▬'*int(64*(self.timestamp/total))+'🔘'+'▬'*int(64-64*(self.timestamp/total))+'`'
            track = discord.Embed(title=f'__{timedelta(seconds=int(self.timestamp))}__ / __{timedelta(seconds=total)}__', description=timestamp, color=0x0369cf)
            
            if 'track' in self.interface:
                await self.interface['track'].edit(content='', embed=track)

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.vk = Vkontakte(path='data/tokens/vkontakte.0')
        self.yt = YouTube(path='data/tokens/youtube.0')
        self.sessions = {}
        self.users = {}
        self.commands = {
            r'^(?:s!|\s*)?(?:j|join|войти)\s*$': self.connect,
            r'^(?:s!|\s*)?(?:l|leave|выйти)\s*$': self.disconnect,

            r'^(?:s!|\s*)?(?:h|help|помощь)\s*$': self.help,

            r'^(?:s!|\s*)?(?:(?:(?:p|play|играть)\s+)?(?P<url>(?:https?://).+[^\s]?))|(?:p|play|играть)\s+(?P<name>.+)\s*$': self.play,
            r'^(?:s!|\s*)?(?:[+]|resume|возобновить)\s*$': self.resume,
            r'^(?:s!|\s*)?(?:[-]|pause|пауза)\s*$': self.pause,

            r'^(?:s!|\s*)?(?:[=]|index|skip|пропустить)\s+(?P<count>[-]?\d+)\s*$': self.index,
            r'^(?:s!|\s*)?(?P<next>[>]+)(?:\s+(?P<count>[-]?\d+))?\s*$': self.next,
            r'^(?:s!|\s*)?(?P<back>[<]+)(?:\s+(?P<count>[-]?\d+))?\s*$': self.back,

            r'^(?:s!|\s*)?(?:r|re)\s*$': self.re,
            r'^(?:s!|\s*)?(?:s|search|искать|поиск)\s+(?P<search>.+)$': self.search,
            r'^(?:s!|\s*)?(?:(?:choice|выбрать)\s+)?(?P<number>[-]?\d+)\s*$': self.choice,
            r'^(?:s!|\s*)?(?::|set|поставить)\s+(?:(?:(?P<shour>\d+)[.:])?(?:(?P<sminute>\d+)[.:]))?(?P<ssecond>\d+)(?:\s+(?:(?:(?P<ehour>\d+)[.:])?(?:(?P<eminute>\d+)[.:]))?(?P<esecond>\d+))?\s*$': self.set,
            
            r'^(?:s!|\s*)?(?:f|filter|фильтр)\s+(?P<filter>\w+)(?:\s+(?P<name>[_a-zA-Z]+))?(?:\s+(?P<value>[-]?(?:\d+(?:[.]\d*)?)|(?:\d*[.]\d+)))\s*$': self.filter,


            r'^(?:s!|\s*)?(?:n|nightcore|быстро)\s*$': self.nightcore,
            r'^(?:s!|\s*)?(?:v|vaporwave|slowed|медленно)\s*$': self.vaporwave,
            r'^(?:s!|\s*)?(?:d|default|обычно)\s*$': self.default,
            r'^(?:s!|\s*)?8[dD]\s*$': self.sd,
        }
        self.update.start()

    @tasks.loop(hours=24)
    async def update(self):
        self.vk.auth(reboot=True)

    async def connect(self, message):
        if message.author.voice:
            if message.guild.id not in self.sessions:
                await message.delete()

                session = await message.author.voice.channel.connect()
                self.sessions[message.guild.id] = session

                session._player = Player(session)
                session._player.start()
                
    async def disconnect(self, message):
        if message.guild.id in self.sessions:
            await message.delete()

            session = self.sessions.pop(message.guild.id)
            # session._player.task.stop()
            # for m in session._player.interface.values():
            #     await m.delete()
            # session._player.interface.clear()
            session._player.stop()
            await session.disconnect()
            del session
        
    async def play(self, message, url: str, name: str):
        if message.author.voice:
            if url:
                item = self.vk.get_item(url) or self.yt.get_item(url)
            elif name:
                yts = self.yt.search(name, {'album': 0, 'track': 1})['tracks']
                if yts:
                    item = yts[0]
                else:
                    vks = self.yt.search(name, {'album': 0, 'track': 1})['tracks']
                    if vks:
                        item = vks[0]
            if item:
                await message.delete()

                if message.guild.id not in self.sessions:
                    session = await message.author.voice.channel.connect()
                    self.sessions[message.guild.id] = session
                    session._player = Player(session)
                    session._player.start()
                else:
                    session = self.sessions[message.guild.id]
                
                session._player.add(item)
                if session._player.source is None:
                    session._player.index = 1
                    session._player.play()
                
                await session._player.update(message)

    async def pause(self, message):
        if message.author.voice:
            if message.guild.id in self.sessions:
                await message.delete()

                session = self.sessions[message.guild.id]
                session._player.pause()
                await session._player.update()
        
    async def resume(self, message):
        if message.author.voice:
            if message.guild.id in self.sessions:
                await message.delete()

                session = self.sessions[message.guild.id]
                session._player.resume()
                await session._player.update()
        
    async def index(self, message, count: int):
        if message.author.voice:
            if message.guild.id in self.sessions:
                await message.delete()

                count = int(count)
                session = self.sessions[message.guild.id]
                if count > 0:
                    for _ in range(count):
                        session._player.index = 1
                if count < 0:
                    session._player.index = count
                session._player.s = 0
                session._player.play()
                await session._player.update()

    async def next(self, message, command: str, count: int):
        if message.author.voice:
            if message.guild.id in self.sessions:
                await message.delete()

                count = abs(len(command)*(int(count) if count else 1))
                session = self.sessions[message.guild.id]
                for _ in range(count):
                    session._player.index = 1
                session._player.s = 0
                session._player.play()
                await session._player.update()


    async def back(self, message, command: str, count: int):
        if message.author.voice:
            if message.guild.id in self.sessions:
                await message.delete()

                count = -abs(len(command)*(int(count) if count else -1))
                session = self.sessions[message.guild.id]
                session._player.index = count
                session._player.s = 0
                session._player.play()
                await session._player.update()


    async def search(self, message, string: str):
        if message.author.voice:
            await message.delete()

            if message.author.id in self.users:
                user = self.users[message.author.id]
                if 'search' in user:
                    await user['search']['message'].delete()
                    del user['search']
                    # print(self.users)
            else:
                self.users[message.author.id] = {}
                self.users[message.author.id]['search'] = {}
            t = perf_counter()
            vks = self.vk.search(string, {'album': 1, 'track': 5})
            yts = self.yt.search(string, {'album': 1, 'track': 5})

            embed = discord.Embed(title=f'🔎 __**`{string}`**__', description='')
            if vks['albums']:
                embed.add_field(
                    name=f'`Type`**:** __**VkontakteAlbum**__',
                    value='\n'.join([f'{i+1}. [{vks["albums"][i].title}](https://vk.com/music/album/{vks["albums"][i].owner}_{vks["albums"][i].album}_{vks["albums"][i].access}) | `{timedelta(seconds=vks["albums"][i].duration)}`' for i in range(len(vks["albums"]))]),
                    inline=False
                )
            if vks['tracks']:
                embed.add_field(
                    name=f'`Type`**:** __**VkontakteTrack**__',
                    value='\n'.join([f'{i+1+len(vks["albums"])}. [{vks["tracks"][i].title}]({vks["tracks"][i].url.split("mp3")[0]}mp3) | `{timedelta(seconds=vks["tracks"][i].duration)}`' for i in range(len(vks["tracks"]))]),
                    inline=False
                )
            if yts['albums']:
                embed.add_field(
                    name=f'`Type`**:** __**YouTubeAlbum**__',
                    value='\n'.join([f'{i+1+len(vks["albums"])+len(vks["tracks"])}. [{yts["albums"][i].title}](https://www.youtube.com/playlist={yts["albums"][i].id}) | `{timedelta(seconds=yts["albums"][i].duration)}`' for i in range(len(yts["albums"]))]),
                    inline=False
                )
            if yts['tracks']:
                embed.add_field(
                    name=f'`Type`**:** __**YouTubeTrack**__',
                    value='\n'.join([f'{i+1+len(vks["albums"])+len(vks["tracks"])+len(yts["albums"])}. [{yts["tracks"][i].title}](https://www.youtube.com/watch?v={yts["tracks"][i].id}) | `{timedelta(seconds=yts["tracks"][i].duration)}`' for i in range(len(yts["tracks"]))]),
                    inline=False
                )

            embed.set_author(name=message.author, icon_url=message.author.avatar_url)
            embed.set_footer(text='Time: {:.3}'.format(perf_counter()-t), icon_url=self.bot.user.avatar_url)

            search = await message.channel.send(embed=embed)
            await search.add_reaction('⏹️')

            self.users[message.author.id]['search'] = {'message': search, 'vkontakte': vks, 'youtube': yts}

    async def choice(self, message, number: int):
        if message.author.voice:
            user = self.users.get(message.author.id)
            if user:
                search = user.get('search')
                if search:
                    if search['message'].channel.id == message.channel.id:
                        await message.delete()
                        await search['message'].delete()

                        items = search['vkontakte']['albums']+search['vkontakte']['tracks']+search['youtube']['albums']+search['youtube']['tracks']
                        number = min(max(int(number), 1), len(items))
                        item = items[number-1]
                        del user['search']

                        if message.guild.id not in self.sessions:
                            session = await message.author.voice.channel.connect()
                            self.sessions[message.guild.id] = session
                            session._player = Player(session)
                            session._player.start()
                        else:
                            session = self.sessions[message.guild.id]

                        session._player.add(item)
                        if session._player.source is None:
                            session._player.index = 1
                            session._player.play()
                        await session._player.update(message)

    async def set(self, message, shour:int, sminute:int, ssecond:int, ehour:int, eminute:int, esecond:int):
        if message.author.voice:
            if message.guild.id in self.sessions:
                await message.delete()

                session = self.sessions[message.guild.id]

                start = 0
                end = 0

                if ssecond:
                    start+=int(ssecond)
                if sminute:
                    start+=60*int(sminute)
                if shour:
                    start+=3600*int(shour)

                if esecond:
                    end+=int(esecond)
                if eminute:
                    end+=60*int(eminute)
                if ehour:
                    end+=3600*int(ehour)

                if start >= end and end != 0:
                    end = start+end

                session._player.s = start if start else None
                session._player.e = end if end else None
                session._player.stamp = 0
                session._player.loops = 0
                session._player.play()
                await session._player.update(message)

    async def filter(self, message, f, n, v):
        if message.author.voice:
            if message.guild.id in self.sessions:
                await message.delete()

                v = float(v)

                session = self.sessions[message.guild.id]
                session._player.filters.update({f: {n: v} if n and v else n if n else v if v else None})
                session._player.play()
                await session._player.update(message)

    async def nightcore(self, message):
        if message.author.voice:
            if message.guild.id in self.sessions:
                await message.delete()

                session = self.sessions[message.guild.id]
                session._player.filters.update({'asetrate': 48000*(10/9)})
                session._player.play()
                await session._player.update(message)

    async def vaporwave(self, message):
        if message.author.voice:
            if message.guild.id in self.sessions:
                await message.delete()

                session = self.sessions[message.guild.id]
                session._player.filters.update({'asetrate': 48000*(9/10)})
                session._player.play()
                await session._player.update(message)

    async def sd(self, message):
        if message.author.voice:
            if message.guild.id in self.sessions:
                await message.delete()

                session = self.sessions[message.guild.id]
                session._player.filters.update({'apulsator': {'hz': 0.08}})
                session._player.play()
                await session._player.update(message)        

    async def default(self, message):
        if message.author.voice:
            if message.guild.id in self.sessions:
                await message.delete()

                session = self.sessions[message.guild.id]
                session._player.filters.clear()
                session._player.play()
                await session._player.update(message)
    
    async def re(self, message):
        if message.author.voice:
            if message.guild.id in self.sessions:
                await message.delete()

                session = self.sessions[message.guild.id]
                await session._player.reload(message)
    
    async def help(self, message):
        if message.author.voice:
            await message.delete()

            if message.author.id in self.users:
                user = self.users[message.author.id]
                if 'help' in user:
                    await user['help']['message'].delete()
                    del user['help']
            else:
                self.users[message.author.id] = {}
                self.users[message.author.id]['help'] = {}

            content = open('help.txt', 'r', encoding='utf-8').read()
            help = await message.channel.send(content=content)
            await help.add_reaction('⏹️')
            self.users[message.author.id]['help'] = {'message': help}


    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.id == self.bot.user.id:
            if before.channel is not None:
                if before.channel.guild.id in self.sessions:
                    if after.channel == None:

                        session = self.sessions.pop(before.channel.guild.id)
                        if session._player:
                            session._player.stop()
                        await session.disconnect(force=True)
                        del session

    @commands.Cog.listener()
    async def on_voice_server_update(self, data):
        print(data)

    @commands.Cog.listener()
    async def on_ready(self):
        pass

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.author.bot:
            for line in str(message.content).split():
                for r in self.commands:
                    command = re.match(r, line)
                    if command:
                        await self.commands[r](message, *command.groups())
                        break
            
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.user_id != self.bot.user.id:
            if payload.user_id in self.users:
                if payload.emoji.name == '⏹️':
                    user = self.users[payload.user_id]
                    if 'search' in user:
                        if payload.message_id == user['search']['message'].id:
                            await user['search']['message'].delete()
                            del user['search']
                    if 'help' in user:
                        if payload.message_id == user['help']['message'].id:
                            await user['help']['message'].delete()
                            del user['help']

            session = self.sessions.get(payload.guild_id)
            if session:
                await session._player.buttons(payload)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        if payload.user_id != self.bot.user.id:
            session = self.sessions.get(payload.guild_id)
            if session:
                await session._player.buttons(payload)


def setup(bot):
    bot.add_cog(Music(bot))
