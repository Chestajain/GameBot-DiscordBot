import discord
from discord.ext import commands
import time 
import os 

# --- Game Logic Class ---

class TicTacToeGame:
    """Manages the state and logic for a single game of Tic-Tac-Toe."""
    def __init__(self, playerX_id: int, playerO_id: int):
        self.board = ['\u200b'] * 9
        self.current_player = 'X'
        self.winner = None
        self.game_over = False
        self.playerX_id = playerX_id
        self.playerO_id = playerO_id
        self.player_map = {'X': self.playerX_id, 'O': self.playerO_id}

    def get_current_player_id(self) -> int:
        return self.player_map[self.current_player]
        
    def get_opponent_id(self) -> int:
        opponent = 'O' if self.current_player == 'X' else 'X'
        return self.player_map[opponent]

    def make_move(self, position: int) -> bool:
        if self.game_over or not (0 <= position < 9) or self.board[position] != '\u200b':
            return False

        self.board[position] = self.current_player
        
        if self._check_win():
            self.winner = self.current_player
            self.game_over = True
        elif self._check_draw():
            self.winner = 'Draw'
            self.game_over = True
        else:
            self._switch_player()
            
        return True

    def _switch_player(self):
        self.current_player = 'O' if self.current_player == 'X' else 'X'

    def _check_win(self) -> bool:
        win_conditions = [
            (0, 1, 2), (3, 4, 5), (6, 7, 8),
            (0, 3, 6), (1, 4, 7), (2, 5, 8),
            (0, 4, 8), (2, 4, 6)             
        ]

        for a, b, c in win_conditions:
            if (self.board[a] == self.current_player and 
                self.board[b] == self.current_player and 
                self.board[c] == self.current_player):
                return True
        return False

    def _check_draw(self) -> bool:
        return '\u200b' not in self.board

    def get_status_message(self) -> str:
        if self.game_over:
            if self.winner == 'Draw':
                return "It's a draw!"
            return f"Player {self.winner} wins!"
        
        return f"Player {self.current_player}'s turn."


# --- Discord View ---

class TicTacToeView(discord.ui.View):
    """
    A persistent view that represents the Tic-Tac-Toe board using buttons.
    """
    def __init__(self, game_session: TicTacToeGame, active_games_ref: dict, message_id: int, *args, **kwargs):
        # Timeout set to 30 seconds for the move timer
        super().__init__(timeout=30) 
        self.game_session = game_session
        self.active_games = active_games_ref
        self.message_id = message_id         
        self.message = None 
        self._create_buttons()

    def _get_button_style(self, marker: str) -> discord.ButtonStyle:
        if marker == 'X':
            return discord.ButtonStyle.primary
        elif marker == 'O':
            return discord.ButtonStyle.success
        return discord.ButtonStyle.secondary

    def _create_buttons(self):
        self.clear_items()
        
        for i in range(9):
            marker = self.game_session.board[i]
            disabled = self.game_session.game_over or marker != '\u200b'
            label = marker if marker != '\u200b' else '\u200b' 
            style = self._get_button_style(marker)
            
            button = discord.ui.Button(
                label=label, 
                style=style, 
                custom_id=f"tictactoe_move_{i}",
                disabled=disabled,
                row=i // 3
            )
            
            button.callback = self.create_move_callback(i)
            self.add_item(button)

    def _create_embed(self, game_over=False) -> tuple[discord.Embed, list[discord.File]]:
        """
        Creates the game board embed and returns (Embed, List[File]).
        """
        files_to_send = []
        
        if game_over:
            winner_id = self.game_session.player_map.get(self.game_session.winner)
            
            if self.game_session.winner == 'Draw':
                status = "It's a draw! 🤝"
                title = "Tic-Tac-Toe Battle: Draw!"
                color = discord.Color.blue()
            else:
                status = f"<@{winner_id}> wins! 🎉"
                title = "Tic-Tac-Toe Battle: Victory!"
                color = discord.Color.gold()
            
            embed = discord.Embed(title=title, description=status, color=color)
            
            # --- WIN IMAGE LOGIC ---
            image_filename = "win_tictactoe.png"
            script_dir = os.path.dirname(os.path.abspath(__file__)) 
            image_file_path = os.path.join(script_dir, image_filename)
            
            if os.path.exists(image_file_path):
                win_file = discord.File(image_file_path, filename="win_image.png")
                embed.set_thumbnail(url="attachment://win_image.png")
                files_to_send.append(win_file)
            else:
                print(f"ERROR: Win image file NOT FOUND: {image_file_path}")

        else:
            embed = discord.Embed(title="Tic-Tac-Toe Battle", color=discord.Color.green())
            current_player_id = self.game_session.get_current_player_id()
            
            # Calculate next timeout time for dynamic display
            timeout_timestamp = int(time.time() + 30)
            
            embed.description = (
                f"It is **<@{current_player_id}>'s turn** ({self.game_session.current_player}).\n"
                f"You have until <t:{timeout_timestamp}:R> to make a move!"
            )
        
        return embed, files_to_send


    def create_move_callback(self, position: int):
        async def callback(interaction: discord.Interaction):
            # 1. Validation
            current_player_id = self.game_session.get_current_player_id()
            if interaction.user.id != current_player_id:
                await interaction.response.send_message("It's not your turn!", ephemeral=True)
                return

            # 2. Attempt move
            if not self.game_session.make_move(position):
                await interaction.response.send_message("That's not a valid move!", ephemeral=True)
                return

            self._create_buttons()

            # 3. Check status and cleanup
            if self.game_session.game_over:
                # Game over message and embed
                embed, files = self._create_embed(game_over=True)
                self.stop() 
                
                # CRUCIAL MANUAL CLEANUP using MESSAGE ID
                try:
                    if self.message_id in self.active_games:
                        del self.active_games[self.message_id]
                except Exception:
                    pass
                
                # Update message with final status and embed, including the files
                await interaction.response.edit_message(content=None, embed=embed, view=self, attachments=files)
            else:
                # Reset the view timeout for the new player's turn
                self.stop() 
                new_view = TicTacToeView(self.game_session, self.active_games, self.message_id)
                new_view.message = self.message # Pass the message reference

                embed, _ = new_view._create_embed(game_over=False)
                
                # Update message with new turn status and embed (no new attachments needed here)
                await interaction.response.edit_message(content=None, embed=embed, view=new_view)

        return callback

    # Handles cleanup when the move timer expires (30 seconds)
    async def on_timeout(self):
        """Called when the 30-second move timer expires. Declares opponent winner."""
        
        if self.message_id in self.active_games:
            opponent_id = self.game_session.get_opponent_id()
            
            # Manually set the game state for the winning condition
            self.game_session.game_over = True
            self.game_session.winner = 'O' if self.game_session.current_player == 'X' else 'X'
            
            # Cleanup Global State
            try:
                del self.active_games[self.message_id]
            except Exception:
                pass
                
            # Update the View and Message
            self._create_buttons() # Disable buttons
            
            # Create the final timeout embed
            embed = discord.Embed(
                title="⏱️ Time Expired!",
                description=(
                    f"<@{self.game_session.get_current_player_id()}> failed to move in 30 seconds. Guess running away was their winning strategy.\n"
                    f"**<@{opponent_id}> wins by forfeit!**"
                ),
                color=discord.Color.red()
            )
            
            # Check if the message object is available
            if self.message:
                try:
                    await self.message.edit(content=None, embed=embed, view=self, attachments=[])
                except Exception:
                    pass