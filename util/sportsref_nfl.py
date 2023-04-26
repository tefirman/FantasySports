#!/usr/bin/env python
# -*-coding:utf-8 -*-
'''
@File    :   sportsref_nfl.py
@Time    :   2023/04/12 21:49:12
@Author  :   Taylor Firman
@Version :   1.0
@Contact :   tefirman@gmail.com
@Desc    :   Collection of functions to easily pull down statistics from pro-football-reference.com
'''

import requests
from bs4 import BeautifulSoup
import time
import pandas as pd

base_url = "https://www.pro-football-reference.com/"

def get_page(endpoint: str):
    """
    Pulls down the raw html for the specified endpoint of Pro Football Reference
    and adds an additional four second delay to avoid triggering the 1hr jailtime 
    for exceeding 20 requests per minute.

    Args:
        endpoint (str): relative location of the page to pull down.

    Returns:
        str: raw html of the specified endpoint.
    """
    time.sleep(4)
    response = requests.get(base_url + endpoint).text
    uncommented = response.replace('<!--','').replace('-->','')
    soup = BeautifulSoup(uncommented,'html.parser')
    return soup


def parse_table(raw_text: str, table_name: str):
    """
    Parses out the desired table from the raw html text into a pandas dataframe.

    Args:
        raw_text (bs4.BeautifulSoup): raw html from the page of interest.
        table_name (str): title of the table to extract.

    Returns:
        pd.DataFrame: dataframe containing the data from the specified table.
    """
    players = raw_text.find(id=table_name).find_all('tr',attrs={'class':None})
    columns = [col.attrs['data-stat'] for col in players.pop(0).find_all('th')]
    stats = pd.DataFrame()
    for player in players:
        if player.text == "Playoffs":
            continue
        entry = {}
        for col in columns:
            entry[col] = player.find(['th','td'],attrs={'data-stat':col})
            if col == 'boxscore_word':
                entry[col] = entry[col].find('a').attrs['href']
                entry[col] = entry[col].split('/')[-1].split('.')[0]
            else:
                if col == 'player':
                    entry['player_id'] = entry[col].attrs['data-append-csv']
                entry[col] = entry[col].text
        stats = pd.concat([stats,pd.DataFrame(entry,index=[stats.shape[0]])])
    stats = stats.replace('',None).reset_index(drop=True)
    for col in stats.columns:
        if col.endswith('_pct'):
            stats[col] = stats[col].str.replace('%','')
        stats[col] = stats[col].astype(float,errors='ignore')
    return stats


def get_schedule(season: int, playoffs=False):
    """
    Pull the specified season schedule from Pro Football Reference 
    and processes it into the form of a pandas dataframe.

    Args:
        season (int): season of interest.
        playoffs (bool, optional): whether to include playoff games, defaults to False.

    Returns:
        pd.DataFrame: details for each game schedule during the regular season of the year provided.
    """
    raw_text = get_page('years/{}/games.htm'.format(season))
    schedule = parse_table(raw_text,'games')
    if not playoffs:
        schedule = schedule.loc[schedule.week_num.str.isnumeric()].reset_index(drop=True)
        schedule.week_num = schedule.week_num.astype(int)
    return schedule


def get_boxscore(game_id: str):
    """
    Pulls down the per-player statistics from the boxscore of the specified game.

    Args:
        game_id (str): SportsReference identifier string for the game in question (e.g. 202209080ram).

    Returns:
        pd.DataFrame: dataframe containing the per-player stats from the specified game.
    """
    raw_text = get_page('boxscores/{}.htm'.format(game_id))
    season_week = raw_text.find('div',attrs={'class':"game_summaries compressed"})
    season_week = season_week.find('a').attrs['href']
    season = int(season_week.split('/')[-2])
    week = int(season_week.split('/')[-1].split('_')[-1].split('.')[0])
    game_stats = pd.concat([parse_table(raw_text,'player_offense'),
                            parse_table(raw_text,'player_defense'),
                            parse_table(raw_text,'returns'),
                            parse_table(raw_text,'kicking')])
    game_stats = game_stats.fillna(0.0).groupby(['player','player_id','team']).sum().reset_index()
    game_stats['season'] = season
    game_stats['week'] = week
    game_stats['game_id'] = game_id
    starters = pd.concat([parse_table(raw_text,'home_starters'),
                          parse_table(raw_text,'vis_starters')])
    snaps = pd.concat([parse_table(raw_text,'home_snap_counts'),
                       parse_table(raw_text,'vis_snap_counts')])
    snaps = snaps.loc[~snaps.player_id.isin(starters.player_id.tolist())]\
    .sort_values(by=['off_pct','def_pct','st_pct'],ascending=False).reset_index(drop=True)
    starters = pd.merge(left=pd.concat([starters.iloc[::-1],snaps]),\
    right=game_stats[['player','player_id','team']],how='inner',on=['player','player_id'])
    starters['dummy'] = 1
    starters['string'] = starters.groupby(['team','pos']).dummy.rank(method='first')
    game_stats = pd.merge(left=game_stats,right=starters[['player','player_id','team','pos','string']],how='inner',on=['player','player_id','team'])
    return game_stats


def get_games(start: int, finish: int):
    """
    Pulls individual player statistics for each game in the specified timeframe from Pro Football Reference.

    Args:
        start (int): year and number of the first week of interest (YYYYWW, e.g. 202102 = week 2 of 2021).
        finish (int): year and number of the last week of interest (YYYYWW, e.g. 202307 = week 7 of 2023).
    
    Returns:
        pd.DataFrame: dataframe containing player statistics for games during the timespan of interest.
    """
    stats = pd.DataFrame()
    for season in range(start//100,finish//100 + 1):
        print(season)
        season_sched = get_schedule(season)
        if season == start//100:
            season_sched = season_sched.loc[season_sched.week_num >= start%100].reset_index(drop=True)
        if season == finish//100:
            season_sched = season_sched.loc[season_sched.week_num <= finish%100].reset_index(drop=True)
        for ind in range(season_sched.shape[0]):
            print(season_sched.loc[ind,'boxscore_word'])
            stats = pd.concat([stats,get_boxscore(season_sched.loc[ind,'boxscore_word'])])
    return stats


def get_names():
    """
    Pulls the player id and name for every player on Pro Football Reference for conversion purposes.

    Returns:
        pd.DataFrame: dataframe containing name, position, 
        player id, and timespan of every player in the database.
    """
    names = pd.DataFrame()
    for letter in range(65, 91):
        raw_text = get_page('players/' + chr(letter))
        players = raw_text.find(id='div_players').find_all('p')
        for player in players:
            entry = {'name':player.find('a').text,
            'position':player.text.split('(')[-1].split(')')[0],
            'player_id':player.find('a').attrs['href'].split('/')[-1].split('.')[0],
            'years_active':player.text.split(') ')[-1]}
            names = pd.concat([names,pd.DataFrame(entry,index=[names.shape[0]])])
    names.loc[names.name == "Logan Thomas", "position"] = "TE"
    names.loc[names.name == "Cordarrelle Patterson", "position"] = "RB"
    return names


