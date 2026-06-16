# PlayCord icon kit

Thin-outline icons for consistent cross-platform UI.

## Source of truth

Emoji keys, filenames, animated flags, game bucket entries, and aliases are declared in
`playcord/presentation/ui/emoji_manifest.py`. Resolved Discord ids are written to
`playcord/configuration/emoji.yaml` (generated id cache).

## Upload options

**In-bot (owner):** `playcord/emoji` — full purge of application emojis, then reupload
from this folder. Aborts without deleting anything if required files are missing.

**Offline CLI:**

```bash
python scripts/upload_emojis.py --token YOUR_BOT_TOKEN
```

Use `--dry-run` to list manifest assets without calling Discord.

## Asset spec

- **Format:** WebP (GIF for animated manifest keys such as `loading`)
- **Size:** 128×128 px canvas, glyph centered
- **Style:** 2px stroke, rounded caps, no fill (outline only)
- **Color:** `#EBEBEB` on transparent background
- **Naming:** `{key}.webp` for general icons; `game_{slug}.webp` for game catalog icons
- **Aliases:** `user` and `hmm` reuse `profile` / `info` assets (no separate files)

## Required icons

Every non-alias entry in `EMOJI_MANIFEST` must have a matching file before sync runs.
See the manifest for the full list (navigation, actions, pages, status, misc, and
`game_*` catalog icons).
