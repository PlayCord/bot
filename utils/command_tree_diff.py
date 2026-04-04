"""
Compare locally registered app commands to Discord's API (``tree.fetch_commands``).
"""

from __future__ import annotations

from typing import Any

import discord
from discord import app_commands
from discord.app_commands.models import AppCommandGroup, Argument
from utils.locale import fmt, get


def _collect_local_leaves(
        cmd: app_commands.Command | app_commands.Group | app_commands.ContextMenu,
        prefix: tuple[str, ...]
) -> dict[str, app_commands.Command | app_commands.ContextMenu]:
    if isinstance(cmd, app_commands.Group):
        new_p = prefix + (cmd.name,)
        out: dict[str, app_commands.Command | app_commands.ContextMenu] = {}

        # FIX: Iterate directly over the list, do not use .values()
        for child in cmd.commands:
            out.update(_collect_local_leaves(child, new_p))
        return out

    path = " ".join(prefix + (cmd.name,))
    return {path: cmd}


def collect_local_tree(
        tree: app_commands.CommandTree, *, guild: discord.abc.Snowflake | None
) -> dict[str, app_commands.Command]:
    merged: dict[str, app_commands.Command] = {}
    for top in tree.get_commands(guild=guild):
        merged.update(_collect_local_leaves(top, ()))
    return merged


def _collect_remote_leaves(ac: discord.AppCommand) -> dict[str, dict[str, Any]]:
    """Map qualified slash path -> {description, arguments} for leaf commands."""
    out: dict[str, dict[str, Any]] = {}
    opts = ac.options or []

    if not opts:
        out[ac.name] = {
            "description": (ac.description or "").strip(),
            "arguments": [],
        }
        return out

    if all(isinstance(x, Argument) for x in opts):
        out[ac.name] = {
            "description": (ac.description or "").strip(),
            "arguments": list(opts),
        }
        return out

    def walk(options: list, parts: tuple[str, ...]) -> None:
        for opt in options or []:
            if isinstance(opt, AppCommandGroup):
                np = parts + (opt.name,)
                ch = opt.options or []
                if ch and all(isinstance(x, Argument) for x in ch):
                    out[" ".join(np)] = {
                        "description": (opt.description or "").strip(),
                        "arguments": list(ch),
                    }
                else:
                    walk(ch, np)

    walk(opts, (ac.name,))
    return out


def collect_remote_tree(commands: list[discord.AppCommand]) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for ac in commands:
        merged.update(_collect_remote_leaves(ac))
    return merged


def _deep_compare_leaf(
        local_cmd: app_commands.Command, remote_description: str, remote_args: list[Argument]
) -> list[str]:
    """Compare a local leaf Command to API description + option list."""
    differences: list[str] = []
    loc_desc = (local_cmd.description or "").strip()
    if loc_desc != remote_description:
        differences.append(get("commands.treediff.diff.command_description_modified"))

    lparams = {p.name: p for p in local_cmd.parameters}
    ropts = {a.name: a for a in remote_args}

    if set(lparams.keys()) != set(ropts.keys()):
        differences.append(
            fmt(
                "commands.treediff.diff.parameter_set_mismatch",
                local_names=", ".join(sorted(lparams.keys())) or "—",
                remote_names=", ".join(sorted(ropts.keys())) or "—",
            )
        )
        return differences

    for name in sorted(lparams):
        p = lparams[name]
        r = ropts[name]
        if (p.description or "").strip() != (r.description or "").strip():
            differences.append(fmt("commands.treediff.diff.param_description_modified", name=name))
        if p.required != r.required:
            differences.append(fmt("commands.treediff.diff.param_required_modified", name=name))
        if p.type.value != r.type.value:
            differences.append(fmt("commands.treediff.diff.param_type_modified", name=name))

    return differences


