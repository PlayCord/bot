import json

import mysql.connector

# Database connection parameters
db_config = {
    'user': 'root',
    'password': 'password',
    'host': 'localhost',
    'database': 'grok_test'
}

try:
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()
except mysql.connector.Error as err:
    print(f"Error connecting to MySQL: {err}")
    exit(1)


# --- User and Server Management ---

def get_user_id(discord_id):
    """Check if a user exists by Discord ID; create if not."""
    discord_id_str = str(discord_id)
    cursor.execute("SELECT user_id FROM users WHERE user_id = %s", (discord_id_str,))
    result = cursor.fetchone()
    if result:
        return result[0]
    else:
        cursor.execute(
            "INSERT INTO users (user_id, ratings, metadata, servers) VALUES (%s, %s, %s, %s)",
            (discord_id_str, json.dumps({}), json.dumps({"total_matches_played": 0}), json.dumps([]))
        )
        conn.commit()
        return discord_id_str


def get_server_id(server_id):
    """Check if a server exists by server_id; create if not."""
    server_id_str = str(server_id)
    cursor.execute("SELECT server_id FROM servers WHERE server_id = %s", (server_id_str,))
    result = cursor.fetchone()
    if result:
        return result[0]
    else:
        cursor.execute(
            "INSERT INTO servers (server_id, metadata) VALUES (%s, %s)",
            (server_id_str, json.dumps({}))
        )
        conn.commit()
        return server_id_str


def link_user_to_server(user_id, server_id):
    """Add a server_id to a user's servers list."""
    user_id_str = str(user_id)
    server_id_str = str(server_id)
    cursor.execute("SELECT servers FROM users WHERE user_id = %s", (user_id_str,))
    result = cursor.fetchone()
    servers = json.loads(result[0]) if result and result[0] else []
    if server_id_str not in servers:
        servers.append(server_id_str)
        cursor.execute("UPDATE users SET servers = %s WHERE user_id = %s",
                       (json.dumps(servers), user_id_str))
        conn.commit()


def get_users_in_server(server_id):
    """Dynamically generate a list of user_ids in a server."""
    server_id_str = str(server_id)
    query = """
        SELECT user_id
        FROM users
        WHERE JSON_CONTAINS(servers, %s)
    """
    server_id_json = json.dumps(server_id_str)
    cursor.execute(query, (server_id_json,))
    rows = cursor.fetchall()
    return [row[0] for row in rows]


# --- Metadata Management (Users) ---

def get_user_metadata(user_id):
    """Retrieve a user's metadata."""
    user_id_str = str(user_id)
    cursor.execute("SELECT metadata FROM users WHERE user_id = %s", (user_id_str,))
    result = cursor.fetchone()
    return json.loads(result[0]) if result and result[0] else {"total_matches_played": 0}


def update_user_metadata(user_id, metadata):
    """Update a user's metadata."""
    user_id_str = str(user_id)
    cursor.execute("UPDATE users SET metadata = %s WHERE user_id = %s",
                   (json.dumps(metadata), user_id_str))
    conn.commit()


def get_total_matches_played(user_id):
    """Get the total matches played across all game modes."""
    metadata = get_user_metadata(user_id)
    return metadata.get("total_matches_played", 0)


def increment_total_matches_played(user_id, increment=1):
    """Increment the total matches played in metadata."""
    metadata = get_user_metadata(user_id)
    metadata["total_matches_played"] = metadata.get("total_matches_played", 0) + increment
    update_user_metadata(user_id, metadata)


# --- Metadata Management (Servers) ---

def get_server_metadata(server_id):
    """Retrieve a server's metadata."""
    server_id_str = str(server_id)
    cursor.execute("SELECT metadata FROM servers WHERE server_id = %s", (server_id_str,))
    result = cursor.fetchone()
    return json.loads(result[0]) if result and result[0] else {}


