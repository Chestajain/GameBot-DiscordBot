import discord
from discord.ext import commands
import asyncio
import datetime
import logging

logging.getLogger(__name__).setLevel(logging.INFO)

FROZEN_ROLE_ID = 1443572793215160440

VOTE_DIFFERENCE = 1            
# Poll Duration
POLL_ACTIVE_MINUTES = 2        
POLL_TIMEOUT_SECONDS = POLL_ACTIVE_MINUTES * 60 

# Freeze Duration
ROLE_DURATION_MINUTES = 2     
FREEZE_DURATION_SECONDS = ROLE_DURATION_MINUTES * 60

# Punishment Cooldown
COOLDOWN_DURATION_SECONDS = 10 

# Immunity Duration (Target cannot be frozen again for this period)
IMMUNITY_MINUTES = 1 
IMMUNITY_DURATION_SECONDS = IMMUNITY_MINUTES * 60 

# Command Cooldown (Initiator cannot run /freeze again for this period)
COMMAND_COOLDOWN_MINUTES = 0 
COMMAND_COOLDOWN_SECONDS = COMMAND_COOLDOWN_MINUTES * 60

# =================================================================
# 🧊 FREEZE VOTE VIEW LOGIC
# =================================================================

class FreezeProtectView(discord.ui.View):
    """View to handle the Freeze/Protect voting buttons and poll state."""
    def __init__(self, target_member: discord.Member, initiator_id: int, timeout=POLL_TIMEOUT_SECONDS):
        super().__init__(timeout=timeout)
        self.target_member = target_member
        self.initiator_id = initiator_id
        self.freeze_votes = 0
        self.protect_votes = 0
        self.voters = set() 
        self.message = None

    async def update_message(self, interaction: discord.Interaction):
        """Edits the poll message with current vote counts."""
        embed = interaction.message.embeds[0]
        self.children[0].label = f"Freeze ({self.freeze_votes})"
        self.children[1].label = f"Protect ({self.protect_votes})"
        await interaction.response.edit_message(embed=embed, view=self)

    async def check_for_success(self, interaction: discord.Interaction):
        """Checks if the freezing condition has been met."""
        if self.freeze_votes - self.protect_votes >= VOTE_DIFFERENCE:
            
            cog = interaction.client.get_cog("FreezeCog")
            if cog:
                # 1. GRANT COMMAND COOLDOWN TO INITIATOR
                cooldown_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=COMMAND_COOLDOWN_MINUTES)
                cog.command_cooldowns[self.initiator_id] = cooldown_time
                
                # 2. GRANT TARGET IMMUNITY
                expiration_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=IMMUNITY_MINUTES)
                cog.immunity_list[self.target_member.id] = expiration_time

            # 3. Create the new Success Embed
            success_embed = discord.Embed(
                title="🧊 Freeze attempt was successful!",
                description=(
                    f"Now, {self.target_member.mention} is frozen for **{ROLE_DURATION_MINUTES} minutes** "
                    f"and they get a timeout for **{COOLDOWN_DURATION_SECONDS} seconds** "
                    f"every time they send a message."
                ),
                color=discord.Color.dark_blue()
            )

            # 4. Edit the original message (Final success message)
            await interaction.edit_original_response(
                content=f"{self.target_member.mention} is now frozen solid. Hope they enjoy their new iceberg lifestyle.",
                embed=success_embed,
                view=None # Remove the buttons
            )
            
            # 5. Apply role and stop poll
            asyncio.create_task(self.apply_freeze(interaction.guild))
            self.stop() 

    # --- Button Callbacks ---
    @discord.ui.button(label="Freeze (0)", style=discord.ButtonStyle.blurple, custom_id="freeze_vote")
    async def freeze_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == self.target_member.id:
            return await interaction.response.send_message("You cannot vote for yourself!", ephemeral=True)
        if interaction.user.id in self.voters:
            return await interaction.response.send_message("You have already cast your vote!", ephemeral=True)
        
        self.voters.add(interaction.user.id)
        self.freeze_votes += 1
        await self.update_message(interaction)
        await self.check_for_success(interaction)

    @discord.ui.button(label="Protect (0)", style=discord.ButtonStyle.green, custom_id="protect_vote")
    async def protect_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == self.target_member.id:
            return await interaction.response.send_message("You cannot vote for yourself!", ephemeral=True)
        if interaction.user.id in self.voters:
            return await interaction.response.send_message("You have already cast your vote!", ephemeral=True)

        self.voters.add(interaction.user.id)
        self.protect_votes += 1
        await self.update_message(interaction)
        await self.check_for_success(interaction)

    async def on_timeout(self):
        # FAILURE/TIMEOUT LOGIC
        if not self.message: return
        
        # Edit message with the custom text and REMOVE THE VIEW
        await self.message.edit(content=(
            f"{self.target_member.mention} walks away unfrozen because nobody could be bothered. " 
            "Congrats on staying warm! 🥶"
        ), embed=None, view=None)

    async def apply_freeze(self, guild: discord.Guild):
        """Applies the role and sets the 10-minute timer."""
        frozen_role = guild.get_role(FROZEN_ROLE_ID)
        if not frozen_role:
            logging.error(f"Error: Frozen role not found with ID {FROZEN_ROLE_ID}.")
            return

        await self.target_member.add_roles(frozen_role, reason=f"Frozen by community vote for {ROLE_DURATION_MINUTES} minutes.")
        await asyncio.sleep(FREEZE_DURATION_SECONDS)
        
        member_after_sleep = guild.get_member(self.target_member.id) 
        
        if member_after_sleep and frozen_role in member_after_sleep.roles:
            await member_after_sleep.remove_roles(frozen_role, reason="Freeze duration ended.")

