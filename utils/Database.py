import discord
import trueskill
import mysql.connector
from mysql.connector import Error
from ruamel.yaml import YAML

from configuration.constants import LOGGING_ROOT, CONFIGURATION, GAME_TYPES
from utils.Player import Player
import logging
fake_data = {"tic_tac_toe": {1085939954758205561: 1000, 897146430664355850: 1200}}
def load_configuration():
    """
    Load configuration from constants.CONFIG_FILE
    :return:
    """
    try:
        loaded_config_file = YAML().load(open("../configuration/config.yaml"))
    except FileNotFoundError:
        return None
    return loaded_config_file

config = load_configuration()
logger = logging.getLogger(f"{LOGGING_ROOT}.database")
connections_made = 1
def create_connection():
    global config
    global connections_made
    log = logger.getChild("connect")
    log.debug(f"Establishing connection #{connections_made} to database")
    connections_made += 1
    try:
        connection = mysql.connector.connect(
            host=config["db"]["domain"],  # Change if necessary
            user=config["db"]["user"],
            password=config["db"]["password"],
            port=config["db"]["port"],
        )
        return connection
    except Error as e:
        log.critical(f"Error connecting to database: {e}")
        return None

def startup():
    db = create_connection()
    if db is None:
        return False  # Return False if failure to start up
    cursor = db.cursor()
    for game_type in GAME_TYPES.keys():
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {game_type}") # Make sure all databases exist
        cursor.execute(f"USE {game_type}")
        cursor.execute("""CREATE TABLE IF NOT EXISTS leaderboard (
                          id INT PRIMARY KEY,
                          mu DECIMAL(10,4) NOT NULL,
                          sigma DECIMAL(10,4) NOT NULL,
                          INDEX mu_sort (mu DESC, sigma));
                       """)
    return True



def get_player(game_type, user: discord.User):
    db = create_connection()
    if db is None:
        return None  # Return none if failure to connect

    cursor = db.cursor()
    cursor.execute(f"USE {game_type}")  # Select database
    cursor.execute(f"SELECT * FROM leaderboard WHERE id={user.id}")  # Get UUID entries
    results = cursor.fetchall()
    if not len(results):  # Player is not in DB, return defaults
        uuid, mu, sigma = user.id, trueskill.MU, trueskill.SIGMA
    else:
        uuid, mu, sigma = results[0]  # Database has info

    player = Player(mu, sigma, user)  # Create player object from data
    # Close connection
    cursor.close()
    db.close()

    return player

def delete_player(user: discord.User):
    db = create_connection()
    if db is None:
        return False  # Return false if failure to connect, because the action failed

    cursor = db.cursor()
    for game_type in GAME_TYPES.keys():
        cursor.execute(f"USE {game_type}")  # Select database
        cursor.execute(f"DELETE FROM leaderboard WHERE id={user.id}")  # Delete UUID entries
    # Close connection
    db.commit()
    cursor.close()
    db.close()
    return True

def update_player(game_type: str, user: discord.User, mu: float, sigma: float):
    db = create_connection()
    if db is None:
        return False  # Return false if failure to connect, because the action failed

    cursor = db.cursor()
    cursor.execute(f"USE {game_type}")  # Select database
    cursor.execute(f"INSERT INTO leaderboard (id, mu, sigma)"
                   f"VALUES ({user.id}, {mu}, {sigma})"
                   f"ON DUPLICATE KEY UPDATE mu = {mu}, sigma = {sigma};")  # Delete UUID entries
    db.commit()

    # Close connection
    cursor.close()
    db.close()
    return True

def update_rankings(teams: list, game_type: str, cached_elo: dict):
    # TODO: implement
    trueskill.Rating()
