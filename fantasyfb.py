#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Sep  7 19:09:47 2019

@author: tefirman
"""

import pandas as pd
import os
import shutil
import numpy as np
from sportsipy.nfl.boxscore import Boxscore, Boxscores
import time
import datetime
from pytz import timezone
import optparse
from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa
import json
import requests
import smtplib, ssl
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv
import traceback
import warnings
warnings.filterwarnings("ignore")

class League:
    """
    League class that gathers all relevant settings and statistics 
    to simulate and assess the fantasy league in question.

    Attributes:
        season: integer specifying the season of interest.
        week: integer specifiying the week of interest.
        oauth: yahoo_oauth object contain user credentials and auth tokens
        lg: yahoo_fantasy_api league object used to connect to Yahoo's API
        gm: yahoo_fantasy_api game object used to connect to Yahoo's API
        name: string specifying the name of the fantasy to be analyzed
        settings: dictionary containing the scheduling and roster settings for the league in question
        scoring: dictionary containing the scoring categories and values for the league in question
        teams: list of dictionaries containing identifiers for each fantasy team in the league
        nfl_teams: dataframe containing different identifiers for each NFL team
        nfl_schedule: dataframe containing NFL schedules throughout the years with elo statistics for both teams
        players: dataframe containing demographics and rates for current NFL players
        num_sims: integer specifying the number of Monte Carlo simulations to run
        earliest: integer describing the earliest week to pull statistics from (YYYYWW)
        reference_games: integer describing the number of games to use as a prior for rates
        basaloppqbtime: list of the four weighting factors when calculating rates
        schedule: dataframe containing the fantasy schedule for the league and season in question
    """
    def __init__(self, name=None, season=None, week=None, roster_pcts=False, injurytries=10,
    num_sims=10000, earliest=None, reference_games=None, basaloppqbtime=[]):
        """
        Initializes a League object using the parameters provided and class functions defined below.

        Args:
            name (str, optional): string describing the name of the fantasy team in question, defaults to None.
            season (int, optional): integer specifying the season of interest, defaults to None.
            week (int, optional): integer specifiying the week of interest, defaults to None.
            roster_pcts (bool, optional): boolean that triggers whether to pull roster percentages, defaults to False.
            injurytries (int, optional): integer specifying the number of attempts to pull injury statuses, defaults to 10.
            num_sims (int, optional): integer specifying the number of Monte Carlo simulations to run, defaults to 10000.
            earliest (int, optional): integer describing the earliest week to pull statistics from (YYYYWW), defaults to None.
            reference_games (int, optional): integer describing the number of games to use as a prior for rates, defaults to None.
            basaloppqbtime (list, optional): list of the four weighting factors when calculating rates, defaults to an empty list.
        """
        self.latest_season = datetime.datetime.now().year - int(datetime.datetime.now().month < 7)
        self.season = season if type(season) == int else self.latest_season
        self.load_credentials()
        self.load_oauth()
        self.load_league(name)
        self.week = week if type(week) == int else self.lg.current_week()
        self.load_settings()
        self.load_fantasy_teams()
        self.load_nfl_abbrevs()
        self.load_nfl_schedule()
        self.get_yahoo_players(injurytries)
        self.get_fantasy_rosters()
        self.name_corrections()
        self.load_parameters(earliest,reference_games,basaloppqbtime)
        self.num_sims = num_sims if type(num_sims) == int else 10000
        self.get_rates()
        self.war_sim()
        self.add_injuries()
        self.add_bye_weeks()
        if roster_pcts:
            self.add_roster_pcts()
        self.get_schedule()
        self.starters(self.week)

    def load_credentials(self):
        # Loading Yahoo OAuth credentials from environment variables
        load_dotenv()
        if 'CONSUMER_KEY' not in os.environ \
        or 'CONSUMER_SECRET' not in os.environ:
            print("No valid .env file present, copying from .env.example")
            shutil.copyfile(".env.example", ".env")
        # Updating .env file if default values are still present
        if os.environ['CONSUMER_KEY'] == 'updatekey' \
        and os.environ['CONSUMER_SECRET'] == 'updatesecret':
            # Only have to do this once since we're storing them in environment variables
            print("It appears you haven't updated your Yahoo OAuth credentials...")
            print("To get credentials: https://developer.yahoo.com/apps/create/")
            consumer_key = input("Yahoo OAuth Key: ")
            os.system("sed -i 's/updatekey/{}/g' .env".format(consumer_key))
            consumer_secret = input("Yahoo OAuth Secret: ")
            os.system("sed -i 's/updatesecret/{}/g' .env".format(consumer_secret))
            load_dotenv()
            # Previous oauth file is probably bad if it exists, deleting it just in case
            if os.path.exists('oauth2.json'):
                os.remove('oauth.json')
    
    def load_oauth(self):
        # Creating oauth file from credentials provided
        if not os.path.exists('oauth2.json'):
            creds = {'consumer_key': os.environ['CONSUMER_KEY'],\
                    'consumer_secret': os.environ['CONSUMER_SECRET']}
            with open('oauth2.json', "w") as f:
                f.write(json.dumps(creds))
        self.oauth = OAuth2(None, None, from_file='oauth2.json')

    def load_league(self, name=None):
        # Pulling user's Yahoo fantasy games
        self.gm = yfa.Game(self.oauth,'nfl')
        while True:
            try:
                leagues = self.gm.yhandler.get_teams_raw()['fantasy_content']['users']['0']['user'][1]['games']
                break
            except:
                print('Teams query crapped out... Waiting 30 seconds and trying again...')
                time.sleep(30)
        # Identifying user's NFL Yahoo fantasy games
        for ind in range(leagues['count'] - 1,-1,-1):
            if type(leagues[str(ind)]['game']) == dict:
                continue
            if leagues[str(ind)]['game'][0]['code'] == 'nfl' and leagues[str(ind)]['game'][0]['season'] == str(self.season):
                teams = leagues[str(ind)]['game'][1]['teams']
                details = [teams[str(ind)]['team'][0] for ind in range(teams['count'])]
                names = [[val['name'] for val in team if 'name' in val][0] for team in details]
                if teams['count'] > 1:
                    # If user has more than one team, use the name input or prompt them to pick one
                    while name not in names:
                        print('Found multiple fantasy teams: ' + ', '.join(names))
                        name = input("Which team would you like to analyze? ")
                    team = teams[str(names.index(name))]['team'][0]
                else:
                    # If user has only one team, use that one and override whatever name was given
                    team = teams['0']['team'][0]
                    name = names[0]
                self.name = name
                self.lg_id = '.'.join([val['team_key'] for val in team if 'team_key' in val][0].split('.')[:3])
                break
        # Creating league object
        self.lg = self.gm.to_league(self.lg_id)

    def load_settings(self):
        # Pulling league settings
        self.settings = self.lg.yhandler.get_settings_raw(self.lg_id)['fantasy_content']['league'][1]['settings'][0]
        self.scoring = pd.merge(left=pd.DataFrame([stat['stat'] for stat in self.settings['stat_categories']['stats']]),\
        right=pd.DataFrame([stat['stat'] for stat in self.settings['stat_modifiers']['stats']]),\
        how='inner',on='stat_id')[['display_name','value']].astype({'value':float})
        self.scoring.loc[(self.scoring.display_name == 'Int') & (self.scoring.value <= 0),'display_name'] = 'Int Thrown'
        self.scoring = self.scoring.drop_duplicates(subset=['display_name']).set_index('display_name')
        if 'FG 0-19' not in self.scoring.index:
            self.scoring.loc['FG 0-19','value'] = 3
        if 'Rec' not in self.scoring.index:
            self.scoring.loc['Rec','value'] = 0
    
    def load_fantasy_teams(self):
        # Pulling list of teams in the fantasy league
        league_info = self.lg.yhandler.get_standings_raw(self.lg_id)['fantasy_content']['league']
        teams_info = league_info[1]['standings'][0]['teams']
        self.teams = [{'team_key':teams_info[str(ind)]['team'][0][0]['team_key'],\
        'name':teams_info[str(ind)]['team'][0][2]['name']} for ind in range(teams_info['count'])]
    
    def load_nfl_abbrevs(self):
        try:
            self.nfl_teams = pd.read_csv("https://raw.githubusercontent.com/" + \
            "tefirman/FantasySports/main/res/football/team_abbrevs.csv")
        except:
            raw_teams = [team.split(',') for team in requests.get("https://raw.githubusercontent.com/" + \
            "tefirman/FantasySports/main/res/football/team_abbrevs.csv",verify=False).text.split('\r')]
            self.nfl_teams = pd.DataFrame(raw_teams[1:],columns=raw_teams[0])
    
    def load_nfl_sched_538(self):
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
        self.nfl_schedule_538 = nfl_schedule

    def load_nfl_sched_sportsref(self):
        if self.nfl_schedule_538.season.max() < self.season:
            current_sched = pd.DataFrame()
            games = Boxscores(1,self.season,17).games
            for week in games.keys():
                week_games = pd.DataFrame(games[week])
                week_games['week'] = int(week.split('-')[0])
                current_sched = current_sched.append(week_games.drop_duplicates(),ignore_index=True,sort=False)
            current_sched['season'] = self.season
            current_sched['date'] = pd.to_datetime(current_sched.boxscore.str[:8],infer_datetime_format=True)
            current_sched['home_abbr'] = current_sched['home_abbr'].str.upper()
            current_sched['away_abbr'] = current_sched['away_abbr'].str.upper()
            current_sched = pd.merge(left=current_sched,right=self.nfl_teams.rename(columns={'real_abbrev':'home_abbr',\
            'fivethirtyeight':'home_team'}),how='inner',on='home_abbr')
            current_sched = pd.merge(left=current_sched,right=self.nfl_teams.rename(columns={'real_abbrev':'away_abbr',\
            'fivethirtyeight':'away_team'}),how='inner',on='away_abbr')
            """ Regress last seasons final team elos to the mean??? Merge in best QB from last season??? """
            prev_elos = self.nfl_schedule_538.loc[(self.nfl_schedule_538.season == self.season - 1) & \
            (self.nfl_schedule_538.week == 17),['home_team','home_elo']].rename(columns={'home_team':'team','home_elo':'elo'})\
            .append(self.nfl_schedule_538.loc[(self.nfl_schedule_538.season == self.season - 1) & \
            (self.nfl_schedule_538.week == 17),['away_team','away_elo']]\
            .rename(columns={'away_team':'team','away_elo':'elo'}),ignore_index=True,sort=False)
            prev_elos['elo'] += (1500 - prev_elos['elo'])*0.333 # Regression FiveThirtyEight uses...
            current_sched = pd.merge(left=current_sched,right=prev_elos[['team','elo']]\
            .rename(columns={'team':'home_team','elo':'home_elo'}),how='inner',on=['home_team'])
            current_sched = pd.merge(left=current_sched,right=prev_elos[['team','elo']]\
            .rename(columns={'team':'away_team','elo':'away_elo'}),how='inner',on=['away_team'])
            qb_elos = self.nfl_schedule_538.loc[self.nfl_schedule_538.season == self.season - 1,\
            ['home_team','home_qb']].rename(columns={'home_team':'team','home_qb':'qb_elo'})\
            .append(self.nfl_schedule_538.loc[(self.nfl_schedule_538.season == self.season - 1) & \
            (self.nfl_schedule_538.week == 17),['away_team','away_qb']]\
            .rename(columns={'away_team':'team','away_qb':'qb_elo'}),ignore_index=True,sort=False)
            qb_elos = qb_elos.groupby('team').qb_elo.max().reset_index()
            current_sched = pd.merge(left=current_sched,right=qb_elos[['team','qb_elo']]\
            .rename(columns={'team':'home_team','qb_elo':'home_qb'}),how='inner',on=['home_team'])
            current_sched = pd.merge(left=current_sched,right=qb_elos[['team','qb_elo']]\
            .rename(columns={'team':'away_team','qb_elo':'away_qb'}),how='inner',on=['away_team'])
            self.nfl_schedule_sportsref = current_sched[['season','week','date',\
            'home_team','away_team','home_elo','away_elo','home_qb','away_qb']]
        else:
            self.nfl_schedule_sportsref = pd.DataFrame(columns=['season','week','date',\
            'home_team','away_team','home_elo','away_elo','home_qb','away_qb'])

    def load_nfl_schedule(self):
        self.load_nfl_sched_538()
        self.load_nfl_sched_sportsref()
        nfl_schedule = self.nfl_schedule_538.append(self.nfl_schedule_sportsref,ignore_index=True,sort=False)
        nfl_schedule = pd.merge(left=nfl_schedule,right=self.nfl_teams[['fivethirtyeight','abbrev']],\
        left_on='home_team',right_on='fivethirtyeight',how='inner')
        nfl_schedule.loc[nfl_schedule.home_team != nfl_schedule.abbrev,'home_team'] = \
        nfl_schedule.loc[nfl_schedule.home_team != nfl_schedule.abbrev,'abbrev']
        del nfl_schedule['fivethirtyeight'], nfl_schedule['abbrev']
        nfl_schedule = pd.merge(left=nfl_schedule,right=self.nfl_teams[['fivethirtyeight','abbrev']],\
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
        nfl_schedule.qb_elo = nfl_schedule.qb_elo/157.5
        self.nfl_schedule = nfl_schedule.sort_values(by=['season','week']).reset_index(drop=True)

    def refresh_oauth(self, threshold=59):
        diff = (datetime.datetime.now(timezone('GMT')) - datetime.datetime(1970,1,1,0,0,0,0,\
        timezone('GMT'))).total_seconds() - self.oauth.token_time
        if diff >= threshold*60:
            time.sleep(max(3600 - diff + 5,0))
            self.oauth = OAuth2(None, None, from_file='oauth2.json')
            self.gm = yfa.Game(self.oauth,'nfl')
            self.lg = self.gm.to_league(self.lg_id)

    def get_yahoo_players(self, injurytries=10):
        self.refresh_oauth()
        tries = 0
        while tries < injurytries:
            tries += 1
            players = []
            # Rostered Players
            for page_ind in range(100):
                page = self.lg.yhandler.get("league/{}/players;start={};count=25;status=T/"\
                .format(self.lg_id,page_ind*25))['fantasy_content']['league'][1]['players']
                if page == []:
                    break
                for player_ind in range(page['count']):
                    player = [field for field in page[str(player_ind)]['player'][0] if type(field) == dict]
                    vals = {}
                    for field in player:
                        vals.update(field)
                    vals['name'] = vals['name']['full']
                    vals['eligible_positions'] = [pos['position'] for pos in vals['eligible_positions']]
                    vals['bye_weeks'] = vals['bye_weeks']['week']
                    players.append(vals)
            # Available Players
            for page_ind in range(100):
                """ Accounting for a weird player_id deletion in 2015... """
                page = self.lg.yhandler.get_players_raw(self.lg_id,page_ind*25,'A')['fantasy_content']['league'][1]['players']
                if page == []:
                    break
                for player_ind in range(page['count']):
                    player = [field for field in page[str(player_ind)]['player'][0] if type(field) == dict]
                    vals = {}
                    for field in player:
                        vals.update(field)
                    vals['name'] = vals['name']['full']
                    vals['eligible_positions'] = [pos['position'] for pos in vals['eligible_positions']]
                    vals['bye_weeks'] = vals['bye_weeks']['week']
                    players.append(vals)
            self.players = pd.DataFrame(players)
            self.players.player_id = self.players.player_id.astype(int)
            if not self.players.status.isnull().all():
                break

    def get_fantasy_rosters(self):
        self.refresh_oauth()
        selected = pd.DataFrame(columns=['player_id','selected_position','fantasy_team'])
        for team in self.teams:
            tm = self.lg.to_team(team['team_key'])
            players = pd.DataFrame(tm.roster(self.week))
            if players.shape[0] == 0:
                continue
            if (~players.player_id.isin(self.players.player_id)).any():
                print('Some players are missing... ' + ', '.join(players.loc[~players.player_id.isin(rosters.player_id),'name']))
            players['fantasy_team'] = team['name']
            selected = selected.append(players[['player_id','selected_position','fantasy_team']],ignore_index=True,sort=False)
        rosters = pd.merge(left=self.players,right=selected,how='left',on='player_id')
        if 'fantasy_team' not in rosters.columns:
            rosters['fantasy_team'] = None
        rosters.loc[rosters.player_id == 100014,'name'] += ' Rams'
        rosters.loc[rosters.player_id == 100024,'name'] += ' Chargers'
        rosters.loc[rosters.player_id == 100020,'name'] += ' Jets'
        rosters.loc[rosters.player_id == 100019,'name'] += ' Giants'
        rosters = pd.merge(left=rosters,right=self.nfl_teams[['abbrev','name']],how='left',on='name')
        rosters.loc[~rosters.abbrev.isnull(),'name'] = rosters.loc[~rosters.abbrev.isnull(),'abbrev']
        """ CONVERT THIS LATER TO USE W/R/T ITSELF!!! """
        rosters['position'] = rosters.eligible_positions.apply(lambda x: [pos for pos in x if pos not in ['W/R/T','W/T']])
        inds = rosters.position.apply(len) == 0
        rosters.loc[inds,'position'] = 'TE'
        rosters.loc[~inds,'position'] = rosters.loc[~inds,'position'].apply(lambda x: x[0])
        self.players = rosters[['name','eligible_positions','selected_position','status',
        'player_id','editorial_team_abbr','fantasy_team','position']]

    def get_games_sportsref(self, start:int,finish:int):
        stats = pd.DataFrame(columns=['boxscore','season','week','team','opponent','points_allowed'])
        for season in range(int(start)//100,int(finish)//100 + 1):
            start_week = start%100 if season == start//100 else 1
            end_week = finish%100 if season == finish//100 else 17
            uris = Boxscores(start_week,season,end_week).games
            for week in uris:
                print(week)
                for game in uris[week]:
                    box = Boxscore(game['boxscore'])
                    time.sleep(10) # Gating SportsReference requests (limit is 20/minute, jail for an hour penalty)
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
        return stats

    def get_names_sportsref(self):
        names = []
        for letter in range(65,91):
            response = requests.get('https://www.pro-football-reference.com/players/' + chr(letter),verify=False)
            names.extend(response.text.split('<div class="section_content" id="div_players">\n\t    <p>')[-1].split('</p>\n\t\t\n')[0].split('</p><p>'))
            time.sleep(10)
        names = pd.DataFrame({'raw':names})
        names['player_id'] = names.raw.str.split('href="').str[-1].str.split('">')\
        .str[0].str.split('/').str[-1].str.split('.htm').str[0]
        names['name'] = names.raw.str.split('.htm">').str[-1].str.split('</a>').str[0]
        names['position'] = names.raw.str.split('\(').str[-1].str.split('\)').str[0]
        names.loc[names.name == 'Logan Thomas','position'] = 'TE'
        names.loc[names.name == 'Cordarrelle Patterson','position'] = 'RB'
        del names['raw']
        return names

    def get_rosters_sportsref(self):
        rosters = pd.DataFrame(columns=['raw','real_abbrev'])
        for team in self.nfl_teams.real_abbrev.unique():
            response = requests.get('https://www.pro-football-reference.com/teams/{}/{}_roster.htm'.format(team.lower(),self.season),verify=False)
            rosters = rosters.append(pd.DataFrame({'raw':response.text.split('</thead>\n<tbody><tr >')[-1]\
            .split('</tr>\n</tbody><tfoot>')[0].split('</tr>\n<tr >')}),ignore_index=True,sort=False)
            rosters.real_abbrev = rosters.real_abbrev.fillna(team)
            time.sleep(10)
        rosters['player_id'] = rosters.raw.str.split('</td>').str[0].str.split('.htm">').str[0].str.split('/').str[-1]
        rosters['name'] = rosters.raw.str.split('</td>').str[0].str.split('.htm">').str[-1].str.split('</a>').str[0]
        rosters['age'] = rosters.raw.str.split('</td>').str[1].str.split('>').str[-1]
        rosters['position'] = rosters.raw.str.split('</td>').str[2].str.split('>').str[-1]
        rosters['games'] = rosters.raw.str.split('</td>').str[3].str.split('>').str[-1]
        rosters['games_started'] = rosters.raw.str.split('</td>').str[4].str.split('>').str[-1]
        rosters['weight'] = rosters.raw.str.split('</td>').str[5].str.split('>').str[-1]
        rosters['height'] = rosters.raw.str.split('</td>').str[6].str.split('>').str[-1]
        rosters['birthdate'] = rosters.raw.str.split('</td>').str[8].str.split('>').str[-1]
        rosters['years'] = rosters.raw.str.split('</td>').str[9].str.split('>').str[-1]
        rosters['drafted'] = rosters.raw.str.split('</td>').str[11].str.split('data-stat="draft_info" >')\
        .str[-1].str.split(' / <a href="https://www.pro-football-reference.com/years/').str[0]
        del rosters['raw']
        return rosters
    
    def get_stats_sportsref(self,start:int,finish:int):
        stats = self.get_games_sportsref(start,finish)
        names = self.get_names_sportsref()
        stats = pd.merge(left=stats,right=names,how='left',on='player_id')
        rosters = self.get_rosters_sportsref()
        stats = pd.merge(left=stats,right=rosters,how='left',on=['player_id','name','position'])
        stats = pd.merge(left=stats,right=self.nfl_teams[['abbrev','real_abbrev']]\
        .rename(columns={'abbrev':'current_team'}),how='inner',on='real_abbrev')
        del stats['real_abbrev']
        to_fix = ~stats.position.isin(['QB','RB','WR','TE','K']) & \
        (stats.position.str.contains('QB') | \
        stats.position.str.contains('WR') | \
        stats.position.str.contains('RB') | \
        stats.position.str.contains('TE') | \
        stats.position.str.contains('K'))
        if to_fix.any():
            print(stats.loc[to_fix,['player_id','name','position']])
        defenses = stats.loc[~stats.position.isin(['QB','RB','WR','TE','K'])]\
        .groupby(['boxscore','season','week','team','opponent','points_allowed']).sum().reset_index()
        defenses = pd.merge(left=defenses,right=self.nfl_teams[['abbrev','real_abbrev']],how='inner',left_on='team',right_on='real_abbrev')
        defenses['name'] = defenses['abbrev']
        defenses['player_id'] = defenses['name']
        del defenses['abbrev'], defenses['real_abbrev']
        defenses['position'] = 'DEF'
        defenses['current_team'] = defenses['name']
        defenses = defenses[[col for col in stats.columns if col in defenses.columns]]
        stats = stats.loc[stats.position.isin(['QB','RB','WR','TE','K'])]
        stats = stats.append(defenses,ignore_index=True)
        return stats
    
    def get_current_team(self):
        as_of = self.season*100 + self.week
        if (self.stats.season*100 + self.stats.week).max() >= as_of:
            teams_as_of = self.stats.loc[self.stats.season*100 + self.stats.week >= as_of].sort_values(by='week')\
            .drop_duplicates(subset='player_id',keep='first')[['player_id','team']].rename(columns={'team':'real_abbrev'})
            teams_as_of = pd.merge(left=teams_as_of,right=self.nfl_teams[['abbrev','real_abbrev']]\
            .rename(columns={'abbrev':'current_team'}),how='inner',on='real_abbrev')
            del teams_as_of['real_abbrev']
        else:
            teams_as_of = self.stats.sort_values(by='week').drop_duplicates(subset='player_id',keep='last')[['player_id','current_team']]
        if 'current_team' in self.stats.columns:
            del self.stats['current_team']
        self.stats = pd.merge(left=self.stats.loc[self.stats.season*100 + self.stats.week < as_of],right=teams_as_of,how='left',on='player_id')

    def load_stats(self,start,finish):
        if os.path.exists('GameByGameFantasyFootballStats.csv'):
            tot = pd.read_csv('GameByGameFantasyFootballStats.csv',low_memory=False)
            if (tot.season*100 + tot.week).min() > start:
                last = int((tot.season*100 + tot.week).min()) - 1
                if last%100 == 0:
                    last -= 83
                tot = tot.append(self.get_stats_sportsref(start,last))
                tot.to_csv('GameByGameFantasyFootballStats.csv',index=False)
            if (tot.season*100 + tot.week).max() < finish:
                first = int((tot.season*100 + tot.week).max()) + 1
                if first%100 == 18:
                    first += 83
                tot = tot.append(self.get_stats_sportsref(first,finish))
                tot.to_csv('GameByGameFantasyFootballStats.csv',index=False)
        else:
            tot = self.get_stats_sportsref(start,finish)
            tot.to_csv('GameByGameFantasyFootballStats.csv',index=False)
        offense = tot.loc[tot.position != 'DEF'].reset_index(drop=True)
        offense['points'] = offense['rush_yards']*self.scoring.loc['Rush Yds','value'] + \
        offense['rush_touchdowns']*self.scoring.loc['Rush TD','value'] + \
        offense['receptions']*self.scoring.loc['Rec','value'] + \
        offense['receiving_yards']*self.scoring.loc['Rec Yds','value'] + \
        offense['receiving_touchdowns']*self.scoring.loc['Rec TD','value'] + \
        offense['passing_yards']*self.scoring.loc['Pass Yds','value'] + \
        offense['passing_touchdowns']*self.scoring.loc['Pass TD','value'] + \
        offense['interceptions_thrown']*self.scoring.loc['Int Thrown','value'] + \
        offense['fumbles_lost']*self.scoring.loc['Fum Lost','value'] + \
        (offense['kickoff_return_yards'] + offense['punt_return_yards'])*\
        (self.scoring.loc['Ret Yds','value'] if 'Ret Yds' in self.scoring.index else 0) + \
        (offense['kickoff_return_touchdown'] + offense['punt_return_touchdown'])*self.scoring.loc['Ret TD','value'] + \
        offense['extra_points_made']*self.scoring.loc['PAT Made','value'] + \
        offense['field_goals_made']*self.scoring.loc['FG 0-19','value']
        defense = tot.loc[tot.position == 'DEF'].reset_index(drop=True)
        defense['points'] = defense['sacks']*self.scoring.loc['Sack','value'] + \
        defense['interceptions']*self.scoring.loc['Int','value'] + \
        defense['fumbles_recovered']*self.scoring.loc['Fum Rec','value'] + \
        defense['interceptions_returned_for_touchdown']*self.scoring.loc['Ret TD','value'] + \
        defense['kickoff_return_touchdown']*self.scoring.loc['Ret TD','value'] + \
        defense['punt_return_touchdown']*self.scoring.loc['Ret TD','value']
        defense.loc[defense.points_allowed == 0,'points'] += self.scoring.loc['Pts Allow 0','value']
        defense.loc[(defense.points_allowed >= 1) & (defense.points_allowed <= 6),'points'] += self.scoring.loc['Pts Allow 1-6','value']
        defense.loc[(defense.points_allowed >= 7) & (defense.points_allowed <= 13),'points'] += self.scoring.loc['Pts Allow 7-13','value']
        defense.loc[(defense.points_allowed >= 14) & (defense.points_allowed <= 20),'points'] += self.scoring.loc['Pts Allow 14-20','value']
        defense.loc[(defense.points_allowed >= 21) & (defense.points_allowed <= 27),'points'] += self.scoring.loc['Pts Allow 21-27','value']
        defense.loc[(defense.points_allowed >= 28) & (defense.points_allowed <= 34),'points'] += self.scoring.loc['Pts Allow 28-34','value']
        defense.loc[(defense.points_allowed >= 35),'points'] += self.scoring.loc['Pts Allow 35+','value']
        self.stats = offense.append(defense,ignore_index=True,sort=False)
        self.stats['weeks_ago'] = (datetime.datetime.now() - pd.to_datetime(self.stats.boxscore.str[:8],infer_datetime_format=True)).dt.days/7.0
        self.get_current_team()
        self.stats = self.stats.loc[self.stats.season*100 + self.stats.week >= start].reset_index(drop=True)

    def name_corrections(self):
        self.load_stats((self.season - 2)*100 + 1,self.season*100 + self.week - 1)
        try:
            corrections = pd.read_csv("https://raw.githubusercontent.com/" + \
            "tefirman/FantasySports/main/res/football/name_corrections.csv")
        except:
            corrections = [player.split(',') for player in requests.get("https://raw.githubusercontent.com/" + \
            "tefirman/FantasySports/main/res/football/name_corrections.csv",verify=False).text.split('\r')]
            corrections = pd.DataFrame(corrections[1:],columns=corrections[0])
        self.players = pd.merge(left=self.players,right=corrections,how='left',on='name')
        to_fix = ~self.players.new_name.isnull()
        self.players.loc[to_fix,'name'] = self.players.loc[to_fix,'new_name']
        not_found = ~self.players.name.isin(self.stats.name.unique()) & ~self.players.fantasy_team.isnull()
        if self.players.loc[not_found].shape[0] > 0:
            print('Need to reconcile player names... ' + ', '.join(self.players.loc[not_found,'name']))

    def load_parameters(self,earliest=None,reference_games=None,basaloppqbtime=[]):
        try:
            params = pd.read_csv("https://raw.githubusercontent.com/" + \
            "tefirman/FantasySports/main/res/football/weighting_factors.csv")
        except:
            params = [player.split(',') for player in requests.get("https://raw.githubusercontent.com/" + \
            "tefirman/FantasySports/main/res/football/weighting_factors.csv",verify=False).text.split('\r')]
        if earliest:
            self.earliest = earliest
        else:
            prior = params.loc[params.week == self.week,'prior'].values[0]
            self.earliest = (self.season - prior//17)*100 + self.week - prior%17
            if (self.earliest%100 == 0) | (self.earliest%100 > 50):
                self.earliest -= 83 # Assuming 17 weeks... Need to change this soon...
        if reference_games:
            self.reference_games = reference_games
        else:
            self.reference_games = params.loc[params.week == self.week,'games'].values[0]
        if basaloppqbtime:
            self.basaloppqbtime = basaloppqbtime
        else:
            self.basaloppqbtime = [1.0] + list(params.loc[params.week == 11,['opp_elo','qb_elo','time_factor']].values[0])

    def add_injuries(self):
        as_of = self.season*100 + self.week
        if 'until' in self.players.columns:
            del self.players['until']
        self.players['until'] = None
        if as_of < self.latest_season*100 + self.lg.current_week():
            self.load_stats(self.season*100 + 1,self.season*100 + 17)
            self.stats = self.stats.loc[self.stats.season*100 + self.stats.week >= as_of]
            healthy = self.stats.loc[self.stats.season*100 + self.stats.week == as_of,'name'].tolist()
            injured = self.players.loc[~self.players.name.isin(healthy),'name'].tolist()
            for name in injured:
                until = self.stats.loc[self.stats.name == name,'week'].min() - 1
                if not np.isnan(until):
                    self.players.loc[self.players.name == name,'until'] = until
                elif self.season < self.latest_season:
                    self.players.loc[self.players.name == name,'until'] = 17
        if as_of//100 == self.latest_season:
            try:
                inj_proj = pd.read_csv("https://raw.githubusercontent.com/" + \
                "tefirman/FantasySports/main/res/football/injured_list.csv")
            except:
                inj_proj = [player.split(',') for player in requests.get("https://raw.githubusercontent.com/" + \
                "tefirman/FantasySports/main/res/football/injured_list.csv",verify=False).text.split('\r')]
                inj_proj = pd.DataFrame(inj_proj[1:],columns=inj_proj[0])
            inj_proj = inj_proj.loc[inj_proj.until >= self.lg.current_week()]
            self.players = pd.merge(left=self.players.rename(columns={'until':'until_orig'}),\
            right=inj_proj,how='left',on=['name','position','current_team'])
            if as_of%100 == self.lg.current_week():
                newInjury = self.players.status.isin(['O','D','SUSP','IR','PUP-R','PUP-P','NFI-R','NA','COVID-19']) & \
                (self.players.until.isnull() | (self.players.until < self.lg.current_week())) & \
                (~self.players.fantasy_team.isnull())# | (self.players.WAR >= 0))
                if newInjury.sum() > 0:
                    print('Need to look up new injuries... ' + ', '.join(self.players.loc[newInjury,'name'].tolist()))
                    self.players.loc[newInjury,'until'] = self.lg.current_week()
                oldInjury = ~self.players.status.isin(['O','D','SUSP','IR','PUP-R','PUP-P','NFI-R','NA','COVID-19']) & \
                (self.players.until >= self.lg.current_week()) & (~self.players.fantasy_team.isnull())# | (self.players.WAR >= 0))
                if oldInjury.sum() > 0:
                    print('Need to update old injuries... ' + ', '.join(self.players.loc[oldInjury,'name'].tolist()))
                    # self.players.loc[oldInjury,'until'] = self.lg.current_week()
            self.players['until'] = self.players[['until_orig','until']].min(axis=1)
            del self.players['until_orig']

    def add_bye_weeks(self):
        byes = pd.DataFrame(columns=['current_team','bye_week'])
        for team in self.nfl_schedule.abbrev.unique():
            bye_week = 1
            while ((self.nfl_schedule.abbrev == team) & (self.nfl_schedule.season == self.season) & (self.nfl_schedule.week == bye_week)).any():
                bye_week += 1
            byes = byes.append({'current_team':team,'bye_week':bye_week},ignore_index=True)
        self.players = pd.merge(left=self.players,right=byes,how='left',on='current_team')

    def add_roster_pcts(self, inc=25):
        self.refresh_oauth()
        roster_pcts = pd.DataFrame()
        for ind in range(self.players.shape[0]//inc + 1):
            while True:
                try:
                    self.refresh_oauth()
                    if self.players.iloc[inc*ind:inc*(ind + 1)].shape[0] == 0:
                        break
                    player_ids = self.players.iloc[inc*ind:inc*(ind + 1)].player_id.astype(str).tolist()
                    player_ids = [val.split('.')[0] for val in player_ids if val != 'nan']
                    pcts = self.lg.yhandler.get("league/{}/players;player_keys=414.p.{}/percent_owned"\
                    .format(self.lg_id,',414.p.'.join(player_ids)))['fantasy_content']['league'][1]['players']
                    break
                except:
                    err_message = traceback.format_exc()
                    print(err_message)
                    print('Roster percentage query crapped out... Waiting 30 seconds and trying again...')
                    time.sleep(30)
            for player_ind in range(pcts['count']):
                player = pcts[str(player_ind)]['player']
                player_id = [int(val['player_id']) for val in player[0] if 'player_id' in val]
                full_name = [val['name']['full'] for val in player[0] if 'name' in val]
                pct_owned = [float(val['value'])/100.0 for val in player[1]['percent_owned'] if 'value' in val]
                if len(pct_owned) == 0:
                    # print("Can't find roster percentage for {}...".format(full_name))
                    pct_owned = [0.0]
                roster_pcts = roster_pcts.append(pd.DataFrame({'player_id':player_id,\
                'name':full_name,'pct_rostered':pct_owned}),ignore_index=True,sort=False)
        self.players = pd.merge(left=self.players,right=roster_pcts,how='left',on=['player_id','name'])
        self.players.pct_rostered = self.players.pct_rostered.fillna(0.0)

    def get_rates(self):
        as_of = self.season*100 + self.week
        self.load_stats(self.earliest,as_of - 1)
        norm_schedule = pd.merge(left=self.nfl_schedule,right=self.nfl_teams[['real_abbrev','abbrev']]\
        .rename(columns={'real_abbrev':'team'}),how='inner',on=['abbrev'])
        self.stats = pd.merge(left=self.stats,right=norm_schedule,how='left',on=['season','week','team'])
        self.stats['game_factor'] = self.basaloppqbtime[0] + \
        self.basaloppqbtime[1]*(self.stats['opp_elo'] - 1) + \
        self.basaloppqbtime[2]*(self.stats['qb_elo'] - 1)
        self.stats.points /= self.stats.game_factor
        by_pos = pd.merge(left=self.stats.groupby('position').points.mean()\
        .reset_index().rename(index=str,columns={'points':'points_avg'}),\
        right=self.stats.groupby('position').points.std().reset_index()\
        .rename(index=str,columns={'points':'points_stdev'}),how='inner',on='position')
        by_pos['name'] = 'Average_' + by_pos['position']
        self.stats = self.stats.groupby('player_id').head(self.reference_games)
        self.stats['weeks_ago'] = 17*(as_of//100 - self.stats.season) + as_of%100 - self.stats.week
        self.stats['time_factor'] = 1 - self.stats.weeks_ago*self.basaloppqbtime[-1]
        self.stats = self.stats.loc[self.stats.time_factor > 0].reset_index(drop=True)
        self.stats = pd.merge(left=self.stats,right=self.stats.groupby(['name','position'])\
        .agg({'time_factor':sum,'player_id':'count'}).rename(columns={'player_id':'num_games',\
        'time_factor':'time_factor_sum'}).reset_index(),how='inner',on=['name','position'])
        self.stats.time_factor = self.stats.time_factor*self.stats.num_games/self.stats.time_factor_sum
        self.stats['weighted_points'] = self.stats.points*self.stats.time_factor
        by_player = pd.merge(left=self.stats.groupby(['name','position']).weighted_points.mean()\
        .reset_index().rename(index=str,columns={'weighted_points':'points_avg'}),\
        right=self.stats.groupby(['name','position']).weighted_points.std().reset_index()\
        .rename(index=str,columns={'weighted_points':'points_stdev'}),how='inner',on=['name','position'])
        by_player = pd.merge(left=by_player,right=self.stats.groupby(['name','position'])\
        .size().to_frame('num_games').reset_index(),how='inner',on=['name','position'])
        by_player = by_player.append(by_pos[['name','position','points_avg','points_stdev']],ignore_index=True,sort=False)
        by_player.points_stdev = by_player.points_stdev.fillna(0.0)
        by_player = pd.merge(left=by_player,right=by_pos[['position','points_avg','points_stdev']]\
        .rename(columns={'points_avg':'pos_avg','points_stdev':'pos_stdev'}),how='inner',on='position')
        inds = by_player.num_games < self.reference_games
        by_player.loc[inds,'points_squared'] = (by_player.loc[inds,'num_games']*(by_player.loc[inds,'points_stdev']**2 + \
        by_player.loc[inds,'points_avg']**2) + (self.reference_games - by_player.loc[inds,'num_games'])*\
        (by_player.loc[inds,'pos_stdev']**2 + by_player.loc[inds,'pos_avg']**2))/self.reference_games
        by_player.loc[inds,'points_avg'] = (by_player.loc[inds,'num_games']*by_player.loc[inds,'points_avg'] + \
        (self.reference_games - by_player.loc[inds,'num_games'])*by_player.loc[inds,'pos_avg'])/self.reference_games
        by_player.loc[inds,'points_stdev'] = (by_player.loc[inds,'points_squared'] - by_player.loc[inds,'points_avg']**2)**0.5
        league_avg = by_player.loc[by_player.name.str.contains('Average_')]
        by_player = pd.merge(left=by_player,right=self.players[['name','position',\
        'player_id','status','fantasy_team','editorial_team_abbr','selected_position']].drop_duplicates(),\
        how='right',on=['name','position']).append(league_avg,ignore_index=True,sort=False)
        rookies = pd.merge(left=by_player.loc[by_player.num_games.isnull(),\
        ['name','player_id','position','fantasy_team','editorial_team_abbr','selected_position']],\
        right=league_avg[['position','points_avg','points_stdev']],how='inner',on='position')
        by_player = by_player.loc[~by_player.num_games.isnull()]
        by_player = by_player.append(rookies[['name','player_id','position',\
        'points_avg','points_stdev','fantasy_team','editorial_team_abbr','selected_position']],ignore_index=True,sort=False)
        if as_of//100 == self.latest_season:
            """ First week issues... """
            by_player = pd.merge(left=by_player,right=self.nfl_teams[['abbrev','yahoo']]\
            .rename(columns={'yahoo':'editorial_team_abbr'}),how='left',on='editorial_team_abbr')
            by_player.loc[~by_player.abbrev.isnull(),'current_team'] = \
            by_player.loc[~by_player.abbrev.isnull(),'abbrev']
            del by_player['abbrev']
            """ First week issues... """
        self.players = by_player

    def get_schedule(self):
        as_of = self.season*100 + self.week
        self.refresh_oauth()
        schedule = pd.DataFrame()
        for team in self.teams:
            tm = self.lg.to_team(team['team_key'])
            limit = max(int(self.settings['playoff_start_week']),as_of%100 + 1) if as_of else int(self.settings['playoff_start_week'])
            for week in range(1,limit):
                while True:
                    try:
                        matchup = tm.yhandler.get_matchup_raw(tm.team_key,week)['fantasy_content']['team'][1]['matchups']
                        break
                    except:
                        print('Matchup query crapped out... Waiting 30 seconds and trying again...')
                        time.sleep(30)
                if '0' in matchup.keys():
                    schedule = schedule.append(pd.DataFrame({'week':[week],\
                    'team_1':[matchup['0']['matchup']['0']['teams']['0']['team'][0][2]['name']],\
                    'team_2':[matchup['0']['matchup']['0']['teams']['1']['team'][0][2]['name']],\
                    'score_1':[matchup['0']['matchup']['0']['teams']['0']['team'][1]['team_points']['total']],\
                    'score_2':[matchup['0']['matchup']['0']['teams']['1']['team'][1]['team_points']['total']]}),ignore_index=True)
        
        """ MANY MILE POSTSEASON """
        if as_of//100 == 2021 and as_of%100 >= 15 and (schedule.team_1.isin(['The Algorithm']).any() or schedule.team_2.isin(['The Algorithm']).any()):
            schedule = schedule.loc[~schedule.week.isin([15,16,17]) | ~schedule.team_1.isin(['The Algorithm',\
            '69ers','Football Cream','Wankstas',"The Adam's Family",'Sunday ShNoz'])].reset_index(drop=True)
            schedule = schedule.append(pd.DataFrame({'week':[15,15,16,16,17],\
            'team_1':["The Adam's Family",'Football Cream','Wankstas',"The Adam's Family",'Sunday ShNoz'],\
            'team_2':['The Algorithm','Sunday ShNoz','Sunday ShNoz','69ers','69ers'],\
            'score_1':[54.28,115.80,126.16,119.60,0.00],'score_2':[119.45,101.46,65.86,98.24,0.00]}),ignore_index=True,sort=False)
        elif as_of//100 == 2022 and as_of%100 >= 15 and (schedule.team_1.isin(['The Algorithm']).any() or schedule.team_2.isin(['The Algorithm']).any()):
            schedule = schedule.loc[~schedule.week.isin([15,16,17]) | ~schedule.team_1.isin(['69ers',\
            'Chase-ing a Dream','Crotch de Fuego','Christian Murder Force','All About the D','The Sofa Kings'])].reset_index(drop=True)
            schedule = schedule.append(pd.DataFrame({'week':[15,15,16,16,17],\
            'team_1':['Crotch de Fuego','Christian Murder Force','Crotch de Fuego','Christian Murder Force','Crotch de Fuego'],\
            'team_2':['Chase-ing a Dream','69ers','The Sofa Kings','All About the D','Christian Murder Force'],\
            'score_1':[90.44,103.46,85.60,82.80,71.86],'score_2':[92.30,117.74,90.80,114.08,126.00]}),ignore_index=True,sort=False)
        """ MANY MILE POSTSEASON """
        
        switch = schedule.team_1 > schedule.team_2
        schedule.loc[switch,'temp'] = schedule.loc[switch,'team_1']
        schedule.loc[switch,'team_1'] = schedule.loc[switch,'team_2']
        schedule.loc[switch,'team_2'] = schedule.loc[switch,'temp']
        schedule.loc[switch,'temp'] = schedule.loc[switch,'score_1']
        schedule.loc[switch,'score_1'] = schedule.loc[switch,'score_2']
        schedule.loc[switch,'score_2'] = schedule.loc[switch,'temp']
        schedule = schedule[['week','team_1','team_2','score_1','score_2']]\
        .drop_duplicates().sort_values(by=['week','team_1','team_2']).reset_index(drop=True)
        schedule[['score_1','score_2']] = schedule[['score_1','score_2']].astype(float)
        team_name = [team['name'] for team in self.teams if team['team_key'] == self.lg.team_key()][0]
        schedule['me'] = (schedule['team_1'] == team_name) | (schedule['team_2'] == team_name)
        if as_of:
            schedule.loc[schedule.week > as_of%100,'score_1'] = 0.0
            schedule.loc[schedule.week > as_of%100,'score_2'] = 0.0
            if self.latest_season > as_of//100 or as_of%100 < self.lg.current_week():
                schedule.loc[schedule.week == as_of%100,'score_1'] = 0.0
                schedule.loc[schedule.week == as_of%100,'score_2'] = 0.0
        self.schedule = schedule

    def starters(self, week):
        as_of = self.season*100 + self.week
        self.refresh_oauth()
        self.players = pd.merge(left=self.players,\
        right=self.nfl_schedule.loc[(self.nfl_schedule.season == as_of//100) & \
        (self.nfl_schedule.week == week),['abbrev','opp_elo','qb_elo','home_away']],\
        how='left',left_on='current_team',right_on='abbrev')
        self.players['opp_factor'] = self.basaloppqbtime[1]*(self.players['opp_elo'] - 1)
        self.players['qb_factor'] = self.basaloppqbtime[2]*(self.players['qb_elo'] - 1)
        self.players['game_factor'] = self.basaloppqbtime[0] + self.players['opp_factor'] + self.players['qb_factor']
        self.players['points_avg'] *= self.players['game_factor'].fillna(1.0)
        del self.players['opp_elo'], self.players['qb_elo'], self.players['home_away'], self.players['abbrev']
        """ WAR is linear with points_avg, but slope/intercept depends on position """
        """ Harder to characterize how WAR varies with points_stdev, ignoring for now... """
        self.players = self.players.sort_values(by='points_avg',ascending=False)
        # self.players = self.players.sort_values(by='WAR',ascending=False)
        self.players['starter'] = False
        self.players['injured'] = self.players.until >= week
        if week == as_of%100 and as_of//100 == self.latest_season \
        and datetime.datetime.now().month > 8: # Careful when your draft is in September...
            cutoff = datetime.datetime.now()
            if datetime.datetime.now().hour < 20:
                cutoff -= datetime.timedelta(days=1)
            completed = self.nfl_schedule.loc[(self.nfl_schedule.season == as_of//100) & \
            (self.nfl_schedule.week == week) & (self.nfl_schedule.date < cutoff),'abbrev'].tolist()
            for team in self.teams:
                started = self.players.loc[(self.players.selected_position != 'BN') & \
                (self.players.fantasy_team == team['name']) & self.players.current_team.isin(completed)]
                not_available = self.players.loc[(self.players.selected_position == 'BN') & \
                (self.players.fantasy_team == team['name']) & self.players.current_team.isin(completed)]
                num_pos = {pos['roster_position']['position']:pos['roster_position']['count'] - \
                sum(started.selected_position == pos['roster_position']['position']) \
                for pos in self.settings['roster_positions'] if pos['roster_position']['position'] not in ['W/R/T','W/T','BN','IR']}
                for pos in num_pos:
                    for num in range(num_pos[pos]):
                        self.players.loc[self.players.loc[(self.players.fantasy_team == team['name']) & \
                        ~self.players.starter & ~self.players.injured & (self.players.bye_week != week) & \
                        (self.players.position == pos) & ~self.players.player_id.isin(started.player_id) & \
                        ~self.players.player_id.isin(not_available.player_id)].iloc[:1].index,'starter'] = True
                flex = [pos['roster_position']['count'] - sum(started.selected_position == pos['roster_position']['position']) \
                for pos in self.settings['roster_positions'] if pos['roster_position']['position'] in ['W/R/T','W/T']]
                for flex in range(sum(flex)):
                    self.players.loc[self.players.loc[(self.players.fantasy_team == team['name']) & \
                    ~self.players.starter & ~self.players.injured & (self.players.bye_week != week) & \
                    self.players.position.isin(['WR','RB','TE']) & ~self.players.player_id.isin(started.player_id) & \
                    ~self.players.player_id.isin(not_available.player_id)].iloc[:1].index,'starter'] = True
        elif week >= as_of%100:
            num_pos = {pos['roster_position']['position']:pos['roster_position']['count'] \
            for pos in self.settings['roster_positions'] if pos['roster_position']['position'] not in ['W/R/T','W/T','BN','IR']}
            for pos in num_pos:
                for num in range(num_pos[pos]):
                    self.players.loc[self.players.loc[~self.players.starter & ~self.players.injured & \
                    (self.players.bye_week != week) & (self.players.position == pos)]\
                    .drop_duplicates(subset=['fantasy_team'],keep='first').index,'starter'] = True
            flex = [pos['roster_position']['count'] for pos in self.settings['roster_positions'] if pos['roster_position']['position'] in ['W/R/T','W/T']]
            for flex in range(sum(flex)):
                self.players.loc[self.players.loc[~self.players.starter & ~self.players.injured & \
                (self.players.bye_week != week) & self.players.position.isin(['WR','RB','TE'])]\
                .drop_duplicates(subset=['fantasy_team'],keep='first').index,'starter'] = True

    def season_sims(self,verbose=False,postseason=True,payouts=[800,300,100],fixed_winner=None):
        as_of = self.season*100 + self.week
        self.refresh_oauth()
        self.players['points_var'] = self.players.points_stdev**2
        projections = pd.DataFrame(columns=['fantasy_team','week','points_avg','points_var'])
        for week in range(17):
            self.starters(week + 1)
            projections = projections.append(self.players.loc[self.players.starter].groupby('fantasy_team')\
            [['points_avg','points_var']].sum().reset_index(),ignore_index=True,sort=False)
            projections.loc[projections.week.isnull(),'week'] = week + 1
        projections['points_stdev'] = projections['points_var']**0.5
        del self.players['points_var']
        schedule = pd.merge(left=self.schedule.copy(),right=projections.rename(index=str,\
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
        schedule_sims = pd.DataFrame().append([schedule]*self.num_sims,ignore_index=True)
        schedule_sims['num_sim'] = schedule_sims.index//schedule.shape[0]
        schedule_sims['sim_1'] = np.random.normal(loc=0,scale=1,size=schedule_sims.shape[0])*schedule_sims['points_stdev_1'] + schedule_sims['points_avg_1']
        schedule_sims['sim_2'] = np.random.normal(loc=0,scale=1,size=schedule_sims.shape[0])*schedule_sims['points_stdev_2'] + schedule_sims['points_avg_2']
        schedule_sims['win_1'] = (schedule_sims.sim_1 > schedule_sims.sim_2).astype(int)
        schedule_sims['win_2'] = 1 - schedule_sims['win_1']
        standings = schedule_sims[['num_sim','week','team_1','sim_1','win_1']].reset_index()\
        .rename(index=str,columns={'team_1':'team','win_1':'wins','sim_1':'points'})\
        .append(schedule_sims[['num_sim','week','team_2','sim_2','win_2']].reset_index()\
        .rename(index=str,columns={'team_2':'team','win_2':'wins','sim_2':'points'}),ignore_index=True)
        standings = standings.loc[standings.week < int(self.settings['playoff_start_week'])]\
        .groupby(['num_sim','team']).sum().sort_values(by=['num_sim','wins','points'],ascending=False).reset_index()
        standings.loc[standings.index%len(self.teams) < int(self.settings['num_playoff_teams']),'playoffs'] = 1
        standings.loc[standings.index%len(self.teams) >= int(self.settings['num_playoff_teams']),'playoffs'] = 0
        standings['playoff_bye'] = 0
        if self.settings['num_playoff_teams'] == '6':
            standings.loc[standings.index%len(self.teams) < 2,'playoff_bye'] = 1
        if postseason:
            algorithm = schedule.team_1.isin(['The Algorithm']).any() \
            or schedule.team_2.isin(['The Algorithm']).any()
            standings['seed'] = standings.index%len(self.teams)
            scores = schedule.loc[schedule.week >= int(self.settings['playoff_start_week']),\
            ['week','team_1','score_1']].rename(columns={'team_1':'team','score_1':'score'})\
            .append(schedule.loc[schedule.week >= int(self.settings['playoff_start_week']),\
            ['week','team_2','score_2']].rename(columns={'team_2':'team','score_2':'score'}),\
            ignore_index=True,sort=False).groupby(['week','team']).score.sum().reset_index()
            playoffs = standings.loc[standings.seed < int(self.settings['num_playoff_teams'])].copy().reset_index()
            if algorithm:
                many_mile = standings.loc[standings.seed >= int(self.settings['num_playoff_teams'])].copy().reset_index()
            if self.settings['num_playoff_teams'] == '6':
                playoffs = pd.merge(left=playoffs,right=scores.loc[scores.week == int(self.settings['playoff_start_week']),['team','score']],how='left',on='team')
                playoffs.score = playoffs.score.fillna(0.0)
                playoffs = pd.merge(left=playoffs,right=projections.loc[projections.week == int(self.settings['playoff_start_week']),\
                ['fantasy_team','points_avg','points_stdev']].rename(columns={'fantasy_team':'team'}),how='left',on='team')
                playoffs.points_avg = playoffs.points_avg.fillna(0.0)
                playoffs.points_stdev = playoffs.points_stdev.fillna(0.0)
                playoffs.loc[playoffs.seed == 0,'matchup'] = 0
                playoffs.loc[playoffs.seed == 1,'matchup'] = 1
                playoffs.loc[playoffs.seed.isin([2,5]),'matchup'] = 2
                playoffs.loc[playoffs.seed.isin([3,4]),'matchup'] = 3
                playoffs['sim'] = np.random.normal(loc=0,scale=1,size=playoffs.shape[0])*playoffs.points_stdev + playoffs.points_avg + playoffs.score
                playoffs = playoffs.sort_values(by=['num_sim','matchup','sim'],ascending=[True,True,False])\
                .drop_duplicates(subset=['num_sim','matchup'],keep='first').reset_index(drop=True)
                del playoffs['matchup'], playoffs['sim'], playoffs['score'], playoffs['points_avg'], playoffs['points_stdev']
                if self.settings['uses_playoff_reseeding']:
                    playoffs = playoffs.sort_values(by=['num_sim','seed'],ascending=True).reset_index(drop=True)
                if algorithm:
                    many_mile = pd.merge(left=many_mile,right=scores.loc[scores.week == int(self.settings['playoff_start_week']),['team','score']],how='left',on='team')
                    many_mile.score = many_mile.score.fillna(0.0)
                    many_mile = pd.merge(left=many_mile,right=projections.loc[projections.week == int(self.settings['playoff_start_week']),\
                    ['fantasy_team','points_avg','points_stdev']].rename(columns={'fantasy_team':'team'}),how='left',on='team')
                    many_mile.points_avg = many_mile.points_avg.fillna(0.0)
                    many_mile.points_stdev = many_mile.points_stdev.fillna(0.0)
                    many_mile.loc[many_mile.seed == 11,'matchup'] = 0
                    many_mile.loc[many_mile.seed == 10,'matchup'] = 1
                    many_mile.loc[many_mile.seed.isin([6,9]),'matchup'] = 2
                    many_mile.loc[many_mile.seed.isin([7,8]),'matchup'] = 3
                    many_mile['sim'] = np.random.normal(loc=0,scale=1,size=many_mile.shape[0])*many_mile.points_stdev + many_mile.points_avg + many_mile.score
                    many_mile = many_mile.sort_values(by=['num_sim','matchup','sim'],ascending=True).drop_duplicates(subset=['num_sim','matchup'],keep='first')
                    del many_mile['matchup'], many_mile['sim'], many_mile['score'], many_mile['points_avg'], many_mile['points_stdev']
            playoffs = pd.merge(left=playoffs,right=scores.loc[scores.week == int(self.settings['playoff_start_week']) + \
            int(self.settings['num_playoff_teams'] == '6'),['team','score']],how='left',on='team')
            playoffs.score = playoffs.score.fillna(0.0)
            playoffs = pd.merge(left=playoffs,right=projections.loc[projections.week == int(self.settings['playoff_start_week']) + \
            int(self.settings['num_playoff_teams'] == '6'),['fantasy_team','points_avg','points_stdev']]\
            .rename(columns={'fantasy_team':'team'}),how='left',on='team')
            playoffs.points_avg = playoffs.points_avg.fillna(0.0)
            playoffs.points_stdev = playoffs.points_stdev.fillna(0.0)
            playoffs['seed'] = playoffs.index%4
            playoffs.loc[playoffs.seed.isin([0,3]),'matchup'] = 0
            playoffs.loc[playoffs.seed.isin([1,2]),'matchup'] = 1
            playoffs['sim'] = np.random.normal(loc=0,scale=1,size=playoffs.shape[0])*playoffs.points_stdev + playoffs.points_avg + playoffs.score
            consolation = playoffs.sort_values(by=['num_sim','matchup','sim'],ascending=True)\
            .drop_duplicates(subset=['num_sim','matchup'],keep='first').reset_index(drop=True)
            playoffs = playoffs.sort_values(by=['num_sim','matchup','sim'],ascending=[True,True,False])\
            .drop_duplicates(subset=['num_sim','matchup'],keep='first').reset_index(drop=True)
            del playoffs['matchup'], playoffs['sim'], playoffs['score'], playoffs['points_avg'], playoffs['points_stdev'], \
            consolation['matchup'], consolation['sim'], consolation['score'], consolation['points_avg'], consolation['points_stdev']
            if algorithm:
                many_mile = pd.merge(left=many_mile,right=scores.loc[scores.week == int(self.settings['playoff_start_week']) + \
                int(self.settings['num_playoff_teams'] == '6'),['team','score']],how='left',on='team')
                many_mile.score = many_mile.score.fillna(0.0)
                many_mile = pd.merge(left=many_mile,right=projections.loc[projections.week == int(self.settings['playoff_start_week']) + \
                int(self.settings['num_playoff_teams'] == '6'),['fantasy_team','points_avg','points_stdev']]\
                .rename(columns={'fantasy_team':'team'}),how='left',on='team')
                many_mile.points_avg = many_mile.points_avg.fillna(0.0)
                many_mile.points_stdev = many_mile.points_stdev.fillna(0.0)
                many_mile['seed'] = many_mile.index%4
                many_mile.loc[many_mile.seed.isin([0,3]),'matchup'] = 0
                many_mile.loc[many_mile.seed.isin([1,2]),'matchup'] = 1
                many_mile['sim'] = np.random.normal(loc=0,scale=1,size=many_mile.shape[0])*many_mile.points_stdev + many_mile.points_avg + many_mile.score
                many_mile = many_mile.sort_values(by=['num_sim','matchup','sim'],ascending=True).drop_duplicates(subset=['num_sim','matchup'],keep='first')
                del many_mile['matchup'], many_mile['sim'], many_mile['score'], many_mile['points_avg'], many_mile['points_stdev']
            playoffs = pd.merge(left=playoffs,right=scores.loc[scores.week == int(self.settings['playoff_start_week']) + \
            1 + int(self.settings['num_playoff_teams'] == '6'),['team','score']],how='left',on='team')
            playoffs.score = playoffs.score.fillna(0.0)
            playoffs = pd.merge(left=playoffs,right=projections.loc[projections.week == int(self.settings['playoff_start_week']) + \
            1 + int(self.settings['num_playoff_teams'] == '6'),['fantasy_team','points_avg','points_stdev']]\
            .rename(columns={'fantasy_team':'team'}),how='left',on='team')
            playoffs.points_avg = playoffs.points_avg.fillna(0.0)
            playoffs.points_stdev = playoffs.points_stdev.fillna(0.0)
            playoffs['sim'] = np.random.normal(loc=0,scale=1,size=playoffs.shape[0])*playoffs.points_stdev + playoffs.points_avg + playoffs.score
            runner_up = playoffs.sort_values(by=['num_sim','sim'],ascending=True)\
            .drop_duplicates(subset=['num_sim'],keep='first')
            winner = playoffs.sort_values(by=['num_sim','sim'],ascending=[True,False])\
            .drop_duplicates(subset=['num_sim'],keep='first')
            consolation = pd.merge(left=consolation,right=scores.loc[scores.week == int(self.settings['playoff_start_week']) + \
            1 + int(self.settings['num_playoff_teams'] == '6'),['team','score']],how='left',on='team')
            consolation.score = consolation.score.fillna(0.0)
            consolation = pd.merge(left=consolation,right=projections.loc[projections.week == int(self.settings['playoff_start_week']) + \
            1 + int(self.settings['num_playoff_teams'] == '6'),['fantasy_team','points_avg','points_stdev']]\
            .rename(columns={'fantasy_team':'team'}),how='inner',on='team')
            consolation['sim'] = np.random.normal(loc=0,scale=1,size=consolation.shape[0])*consolation.points_stdev + consolation.points_avg + consolation.score
            third = consolation.sort_values(by=['num_sim','sim'],ascending=[True,False])\
            .drop_duplicates(subset=['num_sim'],keep='first')
            if algorithm:
                many_mile = pd.merge(left=many_mile,right=scores.loc[scores.week == int(self.settings['playoff_start_week']) + \
                1 + int(self.settings['num_playoff_teams'] == '6'),['team','score']],how='left',on='team')
                many_mile.score = many_mile.score.fillna(0.0)
                many_mile = pd.merge(left=many_mile,right=projections.loc[projections.week == int(self.settings['playoff_start_week']) + \
                1 + int(self.settings['num_playoff_teams'] == '6'),['fantasy_team','points_avg','points_stdev']]\
                .rename(columns={'fantasy_team':'team'}),how='left',on='team')
                many_mile.points_avg = many_mile.points_avg.fillna(0.0)
                many_mile.points_stdev = many_mile.points_stdev.fillna(0.0)
                many_mile['sim'] = np.random.normal(loc=0,scale=1,size=many_mile.shape[0])*many_mile.points_stdev + many_mile.points_avg + many_mile.score
                many_mile = many_mile.sort_values(by=['num_sim','sim'],ascending=True)\
                .drop_duplicates(subset=['num_sim'],keep='first')
            final_probs = pd.merge(left=pd.merge(left=winner.groupby('team').size().to_frame('winner').reset_index(),\
            right=runner_up.groupby('team').size().to_frame('runner_up').reset_index(),how='outer',on='team'),\
            right=third.groupby('team').size().to_frame('third').reset_index(),how='outer',on='team')
            if algorithm:
                final_probs = pd.merge(left=final_probs,right=many_mile.groupby('team')\
                .size().to_frame('many_mile').reset_index(),how='outer',on='team')
                final_probs['many_mile'] /= many_mile.shape[0]
                final_probs['many_mile'] = final_probs['many_mile'].fillna(0.0)
            final_probs['winner'] /= winner.shape[0]
            final_probs['runner_up'] /= runner_up.shape[0]
            final_probs['third'] /= third.shape[0]
            final_probs['winner'] = final_probs['winner'].fillna(0.0)
            final_probs['runner_up'] = final_probs['runner_up'].fillna(0.0)
            final_probs['third'] = final_probs['third'].fillna(0.0)
        else:
            final_probs = pd.DataFrame(columns=['team','winner','runner_up','third','many_mile'])
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
        standings = pd.merge(left=standings,right=final_probs,how='left',on='team')
        standings['winner'] = standings['winner'].fillna(0.0)
        standings['runner_up'] = standings['runner_up'].fillna(0.0)
        standings['third'] = standings['third'].fillna(0.0)
        if algorithm:
            standings['many_mile'] = standings['many_mile'].fillna(0.0)
        scores = schedule_sims[['team_1','sim_1']].rename(index=str,columns={'team_1':'team','sim_1':'sim'})\
        .append(schedule_sims[['team_2','sim_2']].rename(index=str,columns={'team_2':'team','sim_2':'sim'}),\
        ignore_index=True).groupby('team')
        standings = pd.merge(left=standings,right=scores.sim.mean().reset_index()\
        .rename(columns={'sim':'per_game_avg'}),how='inner',on='team')
        standings = pd.merge(left=standings,right=scores.sim.std().reset_index()\
        .rename(columns={'sim':'per_game_stdev'}),how='inner',on='team')
        standings['per_game_fano'] = standings['per_game_stdev']/standings['per_game_avg']
        standings = standings.sort_values(by=['winner' if postseason else 'playoffs'] + \
        (['many_mile'] if 'many_mile' in standings.columns.tolist() else []),\
        ascending=[False] + ([True] if 'many_mile' in standings.columns.tolist() else []))
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

    def war_sim(self):
        as_of = self.season*100 + self.week
        self.load_stats(as_of - 100,as_of - 1)
        """ Creating histograms across all players in each position """
        pos_hists = {'points':np.arange(-10,50.1,0.1)}
        for pos in self.stats.position.unique():
            pos_hists[pos] = np.histogram(self.stats.loc[self.stats.position == pos,'points'],bins=pos_hists['points'])[0]
            pos_hists[pos] = pos_hists[pos]/sum(pos_hists[pos])
        pos_hists['FLEX'] = np.histogram(self.stats.loc[self.stats.position.isin(['RB','WR','TE']),'points'],bins=pos_hists['points'])[0]
        pos_hists['FLEX'] = pos_hists['FLEX']/sum(pos_hists['FLEX'])
        """ Simulating an entire team using average players """
        sim_scores = pd.DataFrame({'QB':np.random.choice(pos_hists['points'][:-1],p=pos_hists['QB'],size=self.num_sims),\
        'RB1':np.random.choice(pos_hists['points'][:-1],p=pos_hists['RB'],size=self.num_sims),\
        'RB2':np.random.choice(pos_hists['points'][:-1],p=pos_hists['RB'],size=self.num_sims),\
        'WR1':np.random.choice(pos_hists['points'][:-1],p=pos_hists['WR'],size=self.num_sims),\
        'WR2':np.random.choice(pos_hists['points'][:-1],p=pos_hists['WR'],size=self.num_sims),\
        'TE':np.random.choice(pos_hists['points'][:-1],p=pos_hists['TE'],size=self.num_sims),\
        'FLEX':np.random.choice(pos_hists['points'][:-1],p=pos_hists['FLEX'],size=self.num_sims),\
        'K':np.random.choice(pos_hists['points'][:-1],p=pos_hists['K'],size=self.num_sims),\
        'DEF':np.random.choice(pos_hists['points'][:-1],p=pos_hists['DEF'],size=self.num_sims)})
        sim_scores['Total'] = sim_scores.QB + sim_scores.RB1 + sim_scores.RB2 + \
        sim_scores.WR1 + sim_scores.WR2 + sim_scores.TE + sim_scores.FLEX + \
        sim_scores.K + sim_scores.DEF
        player_sims = pd.DataFrame({self.players.loc[ind,'name']:np.round(np.random.normal(loc=self.players.loc[ind,'points_avg'],\
        scale=self.players.loc[ind,'points_stdev'],size=sim_scores.shape[0])) for ind in range(self.players.shape[0])})
        sim_scores = pd.merge(left=sim_scores,right=player_sims,left_index=True,right_index=True)
        """ Calculating the number of wins above replacement for each player """
        for player in sim_scores.columns[10:]:
            cols = sim_scores.columns[:9].tolist()
            pos = self.players.loc[self.players.name == player,'position'].values[0]
            if pos in ['RB','WR']:
                pos += '1'
            cols.pop(cols.index(pos))
            cols.append(player)
            sim_scores['Alt_Total'] = sim_scores[cols].sum(axis=1)
            self.players.loc[self.players.name == player,'WAR'] = (sum(sim_scores.loc[:sim_scores.shape[0]//2 - 1,'Alt_Total'].values > \
            sim_scores.loc[sim_scores.shape[0]//2:,'Total'].values)/(sim_scores.shape[0]//2) - 0.5)*14
            del sim_scores['Alt_Total']

    def possible_pickups(self,focus_on=[],exclude=[],limit_per=10,\
    team_name=None,postseason=True,verbose=True,payouts=[800,300,100]):
        as_of = self.season*100 + self.week
        self.refresh_oauth()
        orig_standings = self.season_sims(False,postseason,payouts)[1]
        added_value = pd.DataFrame(columns=['player_to_drop','player_to_add','wins_avg',\
        'wins_stdev','points_avg','points_stdev','per_game_avg','per_game_stdev',\
        'per_game_fano','playoffs','playoff_bye'] + (['winner','runner_up','third','earnings'] + \
        (['many_mile'] if self.schedule.team_1.isin(['The Algorithm']).any() \
        or self.schedule.team_2.isin(['The Algorithm']).any() else []) if postseason else []))
        if not team_name:
            team_name = [team['name'] for team in self.teams if team['team_key'] == self.lg.team_key()][0]
        players_to_drop = self.players.loc[self.players.fantasy_team == team_name]
        if players_to_drop.name.isin(focus_on).sum() > 0:
            players_to_drop = players_to_drop.loc[players_to_drop.name.isin(focus_on)]
        if players_to_drop.name.isin(exclude).sum() > 0:
            players_to_drop = players_to_drop.loc[~players_to_drop.name.isin(exclude)]
        available = self.players.loc[self.players.fantasy_team.isnull()].reset_index(drop=True)
        for my_player in players_to_drop.name:
            self.refresh_oauth(55)
            if players_to_drop.loc[players_to_drop.name == my_player,'until'].values[0] >= as_of%100:
                possible = available.loc[~available.name.str.contains('Average_')]
            else:
                possible = available.loc[~available.name.str.contains('Average_') & \
                (available.WAR >= self.players.loc[self.players.name == my_player,'WAR'].values[0] - 0.5)]
            if available.name.isin(focus_on).sum() > 0:
                possible = possible.loc[possible.name.isin(focus_on)]
            if possible.name.isin(exclude).sum() > 0:
                possible = possible.loc[~possible.name.isin(exclude)]
            if verbose:
                print(my_player + ': ' + str(possible.shape[0]) + ' better players')
                print(datetime.datetime.now())
            possible = possible.groupby('position').head(limit_per)
            for free_agent in possible.name:
                self.players.loc[self.players.name == my_player,'fantasy_team'] = None
                self.players.loc[self.players.name == free_agent,'fantasy_team'] = team_name
                new_standings = self.season_sims(False,postseason,payouts)[1]
                added_value = added_value.append(new_standings.loc[new_standings.team == team_name],ignore_index=True,sort=False)
                added_value.loc[added_value.shape[0] - 1,'player_to_drop'] = my_player
                added_value.loc[added_value.shape[0] - 1,'player_to_add'] = free_agent
                self.players.loc[self.players.name == my_player,'fantasy_team'] = team_name
                self.players.loc[self.players.name == free_agent,'fantasy_team'] = None
            if verbose:
                temp = added_value.iloc[-1*possible.shape[0]:][['player_to_drop','player_to_add','earnings']]
                temp['earnings'] -= orig_standings.loc[orig_standings.team == team_name,'earnings'].values[0]
                if temp.shape[0] > 0:
                    print(temp.sort_values(by='earnings',ascending=False).to_string(index=False))
                del temp
        if added_value.shape[0] > 0:
            for col in ['wins_avg','wins_stdev','points_avg','points_stdev',\
            'playoffs','playoff_bye'] + (['winner','runner_up','third','earnings'] + \
            (['many_mile'] if self.schedule.team_1.isin(['The Algorithm']).any() \
            or self.schedule.team_2.isin(['The Algorithm']).any() else []) if postseason else[]):
                added_value[col] -= orig_standings.loc[orig_standings.team == team_name,col].values[0]
                added_value[col] = round(added_value[col],4)
            added_value = added_value.sort_values(by='winner' if postseason else 'playoffs',ascending=False)
        return added_value

    def possible_adds(self,focus_on=[],exclude=[],limit_per=10,\
    team_name=None,postseason=True,verbose=True,payouts=[800,300,100]):
        as_of = self.season*100 + self.week
        self.refresh_oauth()
        orig_standings = self.season_sims(False,postseason,payouts)[1]
        added_value = pd.DataFrame(columns=['player_to_add','wins_avg','wins_stdev',\
        'points_avg','points_stdev','per_game_avg','per_game_stdev','per_game_fano',\
        'playoffs','playoff_bye'] + (['winner','runner_up','third','earnings'] + \
        (['many_mile'] if self.schedule.team_1.isin(['The Algorithm']).any() \
        or self.schedule.team_2.isin(['The Algorithm']).any() else []) if postseason else []))
        if not team_name:
            team_name = [team['name'] for team in self.teams if team['team_key'] == self.lg.team_key()][0]
        available = self.players.loc[self.players.fantasy_team.isnull()].reset_index(drop=True)
        possible = available.loc[~available.name.str.contains('Average_')]
        if possible.name.isin(focus_on).sum() > 0:
            possible = possible.loc[possible.name.isin(focus_on)]
        if possible.name.isin(exclude).sum() > 0:
            possible = possible.loc[~possible.name.isin(exclude)]
        possible = possible.groupby('position').head(limit_per)
        for free_agent in possible.name:
            self.players.loc[self.players.name == free_agent,'fantasy_team'] = team_name
            new_standings = self.season_sims(False,postseason,payouts)[1]
            added_value = added_value.append(new_standings.loc[new_standings.team == team_name],ignore_index=True,sort=False)
            added_value.loc[added_value.shape[0] - 1,'player_to_add'] = free_agent
            added_value.loc[added_value.shape[0] - 1,'position'] = possible.loc[possible.name == free_agent,'position'].values[0]
            added_value.loc[added_value.shape[0] - 1,'current_team'] = possible.loc[possible.name == free_agent,'current_team'].values[0]
            self.players.loc[self.players.name == free_agent,'fantasy_team'] = None
        if added_value.shape[0] > 0:
            for col in ['wins_avg','wins_stdev','points_avg','points_stdev',\
            'playoffs','playoff_bye'] + (['winner','runner_up','third','earnings'] + \
            (['many_mile'] if self.schedule.team_1.isin(['The Algorithm']).any() \
            or self.schedule.team_2.isin(['The Algorithm']).any() else []) if postseason else[]):
                added_value[col] -= orig_standings.loc[orig_standings.team == team_name,col].values[0]
                added_value[col] = round(added_value[col],4)
            added_value = added_value.sort_values(by='winner' if postseason else 'playoffs',ascending=False)
            if verbose:
                print(added_value[['player_to_add','earnings']].sort_values(by='earnings').to_string(index=False))
        return added_value

    def possible_drops(self,focus_on=[],exclude=[],team_name=None,\
    postseason=True,verbose=True,payouts=[800,300,100]):
        self.refresh_oauth()
        orig_standings = self.season_sims(False,postseason,payouts)[1]
        reduced_value = pd.DataFrame(columns=['player_to_drop','wins_avg','wins_stdev',\
        'points_avg','points_stdev','per_game_avg','per_game_stdev','per_game_fano',\
        'playoffs','playoff_bye'] + (['winner','runner_up','third','earnings'] + \
        (['many_mile'] if self.schedule.team_1.isin(['The Algorithm']).any() \
        or self.schedule.team_2.isin(['The Algorithm']).any() else []) if postseason else []))
        if not team_name:
            team_name = [team['name'] for team in self.teams if team['team_key'] == self.lg.team_key()][0]
        players_to_drop = self.players.loc[self.players.fantasy_team == team_name]
        if players_to_drop.name.isin(focus_on).sum() > 0:
            players_to_drop = players_to_drop.loc[players_to_drop.name.isin(focus_on)]
        if players_to_drop.name.isin(exclude).sum() > 0:
            players_to_drop = players_to_drop.loc[~players_to_drop.name.isin(exclude)]
        for my_player in players_to_drop.name:
            self.players.loc[self.players.name == my_player,'fantasy_team'] = None
            new_standings = self.season_sims(False,postseason,payouts)[1]
            reduced_value = reduced_value.append(new_standings.loc[new_standings.team == team_name],ignore_index=True,sort=False)
            reduced_value.loc[reduced_value.shape[0] - 1,'player_to_drop'] = my_player
            self.players.loc[self.players.name == my_player,'fantasy_team'] = team_name
        if reduced_value.shape[0] > 0:
            for col in ['wins_avg','wins_stdev','points_avg','points_stdev',\
            'playoffs','playoff_bye'] + (['winner','runner_up','third','earnings'] + \
            (['many_mile'] if self.schedule.team_1.isin(['The Algorithm']).any() \
            or self.schedule.team_2.isin(['The Algorithm']).any() else []) if postseason else []):
                reduced_value[col] -= orig_standings.loc[orig_standings.team == team_name,col].values[0]
                reduced_value[col] = round(reduced_value[col],4)
            reduced_value = reduced_value.sort_values(by='winner' if postseason else 'playoffs',ascending=False)
            if verbose:
                print(reduced_value[['player_to_drop','earnings']].sort_values(by='earnings').to_string(index=False))
        return reduced_value

    def possible_trades(self,focus_on=[],exclude=[],given=[],limit_per=10,\
    team_name=None,postseason=True,verbose=True,payouts=[800,300,100]):
        self.refresh_oauth()
        if not team_name:
            team_name = [team['name'] for team in self.teams if team['team_key'] == self.lg.team_key()][0]
        my_players = self.players.loc[(self.players.fantasy_team == team_name) & ~self.players.position.isin(['K','DEF'])]
        if my_players.name.isin(focus_on).sum() > 0:
            my_players = my_players.loc[my_players.name.isin(focus_on)]
        if my_players.name.isin(exclude).sum() > 0:
            my_players = my_players.loc[~my_players.name.isin(exclude)]
        their_players = self.players.loc[(self.players.fantasy_team != team_name) & ~self.players.position.isin(['K','DEF'])]
        if their_players.name.isin(focus_on).sum() > 0:
            their_players = their_players.loc[their_players.name.isin(focus_on)]
        if their_players.name.isin(exclude).sum() > 0:
            their_players = their_players.loc[~their_players.name.isin(exclude)]
        orig_standings = self.season_sims(False,postseason,payouts)[1]
        
        """ Make sure there are two teams and narrow down to that team!!! """
        given_check = type(given) == list and my_players.name.isin(given).any() \
        and their_players.loc[their_players.name.isin(given),'fantasy_team'].unique().shape[0] == 1
        if given_check:
            mine = [player for player in given if my_players.name.isin([player]).any()]
            theirs = [player for player in given if their_players.name.isin([player]).any()]
            their_team = self.players.loc[self.players.name.isin(theirs),'fantasy_team'].values[0]
            self.players.loc[self.players.name.isin(mine),'fantasy_team'] = their_team
            self.players.loc[self.players.name.isin(theirs),'fantasy_team'] = team_name
            my_players = my_players.loc[~my_players.name.isin(given)]
            their_players = their_players.loc[(their_players.fantasy_team == their_team) & ~their_players.name.isin(given)]
            my_players['WAR'] = 0.0
            their_players['WAR'] = 0.0
        """ Make sure there are two teams and narrow down to that teams!!! """
        
        my_added_value = pd.DataFrame()
        their_added_value = pd.DataFrame()
        for my_player in my_players.name:
            self.refresh_oauth(55)
            if their_players.name.isin(focus_on).any():
                possible = their_players.copy()
            else:
                possible = their_players.loc[abs(their_players.WAR - my_players.loc[my_players.name == my_player,'WAR'].values[0]) <= 0.5]
            # possible = their_players.loc[their_players.WAR - my_players.loc[my_players.name == my_player,'WAR'].values[0] > -1.0]
            if verbose:
                print(my_player + ': ' + str(possible.shape[0]) + ' comparable players')
                print(datetime.datetime.now())
            possible = possible.groupby('position').head(limit_per)
            for their_player in possible.name:
                their_team = self.players.loc[self.players.name == their_player,'fantasy_team'].values[0]
                self.players.loc[self.players.name == my_player,'fantasy_team'] = their_team
                self.players.loc[self.players.name == their_player,'fantasy_team'] = team_name
                new_standings = self.season_sims(False,postseason,payouts)[1]
                self.players.loc[self.players.name == my_player,'fantasy_team'] = team_name
                self.players.loc[self.players.name == their_player,'fantasy_team'] = their_team
                my_added_value = my_added_value.append(new_standings.loc[new_standings.team == team_name],ignore_index=True)
                their_added_value = their_added_value.append(new_standings.loc[new_standings.team == their_team],ignore_index=True)
                my_added_value.loc[my_added_value.shape[0] - 1,'player_to_trade_away'] = my_player
                my_added_value.loc[my_added_value.shape[0] - 1,'player_to_trade_for'] = their_player
                their_added_value.loc[their_added_value.shape[0] - 1,'player_to_trade_away'] = my_player
                their_added_value.loc[their_added_value.shape[0] - 1,'player_to_trade_for'] = their_player
            if verbose and possible.shape[0] > 0:
                me = my_added_value.iloc[-1*possible.shape[0]:][['player_to_trade_away','player_to_trade_for','earnings']].rename(columns={'earnings':'my_earnings'})
                them = their_added_value.iloc[-1*possible.shape[0]:][['player_to_trade_away','player_to_trade_for','team','earnings']].rename(columns={'earnings':'their_earnings'})
                me['my_earnings'] -= orig_standings.loc[orig_standings.team == team_name,'earnings'].values[0]
                for their_team in them.team.unique():
                    them.loc[them.team == their_team,'their_earnings'] -= orig_standings.loc[orig_standings.team == their_team,'earnings'].values[0]
                temp = pd.merge(left=me,right=them,how='inner',on=['player_to_trade_away','player_to_trade_for'])
                if temp.shape[0] > 0:
                    print(temp.sort_values(by='my_earnings',ascending=False).to_string(index=False))
                del me, them, temp, their_team
        
        if given_check:
            mine = [player for player in given if my_players.name.isin([player]).any()]
            theirs = [player for player in given if their_players.name.isin([player]).any()]
            their_team = self.players.loc[self.players.name.isin(theirs),'fantasy_team'].values[0]
            self.players.loc[self.players.name.isin(mine),'fantasy_team'] = their_team
            self.players.loc[self.players.name.isin(theirs),'fantasy_team'] = team_name

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

    def perGameDelta(self,team_name=None,postseason=True,payouts=[800,300,100]):
        as_of = self.season*100 + self.week
        self.refresh_oauth()
        if not team_name:
            team_name = [team['name'] for team in self.teams if team['team_key'] == self.lg.team_key()][0]
        deltas = self.season_sims(False,postseason,payouts)[1][['team','earnings']]
        for team in self.players.fantasy_team.unique():
            new_standings = self.season_sims(False,postseason,payouts,\
            fixed_winner=[as_of%100,team])[1][['team','earnings']].rename(columns={'earnings':'earnings_new'})
            deltas = pd.merge(left=deltas,right=new_standings,how='inner',on='team')
            deltas[team] = deltas['earnings_new'] - deltas['earnings']
            del deltas['earnings_new']
            print(deltas[['team',team]].to_string(index=False))
        del deltas['earnings']
        return deltas.set_index('team').T.reset_index().rename(columns={'index':'winner'})

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
        .replace('_2','') in ['playoffs','playoff_bye','winner','runner_up','third','many_mile']:
            writer.sheets[name].set_column(idx,idx,max_len,p)
        else:
            writer.sheets[name].set_column(idx,idx,max_len,f)
    writer.sheets[name].autofilter('A1:' + (chr(64 + (df.shape[1] - 1)//26) + \
    chr(65 + (df.shape[1] - 1)%26)).replace('@','') + str(df.shape[0] + 1))
    return writer

def sendEmail(subject,body,address,filename=None):
    message = MIMEMultipart()
    message["From"] = os.environ['EMAIL_SENDER']
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
        server.login(os.environ['EMAIL_SENDER'],os.environ['EMAIL_PW'])
        server.sendmail(os.environ['EMAIL_SENDER'],address,text)

def main():
    parser = optparse.OptionParser()
    parser.add_option('--season',action="store",dest="season",help="season of interest")
    parser.add_option('--week',action="store",dest="week",help="week to project the season from")
    parser.add_option('--name',action="store",dest="name",help="name of team to analyze in the case of multiple teams in a single season")
    parser.add_option('--earliest',action="store",dest="earliest",help="earliest week of stats being considered, e.g. 201807 corresponds to week 7 of the 2018 season")
    parser.add_option('--games',action="store",dest="games",help="number of games to build each player's prior off of")
    parser.add_option('--basaloppqbtime',action="store",dest="basaloppqbtime",help="scaling factors for basal/opponent/quarterback/time factors, comma-separated string of values")
    parser.add_option('--sims',action="store",dest="sims",help="number of season simulations")
    parser.add_option('--payouts',action="store",dest="payouts",help="comma separated string containing integer payouts for 1st, 2nd, and 3rd")
    parser.add_option('--injurytries',action="store",dest="injurytries",help="number of times to try pulling injury statuses before rolling with it")
    parser.add_option('--rosterpcts',action="store_true",dest="rosterpcts",help="whether to pull roster percentages for each player")
    parser.add_option('--pickups',action="store",dest="pickups",help='assess possible free agent pickups for the players specified ("all" will analyze all possible pickups)')
    parser.add_option('--adds',action="store_true",dest="adds",help="whether to assess possible free agent adds")
    parser.add_option('--drops',action="store_true",dest="drops",help="whether to assess possible drops")
    parser.add_option('--trades',action="store",dest="trades",help='assess possible trades for the players specified ("all" will analyze all possible trades)')
    parser.add_option('--given',action="store",dest="given",help='given players to start with for multi-player trades')
    parser.add_option('--deltas',action="store_true",dest="deltas",help="whether to assess deltas for each matchup of the current week")
    parser.add_option('--output',action="store",dest="output",help="where to save the final projections spreadsheet")
    parser.add_option('--email',action="store",dest="email",help="where to send the final projections spreadsheet")
    options,args = parser.parse_args()
    if str(options.season).isnumeric():
        options.season = int(options.season)
    if str(options.week).isnumeric():
        options.week = int(options.week)
    if options.basaloppqbtime:
        try:
            options.basaloppqbtime = [float(val) for val in options.basaloppqbtime]
        except:
            print('Invalid rate inference parameters, using defaults...')
            options.basaloppqbtime = None
    if str(options.injurytries).isnumeric():
        options.injurytries = int(options.injurytries)
    else:
        options.injurytries = 10

    league = League(name=options.name, season=options.season, week=options.week, 
    roster_pcts=options.rosterpcts, injurytries=options.injurytries,
    num_sims=options.sims, earliest=options.earliest, 
    reference_games=options.games, basaloppqbtime=options.basaloppqbtime)

    if options.payouts:
        options.payouts = options.payouts.split(',')
        if all([val.isnumeric() for val in options.payouts]):
            options.payouts = [float(val) for val in options.payouts]
        else:
            print('Weird values provided for payouts... Assuming standard payouts...')
            options.payouts = [100*len(league.teams)*0.6,100*len(league.teams)*0.3,100*len(league.teams)*0.1]
        if len(options.payouts) > 3:
            print('Too many values provided for payouts... Only using top three...')
            options.payouts = options.payouts[:3]
    elif league.name == 'The Algorithm':
        options.payouts = [720,360,120]
    elif league.name == 'Toothless Wonders':
        options.payouts = [350,100,50]
    elif league.name == 'The GENIEs':
        options.payouts = [100,0,0]
    elif league.name == "The Great Gadsby's":
        options.payouts = [50,35,15]
    else:
        options.payouts = [100*len(league.teams)*0.6,100*len(league.teams)*0.3,100*len(league.teams)*0.1]
    if not options.output:
        options.output = os.path.expanduser('~/Documents/') if os.path.exists(os.path.expanduser('~/Documents/')) else os.path.expanduser('~/')
        if not os.path.exists(options.output + league.name.replace(' ','')):
            os.mkdir(options.output + league.name.replace(' ',''))
        if not os.path.exists(options.output + league.name.replace(' ','') + '/' + str(options.season)):
            os.mkdir(options.output + league.name.replace(' ','') + '/' + str(options.season))
        options.output += league.name.replace(' ','') + '/' + str(options.season)
    if options.output[-1] != '/':
        options.output += '/'
    writer = pd.ExcelWriter(options.output + 'FantasyFootballProjections_{}Week{}.xlsx'\
    .format(datetime.datetime.now().strftime('%A'),options.week),engine='xlsxwriter')
    writer.book.add_format({'align': 'vcenter'})

    rosters = league.players.loc[~league.players.fantasy_team.isnull()]\
    .sort_values(by=['fantasy_team','WAR'],ascending=[True,False]).copy()
    for col in ['points_avg','points_stdev','WAR','game_factor','opp_factor','qb_factor']:
        rosters[col] = round(rosters[col],3)
    writer = excelAutofit(rosters[['name','position','current_team',\
    'points_avg','points_stdev','WAR','fantasy_team','num_games','game_factor',\
    'opp_factor','qb_factor','status','bye_week','until','starter','injured']],'Rosters',writer)
    writer.sheets['Rosters'].freeze_panes(1,1)
    writer.sheets['Rosters'].conditional_format('F2:F' + str(rosters.shape[0] + 1),\
    {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
    available = league.players.loc[league.players.fantasy_team.isnull() & \
    (league.players.until.isnull() | (league.players.until < 17))].sort_values(by='WAR',ascending=False)
    del available['fantasy_team']
    for col in ['points_avg','points_stdev','WAR','game_factor','opp_factor','qb_factor']:
        available[col] = round(available[col],3)
    writer = excelAutofit(available[['name','position','current_team',\
    'points_avg','points_stdev','WAR','num_games','game_factor','opp_factor',\
    'qb_factor','status','bye_week','until']],'Available',writer)
    writer.sheets['Available'].freeze_panes(1,1)
    writer.sheets['Available'].conditional_format('F2:F' + str(available.shape[0] + 1),\
    {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
    
    schedule_sim, standings_sim = league.season_sims(True,payouts=options.payouts)
    print(schedule_sim.loc[schedule_sim.week == league.lg.current_week(),\
    ['week','team_1','team_2','win_1','win_2','points_avg_1','points_avg_2']].to_string(index=False))
    print(standings_sim[['team','wins_avg','points_avg','playoffs','playoff_bye','winner','earnings'] + \
    (['many_mile'] if league.name == 'The Algorithm' else [])].to_string(index=False))
    writer = excelAutofit(schedule_sim[['week','team_1','team_2','win_1','win_2',\
    'points_avg_1','points_stdev_1','points_avg_2','points_stdev_2','me']],'Schedule',writer)
    writer.sheets['Schedule'].freeze_panes(1,3)
    writer.sheets['Schedule'].conditional_format('D2:E' + str(schedule_sim.shape[0] + 1),\
    {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
    writer = excelAutofit(standings_sim[['team','wins_avg','wins_stdev',\
    'points_avg','points_stdev','per_game_avg','per_game_stdev','per_game_fano',\
    'playoffs','playoff_bye','winner','runner_up','third','earnings'] + \
    (['many_mile'] if league.name == 'The Algorithm' else [])],'Standings',writer)
    writer.sheets['Standings'].freeze_panes(1,1)
    writer.sheets['Standings'].conditional_format('I2:M' + str(standings_sim.shape[0] + 1),\
    {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
    writer.sheets['Standings'].conditional_format('N2:N' + str(standings_sim.shape[0] + 1),\
    {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
    if options.name == 'The Algorithm':
        writer.sheets['Standings'].conditional_format('O2:O' + str(standings_sim.shape[0] + 1),\
        {'type':'3_color_scale','max_color':'#FF6347','mid_color':'#FFD700','min_color':'#3CB371'})
    
    if options.pickups:
        pickups = league.possible_pickups(focus_on=[val.strip() for val in options.pickups.split(',')] \
        if options.pickups.lower() != 'all' else [],exclude=[],limit_per=5,payouts=options.payouts)
        writer = excelAutofit(pickups[['player_to_drop','player_to_add','wins_avg','wins_stdev',\
        'points_avg','points_stdev','per_game_avg','per_game_stdev','per_game_fano',\
        'playoffs','playoff_bye','winner','runner_up','third','earnings'] + \
        (['many_mile'] if options.name == 'The Algorithm' else [])],'Pickups',writer)
        writer.sheets['Pickups'].freeze_panes(1,2)
        writer.sheets['Pickups'].conditional_format('J2:N' + str(pickups.shape[0] + 1),\
        {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
        writer.sheets['Pickups'].conditional_format('O2:O' + str(pickups.shape[0] + 1),\
        {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
        if options.name == 'The Algorithm':
            writer.sheets['Pickups'].conditional_format('P2:P' + str(pickups.shape[0] + 1),\
            {'type':'3_color_scale','max_color':'#FF6347','mid_color':'#FFD700','min_color':'#3CB371'})

    if options.adds:
        adds = league.possible_adds(focus_on=[val.strip() for val in options.pickups.split(',')] \
        if options.pickups.lower() != 'all' else [],exclude=[],limit_per=5,payouts=options.payouts)
        writer = excelAutofit(adds[['player_to_add','wins_avg','wins_stdev',\
        'points_avg','points_stdev','per_game_avg','per_game_stdev','per_game_fano',\
        'playoffs','playoff_bye','winner','runner_up','third','earnings'] + \
        (['many_mile'] if options.name == 'The Algorithm' else [])],'Adds',writer)
        writer.sheets['Adds'].freeze_panes(1,1)
        writer.sheets['Adds'].conditional_format('J2:N' + str(adds.shape[0] + 1),\
        {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
        writer.sheets['Adds'].conditional_format('O2:O' + str(adds.shape[0] + 1),\
        {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
        if options.name == 'The Algorithm':
            writer.sheets['Adds'].conditional_format('P2:P' + str(adds.shape[0] + 1),\
            {'type':'3_color_scale','max_color':'#FF6347','mid_color':'#FFD700','min_color':'#3CB371'})

    if options.drops:
        drops = league.possible_drops(focus_on=[val.strip() for val in options.pickups.split(',')] \
        if options.pickups.lower() != 'all' else [],exclude=[],payouts=options.payouts)
        writer = excelAutofit(drops[['player_to_drop','wins_avg','wins_stdev',\
        'points_avg','points_stdev','per_game_avg','per_game_stdev','per_game_fano',\
        'playoffs','playoff_bye','winner','runner_up','third','earnings'] + \
        (['many_mile'] if options.name == 'The Algorithm' else [])],'Drops',writer)
        writer.sheets['Drops'].freeze_panes(1,1)
        writer.sheets['Drops'].conditional_format('J2:N' + str(drops.shape[0] + 1),\
        {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
        writer.sheets['Drops'].conditional_format('O2:O' + str(drops.shape[0] + 1),\
        {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
        if options.name == 'The Algorithm':
            writer.sheets['Drops'].conditional_format('P2:P' + str(drops.shape[0] + 1),\
            {'type':'3_color_scale','max_color':'#FF6347','mid_color':'#FFD700','min_color':'#3CB371'})
    
    if options.trades or options.given:
        if not options.trades:
            options.trades = "all"
        trades = league.possible_trades(focus_on=[val.strip() for val in options.pickups.split(',')] \
        if options.pickups.lower() != 'all' else [],exclude=[],given=[],limit_per=10,payouts=options.payouts)
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
        deltas = league.perGameDelta(payouts=options.payouts)
        writer = excelAutofit(deltas,'Deltas',writer)
        writer.sheets['Deltas'].freeze_panes(0,1)
        writer.sheets['Deltas'].conditional_format('B2:' + chr(ord('A') + deltas.shape[1]) + str(deltas.shape[0] + 1),\
        {'type':'3_color_scale','min_color':'#FF6347','mid_color':'#FFD700','max_color':'#3CB371'})
    
    writer.save()
    os.system('touch -t {} "{}"'.format(datetime.datetime.now().strftime('%Y%m%d%H%M'),'/'.join(options.output.split('/')[:-2])))
    if options.email:
        try:
            sendEmail('Fantasy Football Projections for ' + options.name,\
            'Best of luck to you this fantasy football season!!!',options.email,\
            options.output + 'FantasyFootballProjections_{}Week{}.xlsx'\
            .format(datetime.datetime.now().strftime('%A'),options.week))
        except:
            print("Couldn't email results, maybe no wifi...\nResults saved to " + \
            options.output + 'FantasyFootballProjections_{}Week{}.xlsx'\
            .format(datetime.datetime.now().strftime('%A'),options.week))

if __name__ == "__main__":
    main()





