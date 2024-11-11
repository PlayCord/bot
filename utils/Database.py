import discord
import trueskill
import mysql.connector
from mysql.connector import Error
from ruamel.yaml import YAML
from trueskill import dynamic_draw_probability

import configuration.constants
from configuration.constants import *
from configuration.constants import LOGGING_ROOT, GAME_TYPES, GAME_TRUESKILL, MU
from utils.Player import Player
import logging
fake_data = {"tic_tac_toe": {1085939954758205561: 1000, 897146430664355850: 1200}}

logger = logging.getLogger(f"{LOGGING_ROOT}.database")


connections_made = 1
def create_connection():
    config = configuration.constants.CONFIGURATION
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
                          INDEX skill (mu DESC, sigma));
                       """)
    return True



def get_player(game_type, user: discord.User):
    db = create_connection()
    if db is None:
        return None  # Return none if failure to connect

    cursor = db.cursor()
    cursor.execute(f"USE {game_type}")  # Select database
    cursor.execute(f"SELECT * FROM leaderboard WHERE id={user.id}")  # Get id entries
    results = cursor.fetchall()
    if not len(results):  # Player is not in DB, return defaults
        id, mu, sigma = user.id, trueskill.MU, trueskill.SIGMA
    else:
        id, mu, sigma = results[0]  # Database has info

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
        cursor.execute(f"DELETE FROM leaderboard WHERE id={user.id}")  # Delete id entries
    # Close connection
    db.commit()
    cursor.close()
    db.close()
    return True

def update_player(game_type: str, id: int, mu: float, sigma: float):
    db = create_connection()
    if db is None:
        return False  # Return false if failure to connect, because the action failed

    cursor = db.cursor()
    cursor.execute(f"USE {game_type}")  # Select database
    cursor.execute(f"INSERT INTO leaderboard (id, mu, sigma)"
                   f"VALUES ({id}, {mu}, {sigma})"
                   f"ON DUPLICATE KEY UPDATE mu = {mu}, sigma = {sigma};")  # Delete id entries

    # Close connection
    db.commit()
    cursor.close()
    db.close()
    return True

def update_rankings(teams: list, game_type: str):
    game_type_data = GAME_TRUESKILL[game_type]

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






