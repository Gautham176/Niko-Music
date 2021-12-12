import discord
import wavelink
from discord.ext import commands
import typing as t
import asyncio
import re
import datetime as dt
import random
from enum import Enum
import aiohttp
import lyricsgenius
from discord_components import DiscordComponents, ComponentsBot, Button, Select, SelectOption
from discord import Webhook, AsyncWebhookAdapter

async def sendToWebhook(content):
 async with aiohttp.ClientSession() as session:
    webhook = Webhook.from_url('WEBHOOKURL',   adapter=AsyncWebhookAdapter(session))
    await webhook.send(content)

URL_REGEX = r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))"
LYRICS_URL = "https://some-random-api.ml/lyrics?title="
TIME_REGEX = r"([0-9]{1,2})[:ms](([0-9]{1,2})s?)?"
OPTIONS = {
    "1️⃣": 0,
    "2⃣": 1,
    "3⃣": 2,
    "4⃣": 3,
    "5⃣": 4,
}

class AlreadyConnectedToChannel(commands.CommandError):
    pass

class NoVoiceChannel(commands.CommandError):
    pass
    
class QueueIsEmpty(commands.CommandError):
    pass

class NoTracksFound(commands.CommandError):
    pass
    
class PlayerIsAlreadyPaused(commands.CommandError):
    pass
    
class NoMoreTracks(commands.CommandError):
    pass

class NoPreviousTracks(commands.CommandError):
    pass
    
class VolumeTooLow(commands.CommandError):
    pass


class VolumeTooHigh(commands.CommandError):
    pass


class MaxVolume(commands.CommandError):
    pass


class MinVolume(commands.CommandError):
    pass
    
class NoLyricsFound(commands.CommandError):
    pass
    
class InvalidTimeString(commands.CommandError):
    pass
    
class RepeatMode(Enum):
    STOP = 0
    SONG = 1
    QUEUE = 2

class Queue:
    def __init__(self):
        self._queue = []
        self.position = 0
        self.repeat_mode = RepeatMode.STOP

    @property
    def is_empty(self):
        return not self._queue

    @property
    def current_track(self):
        if not self._queue:
            raise QueueIsEmpty

        if self.position <= len(self._queue) - 1:
            return self._queue[self.position]

    @property
    def upcoming(self):
        if not self._queue:
            raise QueueIsEmpty

        return self._queue[self.position + 1:]

    @property
    def history(self):
        if not self._queue:
            raise QueueIsEmpty

        return self._queue[:self.position]

    @property
    def length(self):
        return len(self._queue)

    def add(self, *args):
        self._queue.extend(args)

    def get_next_track(self):
        if not self._queue:
            raise QueueIsEmpty

        self.position += 1

        if self.position < 0:
            return None
        elif self.position > len(self._queue) - 1:
            if self.repeat_mode == RepeatMode.QUEUE:
                self.position = 0
            else:
                return None

        return self._queue[self.position]

    def shuffle(self):
        if not self._queue:
            raise QueueIsEmpty

        upcoming = self.upcoming
        random.shuffle(upcoming)
        self._queue = self._queue[:self.position + 1]
        self._queue.extend(upcoming)

    def set_repeat_mode(self, mode):
        if mode == "stop":
            self.repeat_mode = RepeatMode.STOP
        elif mode == "song":
            self.repeat_mode = RepeatMode.SONG
        elif mode == "queue":
            self.repeat_mode = RepeatMode.QUEUE

    def empty(self):
        self.position = 0