def analyze_command_tree_drift(
        *,
        local_leaves: dict[str, app_commands.Command],
        remote_leaves: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    added = sorted(set(local_leaves.keys()) - set(remote_leaves.keys()))
    removed = sorted(set(remote_leaves.keys()) - set(local_leaves.keys()))
    modified: dict[str, list[str]] = {}
    for name in sorted(set(local_leaves.keys()) & set(remote_leaves.keys())):
        lc = local_leaves[name]
        rnode = remote_leaves[name]
        rdesc = rnode.get("description") or ""
        rargs = rnode.get("arguments") or []
        diffs = _deep_compare_leaf(lc, rdesc, rargs)
        if diffs:
            modified[name] = diffs
    return {
        "added": added,
        "removed": removed,
        "modified": modified,
        "local_all": sorted(local_leaves.keys()),
        "remote_all": sorted(remote_leaves.keys()),
    }


def format_drift_report(drift: dict[str, Any], *, max_lines: int = 40) -> str:
    lines: list[str] = []
    none = get("common.empty_markdown")
    local_all = drift.get("local_all") or []
    remote_all = drift.get("remote_all") or []
    lines.append(fmt("commands.treediff.report.all_local", count=len(local_all)))
    if local_all:
        lines.extend(f"- `{n}`" for n in local_all)
    else:
        lines.append(none)
    lines.append(fmt("commands.treediff.report.all_remote", count=len(remote_all)))
    if remote_all:
        lines.extend(f"- `{n}`" for n in remote_all)
    else:
        lines.append(none)
    lines.append(get("commands.treediff.report.separator"))
    lines.append(get("commands.treediff.report.section_diff"))
    lines.append(get("commands.treediff.report.added_header"))
    if drift["added"]:
        lines.extend(f"- `{n}`" for n in drift["added"])
    else:
        lines.append(none)
    lines.append(get("commands.treediff.report.removed_header"))
    if drift["removed"]:
        lines.extend(f"- `{n}`" for n in drift["removed"])
    else:
        lines.append(none)
    mod = drift.get("modified") or {}
    if not mod:
        lines.append(get("commands.treediff.report.modified_none"))
    else:
        lines.append(get("commands.treediff.report.modified_header"))
        line_count = 0
        truncated = False
        for cmd_name, changes in mod.items():
            if line_count >= max_lines:
                truncated = True
                break
            lines.append(f"- `{cmd_name}`")
            line_count += 1
            for c in changes:
                if line_count >= max_lines:
                    truncated = True
                    break
                lines.append(f"  - `{c}`")
                line_count += 1
            if truncated:
                break
        if truncated:
            lines.append(get("commands.treediff.report.truncated"))
    return "\n".join(lines)


_ZWSP = "\u200b"


def drift_to_embed(
    drift: dict[str, Any],
    *,
    color: discord.Color,
    title: str,
    inline_column_limit: int = 340,
    max_modified_sections: int = 14,
) -> discord.Embed:
    """
    Build one embed: summary row, three-column drift (added / removed / modified names),
    then non-inline fields per modified command (diff lines).
    """
    local_all = list(drift.get("local_all") or [])
    remote_all = list(drift.get("remote_all") or [])
    added = list(drift.get("added") or [])
    removed = list(drift.get("removed") or [])
    modified: dict[str, list[str]] = dict(drift.get("modified") or {})

    embed = discord.Embed(title=title[:256], color=color)
    embed.description = fmt(
        "commands.treediff.embed_description_stats",
        local_n=len(local_all),
        remote_n=len(remote_all),
        n_add=len(added),
        n_rem=len(removed),
        n_mod=len(modified),
    )[:4096]

    def short_list(names: list[str], lim: int) -> str:
        if not names:
            return get("common.empty_markdown")
        parts = [f"`{n}`" for n in names]
        s = ", ".join(parts)
        if len(s) <= lim:
            return s
        acc: list[str] = []
        total = 0
        for p in parts:
            sep = 2 if acc else 0
            if total + sep + len(p) > lim - 3:
                break
            acc.append(p)
            total += sep + len(p)
        return ", ".join(acc) + "\n…" if acc else "…"

    row_counts = [
        ("commands.treediff.field_local_leaves", str(len(local_all))),
        ("commands.treediff.field_remote_leaves", str(len(remote_all))),
        (
            "commands.treediff.field_drift_totals",
            f"`+{len(added)}` / `−{len(removed)}` / `~{len(modified)}`",
        ),
    ]
    for locale_key, value in row_counts:
        embed.add_field(name=get(locale_key), value=value[:1024], inline=True)

    row_lists = [
        ("commands.treediff.field_added", short_list(added, inline_column_limit)),
        ("commands.treediff.field_removed", short_list(removed, inline_column_limit)),
        (
            "commands.treediff.field_modified_cmds",
            short_list(list(modified.keys()), inline_column_limit),
        ),
    ]
    for locale_key, value in row_lists:
        embed.add_field(name=get(locale_key), value=value[:1024], inline=True)

    mod_sorted = sorted(modified.items())
    shown = 0
    for cmd_name, changes in mod_sorted:
        if len(embed.fields) >= 24 or shown >= max_modified_sections:
            break
        body = "\n".join(f"• {c}" for c in changes)
        if len(body) > 1024:
            body = body[:1021] + "…"
        embed.add_field(
            name=f"`{cmd_name}`"[:256],
            value=body or _ZWSP,
            inline=False,
        )
        shown += 1

    if shown < len(mod_sorted):
        embed.add_field(
            name=get("commands.treediff.field_more_modified"),
            value=fmt("commands.treediff.more_modified_detail", n=len(mod_sorted) - shown),
            inline=False,
        )

    return embed


async def fetch_and_analyze_tree(
        tree: app_commands.CommandTree, *, guild: discord.abc.Snowflake | None = None
) -> dict[str, Any]:
    remote = await tree.fetch_commands(guild=guild)
    local_leaves = collect_local_tree(tree, guild=guild)
    remote_leaves = collect_remote_tree(list(remote))
    return analyze_command_tree_drift(local_leaves=local_leaves, remote_leaves=remote_leaves)
