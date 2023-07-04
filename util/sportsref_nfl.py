#!/usr/bin/env python
# -*-coding:utf-8 -*-
"""
@File    :   sportsref_nfl.py
@Time    :   2023/04/12 21:49:12
@Author  :   Taylor Firman
@Version :   1.0
@Contact :   tefirman@gmail.com
@Desc    :   Collection of functions to easily pull down statistics from pro-football-reference.com
"""

import requests
from bs4 import BeautifulSoup
import time
import numpy as np
import pandas as pd
import os
import datetime
from geopy.distance import geodesic
import shutil
import gzip
import sys

base_url = "https://www.pro-football-reference.com/"


def get_page(endpoint: str):
    """
    Pulls down the raw html for the specified endpoint of Pro Football Reference
    and adds an additional four second delay to avoid triggering the 1hr jailtime
    for exceeding 20 requests per minute.

    Args:
        endpoint (str): relative location of the page to pull down.

    Returns:
        bs4.BeautifulSoup: parsed html of the specified endpoint.
    """
    time.sleep(4)
    try:
        response = requests.get(base_url + endpoint).text
    except requests.exceptions.ConnectionError as e:
        print('GETTING CONNECTION ERROR AGAIN!!!')
        print(endpoint)
        sys.exit(1)
    uncommented = response.replace("<!--", "").replace("-->", "")
    soup = BeautifulSoup(uncommented, "html.parser")
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
    players = raw_text.find(id=table_name).find_all("tr", attrs={"class": None})
    columns = [col.attrs["data-stat"] for col in players.pop(0).find_all("th")]
    stats = pd.DataFrame()
    for player in players:
        if player.text == "Playoffs":
            continue
        entry = {}
        for col in columns:
            entry[col] = player.find(["th", "td"], attrs={"data-stat": col})
            if col in ["boxscore_word", "stadium_name"]:
                abbrev = entry[col].find("a")
                if abbrev is not None:
                    new_col = col.split("_")[0] + "_abbrev"
                    entry[new_col] = abbrev.attrs["href"]
                    entry[new_col] = entry[new_col].split("/")[-1].split(".")[0]
            elif col == "player" and "data-append-csv" in entry[col].attrs:
                entry["player_id"] = entry[col].attrs["data-append-csv"]
            elif col in ["winner", "loser", "home_team", "visitor_team","teams","team"] and entry[col].find("a") is not None:
                entry[col + "_abbrev"] = ", ".join(
                    [team.attrs["href"].split("/")[-2].upper() for team in entry[col].find_all("a")]
                )
            entry[col] = entry[col].text
        stats = pd.concat([stats, pd.DataFrame(entry, index=[stats.shape[0]])])
    stats = stats.replace("", None).reset_index(drop=True)
    for col in stats.columns:
        if col.endswith("_pct"):
            stats[col] = stats[col].str.replace("%", "")
        stats[col] = stats[col].astype(float, errors="ignore")
    return stats


def get_intl_games():
    """
    Pulls details about the games in the NFL International Series (used in annotating neutral site games).

    Returns:
        pd.DataFrame: dataframe containing dates, teams, and scores for each matchup.
    """
    response = requests.get(
        "https://en.wikipedia.org/wiki/NFL_International_Series"
    ).text
    soup = BeautifulSoup(response, "html.parser")
    tables = soup.find_all("table", attrs={"class": "wikitable sortable"})[1:-1]
    intl_games = pd.concat(pd.read_html(str(tables)), ignore_index=True)
    intl_games.Year = intl_games.Year.astype(str).str.split(" ").str[0].astype(int)
    intl_games["team1"] = intl_games["Designated home team"].str.split("\[").str[0]
    intl_games["team2"] = intl_games["Designated visitor"].str.split("\[").str[0]
    intl_games = intl_games.loc[
        ~intl_games.Attendance.astype(str).str.contains("\[")
    ].reset_index(drop=True)
    intl_games["game_date"] = pd.to_datetime(
        intl_games.Date + ", " + intl_games.Year.astype(str), infer_datetime_format=True
    )
    return intl_games[["game_date", "team1", "team2", "Stadium"]]