class Player(wavelink.Player):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.queue = Queue()
        
    async def connect(self, ctx, channel=None):
        if self.is_connected:
            raise AlreadyConnectedToChannel

        if (channel := getattr(ctx.author.voice, "channel", channel)) is None:
            raise NoVoiceChannel

        await super().connect(channel.id)
        return channel

    async def teardown(self):
        try:
            await self.destroy()
        except KeyError:
            pass

    async def add_tracks(self, ctx, tracks):
        if not tracks:
            raise NoTracksFound

        if isinstance(tracks, wavelink.TrackPlaylist):
            self.queue.add(*tracks.tracks)
        elif len(tracks) == 1:
            self.queue.add(tracks[0])
            embed=discord.Embed(description=f":notes: Just added **{tracks[0].title}** to the queue!", color=discord.Colour.green())
            embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
            embed.set_footer(text="Tip : You can check the current queue with `niko queue`!")	
            await ctx.reply(embed=embed, mention_author=False)
        else:
            if (track := await self.choose_track(ctx, tracks)) is not None:
                self.queue.add(track)
                embed=discord.Embed(description=f":notes: Just added **{track.title}** to the queue!", color=discord.Colour.green())
                embed.set_footer(text="Tip : You can check the current queue with `niko queue`!")	
                embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
                await ctx.reply(embed=embed, mention_author=False)

        if not self.is_playing:
            await self.start_playback()
            
    async def choose_track(self, ctx, tracks):
        def _check(r, u):
            return (
                r.emoji in OPTIONS.keys()
                and u == ctx.author
                and r.message.id == msg.id
            )

        embed = discord.Embed(
            title="Pick a song from the list!",
            description=(
                "\n".join(
                    f"**{i+1}.** {t.title} ({t.length//60000}:{str(t.length%60).zfill(2)})"
                    for i, t in enumerate(tracks[:5])
                )
            ),
            colour=discord.Colour.green()
        )
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
        embed.set_footer(text="Please wait for the reactions to load before clicking on an option!")

        msg = await ctx.send(embed=embed)
        for emoji in list(OPTIONS.keys())[:min(len(tracks), len(OPTIONS))]:
            await msg.add_reaction(emoji)

        try:
            reaction, _ = await self.bot.wait_for("reaction_add", timeout=60.0, check=_check)
        except asyncio.TimeoutError:
            embed=discord.Embed(description=":no_entry_sign: Timeout! You were too **late** to reply!")
            embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
            await msg.edit(embed=embed)
            await ctx.message.edit()
        else:
            await msg.delete()
            return tracks[OPTIONS[reaction.emoji]]

    async def start_playback(self):
        await self.play(self.queue.current_track)
        
        
    async def advance(self):
      try:
           if (track := self.queue.get_next_track()) is not None:
             await self.play(track)
             
      except QueueIsEmpty:
          pass
          
    async def repeat_track(self):
        await self.play(self.queue.current_track)