def update_server_metadata(server_id, metadata):
    """Update a server's metadata."""
    server_id_str = str(server_id)
    cursor.execute("UPDATE servers SET metadata = %s WHERE server_id = %s",
                   (json.dumps(metadata), server_id_str))
    conn.commit()


# --- User Ratings Management ---

def get_user_gamemode_stats(user_id, gamemode_id):
    """Get a user's TrueSkill mu, sigma, and matches_played for a game mode from ratings."""
    user_id_str = str(user_id)
    gamemode_id_str = str(gamemode_id)
    cursor.execute("SELECT ratings FROM users WHERE user_id = %s", (user_id_str,))
    result = cursor.fetchone()
    if result and result[0]:
        ratings = json.loads(result[0])
        if gamemode_id_str in ratings:
            return (ratings[gamemode_id_str]["mu"],
                    ratings[gamemode_id_str]["sigma"],
                    ratings[gamemode_id_str]["matches_played"])
    return (25.0, 8.333, 0)


def update_user_gamemode_stats(user_id, gamemode_id, mu, sigma, matches_played):
    """Update a user's ratings (including matches_played) for a game mode with string keys."""
    user_id_str = str(user_id)
    gamemode_id_str = str(gamemode_id)
    cursor.execute("SELECT ratings FROM users WHERE user_id = %s", (user_id_str,))
    result = cursor.fetchone()
    ratings = json.loads(result[0]) if result and result[0] else {}
    ratings[gamemode_id_str] = {"mu": mu, "sigma": sigma, "matches_played": matches_played}
    cursor.execute("UPDATE users SET ratings = %s WHERE user_id = %s", (json.dumps(ratings), user_id_str))
    conn.commit()


# --- Game Mode Management ---

def add_gamemode(gamemode_name):
    """Add a game mode if it doesn't exist."""
    cursor.execute("INSERT INTO gamemodes (name) VALUES (%s) ON DUPLICATE KEY UPDATE name = name",
                   (gamemode_name,))
    conn.commit()
    cursor.execute("SELECT gamemode_id FROM gamemodes WHERE name = %s", (gamemode_name,))
    result = cursor.fetchone()
    return result[0] if result else None


def get_or_create_gamemode(gamemode_name):
    """Get or create a gamemode ID."""
    cursor.execute("SELECT gamemode_id FROM gamemodes WHERE name = %s", (gamemode_name,))
    result = cursor.fetchone()
    if result:
        return str(result[0])
    else:
        return str(add_gamemode(gamemode_name))


# --- Game Operations ---

def create_game(game_id, participants, game_type, version=1):
    """Create a new game with participants and game type; raise error if game exists."""
    game_id_str = str(game_id)
    gamemode_id = get_or_create_gamemode(game_type)
    if not gamemode_id:
        raise ValueError(f"Failed to get or create gamemode '{game_type}'")

    # Check if game already exists
    cursor.execute("SELECT game_id FROM games WHERE game_id = %s", (game_id_str,))
    if cursor.fetchone():
        raise ValueError(f"Game with ID {game_id_str} already exists in the database")

    # Initialize participants JSON with string user_id keys
    participants_data = {}
    for user_id in participants:
        user_id_str = str(user_id)
        mu, sigma, matches_played = get_user_gamemode_stats(user_id_str, gamemode_id)
        participants_data[user_id_str] = {
            "old_mu": mu,
            "old_sigma": sigma,
            "new_mu": mu,
            "new_sigma": sigma,
            "rating_diff": 0.0
        }
    print(f"Creating game with participants: {participants_data}")

    cursor.execute("""
        INSERT INTO games (game_id, gamemode_id, version, participants) 
        VALUES (%s, %s, %s, %s)
    """, (game_id_str, gamemode_id, version, json.dumps(participants_data)))
    conn.commit()
    return game_id_str


