#!/usr/bin/env python
# -*-coding:utf-8 -*-
'''
@File    :   fantasybsb.py
@Time    :   2020/07/19 14:46:49
@Author  :   Taylor Firman
@Version :   1.0
@Contact :   tefirman@gmail.com
@Desc    :   Season-Long Fantasy Baseball Simulator
'''

import pandas as pd
import numpy as np
import datetime
import time
import os
import sportsref_mlb as mlb
from bs4 import BeautifulSoup
from pytz import timezone
import unidecode
import json
from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa
import optparse
import requests
latest_season = datetime.datetime.now().year

def get_starters(team):
    soup = BeautifulSoup(requests.get('https://www.fangraphs.com/teams/{}/schedule'.format(team)).text,'html.parser')
    games = soup.find('div',attrs={'class':'team-schedule-table'}).find_all('tr')
    columns = [col.text for col in games.pop(0).find_all('th')]
    schedule = pd.DataFrame()
    for game in games:
        entry = {}
        for ind in range(len(columns)):
            if columns[ind] == 'Opp':
                entry['opp_full'] = game.find_all('td')[ind].find('a').attrs['href'].split('/')[-1]
            entry[columns[ind]] = game.find_all('td')[ind].text
        schedule = pd.concat([schedule,pd.DataFrame(entry,index=[schedule.shape[0]])])
    schedule = schedule.rename(columns={'':'home_away','Opp':'opp',columns[7]:'starter','Opp Starter':'opp_starter'})
    schedule['team_full'] = team
    schedule['date'] = pd.to_datetime(schedule.Date.str.split(str(latest_season)).str[0] + str(latest_season))
    schedule = schedule[['date','team_full','home_away','opp','opp_full','starter','opp_starter']]
    starters = schedule.loc[schedule.starter != ''].drop_duplicates(subset='starter',keep='first').starter.tolist()
    while len(starters) < (schedule.starter == '').sum():
        starters += starters
    starters = starters[:(schedule.starter == '').sum()]
    schedule.loc[schedule.starter == '','starter'] = starters
    return schedule

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
    global mlb_schedule
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
    gm = yfa.Game(oauth,'mlb')
    while True:
        try:
            leagues = gm.yhandler.get_teams_raw()['fantasy_content']['users']['0']['user'][1]['games']
            break
        except:
            print('Teams query crapped out... Waiting 30 seconds and trying again...')
            time.sleep(30)
    for ind in range(leagues['count'] - 1,-1,-1):
        if type(leagues[str(ind)]['game']) == dict:
            continue
        if leagues[str(ind)]['game'][0]['code'] == 'mlb' and leagues[str(ind)]['game'][0]['season'] == str(latest_season):
            team = leagues[str(ind)]['game'][1]['teams']['0']['team'][0]
            lg_id = '.'.join([val['team_key'] for val in team if 'team_key' in val][0].split('.')[:3])
            break
    lg = gm.to_league(lg_id)
    rules = lg.yhandler.get_settings_raw(lg_id)['fantasy_content']['league'][1]['settings'][0]
    num_spots = sum([pos['roster_position']['count'] for pos in rules['roster_positions'] if pos['roster_position']['position'] != 'IL'])
    league_info = lg.yhandler.get_standings_raw(lg_id)['fantasy_content']['league']
    settings = lg.yhandler.get_settings_raw(lg_id)['fantasy_content']['league'][1]['settings'][0]
    teams_info = league_info[1]['standings'][0]['teams']
    teams = pd.DataFrame([{'team_key':teams_info[str(ind)]['team'][0][0]['team_key'],\
    'name':teams_info[str(ind)]['team'][0][2]['name']} for ind in range(teams_info['count'])])
    mlb_schedule = pd.DataFrame()
    for team in ['blue-jays','orioles','rays','red-sox','yankees','guardians',\
    'royals','tigers','twins','white-sox','angels','astros','athletics',\
    'mariners','rangers','braves','marlins','mets','nationals','phillies',\
    'brewers','cardinals','cubs','pirates','reds','diamondbacks','dodgers',\
    'giants','padres', 'rockies']:
        mlb_schedule = pd.concat([mlb_schedule,get_starters(team)]).reset_index(drop=True)
        time.sleep(4)
    mlb_schedule.loc[mlb_schedule.opp_full == 'cleveland','opp_full'] = 'guardians'
    mlb_schedule = pd.merge(left=mlb_schedule,right=mlb_schedule[['opp','opp_full']].drop_duplicates()\
    .rename(columns={'opp':'team','opp_full':'team_full'}),how='left',on='team_full')
    del mlb_schedule['opp_starter']
    mlb_schedule = pd.merge(left=mlb_schedule,right=mlb_schedule[['team','date','starter']]\
    .rename(columns={'team':'opp','starter':'opp_starter'}),how='left',on=['opp','date'])
    try:
        mlb_teams = pd.read_csv("https://raw.githubusercontent.com/" + \
        "tefirman/FantasySports/master/res/baseball/team_abbrevs.csv")
    except:
        mlb_teams = [team.split(',') for team in requests.get("https://raw.githubusercontent.com/" + \
        "tefirman/FantasySports/master/res/baseball/team_abbrevs.csv",verify=False).text.split('\r')]
        mlb_teams = pd.DataFrame(mlb_teams[1:],columns=mlb_teams[0])
    mlb_schedule = pd.merge(left=mlb_schedule,right=mlb_teams,how='inner',on='team')
    mlb_schedule = mlb_schedule.loc[mlb_schedule.date > datetime.datetime.now()].reset_index(drop=True)
    mlb_schedule.loc[mlb_schedule.starter.isin(['Shohei Ohtani','Michael Lorenzen','Brendan McKay']),'starter'] += ' (Pitcher)'
    mlb_schedule.loc[mlb_schedule.opp_starter.isin(['Shohei Ohtani','Michael Lorenzen','Brendan McKay']),'opp_starter'] += ' (Pitcher)'
#    mlb_schedule = mlb_schedule.loc[mlb_schedule.date < datetime.datetime(2022,7,1)].reset_index(drop=True)

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
        rosters = pd.concat([rosters,roster[['name','player_id','fantasy_team']]]).reset_index(drop=True)
    info = pd.DataFrame(columns=['player_key','player_id','full_name',\
    'editorial_team_abbr','uniform_number','eligible_positions','position_type','status'])
    for page_ind in range(120):
        while True:
            try:
                page = lg.yhandler.get_players_raw(lg.league_id,page_ind*25,'')['fantasy_content']['league'][1]['players']
                break
            except:
                print('Page #' + str(page_ind) + ' messed up... Waiting 30 seconds and trying again...')
                time.sleep(30)
        if type(page) == list:
            break
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
            info = pd.concat([info,pd.DataFrame(vals)])
    info.editorial_team_abbr = info.editorial_team_abbr.str.upper()
    info.loc[info.uniform_number == '','uniform_number'] = '0'
    info[['player_id','uniform_number']] = info[['player_id','uniform_number']].astype(int)
    info = pd.merge(left=info.reset_index(drop=True),right=rosters.rename(index=str,\
    columns={'name':'full_name'}),how='left',on=['full_name','player_id'])
    return info

def get_standings():
    refresh_oauth()
    translation = pd.DataFrame([{'stat_id':stat['stat']['stat_id'],\
    'display_name':stat['stat']['display_name']} for stat in settings['stat_categories']['stats']])
    translation = pd.concat([translation,pd.DataFrame({'stat_id':[1],'display_name':['GP']})]).reset_index(drop=True)
    tm = lg.to_team(teams.team_key.iloc[0])
    standings_data = tm.yhandler.get_standings_raw(lg_id)['fantasy_content']['league'][1]['standings'][0]['teams']
    vals = []
    for ind in range(standings_data['count']):
        name = [val['name'] for val in standings_data[str(ind)]['team'][0] if 'name' in val][0]
        for stat in standings_data[str(ind)]['team'][1]['team_stats']['stats']:
            vals.append({'name':name,'stat_id':int(stat['stat']['stat_id']),'value':stat['stat']['value']})
    standings = pd.merge(left=pd.DataFrame(vals),right=translation,how='inner',on='stat_id')
    standings = standings.groupby(['name','display_name']).value.sum().unstack().reset_index().rename(columns={'name':'fantasy_team'})
    return standings

