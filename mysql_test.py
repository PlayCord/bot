import random

import mysql.connector
from mysql.connector import Error

# Step 1: Establish a connection to the MySQL database
def create_connection():
    try:
        connection = mysql.connector.connect(
            host='localhost',  # Change if necessary
            user='root',
            password='password',
            port=3306,
        )
        if connection.is_connected():
            print("Connected to MySQL database")
        return connection
    except Error as e:
        print(f"Error: {e}")
        return None

# Step 2: Create a leaderboard table
def create_table(connection):
    create_table_query = """
    CREATE TABLE IF NOT EXISTS leaderboard (
        id INT PRIMARY KEY,
        mu DECIMAL(10,4) NOT NULL,
        sigma DECIMAL(10,4) NOT NULL,
        INDEX skill (mu DESC, sigma)
    );
    """
    try:
        cursor = connection.cursor()
        cursor.execute("CREATE DATABASE IF NOT EXISTS leaderboard")
        cursor.execute("USE leaderboard")
        cursor.execute(create_table_query)
        print("Leaderboard table created successfully")
    except Error as e:
        print(f"Error: {e}")

# Step 3: Insert data into the leaderboard table
def insert_leaderboard_entry(connection, id, mu, sigma):
    insert_query = """
    INSERT INTO leaderboard (id, mu, sigma)
    VALUES (%s, %s, %s)
    ON DUPLICATE KEY UPDATE mu = %s, sigma = %s;
    """
    values = (id, mu, sigma, mu, sigma)
    try:
        cursor = connection.cursor()
        cursor.execute(insert_query, values)
        connection.commit()
        #print(f"Entry for ID {id} inserted/updated successfully")
    except Error as e:
        print(f"Error: {e}")

# Step 4: Fetch and display leaderboard entries
def fetch_leaderboard(connection):
    fetch_query = "SELECT * FROM leaderboard ORDER BY mu DESC;"
    try:
        cursor = connection.cursor()
        cursor.execute(fetch_query)
        results = cursor.fetchall()
        for row in results:
            print(f"ID: {row[0]}, Mu: {row[1]}, Sigma: {row[2]}")
    except Error as e:
        print(f"Error: {e}")

# Step 5: Main function to execute steps
def main():
    connection = create_connection()
    if connection:
        create_table(connection)
        #Example: Insert data
        # for i in range(100000):
        insert_leaderboard_entry(connection, 19287, random.uniform(200, 400), random.uniform(1, 8))
        #Fetch and display leaderboard
        fetch_leaderboard(connection)
        connection.close()

if __name__ == "__main__":
    main()