def end_game(game_id, moves, result):
    """End a game: store moves, update ratings and matches_played, and save result with old_mu/old_sigma."""
    game_id_str = str(game_id)
    print(f"Starting end_game with result: {result}")

    # Fetch current participants and gamemode_id
    cursor.execute("SELECT participants, gamemode_id, result FROM games WHERE game_id = %s", (game_id_str,))
    result_fetch = cursor.fetchone()
    if not result_fetch:
        raise ValueError(f"Game ID {game_id_str} not found")
    participants = json.loads(result_fetch[0]) if result_fetch[0] else {}
    gamemode_id = result_fetch[1]
    current_result = json.loads(result_fetch[2]) if result_fetch[2] else {}
    print(f"Fetched participants: {participants}")
    print(f"Gamemode ID: {gamemode_id}")

    # Store moves in bulk with INSERT IGNORE to prevent duplicates
    if moves:
        move_values = [
            (game_id_str, str(move.get("user_id")) if move.get("user_id") is not None else None,
             move["turn_number"], move.get("version", 1), json.dumps(move["metadata"]))
            for move in moves
        ]
        cursor.executemany("""
            INSERT IGNORE INTO moves (game_id, user_id, turn_number, version, metadata)
            VALUES (%s, %s, %s, %s, %s)
        """, move_values)
        conn.commit()

    # Update ratings and matches_played based on result, adding old_mu and old_sigma
    if result and "ratings" in result and "rankings" in result:
        print("Entering ratings update block")
        updated_ratings = {}
        for user_id, ratings in result["ratings"].items():
            user_id_str = str(user_id)
            print(f"Processing user {user_id_str} with ratings: {ratings}")
            if user_id_str in participants:
                old_mu = participants[user_id_str]["old_mu"]
                old_sigma = participants[user_id_str]["old_sigma"]
                new_mu = ratings.get("new_mu", old_mu)
                new_sigma = ratings.get("new_sigma", old_sigma)
                participants[user_id_str].update({
                    "new_mu": new_mu,
                    "new_sigma": new_sigma,
                    "rating_diff": new_mu - old_mu
                })
                updated_ratings[user_id_str] = {
                    "old_mu": old_mu,
                    "old_sigma": old_sigma,
                    "new_mu": new_mu,
                    "new_sigma": new_sigma
                }
                # Update user's ratings with incremented matches_played
                current_mu, current_sigma, matches_played = get_user_gamemode_stats(user_id_str, gamemode_id)
                print(
                    f"Before update - User {user_id_str}: mu={current_mu}, sigma={current_sigma}, matches_played={matches_played}")
                update_user_gamemode_stats(user_id_str, gamemode_id, new_mu, new_sigma, matches_played + 1)
                cursor.execute("SELECT ratings FROM users WHERE user_id = %s", (user_id_str,))
                updated_ratings_raw = cursor.fetchone()[0]
                print(f"After update - User {user_id_str} ratings: {json.loads(updated_ratings_raw)}")
                # Increment total matches_played in metadata
                increment_total_matches_played(user_id_str)
                cursor.execute("SELECT metadata FROM users WHERE user_id = %s", (user_id_str,))
                updated_metadata_raw = cursor.fetchone()[0]
                print(f"After metadata update - User {user_id_str} metadata: {json.loads(updated_metadata_raw)}")
            else:
                print(f"User {user_id_str} not found in participants")
        result["ratings"] = updated_ratings
        conn.commit()
    else:
        print("Ratings update block skipped: result or required keys missing")

    # Update game with participants, result (including old_mu/old_sigma), and end_time
    print(f"Updating games table with result: {result}")
    cursor.execute("""
        UPDATE games 
        SET participants = %s, 
            result = %s, 
            end_time = NOW() 
        WHERE game_id = %s
    """, (json.dumps(participants), json.dumps(result), game_id_str))
    conn.commit()

    # Verify the result was saved
    cursor.execute("SELECT result FROM games WHERE game_id = %s", (game_id_str,))
    saved_result = cursor.fetchone()
    if saved_result and saved_result[0]:
        print(f"Result saved for game {game_id_str}: {json.loads(saved_result[0])}")
    else:
        print(f"Warning: No result saved for game {game_id_str}")


