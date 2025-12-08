import discord
from discord.ext import commands
import os
import tictactoe 
from dotenv import load_dotenv
import logging
import time 

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

load_dotenv() 

BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN") or os.environ.get("DISCORD_TOKEN") 

intents = discord.Intents.default()
intents.message_content = True 
intents.members = True 

bot = commands.Bot(command_prefix="!", intents=intents)

active_challenges = {} 
active_games = {}      

class ChallengeView(discord.ui.View):
    def __init__(self, challenger_id, opponent_id, channel_id, challenges: dict, games: dict):
        super().__init__(timeout=60) 
        self.challenger_id = challenger_id
        self.opponent_id = opponent_id
        self.channel_id = channel_id
        self.active_challenges = challenges 
        self.active_games = games           
        self.message = None 

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success, custom_id="ttt_accept")
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opponent_id:
            await interaction.response.send_message("Only the challenged player can accept this invitation.", ephemeral=True)
            return
        
        if self.channel_id not in self.active_challenges:
             await interaction.response.send_message("This challenge has expired or was cancelled.", ephemeral=True)
             return
        
        del self.active_challenges[self.channel_id]

        playerX_id = self.challenger_id
        playerO_id = self.opponent_id
        
        game_session = tictactoe.TicTacToeGame(playerX_id, playerO_id)
        
        await interaction.response.defer() 
        
        message = await interaction.original_response()
        self.active_games[message.id] = game_session
        
        board_view = tictactoe.TicTacToeView(
            game_session, 
            self.active_games,
            message.id    
        )
        board_view.message = message
        
        initial_embed, _ = board_view._create_embed(game_over=False) 

        self.stop()
        for item in self.children:
            item.disabled = True

        await interaction.edit_original_response(content=None, view=board_view, embed=initial_embed, attachments=[])

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger, custom_id="ttt_decline")
    async def decline_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in [self.challenger_id, self.opponent_id]:
            await interaction.response.send_message("You cannot interact with this challenge.", ephemeral=True)
            return
        
        if self.channel_id in self.active_challenges:
            del self.active_challenges[self.channel_id]

        self.stop()
        for item in self.children:
            item.disabled = True
        
        await interaction.response.edit_message(content="The challenge was declined.", view=None, embed=None, attachments=[])

    async def on_timeout(self):
        if self.channel_id in self.active_challenges:
            logging.info(f"Challenge timed out for channel {self.channel_id}. Removing from active_challenges.")
            del self.active_challenges[self.channel_id]
        
        for item in self.children:
            item.disabled = True
            
        opponent_mention = f"<@{self.opponent_id}>"
        
        expired_embed = discord.Embed(
            title="Challenge Expired",
            description=f"{opponent_mention} is too scared to accept the challenge, so they chose to ignore it instead.",
            color=discord.Color.orange()
        )

        image_filename = "expire_tictactoe.png" 
        script_dir = os.path.dirname(os.path.abspath(__file__))
        image_file_path = os.path.join(script_dir, image_filename)
        
        files_to_send = []
        
        if os.path.exists(image_file_path):
            image_file = discord.File(image_file_path, filename="expire_image.png")
            expired_embed.set_thumbnail(url="attachment://expire_image.png") 
            files_to_send = [image_file]
        else:
            logging.error(f"Expiration image file NOT FOUND: {image_file_path}. Sending embed without image.")

        if self.message:
            try:
                await self.message.edit(
                    content=f"Challenge for {opponent_mention} expired.",
                    embed=expired_embed, 
                    view=self, 
                    attachments=files_to_send
                )
            except discord.NotFound:
                logging.info("Original message for expired challenge not found.")
            except Exception as e:
                logging.error(f"Error updating expired message: {e}")

async def load_extensions():
    try:
        await bot.load_extension("freeze")
        logging.info("Successfully loaded freeze.py Cog.")
    except Exception as e:
        logging.error(f"Failed to load freeze.py Cog: {e}")
        
    try:
        await bot.load_extension("infect")
        logging.info("Successfully loaded infect.py Cog.")
    except Exception as e:
        logging.error(f"Failed to load infect.py Cog: {e}")

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    await load_extensions() 
    await bot.tree.sync()
    print("Slash commands synced.")

@bot.tree.command(name="tictactoe", description="Start a game of Tic-Tac-Toe with another user.")
@discord.app_commands.describe(opponent="The user you want to challenge.")
async def tictactoe_command(interaction: discord.Interaction, opponent: discord.Member):
    channel_id = interaction.channel_id

    if interaction.user.id == opponent.id:
        await interaction.response.send_message("You cannot play a game against yourself!", ephemeral=True)
        return
    
    if channel_id in active_challenges:
        await interaction.response.send_message("A challenge is already pending in this channel! Please wait for it to be accepted or declined.", ephemeral=True)
        return
        
    if opponent.bot:
        await interaction.response.send_message("You cannot challenge a bot right now!", ephemeral=True)
        return

    active_challenges[channel_id] = {
        'challenger_id': interaction.user.id,
        'opponent_id': opponent.id
    }

    await interaction.response.defer()
    
    challenge_view = ChallengeView(
        interaction.user.id, 
        opponent.id, 
        channel_id, 
        active_challenges,
        active_games      
    )
    
    expiration_timestamp = int(time.time() + 60)
    
    embed = discord.Embed(
        title="⚔️ A New Challenge!",
        description=(
            f"<@{opponent.id}>, <@{interaction.user.id}> has challenged you to Tic-Tac-Toe!\n\n"
            f"Click 'Accept' to start the battle! Challenge expires <t:{expiration_timestamp}:R>."
        ),
        color=discord.Color.dark_purple()
    )

    image_filename = "tictactoe.png" 
    script_dir = os.path.dirname(os.path.abspath(__file__))
    image_file_path = os.path.join(script_dir, image_filename)
    
    files_to_send = []

    if os.path.exists(image_file_path):
        image_file = discord.File(image_file_path, filename="challenge_image.png")
        embed.set_thumbnail(url="attachment://challenge_image.png") 
        files_to_send = [image_file]
    else:
        logging.error(f"Image file NOT FOUND: {image_file_path}. Sending embed without image.")

    message = await interaction.edit_original_response(
        content=f"{opponent.mention}, check the challenge below!", 
        embed=embed, 
        view=challenge_view, 
        attachments=files_to_send 
    )
    challenge_view.message = message 

@bot.event
async def on_message(message):
    await bot.process_commands(message)

if __name__ == "__main__":
    if not BOT_TOKEN:
        print("!!! ERROR: DISCORD_BOT_TOKEN environment variable is not set. Please create a .env file and set the token. !!!")
    else:
        bot.run(BOT_TOKEN)
