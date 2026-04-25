"""Reusable helpers for reporting errors back to Discord in the most relevant place.

Provides a single async function `try_send_error_embed` which attempts multiple delivery
strategies (edit game message, post to thread,
post to status channel, edit status message)and logs failures along the way. Designed to be imported and reused by interfaces.
"""

from playcord.utils.containers import (
    ErrorContainer,
    container_edit_kwargs,
    container_send_kwargs,
)
from playcord.utils.locale import get


async def try_send_error_embed(
    logger,
    error: Exception,
    *,
    game_message: object | None = None,
    thread: object | None = None,
    status_message: object | None = None,
    thread_id: int | None = None,
) -> bool:
    """Try to notify users about ``error`` by sending an error embed.

    Attempts (in order):
    1. Edit ``game_message`` with an error embed
    2. Send the embed into ``thread``
    3. Send the embed to ``status_message.channel``
    4. Edit ``status_message`` (simple fallback edit when embed kwargs fail)

    Returns True if any of the attempts succeeded, False otherwise.
    Logs exceptions encountered while trying each channel.
    """
    # Determine a short "what failed" description like the original implementation
    if hasattr(error, "__module__") and "discord" in error.__module__:
        what_failed = f"Discord API: {type(error).__name__}"
    else:
        what_failed = f"Game Engine: {type(error).__name__}"

    error_embed = ErrorContainer(what_failed=what_failed, reason=str(error))

    # 1) Try to edit the game message using container edit kwargs
    try:
        if game_message is not None:
            await game_message.edit(
                **container_edit_kwargs(error_embed, attachments=None)
            )
            return True
    except Exception:
        logger.exception(
            "Failed to edit game_message with error embed; will try fallbacks"
        )

    # 2) Try to send into the private thread using container send kwargs
    try:
        if thread is not None:
            await thread.send(**container_send_kwargs(error_embed))
            return True
    except Exception:
        logger.exception("Failed to send error embed to thread; will try fallbacks")

    # 3) Try to send to the status message channel
    try:
        if (
            status_message is not None
            and getattr(status_message, "channel", None) is not None
        ):
            await status_message.channel.send(**container_send_kwargs(error_embed))
            return True
    except Exception:
        logger.exception(
            "Failed to send error embed to status_message.channel; will try to edit status_message"
        )

    # 4) Try to edit the status message as a
    last resort (use plain content fallback if edit kwargs fail)    try:
        if status_message is not None:
            try:
                await status_message.edit(
                    **container_edit_kwargs(error_embed, attachments=None)
                )
            except Exception:
                # Fall back to a short textual alert if editing with container fails
                try:
                    await status_message.edit(
                        content=get("errors.display_update_failed"),
                        embeds=[],
                        view=None,
                        attachments=[],
                    )
                except Exception:
                    logger.exception(
                        "Failed to edit status_message with fallback content"
                    )
            return True
    except Exception:
        logger.exception("Failed to notify via status_message; giving up")

    return False
