import discord
from discord.ext import commands
import random
import asyncio
import os

# ─────────────── INTENTS ───────────────
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

games = {}
lobbies = {}

# ─────────────── CARD ───────────────
class Card:
    def __init__(self, color, value):
        self.color = color
        self.value = value

    def __str__(self):
        if self.color == "Wild":
            return f"🃏 {self.value}"
        emojis = {"Red": "🔴", "Blue": "🔵", "Green": "🟢", "Yellow": "🟡"}
        return f"{emojis[self.color]} {self.color} {self.value}"

    def can_play(self, top_card, current_color):
        if self.color == "Wild":
            return True
        return self.color == current_color or self.value == top_card.value

# ─────────────── BOT PLAYER ───────────────
class BotPlayer:
    def __init__(self, name):
        self.name = name

    @property
    def mention(self):
        return f"🤖 **{self.name}**"

    def __str__(self):
        return self.name

# ─────────────── LOBBY ───────────────
class Lobby:
    def __init__(self, host, channel):
        self.host = host
        self.channel = channel
        self.players = [host]

    def add_player(self, p):
        if p not in self.players:
            self.players.append(p)
            return True
        return False

# ─────────────── GAME ───────────────
class UnoGame:
    def __init__(self, players, channel):
        self.players = players
        self.channel = channel
        self.hands = {p: [] for p in players}
        self.turn = 0
        self.direction = 1
        self.deck = []
        self.discard = []
        self.current_color = None

        self.create_deck()
        self.deal()

    def create_deck(self):
        colors = ["Red", "Blue", "Green", "Yellow"]
        for c in colors:
            self.deck.append(Card(c, "0"))
            for n in range(1, 10):
                self.deck += [Card(c, str(n)), Card(c, str(n))]
            for _ in range(2):
                self.deck += [Card(c, "Skip"), Card(c, "Reverse"), Card(c, "Draw2")]
        for _ in range(4):
            self.deck += [Card("Wild", "Wild"), Card("Wild", "WildDraw4")]
        random.shuffle(self.deck)

    def deal(self):
        for p in self.players:
            for _ in range(7):
                self.hands[p].append(self.deck.pop())
        first = self.deck.pop()
        self.discard.append(first)
        self.current_color = first.color if first.color != "Wild" else random.choice(
            ["Red", "Blue", "Green", "Yellow"]
        )

    def current_player(self):
        return self.players[self.turn]

    def next_turn(self):
        self.turn = (self.turn + self.direction) % len(self.players)

    def draw(self, player, count=1):
        for _ in range(count):
            if not self.deck:
                self.deck = self.discard[:-1]
                random.shuffle(self.deck)
                self.discard = [self.discard[-1]]
            self.hands[player].append(self.deck.pop())

    def play(self, player, index, color=None):
        card = self.hands[player][index]
        if not card.can_play(self.discard[-1], self.current_color):
            return False, None

        self.hands[player].pop(index)
        self.discard.append(card)

        if card.color == "Wild":
            self.current_color = color
        else:
            self.current_color = card.color

        return True, card

# ─────────────── BOT TURN ───────────────
async def bot_turn(game):
    bot_player = game.current_player()
    await asyncio.sleep(1)

    for i, card in enumerate(game.hands[bot_player]):
        if card.can_play(game.discard[-1], game.current_color):
            chosen_color = None
            if card.color == "Wild":
                chosen_color = random.choice(["Red", "Blue", "Green", "Yellow"])
            game.play(bot_player, i, chosen_color)
            await game.channel.send(f"{bot_player.mention} played {card}")
            game.next_turn()
            return

    game.draw(bot_player)
    await game.channel.send(f"{bot_player.mention} drew a card")
    game.next_turn()

# ─────────────── COMMANDS ───────────────
@bot.command()
async def commands(ctx):
    await ctx.send(
        "**UNO Commands**\n"
        "`!createlobby` `!join` `!leave` `!start`\n"
        "`!hand` `!play <num> [color]` `!draw` `!pass` `!status`"
    )

@bot.command()
async def createlobby(ctx):
    if ctx.channel.id in lobbies:
        return await ctx.send("❌ Lobby already exists.")
    lobbies[ctx.channel.id] = Lobby(ctx.author, ctx.channel)
    await ctx.send("🎮 Lobby created. Use `!join` or `!start`.")

@bot.command()
async def join(ctx):
    lobby = lobbies.get(ctx.channel.id)
    if not lobby:
        return await ctx.send("❌ No lobby.")
    lobby.add_player(ctx.author)
    await ctx.send(f"{ctx.author.mention} joined the lobby.")

@bot.command()
async def leave(ctx):
    lobby = lobbies.get(ctx.channel.id)
    if not lobby or ctx.author not in lobby.players:
        return
    lobby.players.remove(ctx.author)
    await ctx.send("👋 You left the lobby.")

@bot.command()
async def start(ctx):
    lobby = lobbies.get(ctx.channel.id)
    if not lobby or ctx.author != lobby.host:
        return

    if len(lobby.players) == 1:
        for i in range(random.randint(1, 3)):
            lobby.players.append(BotPlayer(f"UNO Bot {i+1}"))
        await ctx.send("🤖 Added bot players.")

    game = UnoGame(lobby.players, ctx.channel)
    games[ctx.channel.id] = game
    del lobbies[ctx.channel.id]

    await ctx.send(
        f"🎮 Game started!\nTop card: {game.discard[-1]}\n"
        f"First turn: {game.current_player().mention}"
    )

    if isinstance(game.current_player(), BotPlayer):
        await bot_turn(game)

@bot.command()
async def hand(ctx):
    game = games.get(ctx.channel.id)
    if not game or ctx.author not in game.hands:
        return
    cards = "\n".join(f"{i+1}. {c}" for i, c in enumerate(game.hands[ctx.author]))
    await ctx.author.send(f"🎴 Your hand:\n{cards}")

@bot.command()
async def play(ctx, num: int, color: str = None):
    game = games.get(ctx.channel.id)
    if not game or ctx.author != game.current_player():
        return

    success, card = game.play(
        ctx.author, num - 1, color.capitalize() if color else None
    )
    if not success:
        return await ctx.send("❌ Invalid move.")

    await ctx.send(f"{ctx.author.mention} played {card}")
    game.next_turn()

    while isinstance(game.current_player(), BotPlayer):
        await bot_turn(game)

@bot.command()
async def draw(ctx):
    game = games.get(ctx.channel.id)
    if not game or ctx.author != game.current_player():
        return
    game.draw(ctx.author)
    await ctx.send(f"{ctx.author.mention} drew a card.")
    game.next_turn()

@bot.command(name="pass")
async def pass_turn(ctx):
    game = games.get(ctx.channel.id)
    if not game or ctx.author != game.current_player():
        return
    game.next_turn()
    await ctx.send("⏭️ Turn passed.")

@bot.command()
async def status(ctx):
    game = games.get(ctx.channel.id)
    if not game:
        return
    counts = "\n".join(f"{p.mention}: {len(game.hands[p])}" for p in game.players)
    await ctx.send(
        f"Top card: {game.discard[-1]}\n"
        f"Current: {game.current_player().mention}\n\n{counts}"
    )

@bot.event
async def on_ready():
    print("UNO bot online")
    await bot.change_presence(activity=discord.Game(name="UNO | !commands"))

# ─────────────── RUN ───────────────
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable not set.")

bot.run(BOT_TOKEN)
