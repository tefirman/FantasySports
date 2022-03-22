#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Sep 11 10:51:38 2021

@author: tefirman
"""

import pandas as pd
import numpy as np
import datetime
from sportsreference.nfl.boxscore import Boxscore, Boxscores
import os
import requests
import json
import multiprocessing
import time
try:
    import emailcreds
except:
    print("Can't find email credentials... Email functionality won't work...")
    emailcreds = None
import smtplib, ssl
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import optparse
try:
    nfl_teams = pd.read_csv("https://raw.githubusercontent.com/" + \
    "tefirman/FantasySports/master/FantasyFootball_NFLTeams.csv")
except:
    nfl_teams = [team.split(',') for team in requests.get("https://raw.githubusercontent.com/" + \
    "tefirman/FantasySports/master/FantasyFootball_NFLTeams.csv",verify=False).text.split('\r')]
    nfl_teams = pd.DataFrame(nfl_teams[1:],columns=nfl_teams[0])
latest_season = datetime.datetime.now().year - int(datetime.datetime.now().month <= 7)

def get_settings(league_id,season,cookie_creds):
    global sched_settings
    global roster_map
    global roster_position
    global scoring
    global current_week
    global nfl_schedule
    settings_data = requests.get('https://fantasy.espn.com/apis/v3/games/ffl/seasons/' + \
    str(season) + '/segments/0/leagues/' + str(league_id) + '?view=mSettings',\
    cookies=cookie_creds).json()
    
    sched_settings = {}
    sched_settings['playoff_start_week'] = settings_data['settings']['scheduleSettings']['matchupPeriodCount'] + 1
    sched_settings['num_playoff_teams'] = settings_data['settings']['scheduleSettings']['playoffTeamCount']
    sched_settings['uses_playoff_reseeding'] = bool(settings_data['settings']['scheduleSettings']['playoffSeedingRuleBy'])
    
    roster_map = pd.DataFrame({0:'QB',1:'TQB',2:'RB',3:'RB/WR',4:'WR',5:'WR/TE',\
    6:'TE',7:'OP',8:'DT',9:'DE',10:'LB',11:'DL',12:'CB',13:'S',14:'DB',15:'DP',\
    16:'DEF',17:'K',18:'P',19:'HC',20:'BE',21:'IR',22:'',23:'RB/WR/TE'},\
    index=['position']).T.reset_index().rename(columns={'index':'pos_ind'})
    roster_position = pd.DataFrame(settings_data['settings']['rosterSettings']['lineupSlotCounts'],\
    index=['count']).T.reset_index().rename(columns={'index':'pos_ind'})
    roster_position.pos_ind = roster_position.pos_ind.astype(int)
    roster_position = pd.merge(left=roster_position,right=roster_map,how='inner',on='pos_ind')
    
    scoring = pd.DataFrame(settings_data['settings']['scoringSettings']['scoringItems'])
    scoring.pointsOverrides = scoring.pointsOverrides.apply(lambda x: x['16'] if '16' in x else float('NaN'))
    scoring.loc[~scoring.pointsOverrides.isnull(),'points'] = scoring.loc[~scoring.pointsOverrides.isnull(),'pointsOverrides']
    stats = pd.DataFrame({'statId':[3,4,19,20,24,25,26,42,43,44,53,72,77,80,85,\
    86,89,90,91,92,95,96,97,98,99,103,123,124,125,128,129,130,132,133,134,135,136,198,201,206,209],\
    'statName':['Pass Yds','Pass TD','Pass 2PT','Int Thrown','Rush Yds','Rush TD',\
    'Rush 2PT','Rec Yds','Rec TD','Rec 2PT','Rec','Fum Lost',\
    'FG 40-49 Yds','FG 0-19','Missed FG','PAT Made',\
    'Pts Allow 0','Pts Allow 1-6','Pts Allow 7-13','Pts Allow 14-20',\
    'Int','Fum Rec','Blocked Kick','Safety','Sack','Ret TD',\
    'Pts Allow 28-34','Pts Allow 35+','46+ Points Allowed',\
    'Less than 100 Yards Allowed','100-199 Yards Allowed','200-299 Yards Allowed',\
    '350-399 Yards Allowed','400-449 Yards Allowed','450-499 Yards Allowed',\
    '500-549 Yards Allowed','550+ Yards Allowed','FG 50-59 Yds','FG 60+ Yds',\
    '2Pt Return','1Pt Safety']})
    scoring = pd.merge(left=scoring,right=stats,how='left',on='statId')
    scoring.loc[scoring.statName.isnull() & (scoring.points == 6),'statName'] = 'Def TD'
    scoring = scoring[['statName','points']].drop_duplicates().rename(columns={'points':'value'})\
    .append(pd.DataFrame({'statName':['Ret Yds','Pts Allow 21-27'],'value':[0.0,0.0]}),\
    ignore_index=True,sort=False).set_index('statName')
    current_week = settings_data['status']['currentMatchupPeriod']
    nfl_schedule = pd.read_csv("https://projects.fivethirtyeight.com/nfl-api/nfl_elo.csv")
    nfl_schedule = nfl_schedule.loc[nfl_schedule.playoff.isnull(),\
    ['season','date','team1','team2','elo1_pre','elo2_pre','qb1_value_pre','qb2_value_pre']]\
    .rename(index=str,columns={'team1':'home_team','team2':'away_team','elo1_pre':'home_elo',\
    'elo2_pre':'away_elo','qb1_value_pre':'home_qb','qb2_value_pre':'away_qb'})
    nfl_schedule.date = pd.to_datetime(nfl_schedule.date,infer_datetime_format=True)
    nfl_schedule = pd.merge(left=nfl_schedule,right=nfl_schedule.groupby('season').date.min()\
    .reset_index().rename(columns={'date':'first_game'}),how='inner',on='season')
    nfl_schedule['week'] = (nfl_schedule.date - nfl_schedule.first_game).dt.days//7 + 1
    del nfl_schedule['first_game']
    if nfl_schedule.season.max() < season:
        """ If current season is not in the csv yet, pull schedule using SportsReference and last season's elos... """
        current_sched = pd.DataFrame()
        games = Boxscores(1,season,17).games
        for week in games.keys():
            week_games = pd.DataFrame(games[week])
            week_games['week'] = int(week.split('-')[0])
            current_sched = current_sched.append(week_games.drop_duplicates(),ignore_index=True,sort=False)
        current_sched['season'] = season
        current_sched['date'] = pd.to_datetime(current_sched.boxscore.str[:8],infer_datetime_format=True)
        current_sched['home_abbr'] = current_sched['home_abbr'].str.upper()
        current_sched['away_abbr'] = current_sched['away_abbr'].str.upper()
        current_sched = pd.merge(left=current_sched,right=nfl_teams.rename(columns={'real_abbrev':'home_abbr',\
        'fivethirtyeight':'home_team'}),how='inner',on='home_abbr')
        current_sched = pd.merge(left=current_sched,right=nfl_teams.rename(columns={'real_abbrev':'away_abbr',\
        'fivethirtyeight':'away_team'}),how='inner',on='away_abbr')
        """ Regress last seasons final team elos to the mean??? Merge in best QB from last season??? """
        prev_elos = nfl_schedule.loc[(nfl_schedule.season == season - 1) & (nfl_schedule.week == 17),\
        ['home_team','home_elo']].rename(columns={'home_team':'team','home_elo':'elo'})\
        .append(nfl_schedule.loc[(nfl_schedule.season == season - 1) & (nfl_schedule.week == 17),\
        ['away_team','away_elo']].rename(columns={'away_team':'team','away_elo':'elo'}),ignore_index=True,sort=False)
        prev_elos['elo'] += (1500 - prev_elos['elo'])*0.333 #Regression FiveThirtyEight uses...
        current_sched = pd.merge(left=current_sched,right=prev_elos[['team','elo']]\
        .rename(columns={'team':'home_team','elo':'home_elo'}),how='inner',on=['home_team'])
        current_sched = pd.merge(left=current_sched,right=prev_elos[['team','elo']]\
        .rename(columns={'team':'away_team','elo':'away_elo'}),how='inner',on=['away_team'])
        qb_elos = nfl_schedule.loc[nfl_schedule.season == season - 1,\
        ['home_team','home_qb']].rename(columns={'home_team':'team','home_qb':'qb_elo'})\
        .append(nfl_schedule.loc[(nfl_schedule.season == season - 1) & (nfl_schedule.week == 17),\
        ['away_team','away_qb']].rename(columns={'away_team':'team','away_qb':'qb_elo'}),ignore_index=True,sort=False)
        qb_elos = qb_elos.groupby('team').qb_elo.max().reset_index()
        current_sched = pd.merge(left=current_sched,right=qb_elos[['team','qb_elo']]\
        .rename(columns={'team':'home_team','qb_elo':'home_qb'}),how='inner',on=['home_team'])
        current_sched = pd.merge(left=current_sched,right=qb_elos[['team','qb_elo']]\
        .rename(columns={'team':'away_team','qb_elo':'away_qb'}),how='inner',on=['away_team'])
        nfl_schedule = nfl_schedule.append(current_sched[['season','week','date','home_team','away_team',\
        'home_elo','away_elo','home_qb','away_qb']],ignore_index=True,sort=False)
    nfl_schedule = pd.merge(left=nfl_schedule,right=nfl_teams[['fivethirtyeight','abbrev']],\
    left_on='home_team',right_on='fivethirtyeight',how='inner')
    nfl_schedule.loc[nfl_schedule.home_team != nfl_schedule.abbrev,'home_team'] = \
    nfl_schedule.loc[nfl_schedule.home_team != nfl_schedule.abbrev,'abbrev']
    del nfl_schedule['fivethirtyeight'], nfl_schedule['abbrev']
    nfl_schedule = pd.merge(left=nfl_schedule,right=nfl_teams[['fivethirtyeight','abbrev']],\
    left_on='away_team',right_on='fivethirtyeight',how='inner')
    nfl_schedule.loc[nfl_schedule.away_team != nfl_schedule.abbrev,'away_team'] = \
    nfl_schedule.loc[nfl_schedule.away_team != nfl_schedule.abbrev,'abbrev']
    del nfl_schedule['fivethirtyeight'], nfl_schedule['abbrev']
    home = nfl_schedule[['season','week','date','home_team','away_elo','home_qb']]\
    .rename(columns={'home_team':'abbrev','away_elo':'opp_elo','home_qb':'qb_elo'})
    home['home_away'] = 'Home'
    away = nfl_schedule[['season','week','date','away_team','home_elo','away_qb']]\
    .rename(columns={'away_team':'abbrev','home_elo':'opp_elo','away_qb':'qb_elo'})
    away['home_away'] = 'Away'
    nfl_schedule = home.append(away,ignore_index=True)
    nfl_schedule.opp_elo = 1500/nfl_schedule.opp_elo
    nfl_schedule.qb_elo = nfl_schedule.qb_elo/175
    nfl_schedule = nfl_schedule.sort_values(by=['season','week']).reset_index(drop=True)

def get_rosters(league_id,season,cookie_creds):
    roster_data = requests.get('https://fantasy.espn.com/apis/v3/games/ffl/seasons/' + \
    str(season) + '/segments/0/leagues/' + str(league_id) + '?view=mRoster',\
    cookies=cookie_creds).json()['teams']
    rosters = pd.DataFrame(columns=['team_id','player_id'])
    for roster in roster_data:
        rosters = rosters.append(pd.DataFrame([{'team_id':roster['id'],\
        'player_id':player['playerId'],'lineupSlotID':player['lineupSlotId']} \
        for player in roster['roster']['entries']]),ignore_index=True,sort=False)
    return rosters

def get_standings(league_id,season,cookie_creds):
    standings_data = requests.get('https://fantasy.espn.com/apis/v3/games/ffl/seasons/' + \
    str(season) + '/segments/0/leagues/' + str(league_id) + '?view=mTeam',\
    cookies=cookie_creds).json()['teams']
    standings = pd.DataFrame([{'abbrev':team['abbrev'],'fantasy_team':team['location'] + ' ' + team['nickname'],\
    'team_id':team['id'],'wins':team['record']['overall']['wins'],'losses':team['record']['overall']['losses'],\
    'ties':team['record']['overall']['ties']} for team in standings_data])
    standings['points'] = standings['wins']*2 + standings['ties']
    standings = standings.sort_values(by='points',ascending=False).reset_index(drop=True)
    return standings[['team_id','abbrev','fantasy_team','wins','losses','ties']]

