# 🧊 Discord Bot: Tic-Tac-Toe & Freeze

This is a multi-feature Discord bot that includes an interactive Tic-Tac-Toe game and a community-driven "Freeze" punishment system.


## 🛡️ Required Discord Permissions

For the bot to function correctly, especially the `/freeze` command and its listener, it must have the following permissions in your Discord server:

| Permission | Purpose |
| :--- | :--- |
| **Manage Roles** | Required to assign and remove the **Frozen Role** during the freeze and unfreeze process. |
| **Moderate Members** | Required to apply the **timeout** when a frozen user attempts to speak (`on_message` listener). |
| **Send Messages** | Required for all command responses and sending direct messages for timeout warnings. |
| **Read Message History** | Required to retrieve the original message object for updating the interactive views (buttons). |
| **Use Application Commands** | Required for users to execute the slash commands (`/freeze`, `/tictactoe`, `/unfreeze`). |

**Note:** For the role management features to work, the bot's role must be positioned **higher** in the server's role hierarchy than the role it is trying to manage (i.e., higher than the `Frozen` role) and higher than the roles of the members it is trying to time out.

## 🎮 Commands

* `/tictactoe @user`: Start a game of Tic-Tac-Toe with another user.
* `/freeze @user`: Start a community vote to freeze a member for **2 minutes**.
* `/unfreeze @user`: (Requires **Manage Roles** permission) Immediately removes the Frozen role from a user. Has a **3 daily uses** cooldown, resetting at GMT midnight.

---