def get_depth_chart(team_abbrev: str):
    response = requests.get("https://www.espn.com/nfl/team/depth/_/name/{}".format(team_abbrev)).text
    soup = BeautifulSoup(response, "html.parser")
    tables = soup.find_all('table')
    depth = pd.DataFrame()
    for table_ind in range(len(tables)//2):
        positions = [pos.text.strip() for pos in tables[table_ind*2].find_all('td')]
        players = [player.text.strip() for player in tables[table_ind*2 + 1].find_all('td')]
        num_strings = len(players)//len(positions)
        for pos in range(len(positions)):
            for string in range(num_strings):
                depth = pd.concat([depth,pd.DataFrame({'player':[players[pos*num_strings + string]],\
                'pos':[positions[pos]],'string':[string + 1]})],ignore_index=True)
    depth.loc[depth.pos.isin(['PK']),'pos'] = 'K'
    wrs = depth.pos == 'WR'
    depth.loc[wrs,'string'] = 1 + (depth.loc[wrs].string.rank(method='first') - 1)/3
    depth = depth.loc[depth.player != '-'].reset_index(drop=True)
    for status in ['Q','SUSP']: # Need to expand this with possible values as the season goes on...
        injured = depth.player.str.endswith(' ' + status)
        depth.loc[injured,'player'] = depth.loc[injured,'player'].str.split(' ').str[:-1].apply(' '.join)
    corrections = pd.read_csv("https://raw.githubusercontent.com/tefirman/FantasySports/main/res/football/name_corrections.csv")
    depth = pd.merge(left=depth, right=corrections.rename(columns={'name':'player'}), how="left", on="player")
    to_fix = ~depth.new_name.isnull()
    depth.loc[to_fix, "player"] = depth.loc[to_fix, "new_name"]
    del depth['new_name']
    return depth


def get_all_depth_charts():
    teams = pd.read_csv("https://raw.githubusercontent.com/tefirman/FantasySports/main/res/football/team_abbrevs.csv")
    teams['espn'] = teams.fivethirtyeight.str.replace('OAK','LV')
    depths = pd.DataFrame(columns=['team'])
    for ind in range(teams.shape[0]):
        depths = pd.concat([depths,get_depth_chart(teams.loc[ind,'espn'])],ignore_index=True)
        depths.team = depths.team.fillna(teams.loc[ind,'real_abbrev'])
    return depths


def get_stadiums():
    """
    Pulls details about all stadiums ever used for an NFL game.

    Returns:
        pd.DataFrame: dataframe containing names, locations, and timespans of each stadium.
    """
    raw_text = get_page("stadiums")
    stadiums = parse_table(raw_text, "stadiums")
    return stadiums


def get_team_stadium(abbrev: str, season: int):
    """
    Identifies the home stadium of the specified team during the specified season.

    Args:
        abbrev (str): team abbreviation according to Pro Football Reference
        season (int): year of the NFL season of interest

    Returns:
        str: stadium identifier according to Pro Football Reference
    """
    raw_text = get_page("teams/{}/{}.htm".format(abbrev.lower(), int(season)))
    team_info = raw_text.find(id="meta").find_all("p")
    stadium_info = [val for val in team_info if val.text.startswith("Stadium:")]
    if len(stadium_info) == 0:
        stadiums = get_stadiums()
        stadiums.teams_abbrev = stadiums.teams_abbrev.str.split(", ")
        stadiums = stadiums.explode("teams_abbrev", ignore_index=True)
        stadium_id = stadiums.loc[
            (stadiums.teams_abbrev == abbrev)
            & (stadiums.year_min <= season)
            & (stadiums.year_max >= season),
            "stadium_abbrev",
        ]
        if stadium_id.shape[0] > 0:
            stadium_id = stadium_id.values[0]
        else:
            print("Can't find home stadium for {} {}...".format(season,abbrev))
            stadium_id = None
    else:
        stadium_info = stadium_info[0]
        stadium_id = stadium_info.find("a").attrs["href"].split("/")[-1].split(".")[0]
    return stadium_id


def get_game_stadium(game_id: str):
    """
    Identifies the stadium where the specified game was played.

    Args:
        game_id (str): Pro Football Reference identifier string for the game in question (e.g. 202209080ram).

    Returns:
        str: stadium identifier according to Pro Football Reference.
    """
    raw_text = get_page("boxscores/{}.htm".format(game_id))
    game_info = raw_text.find("div", attrs={"class": "scorebox_meta"})
    stadium_id = game_info.find("a").attrs["href"].split("/")[-1].split(".")[0]
    return stadium_id


def get_address(stadium_id: str):
    """
    Identifies the address of the specified stadium (with a few typo corrections here and there).

    Args:
        stadium_id (str): stadium identifier according to Pro Football Reference.

    Returns:
        str: address of the specified stadium according to Pro Football Reference.
    """
    raw_text = get_page("stadiums/{}.htm".format(stadium_id))
    address = raw_text.find(id="meta").find("p").text
    fixes = {
        "New Jersey": "NJ",
        "Park Houston": "Park, Houston",
        "Blvd Opa-Locka": "Blvd, Opa-Locka",
        "Northumberland Development Project": "782 High Rd, London N17 0BX, UK",
    }
    for fix in fixes:
        address = address.replace(fix, fixes[fix])
    return address


def download_zip_codes(url: str = "https://nominatim.org/data/us_postcodes.csv.gz"):
    response = requests.get(url,stream=True)
    with open(url.split('/')[-1],'wb') as out_file:
        shutil.copyfileobj(response.raw,out_file)
    with gzip.open(url.split('/')[-1], 'rb') as f_in:
        with open(url.split('/')[-1][:-3], 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
    zips = pd.read_csv(url.split('/')[-1][:-3],dtype={'postcode':str})
    return zips


def get_coordinates(address: str, zips: pd.DataFrame):
    """
    Provides the coordinates of the specified address. If no exact coordinates are available,
    city, state, and zip code are used for an approximate position.

    Args:
        address (str): physical address of interest.

    Returns:
        str: latitudinal and longitudinal coordinates separated by a comma.
    """
    stad_zip = address.split(' ')[-1]
    stad_coords = zips.loc[zips.postcode == stad_zip,['lat','lon']].astype(str)
    if stad_coords.shape[0] > 0:
        coords = ",".join(stad_coords.values[0])
    elif stad_zip == "Mexico":
        coords = "19.3029,-99.1505"
    elif stad_zip == "UK":
        coords = "51.5072,-0.1276"
    elif stad_zip == "Bavaria":
        coords = "48.2188,11.6248"
    else:
        print("Can't find zip code provided: " + str(stad_zip))
        print("Using centerpoint of US...")
        coords = "37.0902,-95.7129"
    return coords


class Schedule:
    """
    Schedule class that gathers all matchups and outcomes for the seasons in question and
    assess the evolution of each team's elo ranking according to 538's methodology.

    Attributes:
        schedule: dataframe containing matchup details for the seasons of interest.
    """

    def __init__(self, start: int, finish: int, playoffs: bool = True, elo: bool = False, qbelo: bool = False):
        """
        Initializes a Schedule object using the parameters provided and class functions defined below.

        Args:
            start (int): first NFL season of interest
            finish (int): last NFL season of interest
            playoffs (bool, optional): whether to include playoff games, defaults to True.
            elo (bool, optional): whether to include elo rating considerations, defaults to False.
            qbelo (bool, optional): whether to include QB elo rating considerations, defaults to False.
        """
        self.get_schedules(start, finish)
        self.add_weeks()
        self.convert_to_home_away()
        self.mark_intl_games()
        self.add_rest()
        if elo:
            self.add_team_coords()
            self.add_game_coords()
            self.add_travel()
            self.add_elo_columns(qbelo)
            while self.schedule.elo1_pre.isnull().any():
                self.next_init_elo()
                self.next_elo_prob()
                self.next_elo_delta()
        if not playoffs:
            self.schedule = self.schedule.loc[
                self.schedule.week_num.str.isnumeric()
            ].reset_index(drop=True)

    def get_schedules(self, start: int, finish: int):
        self.schedule = pd.DataFrame(columns=["season"])
        for season in range(int(start), int(finish) + 1):
            raw_text = get_page("years/{}/games.htm".format(season))
            season_sched = parse_table(raw_text, "games")
            season_sched = season_sched.loc[~season_sched.week_num.str.startswith('Pre')].reset_index(drop=True)
            season_sched['season'] = season
            if "game_date" not in season_sched.columns: # Current season
                season_sched['game_date'] = season_sched.boxscore_word + ', ' + \
                (datetime.datetime.now().year + season_sched.boxscore_word.str.startswith('January').astype(int)).astype(str)
                season_sched = season_sched.rename(columns={'visitor_team':'winner',\
                'visitor_team_abbrev':'winner_abbrev','home_team':'loser','home_team_abbrev':'loser_abbrev'})
                season_sched[['yards_win','to_win','yards_lose','to_lose']] = None
            self.schedule = pd.concat([self.schedule, season_sched], ignore_index=True)

    def add_weeks(self):
        self.schedule.game_date = pd.to_datetime(
            self.schedule.game_date, infer_datetime_format=True
        )
        min_date = self.schedule.groupby("season").game_date.min().reset_index()
        self.schedule = pd.merge(
            left=self.schedule,
            right=min_date,
            how="inner",
            on="season",
            suffixes=("", "_min"),
        )
        self.schedule["days_into_season"] = (
            self.schedule.game_date - self.schedule.game_date_min
        ).dt.days
        self.schedule["week"] = self.schedule.days_into_season // 7 + 1

    def convert_to_home_away(self):
        list1 = ["team1","team1_abbrev","score1","yards1","timeouts1"]
        list2 = ["team2","team2_abbrev","score2","yards2","timeouts2"]
        winner_list = ["winner","winner_abbrev","pts_win","yards_win","to_win"]
        loser_list = ["loser","loser_abbrev","pts_lose","yards_lose","to_lose"]
        home_loser = self.schedule.game_location == "@"
        self.schedule.loc[home_loser, list1] = self.schedule.loc[home_loser, loser_list].values
        self.schedule.loc[home_loser, list2] = self.schedule.loc[home_loser, winner_list].values
        away_loser = self.schedule.game_location.isnull() | self.schedule.game_location.isin(["N"])
        self.schedule.loc[away_loser, list1] = self.schedule.loc[away_loser, winner_list].values
        self.schedule.loc[away_loser, list2] = self.schedule.loc[away_loser, loser_list].values

    def mark_intl_games(self):
        intl = get_intl_games()
        intl = intl.loc[
            (intl.game_date.dt.year >= self.schedule.season.min())
            & (intl.game_date.dt.year <= self.schedule.season.max())
        ]
        intl["international"] = True
        self.schedule = pd.merge(
            left=self.schedule,
            right=intl,
            how="left",
            on=["game_date", "team1", "team2"],
        )
        self.schedule.international = self.schedule.international.fillna(False)
        self.schedule.loc[self.schedule.international, "game_location"] = "N"
        if self.schedule.international.sum() < intl.shape[0]:
            print("Missing some international games!!!")
            bad = pd.merge(
                left=intl,
                right=self.schedule[["boxscore_abbrev", "game_date", "team1", "team2"]],
                how="left",
                on=["game_date", "team1", "team2"],
            )
            bad = bad.loc[bad.boxscore_abbrev.isnull()]
            print(bad)

    def add_team_coords(self):
        teams = pd.concat(
            [
                self.schedule[["season", "team1_abbrev"]].rename(
                    columns={"team1_abbrev": "abbrev"}
                ),
                self.schedule[["season", "team2_abbrev"]].rename(
                    columns={"team2_abbrev": "abbrev"}
                ),
            ]
        ).drop_duplicates(ignore_index=True)
        zips = download_zip_codes()
        for ind in range(teams.shape[0]):
            team = teams.iloc[ind]
            stadium_id = get_team_stadium(team["abbrev"], team["season"])
            address = get_address(stadium_id)
            coords = get_coordinates(address, zips)
            self.schedule.loc[
                self.schedule.team1_abbrev == team["abbrev"], "coords1"
            ] = coords
            self.schedule.loc[
                self.schedule.team2_abbrev == team["abbrev"], "coords2"
            ] = coords

    def add_game_coords(self):
        neutral = self.schedule.game_location == "N"
        self.schedule.loc[~neutral, "game_coords"] = self.schedule.loc[
            ~neutral, "coords1"
        ]
        zips = download_zip_codes()
        for box in self.schedule.loc[neutral, "boxscore_abbrev"]:
            stadium_id = get_game_stadium(box)
            if stadium_id == "":
                stad_name = self.schedule.loc[self.schedule.boxscore_abbrev == box,"Stadium"].values[0]
                if stad_name == "Wembley Stadium":
                    stadium_id = "LON00"
                elif stad_name == "Tottenham Hotspur Stadium":
                    stadium_id = "LON02"
                elif stad_name == "Deutsche Bank Park":
                    stadium_id = "MUN01" # Not quite right, but close enough for now...
            address = get_address(stadium_id)
            coords = get_coordinates(address, zips)
            self.schedule.loc[
                self.schedule.boxscore_abbrev == box, "game_coords"
            ] = coords
        del self.schedule["Stadium"]
        self.schedule.game_coords = self.schedule.game_coords.str.split(",")

    def add_travel(self):
        for team in [1, 2]:
            self.schedule["coords" + str(team)] = self.schedule[
                "coords" + str(team)
            ].str.split(",")
            self.schedule["travel" + str(team)] = self.schedule.apply(
                lambda x: geodesic(x["coords" + str(team)], x["game_coords"]).mi, axis=1
            )

    def add_rest(self):
        for week in range(2, self.schedule.week.max() + 1):
            prev = (
                self.schedule.loc[self.schedule.week == week - 1, ["team1", "team2"]]
                .values.flatten()
                .tolist()
            )
            now = (
                self.schedule.loc[self.schedule.week == week, ["team1", "team2"]]
                .values.flatten()
                .tolist()
            )
            rested = [team for team in now if team not in prev]
            self.schedule.loc[
                (self.schedule.week == week) & self.schedule.team1.isin(rested),
                "rested1",
            ] = True
            self.schedule.loc[
                (self.schedule.week == week) & self.schedule.team2.isin(rested),
                "rested2",
            ] = True
        self.schedule.rested1 = self.schedule.rested1.fillna(False)
        self.schedule.rested2 = self.schedule.rested2.fillna(False)
    
    def add_elo_columns(self, qbelo: bool = False):
        self.schedule[['elo1_pre','elo2_pre','elo1_post','elo2_post','elo_diff',\
        'point_spread','elo_prob1','elo_prob2','score_diff','forecast_delta',\
        'mov_multiplier','elo_delta']] = None
        if qbelo:
            qb_elos = get_qb_elos(self.schedule.season.min(),self.schedule.season.max())
            for team_num in ['1','2']:
                self.schedule = pd.merge(left=self.schedule,right=qb_elos\
                .rename(columns={'game_id':'boxscore_abbrev','team':'team{}_abbrev'.format(team_num),\
                'player':'qb' + team_num,'team_qbvalue_avg':'team{}_qbvalue_avg'.format(team_num),\
                'opp_qbvalue_avg':'opp{}_qbvalue_avg'.format(team_num),\
                'qb_value_pre':'qb{}_value_pre'.format(team_num),'qb_adj':'qb{}_adj'.format(team_num),\
                'qb_value_post':'qb{}_value_post'.format(team_num),'VALUE':'VALUE{}'.format(team_num)}),\
                how='inner',on=['boxscore_abbrev','team{}_abbrev'.format(team_num)])
            # Need to pull depth charts to extrapolate future values...

    def next_init_elo(self, init_elo=1300, regress_pct=0.333):
        ind = self.schedule.loc[self.schedule.elo1_pre.isnull()].index[0]
        for team_num in ['1','2']:
            team = self.schedule.loc[ind,'team{}_abbrev'.format(team_num)]
            prev = self.schedule.iloc[:ind].copy()
            prev = prev.loc[(prev.team1_abbrev == team) | (prev.team2_abbrev == team)]
            if prev.shape[0] > 0:
                # Team already exists
                prev = prev.iloc[-1]
                prev_num = 1 if prev['team1_abbrev'] == team else 2
                if not pd.isnull(prev['elo{}_post'.format(prev_num)]):
                    self.schedule.loc[ind,'elo{}_pre'.format(team_num)] = prev['elo{}_post'.format(prev_num)]
                    if prev['season'] == self.schedule.loc[ind,'season'] - 1:
                        # Start of a new season
                        self.schedule.loc[ind,'elo{}_pre'.format(team_num)] += (1505 - prev['elo{}_post'.format(prev_num)])*regress_pct
                    elif prev['season'] < self.schedule.loc[ind,'season'] - 1:
                        # Resurrected teams (e.g. 1999 Cleveland Browns)
                        self.schedule.loc[ind,'elo{}_pre'.format(team_num)] = init_elo
                else:
                    # Game hasn't been played yet...
                    self.schedule.loc[ind,'elo{}_pre'.format(team_num)] = prev['elo{}_pre'.format(prev_num)]
            else:
                # New Team
                self.schedule.loc[ind,'elo{}_pre'.format(team_num)] = init_elo
            if 'qb{}_adj'.format(team_num) in self.schedule.columns:
                self.schedule.loc[ind,'qbelo{}_pre'.format(team_num)] = \
                self.schedule.loc[ind,'elo{}_pre'.format(team_num)] + \
                self.schedule.loc[ind,'qb{}_adj'.format(team_num)]
    
    def next_elo_prob(self, homefield=48, travel=0.004, rested=25, playoffs=1.2, elo2points=0.04):
        ind = self.schedule.loc[self.schedule.elo_prob1.isnull()].index[0]
        self.schedule.loc[ind,'elo_diff'] = self.schedule.loc[ind,'elo1_pre'] - self.schedule.loc[ind,'elo2_pre']
        self.schedule.loc[ind,'elo_diff'] += homefield # Homefield advantage
        self.schedule.loc[ind,'elo_diff'] += travel*(self.schedule.loc[ind,'travel2'] - self.schedule.loc[ind,'travel1']) # Travel
        if self.schedule.loc[ind,'rested1']:
            self.schedule.loc[ind,'elo_diff'] += rested # Bye week
        if self.schedule.loc[ind,'rested2']:
            self.schedule.loc[ind,'elo_diff'] -= rested # Bye week
        if not self.schedule.loc[ind,'week_num'].isnumeric():
            self.schedule.loc[ind,'elo_diff'] *= playoffs # Playoffs
        self.schedule.loc[ind,'point_spread'] = self.schedule.loc[ind,'elo_diff']*elo2points
        self.schedule.loc[ind,'elo_prob1'] = 1/(10**(self.schedule.loc[ind,'elo_diff']/-400) + 1)
        self.schedule.loc[ind,'elo_prob2'] = 1 - self.schedule.loc[ind,'elo_prob1']
        if 'qb1_adj' in self.schedule.columns and 'qb2_adj' in self.schedule.columns:
            self.schedule.loc[ind,'qbelo_diff'] = self.schedule.loc[ind,'elo_diff'] + \
            self.schedule.loc[ind,'qb1_adj'] - self.schedule.loc[ind,'qb2_adj']
            self.schedule.loc[ind,'qbpoint_spread'] = self.schedule.loc[ind,'qbelo_diff']*elo2points
            self.schedule.loc[ind,'qbelo_prob1'] = 1/(10**(self.schedule.loc[ind,'qbelo_diff']/-400) + 1)
            self.schedule.loc[ind,'qbelo_prob2'] = 1 - self.schedule.loc[ind,'qbelo_prob1']

    def next_elo_delta(self, k_factor=20):
        ind = self.schedule.loc[~self.schedule.elo_prob1.isnull() & self.schedule.elo_delta.isnull()].index[-1]
        if not pd.isnull(self.schedule.loc[ind,'score1']):
            self.schedule.loc[ind,'score_diff'] = self.schedule.loc[ind,'score1'] - self.schedule.loc[ind,'score2']
            self.schedule.loc[ind,'forecast_delta'] = float(self.schedule.loc[ind,'score_diff'] > 0) + \
            0.5*float(self.schedule.loc[ind,'score_diff'] == 0) - self.schedule.loc[ind,'elo_prob1']
            self.schedule.loc[ind,'mov_multiplier'] = np.log(abs(self.schedule.loc[ind,'score_diff']) + 1)*2.2/(self.schedule.loc[ind,'elo_diff']*0.001 + 2.2)
            if pd.isnull(self.schedule.loc[ind,'mov_multiplier']):
                self.schedule.loc[ind,'mov_multiplier'] = 0.0
            self.schedule.loc[ind,'elo_delta'] = self.schedule.loc[ind,'forecast_delta']*self.schedule.loc[ind,'mov_multiplier']*k_factor
            self.schedule.loc[ind,'elo1_post'] = self.schedule.loc[ind,'elo1_pre'] + self.schedule.loc[ind,'elo_delta']
            self.schedule.loc[ind,'elo2_post'] = self.schedule.loc[ind,'elo2_pre'] - self.schedule.loc[ind,'elo_delta']


class Boxscore:
    def __init__(self, game_id: str):
        self.game_id = game_id
        self.get_raw_text()
        self.get_details()
        self.get_stats()
        self.get_advanced_stats()
        self.get_starters()
        self.get_snap_counts()
        self.add_depth_chart()
        self.add_qb_value()
        self.normalize_team_names()

    def get_raw_text(self):
        self.raw_text = get_page("boxscores/{}.htm".format(self.game_id))

    def get_details(self):
        season_week = self.raw_text.find(
            "div", attrs={"class": "game_summaries compressed"}
        )
        season_week = season_week.find("a").attrs["href"]
        self.season = int(season_week.split("/")[-2])
        self.week = int(season_week.split("/")[-1].split("_")[-1].split(".")[0])
        home_scores = self.raw_text.find_all(
            ["th","td"], attrs={"data-stat": "home_team_score"}
        )
        self.team1_abbrev = home_scores[0].text
        self.team1_score = int(home_scores[-1].text)
        away_scores = self.raw_text.find_all(
            ["th","td"], attrs={"data-stat": "vis_team_score"}
        )
        self.team2_abbrev = away_scores[0].text
        self.team2_score = int(away_scores[-1].text)

    def get_stats(self):
        self.game_stats = pd.concat(
            [
                parse_table(self.raw_text, "player_offense"),
                parse_table(self.raw_text, "player_defense"),
                parse_table(self.raw_text, "kicking"),
            ]
        )
        if self.raw_text.find(id="returns"):
            self.game_stats = pd.concat(
                [self.game_stats, parse_table(self.raw_text, "returns")]
            )
        self.game_stats = (
            self.game_stats.fillna(0.0)
            .groupby(["player", "player_id", "team"])
            .sum()
            .reset_index()
        )
        self.game_stats.loc[
            self.game_stats.team == self.team1_abbrev, "opponent"
        ] = self.team2_abbrev
        self.game_stats.loc[
            self.game_stats.team == self.team2_abbrev, "opponent"
        ] = self.team1_abbrev

    def get_advanced_stats(self):
        if self.raw_text.find(id="passing_advanced"):
            advanced = pd.concat(
                [
                    parse_table(self.raw_text, "passing_advanced"),
                    parse_table(self.raw_text, "rushing_advanced"),
                    parse_table(self.raw_text, "receiving_advanced"),
                ]
            )
            advanced = advanced.fillna(0.0).groupby(["player", "player_id", "team"]).sum().reset_index()
        else:
            advanced = pd.DataFrame(columns=['player_id','pass_first_down','rush_first_down','rec_first_down'])
        self.game_stats = pd.merge(left=self.game_stats,right=advanced[['player_id',\
        'pass_first_down','rush_first_down','rec_first_down']],how='left',on='player_id')
        for col in ['pass_first_down','rush_first_down','rec_first_down']:
            self.game_stats[col] = self.game_stats[col].fillna(0.0)

    def get_starters(self):
        self.starters = pd.concat(
            [
                parse_table(self.raw_text, "home_starters"),
                parse_table(self.raw_text, "vis_starters"),
            ]
        )

    def get_snap_counts(self):
        # Games before 2012 don't have snapcounts and therefore no positions for non-starters...
        # Could merge position in via the get_names function...
        if self.raw_text.find(id="home_snap_counts") is not None \
        and self.raw_text.find(id="vis_snap_counts") is not None:
            self.snaps = pd.concat(
                [
                    parse_table(self.raw_text, "home_snap_counts"),
                    parse_table(self.raw_text, "vis_snap_counts"),
                ]
            )
        else:
            self.snaps = self.game_stats[["player", "player_id"]].copy()
            self.snaps[["off_pct","def_pct","st_pct"]] = 0.0

    def add_depth_chart(self):
        nonstarters = self.snaps.loc[
            ~self.snaps.player_id.isin(self.starters.player_id.tolist())
        ].sort_values(by=["off_pct", "def_pct", "st_pct"], ascending=False)
        depth_chart = pd.merge(
            left=pd.concat([self.starters.iloc[::-1], nonstarters]),
            right=self.game_stats[["player", "player_id", "team"]],
            how="inner",
            on=["player", "player_id"],
        )
        depth_chart["dummy"] = 1
        depth_chart["string"] = depth_chart.groupby(["team", "pos"]).dummy.rank(
            method="first"
        )
        self.game_stats = pd.merge(
            left=self.game_stats,
            right=depth_chart[["player", "player_id", "team", "pos", "string"]],
            how="inner",
            on=["player", "player_id", "team"],
        )
    
    def add_qb_value(self, pass_att=-2.2, pass_cmp=3.7, pass_yds=0.2, pass_td=11.3,\
    pass_int=-14.1, pass_sacked=-8.0, rush_att=-1.1, rush_yds=0.6, rush_td=15.9):
        qbs = self.game_stats.pos == 'QB'
        self.game_stats.loc[qbs,'VALUE'] = pass_att*self.game_stats.loc[qbs,'pass_att'] \
        + pass_cmp*self.game_stats.loc[qbs,'pass_cmp'] + pass_yds*self.game_stats.loc[qbs,'pass_yds'] \
        + pass_td*self.game_stats.loc[qbs,'pass_td'] + pass_int*self.game_stats.loc[qbs,'pass_int'] \
        + pass_sacked*self.game_stats.loc[qbs,'pass_sacked'] + rush_att*self.game_stats.loc[qbs,'rush_att'] \
        + rush_yds*self.game_stats.loc[qbs,'rush_yds'] + rush_td*self.game_stats.loc[qbs,'rush_td']

    def normalize_team_names(self):
        abbrevs = {'OAK':'RAI','LVR':'RAI','LAC':'SDG','STL':'RAM','LAR':'RAM',\
        'ARI':'CRD','IND':'CLT','BAL':'RAV','HOU':'HTX','TEN':'OTI'}
        for team in abbrevs:
            for val in ['team','opponent']:
                self.game_stats.loc[self.game_stats[val] == team,val] = abbrevs[team]
        if self.team1_abbrev in abbrevs:
            self.team1_abbrev = abbrevs[self.team1_abbrev]
        if self.team2_abbrev in abbrevs:
            self.team2_abbrev = abbrevs[self.team2_abbrev]


def get_bulk_stats(
    start_season: int,
    start_week: int,
    finish_season: int,
    finish_week: int,
    playoffs: bool = True,
    path: str = None,
):
    """
    Pulls individual player statistics for each game in the specified timeframe from Pro Football Reference.

    Args:
        start_season (int): first season of interest.
        start_week (int): first week of interest.
        finish_season (int): last season of interest.
        finish_week (int): last week of interest.
        playoffs (bool, optional): whether to include playoff games, defaults to True.
        path(str, optional): file path where stats are/should be saved to, defaults to None.

    Returns:
        pd.DataFrame: dataframe containing player statistics for games during the timespan of interest.
    """
    s = Schedule(start_season, finish_season, playoffs)
    s.schedule = s.schedule.loc[
        (s.schedule.season * 100 + s.schedule.week >= start_season * 100 + start_week)
        & (
            s.schedule.season * 100 + s.schedule.week
            <= finish_season * 100 + finish_week
        )
        & ~s.schedule.score1.isnull()
        & ~s.schedule.score2.isnull()
    ].reset_index(drop=True)
    if path is not None and os.path.exists(str(path)):
        stats = pd.read_csv(path)
    else:
        stats = pd.DataFrame(columns=["season", "week", "game_id"])
    to_save = path is not None and (~s.schedule.boxscore_abbrev.isin(stats.game_id.unique())).any()
    for ind in range(s.schedule.shape[0]):
        if s.schedule.iloc[ind]["boxscore_abbrev"] not in stats.game_id.unique():
            print(s.schedule.iloc[ind]["boxscore_abbrev"])
            b = Boxscore(s.schedule.iloc[ind]["boxscore_abbrev"])
            stats = pd.concat([stats, b.game_stats], ignore_index=True)
            stats.season = stats.season.fillna(b.season)
            stats.week = stats.week.fillna(b.week)
            stats.game_id = stats.game_id.fillna(b.game_id)
            if to_save and b.season not in s.schedule.iloc[ind + 1:].season.unique():
                stats.to_csv(path,index=False)
    if to_save:
        stats.to_csv(path,index=False)
    stats = stats.loc[stats.game_id.isin(s.schedule.boxscore_abbrev.tolist())].reset_index(drop=True)
    return stats


def get_draft(season: int):
    raw_text = get_page("years/{}/draft.htm".format(season))
    draft_order = parse_table(raw_text, "drafts")
    return draft_order


def get_bulk_draft_pos(start_season: int, finish_season: int, path: str = None, \
best_qb_val: float = 34.313, qb_val_per_pick: float = -0.137):
    start_season = int(start_season)
    finish_season = int(finish_season)
    if path and os.path.exists(str(path)):
        draft_pos = pd.read_csv(path)
    else:
        draft_pos = pd.DataFrame(columns=['year'])
    new_drafts = any([year not in draft_pos.year.unique() for year in range(start_season,finish_season + 1)])
    for year in range(start_season,finish_season + 1):
        if year not in draft_pos.year.unique():
            draft_pos = pd.concat([draft_pos,get_draft(year)],ignore_index=True)
            draft_pos.year = draft_pos.year.fillna(year)
    if path and new_drafts:
        draft_pos.to_csv(path,index=False)
    draft_pos = draft_pos.loc[draft_pos.year.isin(list(range(start_season,finish_season + 1)))].reset_index(drop=True)
    qbs = draft_pos.pos == 'QB'
    draft_pos.loc[qbs,'qb_value_init'] = draft_pos.loc[qbs,'draft_pick']*qb_val_per_pick + best_qb_val
    return draft_pos


def get_roster(team: str, season: int):
    raw_text = get_page("teams/{}/{}_roster.htm".format(team.lower(),season))
    roster = parse_table(raw_text, "roster")
    return roster


def get_bulk_rosters(start_season: int, finish_season: int, path: str = None):
    s = Schedule(start_season,finish_season)
    # Need to delete and repull after every new week to account for trades, etc.
    if path and os.path.exists(str(path)):
        teams = pd.read_csv(path)
    else:
        teams = pd.DataFrame(columns=["season"])
    new_games = any([season not in teams.season.unique() for season in range(start_season,finish_season + 1)])
    for season in range(start_season,finish_season + 1):
        if season not in teams.season.unique():
            for team in s.schedule.loc[s.schedule.season == season,'team1_abbrev'].unique():
                roster = get_roster(team,season)
                roster['team'] = team
                roster['season'] = season
                teams = pd.concat([teams,roster],ignore_index=True)
    if path and (new_games or finish_season == datetime.datetime.now().year):
        teams.to_csv(path,index=False)
    teams.player = teams.player.str.split(' (',regex=False).str[0]
    return teams


def get_qb_elos(start, finish, regress_pct=0.25, qb_games=10, team_games=20, elo_adj=3.3):
    stats = get_bulk_stats(start - 3,1,finish,50,True,"GameByGameFantasyFootballStats.csv")
    if finish == datetime.datetime.now().year and datetime.datetime.now().month > 5:
        # Accounting for current season
        sched = Schedule(finish,finish).schedule.copy()
        missing = pd.concat([sched.loc[sched.score1.isnull() & sched.score2.isnull(),\
        ['season','week_num','boxscore_abbrev','team1_abbrev','team2_abbrev']]\
        .rename(columns={'week_num':'week','boxscore_abbrev':'game_id','team1_abbrev':'team','team2_abbrev':'opponent'}),\
        sched.loc[sched.score1.isnull() & sched.score2.isnull(),['season','week_num','boxscore_abbrev','team2_abbrev','team1_abbrev']]\
        .rename(columns={'week_num':'week','boxscore_abbrev':'game_id','team2_abbrev':'team','team1_abbrev':'opponent'})],ignore_index=True)
        current = get_all_depth_charts()
        current = current.loc[(current.pos == 'QB') & (current.string == 1.0)]
        missing = pd.merge(left=missing,right=current,how='inner',on='team')
        stats = pd.concat([stats,missing],ignore_index=True)
    draft_pos = get_bulk_draft_pos(start - 10,finish,"NFLDraftPositions.csv")
    prev_all = stats.loc[(stats.season < stats.season.min() + 2) & \
    (stats.pos == 'QB') & (stats.string == 1)].reset_index(drop=True)
    by_opponent = prev_all.groupby(['season','week','game_id','opponent']).VALUE.sum().reset_index()
    by_opponent = by_opponent.sort_values(by=['season','week'],ascending=False).reset_index(drop=True)
    by_opponent = by_opponent.groupby('opponent').head(team_games).groupby('opponent').VALUE.mean().reset_index()
    by_team = prev_all.groupby(['season','week','game_id','team']).VALUE.sum().reset_index()
    by_team = by_team.sort_values(by=['season','week'],ascending=False).reset_index(drop=True)
    by_team = by_team.groupby('team').head(team_games).groupby('team').VALUE.mean().reset_index()
    new = stats.loc[(stats.season >= stats.season.min() + 2) & \
    (stats.pos == 'QB') & (stats.string == 1)].reset_index(drop=True)
    new['qb_value_pre'] = None
    for ind in range(new.shape[0]):
        avg_value = by_opponent.VALUE.mean()
        prev_qb = new.loc[(new.player == new.loc[ind,'player']) & (new.index < ind)]
        if prev_qb.shape[0] == 0:
            drafted = draft_pos.loc[draft_pos.player == new.loc[ind,'player']]
            if drafted.shape[0] > 0:
                new.loc[ind,'qb_value_pre'] = drafted.iloc[0].qb_value_init
            else:
                new.loc[ind,'qb_value_pre'] = 0.0
            new.loc[ind,'num_games'] = 0.0
        else:
            new.loc[ind,'qb_value_pre'] = prev_qb.iloc[-1]['qb_value_post']
            if new.loc[ind,'season'] > prev_qb.iloc[-1]['season'] and prev_qb.shape[0] >= 10 and prev_qb.shape[0] <= 100:
                new.loc[ind,'qb_value_pre'] = (1 - regress_pct)*new.loc[ind,'qb_value_pre'] + regress_pct*avg_value
            new.loc[ind,'num_games'] = prev_qb.shape[0]
        if pd.isnull(new.loc[ind,'VALUE']):
            # Game hasn't been played yet
            new.loc[ind,'qb_value_post'] = new.loc[ind,'qb_value_pre']
            new.loc[ind,'team_qbvalue_avg'] = by_team.loc[by_team.team == new.loc[ind,'team'],'VALUE'].values[0]
        else:
            new.loc[ind,'team_qbvalue_avg'] = by_team.loc[by_team.team == new.loc[ind,'team'],'VALUE'].values[0]
            new.loc[ind,'opp_qbvalue_avg'] = by_opponent.loc[by_opponent.opponent == new.loc[ind,'opponent'],'VALUE'].values[0] - avg_value
            new.loc[ind,'VALUE'] -= new.loc[ind,'opp_qbvalue_avg']
            new.loc[ind,'qb_value_post'] = new.loc[ind,'qb_value_pre']*(1 - 1/qb_games) + new.loc[ind,'VALUE']/qb_games
            by_opponent.loc[by_opponent.opponent == new.loc[ind,'opponent'],'VALUE'] *= (1 - 1/team_games)
            by_opponent.loc[by_opponent.opponent == new.loc[ind,'opponent'],'VALUE'] += new.loc[ind,'VALUE']/team_games
            by_team.loc[by_team.team == new.loc[ind,'team'],'VALUE'] *= (1 - 1/team_games)
            by_team.loc[by_team.team == new.loc[ind,'team'],'VALUE'] += new.loc[ind,'VALUE']/team_games
    new['qb_adj'] = elo_adj*(new.qb_value_pre - new.team_qbvalue_avg)
    return new[['game_id','player','team','team_qbvalue_avg',\
    'opp_qbvalue_avg','qb_value_pre','qb_adj','qb_value_post','VALUE']]


def get_names():
    """
    Pulls the player id and name for every player on Pro Football Reference for conversion purposes.

    Returns:
        pd.DataFrame: dataframe containing name, position,
        player id, and timespan of every player in the database.
    """
    names = pd.DataFrame()
    for letter in range(65, 91):
        raw_text = get_page("players/" + chr(letter))
        players = raw_text.find(id="div_players").find_all("p")
        for player in players:
            entry = {
                "name": player.find("a").text,
                "position": player.text.split("(")[-1].split(")")[0],
                "player_id": player.find("a")
                .attrs["href"]
                .split("/")[-1]
                .split(".")[0],
                "years_active": player.text.split(") ")[-1],
            }
            names = pd.concat([names, pd.DataFrame(entry, index=[names.shape[0]])])
    return names
