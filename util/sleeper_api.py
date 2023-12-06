
import requests
import pandas as pd
import time

base_uri = "https://api.sleeper.app/v1/"
pause = 0.1 # Limit is 1000 API calls per minutes, being conservative

def get_user_details(username: str):
    time.sleep(pause)
    response = requests.get("{}user/{}".format(base_uri,username))
    return response.json()

def get_leagues(user_id: int, season: int, sport: str = "nfl"):
    time.sleep(pause)
    response = requests.get("{}user/{}/leagues/{}/{}".format(base_uri,user_id,sport,season))
    return response.json()

def get_rosters(league_id: int):
    time.sleep(pause)
    response = requests.get("{}league/{}/rosters".format(base_uri,league_id))
    return response.json()

def get_users(league_id: int):
    time.sleep(pause)
    response = requests.get("{}league/{}/users".format(base_uri,league_id))
    return response.json()

def get_matchups(league_id: int, week: int):
    time.sleep(pause)
    response = requests.get("{}league/{}/matchups/{}".format(base_uri,league_id,week))
    return response.json()

def get_draft_picks(league_id: int):
    time.sleep(pause)
    response = requests.get("{}league/{}/drafts".format(base_uri,league_id))
    draft_id = response.json()[0]['draft_id']
    picks = requests.get("{}draft/{}/picks".format(base_uri,draft_id))
    return picks.json()

def get_raw_players(sport: str = "nfl", output: str = "SleeperPlayers"):
    # Saving it to text so that you only need to pull once a day...
    time.sleep(pause)
    response = requests.get("{}players/{}".format(base_uri,sport))
    players = response.json()
    players_df = pd.DataFrame([players[player_id] for player_id in players])
    if output:
        tempData = open(output + '.json','w')
        tempData.write(str(players))
        tempData.close()
        players_df.to_csv(output + '.csv',index=False)
    return players_df

def get_nfl_state(sport: str = "nfl"):
    time.sleep(pause)
    response = requests.get("{}state/{}".format(base_uri,sport))
    return response.json()