def get_players(league_id,season,cookie_creds):
    url = 'https://fantasy.espn.com/apis/v3/games/ffl/seasons/{}/segments/0/leagues/{}/players'.format(season,league_id)
    params = {'view':['players_wl','mRoster']}
    headers = {'x-fantasy-filter':json.dumps({"filterActive":{"value":True}})}
    player_data = requests.get(url,params=params,headers=headers,cookies=cookie_creds)
    players = pd.DataFrame([player['player'] for player in player_data.json()])
    players = players.loc[~players.ownership.isnull()].reset_index(drop=True)
    players['pct_owned'] = players.ownership.apply(lambda x: x['percentOwned'])
    players = players.rename(columns={'id':'player_id','fullName':'name',\
    'proTeamId':'team_id','defaultPositionId':'position_ind','injuryStatus':'injury_status'})
    players = pd.merge(left=players,right=pd.DataFrame({'team_id':list(range(1,31)) + [33,34],\
    'editorial_team_abbr':['ATL','BUF','CHI','CIN','CLE','DAL','DEN','DET',\
    'GNB','TEN','IND','KAN','OAK','LAR','MIA','MIN','NWE','NOR','NYG','NYJ',\
    'PHI','ARI','PIT','LAC','SFO','SEA','TAM','WAS','CAR','JAX','BAL','HOU']}),how='inner',on='team_id')
    players = pd.merge(left=players,right=pd.DataFrame({'position_ind':[1,2,3,4,5,16],\
    'position':['QB','RB','WR','TE','K','DEF']}),how='left',on='position_ind')
    players = pd.merge(left=players,right=pd.DataFrame({'injury_status':['ACTIVE',\
    'INJURY_RESERVE','OUT','QUESTIONABLE','DOUBTFUL','SUSPENSION'],\
    'status':['','IR','O','Q','D','SUSP']}),how='left',on='injury_status')
    weird_status = players.status.isnull() & ~players.injury_status.isnull()
    if weird_status.any():
        print('New injury status: ' + ', '.join(players.loc[weird_status,'injury_status'].unique()))
        players.loc[weird_status,'status'] = players.loc[weird_status,'injury_status']
    players.status = players.status.fillna('')
    players = players.loc[players.universeId != 0].reset_index(drop=True)
    del players['team_id']
    players = pd.merge(left=pd.merge(left=players,right=get_rosters(league_id,season,cookie_creds),\
    how='left',on='player_id'),right=get_standings(league_id,season,cookie_creds)[['team_id','fantasy_team']],how='left',on='team_id')
    
    players = pd.merge(left=players,right=roster_map.rename(columns=\
    {'pos_ind':'lineupSlotID','position':'selected_position'}),how='left',on='lineupSlotID')
    
    return players[['player_id','name','position','editorial_team_abbr','fantasy_team','pct_owned','status','selected_position']]

def get_schedule(league_id,season,cookie_creds,team_name='Team Jacquet'):
    schedule_data = requests.get('https://fantasy.espn.com/apis/v3/games/ffl/seasons/' + \
    str(season) + '/segments/0/leagues/' + str(league_id) + '?view=mMatchup',\
    cookies=cookie_creds).json()
    schedule = pd.DataFrame()
    for ind in range(len(schedule_data['schedule'])):
        schedule = schedule.append(pd.DataFrame({'week':[schedule_data['schedule'][ind]['matchupPeriodId']],\
        'team_1_id':[schedule_data['schedule'][ind]['home']['teamId']],\
        'team_2_id':[schedule_data['schedule'][ind]['away']['teamId']] \
        if 'away' in schedule_data['schedule'][ind] else [float('NaN')],\
        'score_1':[sum([player['playerPoolEntry']['appliedStatTotal'] for player in \
        schedule_data['schedule'][ind]['home']['rosterForMatchupPeriod']['entries']]) \
        if schedule_data['schedule'][ind]['matchupPeriodId'] == current_week \
        else schedule_data['schedule'][ind]['home']['totalPoints']],\
        'score_2':[sum([player['playerPoolEntry']['appliedStatTotal'] for player in \
        schedule_data['schedule'][ind]['away']['rosterForMatchupPeriod']['entries']])\
        if schedule_data['schedule'][ind]['matchupPeriodId'] == current_week \
        else schedule_data['schedule'][ind]['away']['totalPoints']] \
        if 'away' in schedule_data['schedule'][ind] else [float('NaN')]}),ignore_index=True)
    standings = get_standings(league_id,season,cookie_creds)
    schedule = pd.merge(left=schedule,right=standings[['team_id','fantasy_team']]\
    .rename(columns={'team_id':'team_1_id','fantasy_team':'team_1'}),how='inner',on='team_1_id')
    schedule = pd.merge(left=schedule,right=standings[['team_id','fantasy_team']]\
    .rename(columns={'team_id':'team_2_id','fantasy_team':'team_2'}),how='inner',on='team_2_id')
    schedule = schedule.sort_values(by=['week','team_1']).reset_index(drop=True)
    switch = schedule.team_1 > schedule.team_2
    schedule.loc[switch,'temp'] = schedule.loc[switch,'team_1']
    schedule.loc[switch,'team_1'] = schedule.loc[switch,'team_2']
    schedule.loc[switch,'team_2'] = schedule.loc[switch,'temp']
    schedule.loc[switch,'temp'] = schedule.loc[switch,'score_1']
    schedule.loc[switch,'score_1'] = schedule.loc[switch,'score_2']
    schedule.loc[switch,'score_2'] = schedule.loc[switch,'temp']
    schedule = schedule[['week','team_1','team_2','score_1','score_2']]\
    .sort_values(by=['week','team_1','team_2']).reset_index(drop=True)
    schedule['me'] = (schedule['team_1'] == team_name) | (schedule['team_2'] == team_name)
    return schedule

