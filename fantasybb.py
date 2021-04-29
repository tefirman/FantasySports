#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Oct 12 14:28:56 2019

@author: tefirman
"""

import pandas as pd
import numpy as np
import os
import datetime
from pytz import timezone
import optparse
from nba_api.stats.static import players
from nba_api.stats.endpoints import playergamelog
from sportsreference.nba.schedule import Schedule
from sportsreference.nba.teams import Teams
from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa
import json
import time
import sys
import requests
import warnings
warnings.filterwarnings("ignore")
latest_season = datetime.datetime.now().year - int(datetime.datetime.now().month <= 9)

""" Positions: PG, SG, G, SF, PF, F, C, C, Util, Util, BN, BN, BN, IL, IL """
""" Categories: FG%, FT%, 3PTM, PTS, REB, AST, ST, BLK, TO """

def establish_oauth(season=None,name=None,new_login=False):
    global oauth
    global gm
    global lg
    global lg_id
    global scoring
    global settings
    global rules
    global num_spots
    global teams
    global nba_schedule
    if new_login and os.path.exists('oauth2.json'):
        os.remove('oauth2.json')
    if not os.path.exists('oauth2.json'):
        creds = {'consumer_key': 'dj0yJmk9OFFGQ3dueUt6c0NtJmQ9WVdrOU1XdEdNelpJTnpBbWNHbzlNQS0tJnM9Y29uc3VtZXJzZWNyZXQmc3Y9MCZ4PWZm',\
                 'consumer_secret': '0828d2a5d40283ff7d3bd9c56abda72e9ea08b34'}
        with open('oauth2.json', "w") as f:
            f.write(json.dumps(creds))
    oauth = OAuth2(None, None, from_file='oauth2.json')
    if not season:
        season = latest_season
    gm = yfa.Game(oauth,'nba')
    while True:
        try:
            leagues = gm.yhandler.get_teams_raw()['fantasy_content']['users']['0']['user'][1]['games']
            break
        except:
            print('Teams query crapped out... Waiting 30 seconds and trying again...')
            time.sleep(30)
    for ind in range(leagues['count'] - 1,-1,-1):
        if leagues[str(ind)]['game'][0]['code'] == 'nba' and leagues[str(ind)]['game'][0]['season'] == str(latest_season):
            team = leagues[str(ind)]['game'][1]['teams']['0']['team'][0]
            lg_id = '.'.join([val['team_key'] for val in team if 'team_key' in val][0].split('.')[:3])
            break
    lg = gm.to_league(lg_id)
    rules = lg.yhandler.get_settings_raw(lg_id)['fantasy_content']['league'][1]['settings'][0]
    num_spots = sum([pos['roster_position']['count'] for pos in rules['roster_positions'] if pos['roster_position']['position'] != 'IL'])
    league_info = lg.yhandler.get_standings_raw(lg_id)['fantasy_content']['league']
    settings = league_info[0]
    settings['current_week'] = int(settings['current_week'])
    teams_info = league_info[1]['standings'][0]['teams']
    teams = pd.DataFrame([{'team_key':teams_info[str(ind)]['team'][0][0]['team_key'],\
    'name':teams_info[str(ind)]['team'][0][2]['name']} for ind in range(teams_info['count'])])
    nba_schedule = pd.DataFrame()
    for team in Teams():
        nba_schedule = nba_schedule.append(Schedule(team.abbreviation).dataframe,ignore_index=True)
    nba_schedule['week'] = nba_schedule.datetime.dt.week
    nba_schedule.loc[nba_schedule.week < 25,'week'] += nba_schedule.week.max()
    nba_schedule.week -= (nba_schedule.week.min() - 1)
    nba_schedule.date += ', ' + nba_schedule.time
    nba_schedule.date = pd.to_datetime(nba_schedule.date,infer_datetime_format=True)
    nba_schedule = nba_schedule.loc[nba_schedule.date >= datetime.datetime.now()]
    nba_schedule = nba_schedule.groupby(['opponent_abbr','week']).size().to_frame('num_games')

def refresh_oauth(threshold=59):
    global oauth
    global gm
    global lg_id
    global lg
    diff = (datetime.datetime.now(timezone('GMT')) - datetime.datetime(1970,1,1,0,0,0,0,\
    timezone('GMT'))).total_seconds() - oauth.token_time
    if diff >= threshold*60:
        time.sleep(max(3600 - diff + 5,0))
        oauth = OAuth2(None, None, from_file='oauth2.json')
        gm = yfa.Game(oauth,'nfl')
        lg = gm.to_league(lg_id)

def get_players():
    refresh_oauth()
    rosters = pd.DataFrame(columns=['name','player_id','fantasy_team'])
    for team in teams.team_key:
        tm = lg.to_team(team)
        roster = pd.DataFrame(tm.roster())
        if roster.shape[0] == 0:
            continue
        roster['fantasy_team'] = teams.loc[teams.team_key == team,'name'].values[0]
        rosters = rosters.append(roster[['name','player_id','fantasy_team']],ignore_index=True)
    info = pd.DataFrame(columns=['player_key','player_id','full_name',\
    'editorial_team_abbr','uniform_number','eligible_positions','status'])
    for page_ind in range(30):
        page = lg.yhandler.get_players_raw(lg.league_id,page_ind*25,'')['fantasy_content']['league'][1]['players']
        for player_ind in range(page['count']):
            player = page[str(player_ind)]['player'][0]
            vals = {}
            for field in player:
                if type(field) == dict:
                    if list(field.keys())[0] == 'name':
                        vals['full_name'] = [field['name']['full']]
                    elif list(field.keys())[0] == 'eligible_positions':
                        vals['eligible_positions'] = [[pos['position'] for pos in field['eligible_positions']]]
                    elif list(field.keys())[0] == 'status':
                        vals['status'] = [field['status']]
                    elif list(field.keys())[0] in info.columns:
                        vals[list(field.keys())[0]] = list(field.values())
            info = info.append(pd.DataFrame(vals),ignore_index=True,sort=False)
    info.editorial_team_abbr = info.editorial_team_abbr.str.upper()
    info = info.rename(index=str,columns={'editorial_team_abbr':'nba_team'})
    info.loc[info.nba_team == 'BKN','nba_team'] = 'BRK'
    info.loc[info.nba_team == 'CHA','nba_team'] = 'CHO'
    info.loc[info.nba_team == 'GS','nba_team'] = 'GSW'
    info.loc[info.nba_team == 'NO','nba_team'] = 'NOP'
    info.loc[info.nba_team == 'NY','nba_team'] = 'NYK'
    info.loc[info.nba_team == 'SA','nba_team'] = 'SAS'
    info.loc[info.uniform_number == '','uniform_number'] = '0'
    info[['player_id','uniform_number']] = info[['player_id','uniform_number']].astype(int)
    info = pd.merge(left=info,right=rosters.rename(index=str,\
    columns={'name':'full_name'}),how='left',on=['full_name','player_id'])
    return info

def get_games(first_year,last_year):
    nba_players = pd.DataFrame(players.get_players())
    nba_players = nba_players.loc[nba_players.is_active].reset_index(drop=True)
    try:
        missingIDs = pd.read_csv("https://raw.githubusercontent.com/" + \
        "tefirman/FantasySports/master/FantasyBasketball_MissingIDs.csv")
    except:
        missingIDs = [player.split(',') for player in requests.get("https://raw.githubusercontent.com/" + \
        "tefirman/FantasySports/master/FantasyBasketball_MissingIDs.csv",verify=False).text.split('\r')]
        missingIDs = pd.DataFrame(missingIDs[1:],columns=missingIDs[0])
    nba_players = nba_players.append(missingIDs,ignore_index=True)
    games = pd.DataFrame()
    for season in range(first_year,last_year + 1):
        year = str(season) + '-' + str(season%2000 + 1)
        print(season)
        for player_id in nba_players.id:
            if nba_players.loc[nba_players.id == player_id].index[0]%50 == 0:
                print('Player #' + str(nba_players.loc[nba_players.id == player_id].index[0]) + \
                ' out of ' + str(nba_players.shape[0]) + ', ' + str(datetime.datetime.now()))
            numTry = 0
            while True:
                try:
                    games = games.append(playergamelog.PlayerGameLog(player_id,\
                    season=year).get_data_frames()[0],ignore_index=True)
                    break
                except:
                    numTry += 1
                    if numTry == 100:
                        print('Tried 100 times and still not working... Stopping...')
                        sys.exit(0)
                    time.sleep(5)
    games = pd.merge(left=games.rename(index=str,columns={'Player_ID':'id'}),\
    right=nba_players[['id','full_name']],how='inner',on='id')
    games['FG2A'] = games['FGA'] - games['FG3A']
    games['FG2M'] = games['FGM'] - games['FG3M']
    return games

def get_rates(player_stats,start,as_of,num_sims=1000,reference_games=82):
    if as_of//100 < latest_season:
        prev = as_of//100*100 + 17
    else:
        prev = as_of - 1 - (80 if as_of%100 == 1 else 0) + (1 if as_of%100 > 11 else 0) # All-Star break in week 11
    if os.path.exists('FantasyBasketballStats.csv'):
        games = pd.read_csv('FantasyBasketballStats.csv')
        if games.SEASON_ID.min()%20000 > start//100:
            games = games.append(get_games(int(start//100),int(games.SEASON_ID.min()%20000) - 1))
            games.SEASON_ID = games.SEASON_ID.astype(int)
            games['season'] = games.SEASON_ID%20000
            games['week'] = pd.to_datetime(games['GAME_DATE'],infer_datetime_format=True).dt.week
            games.loc[games.week < 40,'week'] += games.week.max()
            games = pd.merge(left=games,right=games.groupby('season').week.min()\
            .reset_index().rename(columns={'week':'min_week'}),how='inner',on='season')
            games.week -= (games.min_week - 1)
            del games['min_week']
            games = games.loc[games.week <= 20]
            games.to_csv('FantasyBasketballStats.csv',index=False)
        if (games.season*100 + games.week).max() < prev:
            games = games.loc[games.season < prev//100]
            if games.shape[0] == 0:
                games = get_games(prev//100,prev//100)
            else:
                games = games.append(get_games(int(games.SEASON_ID.max()%20000) + 1,prev//100))
            games.SEASON_ID = games.SEASON_ID.astype(int)
            games['season'] = games.SEASON_ID%20000
            games['week'] = pd.to_datetime(games['GAME_DATE'],infer_datetime_format=True).dt.week
            games.loc[games.week < 40,'week'] += games.week.max()
            games = pd.merge(left=games,right=games.groupby('season').week.min()\
            .reset_index().rename(columns={'week':'min_week'}),how='inner',on='season')
            games.week -= (games.min_week - 1)
            del games['min_week']
            games = games.loc[games.week <= 20]
            games.to_csv('FantasyBasketballStats.csv',index=False)
    else:
        games = get_games(start//100,as_of//100)
        games.SEASON_ID = games.SEASON_ID.astype(int)
        games['season'] = games.SEASON_ID%20000
        games['week'] = pd.to_datetime(games['GAME_DATE'],infer_datetime_format=True).dt.week
        games.loc[games.week < 40,'week'] += games.week.max()
        games = pd.merge(left=games,right=games.groupby('season').week.min()\
        .reset_index().rename(columns={'week':'min_week'}),how='inner',on='season')
        games.week -= (games.min_week - 1)
        del games['min_week']
        games = games.loc[games.week <= 20]
        games.to_csv('FantasyBasketballStats.csv',index=False)
    games = games.loc[games.MIN >= 10]
    games = games.loc[(games.season*100 + games.week >= start) & (games.season*100 + games.week <= as_of)]
    try:
        corrections = pd.read_csv("https://raw.githubusercontent.com/" + \
        "tefirman/FantasySports/master/FantasyBasketball_NameCorrections.csv")
    except:
        corrections = [player.split(',') for player in requests.get("https://raw.githubusercontent.com/" + \
        "tefirman/FantasySports/master/FantasyBasketball_NameCorrections.csv",verify=False).text.split('\r')]
        corrections = pd.DataFrame(corrections[1:],columns=corrections[0])
    games = pd.merge(left=games,right=corrections,how='left',on='full_name')
    games.loc[~games.new_name.isnull(),'full_name'] = games.loc[~games.new_name.isnull(),'new_name']
    del games['new_name']
    games = pd.merge(left=player_stats,right=games.loc[games.MIN > 0],how='left',on='full_name')
    games = games.loc[~games.SEASON_ID.isnull() | ~games.fantasy_team.isnull()]
    rookies = games.loc[games.SEASON_ID.isnull()]
    if rookies.shape[0] > 0:
        print('No data available for ' + ', '.join(rookies.full_name) + '... Assuming average stats...')
    games = games.loc[~games.SEASON_ID.isnull()]
    """ Only keeping the specified number of games for each player """
    games = games.groupby('full_name').head(reference_games)
    player_stats = player_stats.loc[player_stats.full_name.isin(games.full_name.tolist()) | player_stats.full_name.isin(rookies.full_name.tolist())]
    player_stats = player_stats.append(pd.DataFrame({'full_name':['PG','SG','G','SF','PF','F','C','Util']}),ignore_index=True)
    """ Calculating player and position rates... """
    for player in player_stats.full_name:
        if player in ['PG','SG','G','SF','PF','F','C','Util']:
            inds = games.eligible_positions.apply(lambda x: player in x)
        else:
            inds = games.full_name == player
        player_stats.loc[player_stats.full_name == player,'num_games'] = inds.sum()
        player_stats.loc[player_stats.full_name == player,'MIN_avg'] = \
        (games.loc[inds,'MIN'].sum() + max(reference_games - inds.sum(),0)*games['MIN'].mean())/max(reference_games,inds.sum())
        player_stats.loc[player_stats.full_name == player,'MIN_std'] = \
        ((games.loc[inds,'MIN']**2).sum() + max(reference_games - inds.sum(),0)*(games['MIN']**2).mean())/max(reference_games,inds.sum())
        player_stats.loc[player_stats.full_name == player,'MIN_std'] -= \
        player_stats.loc[player_stats.full_name == player,'MIN_avg']**2
        player_stats.loc[player_stats.full_name == player,'MIN_std'] **= 0.5
        for stat in ['FTA','FG2A','FG3A','AST','STL','BLK','TOV','REB']:
            player_stats.loc[player_stats.full_name == player,stat + '_rate'] = \
            ((games.loc[inds,stat]/games.loc[inds,'MIN']).sum() + \
            max(reference_games - inds.sum(),0)*(games[stat]/games['MIN']).mean())/max(reference_games,inds.sum())
        for stat in ['FTM','FG2M','FG3M']:
            if games.loc[inds,stat[:-1] + 'A'].sum() > 0:
                player_stats.loc[player_stats.full_name == player,stat + '_rate'] = \
                (inds.sum()*games.loc[inds,stat].sum()/games.loc[inds,stat[:-1] + 'A'].sum() + \
                max(reference_games - inds.sum(),0)*games[stat].sum()/games[stat[:-1] + 'A'].sum())/max(reference_games,inds.sum())
            else:
                player_stats.loc[player_stats.full_name == player,stat + '_rate'] = \
                (max(reference_games - inds.sum(),0)*games[stat].sum()/games[stat[:-1] + 'A'].sum())/max(reference_games,inds.sum())
    return player_stats

def get_schedule():
    refresh_oauth()
    schedule = pd.DataFrame()
    for team in teams.team_key:
        tm = lg.to_team(team)
        for week in range(1,max(15,int(settings['current_week']) + 1)):
            while True:
                try:
                    matchup = tm.yhandler.get_matchup_raw(team,week)\
                    ['fantasy_content']['team'][1]['matchups']#['0']['matchup']
                    break
                except:
                    print('Matchup query crapped out... Waiting 30 seconds and trying again...')
                    time.sleep(30)
            if '0' in matchup:
                matchup = matchup['0']['matchup']
            else:
                continue
            schedule = schedule.append(pd.DataFrame({'week':[week],\
            'team_x':[matchup['0']['teams']['0']['team'][0][2]['name']],\
            'team_y':[matchup['0']['teams']['1']['team'][0][2]['name']],\
            'wins_x':[matchup['0']['teams']['0']['team'][1]['team_points']['total']],\
            'wins_y':[matchup['0']['teams']['1']['team'][1]['team_points']['total']],\
            'FG%_x':[matchup['0']['teams']['0']['team'][1]['team_stats']['stats'][0]['stat']['value']],\
            'FT%_x':[matchup['0']['teams']['0']['team'][1]['team_stats']['stats'][2]['stat']['value']],\
            'FG3M_x':[matchup['0']['teams']['0']['team'][1]['team_stats']['stats'][4]['stat']['value']],\
            'PTS_x':[matchup['0']['teams']['0']['team'][1]['team_stats']['stats'][5]['stat']['value']],\
            'REB_x':[matchup['0']['teams']['0']['team'][1]['team_stats']['stats'][6]['stat']['value']],\
            'AST_x':[matchup['0']['teams']['0']['team'][1]['team_stats']['stats'][7]['stat']['value']],\
            'STL_x':[matchup['0']['teams']['0']['team'][1]['team_stats']['stats'][8]['stat']['value']],\
            'BLK_x':[matchup['0']['teams']['0']['team'][1]['team_stats']['stats'][9]['stat']['value']],\
            'TOV_x':[matchup['0']['teams']['0']['team'][1]['team_stats']['stats'][10]['stat']['value']],\
            'FG%_y':[matchup['0']['teams']['1']['team'][1]['team_stats']['stats'][0]['stat']['value']],\
            'FT%_y':[matchup['0']['teams']['1']['team'][1]['team_stats']['stats'][2]['stat']['value']],\
            'FG3M_y':[matchup['0']['teams']['1']['team'][1]['team_stats']['stats'][4]['stat']['value']],\
            'PTS_y':[matchup['0']['teams']['1']['team'][1]['team_stats']['stats'][5]['stat']['value']],\
            'REB_y':[matchup['0']['teams']['1']['team'][1]['team_stats']['stats'][6]['stat']['value']],\
            'AST_y':[matchup['0']['teams']['1']['team'][1]['team_stats']['stats'][7]['stat']['value']],\
            'STL_y':[matchup['0']['teams']['1']['team'][1]['team_stats']['stats'][8]['stat']['value']],\
            'BLK_y':[matchup['0']['teams']['1']['team'][1]['team_stats']['stats'][9]['stat']['value']],\
            'TOV_y':[matchup['0']['teams']['1']['team'][1]['team_stats']['stats'][10]['stat']['value']]}),ignore_index=True)
    switch = schedule.team_x > schedule.team_y
    for stat in ['team','wins','FG%','FT%','FG3M','PTS','REB','AST','STL','BLK','TOV']:
        schedule.loc[switch,'temp'] = schedule.loc[switch,stat + '_x']
        schedule.loc[switch,stat + '_x'] = schedule.loc[switch,stat + '_y']
        schedule.loc[switch,stat + '_y'] = schedule.loc[switch,'temp']
    schedule = schedule[['week','team_x','team_y','wins_x','wins_y',\
    'FG%_x','FT%_x','FG3M_x','PTS_x','REB_x','AST_x','STL_x','BLK_x','TOV_x',\
    'FG%_y','FT%_y','FG3M_y','PTS_y','REB_y','AST_y','STL_y','BLK_y','TOV_y']]\
    .drop_duplicates().sort_values(by=['week','team_x','team_y']).reset_index(drop=True)
    schedule['FGM_x'],schedule['FGA_x'] = schedule['FG%_x'].str.split('/').str
    schedule['FGM_y'],schedule['FGA_y'] = schedule['FG%_y'].str.split('/').str
    schedule['FTM_x'],schedule['FTA_x'] = schedule['FT%_x'].str.split('/').str
    schedule['FTM_y'],schedule['FTA_y'] = schedule['FT%_y'].str.split('/').str
    schedule.replace('',0,inplace=True)
    schedule[['wins_x','wins_y','FGM_x','FGA_x','FTM_x','FTA_x','FG3M_x',\
    'PTS_x','REB_x','AST_x','STL_x','BLK_x','TOV_x','FGM_y','FGA_y','FTM_y',\
    'FTA_y','FG3M_y','PTS_y','REB_y','AST_y','STL_y','BLK_y','TOV_y']] = \
    schedule[['wins_x','wins_y','FGM_x','FGA_x','FTM_x','FTA_x','FG3M_x',\
    'PTS_x','REB_x','AST_x','STL_x','BLK_x','TOV_x','FGM_y','FGA_y','FTM_y',\
    'FTA_y','FG3M_y','PTS_y','REB_y','AST_y','STL_y','BLK_y','TOV_y']].astype(float)
    schedule['FG%_x'] = (schedule['FGM_x']/schedule['FGA_x']).fillna(0.0)
    schedule['FG%_y'] = (schedule['FGM_y']/schedule['FGA_y']).fillna(0.0)
    schedule['FT%_x'] = (schedule['FTM_x']/schedule['FTA_x']).fillna(0.0)
    schedule['FT%_y'] = (schedule['FTM_y']/schedule['FTA_y']).fillna(0.0)
    completed = schedule['wins_x'] + schedule['wins_y'] > 0
    schedule.loc[completed,'wins_x'] += (9 - schedule.loc[completed,'wins_x'] - schedule.loc[completed,'wins_y'])/2
    schedule.loc[completed,'wins_y'] += 9 - schedule.loc[completed,'wins_x'] - schedule.loc[completed,'wins_y']
    return schedule

def team_wins_comp(week):
    schedule = get_schedule()
    schedule = schedule.loc[schedule.week == week]
    scores = schedule[['team_x','FG%_x','FT%_x','FG3M_x','PTS_x','REB_x',\
    'AST_x','STL_x','BLK_x','TOV_x']].rename(index=str,columns={'team_x':'team',\
    'FG%_x':'FG%','FT%_x':'FT%','FG3M_x':'FG3M','PTS_x':'PTS','REB_x':'REB',\
    'AST_x':'AST','STL_x':'STL','BLK_x':'BLK','TOV_x':'TOV'}).append(schedule[['team_y',\
    'FG%_y','FT%_y','FG3M_y','PTS_y','REB_y','AST_y','STL_y','BLK_y','TOV_y']]\
    .rename(index=str,columns={'team_y':'team','FG%_y':'FG%','FT%_y':'FT%',\
    'FG3M_y':'FG3M','PTS_y':'PTS','REB_y':'REB','AST_y':'AST','STL_y':'STL',\
    'BLK_y':'BLK','TOV_y':'TOV'}),ignore_index=True)
    stats = [stat for stat in scores.columns if stat != 'team']
    for team in scores.team.unique():
        scores['wins'] = 0
        for stat in stats:
            if stat == 'TOV':
                scores['wins'] += (scores[stat] > scores.loc[scores.team == team,stat].values[0]).astype(float) + \
                0.5*(scores[stat] == scores.loc[scores.team == team,stat].values[0]).astype(float)
            else:
                scores['wins'] += (scores[stat] < scores.loc[scores.team == team,stat].values[0]).astype(float) + \
                0.5*(scores[stat] == scores.loc[scores.team == team,stat].values[0]).astype(float)
        print('\n' + team)
        print(scores[['team','wins']])
        print('Average: ' + str(round(scores.wins.mean(),2)))
        print('St. Dev.: ' + str(round(scores.wins.std(),2)))
        del scores['wins']

def player_sim(player,num_sims=1000,week=None):
    if week == None: # or week >= 11:
        games_per_week = nba_schedule.groupby('num_games').size().to_frame('freq').loc[2:4]
        num_games = np.random.choice(games_per_week.index.tolist(),\
        p=(games_per_week.freq/games_per_week.freq.sum()).tolist(),size=num_sims)
    elif week == 11: # All-Star Break combines week 11 and 12
        if (player['nba_team'],11) in nba_schedule.index or (player['nba_team'],12) in nba_schedule.index:
            num_games = num_sims*[nba_schedule.loc[(player['nba_team'],[11,12]),'num_games'].sum()]
        else:
            num_games = num_sims*[0]
    elif week >= 12: # All-Star Break combines week 11 and 12
        if (player['nba_team'],week + 1) in nba_schedule.index:
            num_games = num_sims*[nba_schedule.loc[(player['nba_team'],week + 1),'num_games']]
        else:
            num_games = num_sims*[0]
    else:
        if (player['nba_team'],week) in nba_schedule.index:
            num_games = num_sims*[nba_schedule.loc[(player['nba_team'],week),'num_games']]
        else:
            num_games = num_sims*[0]
    
#    """ HARD CODING IN LINEUP ISSUES DURING THE PLAYOFFS!!! """
#    if player['full_name'] in ['Gary Trent Jr.'] and week == 16:
#        num_games = [sim - 1 for sim in num_games]
#    """ HARD CODING IN LINEUP ISSUES DURING THE PLAYOFFS!!! """
    
    player_sims = pd.DataFrame({'sim':np.arange(num_sims),'name':[player]*num_sims,'GM':num_games})
    player_sims['MIN'] = player_sims.GM.apply(lambda x: sum([max(np.random.normal(\
    loc=player['MIN_avg'],scale=player['MIN_std']),0) for y in range(x)]))
    for stat in ['FTA','FG2A','FG3A','AST','STL','BLK','TOV','REB']:
        player_sims[stat] = player_sims.MIN.apply(lambda x: np.random.poisson(lam=x*player[stat + '_rate']))
    for stat in ['FTM','FG2M','FG3M']:
        player_sims[stat] = player_sims[stat[:-1] + 'A'].apply(lambda x: np.random.binomial(x,player[stat + '_rate']))
    player_sims['PTS'] = player_sims['FTM'] + player_sims['FG2M']*2 + player_sims['FG3M']*3
    return player_sims

def team_sim(team,num_sims=1000,week=None):
    team_sims = pd.DataFrame()
    for player in team.full_name:
        team_sims = team_sims.append(player_sim(team.loc[team.full_name == player].iloc[0].to_dict(),num_sims,week))
    team_sims = team_sims.groupby('sim').sum().reset_index()
    team_sims['FGM'] = team_sims['FG2M'] + team_sims['FG3M']
    team_sims['FGA'] = team_sims['FG2A'] + team_sims['FG3A']
    team_sims['FG%'] = team_sims['FGM']/team_sims['FGA']
    team_sims['FT%'] = team_sims['FTM']/team_sims['FTA']
    return team_sims

def get_WAR(players,num_sims=1000):
    avg_sims = team_sim(players.loc[players.full_name.isin(['PG','SG','G','SF','PF','F','C','Util'])]\
    .append(players.loc[players.full_name.isin(['C','Util'])],ignore_index=True),num_sims)
    team_stats = team_sim(players.loc[players.full_name.isin(['PG','SG','G','SF','PF','F','C','Util'])]\
    .append(players.loc[players.full_name.isin(['C'])],ignore_index=True),num_sims)
    player_war = {}
    for full_name in players.full_name:
        if (len(player_war) + 1)%50 == 0:
            print('Player #' + str(len(player_war) + 1) + ' out of ' + str(players.shape[0]))
        sim_stats = team_stats.append(player_sim(players.loc[players.full_name == full_name].iloc[0].to_dict(),num_sims),ignore_index=True,sort=False)
        sims = sim_stats.groupby('sim').sum().reset_index()
        sims['FG%'] = (sims['FG2M'] + sims['FG3M'])/(sims['FG2A'] + sims['FG3A'])
        sims['FT%'] = sims['FTM']/sims['FTA']
        player_war[full_name] = {'FG%':round(((sims['FG%'].values > avg_sims['FG%'].values).sum() + 0.5*(sims['FG%'].values == avg_sims['FG%'].values).sum())/num_sims - 0.5,4),\
        'FT%':round(((sims['FT%'].values > avg_sims['FT%'].values).sum() + 0.5*(sims['FT%'].values == avg_sims['FT%'].values).sum())/num_sims - 0.5,4),\
        'FG3M':round(((sims['FG3M'].values > avg_sims['FG3M'].values).sum() + 0.5*(sims['FG3M'].values == avg_sims['FG3M'].values).sum())/num_sims - 0.5,4),\
        'PTS':round(((sims['PTS'].values > avg_sims['PTS'].values).sum() + 0.5*(sims['PTS'].values == avg_sims['PTS'].values).sum())/num_sims - 0.5,4),\
        'REB':round(((sims['REB'].values > avg_sims['REB'].values).sum() + 0.5*(sims['REB'].values == avg_sims['REB'].values).sum())/num_sims - 0.5,4),\
        'AST':round(((sims['AST'].values > avg_sims['AST'].values).sum() + 0.5*(sims['AST'].values == avg_sims['AST'].values).sum())/num_sims - 0.5,4),\
        'STL':round(((sims['STL'].values > avg_sims['STL'].values).sum() + 0.5*(sims['STL'].values == avg_sims['STL'].values).sum())/num_sims - 0.5,4),\
        'BLK':round(((sims['BLK'].values > avg_sims['BLK'].values).sum() + 0.5*(sims['BLK'].values == avg_sims['BLK'].values).sum())/num_sims - 0.5,4),\
        'TOV':round(((sims['TOV'].values < avg_sims['TOV'].values).sum() + 0.5*(sims['TOV'].values == avg_sims['TOV'].values).sum())/num_sims - 0.5,4)}
        player_war[full_name]['WAR'] = round(player_war[full_name]['FG%'] + player_war[full_name]['FT%'] + \
        player_war[full_name]['FG3M'] + player_war[full_name]['PTS'] + player_war[full_name]['REB'] + \
        player_war[full_name]['AST'] + player_war[full_name]['STL'] + player_war[full_name]['BLK'] + player_war[full_name]['TOV'],4)
    player_war = pd.merge(left=pd.DataFrame(player_war).T.sort_values(by='WAR',ascending=False).reset_index()\
    .rename(index=str,columns={'index':'full_name'}),right=players,how='inner',on='full_name')
    return player_war

def convert_to_wins(matchups):
    matchups['wins_x'] = 0
    matchups['wins_y'] = 0
    for stat in ['FG%','FT%','FG3M','PTS','REB','AST','STL','BLK']:
        matchups[stat + '_x'] = (matchups[stat + '_x'].values > matchups[stat + '_y'].values).astype(float) + \
        0.5*(matchups[stat + '_x'].values == matchups[stat + '_y'].values).astype(float)
        matchups[stat + '_y'] = 1 - matchups[stat + '_x']
        matchups['wins_x'] += matchups[stat + '_x']
        matchups['wins_y'] += matchups[stat + '_y']
    matchups['TOV_x'] = (matchups['TOV_x'].values < matchups['TOV_y'].values).astype(float) + \
    0.5*(matchups['TOV_x'].values == matchups['TOV_y'].values).astype(float)
    matchups['TOV_y'] = 1 - matchups['TOV_x']
    matchups['wins_x'] += matchups['TOV_x']
    matchups['wins_y'] += matchups['TOV_y']
    return matchups

def matchup_sim(team_1,team_2,num_sims=1000,week=None):
    matchups = pd.merge(left=team_sim(team_1,num_sims,week),\
    right=team_sim(team_2,num_sims,week),how='inner',on='sim')
    matchups = convert_to_wins(matchups)
    return matchups

def season_sim(schedule,rosters,num_sims=1000,winner=False,current_week=False):
    refresh_oauth()
    season_sims = pd.DataFrame()
    for ind in range(schedule.shape[0]):
        if schedule.loc[ind,'week'] < settings['current_week']:
            season_sims = season_sims.append([convert_to_wins(schedule.loc[ind:ind])]*num_sims,ignore_index=True)
        else:
            matchups = pd.merge(left=team_sim(rosters.loc[(rosters.fantasy_team == schedule.loc[ind,'team_x']) & \
            (rosters.until.isnull() | (rosters.until < schedule.loc[ind,'week']))].iloc[:num_spots],num_sims,schedule.loc[ind,'week']),\
            right=team_sim(rosters.loc[(rosters.fantasy_team == schedule.loc[ind,'team_y']) & (rosters.until.isnull() | \
            (rosters.until < schedule.loc[ind,'week']))].iloc[:num_spots],num_sims,schedule.loc[ind,'week']),how='inner',on='sim')
            for stat in ['FGM','FGA','FTM','FTA','FG3M','PTS','REB','AST','STL','BLK','TOV']:
                matchups[stat + '_x'] += schedule.loc[ind,stat + '_x']
                matchups[stat + '_y'] += schedule.loc[ind,stat + '_y']
            matchups['FG%_x'] = matchups['FGM_x']/matchups['FGA_x']
            matchups['FG%_y'] = matchups['FGM_y']/matchups['FGA_y']
            matchups['FT%_x'] = matchups['FTM_x']/matchups['FTA_x']
            matchups['FT%_y'] = matchups['FTM_y']/matchups['FTA_y']
            matchups = convert_to_wins(matchups)
            matchups['week'] = schedule.loc[ind,'week']
            matchups['team_x'] = schedule.loc[ind,'team_x']
            matchups['team_y'] = schedule.loc[ind,'team_y']
            season_sims = season_sims.append(matchups,ignore_index=True,sort=False)
    season_sims.loc[season_sims.sim.isnull(),'sim'] = season_sims.loc[season_sims.sim.isnull()].index%num_sims
    if current_week:
        my_team = teams.loc[teams.team_key == lg.team_key(),'name'].values[0]
        current = season_sims.loc[(season_sims.week == settings['current_week']) & \
        (season_sims.team_x == my_team),['wins_x']].rename(columns={'wins_x':'wins'})\
        .append(season_sims.loc[(season_sims.week == settings['current_week']) & \
        (season_sims.team_y == my_team),['wins_y']].rename(columns={'wins_y':'wins'}))
        print(current.groupby('wins').size()/num_sims)
        print('Avg Wins = ' + str(round(current.wins.mean(),2)) + ' +/- ' + str(round(current.wins.std(),2)))
        print('Most Likely Wins = ' + str(current.wins.mode().values[0]))
        print('Overall Win Probability = ' + str(round(100*sum(current.wins > 4.5)/current.shape[0],1)) + '%')
    schedule_sim = season_sims.groupby(['week','team_x','team_y'])[['wins_x','wins_y',\
    'FG%_x','FT%_x','FG3M_x','PTS_x','REB_x','AST_x','STL_x','BLK_x','TOV_x',\
    'FG%_y','FT%_y','FG3M_y','PTS_y','REB_y','AST_y','STL_y','BLK_y','TOV_y']].mean().reset_index()
    standings = season_sims.loc[season_sims.week <= int(settings['end_week']) - 2]\
    .groupby(['sim','team_x'])[['FG%_x','FT%_x','FG3M_x','PTS_x','REB_x','AST_x',\
    'STL_x','BLK_x','TOV_x','wins_x']].sum().reset_index().rename(index=str,\
    columns={'team_x':'team','FG%_x':'FG%','FT%_x':'FT%','FG3M_x':'FG3M',\
    'PTS_x':'PTS','REB_x':'REB','AST_x':'AST','STL_x':'STL','BLK_x':'BLK',\
    'TOV_x':'TOV','wins_x':'wins'}).append(season_sims.loc[season_sims.week <= \
    int(settings['end_week']) - 2].groupby(['sim','team_y'])[['FG%_y','FT%_y',\
    'FG3M_y','PTS_y','REB_y','AST_y','STL_y','BLK_y','TOV_y','wins_y']].sum()\
    .reset_index().rename(index=str,columns={'team_y':'team','FG%_y':'FG%',\
    'FT%_y':'FT%','FG3M_y':'FG3M','PTS_y':'PTS','REB_y':'REB','AST_y':'AST',\
    'STL_y':'STL','BLK_y':'BLK','TOV_y':'TOV','wins_y':'wins'}),ignore_index=True)\
    .groupby(['sim','team']).sum().reset_index().sort_values(by=['sim','wins'],\
    ascending=[True,False]).reset_index(drop=True)
    standings['playoffs'] = standings.index%10 <= 3
    if winner:
        seed_sims = standings.loc[standings.playoffs].groupby('sim').team.apply(lambda x: '_'.join(x)).reset_index()\
        .groupby('team').size().sort_values(ascending=False).to_frame('freq').reset_index()
        winner = {team:[0] for team in standings.team.unique()}
        runner_up = {team:[0] for team in standings.team.unique()}
        third = {team:[0] for team in standings.team.unique()}
        for ind in range(len(seed_sims)):
            if ind%50 == 0:
                print('Seeding #' + str(ind) + ' out of ' + str(len(seed_sims)) + ', ' + str(datetime.datetime.now()))
            seeds = seed_sims.loc[ind,'team'].split('_')
            if settings['current_week'] >= int(settings['end_week']) - 1:
                semi_1 = season_sims.loc[(season_sims.week == int(settings['end_week']) - 1) & \
                season_sims.team_x.isin([seeds[0],seeds[3]])].reset_index(drop=True)
                if semi_1.team_x.values[0] == seeds[3]:
                    for stat in ['team','wins','FG%','FT%','FG3M','PTS','REB','AST','STL','BLK','TOV']:
                        semi_1['temp'] = semi_1[stat + '_x']
                        semi_1[stat + '_x'] = semi_1[stat + '_y']
                        semi_1[stat + '_y'] = semi_1['temp']
                semi_2 = season_sims.loc[(season_sims.week == int(settings['end_week']) - 1) & \
                season_sims.team_x.isin([seeds[1],seeds[2]])].reset_index(drop=True)
                if semi_2.team_x.values[0] == seeds[2]:
                    for stat in ['team','wins','FG%','FT%','FG3M','PTS','REB','AST','STL','BLK','TOV']:
                        semi_2['temp'] = semi_2[stat + '_x']
                        semi_2[stat + '_x'] = semi_2[stat + '_y']
                        semi_2[stat + '_y'] = semi_2['temp']
            else:
                semi_1 = matchup_sim(rosters.loc[(rosters.fantasy_team == seeds[0]) & \
                (rosters.until.isnull() | (rosters.until < int(settings['end_week']) - 1))].iloc[:num_spots],\
                rosters.loc[(rosters.fantasy_team == seeds[3]) & (rosters.until.isnull() | \
                (rosters.until < int(settings['end_week']) - 1))].iloc[:num_spots],seed_sims.loc[ind,'freq'],int(settings['end_week']) - 1)
                semi_2 = matchup_sim(rosters.loc[(rosters.fantasy_team == seeds[1]) & \
                (rosters.until.isnull() | (rosters.until < int(settings['end_week']) - 1))].iloc[:num_spots],\
                rosters.loc[(rosters.fantasy_team == seeds[2]) & (rosters.until.isnull() | \
                (rosters.until < int(settings['end_week']) - 1))].iloc[:num_spots],seed_sims.loc[ind,'freq'],int(settings['end_week']) - 1)
            if ((semi_1.wins_x >= semi_1.wins_y) & (semi_2.wins_x >= semi_2.wins_y)).sum() > 0:
                if settings['current_week'] >= int(settings['end_week']):
                    final = season_sims.loc[(season_sims.week == int(settings['end_week'])) & season_sims.team_x.isin([seeds[0],seeds[1]])]
                    consolation = season_sims.loc[(season_sims.week == int(settings['end_week'])) & season_sims.team_x.isin([seeds[2],seeds[3]])]
                    if final.team_x.values[0] == seeds[1]:
                        for stat in ['team','wins','FG%','FT%','FG3M','PTS','REB','AST','STL','BLK','TOV']:
                            final['temp'] = final[stat + '_x']
                            final[stat + '_x'] = final[stat + '_y']
                            final[stat + '_y'] = final['temp']
                    if consolation.team_x.values[0] == seeds[3]:
                        for stat in ['team','wins','FG%','FT%','FG3M','PTS','REB','AST','STL','BLK','TOV']:
                            consolation['temp'] = consolation[stat + '_x']
                            consolation[stat + '_x'] = consolation[stat + '_y']
                            consolation[stat + '_y'] = consolation['temp']
                else:
                    final = matchup_sim(rosters.loc[(rosters.fantasy_team == seeds[0]) & \
                    (rosters.until.isnull() | (rosters.until < int(settings['end_week'])))].iloc[:num_spots],\
                    rosters.loc[(rosters.fantasy_team == seeds[1]) & (rosters.until.isnull() | \
                    (rosters.until < int(settings['end_week'])))].iloc[:num_spots],\
                    ((semi_1.wins_x >= semi_1.wins_y) & (semi_2.wins_x >= semi_2.wins_y)).sum(),int(settings['end_week']))
                    consolation = matchup_sim(rosters.loc[(rosters.fantasy_team == seeds[2]) & \
                    (rosters.until.isnull() | (rosters.until < int(settings['end_week'])))].iloc[:num_spots],\
                    rosters.loc[(rosters.fantasy_team == seeds[3]) & (rosters.until.isnull() | \
                    (rosters.until < int(settings['end_week'])))].iloc[:num_spots],\
                    ((semi_1.wins_x >= semi_1.wins_y) & (semi_2.wins_x >= semi_2.wins_y)).sum(),int(settings['end_week']))
                winner[seeds[0]][0] += final.loc[final.wins_x >= final.wins_y].shape[0]
                winner[seeds[1]][0] += final.loc[final.wins_x < final.wins_y].shape[0]
                runner_up[seeds[1]][0] += final.loc[final.wins_x >= final.wins_y].shape[0]
                runner_up[seeds[0]][0] += final.loc[final.wins_x < final.wins_y].shape[0]
                third[seeds[2]][0] += consolation.loc[consolation.wins_x >= consolation.wins_y].shape[0]
                third[seeds[3]][0] += consolation.loc[consolation.wins_x < consolation.wins_y].shape[0]
            if ((semi_1.wins_x >= semi_1.wins_y) & (semi_2.wins_x < semi_2.wins_y)).sum() > 0:
                if settings['current_week'] >= int(settings['end_week']):
                    final = season_sims.loc[(season_sims.week == int(settings['end_week'])) & season_sims.team_x.isin([seeds[0],seeds[2]])]
                    consolation = season_sims.loc[(season_sims.week == int(settings['end_week'])) & season_sims.team_x.isin([seeds[1],seeds[3]])]
                    if final.team_x.values[0] == seeds[2]:
                        for stat in ['team','wins','FG%','FT%','FG3M','PTS','REB','AST','STL','BLK','TOV']:
                            final['temp'] = final[stat + '_x']
                            final[stat + '_x'] = final[stat + '_y']
                            final[stat + '_y'] = final['temp']
                    if consolation.team_x.values[0] == seeds[3]:
                        for stat in ['team','wins','FG%','FT%','FG3M','PTS','REB','AST','STL','BLK','TOV']:
                            consolation['temp'] = consolation[stat + '_x']
                            consolation[stat + '_x'] = consolation[stat + '_y']
                            consolation[stat + '_y'] = consolation['temp']
                else:
                    final = matchup_sim(rosters.loc[(rosters.fantasy_team == seeds[0]) & \
                    (rosters.until.isnull() | (rosters.until < int(settings['end_week'])))].iloc[:num_spots],\
                    rosters.loc[(rosters.fantasy_team == seeds[2]) & (rosters.until.isnull() | \
                    (rosters.until < int(settings['end_week'])))].iloc[:num_spots],\
                    ((semi_1.wins_x >= semi_1.wins_y) & (semi_2.wins_x < semi_2.wins_y)).sum(),int(settings['end_week']))
                    consolation = matchup_sim(rosters.loc[(rosters.fantasy_team == seeds[1]) & \
                    (rosters.until.isnull() | (rosters.until < int(settings['end_week'])))].iloc[:num_spots],\
                    rosters.loc[(rosters.fantasy_team == seeds[3]) & (rosters.until.isnull() | \
                    (rosters.until < int(settings['end_week'])))].iloc[:num_spots],\
                    ((semi_1.wins_x >= semi_1.wins_y) & (semi_2.wins_x < semi_2.wins_y)).sum(),int(settings['end_week']))
                winner[seeds[0]][0] += final.loc[final.wins_x >= final.wins_y].shape[0]
                winner[seeds[2]][0] += final.loc[final.wins_x < final.wins_y].shape[0]
                runner_up[seeds[2]][0] += final.loc[final.wins_x >= final.wins_y].shape[0]
                runner_up[seeds[0]][0] += final.loc[final.wins_x < final.wins_y].shape[0]
                third[seeds[1]][0] += consolation.loc[consolation.wins_x >= consolation.wins_y].shape[0]
                third[seeds[3]][0] += consolation.loc[consolation.wins_x < consolation.wins_y].shape[0]
            if ((semi_1.wins_x < semi_1.wins_y) & (semi_2.wins_x >= semi_2.wins_y)).sum() > 0:
                if settings['current_week'] >= int(settings['end_week']):
                    final = season_sims.loc[(season_sims.week == int(settings['end_week'])) & season_sims.team_x.isin([seeds[1],seeds[3]])]
                    consolation = season_sims.loc[(season_sims.week == int(settings['end_week'])) & season_sims.team_x.isin([seeds[0],seeds[2]])]
                    if final.team_x.values[0] == seeds[3]:
                        for stat in ['team','wins','FG%','FT%','FG3M','PTS','REB','AST','STL','BLK','TOV']:
                            final['temp'] = final[stat + '_x']
                            final[stat + '_x'] = final[stat + '_y']
                            final[stat + '_y'] = final['temp']
                    if consolation.team_x.values[0] == seeds[2]:
                        for stat in ['team','wins','FG%','FT%','FG3M','PTS','REB','AST','STL','BLK','TOV']:
                            consolation['temp'] = consolation[stat + '_x']
                            consolation[stat + '_x'] = consolation[stat + '_y']
                            consolation[stat + '_y'] = consolation['temp']
                else:
                    final = matchup_sim(rosters.loc[(rosters.fantasy_team == seeds[1]) & \
                    (rosters.until.isnull() | (rosters.until < int(settings['end_week'])))].iloc[:num_spots],\
                    rosters.loc[(rosters.fantasy_team == seeds[3]) & (rosters.until.isnull() | \
                    (rosters.until < int(settings['end_week'])))].iloc[:num_spots],\
                    ((semi_1.wins_x < semi_1.wins_y) & (semi_2.wins_x >= semi_2.wins_y)).sum(),int(settings['end_week']))
                    consolation = matchup_sim(rosters.loc[(rosters.fantasy_team == seeds[0]) & \
                    (rosters.until.isnull() | (rosters.until < int(settings['end_week'])))].iloc[:num_spots],\
                    rosters.loc[(rosters.fantasy_team == seeds[2]) & (rosters.until.isnull() | \
                    (rosters.until < int(settings['end_week'])))].iloc[:num_spots],\
                    ((semi_1.wins_x < semi_1.wins_y) & (semi_2.wins_x >= semi_2.wins_y)).sum(),int(settings['end_week']))
                winner[seeds[1]][0] += final.loc[final.wins_x >= final.wins_y].shape[0]
                winner[seeds[3]][0] += final.loc[final.wins_x < final.wins_y].shape[0]
                runner_up[seeds[3]][0] += final.loc[final.wins_x >= final.wins_y].shape[0]
                runner_up[seeds[1]][0] += final.loc[final.wins_x < final.wins_y].shape[0]
                third[seeds[0]][0] += consolation.loc[consolation.wins_x >= consolation.wins_y].shape[0]
                third[seeds[2]][0] += consolation.loc[consolation.wins_x < consolation.wins_y].shape[0]
            if ((semi_1.wins_x < semi_1.wins_y) & (semi_2.wins_x < semi_2.wins_y)).sum() > 0:
                if settings['current_week'] >= int(settings['end_week']):
                    final = season_sims.loc[(season_sims.week == int(settings['end_week'])) & season_sims.team_x.isin([seeds[2],seeds[3]])]
                    consolation = season_sims.loc[(season_sims.week == int(settings['end_week'])) & season_sims.team_x.isin([seeds[0],seeds[1]])]
                    if final.team_x.values[0] == seeds[3]:
                        for stat in ['team','wins','FG%','FT%','FG3M','PTS','REB','AST','STL','BLK','TOV']:
                            final['temp'] = final[stat + '_x']
                            final[stat + '_x'] = final[stat + '_y']
                            final[stat + '_y'] = final['temp']
                    if consolation.team_x.values[0] == seeds[1]:
                        for stat in ['team','wins','FG%','FT%','FG3M','PTS','REB','AST','STL','BLK','TOV']:
                            consolation['temp'] = consolation[stat + '_x']
                            consolation[stat + '_x'] = consolation[stat + '_y']
                            consolation[stat + '_y'] = consolation['temp']
                else:
                    final = matchup_sim(rosters.loc[(rosters.fantasy_team == seeds[2]) & \
                    (rosters.until.isnull() | (rosters.until < int(settings['end_week'])))].iloc[:num_spots],\
                    rosters.loc[(rosters.fantasy_team == seeds[3]) & (rosters.until.isnull() | \
                    (rosters.until < int(settings['end_week'])))].iloc[:num_spots],\
                    ((semi_1.wins_x < semi_1.wins_y) & (semi_2.wins_x < semi_2.wins_y)).sum(),int(settings['end_week']))
                    consolation = matchup_sim(rosters.loc[(rosters.fantasy_team == seeds[0]) & \
                    (rosters.until.isnull() | (rosters.until < int(settings['end_week'])))].iloc[:num_spots],\
                    rosters.loc[(rosters.fantasy_team == seeds[1]) & (rosters.until.isnull() | \
                    (rosters.until < int(settings['end_week'])))].iloc[:num_spots],\
                    ((semi_1.wins_x < semi_1.wins_y) & (semi_2.wins_x < semi_2.wins_y)).sum(),int(settings['end_week']))
                winner[seeds[2]][0] += final.loc[final.wins_x >= final.wins_y].shape[0]
                winner[seeds[3]][0] += final.loc[final.wins_x < final.wins_y].shape[0]
                runner_up[seeds[3]][0] += final.loc[final.wins_x >= final.wins_y].shape[0]
                runner_up[seeds[2]][0] += final.loc[final.wins_x < final.wins_y].shape[0]
                third[seeds[0]][0] += consolation.loc[consolation.wins_x >= consolation.wins_y].shape[0]
                third[seeds[1]][0] += consolation.loc[consolation.wins_x < consolation.wins_y].shape[0]
        standings = pd.merge(left=standings.groupby('team').mean().reset_index(),\
        right=pd.DataFrame(winner).T.reset_index().rename(index=str,\
        columns={'index':'team',0:'winner'}),how='inner',on='team')
        standings['winner'] /= standings['winner'].sum()
        standings = pd.merge(left=standings.groupby('team').mean().reset_index(),\
        right=pd.DataFrame(runner_up).T.reset_index().rename(index=str,\
        columns={'index':'team',0:'runner_up'}),how='inner',on='team')
        standings['runner_up'] /= standings['runner_up'].sum()
        standings = pd.merge(left=standings.groupby('team').mean().reset_index(),\
        right=pd.DataFrame(third).T.reset_index().rename(index=str,\
        columns={'index':'team',0:'third'}),how='inner',on='team')
        standings['third'] /= standings['third'].sum()
        standings = standings.sort_values(by='winner',ascending=False)
        standings['earnings'] = standings['winner']*150 + standings['runner_up']*75 + standings['third']*25
    else:
        standings = standings.groupby('team').mean().reset_index()
        standings = standings.sort_values(by='wins',ascending=False)
    del standings['sim']
    return schedule_sim, standings

def possible_sits(rosters,schedule,num_sims=1000):
    refresh_oauth()
    my_team = teams.loc[teams.team_key == lg.team_key(),'name'].values[0]
    current = schedule.loc[(schedule.week == settings['current_week']) & \
    ((schedule.team_x == my_team) | (schedule.team_y == my_team))]
    matchup_sims = pd.DataFrame()
    matchups = pd.merge(left=team_sim(rosters.loc[(rosters.fantasy_team == current.iloc[0]['team_x']) & \
    (rosters.until.isnull() | (rosters.until < settings['current_week']))].iloc[:num_spots],num_sims,current.iloc[0]['week']),\
    right=team_sim(rosters.loc[(rosters.fantasy_team == current.iloc[0]['team_y']) & (rosters.until.isnull() | \
    (rosters.until < settings['current_week']))].iloc[:num_spots],num_sims,current.iloc[0]['week']),how='inner',on='sim')
    for stat in ['FGM','FGA','FTM','FTA','FG3M','PTS','REB','AST','STL','BLK','TOV']:
        matchups[stat + '_x'] += current.iloc[0][stat + '_x']
        matchups[stat + '_y'] += current.iloc[0][stat + '_y']
    matchups['FG%_x'] = matchups['FGM_x']/matchups['FGA_x']
    matchups['FG%_y'] = matchups['FGM_y']/matchups['FGA_y']
    matchups['FT%_x'] = matchups['FTM_x']/matchups['FTA_x']
    matchups['FT%_y'] = matchups['FTM_y']/matchups['FTA_y']
    matchups = convert_to_wins(matchups)
    matchups['win_prob_x'] = matchups['wins_x'] >= matchups['wins_y']
    matchups['win_prob_y'] = matchups['wins_x'] <= matchups['wins_y']
    matchups['player_to_sit'] = 'No one'
    matchup_sims = matchup_sims.append(matchups,ignore_index=True,sort=False)
    if settings['current_week'] < 11:
        schedule_inds = rosters.nba_team.apply(lambda x: (x,settings['current_week']) in nba_schedule.index)
    else:
        schedule_inds = rosters.nba_team.apply(lambda x: (x,settings['current_week'] + 1) in nba_schedule.index)
    my_players = rosters.loc[(rosters.fantasy_team == my_team) & \
    (rosters.until.isnull() | (rosters.until < settings['current_week'])) & schedule_inds]
    if my_players.shape[0] == 0:
        print('No players left to sit... Skipping...')
        return None
    for my_player in my_players.full_name:
        matchups = pd.merge(left=team_sim(rosters.loc[(rosters.fantasy_team == current.iloc[0]['team_x']) & \
        (rosters.until.isnull() | (rosters.until < settings['current_week'])) & \
        (rosters.full_name != my_player)].iloc[:num_spots],num_sims,current.iloc[0]['week']),\
        right=team_sim(rosters.loc[(rosters.fantasy_team == current.iloc[0]['team_y']) & (rosters.until.isnull() | \
        (rosters.until < settings['current_week'])) & (rosters.full_name != my_player)].iloc[:num_spots],\
        num_sims,current.iloc[0]['week']),how='inner',on='sim')
        for stat in ['FGM','FGA','FTM','FTA','FG3M','PTS','REB','AST','STL','BLK','TOV']:
            matchups[stat + '_x'] += current.iloc[0][stat + '_x']
            matchups[stat + '_y'] += current.iloc[0][stat + '_y']
        matchups['FG%_x'] = matchups['FGM_x']/matchups['FGA_x']
        matchups['FG%_y'] = matchups['FGM_y']/matchups['FGA_y']
        matchups['FT%_x'] = matchups['FTM_x']/matchups['FTA_x']
        matchups['FT%_y'] = matchups['FTM_y']/matchups['FTA_y']
        matchups = convert_to_wins(matchups)
        matchups['win_prob_x'] = matchups['wins_x'] >= matchups['wins_y']
        matchups['win_prob_y'] = matchups['wins_x'] <= matchups['wins_y']
        matchups['player_to_sit'] = my_player
        matchup_sims = matchup_sims.append(matchups,ignore_index=True,sort=False)
    if ((rosters.fantasy_team == my_team) & schedule_inds).any():
        if current.iloc[0]['team_x'] == my_team:
            matchups = pd.merge(left=team_sim(rosters.loc[(rosters.fantasy_team == current.iloc[0]['team_x']) & \
            (rosters.until.isnull() | (rosters.until < settings['current_week'])) & \
            schedule_inds].iloc[:num_spots],num_sims,current.iloc[0]['week']),\
            right=team_sim(rosters.loc[(rosters.fantasy_team == current.iloc[0]['team_y']) & (rosters.until.isnull() | \
            (rosters.until < settings['current_week'])) & (rosters.full_name != my_player)].iloc[:num_spots],\
            num_sims,current.iloc[0]['week']),how='inner',on='sim')
        else:
            matchups = pd.merge(left=team_sim(rosters.loc[(rosters.fantasy_team == current.iloc[0]['team_x']) & \
            (rosters.until.isnull() | (rosters.until < settings['current_week'])) & \
            (rosters.full_name != my_player)].iloc[:num_spots],num_sims,current.iloc[0]['week']),\
            right=team_sim(rosters.loc[(rosters.fantasy_team == current.iloc[0]['team_y']) & (rosters.until.isnull() | \
            (rosters.until < settings['current_week'])) & schedule_inds].iloc[:num_spots],\
            num_sims,current.iloc[0]['week']),how='inner',on='sim')
        for stat in ['FGM','FGA','FTM','FTA','FG3M','PTS','REB','AST','STL','BLK','TOV']:
            matchups[stat + '_x'] += current.iloc[0][stat + '_x']
            matchups[stat + '_y'] += current.iloc[0][stat + '_y']
        matchups['FG%_x'] = matchups['FGM_x']/matchups['FGA_x']
        matchups['FG%_y'] = matchups['FGM_y']/matchups['FGA_y']
        matchups['FT%_x'] = matchups['FTM_x']/matchups['FTA_x']
        matchups['FT%_y'] = matchups['FTM_y']/matchups['FTA_y']
        matchups = convert_to_wins(matchups)
        matchups['win_prob_x'] = matchups['wins_x'] >= matchups['wins_y']
        matchups['win_prob_y'] = matchups['wins_x'] <= matchups['wins_y']
        matchups['player_to_sit'] = 'Everyone'
        matchup_sims = matchup_sims.append(matchups,ignore_index=True,sort=False)
    x_or_y = '_x' if current.iloc[0]['team_x'] == my_team else '_y'
    cols = [col + x_or_y for col in ['FG%','FT%','FG3M','PTS','REB','AST','STL','BLK','TOV','wins','win_prob']]
    added_value = matchup_sims.groupby('player_to_sit')[cols].mean().reset_index()
    for my_player in my_players.full_name.tolist() + (['Everyone'] if 'Everyone' in added_value.player_to_sit.tolist() else []):
        for col in cols:
            added_value.loc[added_value.player_to_sit == my_player,col] -= added_value.loc[added_value.player_to_sit == 'No one',col].values[0]
    added_value = added_value.loc[added_value.player_to_sit != 'No one'].rename(columns={col:col.replace(x_or_y,'') for col in cols})
    return added_value

def possible_subs(rosters,available,schedule,num_sims=1000,focus_on=[],exclude=[],limit=20):
    refresh_oauth()
    my_team = teams.loc[teams.team_key == lg.team_key(),'name'].values[0]
    current = schedule.loc[(schedule.week == settings['current_week']) & \
    ((schedule.team_x == my_team) | (schedule.team_y == my_team))]
    matchup_sims = pd.DataFrame()
    matchups = pd.merge(left=team_sim(rosters.loc[(rosters.fantasy_team == current.iloc[0]['team_x']) & \
    (rosters.until.isnull() | (rosters.until < settings['current_week']))].iloc[:num_spots],num_sims,current.iloc[0]['week']),\
    right=team_sim(rosters.loc[(rosters.fantasy_team == current.iloc[0]['team_y']) & (rosters.until.isnull() | \
    (rosters.until < settings['current_week']))].iloc[:num_spots],num_sims,current.iloc[0]['week']),how='inner',on='sim')
    for stat in ['FGM','FGA','FTM','FTA','FG3M','PTS','REB','AST','STL','BLK','TOV']:
        matchups[stat + '_x'] += current.iloc[0][stat + '_x']
        matchups[stat + '_y'] += current.iloc[0][stat + '_y']
    matchups['FG%_x'] = matchups['FGM_x']/matchups['FGA_x']
    matchups['FG%_y'] = matchups['FGM_y']/matchups['FGA_y']
    matchups['FT%_x'] = matchups['FTM_x']/matchups['FTA_x']
    matchups['FT%_y'] = matchups['FTM_y']/matchups['FTA_y']
    matchups = convert_to_wins(matchups)
    matchups['win_prob_x'] = matchups['wins_x'] >= matchups['wins_y']
    matchups['win_prob_y'] = matchups['wins_x'] <= matchups['wins_y']
    matchups['player_to_add'] = 'No one'
    matchups['player_to_drop'] = 'No one'
    matchup_sims = matchup_sims.append(matchups,ignore_index=True,sort=False)
    my_players = rosters.loc[rosters.fantasy_team == my_team]
    if my_players.full_name.isin(focus_on).sum() > 0:
        my_players = my_players.loc[my_players.full_name.isin(focus_on)]
    elif my_players.full_name.isin(exclude).sum() > 0:
        my_players = my_players.loc[~my_players.full_name.isin(exclude)]
    if available.full_name.isin(focus_on).sum() > 0:
        possible = available.loc[available.full_name.isin(focus_on)]
    elif available.full_name.isin(exclude).sum() > 0:
        possible = available.loc[~available.full_name.isin(exclude)]
    else:
        possible = available
    for my_player in my_players.full_name:
        for free_agent in possible.iloc[:limit].full_name:
            new_rosters = rosters.loc[rosters.full_name != my_player].append(\
            available.loc[available.full_name == free_agent],ignore_index=True,sort=False)
            new_rosters.loc[new_rosters.full_name == free_agent,'fantasy_team'] = my_team
            matchups = pd.merge(left=team_sim(new_rosters.loc[(new_rosters.fantasy_team == current.iloc[0]['team_x']) & \
            (new_rosters.until.isnull() | (new_rosters.until < settings['current_week']))].iloc[:num_spots],num_sims,current.iloc[0]['week']),\
            right=team_sim(new_rosters.loc[(new_rosters.fantasy_team == current.iloc[0]['team_y']) & (new_rosters.until.isnull() | \
            (new_rosters.until < settings['current_week']))].iloc[:num_spots],num_sims,current.iloc[0]['week']),how='inner',on='sim')
            for stat in ['FGM','FGA','FTM','FTA','FG3M','PTS','REB','AST','STL','BLK','TOV']:
                matchups[stat + '_x'] += current.iloc[0][stat + '_x']
                matchups[stat + '_y'] += current.iloc[0][stat + '_y']
            matchups['FG%_x'] = matchups['FGM_x']/matchups['FGA_x']
            matchups['FG%_y'] = matchups['FGM_y']/matchups['FGA_y']
            matchups['FT%_x'] = matchups['FTM_x']/matchups['FTA_x']
            matchups['FT%_y'] = matchups['FTM_y']/matchups['FTA_y']
            matchups = convert_to_wins(matchups)
            matchups['win_prob_x'] = matchups['wins_x'] >= matchups['wins_y']
            matchups['win_prob_y'] = matchups['wins_x'] <= matchups['wins_y']
            matchups['player_to_add'] = free_agent
            matchups['player_to_drop'] = my_player
            matchup_sims = matchup_sims.append(matchups,ignore_index=True,sort=False)
    x_or_y = '_x' if current.iloc[0]['team_x'] == my_team else '_y'
    cols = [col + x_or_y for col in ['FG%','FT%','FG3M','PTS','REB','AST','STL','BLK','TOV','wins','win_prob']]
    added_value = matchup_sims.groupby(['player_to_add','player_to_drop'])[cols].mean().reset_index()
    for col in cols:
        added_value[col] -= added_value.loc[added_value.player_to_add == 'No one',col].values[0]
    added_value = added_value.loc[added_value.player_to_add != 'No one'].rename(columns={col:col.replace(x_or_y,'') for col in cols})
    return added_value

def possible_pickups(rosters,available,schedule,num_sims=1000,focus_on=[],exclude=[],limit=100):
    refresh_oauth()
    orig_standings = season_sim(schedule,rosters,num_sims)[1]
    added_value = pd.DataFrame()
    team_name = teams.loc[teams.team_key == lg.team_key(),'name'].values[0]
    my_players = rosters.loc[rosters.fantasy_team == team_name]
    if my_players.full_name.isin(focus_on).sum() > 0:
        my_players = my_players.loc[my_players.full_name.isin(focus_on)]
    elif my_players.full_name.isin(exclude).sum() > 0:
        my_players = my_players.loc[~my_players.full_name.isin(exclude)]
    if available.full_name.isin(focus_on).sum() > 0:
        possible = available.loc[available.full_name.isin(focus_on)]
    elif available.full_name.isin(exclude).sum() > 0:
        possible = available.loc[~available.full_name.isin(exclude)]
    else:
        possible = available
    for my_player in my_players.full_name:
        interest = possible.loc[possible.WAR >= rosters.loc[rosters.full_name == my_player,'WAR'].values[0] - 0.1]
        print(my_player + ': ' + str(interest.shape[0]) + ' comparable players')
        for free_agent in interest.iloc[:limit].full_name:
            print(free_agent)
            new_rosters = rosters.loc[rosters.full_name != my_player].append(\
            available.loc[available.full_name == free_agent],ignore_index=True,sort=False)
            new_rosters.loc[new_rosters.full_name == free_agent,'fantasy_team'] = team_name
            new_standings = season_sim(schedule,new_rosters,num_sims)[1]
            new_standings['player_to_drop'] = my_player
            new_standings['player_to_add'] = free_agent
            added_value = added_value.append(new_standings.loc[new_standings.team == team_name],ignore_index=True)
            print('Playoff Probability: ' + str(round(100*orig_standings.loc[orig_standings.team == team_name,'playoffs'].values[0],1)) + \
            '% --> ' + str(round(100*added_value.iloc[-1]['playoffs'],1)))
    for col in ['FG%','FT%','FG3M','PTS','REB','AST','STL','BLK','TOV','wins','playoffs']:
        added_value[col] -= orig_standings.loc[orig_standings.team == team_name,col].values[0]
        added_value[col] = round(added_value[col],4)
    added_value = added_value.sort_values(by='playoffs',ascending=False)
    return added_value

def possible_adds(rosters,available,schedule,num_sims=1000,focus_on=[],exclude=[],limit=100):
    refresh_oauth()
    orig_standings = season_sim(schedule,rosters,num_sims)[1]
    added_value = pd.DataFrame()
    team_name = teams.loc[teams.team_key == lg.team_key(),'name'].values[0]
    if available.full_name.isin(focus_on).sum() > 0:
        interest = available.loc[available.full_name.isin(focus_on)]
    elif available.full_name.isin(exclude).sum() > 0:
        interest = available.loc[~available.full_name.isin(exclude)]
    else:
        interest = available
    for free_agent in interest.iloc[:limit].full_name:
        print(free_agent)
        new_rosters = rosters.append(available.loc[available.full_name == free_agent],ignore_index=True,sort=False)
        new_rosters.loc[new_rosters.full_name == free_agent,'fantasy_team'] = team_name
        new_standings = season_sim(schedule,new_rosters,num_sims)[1]
        new_standings['player_to_add'] = free_agent
        added_value = added_value.append(new_standings.loc[new_standings.team == team_name],ignore_index=True)
        print('Playoff Probability: ' + str(round(100*orig_standings.loc[orig_standings.team == team_name,'playoffs'].values[0],1)) + \
        '% --> ' + str(round(100*added_value.iloc[-1]['playoffs'],1)))
    for col in ['FG%','FT%','FG3M','PTS','REB','AST','STL','BLK','TOV','wins','playoffs']:
        added_value[col] -= orig_standings.loc[orig_standings.team == team_name,col].values[0]
        added_value[col] = round(added_value[col],4)
    added_value = added_value.sort_values(by='playoffs',ascending=False)
    return added_value

def possible_drops(rosters,schedule,num_sims=1000,focus_on=[],exclude=[]):
    refresh_oauth()
    orig_standings = season_sim(schedule,rosters,num_sims)[1]
    reduced_value = pd.DataFrame()
    team_name = teams.loc[teams.team_key == lg.team_key(),'name'].values[0]
    my_players = rosters.loc[rosters.fantasy_team == team_name]
    if my_players.full_name.isin(focus_on).sum() > 0:
        my_players = my_players.loc[my_players.full_name.isin(focus_on)]
    elif my_players.full_name.isin(exclude).sum() > 0:
        my_players = my_players.loc[~my_players.full_name.isin(exclude)]
    for my_player in my_players.full_name:
        print(my_player)
        new_rosters = rosters.loc[rosters.full_name != my_player]
        new_standings = season_sim(schedule,new_rosters,num_sims)[1]
        new_standings['player_to_drop'] = my_player
        reduced_value = reduced_value.append(new_standings.loc[new_standings.team == team_name],ignore_index=True)
        print('Playoff Probability: ' + str(round(100*orig_standings.loc[orig_standings.team == team_name,'playoffs'].values[0],1)) + \
        '% --> ' + str(round(100*reduced_value.iloc[-1]['playoffs'],1)))
    for col in ['FG%','FT%','FG3M','PTS','REB','AST','STL','BLK','TOV','wins','playoffs']:
        reduced_value[col] -= orig_standings.loc[orig_standings.team == team_name,col].values[0]
        reduced_value[col] = round(reduced_value[col],4)
    reduced_value = reduced_value.sort_values(by='playoffs',ascending=False)
    return reduced_value

def possible_trades(rosters,schedule,num_sims=1000,focus_on=[],exclude=[],limit=100):
    refresh_oauth()
    orig_standings = season_sim(schedule,rosters,num_sims)[1]
    my_added_value = pd.DataFrame()
    my_team = teams.loc[teams.team_key == lg.team_key(),'name'].values[0]
    my_players = rosters.loc[rosters.fantasy_team == my_team]
    if my_players.full_name.isin(focus_on).sum() > 0:
        my_players = my_players.loc[my_players.full_name.isin(focus_on)]
    elif my_players.full_name.isin(exclude).sum() > 0:
        my_players = my_players.loc[~my_players.full_name.isin(exclude)]
    their_added_value = pd.DataFrame()
    their_players = rosters.loc[rosters.fantasy_team != my_team]
    if their_players.full_name.isin(focus_on).sum() > 0:
        their_players = their_players.loc[their_players.full_name.isin(focus_on)]
    elif their_players.full_name.isin(exclude).sum() > 0:
        their_players = their_players.loc[~their_players.full_name.isin(exclude)]
    for my_player in my_players.full_name:
        possible = their_players.loc[abs(their_players.WAR - my_players.loc[my_players.full_name == my_player,'WAR'].values[0]) <= 0.1]
        for their_player in possible.iloc[:limit].full_name:
            print(my_player + ' <--> ' + their_player)
            their_team = rosters.loc[rosters.full_name == their_player,'fantasy_team'].values[0]
            rosters.loc[rosters.full_name == my_player,'fantasy_team'] = their_team
            rosters.loc[rosters.full_name == their_player,'fantasy_team'] = my_team
            new_standings = season_sim(schedule,rosters,num_sims)[1]
            new_standings['player_to_trade_away'] = my_player
            new_standings['player_to_trade_for'] = their_player
            my_added_value = my_added_value.append(new_standings.loc[new_standings.team == my_team],ignore_index=True)
            their_added_value = their_added_value.append(new_standings.loc[new_standings.team == their_team],ignore_index=True)
            print('My Playoff Probability: ' + str(round(100*orig_standings.loc[orig_standings.team == my_team,'playoffs'].values[0],1)) + \
            '% --> ' + str(round(100*my_added_value.iloc[-1]['playoffs'],1)))
            print('Their Playoff Probability: ' + str(round(100*orig_standings.loc[orig_standings.team == their_team,'playoffs'].values[0],1)) + \
            '% --> ' + str(round(100*their_added_value.iloc[-1]['playoffs'],1)))
            rosters.loc[rosters.full_name == my_player,'fantasy_team'] = my_team
            rosters.loc[rosters.full_name == their_player,'fantasy_team'] = their_team
    for col in ['FG%','FT%','FG3M','PTS','REB','AST','STL','BLK','TOV','wins','playoffs']:
        my_added_value[col] -= orig_standings.loc[orig_standings.team == my_team,col].values[0]
        my_added_value[col] = round(my_added_value[col],4)
    for their_team in their_added_value.team.unique():
        for col in ['FG%','FT%','FG3M','PTS','REB','AST','STL','BLK','TOV','wins','playoffs']:
            their_added_value.loc[their_added_value.team == their_team,col] -= \
            orig_standings.loc[orig_standings.team == their_team,col].values[0]
            their_added_value[col] = round(their_added_value[col],4)
    for col in ['team','FG%','FT%','FG3M','PTS','REB','AST','STL','BLK','TOV','wins','playoffs']:
        my_added_value = my_added_value.rename(index=str,columns={col:'my_' + col})
        their_added_value = their_added_value.rename(index=str,columns={col:'their_' + col})
    added_value = pd.merge(left=my_added_value,right=their_added_value,\
    how='inner',on=['player_to_trade_away','player_to_trade_for'])
    added_value = added_value.sort_values(by='my_playoffs',ascending=False)
    return added_value

def excelAutofit(df,name,writer):
    f = writer.book.add_format()
    f.set_align('center')
    f.set_align('vcenter')
    m = writer.book.add_format({'num_format': '$0.00'})
    m.set_align('center')
    m.set_align('vcenter')
    p = writer.book.add_format({'num_format': '0.0%'})
    p.set_align('center')
    p.set_align('vcenter')
    df.to_excel(writer,sheet_name=name,index=False)
    for idx, col in enumerate(df):
        series = df[col]
        max_len = min(max((series.astype(str).map(len).max(),len(str(series.name)))) + 1,50)
        if 'earnings' in col:
            writer.sheets[name].set_column(idx,idx,max_len,m)
        elif 'per_game_' in col:
            writer.sheets[name].set_column(idx,idx,max_len,f,{'hidden':True})
        elif col.replace('my_','').replace('their_','') in ['playoffs','playoff_bye','winner','runner_up','third']:
            writer.sheets[name].set_column(idx,idx,max_len,p)
        else:
            writer.sheets[name].set_column(idx,idx,max_len,f)
    writer.sheets[name].autofilter('A1:' + (chr(64 + (df.shape[1] - 1)//26) + \
    chr(65 + (df.shape[1] - 1)%26)).replace('@','') + str(df.shape[0] + 1))
    return writer

def main():
    parser = optparse.OptionParser()
    parser.add_option('--earliest',action="store",dest="earliest",help="earliest week of stats being considered, e.g. 201807 corresponds to week 7 of the 2018 season")
    parser.add_option('--as_of',action="store",dest="as_of",help="week to project the season from, e.g. 201912 corresponds to week 12 of the 2019 season")
    parser.add_option('--name',action="store",dest="name",help="name of team to analyze in the case of multiple teams in a single season")
    parser.add_option('--games',action="store",dest="games",help="number of games to build each player's prior off of")
    parser.add_option('--simulations',action="store",dest="num_sims",help="number of season simulations")
    parser.add_option('--subs',action="store_true",dest="subs",help="whether to assess possible substitutions")
    parser.add_option('--sits',action="store_true",dest="sits",help="whether to assess possible benchings")
    parser.add_option('--pickups',action="store_true",dest="pickups",help="whether to assess possible free agent pickups")
    parser.add_option('--adds',action="store_true",dest="adds",help="whether to assess possible free agent adds")
    parser.add_option('--drops',action="store_true",dest="drops",help="whether to assess possible drops")
    parser.add_option('--trades',action="store_true",dest="trades",help="whether to assess possible trades")
    parser.add_option('--output',action="store",dest="output",help="path of output csv's")
    options,args = parser.parse_args()
    if not options.as_of:
        establish_oauth(season=latest_season,name=options.name)
        options.as_of = 100*latest_season + lg.current_week()
    else:
        establish_oauth(season=int(options.as_of)//100,name=options.name)
    if options.earliest == None:
        options.earliest = int(options.as_of) - 200 # Still working on optimal values
        if (options.earliest%100 == 0) | (options.earliest%100 > 50):
            options.earliest -= 80
    if options.games == None:
        options.games = 82 # Still working on optimal values
    if options.num_sims == None:
        options.num_sims = 10000
    if options.output == None:
        options.output = '.'
    if options.output[-1] != '/':
        options.output += '/'
    writer = pd.ExcelWriter(options.output + 'FantasyBasketballProjections.xlsx',engine='xlsxwriter')
    writer.book.add_format({'align': 'vcenter'})
    
    """ API skips injury statuses sometimes... """
    yahoo_players = pd.DataFrame({'status':[float('NaN')]})
    tries = 0
    while yahoo_players.status.isnull().all() and tries < 5:
        tries += 1
        yahoo_players = get_players()
        if yahoo_players.status.isnull().all() and tries < 5:
            print("Didn't pull injury statuses for some reason... " + \
            "Trying " + str(5 - tries) + " more time" + ("s" if tries < 4 else "") + "...")
            time.sleep(60)
        elif yahoo_players.status.isnull().all() and tries == 5:
            print("Still can't pull injury statuses... Rolling with it...")
    """ API skips injury statuses sometimes... """
    
    player_rates = get_rates(yahoo_players,int(options.earliest),int(options.as_of),int(options.num_sims),int(options.games))
    player_rates = get_WAR(player_rates,int(options.num_sims))
    try:
        injured = pd.read_csv("https://raw.githubusercontent.com/" + \
        "tefirman/FantasySports/master/FantasyBasketball_InjuredList.csv")
    except:
        injured = [player.split(',') for player in requests.get("https://raw.githubusercontent.com/" + \
        "tefirman/FantasySports/master/FantasyBasketball_InjuredList.csv",verify=False).text.split('\r')]
        injured = pd.DataFrame(injured[1:],columns=injured[0])
    player_rates = pd.merge(left=player_rates,right=injured,how='left',on=['full_name','nba_team'])
    newInjury = player_rates.status.isin(['O','INJ']) & \
    (player_rates.until.isnull() | (player_rates.until < settings['current_week'])) & \
    (~player_rates.fantasy_team.isnull() | (player_rates.WAR >= 0))
    if newInjury.sum() > 0:
        print('Need to look up new injuries... ' + ', '.join(player_rates.loc[newInjury,'full_name'].tolist()))
        player_rates.loc[newInjury,'until'] = settings['current_week']
    oldInjury = ~player_rates.status.isin(['O','INJ']) & (player_rates.until >= settings['current_week']) & \
    (~player_rates.fantasy_team.isnull() | (player_rates.WAR >= 0))
    if oldInjury.sum() > 0:
        print('Need to update old injuries... ' + ', '.join(player_rates.loc[oldInjury,'full_name'].tolist()))
        #player_rates.loc[oldInjury,'until'] = settings['current_week']
    
    rosters = player_rates.loc[~player_rates.fantasy_team.isnull()]
    writer = excelAutofit(rosters[[col for col in rosters.columns if '_rate' not in col \
    and col not in ['MIN_avg','MIN_std','player_key','player_id','uniform_number']]],'Rosters',writer)
    writer.sheets['Rosters'].freeze_panes(1,1)
    writer.sheets['Rosters'].conditional_format('K2:K' + str(rosters.shape[0] + 1),\
    {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
    available = player_rates.loc[player_rates.fantasy_team.isnull() & \
    ~player_rates.full_name.isin(['PG','SG','G','SF','PF','F','C','Util']) & \
    (player_rates.until.isnull() | (player_rates.until < 25))]
    del available['fantasy_team']
    writer = excelAutofit(available[[col for col in available.columns if '_rate' not in col \
    and col not in ['MIN_avg','MIN_std','player_key','player_id','uniform_number']]],'Available',writer)
    writer.sheets['Available'].freeze_panes(1,1)
    writer.sheets['Available'].conditional_format('K2:K' + str(available.shape[0] + 1),\
    {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
    
#    """ HARD CODING ROSTER CHANGES FOR POSSIBLE TRADES!!! """
#    rosters.loc[rosters.full_name.isin(['Ben Simmons','Serge Ibaka']),'fantasy_team'] = 'Mambo Mutombo'
#    rosters.loc[rosters.full_name.isin(['Hassan Whiteside','Ja Morant']),'fantasy_team'] = 'Trust the Process'
#    """ HARD CODING ROSTER CHANGES FOR POSSIBLE TRADES!!! """
    
    """ Need to figure out a way to test if given players can form a full lineup... Odds are good, but not 100%... """
    """ Ignoring it for now... Just assuming the best ten players can play together... """
    
    fantasy_schedule = get_schedule()
    schedule_sim, standings_sim = season_sim(fantasy_schedule,rosters,int(options.num_sims),True,True)
    writer = excelAutofit(schedule_sim,'Schedule',writer)
    writer = excelAutofit(standings_sim,'Standings',writer)
    writer.sheets['Schedule'].freeze_panes(1,3)
    writer.sheets['Schedule'].conditional_format('D2:E' + str(schedule_sim.shape[0] + 1),\
    {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
    writer.sheets['Standings'].freeze_panes(1,1)
    writer.sheets['Standings'].conditional_format('L2:O' + str(standings_sim.shape[0] + 1),\
    {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
    writer.sheets['Standings'].conditional_format('P2:P' + str(standings_sim.shape[0] + 1),\
    {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
    
    if options.subs:
        subs = possible_subs(rosters,available,fantasy_schedule,num_sims=1000,limit=20)
        writer = excelAutofit(subs,'Subs',writer)
        writer.sheets['Subs'].freeze_panes(1,1)
        writer.sheets['Subs'].conditional_format('L2:L' + str(subs.shape[0] + 1),\
        {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
    
    if options.sits:
        sits = possible_sits(rosters,fantasy_schedule,num_sims=1000)
        writer = excelAutofit(sits,'Sits',writer)
        writer.sheets['Sits'].freeze_panes(1,1)
        writer.sheets['Sits'].conditional_format('K2:K' + str(sits.shape[0] + 1),\
        {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
    
    if options.pickups:
        pickups = possible_pickups(rosters,available,fantasy_schedule,num_sims=1000,limit=20)
        pickups = pickups[pickups.columns[-2:].tolist() + pickups.columns[1:-2].tolist()]
        writer = excelAutofit(pickups,'Pickups',writer)
        writer.sheets['Pickups'].freeze_panes(1,2)
        writer.sheets['Pickups'].conditional_format('L2:M' + str(pickups.shape[0] + 1),\
        {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
    
    if options.adds:
        adds = possible_adds(rosters,available,fantasy_schedule,num_sims=1000,limit=20)
        adds = adds[adds.columns[-1:].tolist() + adds.columns[1:-1].tolist()]
        writer = excelAutofit(adds,'Adds',writer)
        writer.sheets['Adds'].freeze_panes(1,1)
        writer.sheets['Adds'].conditional_format('K2:L' + str(adds.shape[0] + 1),\
        {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
    
    if options.drops:
        drops = possible_drops(rosters,fantasy_schedule,num_sims=1000)
        drops = drops[drops.columns[-1:].tolist() + drops.columns[1:-1].tolist()]
        writer = excelAutofit(drops,'Drops',writer)
        writer.sheets['Drops'].freeze_panes(1,1)
        writer.sheets['Drops'].conditional_format('K2:L' + str(drops.shape[0] + 1),\
        {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
    
    if options.trades:
        trades = possible_trades(rosters,fantasy_schedule,num_sims=1000,limit=20)
        writer = excelAutofit(trades[['player_to_trade_away','player_to_trade_for',\
        'their_team','my_FG%','my_FT%','my_FG3M','my_PTS','my_REB','my_AST','my_STL',\
        'my_BLK','my_TOV','my_wins','my_playoffs','their_FG%','their_FT%','their_FG3M',\
        'their_PTS','their_REB','their_AST','their_STL','their_BLK','their_TOV',\
        'their_wins','their_playoffs']],'Trades',writer)
        writer.sheets['Trades'].freeze_panes(1,3)
        writer.sheets['Trades'].conditional_format('M2:N' + str(trades.shape[0] + 1),\
        {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
        writer.sheets['Trades'].conditional_format('X2:Y' + str(trades.shape[0] + 1),\
        {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
    
    writer.save()

if __name__ == "__main__":
    main()



