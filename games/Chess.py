"""
Chess for PlayCord.

A standard chess implementation for 2 players with full move validation.
"""

import html
from enum import Enum
from typing import Any, Optional

try:
    import cairosvg
except ImportError:
    cairosvg = None

from api.Arguments import String
from api.Command import Command
from api.Game import Game
from api.MessageComponents import Button, ButtonStyle, CodeBlock, Description, Image, MessageComponent
from api.Player import Player
from api.Response import Response


def _svg_to_png(svg_markup: str) -> bytes | None:
    if cairosvg is None:
        return None
    return cairosvg.svg2png(bytestring=svg_markup.encode("utf-8"))


def render_chess_board_png(board: list[list[Any | None]]) -> bytes | None:
    square = 74
    margin = 28
    board_size = square * 8
    width = board_size + (margin * 2)
    height = board_size + (margin * 2)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#0f172a"/>',
    ]

    light = "#f0d9b5"
    dark = "#b58863"

    for display_row in range(8):
        board_row = 7 - display_row
        for col in range(8):
            x = margin + (col * square)
            y = margin + (display_row * square)
            color = dark if (board_row + col) % 2 == 0 else light
            parts.append(
                f'<rect x="{x}" y="{y}" width="{square}" height="{square}" fill="{color}"/>'
            )

            piece = board[board_row][col]
            if piece is None:
                continue

            piece_symbol = html.escape(getattr(piece, "symbol", ""))
            piece_color = getattr(getattr(piece, "color", None), "value", "")
            is_white = piece_color == "white"
            fill = "#f8fafc" if is_white else "#111827"
            stroke = "#111827" if is_white else "#f8fafc"
            parts.append(
                f'<text x="{x + (square / 2)}" y="{y + (square / 2)}" text-anchor="middle" '
                f'dominant-baseline="central" font-size="48" font-family="DejaVu Sans, serif" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="1">{piece_symbol}</text>'
            )

    files = "abcdefgh"
    for index, file_name in enumerate(files):
        x = margin + (index * square) + (square / 2)
        parts.append(
            f'<text x="{x}" y="{margin - 10}" text-anchor="middle" '
            f'font-size="14" fill="#e2e8f0">{file_name}</text>'
        )
        parts.append(
            f'<text x="{x}" y="{height - 8}" text-anchor="middle" '
            f'font-size="14" fill="#e2e8f0">{file_name}</text>'
        )

    for display_row in range(8):
        rank = 8 - display_row
        y = margin + (display_row * square) + (square / 2) + 5
        parts.append(
            f'<text x="{margin - 12}" y="{y}" text-anchor="middle" '
            f'font-size="14" fill="#e2e8f0">{rank}</text>'
        )
        parts.append(
            f'<text x="{width - (margin - 12)}" y="{y}" text-anchor="middle" '
            f'font-size="14" fill="#e2e8f0">{rank}</text>'
        )

    parts.append("</svg>")
    return _svg_to_png("".join(parts))


class PieceType(Enum):
    """Chess piece types."""
    PAWN = 'P'
    KNIGHT = 'N'
    BISHOP = 'B'
    ROOK = 'R'
    QUEEN = 'Q'
    KING = 'K'


class Color(Enum):
    """Player colors."""
    WHITE = 'white'
    BLACK = 'black'


class Piece:
    """Represents a chess piece."""

    SYMBOLS = {
        (PieceType.KING, Color.WHITE): '\u2654',
        (PieceType.QUEEN, Color.WHITE): '\u2655',
        (PieceType.ROOK, Color.WHITE): '\u2656',
        (PieceType.BISHOP, Color.WHITE): '\u2657',
        (PieceType.KNIGHT, Color.WHITE): '\u2658',
        (PieceType.PAWN, Color.WHITE): '\u2659',
        (PieceType.KING, Color.BLACK): '\u265a',
        (PieceType.QUEEN, Color.BLACK): '\u265b',
        (PieceType.ROOK, Color.BLACK): '\u265c',
        (PieceType.BISHOP, Color.BLACK): '\u265d',
        (PieceType.KNIGHT, Color.BLACK): '\u265e',
        (PieceType.PAWN, Color.BLACK): '\u265f',
    }

    def __init__(self, piece_type: PieceType, color: Color):
        self.piece_type = piece_type
        self.color = color
        self.has_moved = False

    @property
    def symbol(self) -> str:
        return self.SYMBOLS[(self.piece_type, self.color)]

    def __str__(self) -> str:
        return self.symbol


