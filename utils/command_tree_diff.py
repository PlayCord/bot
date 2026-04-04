"""
Compare locally registered app commands to Discord's API (``tree.fetch_commands``).
"""

from __future__ import annotations

from typing import Any

import discord
from discord import app_commands
from discord.app_commands.models import AppCommandGroup, Argument


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
        differences.append("Command description was modified")

    lparams = {p.name: p for p in local_cmd.parameters}
    ropts = {a.name: a for a in remote_args}

    if set(lparams.keys()) != set(ropts.keys()):
        differences.append(
            f"Parameter set mismatch (local {sorted(lparams)!s}, remote {sorted(ropts)!s})"
        )
        return differences

    for name in sorted(lparams):
        p = lparams[name]
        r = ropts[name]
        if (p.description or "").strip() != (r.description or "").strip():
            differences.append(f"Parameter '{name}' description was modified")
        if p.required != r.required:
            differences.append(f"Parameter '{name}' required status was modified")
        if p.type.value != r.type.value:
            differences.append(f"Parameter '{name}' type was modified")

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
    local_all = drift.get("local_all") or []
    remote_all = drift.get("remote_all") or []
    lines.append(f"**All registered locally ({len(local_all)}):**")
    if local_all:
        lines.extend(f"- `{n}`" for n in local_all)
    else:
        lines.append("_none_")
    lines.append(f"**All registered remotely ({len(remote_all)}):**")
    if remote_all:
        lines.extend(f"- `{n}`" for n in remote_all)
    else:
        lines.append("_none_")
    lines.append("---")
    lines.append("**Diff**")
    lines.append("**Added locally (not on API):**")
    if drift["added"]:
        lines.extend(f"- `{n}`" for n in drift["added"])
    else:
        lines.append("_none_")
    lines.append("**Removed from API (not local):**")
    if drift["removed"]:
        lines.extend(f"- `{n}`" for n in drift["removed"])
    else:
        lines.append("_none_")
    mod = drift.get("modified") or {}
    if not mod:
        lines.append("**Modified:** _none_")
    else:
        lines.append("**Modified:**")
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
            lines.append("… _(truncated)_")
    return "\n".join(lines)


async def fetch_and_analyze_tree(
        tree: app_commands.CommandTree, *, guild: discord.abc.Snowflake | None = None
) -> dict[str, Any]:
    remote = await tree.fetch_commands(guild=guild)
    local_leaves = collect_local_tree(tree, guild=guild)
    remote_leaves = collect_remote_tree(list(remote))
    return analyze_command_tree_drift(local_leaves=local_leaves, remote_leaves=remote_leaves)
