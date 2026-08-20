import asyncio
import logging
import os
from pathlib import Path

import discord

from services import audit_service, auth_service, discord_binding_service, vera_conversation_service
from storage import connection, initialize_storage


logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("vera.discord")
GUILD_ID = int(os.environ["VERA_DISCORD_GUILD_ID"])
CHANNEL_ID = int(os.environ["VERA_DISCORD_CHANNEL_ID"])


def _token() -> str:
    path = Path(os.getenv("VERA_DISCORD_TOKEN_FILE", "/run/secrets/discord_bot_token"))
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError("Discord bot token is empty.")
    return value


class VeraDiscordClient(discord.Client):
    async def on_ready(self):
        logger.info("Vera Discord gateway connected as %s", self.user)

    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if message.guild.id != GUILD_ID or message.channel.id != CHANNEL_ID:
            return
        content = message.content.strip()
        if not content:
            return
        try:
            binding = await asyncio.to_thread(
                discord_binding_service.get_or_create,
                owner_user_id=auth_service.OWNER_ID,
                guild_id=str(message.guild.id),
                channel_id=str(message.channel.id),
                discord_user_id=str(message.author.id),
            )
            async with message.channel.typing():
                result = await asyncio.to_thread(
                    vera_conversation_service.respond,
                    owner_user_id=auth_service.OWNER_ID,
                    conversation_id=binding["conversation_id"],
                    content=content,
                    client_message_id=f"discord:{message.id}",
                    source="discord",
                )
            assistant = result.get("assistant_message")
            if assistant:
                text = assistant["content"]
                for start in range(0, len(text), 1900):
                    await message.reply(text[start:start + 1900], mention_author=False, allowed_mentions=discord.AllowedMentions.none())
        except discord_binding_service.DiscordIdentityDeniedError:
            audit_service.append_event(
                action="discord.identity_denied", resource_type="discord_channel", resource_id=str(CHANNEL_ID),
                outcome="denied", request_id=str(message.id), details={"discord_user_id": str(message.author.id)}
            )
        except Exception:
            logger.exception("Vera could not process Discord message %s", message.id)
            await message.reply("I couldn't complete that response. It was logged for review.", mention_author=False, allowed_mentions=discord.AllowedMentions.none())


def main():
    initialize_storage()
    with connection() as conn:
        owner = conn.execute("SELECT id FROM users WHERE id = ? AND active = 1", (auth_service.OWNER_ID,)).fetchone()
    if not owner:
        raise RuntimeError("Vera owner identity is unavailable.")
    intents = discord.Intents.default()
    intents.message_content = True
    VeraDiscordClient(intents=intents).run(_token(), log_handler=None)


if __name__ == "__main__":
    main()