def season_sim(rosters,current=None,pas_per_game=4,num_sims=1000):
    refresh_oauth()
    if type(current) != pd.DataFrame:
        while True:
            try:
                current = get_standings().rename(columns={'K':'SO'})
                break
            except:
                print('Standings query crapped out... Waiting 30 seconds and trying again...')
                time.sleep(30)
        for col in current.columns:
            if col not in ['fantasy_team','H/AB']:
                current[col] = current[col].astype(float)
        if current['H/AB'].isin(['']).any():
            current['H/AB'] = round(current['GP']*pas_per_game*current['AVG']).astype(str) + \
            '/' + round(current['GP']*pas_per_game).astype(str)
        current['ER'] = round(current['ERA']*current['IP']/9.0)
    position_sched = pd.merge(left=rosters.loc[rosters.eligible_positions.apply(lambda x: 'P' not in x),\
    ['full_name','editorial_team_abbr','fantasy_team','WAR','until']],right=mlb_schedule,how='inner',on='editorial_team_abbr')
    position_sched = position_sched.loc[(position_sched.date > position_sched.until) | position_sched.until.isnull()].reset_index(drop=True)
    sims = pd.concat([position_sched]*num_sims).reset_index(drop=True)
    sims['sim'] = sims.index//position_sched.shape[0]
    sims['played'] = np.random.rand(sims.shape[0]) < 0.8
    sims = sims.loc[sims.played].sort_values(by='WAR',ascending=False)\
    .reset_index(drop=True).groupby(['sim','fantasy_team','date']).head(10)
    good_dates = sims.groupby(['sim','fantasy_team','date']).size().to_frame('games_played').reset_index()
    good_dates['cum_games_played'] = good_dates.groupby(['sim','fantasy_team']).games_played.cumsum()#.reset_index()
    good_dates = pd.merge(left=good_dates,right=current[['fantasy_team','GP']],how='inner',on='fantasy_team')
    good_dates = good_dates.loc[good_dates.cum_games_played + good_dates.GP < 1620,['sim','fantasy_team','date']]
    sims = pd.merge(left=sims,right=good_dates,how='inner',on=['sim','fantasy_team','date'])
    sims = sims.groupby(['sim','full_name','editorial_team_abbr','fantasy_team'])\
    .size().to_frame('games_played').reset_index()
    position_sims = pd.merge(left=rosters,right=sims,how='inner',on=['full_name','editorial_team_abbr','fantasy_team'])
    position_sims.games_played = position_sims.games_played.fillna(0.0)
    for event in ['1B','2B','3B','HR','BB','SB','R','RBI']:
        position_sims[event + '_rate'] = position_sims[event + '_rate'].fillna(0.0)
        position_sims['sim_' + event] = position_sims.apply(lambda x: \
        np.random.binomial(pas_per_game*x['games_played'],x[event + '_rate']),axis=1)
    position_sims['sim_H'] = position_sims[['sim_1B','sim_2B','sim_3B','sim_HR']].sum(axis=1)
    position_standings = position_sims.groupby(['fantasy_team','sim'])[['sim_H','sim_R','sim_RBI',\
    'sim_HR','sim_SB','sim_BB','games_played']].sum(numeric_only=True).reset_index()
    position_standings['sim_AB'] = pas_per_game*position_standings['games_played'] - position_standings['sim_BB']
    position_standings['sim_avg'] = position_standings['sim_H']/position_standings['sim_AB']
    starter_sched = pd.merge(left=rosters.loc[rosters.eligible_positions.apply(lambda x: 'P' in x),\
    ['full_name','editorial_team_abbr','fantasy_team','WAR','until']],right=mlb_schedule.rename(columns={'starter':'full_name'}),\
    how='inner',on=['full_name','editorial_team_abbr'])
    starter_sched = starter_sched.loc[(starter_sched.date > starter_sched.until) | starter_sched.until.isnull()].reset_index(drop=True)
    reliever_sched = pd.merge(left=rosters.loc[rosters.eligible_positions.apply(lambda x: 'P' in x) & \
    ~rosters.full_name.isin(mlb_schedule.starter.unique()),['full_name','editorial_team_abbr','fantasy_team','WAR','until']],\
    right=mlb_schedule,how='inner',on='editorial_team_abbr')
    reliever_sched = reliever_sched.loc[(reliever_sched.date > reliever_sched.until) | reliever_sched.until.isnull()].reset_index(drop=True)
    starter_sims = pd.concat([starter_sched]*num_sims).reset_index(drop=True)
    starter_sims['sim'] = starter_sims.index//starter_sched.shape[0]
    starter_sims['played'] = np.random.rand(starter_sims.shape[0]) < 0.8
    starter_sims['SP_RP'] = 'SP'
    reliever_sims = pd.concat([reliever_sched]*num_sims).reset_index(drop=True)
    reliever_sims['sim'] = reliever_sims.index//reliever_sched.shape[0]
    reliever_sims['played'] = np.random.rand(reliever_sims.shape[0]) < 0.25
    reliever_sims['SP_RP'] = 'RP'
    sims = pd.concat([starter_sims.loc[starter_sims.played],reliever_sims.loc[reliever_sims.played]]).sort_values(by='WAR',ascending=False)\
    .reset_index(drop=True).groupby(['sim','fantasy_team','date']).head(8)
    pitcher_sims = pd.merge(left=rosters,right=sims,how='inner',on=['full_name','editorial_team_abbr','fantasy_team'])
    pitcher_sims.pas_per_game = pitcher_sims.pas_per_game.fillna(0.0)
    pitcher_sims.loc[pitcher_sims.SP_RP == 'RP','pas_per_game'] = \
    pitcher_sims.loc[pitcher_sims.SP_RP == 'RP','pas_per_game'].apply(lambda x: max(x,6))
    pitcher_sims['sim_IP'] = round(pitcher_sims['pas_per_game'])*(1 - \
    pitcher_sims['BBA_rate'] - pitcher_sims['HA_rate'])/3
    good_dates = pitcher_sims.groupby(['sim','fantasy_team','date']).sim_IP.sum().reset_index()
    good_dates['cum_innings_pitched'] = good_dates.groupby(['sim','fantasy_team']).sim_IP.cumsum()
    good_dates = pd.merge(left=good_dates,right=current[['fantasy_team','IP']],how='inner',on='fantasy_team')
    good_dates = good_dates.loc[good_dates.cum_innings_pitched + good_dates.IP < 1400,['sim','fantasy_team','date']]
    pitcher_sims = pd.merge(left=pitcher_sims,right=good_dates,how='inner',on=['sim','fantasy_team','date'])
    pitcher_sims = pitcher_sims.groupby(['sim','full_name','editorial_team_abbr','fantasy_team'])\
    .size().to_frame('games_played').reset_index()
    pitcher_sims = pd.merge(left=rosters,right=pitcher_sims,\
    how='inner',on=['full_name','editorial_team_abbr','fantasy_team'])
    pitcher_sims.pas_per_game = pitcher_sims.pas_per_game.fillna(0.0)
    for event in ['SO','BBA','HA','HRA']:
        pitcher_sims[event + '_rate'] = pitcher_sims[event + '_rate'].fillna(0.0)
        pitcher_sims['sim_' + event] = pitcher_sims.apply(lambda x: \
        np.random.binomial(round(x['pas_per_game']*x['games_played']),x[event + '_rate']),axis=1)
    pitcher_sims['sim_IP'] = (round(pitcher_sims['pas_per_game']*pitcher_sims['games_played']) - \
    pitcher_sims['sim_BBA'] - pitcher_sims['sim_HA'])/3
    pitcher_sims['sim_2BA'] = pitcher_sims.apply(lambda x: np.round(0.2187*(x['sim_HA'] - x['sim_HRA'])),axis=1)
    pitcher_sims['sim_3BA'] = pitcher_sims.apply(lambda x: np.round(0.0234*(x['sim_HA'] - x['sim_HRA'] - x['sim_2BA'])),axis=1)
    pitcher_sims['sim_1BA'] = pitcher_sims['sim_HA'] - pitcher_sims['sim_HRA'] - pitcher_sims['sim_2BA'] - pitcher_sims['sim_3BA']
    pitcher_sims['sim_RA'] = (pitcher_sims['sim_HA'] + pitcher_sims['sim_BBA'])*(pitcher_sims['sim_1BA'] + 2*pitcher_sims['sim_2BA'] + \
    3*pitcher_sims['sim_3BA'] + 4*pitcher_sims['sim_HRA'])/round(pitcher_sims['pas_per_game']*pitcher_sims['games_played'])
    pitcher_sims.wins_per_game = pitcher_sims.wins_per_game.fillna(0.0)
    pitcher_sims.saves_per_game = pitcher_sims.saves_per_game.fillna(0.0)
    pitcher_sims['sim_W'] = pitcher_sims.apply(lambda x: np.random.binomial(x['games_played'],x['wins_per_game']),axis=1)
    pitcher_sims['sim_SV'] = pitcher_sims.apply(lambda x: np.random.binomial(x['games_played'],x['saves_per_game']),axis=1)
    pitcher_standings = pitcher_sims.groupby(['fantasy_team','sim'])\
    [['sim_HA','sim_IP','sim_RA','sim_BBA','sim_SO','sim_W','sim_SV']].sum().reset_index()
    pitcher_standings['sim_WHIP'] = (pitcher_standings['sim_HA'] + \
    pitcher_standings['sim_BBA'])/pitcher_standings['sim_IP']
    pitcher_standings['sim_ERA'] = pitcher_standings['sim_RA']/pitcher_standings['sim_IP']*9
    standings = pd.merge(left=position_standings,right=pitcher_standings,how='inner',on=['fantasy_team','sim'])
    standings = pd.merge(left=standings,right=current,how='inner',on='fantasy_team')
    standings['points_total'] = 0
    standings['earnings'] = 0
    for stat in ['R','RBI','HR','SB','avg','SO','WHIP','ERA','W','SV']:
        if stat == 'avg':
            standings['H'] = standings['H/AB'].str.split('/').str[0].astype(float)
            standings['AB'] = standings['H/AB'].str.split('/').str[-1].astype(float)
            standings['sim_avg'] = (standings['sim_H'] + standings['H'])/\
            (standings['sim_AB'] + standings['AB'])
        elif stat == 'WHIP':
            standings['sim_WHIP'] = (standings['sim_H'] + standings['sim_BB'] + \
            round(standings['WHIP']*standings['IP']))/(standings['sim_IP'] + standings['IP'])
        elif stat == 'ERA':
            standings['sim_ERA'] = (standings['sim_R'] + standings['ER'])/\
            (standings['sim_IP'] + standings['IP'])*9
        else:
            standings['sim_' + stat] += standings[stat]
        standings['points_' + stat] = standings.groupby(['sim'])['sim_' + stat].rank(ascending=stat not in ['WHIP','ERA'])
        standings = pd.merge(left=standings,right=standings.groupby('sim')['points_' + stat].max()\
        .reset_index().rename(columns={'points_' + stat:'max_points_' + stat}),how='inner',on='sim')
        standings['winner_' + stat] = standings['points_' + stat] == standings['max_points_' + stat]
        standings = pd.merge(left=standings,right=standings.loc[standings['winner_' + stat]]\
        .groupby('sim').size().to_frame('num_winners_' + stat).reset_index(),how='inner',on='sim')
        standings['winner_' + stat] = standings['winner_' + stat].astype(float)/standings['num_winners_' + stat]
        del standings['max_points_' + stat], standings['num_winners_' + stat]
        standings['earnings'] += standings['winner_' + stat]*100
        standings['points_total'] += standings['points_' + stat]
    
    # standings['sim_IP'] += standings['IP']

    standings['overall_rank'] = standings.groupby(['sim'])['points_total'].rank(ascending=False)
    standings = pd.merge(left=standings,right=standings.groupby('sim')['points_total'].max()\
    .reset_index().rename(columns={'points_total':'max_points_total'}),how='inner',on='sim')
    standings['winner'] = standings['points_total'] == standings['max_points_total']
    standings = pd.merge(left=standings,right=standings.loc[standings['winner']]\
    .groupby('sim').size().to_frame('num_winners').reset_index(),how='inner',on='sim')
    standings['winner'] = standings['winner'].astype(float)/standings['num_winners']
    del standings['max_points_total'], standings['num_winners']
    standings = pd.merge(left=standings,right=standings.sort_values(by='points_total',ascending=True)\
    .groupby('sim').head(11).groupby('sim')['points_total'].max().reset_index()\
    .rename(columns={'points_total':'second_points_total'}),how='inner',on='sim')
    standings['runner_up'] = standings['points_total'] == standings['second_points_total']
    standings = pd.merge(left=standings,right=standings.loc[standings['runner_up']]\
    .groupby('sim').size().to_frame('num_runners_up').reset_index(),how='inner',on='sim')
    standings['runner_up'] = standings['runner_up'].astype(float)/standings['num_runners_up']
    del standings['second_points_total'], standings['num_runners_up']
    standings = pd.merge(left=standings,right=standings.sort_values(by='points_total',ascending=True)\
    .groupby('sim').head(10).groupby('sim')['points_total'].max().reset_index()\
    .rename(columns={'points_total':'third_points_total'}),how='inner',on='sim')
    standings['third'] = standings['points_total'] == standings['third_points_total']
    standings = pd.merge(left=standings,right=standings.loc[standings['third']]\
    .groupby('sim').size().to_frame('num_thirds').reset_index(),how='inner',on='sim')
    standings['third'] = standings['third'].astype(float)/standings['num_thirds']
    del standings['third_points_total'], standings['num_thirds']
    standings['earnings'] += standings.winner*800 + standings.runner_up*400 + standings.third*200
    return standings.groupby('fantasy_team').mean(numeric_only=True).reset_index()