class ChessBoard:
    """Represents the chess board and handles move validation."""

    def __init__(self):
        self.board: list[list[Optional[Piece]]] = [[None] * 8 for _ in range(8)]
        self.en_passant_target: Optional[tuple[int, int]] = None
        self._setup_pieces()

    def _setup_pieces(self):
        """Set up the initial board position."""
        back_row = [PieceType.ROOK, PieceType.KNIGHT, PieceType.BISHOP, PieceType.QUEEN,
                    PieceType.KING, PieceType.BISHOP, PieceType.KNIGHT, PieceType.ROOK]

        for col, piece_type in enumerate(back_row):
            self.board[0][col] = Piece(piece_type, Color.WHITE)
            self.board[7][col] = Piece(piece_type, Color.BLACK)

        for col in range(8):
            self.board[1][col] = Piece(PieceType.PAWN, Color.WHITE)
            self.board[6][col] = Piece(PieceType.PAWN, Color.BLACK)

    def get_piece(self, row: int, col: int) -> Optional[Piece]:
        """Get piece at position."""
        if 0 <= row < 8 and 0 <= col < 8:
            return self.board[row][col]
        return None

    def set_piece(self, row: int, col: int, piece: Optional[Piece]):
        """Set piece at position."""
        self.board[row][col] = piece

    def move_piece(self, from_row: int, from_col: int, to_row: int, to_col: int) -> Optional[Piece]:
        """Move piece and return captured piece if any."""
        piece = self.board[from_row][from_col]
        captured = self.board[to_row][to_col]

        self.board[to_row][to_col] = piece
        self.board[from_row][from_col] = None

        if piece:
            piece.has_moved = True

        return captured

    def is_valid_move(self, from_row: int, from_col: int, to_row: int, to_col: int,
                      color: Color) -> tuple[bool, str]:
        """Check if a move is valid. Returns (valid, error_message)."""
        piece = self.get_piece(from_row, from_col)

        if piece is None:
            return False, "No piece at that position"

        if piece.color != color:
            return False, "That's not your piece"

        target = self.get_piece(to_row, to_col)
        if target and target.color == color:
            return False, "Can't capture your own piece"

        if not self._is_valid_piece_move(piece, from_row, from_col, to_row, to_col):
            return False, f"Invalid move for {piece.piece_type.name.lower()}"

        if self._would_be_in_check(from_row, from_col, to_row, to_col, color):
            return False, "Move would leave your king in check"

        return True, ""

    def _is_valid_piece_move(self, piece: Piece, from_row: int, from_col: int,
                             to_row: int, to_col: int) -> bool:
        """Check if the move follows the piece's movement rules."""
        dr = to_row - from_row
        dc = to_col - from_col
        target = self.get_piece(to_row, to_col)

        if piece.piece_type == PieceType.PAWN:
            direction = 1 if piece.color == Color.WHITE else -1
            start_row = 1 if piece.color == Color.WHITE else 6

            if dc == 0 and target is None:
                if dr == direction:
                    return True
                if dr == 2 * direction and from_row == start_row:
                    return self.get_piece(from_row + direction, from_col) is None

            if abs(dc) == 1 and dr == direction:
                if target is not None:
                    return True
                if (to_row, to_col) == self.en_passant_target:
                    return True

            return False

        elif piece.piece_type == PieceType.KNIGHT:
            return (abs(dr), abs(dc)) in [(1, 2), (2, 1)]

        elif piece.piece_type == PieceType.BISHOP:
            return abs(dr) == abs(dc) and self._path_clear(from_row, from_col, to_row, to_col)

        elif piece.piece_type == PieceType.ROOK:
            return (dr == 0 or dc == 0) and self._path_clear(from_row, from_col, to_row, to_col)

        elif piece.piece_type == PieceType.QUEEN:
            return ((dr == 0 or dc == 0 or abs(dr) == abs(dc)) and
                    self._path_clear(from_row, from_col, to_row, to_col))

        elif piece.piece_type == PieceType.KING:
            if abs(dr) <= 1 and abs(dc) <= 1:
                return True
            if dr == 0 and abs(dc) == 2 and not piece.has_moved:
                return self._can_castle(from_row, from_col, to_col > from_col, piece.color)

        return False

    def _path_clear(self, from_row: int, from_col: int, to_row: int, to_col: int) -> bool:
        """Check if path between squares is clear."""
        dr = 0 if to_row == from_row else (1 if to_row > from_row else -1)
        dc = 0 if to_col == from_col else (1 if to_col > from_col else -1)

        row, col = from_row + dr, from_col + dc
        while (row, col) != (to_row, to_col):
            if self.board[row][col] is not None:
                return False
            row += dr
            col += dc

        return True

    def _can_castle(self, row: int, col: int, kingside: bool, color: Color) -> bool:
        """Check if castling is valid."""
        rook_col = 7 if kingside else 0
        rook = self.get_piece(row, rook_col)

        if rook is None or rook.piece_type != PieceType.ROOK or rook.has_moved:
            return False

        start_col = min(col, rook_col) + 1
        end_col = max(col, rook_col)
        for c in range(start_col, end_col):
            if self.board[row][c] is not None:
                return False

        direction = 1 if kingside else -1
        for c in [col, col + direction, col + 2 * direction]:
            if self._is_square_attacked(row, c, color):
                return False

        return True

    def _would_be_in_check(self, from_row: int, from_col: int,
                           to_row: int, to_col: int, color: Color) -> bool:
        """Check if a move would leave the king in check."""
        piece = self.board[from_row][from_col]
        captured = self.board[to_row][to_col]
        self.board[to_row][to_col] = piece
        self.board[from_row][from_col] = None

        in_check = self.is_in_check(color)

        self.board[from_row][from_col] = piece
        self.board[to_row][to_col] = captured

        return in_check

    def is_in_check(self, color: Color) -> bool:
        """Check if the given color's king is in check."""
        king_pos = self._find_king(color)
        if king_pos is None:
            return False
        return self._is_square_attacked(king_pos[0], king_pos[1], color)

    def _find_king(self, color: Color) -> Optional[tuple[int, int]]:
        """Find the king's position."""
        for row in range(8):
            for col in range(8):
                piece = self.board[row][col]
                if piece and piece.piece_type == PieceType.KING and piece.color == color:
                    return (row, col)
        return None

    def _is_square_attacked(self, row: int, col: int, by_color: Color) -> bool:
        """Check if a square is attacked by the opponent."""
        opponent = Color.BLACK if by_color == Color.WHITE else Color.WHITE

        for r in range(8):
            for c in range(8):
                piece = self.board[r][c]
                if piece and piece.color == opponent:
                    if self._is_valid_piece_move(piece, r, c, row, col):
                        return True
        return False

    def is_checkmate(self, color: Color) -> bool:
        """Check if the given color is in checkmate."""
        if not self.is_in_check(color):
            return False
        return not self._has_legal_moves(color)

    def is_stalemate(self, color: Color) -> bool:
        """Check if the given color is in stalemate."""
        if self.is_in_check(color):
            return False
        return not self._has_legal_moves(color)

    def _has_legal_moves(self, color: Color) -> bool:
        """Check if the color has any legal moves."""
        for from_row in range(8):
            for from_col in range(8):
                piece = self.board[from_row][from_col]
                if piece and piece.color == color:
                    for to_row in range(8):
                        for to_col in range(8):
                            valid, _ = self.is_valid_move(from_row, from_col,
                                                          to_row, to_col, color)
                            if valid:
                                return True
        return False

    def render(self) -> str:
        """Render the board as a string."""
        lines = []
        lines.append("  a b c d e f g h")
        lines.append(
            "  \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")

        for row in range(7, -1, -1):
            row_str = f"{row + 1}\u2502"
            for col in range(8):
                piece = self.board[row][col]
                if piece:
                    row_str += piece.symbol + " "
                else:
                    row_str += "\u00b7 " if (row + col) % 2 == 0 else "  "
            row_str += f"\u2502{row + 1}"
            lines.append(row_str)

        lines.append(
            "  \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
        lines.append("  a b c d e f g h")

        return "\n".join(lines)


class ChessGame(Game):
    """Chess implementation."""

    summary = "Play Chess!"
    move_command_group_description = "Commands for Chess"
    description = (
        "Classic Chess - the timeless strategy game. Checkmate your opponent's king to win!"
    )
    name = "Chess"
    players = [2]
    moves = [
        Command(name="move", description="Make a move (e.g., e2e4 or e2-e4).",
                callback="make_move",
                options=[String(argument_name="notation", description="Move in coordinate notation (e.g., e2e4)")]),
        Command(name="resign", description="Resign the game.",
                callback="resign", require_current_turn=False),
        Command(name="offer_draw", description="Offer a draw.",
                callback="offer_draw"),
    ]
    author = "@quantumbagel"
    version = "1.0"
    author_link = "https://github.com/quantumbagel"
    source_link = "https://github.com/PlayCord/bot/blob/main/games/Chess.py"
    time = "30min"
    difficulty = "Hard"

    def __init__(self, players: list[Player]) -> None:
        self.players = players
        self.board = ChessBoard()
        self.turn = 0
        self.finished = False
        self.winner: Optional[Player] = None
        self.draw = False
        self.draw_offered_by: Optional[Player] = None
        self.move_history: list[str] = []
        self.last_move: str = ""
        self.result_reason: str = ""

    @property
    def white(self) -> Player:
        return self.players[0]

    @property
    def black(self) -> Player:
        return self.players[1]

    @property
    def current_color(self) -> Color:
        return Color.WHITE if self.turn == 0 else Color.BLACK

    def state(self):
        """Return current game state."""
        if self.finished:
            if self.draw:
                status = "Draw! Game ended in a draw!"
            else:
                status = f"Checkmate! {self.winner.mention} wins by {self.result_reason}!"
        else:
            color_name = "White" if self.turn == 0 else "Black"
            check_warning = " - CHECK!" if self.board.is_in_check(self.current_color) else ""
            status = f"{color_name}'s turn: {self.current_turn().mention}{check_warning}"

        description_text = f"**{status}**\n\n"
        if self.last_move:
            description_text += f"Last move: {self.last_move}\n"
        description_text += f"\n{self.white.mention} plays White\n{self.black.mention} plays Black"

        components: list[MessageComponent] = [
            Description(description_text),
        ]

        board_png = render_chess_board_png(self.board.board)
        if board_png is not None:
            components.append(Image(board_png))
        else:
            components.append(CodeBlock(self.board.render(), language=""))

        if not self.finished:
            if self.draw_offered_by and self.draw_offered_by != self.current_turn():
                components.append(Button(label="Accept Draw", callback=self.accept_draw,
                                         row=0, style=ButtonStyle.green))
                components.append(Button(label="Decline Draw", callback=self.decline_draw,
                                         row=0, style=ButtonStyle.red))

        return components

    def current_turn(self) -> Player:
        """Return current player to move."""
        return self.players[self.turn]

    def _parse_notation(self, notation: str) -> Optional[tuple[int, int, int, int]]:
        """Parse coordinate notation like e2e4 or e2-e4."""
        notation = notation.lower().replace("-", "").replace(" ", "")

        if len(notation) != 4:
            return None

        try:
            from_col = ord(notation[0]) - ord('a')
            from_row = int(notation[1]) - 1
            to_col = ord(notation[2]) - ord('a')
            to_row = int(notation[3]) - 1

            if not all(0 <= x < 8 for x in [from_col, from_row, to_col, to_row]):
                return None

            return (from_row, from_col, to_row, to_col)
        except (ValueError, IndexError):
            return None

    def make_move(self, player: Player, notation: str):
        """Make a chess move."""
        if player != self.current_turn():
            return Response(content="It's not your turn!", ephemeral=True, delete_after=5)

        coords = self._parse_notation(notation)
        if coords is None:
            return Response(
                content="Invalid notation. Use coordinate notation like 'e2e4' or 'e2-e4'.",
                ephemeral=True, delete_after=5
            )

        from_row, from_col, to_row, to_col = coords

        valid, error = self.board.is_valid_move(from_row, from_col, to_row, to_col,
                                                self.current_color)
        if not valid:
            return Response(content=f"Invalid move: {error}", ephemeral=True, delete_after=5)

        piece = self.board.get_piece(from_row, from_col)

        # Handle castling
        if piece.piece_type == PieceType.KING and abs(to_col - from_col) == 2:
            kingside = to_col > from_col
            rook_from = 7 if kingside else 0
            rook_to = 5 if kingside else 3
            self.board.move_piece(from_row, rook_from, from_row, rook_to)
            move_str = "O-O" if kingside else "O-O-O"
        else:
            move_str = notation.lower()

        # Handle en passant capture
        if piece.piece_type == PieceType.PAWN:
            if (to_row, to_col) == self.board.en_passant_target:
                capture_row = from_row
                self.board.set_piece(capture_row, to_col, None)

            if abs(to_row - from_row) == 2:
                self.board.en_passant_target = ((from_row + to_row) // 2, from_col)
            else:
                self.board.en_passant_target = None
        else:
            self.board.en_passant_target = None

        self.board.move_piece(from_row, from_col, to_row, to_col)

        # Handle pawn promotion
        if piece.piece_type == PieceType.PAWN:
            if (piece.color == Color.WHITE and to_row == 7) or \
                    (piece.color == Color.BLACK and to_row == 0):
                self.board.set_piece(to_row, to_col, Piece(PieceType.QUEEN, piece.color))
                move_str += "=Q"

        self.last_move = move_str
        self.move_history.append(move_str)
        self.draw_offered_by = None

        self.turn = 1 - self.turn

        opponent_color = self.current_color
        if self.board.is_checkmate(opponent_color):
            self.finished = True
            self.winner = self.players[1 - self.turn]
            self.result_reason = "checkmate"
        elif self.board.is_stalemate(opponent_color):
            self.finished = True
            self.draw = True
            self.result_reason = "stalemate"

        return None

    def resign(self, player: Player):
        """Resign the game."""
        self.finished = True
        self.winner = self.white if player == self.black else self.black
        self.result_reason = "resignation"
        self.last_move = f"{player.mention} resigned"
        return None

    def offer_draw(self, player: Player):
        """Offer a draw to the opponent."""
        if self.draw_offered_by == player:
            return Response(content="You already offered a draw.", ephemeral=True, delete_after=5)

        self.draw_offered_by = player
        return Response(content=f"{player.mention} offers a draw!")

    def accept_draw(self, player: Player):
        """Accept a draw offer."""
        if self.draw_offered_by is None:
            return Response(content="No draw offer to accept.", ephemeral=True, delete_after=5)

        if self.draw_offered_by == player:
            return Response(content="You can't accept your own draw offer.",
                            ephemeral=True, delete_after=5)

        self.finished = True
        self.draw = True
        self.result_reason = "agreement"
        self.last_move = "Draw agreed"
        return None

    def decline_draw(self, player: Player):
        """Decline a draw offer."""
        if self.draw_offered_by is None:
            return Response(content="No draw offer to decline.", ephemeral=True, delete_after=5)

        if self.draw_offered_by == player:
            return Response(content="You can't decline your own draw offer.",
                            ephemeral=True, delete_after=5)

        self.draw_offered_by = None
        return Response(content=f"{player.mention} declines the draw offer.")

    def outcome(self):
        """Return game outcome."""
        if not self.finished:
            return None

        if self.draw:
            return [[self.white, self.black]]

        loser = self.black if self.winner == self.white else self.white
        return [[self.winner], [loser]]