# =================================================================
# 🧊 FREEZE COMMAND COG
# =================================================================

class FreezeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # State tracking for the cog
        self.immunity_list = {}     # {target_id: immunity_expiration_datetime}
        self.command_cooldowns = {} # {initiator_id: command_cooldown_expiration_datetime}
        # --- NEW MANUAL COOLDOWN STATE ---
        # Stores {user_id: {'count': int, 'last_day': date_str_GMT}}
        self.unfreeze_cooldowns = {} 

    @commands.hybrid_command(name="freeze", description=f"Start a vote to freeze a member for {ROLE_DURATION_MINUTES} minutes.")
    @discord.app_commands.describe(target="The user to initiate the freeze vote against.")
    async def freeze_command(self, ctx: commands.Context, target: discord.Member):
        
        # 1. Standard Checks
        if target.id == ctx.author.id:
            return await ctx.send("You cannot freeze yourself!", ephemeral=True)
        if target.bot:
            return await ctx.send("You cannot freeze a bot!", ephemeral=True)
        
        frozen_role = ctx.guild.get_role(FROZEN_ROLE_ID)
        if not frozen_role:
             return await ctx.send(f"Error: The 'Frozen' role (ID: {FROZEN_ROLE_ID}) was not found. Please configure the bot.", ephemeral=True)
        
        if frozen_role in target.roles:
             return await ctx.send(f"{target.mention} is already frozen. Wait for the duration to end.", ephemeral=True)

        # 2. COMMAND COOLDOWN CHECK (Initiator)
        now = datetime.datetime.now(datetime.timezone.utc)
        initiator_id = ctx.author.id

        if initiator_id in self.command_cooldowns:
            expiration_time = self.command_cooldowns[initiator_id]
            
            if expiration_time > now:
                # Cooldown is active. Format the message with the relative timestamp tag.
                timestamp_unix = int(expiration_time.timestamp())
                message = f"Chill Elsa! You can use your powers again <t:{timestamp_unix}:R>"
                return await ctx.send(message, ephemeral=True)
            else:
                # Cooldown expired, clear it
                del self.command_cooldowns[initiator_id]

        # 3. IMMUNITY CHECK (Target)
        target_id = target.id
        if target_id in self.immunity_list:
            expiration_time = self.immunity_list[target_id]
            
            if expiration_time > now:
                # Immunity is active. Format the message with the relative timestamp tag.
                timestamp_unix = int(expiration_time.timestamp())
                
                message = (
                    f"{target.mention} is having some hot buttered rum right now. "
                    f"You can freeze them <t:{timestamp_unix}:R>."
                )
                return await ctx.send(message, ephemeral=True)
            
            else:
                # Immunity expired, clear it
                del self.immunity_list[target_id]


        # 4. Start Poll
        
        if ctx.interaction:
            await ctx.interaction.response.defer()

        # Calculate Poll Expiration Time and Unix Timestamp for the embed
        expiration_dt = now + datetime.timedelta(seconds=POLL_TIMEOUT_SECONDS)
        expiration_unix = int(expiration_dt.timestamp()) 
        
        # Construct the Embed Description with the Timestamp
        embed = discord.Embed(
            title="❄️ A FREEZE VOTE IS HAPPENING! 🥶",
            description=(
                f"{ctx.author.mention} is trying to **FREEZE** {target.mention}!\n\n"
                f"The freeze will succeed if the **Freeze** votes are **{VOTE_DIFFERENCE} or more** than the **Protect** votes.\n\n"
                f"**Voting ends <t:{expiration_unix}:R>**"
            ),
            color=discord.Color.blue()
        )
        
        # Pass the initiator's ID to the View
        view = FreezeProtectView(target_member=target, initiator_id=initiator_id)
        
        # Custom bolded header message
        message = await ctx.send(
            content=f"**{ctx.author.mention} is trying to freeze {target.mention}!**", 
            embed=embed, 
            view=view
        )
        
        # Ensure view.message holds the Message object for on_timeout edits
        if ctx.interaction:
             view.message = await ctx.interaction.original_response()
        else:
             view.message = message 

    # --- NEW /UNFREEZE COMMAND ---
    @commands.hybrid_command(name="unfreeze", description="Immediately removes the Frozen role from a user (3 daily uses, GMT reset).")
    @discord.app_commands.describe(target="The user to manually unfreeze.")
    @commands.has_permissions(manage_roles=True)
    async def unfreeze_command(self, ctx: commands.Context, target: discord.Member):
        
        # --- MANUAL GMT COOLDOWN LOGIC START ---
        MAX_USES = 3
        
        # 1. Determine current GMT day
        now_gmt = datetime.datetime.now(datetime.timezone.utc)
        today_gmt_str = now_gmt.strftime('%Y-%m-%d')
        user_id = ctx.author.id

        # 2. Check and update usage count
        if user_id in self.unfreeze_cooldowns:
            usage_data = self.unfreeze_cooldowns[user_id]
            
            # Reset count if the day has changed (GMT midnight reset)
            if usage_data['last_day'] != today_gmt_str:
                usage_data['count'] = 0
                usage_data['last_day'] = today_gmt_str
            
            current_count = usage_data['count']
            
            if current_count >= MAX_USES:
                # Calculate time until GMT midnight (00:00:00 UTC tomorrow)
                tomorrow_gmt = now_gmt.date() + datetime.timedelta(days=1)
                midnight_gmt = datetime.datetime.combine(tomorrow_gmt, datetime.time(0, 0), datetime.timezone.utc)
                timestamp_unix = int(midnight_gmt.timestamp())

                message = (
                    f"Chill! You've used your three daily manual unfreezes. "
                    f"Your uses will reset <t:{timestamp_unix}:R>."
                )
                return await ctx.send(message, ephemeral=True)
        else:
            # First time running today
            self.unfreeze_cooldowns[user_id] = {'count': 0, 'last_day': today_gmt_str}
            current_count = 0
        
        frozen_role = ctx.guild.get_role(FROZEN_ROLE_ID)

        if not frozen_role:
             return await ctx.send("Error: The 'Frozen' role is not configured correctly on the bot.", ephemeral=True)
        
        if frozen_role not in target.roles:
            # Do NOT consume a use if the target isn't frozen.
            return await ctx.send(f"{target.mention} is not currently frozen.", ephemeral=True)

        try:
            # --- SUCCESS PATH: INCREMENT USAGE COUNT ---
            self.unfreeze_cooldowns[user_id]['count'] += 1
            uses_remaining = MAX_USES - self.unfreeze_cooldowns[user_id]['count']

            # Remove the role
            await target.remove_roles(frozen_role, reason=f"Manually unfrozen by {ctx.author.name} (Use {current_count + 1}/{MAX_USES} today)")
            
            # Send success message
            await ctx.send(f"✅ **Success!** {target.mention} has been manually unfrozen. ({uses_remaining} uses remaining today.)")
            
            # Clear target immunity (Optional cleanup)
            if target.id in self.immunity_list:
                 del self.immunity_list[target.id]
                 
        except discord.Forbidden:
            await ctx.send("I don't have permission to remove the 'Frozen' role. Check my role hierarchy!", ephemeral=True)
        except Exception as e:
            await ctx.send(f"An unexpected error occurred during unfreeze: {e}", ephemeral=True)

    # --- Listener for MissingPermissions Errors ONLY ---
    @unfreeze_command.error
    async def unfreeze_command_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("Sorry, you need the **Manage Roles** permission to manually unfreeze users.", ephemeral=True)
        else:
            raise error
            
    # --- Listener for Frozen User Speaking ---
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listener to enforce the 10-second timeout for frozen users without deleting the message."""
        if message.author.bot or not message.guild:
            return
        
        frozen_role = message.guild.get_role(FROZEN_ROLE_ID)
        
        if frozen_role and frozen_role in message.author.roles:
            try:
                # Apply the COOLDOWN_DURATION_SECONDS timeout
                timeout_end_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=COOLDOWN_DURATION_SECONDS)
                
                await message.author.timeout(
                    timeout_end_time, 
                    reason=f"Attempted to speak while Frozen. Applied {COOLDOWN_DURATION_SECONDS}s message cooldown."
                )
                
                # Send a warning to the user
                await message.author.send(
                    f"**You are currently Frozen!** You received a **{COOLDOWN_DURATION_SECONDS}-second** speaking timeout (message cooldown) for sending a message in {message.channel.mention}."
                )
                
            except discord.Forbidden:
                logging.error(f"Bot lacks permissions (moderate_members) for freeze enforcement in guild {message.guild.id}.")
            except Exception as e:
                logging.error(f"Error during freeze enforcement: {e}")

# This setup function is required by discord.py to load the Cog
async def setup(bot):
    await bot.add_cog(FreezeCog(bot))