# --- Leaderboard Retrieval ---

def get_rankings(game_id, server_id=None, local=False, offset=0, count=25):
    """Retrieve rankings based on game_id with optional local server filtering."""
    game_id_str = str(game_id)
    server_id_str = str(server_id) if server_id is not None else None
    cursor.execute("SELECT gamemode_id FROM games WHERE game_id = %s", (game_id_str,))
    result = cursor.fetchone()
    if not result:
        raise ValueError(f"Game ID {game_id_str} not found")
    gamemode_id = str(result[0])

    if local:
        if server_id is None:
            raise ValueError("server_id is required when local=True")
        query = """
            SELECT 
                u.user_id AS discord_id,
                JSON_EXTRACT(u.ratings, %s) AS mu,
                JSON_EXTRACT(u.ratings, %s) AS sigma
            FROM users u
            WHERE JSON_CONTAINS(servers, %s)
              AND JSON_EXTRACT(u.ratings, %s) IS NOT NULL
            ORDER BY 
                JSON_EXTRACT(u.ratings, %s) DESC,
                JSON_EXTRACT(u.ratings, %s) ASC
            LIMIT %s, %s
        """
        mu_path = f'$."{gamemode_id}".mu'
        sigma_path = f'$."{gamemode_id}".sigma'
        ratings_path = f'$."{gamemode_id}"'
        server_id_json = json.dumps(server_id_str)
        cursor.execute(query, (mu_path, sigma_path, server_id_json, ratings_path, mu_path, sigma_path, offset, count))
    else:
        query = """
            SELECT 
                u.user_id AS discord_id,
                JSON_EXTRACT(u.ratings, %s) AS mu,
                JSON_EXTRACT(u.ratings, %s) AS sigma
            FROM users u
            WHERE JSON_EXTRACT(u.ratings, %s) IS NOT NULL
            ORDER BY 
                JSON_EXTRACT(u.ratings, %s) DESC,
                JSON_EXTRACT(u.ratings, %s) ASC
            LIMIT %s, %s
        """
        mu_path = f'$."{gamemode_id}".mu'
        sigma_path = f'$."{gamemode_id}".sigma'
        ratings_path = f'$."{gamemode_id}"'
        cursor.execute(query, (mu_path, sigma_path, ratings_path, mu_path, sigma_path, offset, count))

    rows = cursor.fetchall()
    return [(row[0], float(row[1]), float(row[2])) for row in rows] if rows else []


# --- Game Replays and History ---

def get_user_last_games(user_id, limit=25):
    """Retrieve the last N games for a user, including version and JSON result."""
    user_id_str = str(user_id)
    query = """
        SELECT 
            g.game_id, 
            g.gamemode_id, 
            g.version,
            g.start_time, 
            g.end_time, 
            g.result,
            g.participants
        FROM games g
        WHERE JSON_CONTAINS_PATH(g.participants, "one", %s)
        ORDER BY g.end_time DESC
        LIMIT %s
    """
    user_id_json = f"$.\"{user_id_str}\""
    cursor.execute(query, (user_id_json, limit))
    rows = cursor.fetchall()
    print([r for r in rows])
    return [(r[0], r[1], r[2], r[3], r[4], json.loads(r[5]) if r[5] else None, json.loads(r[6]) if r[6] else {}) for r
            in rows]


def get_game_moves(game_id):
    """Retrieve all moves and events for a specific game, with nullable user_id."""
    game_id_str = str(game_id)
    cursor.execute("""
        SELECT 
            m.turn_number,
            m.version,
            m.metadata,
            m.user_id AS move_by
        FROM moves AS m
        WHERE m.game_id = %s
        ORDER BY m.turn_number ASC
    """, (game_id_str,))
    return cursor.fetchall()


