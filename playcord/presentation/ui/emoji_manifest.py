"""Canonical emoji manifest: keys, assets, and upload metadata."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from playcord.infrastructure.constants import ICONS_DIR


@dataclass(frozen=True, slots=True)
class EmojiAsset:
    """One application emoji declared by PlayCord."""

    key: str
    filename: str | None = None
    animated: bool = False
    game: bool = False
    alias_of: str | None = None

    def upload_name(self) -> str:
        """Discord application emoji name (unique across the app)."""
        if self.alias_of is not None:
            msg = f"Alias asset {self.key!r} has no upload name"
            raise ValueError(msg)
        return f"game_{self.key}" if self.game else self.key

    def resolve_filename(self) -> str | None:
        if self.filename is not None:
            return self.filename
        if self.alias_of is not None:
            return None
        ext = "webp"
        if self.game:
            return f"game_{self.key}.{ext}"
        return f"{self.key}.{ext}"

    def asset_path(self, icons_dir: Path | None = None) -> Path | None:
        name = self.resolve_filename()
        if name is None:
            return None
        root = icons_dir or ICONS_DIR
        return root / name


def _asset(
    key: str,
    *,
    animated: bool = False,
    game: bool = False,
    alias_of: str | None = None,
    filename: str | None = None,
) -> EmojiAsset:
    return EmojiAsset(
        key=key,
        filename=filename,
        animated=animated,
        game=game,
        alias_of=alias_of,
    )


EMOJI_MANIFEST: tuple[EmojiAsset, ...] = (
    # Navigation
    _asset("back"),
    _asset("forward"),
    _asset("first"),
    _asset("last"),
    # Actions
    _asset("play"),
    _asset("join"),
    _asset("leave"),
    _asset("ready"),
    _asset("creator"),
    _asset("rematch"),
    _asset("spectate"),
    _asset("peek"),
    _asset("external_link"),
    # Pages / commands
    _asset("settings"),
    _asset("info"),
    _asset("about"),
    _asset("stats"),
    _asset("profile"),
    _asset("catalog"),
    _asset("history"),
    _asset("replay"),
    _asset("help"),
    # Status
    _asset("success"),
    _asset("error"),
    _asset("pending"),
    _asset("timer"),
    _asset("warning"),
    _asset("loading", animated=True),
    # Misc
    _asset("pointing"),
    _asset("github"),
    _asset("heart"),
    _asset("assign_roles"),
    _asset("playcord"),
    # Legacy / expressive
    _asset("user", alias_of="profile"),
    _asset("facepalm", animated=True),
    _asset("clueless"),
    _asset("explosion", animated=True),
    _asset("hmm", alias_of="info"),
    # Game catalog icons
    _asset("tictactoe", game=True),
    _asset("connectfour", game=True),
    _asset("nim", game=True),
    _asset("mafia", game=True),
    _asset("secret_hitler", game=True),
)


def manifest_by_key() -> dict[str, EmojiAsset]:
    return {asset.key: asset for asset in EMOJI_MANIFEST}


def manifest_by_bucket() -> tuple[dict[str, dict], dict[str, dict]]:
    """Seed ``emojis`` and ``game_emojis`` dicts from the manifest (id defaults to 0)."""
    general: dict[str, dict] = {}
    games: dict[str, dict] = {}
    for asset in EMOJI_MANIFEST:
        entry = {"id": 0, "animated": asset.animated}
        if asset.game:
            games[asset.key] = entry
        else:
            general[asset.key] = entry
    return general, games


def uploadable_assets() -> tuple[EmojiAsset, ...]:
    return tuple(asset for asset in EMOJI_MANIFEST if asset.alias_of is None)


def alias_assets() -> tuple[EmojiAsset, ...]:
    return tuple(asset for asset in EMOJI_MANIFEST if asset.alias_of is not None)


def missing_asset_paths(icons_dir: Path | None = None) -> list[Path]:
    """Local files required before a purge/reupload may run."""
    root = icons_dir or ICONS_DIR
    missing: list[Path] = []
    for asset in uploadable_assets():
        path = asset.asset_path(root)
        if path is None or not path.is_file():
            missing.append(path or root / (asset.resolve_filename() or asset.key))
    return missing
