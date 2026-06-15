"""Match, participant, move, replay, and match-history SQL."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

try:
    from psycopg import errors as pg_errors
except ImportError:
    pg_errors = None  # type: ignore[assignment]

from playcord.core.generators import generate_match_code
from playcord.infrastructure.database.models import (
    Match,
    MatchStatus,
    Participant,
    row_to_match,
    row_to_participant,
)

if TYPE_CHECKING:
    from playcord.infrastructure.database.implementation.database import Database


@dataclass(slots=True)
class MatchRepository:
    database: Database
    users: Any  # PlayerRepository
    guilds: Any  # GuildRepository
    games: Any  # GameRepository

    def get(self, match_id: int) -> Match | None:
        return self.get_match(match_id)

    def get_match(self, match_id: int) -> Match | None:
        query = "SELECT * FROM matches WHERE match_id = %s;"
        result = self.database.execute_query(query, (match_id,), fetchone=True)
        return row_to_match(result) if result else None

    def get_match_by_code(self, code: str) -> Match | None:
        c = (code or "").strip().lower()
        if not c:
            return None
        query = "SELECT * FROM matches WHERE lower(match_code) = %s;"
        result = self.database.execute_query(query, (c,), fetchone=True)
        return row_to_match(result) if result else None

    def get_by_code(self, code: str) -> Match | None:
        return self.get_match_by_code(code)

    def update_match_status(
        self,
        match_id: int,
        status: str,
        metadata_patch: dict[str, Any] | None = None,
    ) -> None:
        if metadata_patch:
            payload = json.dumps(metadata_patch)
            query = """
                UPDATE matches
                SET status = %s,
                    updated_at = NOW(),
                    ended_at = CASE WHEN %s = 'in_progress' THEN ended_at ELSE COALESCE(ended_at, NOW()) END,
                    metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb
                WHERE match_id = %s;
            """
            self.database.execute_query(query, (status, status, payload, match_id))
            return

        query = """
            UPDATE matches
            SET status = %s,
                updated_at = NOW(),
                ended_at = CASE WHEN %s = 'in_progress' THEN ended_at ELSE COALESCE(ended_at, NOW()) END
            WHERE match_id = %s;
        """
        self.database.execute_query(query, (status, status, match_id))

    def update_status(
        self,
        match_id: int,
        status: str,
        *,
        metadata_patch: dict[str, Any] | None = None,
    ) -> None:
        self.update_match_status(match_id, status, metadata_patch=metadata_patch)

    def interrupt_stale_matches(self, reason: str = "bot_restart") -> int:
        payload = json.dumps({"interrupt_reason": reason})
        query = """
            UPDATE matches
            SET status = 'interrupted',
                ended_at = COALESCE(ended_at, NOW()),
                updated_at = NOW(),
                metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb
            WHERE status = 'in_progress';
        """
        with self.database.get_connection() as conn, conn.cursor() as cur:
            cur.execute(query, (payload,))
            count = cur.rowcount
            conn.commit()
            return int(count) if count is not None else 0

    def merge_match_metadata_outcome_display(
        self,
        match_id: int,
        *,
        summaries: dict[int, str] | None = None,
        global_summary: str | None = None,
    ) -> None:
        patch: dict[str, Any] = {}
        if global_summary and str(global_summary).strip():
            patch["outcome_global_summary"] = str(global_summary).strip()
        if summaries is not None:
            patch["outcome_summaries"] = {
                str(uid): text for uid, text in summaries.items()
            }
        if not patch:
            return
        payload = json.dumps(patch)
        query = """
            UPDATE matches
            SET metadata = (COALESCE(metadata, '{}'::jsonb) - 'outcome_summary')
                || %s::jsonb
            WHERE match_id = %s;
        """
        self.database.execute_query(query, (payload, match_id))

    def get_match_human_user_ids_ordered(self, match_id: int) -> list[int]:
        query = """
            SELECT mp.user_id
            FROM match_participants mp
            JOIN users u ON u.user_id = mp.user_id
            WHERE mp.match_id = %s AND u.is_bot = FALSE AND mp.is_deleted = FALSE
            ORDER BY mp.player_number;
        """
        rows = self.database.execute_query(query, (match_id,), fetchall=True) or []
        return [int(r["user_id"]) for r in rows]

    def ensure_unique_match_code(self) -> str:
        """Reserve an unused public match code (may race with concurrent inserts)."""
        for _ in range(48):
            code = generate_match_code()
            if self.get_match_by_code(code) is None:
                return code
        msg = "Could not allocate a unique match_code"
        raise RuntimeError(msg)

    def create_match(
        self,
        game_id: int,
        guild_id: int,
        channel_id: int,
        thread_id: int | None,
        participants: list[int],
        game_config: dict[str, Any] | None = None,
        *,
        match_id: int,
        preset_match_code: str | None = None,
    ) -> tuple[int, str]:
        self.guilds.create_guild(guild_id)
        for user_id in participants:
            self.users.create_user(user_id)

        config_json = json.dumps(game_config or {})
        last_err: Exception | None = None
        for attempt in range(48):
            match_code = (
                preset_match_code
                if attempt == 0 and preset_match_code is not None
                else generate_match_code()
            )
            try:
                with self.database.transaction() as cur:
                    cur.execute(
                        """
                        INSERT INTO matches (match_id, game_id, guild_id, channel_id, thread_id,
                            game_config, status, match_code)
                        VALUES (%s, %s, %s, %s, %s, %s::jsonb, 'in_progress', %s)
                        RETURNING match_id;
                        """,
                        (
                            match_id,
                            game_id,
                            guild_id,
                            channel_id,
                            thread_id,
                            config_json,
                            match_code,
                        ),
                    )
                    result = cur.fetchone()
                    resolved_match_id = result["match_id"]

                    for idx, user_id in enumerate(participants, start=1):
                        cur.execute(
                            """
                            INSERT INTO match_participants
                                (match_id, user_id, player_number)
                            VALUES (%s, %s, %s);
                            """,
                            (resolved_match_id, user_id, idx),
                        )
                return resolved_match_id, match_code
            except Exception as e:
                if pg_errors and isinstance(
                    e,
                    pg_errors.UniqueViolation,
                ):  # type: ignore[misc]
                    last_err = e
                    continue
                raise
        msg = "Could not allocate a unique match_code"
        raise RuntimeError(msg) from last_err

    def end_match(
        self,
        match_id: int,
        final_state: dict[str, Any],
        results: dict[int, dict[str, Any]],
    ) -> None:
        metadata_patch_json = json.dumps({"final_state": final_state})
        with self.database.transaction() as cur:
            cur.execute(
                """
                SELECT game_id, guild_id, status
                FROM matches
                WHERE match_id = %s
                FOR UPDATE;
                """,
                (match_id,),
            )
            match = cur.fetchone()
            if not match:
                msg = f"Match {match_id} not found"
                raise ValueError(msg)
            if match["status"] == MatchStatus.COMPLETED.value:
                msg = f"Match {match_id} is already completed"
                raise ValueError(msg)

            for user_id, result in results.items():
                cur.execute(
                    """
                    UPDATE match_participants
                    SET final_ranking = %s,
                        score = %s
                    WHERE match_id = %s AND user_id = %s;
                    """,
                    (
                        result["ranking"],
                        result.get("score"),
                        match_id,
                        user_id,
                    ),
                )

            cur.execute(
                """
                UPDATE matches
                SET status = 'completed',
                    ended_at = NOW(),
                    metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb,
                    updated_at = NOW()
                WHERE match_id = %s;
                """,
                (metadata_patch_json, match_id),
            )

    def get_participants(self, match_id: int) -> list[Participant]:
        query = """
            SELECT * FROM match_participants
            WHERE match_id = %s AND is_deleted = FALSE
            ORDER BY player_number;
        """
        results = self.database.execute_query(query, (match_id,), fetchall=True)
        return [row_to_participant(row) for row in results] if results else []

    def record_move(
        self,
        match_id: int,
        user_id: int | None,
        move_number: int | None = None,
        move_data: dict[str, Any] | None = None,
        game_state_after: dict[str, Any] | None = None,
        time_taken_ms: int | None = None,
        is_game_affecting: bool = True,
        kind: str = "move",
    ) -> None:
        _ = move_number
        move_json = json.dumps(move_data) if move_data else None
        state_json = json.dumps(game_state_after) if game_state_after else None
        query_next = """
            SELECT COALESCE(MAX(move_number), 0) + 1 as next_move_num
            FROM match_moves
            WHERE match_id = %s;
        """
        result = self.database.execute_query(query_next, (match_id,), fetchone=True)
        auto_sequence = result["next_move_num"] if result else 1
        query = """
            INSERT INTO match_moves
                (match_id, user_id, move_number, kind, move_data, game_state_after,
                 time_taken_ms, is_game_affecting)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s);
        """
        self.database.execute_query(
            query,
            (
                match_id,
                user_id,
                auto_sequence,
                kind,
                move_json,
                state_json,
                time_taken_ms,
                is_game_affecting,
            ),
        )

    def get_move_count(self, match_id: int) -> int:
        query = "SELECT COUNT(*) as count FROM match_moves WHERE match_id = %s AND is_deleted = FALSE;"
        result = self.database.execute_query(query, (match_id,), fetchone=True)
        return result["count"] if result else 0

    def get_user_match_history(
        self,
        user_id: int,
        guild_id: int | None,
        game_id: int | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT
                m.match_id,
                m.match_code,
                m.game_id,
                g.game_name as game_key,
                g.display_name as game_name,
                m.ended_at,
                m.status,
                m.metadata,
                mp.final_ranking as final_ranking,
                mp.player_number,
                COUNT(*) OVER (PARTITION BY m.match_id) as player_count
            FROM match_participants mp
            JOIN matches m ON mp.match_id = m.match_id
            JOIN games g ON m.game_id = g.game_id
            WHERE mp.user_id = %s
              AND m.status IN ('completed', 'interrupted', 'abandoned')
        """
        params: list[Any] = [user_id]
        if guild_id is not None:
            query += " AND m.guild_id = %s"
            params.append(guild_id)
        if game_id is not None:
            query += " AND m.game_id = %s"
            params.append(game_id)
        query += """
            ORDER BY m.ended_at DESC
            LIMIT %s OFFSET %s;
        """
        params.extend([limit, offset])
        results = self.database.execute_query(query, tuple(params), fetchall=True)
        return results or []

    def get_history_for_user(
        self,
        user_id: int,
        *,
        guild_id: int | None = None,
        game_id: int | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        return self.get_user_match_history(
            user_id,
            guild_id,
            game_id=game_id,
            limit=limit,
            offset=offset,
        )

    def count_matches_for_user(
        self,
        user_id: int,
        guild_id: int,
    ) -> int:
        query = """
            SELECT COUNT(DISTINCT m.match_id) AS total_matches
            FROM match_participants mp
            JOIN matches m ON mp.match_id = m.match_id
            WHERE mp.user_id = %s AND m.guild_id = %s
              AND m.status IN ('completed', 'interrupted', 'abandoned')
              AND mp.is_deleted = FALSE;
        """
        result = self.database.execute_query(query, (user_id, guild_id), fetchone=True)
        return result["total_matches"] if result else 0

    def create_game(
        self,
        game_name: str,
        guild_id: int,
        participants: list[int],
        channel_id: int | None = None,
        thread_id: int | None = None,
        game_config: dict[str, Any] | None = None,
        *,
        match_id: int,
        preset_match_code: str | None = None,
    ) -> tuple[int, str]:
        game = self.games.get_game(game_name)
        if not game:
            msg = f"Game {game_name} not found"
            raise ValueError(msg)
        resolved_channel_id = channel_id if channel_id is not None else 0
        return self.create_match(
            game_id=game.game_id,
            guild_id=guild_id,
            channel_id=resolved_channel_id,
            thread_id=thread_id,
            participants=participants,
            game_config=game_config or {},
            match_id=match_id,
            preset_match_code=preset_match_code,
        )


@dataclass(slots=True)
class ReplayRepository:
    database: Database

    def get_replay_events(self, match_id: int) -> list[dict[str, Any]]:
        rows = (
            self.database.execute_query(
                """
            SELECT sequence_number, event_type, actor_user_id, payload
            FROM replay_events
            WHERE match_id = %s
            ORDER BY sequence_number ASC;
            """,
                (match_id,),
                fetchall=True,
            )
            or []
        )
        events: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row.get("payload") or {})
            event_type = str(
                row.get("event_type") or payload.pop("event_type", "event"),
            )
            payload["type"] = event_type
            actor_user_id = row.get("actor_user_id")
            if actor_user_id is not None and "user_id" not in payload:
                payload["user_id"] = actor_user_id
            events.append(payload)
        return events

    def append_replay_event(self, match_id: int, event: dict[str, Any]) -> None:
        payload = dict(event or {})
        event_type = str(payload.pop("type", "event") or "event")
        actor_user_id = payload.pop("user_id", None)
        if actor_user_id is not None:
            try:
                actor_user_id = int(actor_user_id)
            except (TypeError, ValueError):
                actor_user_id = None
        replay_payload = dict(payload or {})
        with self.database.transaction() as cur:
            cur.execute(
                "SELECT 1 FROM matches WHERE match_id = %s FOR UPDATE;",
                (match_id,),
            )
            cur.execute(
                """
                SELECT COALESCE(MAX(sequence_number), 0) + 1 AS next_sequence_number
                FROM replay_events
                WHERE match_id = %s;
                """,
                (match_id,),
            )
            next_sequence_number = cur.fetchone()["next_sequence_number"]
            cur.execute(
                """
                INSERT INTO replay_events (
                    match_id, sequence_number, event_type, actor_user_id, payload
                )
                VALUES (%s, %s, %s, %s, %s::jsonb);
                """,
                (
                    match_id,
                    next_sequence_number,
                    event_type,
                    actor_user_id,
                    json.dumps(replay_payload),
                ),
            )

    def get_events(self, match_id: int) -> list[dict[str, Any]]:
        return self.get_replay_events(match_id)

    def append_event(
        self,
        match_id: int,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        event: dict[str, Any] = {"type": event_type, **(payload or {})}
        self.append_replay_event(match_id, event)

    def append_replay_dict(self, match_id: int, event: dict[str, Any]) -> None:
        self.append_replay_event(match_id, event)
