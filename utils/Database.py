

fake_data = {"tic_tac_toe": {1085939954758205561: 1000, 897146430664355850: 1200}}



def get_elo_for_player(game_type, player_id):
    if player_id not in fake_data[game_type].keys():
        return 1500, True
    else:
        return fake_data[game_type][player_id], False

def formatted_elo(elo_response):
    if elo_response[1]:
        return elo_response[0]+"?"
    else:
        return elo_response[0]