def matchup_sim(team_1,team_2,pas_per_game=4,games_per_week=6,num_sims=10000):
    for event in ['1B','2B','3B','HR','BB','SB','RBI','R']:
        team_1['sim_' + event] = team_1[event + '_rate'].apply(lambda x: \
        np.random.binomial(pas_per_game*games_per_week,x,size=num_sims))
        team_2['sim_' + event] = team_2[event + '_rate'].apply(lambda x: \
        np.random.binomial(pas_per_game*games_per_week,x,size=num_sims))
    team_1['sim_hits'] = team_1[['sim_1B','sim_2B','sim_3B','sim_HR']].sum(axis=1)
    team_1['sim_avg'] = team_1['sim_hits']/(pas_per_game*games_per_week - team_1['sim_BB'])
    team_2['sim_hits'] = team_2[['sim_1B','sim_2B','sim_3B','sim_HR']].sum(axis=1)
    team_2['sim_avg'] = team_2['sim_hits']/(pas_per_game*games_per_week - team_2['sim_BB'])
    wins_R = (team_1.sim_R.sum() > team_2.sim_R.sum()).sum()/num_sims
    wins_HR = (team_1.sim_HR.sum() > team_2.sim_HR.sum()).sum()/num_sims
    wins_SB = (team_1.sim_SB.sum() > team_2.sim_SB.sum()).sum()/num_sims
    wins_RBI = (team_1.sim_RBI.sum() > team_2.sim_RBI.sum()).sum()/num_sims
    wins_AVG = (team_1.sim_hits.sum()/(9*pas_per_game*games_per_week - team_1.sim_BB.sum()) > \
    team_2.sim_hits.sum()/(9*pas_per_game*games_per_week - team_2.sim_BB.sum())).sum()/num_sims
    wins = pd.DataFrame({'R_1':[wins_R],'HR_1':[wins_HR],'SB_1':[wins_SB],\
    'RBI_1':[wins_RBI],'AVG_1':[wins_AVG],'wins_1':[wins_R + wins_HR + wins_SB + wins_RBI + wins_AVG]})
    cols = wins.columns.tolist()
    for col in cols:
        wins[col.replace('_1','_2')] = (6 if col == 'wins_1' else 1) - wins[col]
    return wins

def get_rates_position(player_stats,min_starts=0,min_pas=3,pas_per_game=4,games_per_week=6,num_sims=10000):
    num_games = player_stats.groupby('name').size().to_frame('games_played').reset_index()
    player_stats = pd.merge(left=player_stats.groupby('name').sum(numeric_only=True).reset_index(),right=num_games,how='inner',on='name')
    player_stats = player_stats.loc[(player_stats.games_played >= min_starts) & (player_stats.PA >= min_pas)].reset_index(drop=True)
    player_stats.loc[player_stats.name.isin(['Shohei Ohtani','Michael Lorenzen','Brendan McKay']),'name'] += ' (Batter)'
    player_stats['1B'] = player_stats['H'] - player_stats['2B'] - \
    player_stats['3B'] - player_stats['HR']
    avg_player = player_stats[['1B','2B','3B','HR','BB','SB','RBI','R','PA']].sum().to_frame().T
    for ind in range(1,20):
        avg_player['name'] = ('Average' if ind < 10 else 'Opposing') + ' Player ' + str(ind%10 + 1)
        player_stats = pd.concat([player_stats,avg_player]).reset_index(drop=True)
    for event in ['1B','2B','3B','HR','BB','SB','RBI','R']:
        player_stats[event + '_rate'] = player_stats[event]/player_stats.PA
    opp = player_stats.loc[player_stats.name.str.contains('Opposing Player')].reset_index(drop=True)
    for player in player_stats.iloc[:-19].name:
        my_team = player_stats.loc[(player_stats.name == player) | player_stats.name.str.contains('Average Player')].reset_index(drop=True)
        wins = matchup_sim(my_team,opp,pas_per_game,games_per_week,num_sims)
        player_stats.loc[player_stats.name == player,'WAR_R'] = wins.R_1.values[0] - 0.5
        player_stats.loc[player_stats.name == player,'WAR_HR'] = wins.HR_1.values[0] - 0.5
        player_stats.loc[player_stats.name == player,'WAR_SB'] = wins.SB_1.values[0] - 0.5
        player_stats.loc[player_stats.name == player,'WAR_RBI'] = wins.RBI_1.values[0] - 0.5
        player_stats.loc[player_stats.name == player,'WAR_AVG'] = wins.AVG_1.values[0] - 0.5
    player_stats['WAR'] = player_stats.WAR_R + player_stats.WAR_HR + \
    player_stats.WAR_SB + player_stats.WAR_RBI + player_stats.WAR_AVG
    return player_stats

