from bot import MusicBot	
from discord_components import DiscordComponents, ComponentsBot, Button

def main():
    bot = MusicBot()
    DiscordComponents(bot)
    bot.run()

if __name__ == "__main__":
    main()