def get_games(start,finish):
    if type(start) != int:
        start = int(start)
    if type(finish) != int:
        finish = int(finish)
    stats = pd.DataFrame(columns=['boxscore','season','week','team','opponent','points_allowed'])
    for season in range(start//100,finish//100 + 1):
        start_week = start%100 if season == start//100 else 1
        end_week = finish%100 if season == finish//100 else 17
        uris = Boxscores(start_week,season,end_week).games
        for week in uris:
            print(week)
            for game in uris[week]:
                box = Boxscore(game['boxscore'])
                """ Blank rosters due to weird team name changes """
                if len(box.home_players) == 0 or len(box.away_players) == 0:
                    print('BLANK ROSTER FOR ' + game['boxscore'] + '!!!')
                for player in box.home_players:
                    stats = stats.append(player.dataframe,sort=False)
                stats.loc[stats.team.isnull(),'team'] = box.home_abbreviation
                stats.loc[stats.opponent.isnull(),'opponent'] = box.away_abbreviation
                stats.loc[stats.points_allowed.isnull(),'points_allowed'] = box.away_points
                for player in box.away_players:
                    stats = stats.append(player.dataframe,sort=False)
                stats.loc[stats.team.isnull(),'team'] = box.away_abbreviation
                stats.loc[stats.opponent.isnull(),'opponent'] = box.home_abbreviation
                stats.loc[stats.points_allowed.isnull(),'points_allowed'] = box.home_points
                stats.loc[stats.season.isnull(),'season'] = season
                stats.loc[stats.week.isnull(),'week'] = int(week.split('-')[0])
                stats.loc[stats.boxscore.isnull(),'boxscore'] = game['boxscore']
    stats = stats.reset_index().rename(index=str,columns={'index':'player_id'}).fillna(0.0)
    stats.team = stats.team.str.upper()
    stats.opponent = stats.opponent.str.upper()
    for player_id in stats.player_id.unique():
        if stats.player_id.unique().tolist().index(player_id)%100 == 0:
            print('Player #' + str(stats.player_id.unique().tolist().index(player_id)) + \
            ' out of ' + str(stats.player_id.unique().shape[0]))
        response = requests.get('https://www.pro-football-reference.com/players/' + player_id[0].upper() + '/' + player_id + '.htm')
        if response.text == '':
            print(player_id + ' has a blank html page... Skipping...')
        else:
            if '<h1 itemprop="name">' in response.text:
                stats.loc[stats.player_id == player_id,'name'] = ' '.join([val for val in \
                response.text.split('<h1 itemprop="name">\n\t\t<span>')[1].split('</span>')[0].split(' ') if val != ''])
            else:
                print(player_id + " doesn't have name on personal page...")
            bad_pos = {'SnelBe00':'RB','WillQu01':'LB','GreeVi00':'TE',\
            'HowaTy00':'DT','SmitTr04':'CB','DaviMi03':'CB','ThomJa04':'S',\
            'BealSa00':'CB','AlexAd00':'DB','CrowTa00':'LB','BrowVi00':'WR',\
            'MintAn00':'LB'}
            if '<strong>Position</strong>: ' in response.text:
                stats.loc[stats.player_id == player_id,'position'] = response.text.split('<strong>Position</strong>: ')[1].split('\n')[0]
                if response.text.split('<strong>Position</strong>: ')[1].split('\n')[0] == 'WR/RB':
                    print('Changing ' + stats.loc[stats.player_id == player_id,'name'].values[0] + ' from WR/RB to RB...')
                    stats.loc[stats.player_id == player_id,'position'] = 'RB'
                elif response.text.split('<strong>Position</strong>: ')[1].split('\n')[0] == 'QB/TE':
                    print('Changing ' + stats.loc[stats.player_id == player_id,'name'].values[0] + ' from QB/TE to TE...')
                    stats.loc[stats.player_id == player_id,'position'] = 'TE'
                elif response.text.split('<strong>Position</strong>: ')[1].split('\n')[0] == 'WR/CB':
                    print('Changing ' + stats.loc[stats.player_id == player_id,'name'].values[0] + ' from WR/CB to WR...')
                    stats.loc[stats.player_id == player_id,'position'] = 'WR'
                elif ('QB' in response.text.split('<strong>Position</strong>: ')[1].split('\n')[0] \
                or 'RB' in response.text.split('<strong>Position</strong>: ')[1].split('\n')[0] \
                or 'WR' in response.text.split('<strong>Position</strong>: ')[1].split('\n')[0] \
                or 'TE' in response.text.split('<strong>Position</strong>: ')[1].split('\n')[0]) \
                and '/' in response.text.split('<strong>Position</strong>: ')[1].split('\n')[0]:
                    print('Weird combo position for ' + stats.loc[stats.player_id == player_id,'name'].values[0] + ': ' + \
                    response.text.split('<strong>Position</strong>: ')[1].split('\n')[0])
            elif player_id in bad_pos:
                stats.loc[stats.player_id == player_id,'position'] = bad_pos[player_id]
            else:
                print(player_id + " doesn't have position on personal page...")
            if '<strong>Team</strong>: <span itemprop="affiliation"><a href="/teams/' in response.text:
                stats.loc[stats.player_id == player_id,'real_abbrev'] = response.text.split('<strong>Team</strong>: ' + \
                '<span itemprop="affiliation"><a href="/teams/')[1].split('/')[0].upper()
            else:
                #print(player_id + " doesn't have team on personal page...")
                stats.loc[stats.player_id == player_id,'real_abbrev'] = \
                stats.loc[stats.player_id == player_id].sort_values(by=['season','week'],ascending=False)\
                .drop_duplicates(subset='player_id',keep='first').team.values[0]
    stats = pd.merge(left=stats,right=nfl_teams[['abbrev','real_abbrev']]\
    .rename(columns={'abbrev':'current_team'}),how='inner',on='real_abbrev')
    del stats['real_abbrev']
    """ Modified the sportsreference boxscore source code to account for weird team abbreviations... """
    defenses = stats.loc[~stats.position.isin(['QB','RB','WR','TE','K'])]\
    .groupby(['boxscore','season','week','team','opponent','points_allowed']).sum().reset_index()
    defenses = pd.merge(left=defenses,right=nfl_teams[['abbrev','real_abbrev']],how='inner',left_on='team',right_on='real_abbrev')
    defenses['name'] = defenses['abbrev']
    defenses['player_id'] = defenses['name']
    del defenses['abbrev'], defenses['real_abbrev']
    defenses['position'] = 'DEF'
    defenses['current_team'] = defenses['name']
    defenses = defenses[stats.columns.tolist()]
    stats = stats.loc[stats.position.isin(['QB','RB','WR','TE','K'])]
    stats = stats.append(defenses,ignore_index=True)
    return stats

def get_rates(rosters,start,as_of,num_sims=10000,reference_games=16,time_factor=0.0,tot=None,war_sim=True):
    if as_of//100 < datetime.datetime.now().year:
        prev = as_of//100*100 + 17
    else:
        prev = as_of - 1 - (83 if as_of%100 == 1 else 0)
    if type(tot) != pd.core.frame.DataFrame:
        if os.path.exists('GameByGameFantasyFootballStats.csv'):
            tot = pd.read_csv('GameByGameFantasyFootballStats.csv')
            if (tot.season*100 + tot.week).min() > start:
                last = (tot.season*100 + tot.week).min() - 1
                if last%100 == 0:
                    last -= 83
                tot = tot.append(get_games(start,last))
                tot.to_csv('GameByGameFantasyFootballStats.csv',index=False)
            if (tot.season*100 + tot.week).max() < prev:
                first = (tot.season*100 + tot.week).max() + 1
                if first%100 == 18:
                    first += 83
                tot = tot.append(get_games(first,prev))
                tot.to_csv('GameByGameFantasyFootballStats.csv',index=False)
            tot = tot.loc[tot.season*100 + tot.week >= start]
        else:
            tot = get_games(start,prev)
            tot.to_csv('GameByGameFantasyFootballStats.csv',index=False)
    else:
        tot = tot.loc[(tot.season*100 + tot.week >= start) & (tot.season <= as_of//100)]
    if (tot.season*100 + tot.week).max() >= as_of:
        teams_as_of = tot.loc[tot.season*100 + tot.week >= as_of].sort_values(by='week')\
        .drop_duplicates(subset='player_id',keep='first')[['player_id','team']].rename(columns={'team':'real_abbrev'})
        teams_as_of = pd.merge(left=teams_as_of,right=nfl_teams[['abbrev','real_abbrev']]\
        .rename(columns={'abbrev':'current_team'}),how='inner',on='real_abbrev')
        del teams_as_of['real_abbrev']
    else:
        teams_as_of = tot.sort_values(by='week').drop_duplicates(subset='player_id',keep='last')[['player_id','current_team']]
    if 'current_team' in tot.columns:
        del tot['current_team']
    tot = pd.merge(left=tot.loc[tot.season*100 + tot.week < as_of],right=teams_as_of,how='left',on='player_id')
    tot.loc[tot.current_team.isnull(),'current_team'] = 'UNK'
    """ Calculating fantasy points corresponding to league settings """
    defenses = tot.position == 'DEF'
    tot.loc[~defenses,'points'] = tot.loc[~defenses,'rush_yards']*scoring.loc['Rush Yds','value'] + \
    tot.loc[~defenses,'rush_touchdowns']*scoring.loc['Rush TD','value'] + \
    tot.loc[~defenses,'receptions']*scoring.loc['Rec','value'] + \
    tot.loc[~defenses,'receiving_yards']*scoring.loc['Rec Yds','value'] + \
    tot.loc[~defenses,'receiving_touchdowns']*scoring.loc['Rec TD','value'] + \
    tot.loc[~defenses,'passing_yards']*scoring.loc['Pass Yds','value'] + \
    tot.loc[~defenses,'passing_touchdowns']*scoring.loc['Pass TD','value'] + \
    tot.loc[~defenses,'interceptions_thrown']*scoring.loc['Int Thrown','value'] + \
    tot.loc[~defenses,'fumbles_lost']*scoring.loc['Fum Lost','value'] + \
    (tot.loc[~defenses,'kickoff_return_yards'] + tot.loc[~defenses,'punt_return_yards'])*(scoring.loc['Ret Yds','value'] if 'Ret Yds' in scoring.index else 0) + \
    (tot.loc[~defenses,'kickoff_return_touchdown'] + tot.loc[~defenses,'punt_return_touchdown'])*scoring.loc['Ret TD','value'] + \
    tot.loc[~defenses,'extra_points_made']*scoring.loc['PAT Made','value'] + \
    tot.loc[~defenses,'field_goals_made']*scoring.loc['FG 0-19','value']
    tot.loc[defenses,'points'] = tot.loc[defenses,'sacks']*scoring.loc['Sack','value'] + \
    tot.loc[defenses,'interceptions']*scoring.loc['Int','value'] + \
    tot.loc[defenses,'fumbles_recovered']*scoring.loc['Fum Rec','value'] + \
    tot.loc[defenses,'interceptions_returned_for_touchdown']*scoring.loc['Ret TD','value'] + \
    tot.loc[defenses,'kickoff_return_touchdown']*scoring.loc['Ret TD','value'] + \
    tot.loc[defenses,'punt_return_touchdown']*scoring.loc['Ret TD','value']
    tot.loc[defenses & (tot.points_allowed == 0),'points'] += scoring.loc['Pts Allow 0','value']
    tot.loc[defenses & (tot.points_allowed >= 1) & (tot.points_allowed <= 6),'points'] += scoring.loc['Pts Allow 1-6','value']
    tot.loc[defenses & (tot.points_allowed >= 7) & (tot.points_allowed <= 13),'points'] += scoring.loc['Pts Allow 7-13','value']
    tot.loc[defenses & (tot.points_allowed >= 14) & (tot.points_allowed <= 20),'points'] += scoring.loc['Pts Allow 14-20','value']
    tot.loc[defenses & (tot.points_allowed >= 21) & (tot.points_allowed <= 27),'points'] += scoring.loc['Pts Allow 21-27','value']
    tot.loc[defenses & (tot.points_allowed >= 28) & (tot.points_allowed <= 34),'points'] += scoring.loc['Pts Allow 28-34','value']
    tot.loc[defenses & (tot.points_allowed >= 35),'points'] += scoring.loc['Pts Allow 35+','value']
    """ Only keeping the specified number of games for each player """
    tot = tot.groupby('player_id').head(reference_games)
    """ Adding weights based on how long ago the game was... """
    tot['weeks_ago'] = (datetime.datetime.now() - pd.to_datetime(tot.boxscore.str[:8],infer_datetime_format=True)).dt.days/7.0
    tot['time_factor'] = 1 - tot.weeks_ago*time_factor # Optimize this factor!!! Guess = 0.1?
    tot.loc[tot.time_factor < 0,'time_factor'] = 0
    tot = pd.merge(left=tot,right=tot.groupby(['name','position','current_team'])\
    .time_factor.sum().reset_index().rename(columns={'time_factor':'time_factor_sum'}),\
    how='inner',on=['name','position','current_team'])
    tot = pd.merge(left=tot,right=tot.groupby(['name','position','current_team'])\
    .size().to_frame('num_games').reset_index(),how='inner',on=['name','position','current_team'])
    tot.time_factor = tot.time_factor*tot.num_games/tot.time_factor_sum
    tot['weighted_points'] = tot.points*tot.time_factor
    by_player = pd.merge(left=tot.groupby(['name','position','current_team']).weighted_points.mean()\
    .reset_index().rename(index=str,columns={'weighted_points':'points_avg'}),\
    right=tot.groupby(['name','position','current_team']).weighted_points.std().reset_index()\
    .rename(index=str,columns={'weighted_points':'points_stdev'}),how='inner',on=['name','position','current_team'])
    """ Simulating each player based on their average and standard deviation """
    by_player = pd.merge(left=by_player,right=tot.groupby(['name','position','current_team'])\
    .size().to_frame('num_games').reset_index(),how='inner',on=['name','position','current_team'])
    by_pos = pd.merge(left=tot.groupby('position').points.mean()\
    .reset_index().rename(index=str,columns={'points':'points_avg'}),\
    right=tot.groupby('position').points.std().reset_index()\
    .rename(index=str,columns={'points':'points_stdev'}),how='inner',on='position')
    by_pos['name'] = 'Average_' + by_pos['position']
    by_player = by_player.append(by_pos[['name','position','points_avg','points_stdev']],ignore_index=True,sort=False)
    by_player.points_stdev = by_player.points_stdev.fillna(0.0)
    by_player = pd.merge(left=by_player,right=by_pos[['position','points_avg','points_stdev']]\
    .rename(columns={'points_avg':'pos_avg','points_stdev':'pos_stdev'}),how='inner',on='position')
    inds = by_player.num_games < reference_games
    by_player.loc[inds,'points_squared'] = (by_player.loc[inds,'num_games']*(by_player.loc[inds,'points_stdev']**2 + \
    by_player.loc[inds,'points_avg']**2) + (reference_games - by_player.loc[inds,'num_games'])*\
    (by_player.loc[inds,'pos_stdev']**2 + by_player.loc[inds,'pos_avg']**2))/reference_games
    by_player.loc[inds,'points_avg'] = (by_player.loc[inds,'num_games']*by_player.loc[inds,'points_avg'] + \
    (reference_games - by_player.loc[inds,'num_games'])*by_player.loc[inds,'pos_avg'])/reference_games
    by_player.loc[inds,'points_stdev'] = (by_player.loc[inds,'points_squared'] - by_player.loc[inds,'points_avg']**2)**0.5
    if war_sim:
        """ Creating histograms across all players in each position """
        pos_hists = {'points':np.arange(-10,50.1,0.1)}
        for pos in tot.position.unique():
            pos_hists[pos] = np.histogram(tot.loc[tot.position == pos,'points'],bins=pos_hists['points'])[0]
            pos_hists[pos] = pos_hists[pos]/sum(pos_hists[pos])
        pos_hists['FLEX'] = np.histogram(tot.loc[tot.position.isin(['RB','WR','TE']),'points'],bins=pos_hists['points'])[0]
        pos_hists['FLEX'] = pos_hists['FLEX']/sum(pos_hists['FLEX'])
        """ Simulating an entire team using average players """
        sim_scores = pd.DataFrame({'QB':np.random.choice(pos_hists['points'][:-1],p=pos_hists['QB'],size=num_sims),\
        'RB1':np.random.choice(pos_hists['points'][:-1],p=pos_hists['RB'],size=num_sims),\
        'RB2':np.random.choice(pos_hists['points'][:-1],p=pos_hists['RB'],size=num_sims),\
        'WR1':np.random.choice(pos_hists['points'][:-1],p=pos_hists['WR'],size=num_sims),\
        'WR2':np.random.choice(pos_hists['points'][:-1],p=pos_hists['WR'],size=num_sims),\
        'TE':np.random.choice(pos_hists['points'][:-1],p=pos_hists['TE'],size=num_sims),\
        'FLEX':np.random.choice(pos_hists['points'][:-1],p=pos_hists['FLEX'],size=num_sims),\
        'K':np.random.choice(pos_hists['points'][:-1],p=pos_hists['K'],size=num_sims),\
        'DEF':np.random.choice(pos_hists['points'][:-1],p=pos_hists['DEF'],size=num_sims)})
        sim_scores['Total'] = sim_scores.QB + sim_scores.RB1 + sim_scores.RB2 + \
        sim_scores.WR1 + sim_scores.WR2 + sim_scores.TE + sim_scores.FLEX + \
        sim_scores.K + sim_scores.DEF
        for ind in range(by_player.shape[0]):
            if by_player.loc[ind,'name'] in sim_scores.columns:
                continue
            sim_scores = pd.merge(left=sim_scores,right=pd.DataFrame({by_player.loc[ind,'name']:\
            np.round(np.random.normal(loc=by_player.loc[ind,'points_avg'],\
            scale=by_player.loc[ind,'points_stdev'],size=sim_scores.shape[0]))}),\
            left_index=True,right_index=True)
        """ Calculating the number of wins above replacement for each player """
        for player in sim_scores.columns[10:]:
            cols = sim_scores.columns[:9].tolist()
            pos = by_player.loc[by_player.name == player,'position'].values[0]
            if pos in ['RB','WR']:
                pos += '1'
            cols.pop(cols.index(pos))
            cols.append(player)
            sim_scores['Alt_Total'] = sim_scores[cols].sum(axis=1)
            by_player.loc[by_player.name == player,'WAR'] = (sum(sim_scores.loc[:sim_scores.shape[0]//2 - 1,'Alt_Total'].values > \
            sim_scores.loc[sim_scores.shape[0]//2:,'Total'].values)/(sim_scores.shape[0]//2) - 0.5)*14
            del sim_scores['Alt_Total']
    else:
        by_player = pd.merge(left=by_player,right=pd.DataFrame({'position':\
        ['QB','WR','RB','TE','K','DEF'],'slope':[0.2084,0.2006,0.1882,0.2103,0.2148,0.2149],\
        'intercept':[-3.1978,-1.0231,-1.2478,-0.7767,-1.5785,-1.6107]}),how='inner',on='position')
        by_player['WAR'] = by_player.slope*by_player.points_avg + by_player.intercept
        del by_player['slope'], by_player['intercept']
    
    try:
        corrections = pd.read_csv("https://raw.githubusercontent.com/" + \
        "tefirman/FantasySports/master/FantasyFootball_NameCorrections.csv")
    except:
        corrections = [player.split(',') for player in requests.get("https://raw.githubusercontent.com/" + \
        "tefirman/FantasySports/master/FantasyFootball_NameCorrections.csv",verify=False).text.split('\r')]
        corrections = pd.DataFrame(corrections[1:],columns=corrections[0])
    rosters = pd.merge(left=rosters,right=corrections,how='left',on='name')
    rosters.loc[~rosters.new_name.isnull(),'name'] = rosters.loc[~rosters.new_name.isnull(),'new_name']
    
    """ Comment out during optimization... """
    if rosters.loc[~rosters.name.isin(by_player.name) & ~rosters.fantasy_team.isnull()].shape[0] > 0:
        print('Need to reconcile player names... ' + ', '.join(rosters.loc[~rosters.name.isin(by_player.name) & ~rosters.fantasy_team.isnull(),'name']))
    """ Comment out during optimization... """
    
    league_avg = by_player.loc[by_player.name.str.contains('Average_')]
    by_player = pd.merge(left=by_player,right=rosters[['name','position',\
    'player_id','status','fantasy_team','editorial_team_abbr','selected_position']].drop_duplicates(),\
    how='right',on=['name','position']).append(league_avg,ignore_index=True,sort=False)
    rookies = pd.merge(left=by_player.loc[by_player.WAR.isnull(),['name','player_id','position',\
    'current_team','fantasy_team','editorial_team_abbr','selected_position']],\
    right=league_avg[['position','points_avg','points_stdev','WAR']],how='inner',on='position')
    by_player = by_player.loc[~by_player.WAR.isnull()]
    by_player = by_player.append(rookies[['name','player_id','position','current_team',\
    'points_avg','points_stdev','WAR','fantasy_team','editorial_team_abbr','selected_position']],ignore_index=True,sort=False)
    
    if as_of//100 == datetime.datetime.now().year: # and lg.current_week() == 1:
        """ First week issues... """
        by_player = pd.merge(left=by_player,right=nfl_teams[['abbrev','yahoo']]\
        .rename(columns={'yahoo':'editorial_team_abbr'}),how='left',on='editorial_team_abbr')
        by_player.loc[~by_player.abbrev.isnull(),'current_team'] = \
        by_player.loc[~by_player.abbrev.isnull(),'abbrev']
#        by_player.loc[by_player.current_team.isnull() & ~by_player.abbrev.isnull(),'current_team'] = \
#        by_player.loc[by_player.current_team.isnull() & ~by_player.abbrev.isnull(),'abbrev']
#        del by_player['editorial_team_abbr'], by_player['abbrev']
        del by_player['abbrev']
        """ First week issues... """
    
    return by_player

def bye_weeks(season):
    byes = pd.DataFrame(columns=['current_team','bye_week'])
    for team in nfl_schedule.abbrev.unique():
        bye_week = 1
        while ((nfl_schedule.abbrev == team) & (nfl_schedule.season == season) & (nfl_schedule.week == bye_week)).any():
            bye_week += 1
        byes = byes.append({'current_team':team,'bye_week':bye_week},ignore_index=True)
    return byes

def add_injuries(by_player,as_of):
    if 'until' in by_player.columns:
        del by_player['until']
    by_player['until'] = None
    if as_of < datetime.datetime.now().year*100 + current_week:
        games = pd.read_csv('GameByGameFantasyFootballStats.csv')
        games = games.loc[games.season*100 + games.week >= as_of]
        injured = by_player.loc[~by_player.name.isin(games.loc[games.season*100 + games.week == as_of,'name']),'name'].tolist()
        for name in injured:
            until = games.loc[games.name == name,'week'].min() - 1
            if not np.isnan(until):
                by_player.loc[by_player.name == name,'until'] = until
            elif as_of//100 < datetime.datetime.now().year:
                by_player.loc[by_player.name == name,'until'] = 17
    if as_of//100 == datetime.datetime.now().year:
        try:
            inj_proj = pd.read_csv("https://raw.githubusercontent.com/" + \
            "tefirman/FantasySports/master/FantasyFootball_InjuredList.csv")
        except:
            inj_proj = [player.split(',') for player in requests.get("https://raw.githubusercontent.com/" + \
            "tefirman/FantasySports/master/FantasyFootball_InjuredList.csv",verify=False).text.split('\r')]
            inj_proj = pd.DataFrame(inj_proj[1:],columns=inj_proj[0])
        inj_proj = inj_proj.loc[inj_proj.until >= current_week]
        by_player = pd.merge(left=by_player.rename(columns={'until':'until_orig'}),\
        right=inj_proj,how='left',on=['name','position','current_team'])
        if as_of%100 == current_week:
            newInjury = by_player.status.isin(['O','D','SUSP','IR','PUP-R','PUP-P','NFI-R','NA','COVID-19']) & \
            (by_player.until.isnull() | (by_player.until < current_week)) & \
            (~by_player.fantasy_team.isnull() | (by_player.WAR >= 0))
            if newInjury.sum() > 0:
                print('Need to look up new injuries... ' + ', '.join(by_player.loc[newInjury,'name'].tolist()))
                by_player.loc[newInjury,'until'] = current_week
            oldInjury = ~by_player.status.isin(['O','D','SUSP','IR','PUP-R','PUP-P','NFI-R','NA','COVID-19']) & \
            (by_player.until >= current_week) & (~by_player.fantasy_team.isnull() | (by_player.WAR >= 0))
            if oldInjury.sum() > 0:
                print('Need to update old injuries... ' + ', '.join(by_player.loc[oldInjury,'name'].tolist()))
                #by_player.loc[oldInjury,'until'] = lg.current_week()
        by_player['until'] = by_player[['until_orig','until']].min(axis=1)
        del by_player['until_orig']
    return by_player

def starters(rosters,week,as_of=None,homeawayoppqb=[1,1,0,0]):
    if not as_of:
        as_of = latest_season*100 + current_week
    rosters = pd.merge(left=rosters,right=nfl_schedule.loc[(nfl_schedule.season == as_of//100) & \
    (nfl_schedule.week == week)],how='left',left_on='current_team',right_on='abbrev')
    rosters.loc[rosters.home_away == 'Home','homeaway_factor'] = homeawayoppqb[0]
    rosters.loc[rosters.home_away == 'Away','homeaway_factor'] = homeawayoppqb[1]
    rosters['opp_factor'] = homeawayoppqb[2]*rosters['opp_elo']
    rosters['qb_factor'] = homeawayoppqb[3]*rosters['qb_elo']
    rosters['points_avg'] *= (rosters['homeaway_factor'] + rosters['opp_factor'] + rosters['qb_factor'])
    """ WAR is linear with points_avg, but slope/intercept depends on position """
    """ Harder to characterize how WAR varies with points_stdev, ignoring for now... """
    rosters = rosters.sort_values(by='points_avg',ascending=False)
    #rosters = rosters.sort_values(by='WAR',ascending=False)
    rosters['starter'] = False
    rosters['injured'] = rosters.until >= week
    if week == as_of%100 and as_of//100 == datetime.datetime.now().year \
    and datetime.datetime.now().month > 8: # Careful when your draft is in September...
        if datetime.datetime.now().hour < 20:
            completed = nfl_schedule.loc[(nfl_schedule.season == as_of//100) & (nfl_schedule.week == week) & \
            (nfl_schedule.date.dt.date < datetime.datetime.now().date()),'abbrev'].tolist()
        else:
            completed = nfl_schedule.loc[(nfl_schedule.season == as_of//100) & (nfl_schedule.week == week) & \
            (nfl_schedule.date.dt.date <= datetime.datetime.now().date()),'abbrev'].tolist()
        for team in rosters.fantasy_team.unique():
            players = rosters.loc[rosters.fantasy_team == team]
            started = players.loc[~players.selected_position.isin(['BE','IR']) & \
            players.editorial_team_abbr.isin(completed)]
            not_available = players.loc[players.selected_position.isin(['BE','IR']) & \
            players.editorial_team_abbr.isin(completed)]
            num_pos = pd.merge(left=roster_position.loc[(roster_position['count'] > 0) & \
            ~roster_position.position.isin(['BE','IR','RB/WR/TE'])],\
            right=started.groupby('selected_position').size().to_frame('already')\
            .reset_index().rename(columns={'selected_position':'position'}),how='left',on='position')
            num_pos.already = num_pos.already.fillna(0.0)
            num_pos['count'] -= num_pos['already']
            for ind in range(num_pos.shape[0]):
                for num in range(int(num_pos.loc[ind,'count'])):
                    rosters.loc[rosters.loc[(rosters.fantasy_team == team) & \
                    ~rosters.starter & ~rosters.injured & (rosters.bye_week != week) & \
                    (rosters.position == num_pos.loc[ind,'position']) & ~rosters.player_id.isin(started.player_id) & \
                    ~rosters.player_id.isin(not_available.player_id)].iloc[:1].index,'starter'] = True
            flex = pd.merge(left=roster_position.loc[(roster_position['count'] > 0) & \
            roster_position.position.isin(['RB/WR/TE'])],\
            right=started.groupby('selected_position').size().to_frame('already')\
            .reset_index().rename(columns={'selected_position':'position'}),how='left',on='position')
            flex.already = flex.already.fillna(0.0)
            flex['count'] -= flex['already']
            for ind in range(flex.shape[0]):
                for num in range(int(flex.loc[ind,'count'])):
                    rosters.loc[rosters.loc[(rosters.fantasy_team == team) & \
                    ~rosters.starter & ~rosters.injured & (rosters.bye_week != week) & \
                    rosters.position.isin(['WR','RB','TE']) & ~rosters.player_id.isin(started.player_id) & \
                    ~rosters.player_id.isin(not_available.player_id)].iloc[:1].index,'starter'] = True
    elif week >= as_of%100:
        num_pos = roster_position.loc[(roster_position['count'] > 0) & \
        ~roster_position.position.isin(['BE','IR','RB/WR/TE'])].reset_index(drop=True)
        for ind in range(num_pos.shape[0]):
            for num in range(int(num_pos.loc[ind,'count'])):
                rosters.loc[rosters.loc[~rosters.starter & ~rosters.injured & \
                (rosters.bye_week != week) & (rosters.position == num_pos.loc[ind,'position'])]\
                .drop_duplicates(subset=['fantasy_team'],keep='first').index,'starter'] = True
        flex = roster_position.loc[(roster_position['count'] > 0) & \
        roster_position.position.isin(['RB/WR/TE'])].reset_index(drop=True)
        for ind in range(flex.shape[0]):
            for num in range(int(flex.loc[ind,'count'])):
                rosters.loc[rosters.loc[~rosters.starter & ~rosters.injured & \
                (rosters.bye_week != week) & rosters.position.isin(['WR','RB','TE'])]\
                .drop_duplicates(subset=['fantasy_team'],keep='first').index,'starter'] = True
    return rosters

def season_sims(rosters,schedule,num_sims=10000,verbose=False,as_of=None,\
postseason=True,homeawayoppqb=[1,1,0,0],payouts=[800,300,100],fixed_winner=None):
    rosters['points_var'] = rosters.points_stdev**2
    projections = pd.DataFrame(columns=['fantasy_team','week','points_avg','points_var'])
    for week in range(18):
        rosters_weighted = starters(rosters,week + 1,as_of,homeawayoppqb)
        projections = projections.append(rosters_weighted.loc[rosters_weighted.starter].groupby('fantasy_team')\
        [['points_avg','points_var']].sum().reset_index(),ignore_index=True,sort=False)
        projections.loc[projections.week.isnull(),'week'] = week + 1
    projections['points_stdev'] = projections['points_var']**0.5
    del rosters['points_var']
    schedule = pd.merge(left=schedule,right=projections.rename(index=str,\
    columns={'fantasy_team':'team_1','points_avg':'points_avg_1',\
    'points_stdev':'points_stdev_1'}),how='left',on=['week','team_1'])
    schedule = pd.merge(left=schedule,right=projections.rename(index=str,\
    columns={'fantasy_team':'team_2','points_avg':'points_avg_2',\
    'points_stdev':'points_stdev_2'}),how='left',on=['week','team_2'])
    schedule['points_avg_1'] = schedule['points_avg_1'].fillna(0.0)
    schedule['points_avg_2'] = schedule['points_avg_2'].fillna(0.0)
    schedule['points_stdev_1'] = schedule['points_stdev_1'].fillna(0.0)
    schedule['points_stdev_2'] = schedule['points_stdev_2'].fillna(0.0)
    schedule['points_avg_1'] += schedule['score_1']
    schedule['points_avg_2'] += schedule['score_2']
    if fixed_winner:
        if ((schedule.week == fixed_winner[0]) & (schedule.team_1 == fixed_winner[1])).any():
            winner,loser = '1','2'
        else:
            winner,loser = '2','1'
        schedule.loc[(schedule.week == fixed_winner[0]) & (schedule['team_' + winner] == fixed_winner[1]),'points_avg_' + winner] = 100.1
        schedule.loc[(schedule.week == fixed_winner[0]) & (schedule['team_' + winner] == fixed_winner[1]),'points_avg_' + loser] = 100.0
        schedule.loc[(schedule.week == fixed_winner[0]) & (schedule['team_' + winner] == fixed_winner[1]),'points_stdev_' + winner] = 0.0
        schedule.loc[(schedule.week == fixed_winner[0]) & (schedule['team_' + winner] == fixed_winner[1]),'points_stdev_' + loser] = 0.0
    schedule_sims = pd.DataFrame().append([schedule]*num_sims,ignore_index=True)
    schedule_sims['num_sim'] = schedule_sims.index//schedule.shape[0]
    schedule_sims['sim_1'] = np.random.normal(loc=0,scale=1,size=schedule_sims.shape[0])*schedule_sims['points_stdev_1'] + schedule_sims['points_avg_1']
    schedule_sims['sim_2'] = np.random.normal(loc=0,scale=1,size=schedule_sims.shape[0])*schedule_sims['points_stdev_2'] + schedule_sims['points_avg_2']
    schedule_sims['win_1'] = (schedule_sims.sim_1 > schedule_sims.sim_2).astype(int)
    schedule_sims['win_2'] = 1 - schedule_sims['win_1']
    standings = schedule_sims[['num_sim','week','team_1','sim_1','win_1']]\
    .rename(index=str,columns={'team_1':'team','win_1':'wins','sim_1':'points'})\
    .append(schedule_sims[['num_sim','week','team_2','sim_2','win_2']]\
    .rename(index=str,columns={'team_2':'team','win_2':'wins','sim_2':'points'}),ignore_index=True)
    
    standings.points = standings.points.astype(float)
    
#    standings = standings.loc[standings.week < int(sched_settings['playoff_start_week'])]\
#    .groupby(['num_sim','team']).sum().sort_values(by=['num_sim','wins','points'],ascending=False).reset_index()
    
    num_games = standings[['week','team']].drop_duplicates().groupby('team').size().to_frame('tot_games').reset_index()
    standings = standings.loc[standings.week < int(sched_settings['playoff_start_week'])].groupby(['num_sim','team']).sum().reset_index()
    standings = pd.merge(left=standings,right=num_games,how='inner',on='team')
    standings['win_pct'] = standings['wins']/standings['tot_games']
    standings = standings.sort_values(by=['num_sim','win_pct','points'],ascending=False).reset_index(drop=True)
    del standings['tot_games'], standings['win_pct']
    
    standings.loc[standings.index%len(rosters.fantasy_team.unique()) < int(sched_settings['num_playoff_teams']),'playoffs'] = 1
    standings.loc[standings.index%len(rosters.fantasy_team.unique()) >= int(sched_settings['num_playoff_teams']),'playoffs'] = 0
    standings['playoff_bye'] = 0
    if sched_settings['num_playoff_teams'] == '6':
        standings.loc[standings.index%len(rosters.fantasy_team.unique()) < 2,'playoff_bye'] = 1
    if postseason:
        standings['winner'] = 0
        standings['runner_up'] = 0
        standings['third'] = 0
        for num_season in range(num_sims):
            if num_season%1000 == 0 and verbose:
                print('Season #' + str(num_season) + ', ' + str(datetime.datetime.now()))
            playoffs = standings.loc[(standings.num_sim == num_season) & \
            (standings.index%len(rosters.fantasy_team.unique()) < int(sched_settings['num_playoff_teams']))].copy().reset_index()
            if sched_settings['num_playoff_teams'] == '6':
                quarter_sched = schedule.week == int(sched_settings['playoff_start_week'])
                score3 = schedule.loc[quarter_sched & (schedule.team_1 == playoffs.loc[2,'team']),'score_1'].sum() + \
                schedule.loc[quarter_sched & (schedule.team_2 == playoffs.loc[2,'team']),'score_2'].sum()
                score4 = schedule.loc[quarter_sched & (schedule.team_1 == playoffs.loc[3,'team']),'score_1'].sum() + \
                schedule.loc[quarter_sched & (schedule.team_2 == playoffs.loc[3,'team']),'score_2'].sum()
                score5 = schedule.loc[quarter_sched & (schedule.team_1 == playoffs.loc[4,'team']),'score_1'].sum() + \
                schedule.loc[quarter_sched & (schedule.team_2 == playoffs.loc[4,'team']),'score_2'].sum()
                score6 = schedule.loc[quarter_sched & (schedule.team_1 == playoffs.loc[5,'team']),'score_1'].sum() + \
                schedule.loc[quarter_sched & (schedule.team_2 == playoffs.loc[5,'team']),'score_2'].sum()
                quarter = projections.week == int(sched_settings['playoff_start_week'])
                seed3 = quarter & (projections.fantasy_team == playoffs.loc[2,'team'])
                seed4 = quarter & (projections.fantasy_team == playoffs.loc[3,'team'])
                seed5 = quarter & (projections.fantasy_team == playoffs.loc[4,'team'])
                seed6 = quarter & (projections.fantasy_team == playoffs.loc[5,'team'])
                if sched_settings['uses_playoff_reseeding']:
                    if np.random.normal(loc=projections.loc[seed3,'points_avg'].sum() + score3,scale=projections.loc[seed3,'points_stdev'].sum()) > \
                    np.random.normal(loc=projections.loc[seed6,'points_avg'].sum() + score6,scale=projections.loc[seed6,'points_stdev'].sum()):
                        playoffs = playoffs.loc[playoffs.index != 5]
                    else:
                        playoffs = playoffs.loc[playoffs.index != 2]
                    if np.random.normal(loc=projections.loc[seed4,'points_avg'].sum() + score4,scale=projections.loc[seed4,'points_stdev'].sum()) > \
                    np.random.normal(loc=projections.loc[seed5,'points_avg'].sum() + score5,scale=projections.loc[seed5,'points_stdev'].sum()):
                        playoffs = playoffs.loc[playoffs.index != 4]
                    else:
                        playoffs = playoffs.loc[playoffs.index != 3]
                    playoffs = playoffs.reset_index(drop=True)
                else:
                    if np.random.normal(loc=projections.loc[seed3,'points_avg'].sum() + score3,scale=projections.loc[seed3,'points_stdev'].sum()) < \
                    np.random.normal(loc=projections.loc[seed6,'points_avg'].sum() + score6,scale=projections.loc[seed6,'points_stdev'].sum()):
                        playoffs.loc[2] = playoffs.loc[5]
                    if np.random.normal(loc=projections.loc[seed4,'points_avg'].sum() + score4,scale=projections.loc[seed4,'points_stdev'].sum()) < \
                    np.random.normal(loc=projections.loc[seed5,'points_avg'].sum() + score5,scale=projections.loc[seed5,'points_stdev'].sum()):
                        playoffs.loc[3] = playoffs.loc[4]
                    playoffs = playoffs.loc[:3]
            semi_sched = schedule.week.isin([int(sched_settings['playoff_start_week']),int(sched_settings['playoff_start_week']) + 1])
            score1 = schedule.loc[semi_sched & (schedule.team_1 == playoffs.loc[0,'team']),'score_1'].sum() + \
            schedule.loc[semi_sched & (schedule.team_2 == playoffs.loc[0,'team']),'score_2'].sum()
            score2 = schedule.loc[semi_sched & (schedule.team_1 == playoffs.loc[1,'team']),'score_1'].sum() + \
            schedule.loc[semi_sched & (schedule.team_2 == playoffs.loc[1,'team']),'score_2'].sum()
            score3 = schedule.loc[semi_sched & (schedule.team_1 == playoffs.loc[2,'team']),'score_1'].sum() + \
            schedule.loc[semi_sched & (schedule.team_2 == playoffs.loc[2,'team']),'score_2'].sum()
            score4 = schedule.loc[semi_sched & (schedule.team_1 == playoffs.loc[3,'team']),'score_1'].sum() + \
            schedule.loc[semi_sched & (schedule.team_2 == playoffs.loc[3,'team']),'score_2'].sum()
            semi = projections.week.isin([int(sched_settings['playoff_start_week']),int(sched_settings['playoff_start_week']) + 1])
            seed1 = semi & (projections.fantasy_team == playoffs.loc[0,'team'])
            seed2 = semi & (projections.fantasy_team == playoffs.loc[1,'team'])
            seed3 = semi & (projections.fantasy_team == playoffs.loc[2,'team'])
            seed4 = semi & (projections.fantasy_team == playoffs.loc[3,'team'])
            if np.random.normal(loc=projections.loc[seed1,'points_avg'].sum() + score1,\
            scale=(projections.loc[seed1,'points_stdev']**2.0).sum()**0.5) > \
            np.random.normal(loc=projections.loc[seed4,'points_avg'].sum() + score4,\
            scale=(projections.loc[seed4,'points_stdev']**2.0).sum()**0.5):
                consolation = playoffs.loc[playoffs.index == 3]
                playoffs = playoffs.loc[playoffs.index != 3]
            else:
                consolation = playoffs.loc[playoffs.index == 0]
                playoffs = playoffs.loc[playoffs.index != 0]
            if np.random.normal(loc=projections.loc[seed2,'points_avg'].sum() + score2,\
            scale=(projections.loc[seed2,'points_stdev']**2.0).sum()**0.5) > \
            np.random.normal(loc=projections.loc[seed3,'points_avg'].sum() + score3,\
            scale=(projections.loc[seed3,'points_stdev']**2.0).sum()**0.5):
                consolation = consolation.append(playoffs.loc[playoffs.index == 2],ignore_index=True)
                playoffs = playoffs.loc[playoffs.index != 2]
            else:
                consolation = consolation.append(playoffs.loc[playoffs.index == 1],ignore_index=True)
                playoffs = playoffs.loc[playoffs.index != 1]
            playoffs = playoffs.reset_index(drop=True)
            consolation = consolation.reset_index(drop=True)
            final_sched = schedule.week.isin([int(sched_settings['playoff_start_week']) + 2,int(sched_settings['playoff_start_week']) + 3])
            score1 = schedule.loc[final_sched & (schedule.team_1 == playoffs.loc[0,'team']),'score_1'].sum() + \
            schedule.loc[final_sched & (schedule.team_2 == playoffs.loc[0,'team']),'score_2'].sum()
            score2 = schedule.loc[final_sched & (schedule.team_1 == playoffs.loc[1,'team']),'score_1'].sum() + \
            schedule.loc[final_sched & (schedule.team_2 == playoffs.loc[1,'team']),'score_2'].sum()
            final = projections.week.isin([int(sched_settings['playoff_start_week']) + 2,int(sched_settings['playoff_start_week']) + 3])
            seed1 = final & (projections.fantasy_team == playoffs.loc[0,'team'])
            seed2 = final & (projections.fantasy_team == playoffs.loc[1,'team'])
            if np.random.normal(loc=projections.loc[seed1,'points_avg'].sum() + score1,\
            scale=(projections.loc[seed1,'points_stdev']**2.0).sum()**0.5) > \
            np.random.normal(loc=projections.loc[seed2,'points_avg'].sum() + score2,\
            scale=(projections.loc[seed2,'points_stdev']**2.0).sum()**0.5):
                standings.loc[(standings.team == playoffs.loc[0,'team']) & \
                (standings.num_sim == num_season),'winner'] = 1
                standings.loc[(standings.team == playoffs.loc[1,'team']) & \
                (standings.num_sim == num_season),'runner_up'] = 1
            else:
                standings.loc[(standings.team == playoffs.loc[1,'team']) & \
                (standings.num_sim == num_season),'winner'] = 1
                standings.loc[(standings.team == playoffs.loc[0,'team']) & \
                (standings.num_sim == num_season),'runner_up'] = 1
            score1 = schedule.loc[final_sched & (schedule.team_1 == consolation.loc[0,'team']),'score_1'].sum() + \
            schedule.loc[final_sched & (schedule.team_2 == consolation.loc[0,'team']),'score_2'].sum()
            score2 = schedule.loc[final_sched & (schedule.team_1 == consolation.loc[1,'team']),'score_1'].sum() + \
            schedule.loc[final_sched & (schedule.team_2 == consolation.loc[1,'team']),'score_2'].sum()
            seed1 = final & (projections.fantasy_team == consolation.loc[0,'team'])
            seed2 = final & (projections.fantasy_team == consolation.loc[1,'team'])
            if np.random.normal(loc=projections.loc[seed1,'points_avg'].sum() + score1,\
            scale=(projections.loc[seed1,'points_stdev']**2.0).sum()**0.5) > \
            np.random.normal(loc=projections.loc[seed2,'points_avg'].sum() + score2,\
            scale=(projections.loc[seed2,'points_stdev']**2.0).sum()**0.5):
                standings.loc[(standings.team == consolation.loc[0,'team']) & \
                (standings.num_sim == num_season),'third'] = 1
            else:
                standings.loc[(standings.team == consolation.loc[1,'team']) & \
                (standings.num_sim == num_season),'third'] = 1
    
    schedule_sims.points_avg_1 = schedule_sims.points_avg_1.astype(float)
    schedule_sims.points_stdev_1 = schedule_sims.points_stdev_1.astype(float)
    schedule_sims.points_avg_2 = schedule_sims.points_avg_2.astype(float)
    schedule_sims.points_stdev_2 = schedule_sims.points_stdev_2.astype(float)
    
    schedule = schedule_sims.groupby(['week','team_1','team_2']).mean().reset_index()
    schedule['points_avg_1'] = round(schedule['points_avg_1'],1)
    schedule['points_stdev_1'] = round(schedule['points_stdev_1'],1)
    schedule['points_avg_2'] = round(schedule['points_avg_2'],1)
    schedule['points_stdev_2'] = round(schedule['points_stdev_2'],1)
    standings = pd.merge(left=standings.groupby('team').mean().reset_index()\
    .rename(index=str,columns={'wins':'wins_avg','points':'points_avg'}),\
    right=standings[['team','wins','points']].groupby('team').std().reset_index()\
    .rename(index=str,columns={'wins':'wins_stdev','points':'points_stdev'}),\
    how='inner',on='team')
    scores = schedule_sims[['team_1','sim_1']].rename(index=str,columns={'team_1':'team','sim_1':'sim'})\
    .append(schedule_sims[['team_2','sim_2']].rename(index=str,columns={'team_2':'team','sim_2':'sim'}),ignore_index=True)
    scores.sim = scores.sim.astype(float)
    standings = pd.merge(left=standings,right=scores.groupby('team').sim.mean().reset_index()\
    .rename(columns={'sim':'per_game_avg'}),how='inner',on='team')
    standings = pd.merge(left=standings,right=scores.groupby('team').sim.std().reset_index()\
    .rename(columns={'sim':'per_game_stdev'}),how='inner',on='team')
    standings['per_game_fano'] = standings['per_game_stdev']/standings['per_game_avg']
    standings = standings.sort_values(by='winner' if postseason else 'playoffs',ascending=False)
    if postseason:
        standings['earnings'] = round(standings['winner']*payouts[0] + \
        standings['runner_up']*payouts[1] + standings['third']*payouts[2],2)
    standings['wins_avg'] = round(standings['wins_avg'],3)
    standings['wins_stdev'] = round(standings['wins_stdev'],3)
    standings['points_avg'] = round(standings['points_avg'],1)
    standings['points_stdev'] = round(standings['points_stdev'],1)
    standings['per_game_avg'] = round(standings['per_game_avg'],1)
    standings['per_game_stdev'] = round(standings['per_game_stdev'],1)
    standings['per_game_fano'] = round(standings['per_game_fano'],3)
    return schedule, standings

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
        if 'earnings' in col or (name == 'Deltas' and col != 'team'):
            writer.sheets[name].set_column(idx,idx,max_len,m)
        elif 'per_game_' in col or col.endswith('_factor'):
            writer.sheets[name].set_column(idx,idx,max_len,f,{'hidden':True})
        elif col.replace('my_','').replace('their_','').replace('_delta','').replace('_1','')\
        .replace('_2','') in ['playoffs','playoff_bye','winner','runner_up','third']:
            writer.sheets[name].set_column(idx,idx,max_len,p)
        else:
            writer.sheets[name].set_column(idx,idx,max_len,f)
    writer.sheets[name].autofilter('A1:' + (chr(64 + (df.shape[1] - 1)//26) + \
    chr(65 + (df.shape[1] - 1)%26)).replace('@','') + str(df.shape[0] + 1))
    return writer

def season_sims_mp(index,pause,rosters,schedule,num_sims=10000,verbose=False,\
as_of=None,postseason=True,homeawayoppqb=[1,1,0,0],payouts=[800,300,100]):
    global return_dict
    np.random.seed()
    time.sleep(pause)
    return_dict[index] = season_sims(rosters,schedule,num_sims,\
    verbose,as_of,postseason,homeawayoppqb,payouts)[1]

def possible_pickups(rosters,available,schedule,as_of=None,num_sims=1000,\
focus_on=[],exclude=[],limit_per=10,team_name='Team Jacquet',postseason=True,\
verbose=True,homeawayoppqb=[1,1,0,0],payouts=[800,300,100]):
    global return_dict
    orig_standings = season_sims(rosters,schedule,num_sims,False,as_of,\
    postseason=postseason,homeawayoppqb=homeawayoppqb,payouts=payouts)[1]
    added_value = pd.DataFrame(columns=['player_to_drop','player_to_add','wins_avg',\
    'wins_stdev','points_avg','points_stdev','per_game_avg','per_game_stdev',\
    'per_game_fano','playoffs','playoff_bye'] + (['winner','runner_up','third','earnings'] if postseason else []))
    players_to_drop = rosters.loc[rosters.fantasy_team == team_name]
    if players_to_drop.name.isin(focus_on).sum() > 0:
        players_to_drop = players_to_drop.loc[players_to_drop.name.isin(focus_on)]
    if players_to_drop.name.isin(exclude).sum() > 0:
        players_to_drop = players_to_drop.loc[~players_to_drop.name.isin(exclude)]
    for my_player in players_to_drop.name:
        if players_to_drop.loc[players_to_drop.name == my_player,'until'].values[0] >= as_of%100:
            possible = available.loc[~available.name.str.contains('Average_')]
        else:
            possible = available.loc[~available.name.str.contains('Average_') & \
            (available.WAR >= rosters.loc[rosters.name == my_player,'WAR'].values[0] - 0.1)]
        if possible.name.isin(focus_on).sum() > 0:
            possible = possible.loc[possible.name.isin(focus_on)]
        if possible.name.isin(exclude).sum() > 0:
            possible = possible.loc[~possible.name.isin(exclude)]
        if verbose:
            print(my_player + ': ' + str(possible.shape[0]) + ' better players')
            print(datetime.datetime.now())
        possible = possible.groupby('position').head(limit_per)
        manager = multiprocessing.Manager()
        return_dict = manager.dict()
        processes = []
        for free_agent in possible.name:
            new_rosters = rosters.loc[rosters.name != my_player].append(\
            available.loc[available.name == free_agent],ignore_index=True,sort=False)
            new_rosters.loc[new_rosters.name == free_agent,'fantasy_team'] = team_name
            p = multiprocessing.Process(target=season_sims_mp,\
            args=(free_agent,possible.name.tolist().index(free_agent),\
            new_rosters.copy(),schedule.copy(),num_sims,False,as_of,\
            postseason,homeawayoppqb,payouts))
            processes.append(p)
            p.start()
        for process in processes:
            process.join()
        for free_agent in return_dict.keys():
            added_value = added_value.append(return_dict[free_agent].loc[return_dict[free_agent].team == team_name],ignore_index=True)
            added_value.loc[added_value.shape[0] - 1,'player_to_drop'] = my_player
            added_value.loc[added_value.shape[0] - 1,'player_to_add'] = free_agent
        
        """ JUST FOR A PROGRESS REPORT!!! """
        if verbose:
            temp = added_value.iloc[-1*len(return_dict.keys()):][['player_to_drop','player_to_add','earnings']]
            temp['earnings'] -= orig_standings.loc[orig_standings.team == team_name,'earnings'].values[0]
            if temp.shape[0] > 0:
                print(temp)
            del temp
        """ JUST FOR A PROGRESS REPORT!!! """
        
    if added_value.shape[0] > 0:
        for col in ['wins_avg','wins_stdev','points_avg','points_stdev',\
        'playoffs','playoff_bye'] + (['winner','runner_up','third','earnings'] if postseason else[]):
            added_value[col] -= orig_standings.loc[orig_standings.team == team_name,col].values[0]
            added_value[col] = round(added_value[col],4)
        added_value = added_value.sort_values(by='winner' if postseason else 'playoffs',ascending=False)
    return added_value

def possible_adds(rosters,available,schedule,as_of=None,num_sims=1000,\
focus_on=[],exclude=[],limit_per=10,team_name=None,postseason=True,\
verbose=True,homeawayoppqb=[1,1,0,0],payouts=[800,300,100]):
    global return_dict
    orig_standings = season_sims(rosters,schedule,num_sims,False,as_of,\
    postseason=postseason,homeawayoppqb=homeawayoppqb,payouts=payouts)[1]
    added_value = pd.DataFrame(columns=['player_to_add','wins_avg','wins_stdev',\
    'points_avg','points_stdev','per_game_avg','per_game_stdev','per_game_fano',\
    'playoffs','playoff_bye'] + (['winner','runner_up','third','earnings'] if postseason else []))
    if not team_name:
        team_name = 'Team Jacquet'
    possible = available.loc[~available.name.str.contains('Average_')]
    if possible.name.isin(focus_on).sum() > 0:
        possible = possible.loc[possible.name.isin(focus_on)]
    if possible.name.isin(exclude).sum() > 0:
        possible = possible.loc[~possible.name.isin(exclude)]
    possible = possible.groupby('position').head(limit_per)
    manager = multiprocessing.Manager()
    return_dict = manager.dict()
    processes = []
    for free_agent in possible.name:
        new_rosters = rosters.append(available.loc[available.name == free_agent],ignore_index=True,sort=False)
        new_rosters.loc[new_rosters.name == free_agent,'fantasy_team'] = team_name
        p = multiprocessing.Process(target=season_sims_mp,\
        args=(free_agent,possible.name.tolist().index(free_agent),\
        new_rosters.copy(),schedule.copy(),num_sims,False,as_of,\
        postseason,homeawayoppqb,payouts))
        processes.append(p)
        p.start()
    for process in processes:
        process.join()
    for free_agent in return_dict.keys():
        added_value = added_value.append(return_dict[free_agent].loc[return_dict[free_agent].team == team_name],ignore_index=True)
        added_value.loc[added_value.shape[0] - 1,'player_to_add'] = free_agent
        added_value.loc[added_value.shape[0] - 1,'position'] = possible.loc[possible.name == free_agent,'position'].values[0]
        added_value.loc[added_value.shape[0] - 1,'current_team'] = possible.loc[possible.name == free_agent,'current_team'].values[0]
    
    """ JUST FOR A PROGRESS REPORT!!! """
    if verbose:
        temp = added_value.iloc[-1*len(return_dict.keys()):][['player_to_add','earnings']]
        temp['earnings'] -= orig_standings.loc[orig_standings.team == team_name,'earnings'].values[0]
        if temp.shape[0] > 0:
            print(temp)
        del temp
    """ JUST FOR A PROGRESS REPORT!!! """
    
    if added_value.shape[0] > 0:
        for col in ['wins_avg','wins_stdev','points_avg','points_stdev',\
        'playoffs','playoff_bye'] + (['winner','runner_up','third','earnings'] if postseason else[]):
            added_value[col] -= orig_standings.loc[orig_standings.team == team_name,col].values[0]
            added_value[col] = round(added_value[col],4)
        added_value = added_value.sort_values(by='winner' if postseason else 'playoffs',ascending=False)
    return added_value

def possible_drops(rosters,schedule,as_of=None,num_sims=1000,focus_on=[],\
exclude=[],team_name=None,postseason=True,verbose=True,homeawayoppqb=[1,1,0,0],payouts=[800,300,100]):
    global return_dict
    orig_standings = season_sims(rosters,schedule,num_sims,False,as_of,\
    postseason=postseason,homeawayoppqb=homeawayoppqb,payouts=payouts)[1]
    reduced_value = pd.DataFrame(['player_to_drop','wins_avg','wins_stdev',\
    'points_avg','points_stdev','per_game_avg','per_game_stdev','per_game_fano',\
    'playoffs','playoff_bye'] + (['winner','runner_up','third','earnings'] if postseason else []))
    if not team_name:
        team_name = 'Team Jacquet'
    players_to_drop = rosters.loc[rosters.fantasy_team == team_name]
    if players_to_drop.name.isin(focus_on).sum() > 0:
        players_to_drop = players_to_drop.loc[players_to_drop.name.isin(focus_on)]
    if players_to_drop.name.isin(exclude).sum() > 0:
        players_to_drop = players_to_drop.loc[~players_to_drop.name.isin(exclude)]
    manager = multiprocessing.Manager()
    return_dict = manager.dict()
    processes = []
    for my_player in players_to_drop.name:
        new_rosters = rosters.loc[rosters.name != my_player]
        p = multiprocessing.Process(target=season_sims_mp,\
        args=(my_player,players_to_drop.name.tolist().index(my_player),\
        new_rosters.copy(),schedule.copy(),num_sims,False,as_of,\
        postseason,homeawayoppqb,payouts))
        processes.append(p)
        p.start()
    for process in processes:
        process.join()
    for my_player in return_dict.keys():
        reduced_value = reduced_value.append(return_dict[my_player].loc[return_dict[my_player].team == team_name],ignore_index=True)
        reduced_value.loc[reduced_value.shape[0] - 1,'player_to_drop'] = my_player
    
    """ JUST FOR A PROGRESS REPORT!!! """
    if verbose:
        temp = reduced_value.iloc[-1*len(return_dict.keys()):][['player_to_drop','earnings']]
        temp['earnings'] -= orig_standings.loc[orig_standings.team == team_name,'earnings'].values[0]
        if temp.shape[0] > 0:
            print(temp)
        del temp
    """ JUST FOR A PROGRESS REPORT!!! """
    
    if reduced_value.shape[0] > 0:
        for col in ['wins_avg','wins_stdev','points_avg','points_stdev',\
        'playoffs','playoff_bye'] + (['winner','runner_up','third','earnings'] if postseason else []):
            reduced_value[col] -= orig_standings.loc[orig_standings.team == team_name,col].values[0]
            reduced_value[col] = round(reduced_value[col],4)
        reduced_value = reduced_value.sort_values(by='winner' if postseason else 'playoffs',ascending=False)
    return reduced_value

def possible_trades(rosters,schedule,as_of=None,num_sims=1000,focus_on=[],\
exclude=[],given=[],limit_per=10,team_name=None,postseason=True,verbose=True,\
homeawayoppqb=[1,1,0,0],payouts=[800,300,100]):
    global return_dict
    if not team_name:
        team_name = 'Team Jacquet'
    my_players = rosters.loc[(rosters.fantasy_team == team_name) & ~rosters.position.isin(['K','DEF'])]
    if my_players.name.isin(focus_on).sum() > 0:
        my_players = my_players.loc[my_players.name.isin(focus_on)]
    if my_players.name.isin(exclude).sum() > 0:
        my_players = my_players.loc[~my_players.name.isin(exclude)]
    their_players = rosters.loc[(rosters.fantasy_team != team_name) & ~rosters.position.isin(['K','DEF'])]
    if their_players.name.isin(focus_on).sum() > 0:
        their_players = their_players.loc[their_players.name.isin(focus_on)]
    if their_players.name.isin(exclude).sum() > 0:
        their_players = their_players.loc[~their_players.name.isin(exclude)]
    orig_standings = season_sims(rosters,schedule,num_sims,False,as_of,\
    postseason=postseason,homeawayoppqb=homeawayoppqb,payouts=payouts)[1]
    
    """ Make sure there are two teams and narrow down to that team!!! """
    if type(given) == list and my_players.name.isin(given).any() \
    and their_players.loc[their_players.name.isin(given),'fantasy_team'].unique().shape[0] == 1:
        mine = [player for player in given if my_players.name.isin([player]).any()]
        theirs = [player for player in given if their_players.name.isin([player]).any()]
        their_team = rosters.loc[rosters.name.isin(theirs),'fantasy_team'].values[0]
        rosters.loc[rosters.name.isin(mine),'fantasy_team'] = their_team
        rosters.loc[rosters.name.isin(theirs),'fantasy_team'] = team_name
        my_players = my_players.loc[~my_players.name.isin(given)]
        their_players = their_players.loc[(their_players.fantasy_team == their_team) & ~their_players.name.isin(given)]
        my_players['WAR'] = 0.0
        their_players['WAR'] = 0.0
    """ Make sure there are two teams and narrow down to that teams!!! """
    
    my_added_value = pd.DataFrame()
    their_added_value = pd.DataFrame()
    for my_player in my_players.name:
        possible = their_players.loc[abs(their_players.WAR - my_players.loc[my_players.name == my_player,'WAR'].values[0]) <= 0.25]
#        possible = their_players.loc[their_players.WAR - my_players.loc[my_players.name == my_player,'WAR'].values[0] > 0.0]
        if verbose:
            print(my_player + ': ' + str(possible.shape[0]) + ' comparable players')
            print(datetime.datetime.now())
        possible = possible.groupby('position').head(limit_per)
        manager = multiprocessing.Manager()
        return_dict = manager.dict()
        processes = []
        for their_player in possible.name:
            their_team = rosters.loc[rosters.name == their_player,'fantasy_team'].values[0]
            rosters.loc[rosters.name == my_player,'fantasy_team'] = their_team
            rosters.loc[rosters.name == their_player,'fantasy_team'] = team_name
            p = multiprocessing.Process(target=season_sims_mp,\
            args=(their_player,possible.name.tolist().index(their_player),\
            rosters.copy(),schedule.copy(),num_sims,False,as_of,postseason,homeawayoppqb,payouts))
            processes.append(p)
            p.start()
            rosters.loc[rosters.name == my_player,'fantasy_team'] = team_name
            rosters.loc[rosters.name == their_player,'fantasy_team'] = their_team
        for process in processes:
            process.join()
        for their_player in return_dict.keys():
            their_team = rosters.loc[rosters.name == their_player,'fantasy_team'].values[0]
            my_added_value = my_added_value.append(return_dict[their_player].loc[return_dict[their_player].team == team_name],ignore_index=True)
            their_added_value = their_added_value.append(return_dict[their_player].loc[return_dict[their_player].team == their_team],ignore_index=True)
            my_added_value.loc[my_added_value.shape[0] - 1,'player_to_trade_away'] = my_player
            my_added_value.loc[my_added_value.shape[0] - 1,'player_to_trade_for'] = their_player
            their_added_value.loc[their_added_value.shape[0] - 1,'player_to_trade_away'] = my_player
            their_added_value.loc[their_added_value.shape[0] - 1,'player_to_trade_for'] = their_player
        
        """ JUST FOR A PROGRESS REPORT!!! """
        if verbose and len(return_dict.keys()) > 0:
            me = my_added_value.iloc[-1*len(return_dict.keys()):][['player_to_trade_away','player_to_trade_for','earnings']].rename(columns={'earnings':'my_earnings'})
            them = their_added_value.iloc[-1*len(return_dict.keys()):][['player_to_trade_away','player_to_trade_for','team','earnings']].rename(columns={'earnings':'their_earnings'})
            me['my_earnings'] -= orig_standings.loc[orig_standings.team == team_name,'earnings'].values[0]
            for their_team in them.team.unique():
                them.loc[them.team == their_team,'their_earnings'] -= orig_standings.loc[orig_standings.team == their_team,'earnings'].values[0]
            temp = pd.merge(left=me,right=them,how='inner',on=['player_to_trade_away','player_to_trade_for'])
            if temp.shape[0] > 0:
                print(temp)
            del me, them, temp, their_team
        """ JUST FOR A PROGRESS REPORT!!! """
        
    for col in ['wins_avg','wins_stdev','points_avg','points_stdev',\
    'per_game_avg','per_game_stdev','per_game_fano','playoffs','playoff_bye'] + \
    (['winner','runner_up','third','earnings'] if postseason else []):
        my_added_value[col] -= orig_standings.loc[orig_standings.team == team_name,col].values[0]
        my_added_value[col] = round(my_added_value[col],4)
    for their_team in their_added_value.team.unique():
        for col in ['wins_avg','wins_stdev','points_avg','points_stdev',\
        'per_game_avg','per_game_stdev','per_game_fano','playoffs','playoff_bye'] + \
        (['winner','runner_up','third','earnings'] if postseason else []):
            their_added_value.loc[their_added_value.team == their_team,col] -= \
            orig_standings.loc[orig_standings.team == their_team,col].values[0]
            their_added_value[col] = round(their_added_value[col],4)
    for col in ['team','wins_avg','wins_stdev','points_avg','points_stdev',\
    'per_game_avg','per_game_stdev','per_game_fano','playoffs','playoff_bye'] + \
    (['winner','runner_up','third','earnings'] if postseason else []):
        my_added_value = my_added_value.rename(index=str,columns={col:'my_' + col})
        their_added_value = their_added_value.rename(index=str,columns={col:'their_' + col})
    added_value = pd.merge(left=my_added_value,right=their_added_value,\
    how='inner',on=['player_to_trade_away','player_to_trade_for'])
    added_value = added_value.sort_values(by='my_winner' if postseason else 'playoffs',ascending=False)
    return added_value

def perGameDelta(rosters,schedule,as_of=None,num_sims=1000,team_name=None,\
postseason=True,homeawayoppqb=[1,1,0,0],payouts=[800,300,100]):
    if not team_name:
        team_name = 'Team Jacquet'
    deltas = season_sims(rosters,schedule,num_sims,False,as_of,postseason=postseason,\
    homeawayoppqb=homeawayoppqb,payouts=payouts)[1][['team','earnings']]
    for team in rosters.fantasy_team.unique():
        new_standings = season_sims(rosters,schedule,num_sims,False,as_of,postseason=postseason,\
        homeawayoppqb=homeawayoppqb,payouts=payouts,fixed_winner=[as_of%100,team])[1]\
        [['team','earnings']].rename(columns={'earnings':'earnings_new'})
        deltas = pd.merge(left=deltas,right=new_standings,how='inner',on='team')
        deltas[team] = deltas['earnings_new'] - deltas['earnings']
        del deltas['earnings_new']
        print(deltas[['team',team]])
    del deltas['earnings']
    return deltas.set_index('team').T.reset_index().rename(columns={'index':'winner'})

def sendEmail(subject,body,address,filename=None):
    message = MIMEMultipart()
    message["From"] = emailcreds.sender
    message["To"] = address
    message["Subject"] = subject
    message.attach(MIMEText(body + '\n\n', "plain"))
    if filename and os.path.exists(str(filename)):
        with open(filename, "rb") as attachment:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(attachment.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition","attachment; filename= " + filename.split('/')[-1])
        message.attach(part)
    text = message.as_string()
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com",465,context=context) as server:
        server.login(emailcreds.sender,emailcreds.password)
        server.sendmail(emailcreds.sender,address,text)

def main():
    parser = optparse.OptionParser()
    parser.add_option('--swid',action="store",dest="swid",help="swid credential from ESPN cookies")
    parser.add_option('--espn_s2',action="store",dest="espn_s2",help="espn_s2 credential from ESPN cookies")
    parser.add_option('--league_id',action="store",dest="league_id",help="league id from ESPN url")
    parser.add_option('--name',action="store",dest="name",help="name of team to analyze in the case of multiple teams in a single season")
    parser.add_option('--earliest',action="store",dest="earliest",help="earliest week of stats being considered, e.g. 201807 corresponds to week 7 of the 2018 season")
    parser.add_option('--as_of',action="store",dest="as_of",help="week to project the season from, e.g. 201912 corresponds to week 12 of the 2019 season")
    parser.add_option('--games',action="store",dest="games",help="number of games to build each player's prior off of")
    parser.add_option('--timefactor',action="store",dest="timefactor",help="scaling factor for how heavily a game is weighted based on how long ago it was")
    parser.add_option('--homeawayoppqb',action="store",dest="homeawayoppqb",help="scaling factors for home/away/opposition/quarterback factors, comma-separated string of values")
    parser.add_option('--sims',action="store",dest="sims",help="number of season simulations")
    parser.add_option('--payouts',action="store",dest="payouts",help="comma separated string containing integer payouts for 1st, 2nd, and 3rd")
    parser.add_option('--pickups',action="store",dest="pickups",help='assess possible free agent pickups for the players specified ("all" will analyze all possible pickups)')
    parser.add_option('--adds',action="store_true",dest="adds",help="whether to assess possible free agent adds")
    parser.add_option('--drops',action="store_true",dest="drops",help="whether to assess possible drops")
    parser.add_option('--trades',action="store",dest="trades",help='assess possible trades for the players specified ("all" will analyze all possible trades)')
    parser.add_option('--deltas',action="store_true",dest="deltas",help="whether to assess deltas for each matchup of the current week")
    parser.add_option('--output',action="store",dest="output",help="where to save the final projections spreadsheet")
    parser.add_option('--email',action="store",dest="email",help="where to send the final projections spreadsheet")
    options,args = parser.parse_args()
    if not options.swid:
        options.swid = '{C75B8A79-DF90-4687-B360-D5E6DEDF99E4}'
    if not options.espn_s2:
        options.espn_s2 = 'AEBQR4NbPsyPB03sZiUAHWTTdZ5mTI8yRUL3mqoUr0g4t%2Bg2g95cfMd11tI%2BefXl' + \
        'jV35ByoBZSTiRV5RVkiDxJFAzVwOWG1Sbff4EpBe74PY85G2HxKjfjyqJPiHleJq7Vbn2qB%2BvCbQ' + \
        'xU3C%2FV8mp39P2x6KJxb%2FK5oQ3B8UbXEBAyxpWwBAnQJ9%2BNMI2dEnlJxaWfq%2F6ZEkcNBzCl' + \
        'h8BEaLNBiEhP%2FGp67Iz%2B1AvwnJaQyZ5EtZ0Dq6yP1EpaMUxqWq%2BBXWgXvIZufOpp0%2FrQB0' + \
        'xGDFhSLjVg0UDOomWdW9sGvGIRAONKaRlIhjqgnMeOE%3D'
    if not options.league_id:
        options.league_id = 1575798984
    cookie_creds = {'SWID':options.swid,'espn_s2':options.espn_s2}
    if not options.as_of:
        get_settings(options.league_id,latest_season,cookie_creds)
        options.as_of = 100*latest_season + current_week
    else:
        get_settings(options.league_id,options.as_of//100,cookie_creds)
    if not options.name:
        options.name = 'Team Jacquet'
    if not options.earliest:
        options.earliest = int(options.as_of) - 106 # Optimal values
        if (options.earliest%100 == 0) | (options.earliest%100 > 50):
            options.earliest -= 83
    if not options.games:
        options.games = 27 # Optimal values
    if not options.timefactor:
        options.timefactor = 0.0021 # Optimal values
    if options.homeawayoppqb:
        options.homeawayoppqb = options.homeawayoppqb.split(',')
        if len(options.homeawayoppqb) > 4:
            print('Too many scaling factors provided... Using optimal values...')
            options.homeawayoppqb = [0.1617,0.1428,0.8130,0.06988] # Optimal values
        elif len(options.homeawayoppqb) < 4:
            print('Not enough scaling factors provided... Using optimal values...')
            options.homeawayoppqb = [0.1617,0.1428,0.8130,0.06988] # Optimal values
        else:
            try:
                options.homeawayoppqb = [float(val) for val in options.homeawayoppqb]
            except:
                print('Non-numeric scaling factors provided... Using optimal values')
                options.homeawayoppqb = [0.1617,0.1428,0.8130,0.06988] # Optimal values
    else:
        options.homeawayoppqb = [0.1617,0.1428,0.8130,0.06988] # Optimal values
    if not options.sims:
        options.sims = 10000
    if options.payouts:
        options.payouts = options.payouts.split(',')
        if all([val.isnumeric() for val in options.payouts]):
            options.payouts = [float(val) for val in options.payouts]
        else:
            print('Weird values provided for payouts... Assuming standard payouts...')
            options.payouts = [700,200,100]
        if len(options.payouts) > 3:
            print('Too many values provided for payouts... Only using top three...')
            options.payouts = options.payouts[:3]
    elif options.name == 'The Algorithm':
        options.payouts = [800,300,100]
    elif options.name == 'Toothless Wonders':
        options.payouts = [350,100,50]
    elif options.name == 'The GENIEs':
        options.payouts = [70,0,0]
    else:
        options.payouts = [700,200,100]
    if not options.output:
        options.output = os.path.expanduser('~/Documents/') if os.path.exists(os.path.expanduser('~/Documents/')) else os.path.expanduser('~/')
        if not os.path.exists(options.output + options.name.replace(' ','')):
            os.mkdir(options.output + options.name.replace(' ',''))
        if not os.path.exists(options.output + options.name.replace(' ','') + '/' + str(options.as_of//100)):
            os.mkdir(options.output + options.name.replace(' ','') + '/' + str(options.as_of//100))
        options.output += options.name.replace(' ','') + '/' + str(options.as_of//100)
    if options.output[-1] != '/':
        options.output += '/'
    
    by_player = get_players(options.league_id,options.as_of//100,cookie_creds)
    fantasy_schedule = get_schedule(options.league_id,options.as_of//100,cookie_creds)
    
    writer = pd.ExcelWriter(options.output + 'FantasyFootballProjections_{}Week{}.xlsx'\
    .format(datetime.datetime.now().strftime('%A'),options.as_of%100),engine='xlsxwriter')
    writer.book.add_format({'align': 'vcenter'})
    
    """ Duplicate name issues... """
    by_player = by_player.loc[by_player.editorial_team_abbr.isin(['TB','Sea']) | \
    ~by_player.name.isin(['Ryan Griffin','Josh Johnson'])]
    """ Duplicate name issues... """
    
    by_player = get_rates(by_player,int(options.earliest),int(options.as_of),int(options.sims),int(options.games),options.timefactor,None,True)
    by_player = pd.merge(left=by_player,right=bye_weeks(latest_season),how='left',on='current_team')
    by_player = add_injuries(by_player,options.as_of)
    
#    """ TESTING OUT SITTING EVERYBODY FOR WEEK 14 """
#    """ TESTING OUT SITTING EVERYBODY FOR WEEK 14 """
#    """ TESTING OUT SITTING EVERYBODY FOR WEEK 14 """
#    by_player.loc[(by_player.fantasy_team == options.name) & \
#    (by_player.until.isnull() | (by_player.until < 14)),'until'] = 14
#    """ TESTING OUT SITTING EVERYBODY FOR WEEK 14 """
#    """ TESTING OUT SITTING EVERYBODY FOR WEEK 14 """
#    """ TESTING OUT SITTING EVERYBODY FOR WEEK 14 """
    
    if (by_player.current_team.isnull() & ~by_player.name.str.contains('Average_')).sum() > 0:
        print(str((by_player.current_team.isnull() & ~by_player.name.str.contains('Average_')).sum()) + " players' teams cannot be identified...")
    
    by_player = by_player.loc[~by_player.current_team.isnull() | by_player.name.str.contains('Average_')].reset_index(drop=True)
    
    if by_player.loc[~by_player.name.str.contains('Average_')].groupby('name').size().max() > 1:
        print('Some players are being duplicated...')
        repeats = by_player.loc[~by_player.name.str.contains('Average_')].groupby('name').size().to_frame('freq').reset_index()
        print(repeats.loc[repeats.freq > 1,'name'].tolist())
    rosters = by_player.loc[~by_player.fantasy_team.isnull()].sort_values(by=['fantasy_team','WAR'],ascending=[True,False])
    rosters_weighted = starters(rosters,options.as_of%100,options.as_of,options.homeawayoppqb)
    for col in ['points_avg','points_stdev','WAR','homeaway_factor','opp_factor','qb_factor']:
        rosters_weighted[col] = round(rosters_weighted[col],3)
    writer = excelAutofit(rosters_weighted[['name','position','current_team',\
    'points_avg','points_stdev','WAR','fantasy_team','num_games','homeaway_factor',\
    'opp_factor','qb_factor','status','bye_week','until','starter','injured']],'Rosters',writer)
    writer.sheets['Rosters'].freeze_panes(1,1)
    writer.sheets['Rosters'].conditional_format('F2:F' + str(rosters_weighted.shape[0] + 1),\
    {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
    available = by_player.loc[by_player.fantasy_team.isnull() & \
    (by_player.until.isnull() | (by_player.until < 17))].sort_values(by='WAR',ascending=False)
    del available['fantasy_team']
    
    """ WEIGHT AVAILABLE PLAYERS SCORES TOO!!! """
    available_weighted = pd.merge(left=available,right=nfl_schedule.loc[(nfl_schedule.season == options.as_of//100) & \
    (nfl_schedule.week == options.as_of%100)],how='left',left_on='current_team',right_on='abbrev')
    available_weighted.loc[available_weighted.home_away == 'Home','homeaway_factor'] = options.homeawayoppqb[0]
    available_weighted.loc[available_weighted.home_away == 'Away','homeaway_factor'] = options.homeawayoppqb[1]
    available_weighted['opp_factor'] = options.homeawayoppqb[2]*available_weighted['opp_elo']
    available_weighted['qb_factor'] = options.homeawayoppqb[3]*available_weighted['qb_elo']
    available_weighted['points_avg'] *= (available_weighted['homeaway_factor'] + available_weighted['opp_factor'] + available_weighted['qb_factor'])
    for col in ['points_avg','points_stdev','WAR','homeaway_factor','opp_factor','qb_factor']:
        available_weighted[col] = round(available_weighted[col],3)
    """ WEIGHT AVAILABLE PLAYERS SCORES TOO!!! """
    
    writer = excelAutofit(available_weighted[['name','position','current_team',\
    'points_avg','points_stdev','WAR','num_games','homeaway_factor','opp_factor',\
    'qb_factor','status','bye_week','until']],'Available',writer)
    writer.sheets['Available'].freeze_panes(1,1)
    writer.sheets['Available'].conditional_format('F2:F' + str(available_weighted.shape[0] + 1),\
    {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
    
    schedule_sim, standings_sim = season_sims(rosters,fantasy_schedule,options.sims,\
    True,options.as_of,homeawayoppqb=options.homeawayoppqb,payouts=options.payouts)
    
    """ JUST FOR A PROGRESS REPORT!!! """
    print(schedule_sim.loc[schedule_sim.week == current_week,\
    ['week','team_1','team_2','win_1','win_2','points_avg_1','points_avg_2']])
    print(standings_sim[['team','wins_avg','points_avg','playoffs','playoff_bye','winner','earnings']])
    """ JUST FOR A PROGRESS REPORT!!! """
    
    writer = excelAutofit(schedule_sim[['week','team_1','team_2','win_1','win_2',\
    'points_avg_1','points_stdev_1','points_avg_2','points_stdev_2','me']],'Schedule',writer)
    writer.sheets['Schedule'].freeze_panes(1,3)
    writer.sheets['Schedule'].conditional_format('D2:E' + str(schedule_sim.shape[0] + 1),\
    {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
    writer = excelAutofit(standings_sim[['team','wins_avg','wins_stdev',\
    'points_avg','points_stdev','per_game_avg','per_game_stdev','per_game_fano',\
    'playoffs','playoff_bye','winner','runner_up','third','earnings']],'Standings',writer)
    writer.sheets['Standings'].freeze_panes(1,1)
    writer.sheets['Standings'].conditional_format('I2:M' + str(standings_sim.shape[0] + 1),\
    {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
    writer.sheets['Standings'].conditional_format('N2:N' + str(standings_sim.shape[0] + 1),\
    {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
    
    if options.pickups:
        pickups = possible_pickups(rosters,available,fantasy_schedule,options.as_of,1000,\
        focus_on=[val.strip() for val in options.pickups.split(',')] if options.pickups.lower() != 'all' else [],\
        exclude=['Kirk Cousins','DeAndre Hopkins','Cole Beasley','Deshaun Watson','Gardner Minshew II','Carson Wentz','Drew Brees'],\
        limit_per=5,homeawayoppqb=options.homeawayoppqb,payouts=options.payouts)
        writer = excelAutofit(pickups[['player_to_drop','player_to_add','wins_avg','wins_stdev',\
        'points_avg','points_stdev','per_game_avg','per_game_stdev','per_game_fano',\
        'playoffs','playoff_bye','winner','runner_up','third','earnings']],'Pickups',writer)
        writer.sheets['Pickups'].freeze_panes(1,2)
        writer.sheets['Pickups'].conditional_format('J2:N' + str(pickups.shape[0] + 1),\
        {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
        writer.sheets['Pickups'].conditional_format('O2:O' + str(pickups.shape[0] + 1),\
        {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
    
    if options.adds:
        adds = possible_adds(rosters,available,fantasy_schedule,int(options.as_of),\
        1000,exclude=['Kirk Cousins','DeAndre Hopkins','Cole Beasley','Deshaun Watson','Gardner Minshew II','Carson Wentz','Drew Brees'],\
        limit_per=5,homeawayoppqb=options.homeawayoppqb,payouts=options.payouts)
        writer = excelAutofit(adds[['player_to_add','wins_avg','wins_stdev',\
        'points_avg','points_stdev','per_game_avg','per_game_stdev','per_game_fano',\
        'playoffs','playoff_bye','winner','runner_up','third','earnings']],'Adds',writer)
        writer.sheets['Adds'].freeze_panes(1,1)
        writer.sheets['Adds'].conditional_format('J2:N' + str(adds.shape[0] + 1),\
        {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
        writer.sheets['Adds'].conditional_format('O2:O' + str(adds.shape[0] + 1),\
        {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
    
    if options.drops:
        drops = possible_drops(rosters,fantasy_schedule,int(options.as_of),\
        1000,homeawayoppqb=options.homeawayoppqb,payouts=options.payouts)
        writer = excelAutofit(drops[['player_to_drop','wins_avg','wins_stdev',\
        'points_avg','points_stdev','per_game_avg','per_game_stdev','per_game_fano',\
        'playoffs','playoff_bye','winner','runner_up','third','earnings']],'Drops',writer)
        writer.sheets['Drops'].freeze_panes(1,1)
        writer.sheets['Drops'].conditional_format('J2:N' + str(drops.shape[0] + 1),\
        {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
        writer.sheets['Drops'].conditional_format('O2:O' + str(drops.shape[0] + 1),\
        {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
    
    if options.trades:
        trades = possible_trades(rosters,fantasy_schedule,int(options.as_of),1000,\
        focus_on=[val.strip() for val in options.trades.split(',')] if options.trades.lower() != 'all' else [],\
        exclude=['Kirk Cousins','DeAndre Hopkins','Cole Beasley','Deshaun Watson','Gardner Minshew II','Carson Wentz'],\
        limit_per=5,homeawayoppqb=options.homeawayoppqb,payouts=options.payouts)
#        trades = possible_trades(rosters,fantasy_schedule,int(options.as_of),1000,\
#        focus_on=['Amari Cooper','Deebo Samuel','Keenan Allen','Mike Williams',\
#        'Curtis Samuel','Travis Fulgham'],exclude=['Kirk Cousins','DeAndre Hopkins',\
#        'Cole Beasley','Deshaun Watson'],limit_per=5,homeawayoppqb=options.homeawayoppqb,payouts=options.payouts)
        writer = excelAutofit(trades[['player_to_trade_away','player_to_trade_for',\
        'their_team','my_wins_avg','my_wins_stdev','my_points_avg','my_points_stdev',\
        'my_per_game_avg','my_per_game_stdev','my_per_game_fano','my_playoffs',\
        'my_playoff_bye','my_winner','my_runner_up','my_third','my_earnings',\
        'their_wins_avg','their_wins_stdev','their_points_avg','their_points_stdev',\
        'their_per_game_avg','their_per_game_stdev','their_per_game_fano',\
        'their_playoffs','their_playoff_bye','their_winner','their_runner_up',\
        'their_third','their_earnings']],'Trades',writer)
        writer.sheets['Trades'].freeze_panes(1,3)
        writer.sheets['Trades'].conditional_format('K2:O' + str(trades.shape[0] + 1),\
        {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
        writer.sheets['Trades'].conditional_format('P2:P' + str(trades.shape[0] + 1),\
        {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
        writer.sheets['Trades'].conditional_format('X2:AB' + str(trades.shape[0] + 1),\
        {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
        writer.sheets['Trades'].conditional_format('AC2:AC' + str(trades.shape[0] + 1),\
        {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
    
    if options.deltas:
        deltas = perGameDelta(rosters,fantasy_schedule,int(options.as_of),\
        1000,homeawayoppqb=options.homeawayoppqb,payouts=options.payouts)
        writer = excelAutofit(deltas,'Deltas',writer)
        writer.sheets['Deltas'].freeze_panes(0,1)
        writer.sheets['Deltas'].conditional_format('B2:' + chr(ord('A') + deltas.shape[1]) + str(deltas.shape[0] + 1),\
        {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
    
    writer.save()
    os.system('touch -t {} {}'.format(datetime.datetime.now().strftime('%Y%m%d%H%M'),'/'.join(options.output.split('/')[:-2])))
    if options.email:
        try:
            sendEmail('Fantasy Football Projections for ' + options.name,\
            'Best of luck to you this fantasy football season!!!',options.email,\
            options.output + 'FantasyFootballProjections_{}Week{}.xlsx'\
            .format(datetime.datetime.now().strftime('%A'),options.as_of%100))
        except:
            print("Couldn't email results, maybe no wifi...\nResults saved to " + \
            options.output + 'FantasyFootballProjections_{}Week{}.xlsx'\
            .format(datetime.datetime.now().strftime('%A'),options.as_of%100))

if __name__ == "__main__":
    main()