def get_rates_pitcher(player_stats,min_games=0,num_sims=10000):
    num_games = player_stats.groupby('name').size().to_frame('games_played').reset_index()
    player_stats = pd.merge(left=player_stats.groupby('name').sum(numeric_only=True).reset_index(),right=num_games,how='inner',on='name')
    player_stats = player_stats.rename(columns={'BB':'BBA','H':'HA','HR':'HRA'})
    player_stats = player_stats.loc[(player_stats.games_played >= min_games)].reset_index(drop=True)
    player_stats.loc[player_stats.name.isin(['Shohei Ohtani','Michael Lorenzen','Brendan McKay']),'name'] += ' (Pitcher)'
    avg_P = player_stats[['SO','BBA','HA','HRA','batters_faced','IP','W','SV','games_played']].sum().to_frame().T
    games_P = player_stats.games_played.mean()
    wins_P = player_stats.W.mean()
    saves_P = player_stats.SV.mean()
    batters_faced_P = player_stats.batters_faced.mean()
    for ind in range(16):
        avg_P['name'] = ('Average' if ind < 8 else 'Opposing') + ' P ' + str(ind%8 + 1)
        if ind > 0:
            player_stats = pd.concat([player_stats,avg_P]).reset_index(drop=True)
    for event in ['SO','BBA','HA','HRA']:
        player_stats[event + '_rate'] = player_stats[event]/player_stats.batters_faced
    player_stats['games_per_week'] = player_stats['games_played']/27
    player_stats['pas_per_game'] = player_stats['batters_faced']/player_stats['games_played']
    player_stats['wins_per_week'] = player_stats['W']/27
    player_stats['wins_per_game'] = player_stats['W']/player_stats['games_played']
    player_stats['saves_per_week'] = player_stats['SV']/27
    player_stats['saves_per_game'] = player_stats['SV']/player_stats['games_played']
    player_stats.loc[player_stats.name.str.contains('Average P ') | \
    player_stats.name.str.contains('Opposing P '),'games_per_week'] = games_P/27
    player_stats.loc[player_stats.name.str.contains('Average P ') | \
    player_stats.name.str.contains('Opposing P '),'pas_per_game'] = batters_faced_P/games_P
    player_stats.loc[player_stats.name.str.contains('Average P ') | \
    player_stats.name.str.contains('Opposing P '),'wins_per_week'] = wins_P/27
    player_stats.loc[player_stats.name.str.contains('Average P ') | \
    player_stats.name.str.contains('Opposing P '),'saves_per_week'] = saves_P/27
    player_stats['pas_per_game'] = player_stats['pas_per_game'].fillna(0.0)
    player_stats['games_per_week'] = player_stats['games_per_week'].fillna(0.0)
    for event in ['SO','BBA','HA','HRA']:
        player_stats[event + '_rate'] = player_stats[event + '_rate'].fillna(0.0)
        if (player_stats[event + '_rate'] > 1).any():
            player_stats = player_stats.loc[player_stats[event + '_rate'] <= 1].reset_index(drop=True)
        player_stats['sim_' + event] = player_stats.apply(lambda x: \
        np.random.binomial(round(x['pas_per_game']*x['games_per_week']),x[event + '_rate'],size=num_sims),axis=1)
    player_stats['sim_IP'] = (round(player_stats['pas_per_game']*player_stats['games_per_week']) - \
    player_stats['sim_BBA'] - player_stats['sim_HA'])/3
    player_stats['sim_2BA'] = player_stats.apply(lambda x: np.round(0.2187*(x['sim_HA'] - x['sim_HRA'])),axis=1)
    player_stats['sim_3BA'] = player_stats.apply(lambda x: np.round(0.0234*(x['sim_HA'] - x['sim_HRA'] - x['sim_2BA'])),axis=1)
    player_stats['sim_1BA'] = player_stats['sim_HA'] - player_stats['sim_HRA'] - player_stats['sim_2BA'] - player_stats['sim_3BA']
    player_stats['sim_RA'] = (player_stats['sim_HA'] + player_stats['sim_BBA'])*\
    (player_stats['sim_1BA'] + 2*player_stats['sim_2BA'] + 3*player_stats['sim_3BA'] + 4*player_stats['sim_HRA'])/\
    round(player_stats['pas_per_game']*player_stats['games_per_week'])
    player_stats['sim_W'] = player_stats.wins_per_week.apply(lambda x: np.random.poisson(lam=x,size=num_sims))
    player_stats['sim_SV'] = player_stats.saves_per_week.apply(lambda x: np.random.poisson(lam=x,size=num_sims))
    opp = player_stats.loc[player_stats.name.str.contains('Opposing P')]
    for player in player_stats.iloc[:-15].name:
        my_team = player_stats.loc[(player_stats.name == player) | player_stats.name.str.contains('Average P')]
        player_stats.loc[player_stats.name == player,'WAR_K'] = ((my_team.sim_SO.sum() > opp.sim_SO.sum()).sum()/num_sims - 0.5)
        player_stats.loc[player_stats.name == player,'WAR_WHIP'] = (((my_team.sim_HA.sum() + my_team.sim_BBA.sum())/my_team.sim_IP.sum() < \
        (opp.sim_HA.sum() + opp.sim_BBA.sum())/opp.sim_IP.sum()).sum()/num_sims - 0.5)
        player_stats.loc[player_stats.name == player,'WAR_ERA'] = ((9*my_team.sim_RA.sum()/my_team.sim_IP.sum() < \
        9*opp.sim_RA.sum()/opp.sim_IP.sum()).sum()/num_sims - 0.5)
        player_stats.loc[player_stats.name == player,'WAR_W'] = ((my_team.sim_W.sum() > opp.sim_W.sum()).sum()/num_sims - 0.5)
        player_stats.loc[player_stats.name == player,'WAR_SV'] = ((my_team.sim_SV.sum() > opp.sim_SV.sum()).sum()/num_sims - 0.5)
    player_stats['WAR'] = player_stats.WAR_K + player_stats.WAR_WHIP + \
    player_stats.WAR_ERA + player_stats.WAR_W + player_stats.WAR_SV
    return player_stats

def add_injuries(by_player):
    try:
        inj_proj = pd.read_csv("https://raw.githubusercontent.com/" + \
        "tefirman/FantasySports/master/res/baseball/injured_list.csv")
    except:
        inj_proj = [player.split(',') for player in requests.get("https://raw.githubusercontent.com/" + \
        "tefirman/FantasySports/master/res/baseball/injured_list.csv",verify=False).text.split('\r')]
        inj_proj = pd.DataFrame(inj_proj[1:],columns=inj_proj[0])
    inj_proj.until = pd.to_datetime(inj_proj.until)
    inj_proj = inj_proj.loc[inj_proj.until >= datetime.datetime.now()]
    by_player = pd.merge(left=by_player,right=inj_proj,how='left',on=['full_name','editorial_team_abbr'])
    by_player.loc[by_player.status.isin(['DTD']) & by_player.until.isnull(),'until'] = datetime.datetime.now() + datetime.timedelta(days=1)
    # newInjury = by_player.status.isin(['IL15','IL10','IL7','COVID-19','IL60','NA','SUSP']) & \
    # by_player.until.isnull() & (~by_player.fantasy_team.isnull() | (by_player.WAR >= -0.4))
    newInjury = by_player.status.isin(['IL15','IL10','IL7','COVID-19','IL60','NA','SUSP']) & \
    by_player.until.isnull() & (~by_player.fantasy_team.isnull() | (by_player.pct_owned >= 0.1))
    if newInjury.sum() > 0:
        print('Need to look up new injuries... ' + ', '.join(by_player.loc[newInjury,'full_name'].tolist()))
        by_player.loc[newInjury & by_player.status.isin(['IL10','IL7','COVID-19','NA']),'until'] = datetime.datetime.now() + datetime.timedelta(days=10)
        by_player.loc[newInjury & by_player.status.isin(['IL15']),'until'] = datetime.datetime.now() + datetime.timedelta(days=20)
        by_player.loc[newInjury & by_player.status.isin(['IL60','SUSP']),'until'] = datetime.datetime.now() + datetime.timedelta(days=60)
    # oldInjury = ~by_player.status.isin(['DTD','IL15','IL10','IL7','COVID-19','IL60','NA','SUSP']) & ~by_player.until.isnull() & \
    # (~by_player.fantasy_team.isnull() | (by_player.WAR >= -0.4))
    oldInjury = ~by_player.status.isin(['DTD','IL15','IL10','IL7','COVID-19','IL60','NA','SUSP']) & ~by_player.until.isnull() & \
    (~by_player.fantasy_team.isnull() | (by_player.pct_owned >= 0.1))
    if oldInjury.sum() > 0:
        print('Need to update old injuries... ' + ', '.join(by_player.loc[oldInjury,'full_name'].tolist()))
    return by_player

