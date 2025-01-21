import trueskill
import mysql.connector
from mysql.connector import Error
from mysql.connector.pooling import PooledMySQLConnection

import configuration.constants
from configuration.constants import *
from configuration.constants import LOGGING_ROOT, GAME_TYPES, GAME_TRUESKILL, MU
from api.Player import Player
import logging

# Database logger
logger = logging.getLogger(f"{LOGGING_ROOT}.database")


connections_made = 1  # Keep track of how many connections were made

def create_connection() -> PooledMySQLConnection | None:
    """
    Create a connection to the database.
    :return: MySQL connection if success, None otherwise.
    """
    config = configuration.constants.CONFIGURATION  # Force a recopy of the configuration in case of changes.
    global connections_made
    log = logger.getChild("connect")
    log.debug(f"Establishing connection #{connections_made} to database")
    connections_made += 1  # Update connection attempt counter

    # Attempt a connection
    try:
        connection = mysql.connector.connect(
            host=config["db"]["domain"],  # Change if necessary
            user=config["db"]["user"],
            password=config["db"]["password"],
            port=config["db"]["port"],
        )
        return connection
    except Error as e:  # Something went wrong.
        log.critical(f"Error connecting to database: {e}")
        return None


def startup() -> bool:
    """
    Ensure the required database tables exist on startup.
    :return: True if success, False otherwise (database connection failure).
    """
    db = create_connection()  # Get the connection
    if db is None:
        return False  # Return False if failure to start up
    cursor = db.cursor()
    for game_type in GAME_TYPES.keys():
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {game_type}") # Make sure all databases exist
        cursor.execute(f"USE {game_type}")

        # Create the leaderboard table within the game's database
        cursor.execute("""CREATE TABLE IF NOT EXISTS leaderboard (  
                          id BIGINT UNSIGNED PRIMARY KEY,
                          mu DECIMAL(10,4) NOT NULL,
                          sigma DECIMAL(10,4) NOT NULL,
                          ranking BIGINT UNSIGNED DEFAULT null,
                          INDEX skill (mu DESC, sigma));
                       """)

    cursor.close()  # Close the connection
    db.close()
    return True


def get_player(game_type: str, user: discord.User) -> Player | None:
    """
    Get a utils.Player object from the database.
    :param game_type: The game_type the Player is playing
    :param user: the discord.User object to base the player off
    :return: the Player or None if failed (database connection error)
    """
    db = create_connection()  # Get the connection
    if db is None:
        return None  # Return none if failure to connect

    cursor = db.cursor()
    cursor.execute(f"USE {game_type}")  # Select database
    cursor.execute(f"SELECT * FROM leaderboard WHERE id={user.id}")  # Get id entries

    results = cursor.fetchall()  # Get the results of the query

    if not len(results):  # Player is not in DB, return default values of mu and sigma
        id, mu, sigma, ranking = user.id, MU, GAME_TRUESKILL[game_type]["sigma"] * MU, None
    else:
        id, mu, sigma, ranking = results[0]
        # Database has info, return that
        # Idk why, but we get a decimal.Decimal (infinite precision?)
        mu = float(mu)
        sigma = float(sigma)

    player = Player(mu, sigma, user, ranking)  # Create player object from data
    # Close connection
    cursor.close()
    db.close()

    return player  # Return the created object

def delete_player(player: Player) -> bool:
    """
    Delete a player from the database.
    :param player: The Player object to delete from the database
    :return: True if success, False otherwise (database connection failure).
    """
    db = create_connection()
    if db is None:
        return False  # Return false if failure to connect because the action failed

    cursor = db.cursor()
    for game_type in GAME_TYPES.keys():
        cursor.execute(f"USE {game_type}")  # Select database
        cursor.execute(f"DELETE FROM leaderboard WHERE id={player.id}")  # Delete entries by id

    db.commit()  # Force the changes
    # Close connection
    cursor.close()
    db.close()
    return True


def update_player(game_type: str, player: Player) -> bool:
    """
    Update a player's mu/sigma values in the database.
    :param game_type: the game_type the Player is playing
    :param player: the Player object to use when updating the database
    :return: True if success, False otherwise (database connection failure).
    """
    db = create_connection()
    if db is None:
        return False  # Return false if failure to connect, because the action failed

    cursor = db.cursor()
    cursor.execute(f"USE {game_type}")  # Select database
    cursor.execute(f"INSERT INTO leaderboard (id, mu, sigma)"
                   f"VALUES ({player.id}, {player.mu}, {player.sigma})"
                   f"ON DUPLICATE KEY UPDATE mu = {player.mu}, sigma = {player.sigma};")  # update on id entries

    # Close connection
    db.commit()
    cursor.close()
    db.close()
    return True


def update_rankings(game_type: str, teams: list[list[Player]]) -> bool:
    """
    Update the ELO of the players in the database after a rated match has finished.
    :param teams: an ordered list of the rankings of the teams (TrueSkill format)
    :param game_type: the game type being playing
    :return: True if success, False otherwise (database connection failure).

    TODO: finish, use ID from Player objects
    """
    game_type_data = GAME_TRUESKILL[game_type]  # TrueSkill environment constants for this game

    # The variables for the specific game type
    sigma, beta, tau, draw_probability = (game_type_data["sigma"],
                                          game_type_data["beta"],
                                          game_type_data["tau"],
                                          game_type_data["draw"])

    environment = trueskill.TrueSkill(MU, sigma, beta, tau, draw_probability)  # Create game environment

    # Convert Player to TrueSkill.Rating
    outcome = []
    for team in teams:
        team_ratings = []
        for player in team:
            team_ratings.append(environment.create_rating(player.mu, player.sigma))
        outcome.append(team_ratings)


    updated_rating_groups = environment.rate(outcome)  # Rerate the players based on outcome

    # Update the Player objects and send that data to update_player to propagate to the DB
    for team_index, team in enumerate(updated_rating_groups):
        for player_index, player in enumerate(team):
            teams[team_index][player_index].mu = player.mu
            teams[team_index][player_index].sigma = player.sigma
            update_player(game_type, teams[team_index][player_index].id, player.mu, player.sigma)

            
def update_db_rankings(game_type):
    db = create_connection()
    if db is None:
        return False  # Return false if failure to connect, because the action failed

    cursor = db.cursor()
    cursor.execute(f"USE {game_type}")  # Select database
    cursor.execute("""CREATE TEMPORARY TABLE temp_leaderboard_ranking AS
    SELECT id, FIND_IN_SET(mu, (
        SELECT GROUP_CONCAT(sub.mu ORDER BY sub.mu DESC, sub.sigma)
        FROM leaderboard AS sub
    )) AS ranking
    FROM leaderboard;
    """)
    cursor.execute("""UPDATE leaderboard AS ldr
    JOIN temp_leaderboard_ranking AS temp
    ON ldr.id = temp.id
    SET ldr.ranking = temp.ranking;
    """)
    cursor.execute("DROP TEMPORARY TABLE temp_leaderboard_ranking;")
    # Close connection
    db.commit()
    cursor.close()
    db.close()
    return True


