import discord
from discord import app_commands, ui
from discord.ext import commands
from datetime import timedelta
import logging

INFECTED_ROLE_NAME = "Infected" 

log = logging.getLogger(__name__)

class InfectionView(ui.View):
    def __init__(self, initiator: discord.Member, target: discord.Member):
        super().__init__(timeout=300) 
        self.initiator = initiator
        self.target = target
        self.infect_voters = set()
        self.protect_voters = set()
        self.message = None 

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(content=f"The infection attempt against {self.target.mention} has expired.", view=self, embed=None)
            except Exception as e:
                log.error(f"Error editing message on timeout in InfectionView: {e}")


    async def check_win_condition(self, interaction: discord.Interaction):
        score = len(self.infect_voters) - len(self.protect_voters)
        
        if score >= 5:
            for item in self.children:
                item.disabled = True

            infected_role = discord.utils.get(interaction.guild.roles, name=INFECTED_ROLE_NAME)

            if not infected_role:
                error_embed = discord.Embed(
                    title="Setup Error!",
                    description=f"The role `{INFECTED_ROLE_NAME}` was not found. A server admin needs to create it.",
                    color=discord.Color.red()
                )
                await interaction.message.edit(embed=error_embed, view=self)
                self.stop()
                return

            try:
                await self.target.add_roles(infected_role, reason="Lost the infection vote.")
                await self.target.timeout(timedelta(minutes=1), reason="Infected by popular vote.")
                
                success_embed = discord.Embed(
                    title="☣️ Infection Successful! ☣️",
                    description=f"**{self.target.mention} has been infected!**\n\n"
                                f"They have been given the `{INFECTED_ROLE_NAME}` role and timed out for 1 minute.",
                    color=discord.Color.red()
                )
                success_embed.set_footer(text=f"Final Score: {len(self.infect_voters)} Infect vs. {len(self.protect_voters)} Protect")
                await interaction.message.edit(embed=success_embed, view=self)

            except discord.Forbidden:
                error_embed = discord.Embed(
                    title="Permission Error!",
                    description="I don't have the required permissions to assign roles or timeout members.\n"
                                "Please ensure my role is above the `Infected` role and I have `Manage Roles` "
                                "and `Moderate Members` permissions.",
                    color=discord.Color.orange()
                )
                await interaction.message.edit(embed=error_embed, view=self)
            except Exception as e:
                 log.error(f"Unexpected error during infection: {e}")
                 await interaction.message.edit(content="An unexpected error occurred. Check logs.", view=None, embed=None)
            
            self.stop()


    @ui.button(label="Infect (1000FFcoins)", style=discord.ButtonStyle.red, custom_id="infect_button")
    async def infect_button_callback(self, interaction: discord.Interaction, button: ui.Button):
        voter = interaction.user
        
        if voter == self.target:
            return await interaction.response.send_message("You cannot vote on your own infection!", ephemeral=True)
            
        if voter in self.protect_voters:
            self.protect_voters.remove(voter)

        if voter not in self.infect_voters:
             self.infect_voters.add(voter)
        
        self.children[0].label = f"Infect ({len(self.infect_voters)} FFcoins)"
        self.children[1].label = f"Protect ({len(self.protect_voters)} FFcoins)"

        await interaction.response.edit_message(view=self)
        
        await self.check_win_condition(interaction)

    @ui.button(label="Protect (1000FFcoins)", style=discord.ButtonStyle.green, custom_id="protect_button")
    async def protect_button_callback(self, interaction: discord.Interaction, button: ui.Button):
        voter = interaction.user
        
        if voter == self.target:
            return await interaction.response.send_message("You cannot vote on your own infection!", ephemeral=True)

        if voter in self.infect_voters:
            self.infect_voters.remove(voter)
            
        if voter not in self.protect_voters:
             self.protect_voters.add(voter)

        self.children[0].label = f"Infect ({len(self.infect_voters)} FFcoins)"
        self.children[1].label = f"Protect ({len(self.protect_voters)} FFcoins)"

        await interaction.response.edit_message(view=self)

        await self.check_win_condition(interaction)

class InfectCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
    @app_commands.command(name="infect", description="Attempt to infect a user with a vote.")
    @app_commands.describe(target="The user you want to infect.")
    async def infect(self, interaction: discord.Interaction, target: discord.Member):
        
        if target == interaction.user:
            await interaction.response.send_message("You can't infect yourself!", ephemeral=True)
            return
        if target.bot:
            await interaction.response.send_message("You can't infect a bot!", ephemeral=True)
            return

        infected_role = discord.utils.get(interaction.guild.roles, name=INFECTED_ROLE_NAME)
        if infected_role and infected_role in target.roles:
             await interaction.response.send_message(f"{target.mention} is already infected! Wait for the role to be manually removed or for a future un-infect command.", ephemeral=True)
             return

        embed = discord.Embed(
            title="🦠 An Infection is Spreading! 🦠",
            description=f"**{interaction.user.mention} is trying to infect {target.mention}!**\n\n"
                        f"The infection will succeed if the **Infect** votes are **5 or more** than the **Protect** votes.",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Click a button below to cast your vote (1000 imaginary FFcoins per vote).")

        view = InfectionView(initiator=interaction.user, target=target)
        await interaction.response.send_message(embed=embed, view=view)
        
        original_response = await interaction.original_response()
        view.message = original_response

async def setup(bot):
    await bot.add_cog(InfectCog(bot))
