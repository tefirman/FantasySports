
import requests
import pandas as pd

base_uri = "https://api.sleeper.app/v1/"

def get_user_details(username: str):
    response = requests.get("{}user/{}".format(base_uri,username))
    return response.json()

def get_leagues(user_id: int, season: int, sport: str = "nfl"):
    response = requests.get("{}user/{}/leagues/{}/{}".format(base_uri,user_id,sport,season))
    return response.json()

def get_rosters(league_id: int):
    response = requests.get("{}league/{}/rosters".format(base_uri,league_id))
    return response.json()

def get_users(league_id: int):
    response = requests.get("{}league/{}/users".format(base_uri,league_id))
    return response.json()

def get_matchups(league_id: int, week: int):
    response = requests.get("{}league/{}/matchups/{}".format(base_uri,league_id,week))
    return response.json()

def get_raw_players(sport: str = "nfl", output: str = "SleeperPlayers"):
    # Not entirely sure how to process this in the form of a pandas dataframe...
    # Saving it to text for now...
    response = requests.get("{}players/{}".format(base_uri,sport))
    players = response.json()
    players_df = pd.DataFrame([players[player_id] for player_id in players])
    if output:
        tempData = open(output + '.json','w')
        tempData.write(str(players))
        tempData.close()
        players_df.to_csv(output + '.csv',index=False)
    return players_df


