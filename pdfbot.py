"""
Discord bot that converts PDF files into images and sends them.

This bot only needs the Message Content Intent. However, it also needs the
following permissions:
 - Send messages
 - Add reactions
 - Read message history
"""

# Copyright 2024 Sebastian Ashkar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
import functools
import logging
import os
import sys
import typing

import aiohttp
import dotenv
import hikari
import pdf2image

DOTENV_PATH: typing.Final[str | None] = ".env"  # Default to first CLI arg.
IMAGE_DPI: typing.Final[int] = 800
LOGGER: typing.Final[logging.Logger] = logging.getLogger()
REACT_TO_MESSAGES: typing.Final[bool] = True
MAX_THREAD_COUNT: typing.Final[int] = 10  # Maxes out at 1 thread per page.


async def handle_pdf(
    message: hikari.Message,
    attachment: hikari.Attachment,
) -> None:
    """Download a PDF file attachment, and send JPEG files of its pages."""
    async with aiohttp.ClientSession() as session:
        async with await session.get(attachment.url) as response:
            if response.status != 200:
                logging.error(
                    "HTTP %d: %s during GET '%s'",
                    response.status,
                    response.reason,
                    attachment.url,
                )
                return

            pdf_file_bytes = await response.read()
            loop = asyncio.get_event_loop()
            images = await loop.run_in_executor(
                None,
                functools.partial(
                    pdf2image.convert_from_bytes,
                    pdf_file_bytes,
                    dpi=IMAGE_DPI,
                    fmt="jpeg",
                    thread_count=MAX_THREAD_COUNT,
                ),
            )

            try:
                basename = next(iter(attachment.filename.split(".")), "pdf")
                await message.respond(
                    reply=True,
                    attachments=[
                        hikari.Bytes(
                            bytes(image.tobytes("jpeg", ("RGB"))),
                            f"{basename}_{i + 1}.jpg",
                        )
                        for i, image in enumerate(images)
                    ],
                )
            except hikari.ForbiddenError as e:
                pass


async def handle_message(
    bot: hikari.GatewayBot, event: hikari.MessageCreateEvent
) -> None:
    """Handle an incoming message."""
    message = await bot.rest.fetch_message(event.channel_id, event.message)
    if not message or message.author.is_bot or message.author.is_system:
        return

    pdf_attachments = [a for a in message.attachments if a.filename.endswith(".pdf")]
    if len(pdf_attachments) == 0:
        return

    if REACT_TO_MESSAGES:
        try:
            await message.add_reaction("⏳")
        except hikari.ForbiddenError:
            pass

    LOGGER.info(
        "converting %d file(s) from %s",
        len(pdf_attachments),
        message.make_link(
            event.guild_id
            if isinstance(event, hikari.GuildMessageCreateEvent)
            else None
        ),
    )

    for attachment in pdf_attachments:
        await handle_pdf(message, attachment)


def main() -> None:
    """Main program entry-point."""
    if DOTENV_PATH is not None:
        dotenv.load_dotenv(DOTENV_PATH)
        discord_token = os.environ["DISCORD_TOKEN"]

    else:
        if len(sys.argv) < 2:
            print(f"usage: python3 {sys.argv[0]} <discord-token>", file=sys.stderr)
            return

        discord_token = sys.argv[1]

    bot = hikari.GatewayBot(
        banner=None,
        token=discord_token,
        intents=hikari.Intents.GUILD_MESSAGES
        | hikari.Intents.DM_MESSAGES
        | hikari.Intents.MESSAGE_CONTENT,
    )

    message_handler = functools.partial(handle_message, bot)
    bot.listen(hikari.GuildMessageCreateEvent)(message_handler)
    bot.listen(hikari.DMMessageCreateEvent)(message_handler)
    bot.run()


if __name__ == "__main__":
    main()