def get_game_participants(game_id):
    """Retrieve participant details and rating changes from games.participants."""
    game_id_str = str(game_id)
    cursor.execute("SELECT participants FROM games WHERE game_id = %s", (game_id_str,))
    result = cursor.fetchone()
    if result and result[0]:
        participants = json.loads(result[0])
        return [(user_id, participants[user_id]) for user_id in participants]
    return []


# --- Test the Changes ---

if __name__ == "__main__":
    # Setup test data
    user1 = get_user_id(123456789012345670)
    user2 = get_user_id(123456789012345671)
    server_id = get_server_id(987654321)
    link_user_to_server(user1, server_id)
    link_user_to_server(user2, server_id)

    # Add some server metadata
    update_server_metadata(server_id, {"prefix": "!", "welcome_channel": "123456789"})

    # Create a game (will raise ValueError if run again with same game_id)
    game_id = 1000000001
    participants = [user1, user2]
    try:
        create_game(game_id, participants, "tic_tac_toe")
    except ValueError as e:
        print(f"Error: {e}")

    # Simulate game play and end it
    moves = [
        {"user_id": user1, "turn_number": 1, "metadata": {"board": "X  /   /   ", "played": [0, 0]}},
        {"user_id": user2, "turn_number": 2, "metadata": {"board": "X  / O /   ", "played": [1, 0]}},
        {"user_id": user1, "turn_number": 3, "metadata": {"board": "X  / O / X ", "played": [2, 0]}},
        {"user_id": None, "turn_number": 4, "metadata": {"event": "Game ends early"}}
    ]
    result = {
        "reason": "Player conceded",
        "rankings": [[user1], [user2]],  # user1 in 1st, user2 in 2nd
        "ratings": {
            user1: {"new_mu": 28.0, "new_sigma": 7.5},
            user2: {"new_mu": 23.0, "new_sigma": 8.5}
        }
    }
    end_game(game_id, moves, result)

    # Test outputs
    print("Game Participants:")
    participants = get_game_participants(game_id)
    for user_id, data in participants:
        print(f"User {user_id}: {data}")

    print("\nMoves:")
    moves = get_game_moves(game_id)
    for turn_number, version, metadata, user_id in moves:
        print(f"Turn {turn_number}: User {user_id}, Metadata {json.loads(metadata)}")

    print("\nGlobal Rankings:")
    rankings = get_rankings(game_id, local=False)
    for rank, (discord_id, mu, sigma) in enumerate(rankings, 1):
        print(f"Rank {rank}: User {discord_id}, mu={mu}, sigma={sigma}")

    print(f"\nLocal Server Rankings (server_id={server_id}):")
    rankings = get_rankings(game_id, server_id=server_id, local=True)
    for rank, (discord_id, mu, sigma) in enumerate(rankings, 1):
        print(f"Rank {rank}: User {discord_id}, mu={mu}, sigma={sigma}")

    print("\nUsers in Server:")
    users_in_server = get_users_in_server(server_id)
    print(f"Server {server_id} Users: {users_in_server}")

    print("\nUser Data:")
    for user_id in [user1, user2]:
        cursor.execute("SELECT ratings, metadata, servers FROM users WHERE user_id = %s", (user_id,))
        ratings, metadata, servers = cursor.fetchone()
        print(
            f"User {user_id}: Ratings={json.loads(ratings)}, Metadata={json.loads(metadata)}, Servers={json.loads(servers)}")

    print("\nServer Metadata:")
    server_metadata = get_server_metadata(server_id)
    print(f"Server {server_id}: {server_metadata}")

    print("\nLast Games for User 1:")
    last_games = get_user_last_games(user1)
    for game in last_games:
        print(f"Game {game[0]}: {game}")

    # Fetch and print the game result to verify
    cursor.execute("SELECT result FROM games WHERE game_id = %s", (game_id,))
    game_result = cursor.fetchone()
    print(f"\nGame Result for {game_id}: {json.loads(game_result[0]) if game_result and game_result[0] else 'None'}")
