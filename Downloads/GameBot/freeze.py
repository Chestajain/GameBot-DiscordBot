import discord
from discord.ext import commands
import asyncio
import datetime
import logging

logging.getLogger(__name__).setLevel(logging.INFO)

FROZEN_ROLE_ID = 1443572793215160440

VOTE_DIFFERENCE = 1
POLL_ACTIVE_MINUTES = 2
POLL_TIMEOUT_SECONDS = POLL_ACTIVE_MINUTES * 60

ROLE_DURATION_MINUTES = 2
FREEZE_DURATION_SECONDS = ROLE_DURATION_MINUTES * 60

COOLDOWN_DURATION_SECONDS = 10

IMMUNITY_MINUTES = 1
IMMUNITY_DURATION_SECONDS = IMMUNITY_MINUTES * 60

COMMAND_COOLDOWN_MINUTES = 0
COMMAND_COOLDOWN_SECONDS = COMMAND_COOLDOWN_MINUTES * 60

class FreezeProtectView(discord.ui.View):
    def __init__(self, target_member: discord.Member, initiator_id: int, timeout=POLL_TIMEOUT_SECONDS):
        super().__init__(timeout=timeout)
        self.target_member = target_member
        self.initiator_id = initiator_id
        self.freeze_votes = 0
        self.protect_votes = 0
        self.voters = set()
        self.message = None

    async def update_message(self, interaction: discord.Interaction):
        embed = interaction.message.embeds[0]
        self.children[0].label = f"Freeze ({self.freeze_votes})"
        self.children[1].label = f"Protect ({self.protect_votes})"
        await interaction.response.edit_message(embed=embed, view=self)

    async def check_for_success(self, interaction: discord.Interaction):
        if self.freeze_votes - self.protect_votes >= VOTE_DIFFERENCE:

            cog = interaction.client.get_cog("FreezeCog")
            if cog:
                cooldown_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=COMMAND_COOLDOWN_MINUTES)
                cog.command_cooldowns[self.initiator_id] = cooldown_time

                expiration_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=IMMUNITY_MINUTES)
                cog.immunity_list[self.target_member.id] = expiration_time

            success_embed = discord.Embed(
                title="🧊 Freeze attempt was successful!",
                description=(
                    f"Now, {self.target_member.mention} is frozen for **{ROLE_DURATION_MINUTES} minutes** "
                    f"and they get a timeout for **{COOLDOWN_DURATION_SECONDS} seconds** "
                    f"every time they send a message."
                ),
                color=discord.Color.dark_blue()
            )

            await interaction.edit_original_response(
                content=f"{self.target_member.mention} is now frozen solid. Hope they enjoy their new iceberg lifestyle.",
                embed=success_embed,
                view=None
            )

            asyncio.create_task(self.apply_freeze(interaction.guild))
            self.stop()

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
        if not self.message: return

        await self.message.edit(content=(
            f"{self.target_member.mention} walks away unfrozen because nobody could be bothered. "
            "Congrats on staying warm! 🥶"
        ), embed=None, view=None)

    async def apply_freeze(self, guild: discord.Guild):
        frozen_role = guild.get_role(FROZEN_ROLE_ID)
        if not frozen_role:
            logging.error(f"Error: Frozen role not found with ID {FROZEN_ROLE_ID}.")
            return

        await self.target_member.add_roles(frozen_role, reason=f"Frozen by community vote for {ROLE_DURATION_MINUTES} minutes.")
        await asyncio.sleep(FREEZE_DURATION_SECONDS)

        member_after_sleep = guild.get_member(self.target_member.id)

        if member_after_sleep and frozen_role in member_after_sleep.roles:
            await member_after_sleep.remove_roles(frozen_role, reason="Freeze duration ended.")

class FreezeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.immunity_list = {}
        self.command_cooldowns = {}
        self.unfreeze_cooldowns = {}

    @commands.hybrid_command(name="freeze", description=f"Start a vote to freeze a member for {ROLE_DURATION_MINUTES} minutes.")
    @discord.app_commands.describe(target="The user to initiate the freeze vote against.")
    async def freeze_command(self, ctx: commands.Context, target: discord.Member):

        if target.id == ctx.author.id:
            return await ctx.send("You cannot freeze yourself!", ephemeral=True)
        if target.bot:
            return await ctx.send("You cannot freeze a bot!", ephemeral=True)

        frozen_role = ctx.guild.get_role(FROZEN_ROLE_ID)
        if not frozen_role:
             return await ctx.send(f"Error: The 'Frozen' role (ID: {FROZEN_ROLE_ID}) was not found. Please configure the bot.", ephemeral=True)

        if frozen_role in target.roles:
             return await ctx.send(f"{target.mention} is already frozen. Wait for the duration to end.", ephemeral=True)

        now = datetime.datetime.now(datetime.timezone.utc)
        initiator_id = ctx.author.id

        if initiator_id in self.command_cooldowns:
            expiration_time = self.command_cooldowns[initiator_id]

            if expiration_time > now:
                timestamp_unix = int(expiration_time.timestamp())
                message = f"Chill Elsa! You can use your powers again <t:{timestamp_unix}:R>"
                return await ctx.send(message, ephemeral=True)
            else:
                del self.command_cooldowns[initiator_id]

        target_id = target.id
        if target_id in self.immunity_list:
            expiration_time = self.immunity_list[target_id]

            if expiration_time > now:
                timestamp_unix = int(expiration_time.timestamp())

                message = (
                    f"{target.mention} is having some hot buttered rum right now. "
                    f"You can freeze them <t:{timestamp_unix}:R>."
                )
                return await ctx.send(message, ephemeral=True)

            else:
                del self.immunity_list[target_id]

        if ctx.interaction:
            await ctx.interaction.response.defer()

        expiration_dt = now + datetime.timedelta(seconds=POLL_TIMEOUT_SECONDS)
        expiration_unix = int(expiration_dt.timestamp())

        embed = discord.Embed(
            title="❄️ A FREEZE VOTE IS HAPPENING! 🥶",
            description=(
                f"{ctx.author.mention} is trying to **FREEZE** {target.mention}!\n\n"
                f"The freeze will succeed if the **Freeze** votes are **{VOTE_DIFFERENCE} or more** than the **Protect** votes.\n\n"
                f"**Voting ends <t:{expiration_unix}:R>**"
            ),
            color=discord.Color.blue()
        )

        view = FreezeProtectView(target_member=target, initiator_id=initiator_id)

        message = await ctx.send(
            content=f"**{ctx.author.mention} is trying to freeze {target.mention}!**",
            embed=embed,
            view=view
        )

        if ctx.interaction:
             view.message = await ctx.interaction.original_response()
        else:
             view.message = message

    @commands.hybrid_command(name="unfreeze", description="Immediately removes the Frozen role from a user (3 daily uses, GMT reset).")
    @discord.app_commands.describe(target="The user to manually unfreeze.")
    @commands.has_permissions(manage_roles=True)
    async def unfreeze_command(self, ctx: commands.Context, target: discord.Member):

        MAX_USES = 3

        now_gmt = datetime.datetime.now(datetime.timezone.utc)
        today_gmt_str = now_gmt.strftime('%Y-%m-%d')
        user_id = ctx.author.id

        if user_id in self.unfreeze_cooldowns:
            usage_data = self.unfreeze_cooldowns[user_id]

            if usage_data['last_day'] != today_gmt_str:
                usage_data['count'] = 0
                usage_data['last_day'] = today_gmt_str

            current_count = usage_data['count']

            if current_count >= MAX_USES:
                tomorrow_gmt = now_gmt.date() + datetime.timedelta(days=1)
                midnight_gmt = datetime.datetime.combine(tomorrow_gmt, datetime.time(0, 0), datetime.timezone.utc)
                timestamp_unix = int(midnight_gmt.timestamp())

                message = (
                    f"Chill! You've used your three daily manual unfreezes. "
                    f"Your uses will reset <t:{timestamp_unix}:R>."
                )
                return await ctx.send(message, ephemeral=True)
        else:
            self.unfreeze_cooldowns[user_id] = {'count': 0, 'last_day': today_gmt_str}
            current_count = 0

        frozen_role = ctx.guild.get_role(FROZEN_ROLE_ID)

        if not frozen_role:
             return await ctx.send("Error: The 'Frozen' role is not configured correctly on the bot.", ephemeral=True)

        if frozen_role not in target.roles:
            return await ctx.send(f"{target.mention} is not currently frozen.", ephemeral=True)

        try:
            self.unfreeze_cooldowns[user_id]['count'] += 1
            uses_remaining = MAX_USES - self.unfreeze_cooldowns[user_id]['count']

            await target.remove_roles(frozen_role, reason=f"Manually unfrozen by {ctx.author.name} (Use {current_count + 1}/{MAX_USES} today)")

            await ctx.send(f"✅ **Success!** {target.mention} has been manually unfrozen. ({uses_remaining} uses remaining today.)")

            if target.id in self.immunity_list:
                 del self.immunity_list[target.id]

        except discord.Forbidden:
            await ctx.send("I don't have permission to remove the 'Frozen' role. Check my role hierarchy!", ephemeral=True)
        except Exception as e:
            await ctx.send(f"An unexpected error occurred during unfreeze: {e}", ephemeral=True)

    @unfreeze_command.error
    async def unfreeze_command_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("Sorry, you need the **Manage Roles** permission to manually unfreeze users.", ephemeral=True)
        else:
            raise error

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        frozen_role = message.guild.get_role(FROZEN_ROLE_ID)

        if frozen_role and frozen_role in message.author.roles:
            try:
                timeout_end_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=COOLDOWN_DURATION_SECONDS)

                await message.author.timeout(
                    timeout_end_time,
                    reason=f"Attempted to speak while Frozen. Applied {COOLDOWN_DURATION_SECONDS}s message cooldown."
                )

                await message.author.send(
                    f"**You are currently Frozen!** You received a **{COOLDOWN_DURATION_SECONDS}-second** speaking timeout (message cooldown) for sending a message in {message.channel.mention}."
                )

            except discord.Forbidden:
                logging.error(f"Bot lacks permissions (moderate_members) for freeze enforcement in guild {message.guild.id}.")
            except Exception as e:
                logging.error(f"Error during freeze enforcement: {e}")

async def setup(bot):
    await bot.add_cog(FreezeCog(bot))