class Music(commands.Cog, wavelink.WavelinkMixin):
    def __init__(self, bot):
        self.bot = bot
        self.wavelink = wavelink.Client(bot=bot)
        self.bot.loop.create_task(self.start_nodes())

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if not member.bot and after.channel is None:
            if not [m for m in before.channel.members if not m.bot]:
                await self.get_player(member.guild).teardown()
               

    @wavelink.WavelinkMixin.listener()
    async def on_node_ready(self, node):
        print(f"Music server is up!")
        
    @wavelink.WavelinkMixin.listener("on_track_stuck")
    @wavelink.WavelinkMixin.listener("on_track_end")
    @wavelink.WavelinkMixin.listener("on_track_exception")
    async def on_player_stop(self, node, payload):
        if payload.player.queue.repeat_mode == RepeatMode.SONG:
            await payload.player.repeat_track()
        else:
            await payload.player.advance()

    async def cog_check(self, ctx):
        if isinstance(ctx.channel, discord.DMChannel):
            await ctx.reply("Sorry, you can't use my music commands in a DM!")
            return False

        return True

    async def start_nodes(self):
        await self.bot.wait_until_ready()

        nodes = {
            "MAIN": {
                "host": "127.0.0.1",
                "port": 2333,
                "rest_uri": "http://127.0.0.1:2333",
                "password": "youshallnotpass",
                "identifier": "MAIN",
                "region": "asia",
            }
        }

        for node in nodes.values():
            await self.wavelink.initiate_node(**node)


    def get_player(self, obj):
        if isinstance(obj, commands.Context):
            return self.wavelink.get_player(obj.guild.id, cls=Player, context=obj)
        elif isinstance(obj, discord.Guild):
            return self.wavelink.get_player(obj.id, cls=Player)

    @commands.command(name="connect", aliases=["join"])
    async def connect_command(self, ctx, *, channel: t.Optional[discord.VoiceChannel]):
        player = self.get_player(ctx)
        channel = await player.connect(ctx, channel)
        embed=discord.Embed(description=f":wave: Just joined **{channel.name}**! What's up?", color=discord.Colour.green())
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
        await ctx.reply(embed=embed, mention_author=False)
        await sendToWebhook(content=f"Joined VC in `{ctx.message.guild.name}`. Requested by `{ctx.author.name}`")

    @connect_command.error
    async def connect_command_error(self, ctx, exc):
        if isinstance(exc, AlreadyConnectedToChannel):
            embed=discord.Embed(description=f":no_entry_sign: Sorry, you are already **in** a voice channel.", color=discord.Colour.red())
            embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
            await ctx.reply(embed=embed, mention_author=False)
        elif isinstance(exc, NoVoiceChannel):
            embed=discord.Embed(description=f":no_entry_sign: Sorry, you are not currently **in** a voice channel.", color=discord.Colour.red())
            embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
            await ctx.reply(embed=embed, mention_author=False)
            
    @commands.command(name="disconnect", aliases=["leave"])
    async def disconnect_command(self, ctx):
        player = self.get_player(ctx)
        await player.teardown()
        embed=discord.Embed(description=f":wave: Just **left** your VC!", color=discord.Colour.green())
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
        await ctx.reply(embed=embed, mention_author=False)
        await sendToWebhook(content=f"Left VC in `{ctx.message.guild.name}`. Requested by `{ctx.author.name}`")
        
        
        
    @commands.command(name="play")
    async def play_command(self, ctx, *, query: t.Optional[str]):
        player = self.get_player(ctx)

        if not player.is_connected:
            await player.connect(ctx)

        if query is None:
            if player.queue.is_empty:
                raise QueueIsEmpty

        else:
            query = query.strip("<>")
            if not re.match(URL_REGEX, query):
                query = f"ytsearch:{query}"
            await player.add_tracks(ctx, await self.wavelink.get_tracks(query))
            await sendToWebhook(content=f"``{ctx.author.name}`` is playing ``{player.queue.current_track.title}`` by ``{player.queue.current_track.author}`` in ``{ctx.message.guild.name}``")
            
    @play_command.error
    async def play_command_error(self, ctx, exc):
        if isinstance(exc, QueueIsEmpty):
            embed=discord.Embed(description=f":no_entry_sign: Sorry! The queue is **empty**!", color=discord.Colour.red())
            embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
            embed.set_footer(text="Tip : You can add a song to the queue by playing a song with `niko play`")
            await ctx.reply(embed=embed, mention_author=False)	
        elif isinstance(exc, NoVoiceChannel):
            embed=discord.Embed(description=f":no_entry_sign: Sorry, you are not currently **in** a voice channel.", color=discord.Colour.red())
            embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
            await ctx.reply(embed=embed, mention_author=False)
            
    @commands.command(name="pause")
    async def pause_command(self, ctx):
        player = self.get_player(ctx)
        if player.is_paused:
            raise PlayerIsAlreadyPaused
        await player.set_pause(True)
        embed=discord.Embed(description=":pause_button: **Paused** the song!", color=discord.Colour.green())
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
        await ctx.reply(embed=embed, mention_author=False)

    @pause_command.error
    async def pause_command_error(self, ctx, exc):
        if isinstance(exc, PlayerIsAlreadyPaused):
         embed=discord.Embed(description=":pause_button: The song is already **paused**!", color=discord.Colour.red())
         embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
        await ctx.reply(embed=embed, mention_author=False)     

    @commands.command(name="resume")
    async def resume_command(self, ctx):
        player = self.get_player(ctx)
        if not player.is_paused:
            raise PlayerIsAlreadyPaused
        await player.set_pause(False)
        embed=discord.Embed(description=":play_pause: **Resumed** the song!", color=discord.Colour.green())
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
        await ctx.reply(embed=embed, mention_author=False)

    @commands.command(name="stop")
    async def stop_command(self, ctx):
        player = self.get_player(ctx)
        player.queue.empty()
        await player.stop()
        embed=discord.Embed(description=":no_entry_sign: **Stopped** the song!", color=discord.Colour.red())
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
        await ctx.reply(embed=embed, mention_author=False)
        
    @commands.command(name="next", aliases=["skip"])
    async def next_command(self, ctx):
        player = self.get_player(ctx)

        if not player.queue.upcoming:
            raise NoMoreTracks

        await player.stop()
        embed=discord.Embed(description=":play_pause: Playing the **next** song in the queue!", color=discord.Colour.green())
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
        embed.set_footer(text="Tip : You can check the current queue with `niko queue`")
        await ctx.reply(embed=embed, mention_author=False)
        
    @next_command.error
    async def next_command_error(self, ctx, exc):
        if isinstance(exc, QueueIsEmpty):
            embed=discord.Embed(description=f":no_entry_sign: Sorry! The queue is **empty**!", color=discord.Colour.red())
            embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
            embed.set_footer(text="Tip : You can add a song to the queue by playing a song with `niko play`")	
            await ctx.reply(embed=embed, mention_author=False)
        elif isinstance(exc, NoMoreTracks): 
            embed=discord.Embed(description=f":no_entry_sign: Sorry! There are no more **tracks** in the queue!", color=discord.Colour.red())
            embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
            await ctx.reply(embed=embed, mention_author=False)
          
    @commands.command(name="previous")
    async def previous_command(self, ctx):
        player = self.get_player(ctx)
        if not player.queue.history:
            raise NoPreviousTracks
        player.queue.position -= 2
        await player.stop()
        embed=discord.Embed(description=":rewind: Playing the **previous** song in the queue!", color=discord.Colour.green())
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
        embed.set_footer(text="Tip : You can check the current queue with `niko queue`")
        await ctx.reply(embed=embed, mention_author=False)
          
    @previous_command.error
    async def previous_command_error(self, ctx, exc):
        if isinstance(exc, QueueIsEmpty):
            embed=discord.Embed(description=f":no_entry_sign: Sorry! The queue is **empty**!", color=discord.Colour.red())
            embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
            embed.set_footer(text="Tip : You can add a song to the queue by playing a song with `niko play`")	
            await ctx.reply(embed=embed, mention_author=False)
        elif isinstance(exc, NoPreviousTracks):
            embed=discord.Embed(description=f":no_entry_sign: Sorry! There are no **previous** tracks in the queue!", color=discord.Colour.red())
            embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
            await ctx.reply(embed=embed, mention_author=False)
          
    @commands.command(name="shuffle")
    async def shuffle_command(self, ctx):
        player = self.get_player(ctx)
        player.queue.shuffle()
        embed=discord.Embed(description=f"**Shuffled** the queue!", color=discord.Colour.green())
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
        embed.set_footer(text="Tip : You can check the new queue with `niko queue`")
        await ctx.reply(embed=embed, mention_author=False)

    @shuffle_command.error
    async def shuffle_command_error(self, ctx, exc):
        if isinstance(exc, QueueIsEmpty):
            embed=discord.Embed(description=f":no_entry_sign: Sorry! The queue is **empty**!", color=discord.Colour.red())
            embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
            embed.set_footer(text="Tip : You can add a song to the queue by playing a song with `niko play`")	
            await ctx.reply(embed=embed, mention_author=False)
            
    @commands.command(name="loop")
    async def repeat_command(self, ctx, mode: str):
        if mode not in ("stop", "song", "queue"):
            raise InvalidRepeatMode
        if mode == "stop":
          player = self.get_player(ctx)
          player.queue.set_repeat_mode("stop")
          embed=discord.Embed(description=f":no_entry_sign: **Stopped** the loop!", color=discord.Colour.red())
          embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
          embed.set_footer(text="Available options for loop : stop, song and queue")
          await ctx.reply(embed=embed, mention_author=False)
        if mode == "song":
          player = self.get_player(ctx)
          player.queue.set_repeat_mode("song")
          embed=discord.Embed(description=f":loop: Looping the **currently** playing song!", color=discord.Colour.green())
          embed.set_footer(text="Available options for loop : stop, song and queue")
          embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
          await ctx.reply(embed=embed, mention_author=False)
        if mode == "queue":
          player = self.get_player(ctx)
          player.queue.set_repeat_mode("queue")
          embed=discord.Embed(description=f":loop: Looping the **queue**!", color=discord.Colour.green())
          embed.set_footer(text="Available options for loop : stop, song and queue")
          embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
          await ctx.reply(embed=embed, mention_author=False)
          
    @commands.command(name="queue")
    async def queue_command(self, ctx, show: t.Optional[int] = 10):
        player = self.get_player(ctx)

        if player.queue.is_empty:
            raise QueueIsEmpty

        embed = discord.Embed(
            title="Here's the current Queue",
            description=f"The next **{show}** tracks",
            colour=discord.Colour.green()
        )
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
        embed.add_field(name=":notes: Currently playing", value=getattr(player.queue.current_track, "title", "No tracks are **currently** playing!"), inline=False)
        if upcoming := player.queue.upcoming:
            embed.add_field(
                name="What's next",
                value="\n".join(t.title for t in upcoming[:show]),
                inline=False
            )

        msg = await ctx.reply(embed=embed, mention_author=False)
	
    @queue_command.error
    async def queue_command_error(self, ctx, exc):
        if isinstance(exc, QueueIsEmpty):
            embed=discord.Embed(description=f":no_entry_sign: Sorry! The queue is **empty**!", color=discord.Colour.red())
            embed.set_footer(text="Tip : You can add a song to the queue by playing a song with `niko play`!")	
            embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
            await ctx.reply(embed=embed, mention_author=False)


    @commands.group(name="volume", invoke_without_command=True)
    async def volume_group(self, ctx, volume: int):
        player = self.get_player(ctx)

        if volume < 0:
            raise VolumeTooLow

        if volume > 150:
            raise VolumeTooHigh

        await player.set_volume(volume)
        embed=discord.Embed(description=f":loud_sound: Volume set to **{volume:,}**%", color=discord.Colour.green())
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
        await ctx.reply(embed=embed, mention_author=False)
        
    @volume_group.error
    async def volume_group_error(self, ctx, exc):
        if isinstance(exc, VolumeTooLow):
         embed=discord.Embed(description=f":loud_sound: The volume must be higher than **0**%", color=discord.Colour.red())
         embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
         await ctx.reply(embed=embed, mention_author=False)
        elif isinstance(exc, VolumeTooHigh):
         embed=discord.Embed(description=f":loud_sound: The volume must be less than **150**%", color=discord.Colour.red())
         embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
         await ctx.reply(embed=embed, mention_author=False)
        
    @volume_group.command(name="up")
    async def volume_up_command(self, ctx):
        player = self.get_player(ctx)

        if player.volume == 150:
            raise MaxVolume

        await player.set_volume(value := min(player.volume + 10, 150))
        embed=discord.Embed(description=f":loud_sound: Volume set to **{volume:,}**%", color=discord.Colour.green())
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
        await ctx.reply(embed=embed, mention_author=False)
        
    @volume_up_command.error
    async def volume_up_command_error(self, ctx, exc):
        if isinstance(exc, MaxVolume):
            embed=discord.Embed(description=f":sound: Volume is at the **max** level (150%)", color=discord.Colour.red())
            embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
            await ctx.reply(embed=embed, mention_author=False)

    @volume_group.command(name="down")
    async def volume_down_command(self, ctx):
        player = self.get_player(ctx)

        if player.volume == 0:
            raise MinVolume

        await player.set_volume(value := max(0, player.volume - 10))
        embed=discord.Embed(description=f":loud_sound: Volume set to **{volume:,}**%", color=discord.Colour.green())
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
        await ctx.reply(embed=embed, mention_author=False)

    @volume_down_command.error
    async def volume_down_command_error(self, ctx, exc):
        if isinstance(exc, MinVolume):
            embed=discord.Embed(description=f":sound: Volume is at the **minimum** level (0%)", color=discord.Colour.red())
            embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
            await ctx.reply(embed=embed, mention_author=False)
            
    @commands.command(name="playing", aliases=["np"])
    async def playing_command(self, ctx):
        player = self.get_player(ctx)

        if not player.is_playing:
            raise PlayerIsAlreadyPaused

        embed = discord.Embed(
            title=":notes: Now playing",
            colour=discord.Colour.green(),
        )
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
        embed.add_field(name="Title", value=player.queue.current_track.title, inline=False)
        embed.add_field(name="Artist", value=player.queue.current_track.author, inline=False)

        position = divmod(player.position, 60000)
        length = divmod(player.queue.current_track.length, 60000)
        embed.add_field(
            name=":alarm_clock: Duration Played",
            value=f"{int(position[0])}:{round(position[1]/1000):02}/{int(length[0])}:{round(length[1]/1000):02}",
            inline=False
        )

        await ctx.reply(embed=embed, mention_author=False)

    @playing_command.error
    async def playing_command_error(self, ctx, exc):
        if isinstance(exc, PlayerIsAlreadyPaused):
            embed=discord.Embed(description=f":no_entry_sign: Sorry! There is no song **playing** at the moment!", color=discord.Colour.red())
            embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
            await ctx.reply(embed=embed, mention_author=False)
            
    @commands.command(name="skipto", aliases=["goto"])
    async def skipto_command(self, ctx, index: int):
        player = self.get_player(ctx)

        if player.queue.is_empty:
            raise QueueIsEmpty

        if not 0 <= index <= player.queue.length:
            raise NoMoreTracks

        player.queue.position = index - 2
        await player.stop()
        embed=discord.Embed(description=f":notes: Playing track in position **{index}**", color=discord.Colour.green())
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
        await ctx.reply(embed=embed, mention_author=False)

    @skipto_command.error
    async def skipto_command_error(self, ctx, exc):
        if isinstance(exc, QueueIsEmpty):
         embed=discord.Embed(description=f":no_entry_sign: Sorry! The queue is **empty**!", color=discord.Colour.red())
         embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
         await ctx.reply(embed=embed, mention_author=False)
        elif isinstance(exc, NoMoreTracks):
         embed=discord.Embed(description=f":no_entry_sign: Sorry! That position does not **exist**!", color=discord.Colour.red())
         embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
         await ctx.reply(embed=embed, mention_author=False)
            
    @commands.command(name="replay")
    async def restart_command(self, ctx):
        player = self.get_player(ctx)

        if player.queue.is_empty:
            raise QueueIsEmpty

        await player.seek(0)
        embed=discord.Embed(description=f":repeat: **Replaying** the song!", color=discord.Colour.green())
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
        await ctx.reply(embed=embed, mention_author=False)

    @restart_command.error
    async def restart_command_error(self, ctx, exc):
        if isinstance(exc, QueueIsEmpty):
          embed=discord.Embed(description=f":no_entry_sign: Sorry! There are no **tracks** in the queue!", color=discord.Colour.red())
          embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
          await ctx.reply(embed=embed, mention_author=False)

    @commands.command(name="seek")
    async def seek_command(self, ctx, position: str):
        player = self.get_player(ctx)

        if player.queue.is_empty:
            raise QueueIsEmpty

        if not (match := re.match(TIME_REGEX, position)):
            raise InvalidTimeString

        if match.group(3):
            secs = (int(match.group(1)) * 60) + (int(match.group(3)))
        else:
            secs = int(match.group(1))

        await player.seek(secs * 1000)
        embed=discord.Embed(description=f"**Seeked** the song!", color=discord.Colour.red())
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
        await ctx.reply(embed=embed, mention_author=False)
            
    @commands.command(name="lyrics")
    async def lyrics_command(self, ctx, *, title):
     genius = lyricsgenius.Genius("GENIUS API KEY")
     genius.verbose = False
     genius.remove_section_headers = True
     genius.skip_non_songs = True
     song = genius.search_song(f"{title}")
     test_stirng = f"{song.lyrics}"
     embed1=discord.Embed(description=":mag: Searching for lyrics... please wait!")
     msg = await ctx.reply(embed=embed1, mention_author=False)
     total = 1
     for i in range(len(test_stirng)):
       if(test_stirng[i] == ' ' or test_stirng == '\n' or test_stirng == '\t'):
         total = total + 1
     if total > 600:
       embed=discord.Embed(description=f":no_entry_sign: Sorry! The number of characters in **{title}** exceeds Discord's character limit! (6000 characters). There's nothing I can do :pensive: ", color=discord.Colour.red())
       await asyncio.sleep(1)
       await msg.edit(embed=embed)
     await asyncio.sleep(3)
     embed2=discord.Embed(title=f"📜 Lyrics for **{title}**!" ,description=f"{song.lyrics}")
     await msg.edit(embed=embed2)
     
    @commands.command(name="help")
    async def select(self, ctx):
        async def callback(interaction):
          embed=discord.Embed(title="Music commands",description="Here's a list of all my music commands.", color=discord.Colour.green())
          embed.add_field(name = ":notes: niko play", value = "Niko play any song you want.")
          embed.add_field(name = ":lock: niko join", value = "Niko joins your VC.")
          embed.add_field(name = "🔓niko leave", value = "Niko leaves your VC.")
          embed.add_field(name = "⏸️ niko pause", value = "Niko pauses the song.")
          embed.add_field(name = "▶️ niko resume", value = "Niko resumes the song.")
          embed.add_field(name = ":repeat: niko loop", value = "Niko loops your requested song.")
          embed.add_field(name = ":eyes: niko seek", value = "Niko move ahead in the song based on the time provided.")
          embed.add_field(name = " :scroll: niko queue", value = "Niko shows you the queue.")
          embed.add_field(name = " ❌️ niko skip", value = "Niko skips the currently playing song")
          embed.add_field(name = " 👆️ niko goto", value = "Niko plays a track from the queue based on an integer.")
          embed.add_field(name = " 🔊️ niko volume", value = "Niko changes the volume.")
          embed.add_field(name = " :alarm_clock:  niko np", value = "Niko shows the currently playing song.")
          embed.add_field(name = "🃏️ niko shuffle", value = "Niko plays a random song from the queue.")
          embed.add_field(name = "🛑 niko stop", value = "Niko stops the song.")
          embed.add_field(name = ":abc: niko lyrics", value = "Niko finds lyrics on most songs!")
          embed.add_field(name = ":rewind: niko replay", value = "Niko rewinds the song from the start.")
          embed.add_field(name = "📩 niko invite", value = "Invite niko to other servers!")
          await interaction.edit_origin(embed=embed)
        
        embed=discord.Embed(title="🏥 Help Center",description="Please select a category from the list below!")
        msg = await ctx.send(
            embed=embed,
            components=[
                self.bot.components_manager.add_callback(
                    Select(
                        options=[
                            SelectOption(label = "🎶️ Music ", value = "See a list of all the music commands!"),
                        ],
                    ),
                    callback,
                )
            ],
        )
        
    @commands.command()
    async def invite(self, ctx):
        async def callback(interaction):
            await interaction.send(content="Yay")
 
        embed=discord.Embed(description="Here are some of my **Related Links!**")
        await ctx.send(
            embed=embed,
            components=[
                self.bot.components_manager.add_callback(
                    Button(style=5, label="Invite me!", url="https://discord.com/api/oauth2/authorize?client_id=915595163286532167&permissions=66087744&scope=bot"),callback
                ),
            ],
        )
    
def setup(bot):
    bot.add_cog(Music(bot))