def add_ownership(players,inc=25):
    refresh_oauth()
    ownership = pd.DataFrame()
    for ind in range(players.shape[0]//inc + 1):
        while True:
            try:
                refresh_oauth()
                
                if players.iloc[inc*ind:inc*(ind + 1)].shape[0] == 0:
                    break
                pcts = lg.yhandler.get("league/{}/players;player_keys=422.p.{}/percent_owned".format(lg_id,\
                ',422.p.'.join(players.iloc[inc*ind:inc*(ind + 1)].player_id.astype(str).tolist())))\
                ['fantasy_content']['league'][1]['players']
                break
            except:
                print('Ownership query crapped out... Waiting 30 seconds and trying again...')
                time.sleep(30)
        for player_ind in range(pcts['count']):
            player = pcts[str(player_ind)]['player']
            player_id = [int(val['player_id']) for val in player[0] if 'player_id' in val]
            full_name = [val['name']['full'] for val in player[0] if 'name' in val]
            pct_owned = [float(val['value'])/100.0 for val in player[1]['percent_owned'] if 'value' in val]
            if len(pct_owned) == 0:
                #print("Can't find ownership percentage for {}...".format(full_name))
                pct_owned = [0.0]
            ownership = pd.concat([ownership,pd.DataFrame({'player_id':player_id,\
            'full_name':full_name,'pct_owned':pct_owned})]).reset_index(drop=True)
    ownership.full_name = ownership.full_name.apply(unidecode.unidecode)
    players = pd.merge(left=players,right=ownership,how='left',on=['player_id','full_name'])
    players.pct_owned = players.pct_owned.fillna(0.0)
    return players

def possible_pickups(rosters,available,team_name,focus_on=[],exclude=[],\
position=None,min_owner=0.1,limit=10,pas_per_game=4):
    refresh_oauth()
    while True:
        try:
            current = get_standings().rename(columns={'K':'SO'})
            break
        except:
            print('Standings query crapped out... Waiting 30 seconds and trying again...')
            time.sleep(30)
    for col in current.columns:
        if col not in ['fantasy_team','H/AB']:
            current[col] = current[col].astype(float)
    if current['H/AB'].isin(['']).any():
        current['H/AB'] = round(current['GP']*pas_per_game*current['AVG']).astype(str) + \
        '/' + round(current['GP']*pas_per_game).astype(str)
    current['ER'] = round(current['ERA']*current['IP']/9.0)
    orig_standings = season_sim(rosters,current)
    added_value = pd.DataFrame()
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
    
    possible = possible.loc[(possible.until.dt.month < 10) | possible.until.isnull()]
    if possible.eligible_positions.apply(lambda x: str(position).replace('UTIL','Util') in x).any():
        possible = possible.loc[possible.eligible_positions.apply(lambda x: str(position).replace('UTIL','Util') in x)]
    for my_player in my_players.full_name.iloc[::-1]:
        interest = possible.loc[(possible.pct_owned >= min_owner)]
        print(my_player + ': ' + str(interest.shape[0]) + ' comparable players')
        interest = pd.concat([interest.loc[interest.eligible_positions.apply(lambda x: 'Util' in x)].iloc[:limit],\
        interest.loc[interest.eligible_positions.apply(lambda x: 'P' in x)].iloc[:limit]]).reset_index(drop=True)
        for free_agent in interest.full_name:
            print(free_agent + ', ' + str(datetime.datetime.now()))
            new_rosters = pd.concat([rosters.loc[rosters.full_name != my_player],\
            available.loc[available.full_name == free_agent]]).reset_index(drop=True)
            new_rosters.loc[new_rosters.full_name == free_agent,'fantasy_team'] = team_name
            new_standings = season_sim(new_rosters,current)
            new_standings['player_to_drop'] = my_player
            new_standings['player_to_add'] = free_agent
            added_value = pd.concat([added_value,new_standings.loc[new_standings.fantasy_team == team_name]]).reset_index(drop=True)
            print('Earnings Change: $' + str(round(orig_standings.loc[orig_standings.fantasy_team == team_name,'earnings'].values[0],2)) + \
            ' --> $' + str(round(added_value.iloc[-1]['earnings'],2)))
    for col in ['R','HR','RBI','SB','avg','W','SV','SO','ERA','WHIP']:
        added_value['winner_' + col] -= orig_standings.loc[orig_standings.fantasy_team == team_name,'winner_' + col].values[0]
        added_value['winner_' + col] = round(added_value['winner_' + col],4)
    for col in ['winner','runner_up','third','earnings']:
        added_value[col] -= orig_standings.loc[orig_standings.fantasy_team == team_name,col].values[0]
        added_value[col] = round(added_value[col],4)
    added_value = added_value.sort_values(by='earnings',ascending=False)
    return added_value

def possible_adds(rosters,available,team_name,focus_on=[],exclude=[],\
position=None,min_owner=0.1,limit=10,pas_per_game=4):
    refresh_oauth()
    while True:
        try:
            current = get_standings().rename(columns={'K':'SO'})
            break
        except:
            print('Standings query crapped out... Waiting 30 seconds and trying again...')
            time.sleep(30)
    for col in current.columns:
        if col not in ['fantasy_team','H/AB']:
            current[col] = current[col].astype(float)
    if current['H/AB'].isin(['']).any():
        current['H/AB'] = round(current['GP']*pas_per_game*current['AVG']).astype(str) + \
        '/' + round(current['GP']*pas_per_game).astype(str)
    current['ER'] = round(current['ERA']*current['IP']/9.0)
    orig_standings = season_sim(rosters,current)
    added_value = pd.DataFrame()
    if available.full_name.isin(focus_on).sum() > 0:
        interest = available.loc[available.full_name.isin(focus_on)]
    elif available.full_name.isin(exclude).sum() > 0:
        interest = available.loc[~available.full_name.isin(exclude)]
    else:
        interest = available
    interest = interest.loc[(interest.until < datetime.datetime(datetime.datetime.now().year,10,1)) | interest.until.isnull()]
    if interest.eligible_positions.apply(lambda x: str(position).replace('UTIL','Util') in x).any():
        interest = interest.loc[interest.eligible_positions.apply(lambda x: str(position).replace('UTIL','Util') in x)]
    interest = interest.loc[interest.pct_owned >= min_owner]
    interest = pd.concat([interest.loc[interest.eligible_positions.apply(lambda x: 'Util' in x)].iloc[:limit],\
    interest.loc[interest.eligible_positions.apply(lambda x: 'P' in x)].iloc[:limit]]).reset_index(drop=True)
    for free_agent in interest.full_name:
        print(free_agent + ', ' + str(datetime.datetime.now()))
        new_rosters = pd.concat([rosters,available.loc[available.full_name == free_agent]]).reset_index(drop=True)
        new_rosters.loc[new_rosters.full_name == free_agent,'fantasy_team'] = team_name
        new_standings = season_sim(new_rosters,current)
        new_standings['player_to_add'] = free_agent
        added_value = pd.concat([added_value,new_standings.loc[new_standings.fantasy_team == team_name]]).reset_index(drop=True)
        print('Earnings Change: $' + str(round(orig_standings.loc[orig_standings.fantasy_team == team_name,'earnings'].values[0],2)) + \
        ' --> $' + str(round(added_value.iloc[-1]['earnings'],2)))
    for col in ['R','HR','RBI','SB','avg','W','SV','SO','ERA','WHIP']:
        added_value['winner_' + col] -= orig_standings.loc[orig_standings.fantasy_team == team_name,'winner_' + col].values[0]
        added_value['winner_' + col] = round(added_value['winner_' + col],4)
    for col in ['winner','runner_up','third','earnings']:
        added_value[col] -= orig_standings.loc[orig_standings.fantasy_team == team_name,col].values[0]
        added_value[col] = round(added_value[col],4)
    added_value = added_value.sort_values(by='earnings',ascending=False)
    return added_value

def possible_drops(rosters,team_name,focus_on=[],exclude=[],pas_per_game=4):
    refresh_oauth()
    while True:
        try:
            current = get_standings().rename(columns={'K':'SO'})
            break
        except:
            print('Standings query crapped out... Waiting 30 seconds and trying again...')
            time.sleep(30)
    for col in current.columns:
        if col not in ['fantasy_team','H/AB']:
            current[col] = current[col].astype(float)
    if current['H/AB'].isin(['']).any():
        current['H/AB'] = round(current['GP']*pas_per_game*current['AVG']).astype(str) + \
        '/' + round(current['GP']*pas_per_game).astype(str)
    current['ER'] = round(current['ERA']*current['IP']/9.0)
    orig_standings = season_sim(rosters,current)
    reduced_value = pd.DataFrame()
    my_players = rosters.loc[rosters.fantasy_team == team_name]
    if my_players.full_name.isin(focus_on).sum() > 0:
        my_players = my_players.loc[my_players.full_name.isin(focus_on)]
    elif my_players.full_name.isin(exclude).sum() > 0:
        my_players = my_players.loc[~my_players.full_name.isin(exclude)]
    for my_player in my_players.full_name.iloc[::-1]:
        print(my_player + ', ' + str(datetime.datetime.now()))
        new_rosters = rosters.loc[rosters.full_name != my_player]
        new_standings = season_sim(new_rosters,current)
        # prev_val = rosters.loc[rosters.full_name == my_player,'until'].values[0]
        # rosters.loc[rosters.full_name == my_player,'until'] = datetime.datetime.now() + datetime.timedelta(days=2)
        # new_standings = season_sim(rosters,current)
        new_standings['player_to_drop'] = my_player
        reduced_value = pd.concat([reduced_value,new_standings.loc[new_standings.fantasy_team == team_name]]).reset_index(drop=True)
        print('Earnings Change: $' + str(round(orig_standings.loc[orig_standings.fantasy_team == team_name,'earnings'].values[0],2)) + \
        ' --> $' + str(round(reduced_value.iloc[-1]['earnings'],2)))
        # rosters.loc[rosters.full_name == my_player,'until'] = prev_val
    for col in ['R','HR','RBI','SB','avg','W','SV','SO','ERA','WHIP']:
        reduced_value['winner_' + col] -= orig_standings.loc[orig_standings.fantasy_team == team_name,'winner_' + col].values[0]
        reduced_value['winner_' + col] = round(reduced_value['winner_' + col],4)
    for col in ['winner','runner_up','third','earnings']:
        reduced_value[col] -= orig_standings.loc[orig_standings.fantasy_team == team_name,col].values[0]
        reduced_value[col] = round(reduced_value[col],4)
    reduced_value = reduced_value.sort_values(by='earnings',ascending=False)
    return reduced_value

def possible_trades(rosters,team_name,focus_on=[],exclude=[],given=[],drops=[],position=None,limit=100,pas_per_game=4):
    refresh_oauth()
    while True:
        try:
            current = get_standings().rename(columns={'K':'SO'})
            break
        except:
            print('Standings query crapped out... Waiting 30 seconds and trying again...')
            time.sleep(30)
    for col in current.columns:
        if col not in ['fantasy_team','H/AB']:
            current[col] = current[col].astype(float)
    if current['H/AB'].isin(['']).any():
        current['H/AB'] = round(current['GP']*pas_per_game*current['AVG']).astype(str) + \
        '/' + round(current['GP']*pas_per_game).astype(str)
    current['ER'] = round(current['ERA']*current['IP']/9.0)
    orig_standings = season_sim(rosters,current)
    my_added_value = pd.DataFrame()
    my_players = rosters.loc[rosters.fantasy_team == team_name]
    if my_players.full_name.isin(focus_on).sum() > 0:
        my_players = my_players.loc[my_players.full_name.isin(focus_on)]
    elif my_players.full_name.isin(exclude).sum() > 0:
        my_players = my_players.loc[~my_players.full_name.isin(exclude)]
    their_added_value = pd.DataFrame()
    their_players = rosters.loc[rosters.fantasy_team != team_name]
    if their_players.full_name.isin(focus_on).sum() > 0:
        their_players = their_players.loc[their_players.full_name.isin(focus_on)]
    elif their_players.full_name.isin(exclude).sum() > 0:
        their_players = their_players.loc[~their_players.full_name.isin(exclude)]
    if their_players.eligible_positions.apply(lambda x: str(position).replace('UTIL','Util') in x).any():
        their_players = their_players.loc[their_players.eligible_positions.apply(lambda x: str(position).replace('UTIL','Util') in x)]
    
    """ Make sure there are two teams and narrow down to that team!!! """
    if type(given) == list and their_players.loc[their_players.full_name.isin(given),'fantasy_team'].unique().shape[0] == 1:
        mine = [player for player in given if my_players.full_name.isin([player]).any()]
        theirs = [player for player in given if their_players.full_name.isin([player]).any()]
        their_team = rosters.loc[rosters.full_name.isin(theirs),'fantasy_team'].values[0]
        rosters.loc[rosters.full_name.isin(mine),'fantasy_team'] = their_team
        rosters.loc[rosters.full_name.isin(theirs),'fantasy_team'] = team_name
        my_players = my_players.loc[~my_players.full_name.isin(given)]
        their_players = their_players.loc[(their_players.fantasy_team == their_team) & ~their_players.full_name.isin(given)]
        my_players['WAR'] = 0.0
        their_players['WAR'] = 0.0
        if my_players.full_name.isin(drops).any() or their_players.full_name.isin(drops).any():
            rosters = rosters.loc[~rosters.full_name.isin(drops)].reset_index(drop=True)
    """ Make sure there are two teams and narrow down to that teams!!! """
    
    for my_player in my_players.full_name:
#        possible = their_players.loc[abs(their_players.WAR - my_players.loc[my_players.full_name == my_player,'WAR'].values[0]) <= 0.1]
        possible = their_players.loc[their_players.WAR - my_players.loc[my_players.full_name == my_player,'WAR'].values[0] > -float('inf')]
        for their_player in possible.iloc[:limit].full_name:
            print(my_player + ' <--> ' + their_player + ', ' + str(datetime.datetime.now()))
            their_team = rosters.loc[rosters.full_name == their_player,'fantasy_team'].values[0]
            rosters.loc[rosters.full_name == my_player,'fantasy_team'] = their_team
            rosters.loc[rosters.full_name == their_player,'fantasy_team'] = team_name
            new_standings = season_sim(rosters,current)
            new_standings['player_to_trade_away'] = my_player
            new_standings['player_to_trade_for'] = their_player
            my_added_value = pd.concat([my_added_value,new_standings.loc[new_standings.fantasy_team == team_name]]).reset_index(drop=True)
            their_added_value = pd.concat([their_added_value,new_standings.loc[new_standings.fantasy_team == their_team]]).reset_index(drop=True)
            print('My Earnings: ' + str(round(orig_standings.loc[orig_standings.fantasy_team == team_name,'earnings'].values[0],3)) + \
            ' --> ' + str(round(my_added_value.iloc[-1]['earnings'],3)))
            print('Their Earnings: ' + str(round(orig_standings.loc[orig_standings.fantasy_team == their_team,'earnings'].values[0],3)) + \
            ' --> ' + str(round(their_added_value.iloc[-1]['earnings'],3)))
            rosters.loc[rosters.full_name == my_player,'fantasy_team'] = team_name
            rosters.loc[rosters.full_name == their_player,'fantasy_team'] = their_team
    for col in ['R','HR','RBI','SB','avg','W','SV','SO','ERA','WHIP']:
        my_added_value['winner_' + col] -= orig_standings.loc[orig_standings.fantasy_team == team_name,'winner_' + col].values[0]
        my_added_value['winner_' + col] = round(my_added_value['winner_' + col],4)
    for their_team in their_added_value.fantasy_team.unique():
        for col in ['R','HR','RBI','SB','avg','W','SV','SO','ERA','WHIP']:
            their_added_value.loc[their_added_value.fantasy_team == their_team,'winner_' + col] -= \
            orig_standings.loc[orig_standings.fantasy_team == their_team,'winner_' + col].values[0]
            their_added_value['winner_' + col] = round(their_added_value['winner_' + col],4)
    for col in ['winner','runner_up','third','earnings']:
        my_added_value[col] -= orig_standings.loc[orig_standings.fantasy_team == team_name,col].values[0]
        my_added_value[col] = round(my_added_value[col],4)
    for their_team in their_added_value.fantasy_team.unique():
        for col in ['winner','runner_up','third','earnings']:
            their_added_value.loc[their_added_value.fantasy_team == their_team,col] -= \
            orig_standings.loc[orig_standings.fantasy_team == their_team,col].values[0]
            their_added_value[col] = round(their_added_value[col],4)
    for col in ['R','HR','RBI','SB','avg','W','SV','SO','ERA','WHIP']:
        my_added_value = my_added_value.rename(index=str,columns={'winner_' + col:'my_winner_' + col})
        their_added_value = their_added_value.rename(index=str,columns={'winner_' + col:'their_winner_' + col})
    for col in ['winner','runner_up','third','earnings']:
        my_added_value = my_added_value.rename(index=str,columns={col:'my_' + col})
        their_added_value = their_added_value.rename(index=str,columns={col:'their_' + col})
    added_value = pd.merge(left=my_added_value,right=their_added_value,\
    how='inner',on=['player_to_trade_away','player_to_trade_for'])
    added_value = added_value.sort_values(by='my_earnings',ascending=False)
    return added_value

def excelAutofit(df,name,writer,pcts=[],money=[],hidden=[]):
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
        writer.sheets[name].set_column(idx,idx,max_len,m if col in money \
        else (p if col in pcts else f),{'hidden':col in hidden})
    writer.sheets[name].autofilter('A1:' + (chr(64 + (df.shape[1] - 1)//26) + \
    chr(65 + (df.shape[1] - 1)%26)).replace('@','') + str(df.shape[0] + 1))
    return writer

def main():
    """ Initializing arguments """
    parser = optparse.OptionParser()
    parser.add_option('--earliest',action="store",dest="earliest",help="earliest season of stats being considered")
    parser.add_option('--season',action="store",dest="season",help="season to be analyzed")
    parser.add_option('--team_name',action="store",dest="team_name",help="name of team to be analyzed")
    parser.add_option('--simulations',action="store",dest="num_sims",help="number of season simulations")
    parser.add_option('--injurytries',action="store",dest="injurytries",help="number of times to try pulling injury statuses before rolling with it")
    parser.add_option('--pickups',action="store",dest="pickups",help='assess possible free agent pickups for the players specified ("all" will analyze all possible pickups)')
    parser.add_option('--adds',action="store",dest="adds",help='assess possible free agent adds for the players specified ("all" will analyze all possible adds)')
    parser.add_option('--drops',action="store_true",dest="drops",help="whether to assess possible drops")
    parser.add_option('--trades',action="store",dest="trades",help='assess possible trades for the players specified ("all" will analyze all possible trades)')
    parser.add_option('--output',action="store",dest="output",help="path of output csv's")
    options,args = parser.parse_args()
    if not options.season:
        options.season = datetime.datetime.now().year
    else:
        options.season = int(options.season)
    if not options.earliest:
        options.earliest = datetime.datetime.now() - datetime.timedelta(days=365)
    else:
        options.earliest = pd.to_datetime(options.earliest)
    if not options.team_name:
        options.team_name = "This Year's The Year"
    if not options.num_sims:
        options.num_sims = 1000
    if str(options.injurytries).isnumeric():
        options.injurytries = int(options.injurytries)
    else:
        options.injurytries = 5
    if not options.output:
        options.output = os.path.expanduser('~/Documents/') if os.path.exists(os.path.expanduser('~/Documents/')) else os.path.expanduser('~/')
        if not os.path.exists(options.output + options.team_name.replace(' ','').replace("'","")):
            os.mkdir(options.output + options.team_name.replace(' ','').replace("'",""))
        if not os.path.exists(options.output + options.team_name.replace(' ','').replace("'","") + '/' + str(datetime.datetime.now().year)):
            os.mkdir(options.output + options.team_name.replace(' ','').replace("'","") + '/' + str(datetime.datetime.now().year))
        options.output += options.team_name.replace(' ','').replace("'","") + '/' + str(datetime.datetime.now().year)
    if options.output[-1] != '/':
        options.output += '/'
    
    """ Downloading rosters """
    establish_oauth(options.season,options.team_name)
    """ API skips injury statuses sometimes... """
    yahoo_players = pd.DataFrame({'status':[float('NaN')]})
    tries = 0
    while yahoo_players.status.isnull().all() and tries < options.injurytries:
        tries += 1
        yahoo_players = get_players()
        if yahoo_players.status.isnull().all() and tries < options.injurytries:
            print("Didn't pull injury statuses for some reason... " + \
            "Trying " + str(options.injurytries - tries) + " more time" + \
            ("s" if tries < options.injurytries - 1 else "") + "...")
            establish_oauth()
            time.sleep(60)
        elif yahoo_players.status.isnull().all() and tries == options.injurytries:
            print("Still can't pull injury statuses... Rolling with it...")
    """ API skips injury statuses sometimes... """
    yahoo_players.full_name = yahoo_players.full_name.apply(unidecode.unidecode)
    yahoo_players = add_ownership(yahoo_players)
    
    """ Downloading game stats and calculating WAR """
    
    if os.path.exists('GameByGameFantasyBaseballBattingStats.csv'):
        batting = pd.read_csv('GameByGameFantasyBaseballBattingStats.csv',dtype={'game_id':str})
        pitching = pd.read_csv('GameByGameFantasyBaseballPitchingStats.csv',dtype={'game_id':str})
        batting.date = pd.to_datetime(batting.date)
        pitching.date = pd.to_datetime(pitching.date)
        if (datetime.datetime.now() - batting.date.max()).days > 1:
            new_batting,new_pitching = mlb.get_games(str(batting.date.max() + \
            datetime.timedelta(days=1)),str(datetime.datetime.now() - datetime.timedelta(days=1)))
            batting = pd.concat([batting,new_batting])
            pitching = pd.concat([pitching,new_pitching])
            batting.to_csv('GameByGameFantasyBaseballBattingStats.csv',index=False)
            pitching.to_csv('GameByGameFantasyBaseballPitchingStats.csv',index=False)
    else:
        batting,pitching = mlb.get_games(str(datetime.datetime.now() - \
        datetime.timedelta(days=365)),str(datetime.datetime.now() - datetime.timedelta(days=1)))

    batting = batting.loc[batting.date >= options.earliest].reset_index(drop=True)
    pitching = pitching.loc[pitching.date >= options.earliest].reset_index(drop=True)
    batting['name'] = batting.player.apply(unidecode.unidecode)
    batting_rates = get_rates_position(batting).rename(columns={'name':'full_name'})
    pitching['name'] = pitching.player.apply(unidecode.unidecode)
    pitching_rates = get_rates_pitcher(pitching).rename(columns={'name':'full_name'})

    players = pd.merge(left=yahoo_players,right=pd.concat([batting_rates,pitching_rates]).reset_index(drop=True)\
    [['full_name','1B_rate','2B_rate','3B_rate','HR_rate','BB_rate','SB_rate','RBI_rate',\
    'R_rate','SO_rate','BBA_rate','HA_rate','HRA_rate','pas_per_game',\
    'wins_per_game','saves_per_game','WAR_R','WAR_HR','WAR_SB','WAR_RBI',\
    'WAR_AVG','WAR_K','WAR_WHIP','WAR_ERA','WAR_W','WAR_SV','WAR']],how='left',on='full_name')
    
    players = players.sort_values(by='WAR',ascending=False)\
    .drop_duplicates(subset=['full_name','editorial_team_abbr','fantasy_team']).reset_index(drop=True)
    players = add_injuries(players)
    
    # # HOTFIX FOR POTENTIAL MOVE!!!
    # # players.loc[players.full_name.isin(['Grayson Rodriguez']),'fantasy_team'] = None
    # players.loc[players.full_name.isin(['Jordan Romano']),'fantasy_team'] = "AbeFroman"
    # players.loc[players.full_name.isin(['Freddie Freeman','Ty France']),'fantasy_team'] = "This Year's The Year"
    # # HOTFIX FOR POTENTIAL MOVE!!!

    """ Running season-long simulation """
    rosters = players.loc[~players.fantasy_team.isnull()].reset_index(drop=True)
    available = players.loc[players.fantasy_team.isnull()].reset_index(drop=True)
    del available['fantasy_team']
    standings_sim = season_sim(rosters,num_sims=options.num_sims)
    
    writer = pd.ExcelWriter(options.output + 'FantasyBaseballProjections_{}.xlsx'\
    .format(datetime.datetime.now().strftime('%m%d%y')),engine='xlsxwriter')
    writer.book.add_format({'align': 'vcenter'})
    
    for col in rosters.columns:
        if rosters[col].dtype == float:
            rosters[col] = round(rosters[col],3)
    writer = excelAutofit(rosters[[col for col in rosters.columns \
    if not col.endswith('_rate') and not col.endswith('_per_game') \
    and col not in ['player_key','player_id','uniform_number']]],'Rosters',writer,pcts=['pct_owned'])
    writer.sheets['Rosters'].freeze_panes(1,1)
    writer.sheets['Rosters'].conditional_format('R2:R' + str(rosters.shape[0] + 1),\
    {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
    for col in available.columns:
        if available[col].dtype == float:
            available[col] = round(available[col],3)
    writer = excelAutofit(available[[col for col in available.columns \
    if not col.endswith('_rate') and not col.endswith('_per_game') \
    and col not in ['player_key','player_id','uniform_number']]],'Available',writer,pcts=['pct_owned'])
    writer.sheets['Available'].freeze_panes(1,1)
    writer.sheets['Available'].conditional_format('Q2:Q' + str(available.shape[0] + 1),\
    {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
    for col in standings_sim.columns:
        if standings_sim[col].dtype == float:
            standings_sim[col] = round(standings_sim[col],3)
    
    writer = excelAutofit(standings_sim[['fantasy_team','games_played',\
    'sim_R','sim_HR','sim_RBI','sim_SB','sim_avg',\
    'sim_IP','sim_W','sim_SV','sim_SO','sim_ERA','sim_WHIP']]\
    .rename(columns={'games_played':'GP','sim_R':'R','sim_RBI':'RBI',\
    'sim_HR':'HR','sim_SB':'SB','sim_avg':'AVG','sim_IP':'IP',\
    'sim_W':'W','sim_SV':'SV','sim_SO':'K','sim_ERA':'ERA','sim_WHIP':'WHIP'}),'Stats',writer)
    writer = excelAutofit(standings_sim[['fantasy_team','points_R','points_HR',\
    'points_RBI','points_SB','points_avg','points_W','points_SV',\
    'points_SO','points_ERA','points_WHIP','overall_rank']].sort_values(by='overall_rank',ascending=True)\
    .rename(columns={'points_R':'R','points_RBI':'RBI','points_HR':'HR',\
    'points_SB':'SB','points_avg':'AVG','points_W':'W','points_SV':'SV',\
    'points_SO':'K','points_ERA':'ERA','points_WHIP':'WHIP'}),'Points',writer)
    writer = excelAutofit(standings_sim[['fantasy_team','winner_R','winner_HR',\
    'winner_RBI','winner_SB','winner_avg','winner_W','winner_SV',\
    'winner_SO','winner_ERA','winner_WHIP','winner','runner_up','third','earnings']]\
    .sort_values(by='earnings',ascending=False).rename(columns={'winner_R':'R',\
    'winner_RBI':'RBI','winner_HR':'HR','winner_SB':'SB',\
    'winner_avg':'AVG','winner_W':'W','winner_SV':'SV','winner_SO':'K',\
    'winner_ERA':'ERA','winner_WHIP':'WHIP'}),'Probabilities',writer,pcts=['R','HR',\
    'RBI','SB','AVG','W','SV','K','ERA','WHIP','winner','runner_up','third'],money=['earnings'])
    writer.sheets['Stats'].freeze_panes(1,1)
    writer.sheets['Points'].freeze_panes(1,1)
    writer.sheets['Probabilities'].freeze_panes(1,1)
    for col in range(67,78):
        writer.sheets['Stats'].conditional_format(chr(col) + '2:' + chr(col) + str(standings_sim.shape[0] + 1),\
        {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
    writer.sheets['Points'].conditional_format('B2:K' + str(standings_sim.shape[0] + 1),\
    {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
    writer.sheets['Points'].conditional_format('L2:L' + str(standings_sim.shape[0] + 1),\
    {'type':'3_color_scale','min_color':'#3CB371','mid_color':'#FFD700','max_color':'#FF6347'})
    writer.sheets['Probabilities'].conditional_format('B2:N' + str(standings_sim.shape[0] + 1),\
    {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
    writer.sheets['Probabilities'].conditional_format('O2:O' + str(standings_sim.shape[0] + 1),\
    {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
    
    if options.pickups:
        pickups = possible_pickups(rosters,available,options.team_name,limit=10,\
        exclude=['Luis Garcia'],focus_on=[val.strip() for val in options.pickups.split(',')] \
        if options.pickups.upper() not in ['ALL','SP','RP','P','C','1B','2B','3B','SS','OF','UTIL'] else [],\
        position=options.pickups.upper() if options.pickups.upper() in ['SP','RP','P','C','1B','2B','3B','SS','OF','UTIL'] else None)
        writer = excelAutofit(pickups[['player_to_drop','player_to_add','winner_R','winner_HR',\
        'winner_RBI','winner_SB','winner_avg','winner_W','winner_SV',\
        'winner_SO','winner_ERA','winner_WHIP','winner','runner_up','third','earnings']]\
        .sort_values(by='earnings',ascending=False).rename(columns={'winner_R':'R',\
        'winner_RBI':'RBI','winner_HR':'HR','winner_SB':'SB',\
        'winner_avg':'AVG','winner_W':'W','winner_SV':'SV','winner_SO':'K',\
        'winner_ERA':'ERA','winner_WHIP':'WHIP'}),'Pickups',writer,pcts=['R','HR','RBI','SB',\
        'AVG','W','SV','K','ERA','WHIP','winner','runner_up','third'],money=['earnings'])
        writer.sheets['Pickups'].freeze_panes(1,2)
        writer.sheets['Pickups'].conditional_format('C2:O' + str(pickups.shape[0] + 1),\
        {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
        writer.sheets['Pickups'].conditional_format('P2:P' + str(pickups.shape[0] + 1),\
        {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
    
    if options.adds:
        adds = possible_adds(rosters,available,options.team_name,limit=20,\
        exclude=['Luis Garcia'],focus_on=[val.strip() for val in options.adds.split(',')] \
        if options.adds.upper() not in ['ALL','SP','RP','P','C','1B','2B','3B','SS','OF','UTIL','IL'] else [],\
        position=options.adds.upper() if options.adds.upper() in ['SP','RP','P','C','1B','2B','3B','SS','OF','UTIL','IL'] else None)
        writer = excelAutofit(adds[['player_to_add','winner_R','winner_HR',\
        'winner_RBI','winner_SB','winner_avg','winner_W','winner_SV',\
        'winner_SO','winner_ERA','winner_WHIP','winner','runner_up','third','earnings']]\
        .sort_values(by='earnings',ascending=False).rename(columns={'winner_R':'R',\
        'winner_RBI':'RBI','winner_HR':'HR','winner_SB':'SB',\
        'winner_avg':'AVG','winner_W':'W','winner_SV':'SV','winner_SO':'K',\
        'winner_ERA':'ERA','winner_WHIP':'WHIP'}),'Adds',writer,pcts=['R','HR','RBI','SB',\
        'AVG','W','SV','K','ERA','WHIP','winner','runner_up','third'],money=['earnings'])
        writer.sheets['Adds'].freeze_panes(1,1)
        writer.sheets['Adds'].conditional_format('B2:N' + str(adds.shape[0] + 1),\
        {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
        writer.sheets['Adds'].conditional_format('O2:O' + str(adds.shape[0] + 1),\
        {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
    
    if options.drops:
        drops = possible_drops(rosters,options.team_name)
        writer = excelAutofit(drops[['player_to_drop','winner_R','winner_HR',\
        'winner_RBI','winner_SB','winner_avg','winner_W','winner_SV',\
        'winner_SO','winner_ERA','winner_WHIP','winner','runner_up','third','earnings']]\
        .sort_values(by='earnings',ascending=False).rename(columns={'winner_R':'R',\
        'winner_RBI':'RBI','winner_HR':'HR','winner_SB':'SB',\
        'winner_avg':'AVG','winner_W':'W','winner_SV':'SV','winner_SO':'K',\
        'winner_ERA':'ERA','winner_WHIP':'WHIP'}),'Drops',writer,pcts=['R','HR','RBI','SB',\
        'AVG','W','SV','K','ERA','WHIP','winner','runner_up','third'],money=['earnings'])
        writer.sheets['Drops'].freeze_panes(1,1)
        writer.sheets['Drops'].conditional_format('B2:N' + str(drops.shape[0] + 1),\
        {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
        writer.sheets['Drops'].conditional_format('O2:O' + str(drops.shape[0] + 1),\
        {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
    
    if options.trades:
        trades = possible_trades(rosters,options.team_name,limit=20,given=[],drops=[],\
        exclude=['Luis Garcia'],focus_on=[val.strip() for val in options.trades.split(',')] \
        if options.trades.upper() not in ['ALL','SP','RP','P','C','1B','2B','3B','SS','OF','UTIL'] else [],\
        position=options.trades.upper() if options.trades.upper() in ['SP','RP','P','C','1B','2B','3B','SS','OF','UTIL'] else None)
        writer = excelAutofit(trades[['player_to_trade_away','player_to_trade_for','fantasy_team_y',\
        'my_winner_R','my_winner_HR','my_winner_RBI','my_winner_SB',\
        'my_winner_avg','my_winner_W','my_winner_SV','my_winner_SO','my_winner_ERA',\
        'my_winner_WHIP','my_winner','my_runner_up','my_third','my_earnings','their_winner_R',\
        'their_winner_HR','their_winner_RBI','their_winner_SB',\
        'their_winner_avg','their_winner_W','their_winner_SV','their_winner_SO',\
        'their_winner_ERA','their_winner_WHIP','their_winner','their_runner_up','their_third',\
        'their_earnings']].sort_values(by='my_earnings',ascending=False)\
        .rename(columns={'fantasy_team_y':'fantasy_team','my_winner_R':'my_R','my_winner_RBI':'my_RBI','my_winner_HR':'my_HR',\
        'my_winner_SB':'my_SB','my_winner_avg':'my_AVG','my_winner_W':'my_W','my_winner_SV':'my_SV',\
        'my_winner_SO':'my_K','my_winner_ERA':'my_ERA','my_winner_WHIP':'my_WHIP','their_winner_R':'their_R',\
        'their_winner_RBI':'their_RBI','their_winner_HR':'their_HR','their_winner_SB':'their_SB',\
        'their_winner_avg':'their_AVG','their_winner_W':'their_W','their_winner_SV':'their_SV','their_winner_SO':'their_K',\
        'their_winner_ERA':'their_ERA','their_winner_WHIP':'their_WHIP'}),'Trades',writer,pcts=['my_R','my_HR','my_RBI','my_SB',\
        'my_AVG','my_W','my_SV','my_K','my_ERA','my_WHIP','my_winner','my_runner_up','my_third','their_R','their_HR','their_RBI',\
        'their_SB','their_AVG','their_W','their_SV','their_K','their_ERA','their_WHIP','their_winner',\
        'their_runner_up','their_third'],money=['my_earnings','their_earnings'])
        writer.sheets['Trades'].freeze_panes(1,2)
        writer.sheets['Trades'].conditional_format('D2:P' + str(trades.shape[0] + 1),\
        {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
        writer.sheets['Trades'].conditional_format('Q2:Q' + str(trades.shape[0] + 1),\
        {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
        writer.sheets['Trades'].conditional_format('R2:AD' + str(trades.shape[0] + 1),\
        {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
        writer.sheets['Trades'].conditional_format('AE2:AE' + str(trades.shape[0] + 1),\
        {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
    
    writer.close()
    os.system('touch -t {} {}'.format(datetime.datetime.now().strftime('%Y%m%d%H%M'),'/'.join(options.output.split('/')[:-2])))

if __name__ == "__main__":
    main()

