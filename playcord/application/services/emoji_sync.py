"""Purge and reupload Discord application emojis from the manifest."""

from __future__ import annotations

from dataclasses import dataclass, field

from discord.ext import commands

from playcord.infrastructure.constants import ICONS_DIR
from playcord.infrastructure.logging import get_logger
from playcord.presentation.ui import emojis
from playcord.presentation.ui.emoji_manifest import (
    alias_assets,
    missing_asset_paths,
    uploadable_assets,
)

logger = get_logger("emoji_sync")


@dataclass(slots=True)
class EmojiSyncReport:
    deleted: int = 0
    uploaded: int = 0
    aliased: int = 0
    failures: list[str] = field(default_factory=list)
    missing_assets: list[str] = field(default_factory=list)
    aborted: bool = False

    @property
    def ok(self) -> bool:
        return not self.aborted and not self.failures


async def purge_and_reupload(bot: commands.Bot) -> EmojiSyncReport:
    """
    Delete all application emojis and reupload from ``assets/icons/``.

    Aborts without deleting anything when required asset files are missing.
    """
    report = EmojiSyncReport()
    missing = missing_asset_paths(ICONS_DIR)
    if missing:
        report.missing_assets = [
            str(path.relative_to(ICONS_DIR)) if path.is_relative_to(ICONS_DIR) else str(path)
            for path in missing
        ]
        logger.warning(
            "Emoji sync: %s asset(s) missing under %s, skipping them.",
            len(missing),
            ICONS_DIR,
        )

    try:
        existing = await bot.fetch_application_emojis()
    except Exception as exc:
        report.failures.append(f"fetch application emojis: {exc}")
        logger.exception("Failed to fetch application emojis")
        return report

    for emoji in existing:
        try:
            await emoji.delete()
            report.deleted += 1
        except Exception as exc:
            report.failures.append(f"delete {getattr(emoji, 'name', emoji)!r}: {exc}")
            logger.exception("Failed to delete application emoji %r", getattr(emoji, "name", emoji))

    mapping: dict[str, int] = {}
    for asset in uploadable_assets():
        path = asset.asset_path(ICONS_DIR)
        if path is None:
            report.failures.append(f"upload {asset.key}: no asset path")
            continue
        try:
            created = await bot.create_application_emoji(
                name=asset.upload_name(),
                image=path.read_bytes(),
            )
        except Exception as exc:
            report.failures.append(f"upload {asset.key}: {exc}")
            logger.exception("Failed to upload emoji %r", asset.key)
            continue
        mapping[asset.key] = int(created.id)
        report.uploaded += 1

    for asset in alias_assets():
        target_id = mapping.get(asset.alias_of or "")
        if target_id is None:
            report.failures.append(
                f"alias {asset.key}: target {asset.alias_of!r} was not uploaded",
            )
            continue
        mapping[asset.key] = target_id
        report.aliased += 1

    if mapping:
        emojis.apply_uploaded_ids(mapping)
        emojis.write_id_cache()

    return report
