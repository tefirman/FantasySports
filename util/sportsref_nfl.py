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
import sys
import pandas as pd
from geopy.distance import geodesic
from geopy.geocoders import Nominatim
geocoder = Nominatim(user_agent='fff')
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
    response = requests.get(base_url + endpoint).text
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
                new_col = col.split('_')[0] + '_abbrev'
                entry[new_col] = entry[col].find("a").attrs["href"]
                entry[new_col] = entry[new_col].split("/")[-1].split(".")[0]
            elif col == "player":
                entry["player_id"] = entry[col].attrs["data-append-csv"]
            elif col in ["winner", "loser"]:
                entry[col + "_abbrev"] = entry[col].find("a").attrs["href"].split("/")[-2].upper()
            if col != "boxscore_word":
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
    response = requests.get("https://en.wikipedia.org/wiki/NFL_International_Series").text
    soup = BeautifulSoup(response, "html.parser")
    tables = soup.find_all('table',attrs={'class':'wikitable sortable'})[1:-1]
    intl_games = pd.concat(pd.read_html(str(tables)),ignore_index=True)
    intl_games.Year = intl_games.Year.astype(str).str.split(' ').str[0].astype(int)
    intl_games['team1'] = intl_games['Designated home team'].str.split('\[').str[0]
    intl_games['team2'] = intl_games['Designated visitor'].str.split('\[').str[0]
    intl_games = intl_games.loc[~intl_games.Attendance.astype(str).str.contains('\[')].reset_index(drop=True)
    intl_games['game_date'] = pd.to_datetime(intl_games.Date + ', ' + intl_games.Year.astype(str),infer_datetime_format=True)
    return intl_games[['game_date','team1','team2']]


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
    raw_text = get_page("teams/{}/{}.htm".format(abbrev.lower(),int(season)))
    team_info = raw_text.find(id="meta").find_all('p')
    stadium_info = [val for val in team_info if val.text.startswith("Stadium:")]#[0]
    if len(stadium_info) == 0:
        stadiums = get_stadiums()
        stadiums.teams = stadiums.teams.str.split(', ')
        stadiums = stadiums.explode('teams',ignore_index=True)
        name = raw_text.find('div',attrs={"data-template":"Partials/Teams/Summary"}).find_all('span')[1].text
        stadium_id = stadiums.loc[(stadiums.teams == name) & (stadiums.year_min <= season) & \
                                  (stadiums.year_max >= season),'stadium_abbrev'].values[0]
    else:
        stadium_info = stadium_info[0]
        stadium_id = stadium_info.find("a").attrs['href'].split('/')[-1].split('.')[0]
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
    game_info = raw_text.find("div",attrs={"class":"scorebox_meta"})
    stadium_id = game_info.find("a").attrs['href'].split('/')[-1].split('.')[0]
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
    address = raw_text.find(id='meta').find('p').text
    fixes = {'New Jersey':'NJ','Park Houston':'Park, Houston','Blvd Opa-Locka':'Blvd, Opa-Locka',\
             "Northumberland Development Project":"782 High Rd, London N17 0BX, UK"}
    for fix in fixes:
        address = address.replace(fix,fixes[fix])
    return address


def try_geocoder(address: str, pause: int = 30, max_tries: int = 10):
    """
    Tries to pull address coordinates using geocoder while accounting for possible server crapouts.

    Args:
        address (str): physical address of interest.
        pause (int, optional): number of seconds to wait between each try, defaults to 30.
        max_tries (int, optional): maximum number of times to try, defaults to 10.

    Returns:
        geopy.location.Location: geopy object containing details about the location of interest.
    """
    num_tries = 0
    while num_tries < max_tries:
        try:
            location = geocoder.geocode(address)
            break
        except:
            num_tries += 1
            if num_tries < max_tries:
                print("Geocoder crapped out... Waiting {} seconds and trying again...".format(pause))
                time.sleep(pause)
            else:
                print("Geocoder is consistently crapping out... Returning None for now...")
                location = None
    return location


def get_coordinates(address: str):
    """
    Provides the coordinates of the specified address. If no exact coordinates are available, 
    city, state, and zip code are used for an approximate position.

    Args:
        address (str): physical address of interest.

    Returns:
        str: latitudinal and longitudinal coordinates separated by a comma.
    """
    location = try_geocoder(address)
    if location:
        coords = str(location.latitude) + ',' + str(location.longitude)
    else:
        print("Can't find location for: " + address)
        print("Using city, state, and zip...")
        address = ', '.join(address.split(', ')[-2:])
        location = try_geocoder(address)
        if location:
            coords = str(location.latitude) + ',' + str(location.longitude)
        else:
            print("Still can't find location for: " + address)
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

    def __init__(self, start: int, finish: int, playoffs: bool = True):
        """
        Initializes a Schedule object using the parameters provided and class functions defined below.

        Args:
            start (int): first NFL season of interest
            finish (int): last NFL season of interest
            playoffs (bool, optional): whether to include playoff games, defaults to True.
        """
        self.get_schedules(start, finish, playoffs)
        self.add_weeks()
        self.convert_to_home_away()
        self.mark_intl_games()
        self.add_team_coords()
        self.add_game_coords()
        self.add_travel()
        self.add_rest()

    def get_schedules(self, start: int, finish: int, playoffs: bool = True):
        self.schedule = pd.DataFrame(columns=['season'])
        for season in range(start,finish + 1):
            raw_text = get_page("years/{}/games.htm".format(season))
            self.schedule = pd.concat([self.schedule,parse_table(raw_text, "games")],ignore_index=True)
            self.schedule.season = self.schedule.season.fillna(season)
        if not playoffs:
            self.schedule = self.schedule.loc[self.schedule.week_num.str.isnumeric()].reset_index(drop=True)

    def add_weeks(self):
        self.schedule.game_date = pd.to_datetime(self.schedule.game_date,infer_datetime_format=True)
        min_date = self.schedule.groupby('season').game_date.min().reset_index()
        self.schedule = pd.merge(left=self.schedule,right=min_date,how='inner',on='season',suffixes=('','_min'))
        self.schedule['days_into_season'] = (self.schedule.game_date - self.schedule.game_date_min).dt.days
        self.schedule['week'] = self.schedule.days_into_season//7 + 1

    def convert_to_home_away(self):
        home_loser = self.schedule.game_location == '@'
        self.schedule.loc[home_loser,'team1'] = self.schedule.loc[home_loser,'loser']
        self.schedule.loc[home_loser,'team1_abbrev'] = self.schedule.loc[home_loser,'loser_abbrev']
        self.schedule.loc[home_loser,'score1'] = self.schedule.loc[home_loser,'pts_lose']
        self.schedule.loc[home_loser,'yards1'] = self.schedule.loc[home_loser,'yards_lose']
        self.schedule.loc[home_loser,'timeouts1'] = self.schedule.loc[home_loser,'to_lose']
        self.schedule.loc[home_loser,'team2'] = self.schedule.loc[home_loser,'winner']
        self.schedule.loc[home_loser,'team2_abbrev'] = self.schedule.loc[home_loser,'winner_abbrev']
        self.schedule.loc[home_loser,'score2'] = self.schedule.loc[home_loser,'pts_win']
        self.schedule.loc[home_loser,'yards2'] = self.schedule.loc[home_loser,'yards_win']
        self.schedule.loc[home_loser,'timeouts2'] = self.schedule.loc[home_loser,'to_win']
        away_loser = self.schedule.game_location.isnull() | (self.schedule.game_location == 'N')
        self.schedule.loc[away_loser,'team1'] = self.schedule.loc[away_loser,'winner']
        self.schedule.loc[away_loser,'team1_abbrev'] = self.schedule.loc[away_loser,'winner_abbrev']
        self.schedule.loc[away_loser,'score1'] = self.schedule.loc[away_loser,'pts_win']
        self.schedule.loc[away_loser,'yards1'] = self.schedule.loc[away_loser,'yards_win']
        self.schedule.loc[away_loser,'timeouts1'] = self.schedule.loc[away_loser,'to_win']
        self.schedule.loc[away_loser,'team2'] = self.schedule.loc[away_loser,'loser']
        self.schedule.loc[away_loser,'team2_abbrev'] = self.schedule.loc[away_loser,'loser_abbrev']
        self.schedule.loc[away_loser,'score2'] = self.schedule.loc[away_loser,'pts_lose']
        self.schedule.loc[away_loser,'yards2'] = self.schedule.loc[away_loser,'yards_lose']
        self.schedule.loc[away_loser,'timeouts2'] = self.schedule.loc[away_loser,'to_lose']

    def mark_intl_games(self):
        intl = get_intl_games()
        intl = intl.loc[(intl.game_date.dt.year >= self.schedule.season.min()) & (intl.game_date.dt.year <= self.schedule.season.max())]
        intl['international'] = True
        self.schedule = pd.merge(left=self.schedule,right=intl,how='left',on=['game_date','team1','team2'])
        self.schedule.international = self.schedule.international.fillna(False)
        self.schedule.loc[self.schedule.international,'game_location'] = "N"
        if self.schedule.international.sum() < intl.shape[0]:
            print('Missing some international games!!!')
            bad = pd.merge(left=intl,right=self.schedule[['boxscore_abbrev','game_date','team1','team2']],how='left',on=['game_date','team1','team2'])
            bad = bad.loc[bad.boxscore_abbrev.isnull()]
            print(bad)

    def add_team_coords(self):
        teams = pd.concat([self.schedule[['season','team1_abbrev']].rename(columns={'team1_abbrev':'abbrev'}),\
        self.schedule[['season','team2_abbrev']].rename(columns={'team2_abbrev':'abbrev'})]).drop_duplicates(ignore_index=True)
        for ind in range(teams.shape[0]):
            team = teams.iloc[ind]
            stadium_id = get_team_stadium(team['abbrev'],team['season'])
            address = get_address(stadium_id)
            coords = get_coordinates(address)
            self.schedule.loc[self.schedule.team1_abbrev == team['abbrev'],'coords1'] = coords
            self.schedule.loc[self.schedule.team2_abbrev == team['abbrev'],'coords2'] = coords

    def add_game_coords(self):
        neutral = self.schedule.game_location == 'N'
        self.schedule.loc[~neutral,'game_coords'] = self.schedule.loc[~neutral,'coords1']
        for box in self.schedule.loc[neutral,'boxscore_abbrev']:
            stadium_id = get_game_stadium(box)
            address = get_address(stadium_id)
            coords = get_coordinates(address)
            self.schedule.loc[self.schedule.boxscore_abbrev == box,'game_coords'] = coords
        self.schedule.game_coords = self.schedule.game_coords.str.split(',')
    
    def add_travel(self):
        for team in [1,2]:
            self.schedule['coords' + str(team)] = self.schedule['coords' + str(team)].str.split(',')
            self.schedule['travel' + str(team)] = self.schedule.apply(lambda x: geodesic(x['coords' + str(team)],x['game_coords']).mi,axis=1)
    
    def add_rest(self):
        for week in range(2,self.schedule.week.max() + 1):
            prev = self.schedule.loc[self.schedule.week == week - 1,['team1','team2']].values.flatten().tolist()
            now = self.schedule.loc[self.schedule.week == week,['team1','team2']].values.flatten().tolist()
            rested = [team for team in now if team not in prev]
            self.schedule.loc[(self.schedule.week == week) & self.schedule.team1.isin(rested),'rested1'] = True
            self.schedule.loc[(self.schedule.week == week) & self.schedule.team2.isin(rested),'rested2'] = True
        self.schedule.rested1 = self.schedule.rested1.fillna(False)
        self.schedule.rested2 = self.schedule.rested2.fillna(False)


class Boxscore:
    def __init__(self, game_id: str):
        self.game_id = game_id
        self.get_raw_text()
        self.get_details()
        self.get_stats()
        self.get_starters()
        self.get_snap_counts()
        self.add_depth_chart()

    def get_raw_text(self):
        self.raw_text = get_page("boxscores/{}.htm".format(self.game_id))
    
    def get_details(self):
        season_week = self.raw_text.find("div", attrs={"class": "game_summaries compressed"})
        season_week = season_week.find("a").attrs["href"]
        self.season = int(season_week.split("/")[-2])
        self.week = int(season_week.split("/")[-1].split("_")[-1].split(".")[0])
        self.team1_abbrev = self.raw_text.find("th", attrs={"data-stat":"home_team_score"}).text
        self.team2_abbrev = self.raw_text.find("th", attrs={"data-stat":"vis_team_score"}).text
    
    def get_stats(self):
        self.game_stats = pd.concat(
            [
                parse_table(self.raw_text, "player_offense"),
                parse_table(self.raw_text, "player_defense"),
                parse_table(self.raw_text, "returns"),
                parse_table(self.raw_text, "kicking"),
            ]
        )
        self.game_stats = (
            self.game_stats.fillna(0.0)
            .groupby(["player", "player_id", "team"])
            .sum()
            .reset_index()
        )
        self.game_stats.loc[self.game_stats.team == self.team1_abbrev,'opponent'] = self.team2_abbrev
        self.game_stats.loc[self.game_stats.team == self.team2_abbrev,'opponent'] = self.team1_abbrev
    
    def get_starters(self):
        self.starters = pd.concat(
            [parse_table(self.raw_text, "home_starters"), parse_table(self.raw_text, "vis_starters")]
        )
    
    def get_snap_counts(self):
        self.snaps = pd.concat(
            [
                parse_table(self.raw_text, "home_snap_counts"),
                parse_table(self.raw_text, "vis_snap_counts"),
            ]
        )
    
    def add_depth_chart(self):
        nonstarters = (
            self.snaps.loc[~self.snaps.player_id.isin(self.starters.player_id.tolist())]
            .sort_values(by=["off_pct", "def_pct", "st_pct"], ascending=False)
        )
        depth_chart = pd.merge(
            left=pd.concat([self.starters.iloc[::-1], nonstarters]),
            right=self.game_stats[["player", "player_id", "team"]],
            how="inner",
            on=["player", "player_id"],
        )
        depth_chart["dummy"] = 1
        depth_chart["string"] = depth_chart.groupby(["team", "pos"]).dummy.rank(method="first")
        self.game_stats = pd.merge(
            left=self.game_stats,
            right=depth_chart[["player", "player_id", "team", "pos", "string"]],
            how="inner",
            on=["player", "player_id", "team"],
        )


def get_bulk_stats(start_season: int, start_week: int, finish_season: int, finish_week: int, playoffs: bool = True):
    """
    Pulls individual player statistics for each game in the specified timeframe from Pro Football Reference.

    Args:
        start_season (int): first season of interest.
        start_week (int): first week of interest.
        finish_season (int): last season of interest.
        finish_week (int): last week of interest.
        playoffs (bool, optional): whether to include playoff games, defaults to True.

    Returns:
        pd.DataFrame: dataframe containing player statistics for games during the timespan of interest.
    """
    s = Schedule(start_season, finish_season, playoffs)
    s.schedule = s.schedule.loc[(s.schedule.season*100 + s.schedule.week >= start_season*100 + start_week) & \
    (s.schedule.season*100 + s.schedule.week <= finish_season*100 + finish_week)].reset_index(drop=True)
    stats = pd.DataFrame(columns=['season','week','game_id'])
    for ind in range(s.schedule.shape[0]):
        print(s.schedule.iloc[ind]["boxscore_abbrev"])
        b = Boxscore(s.schedule.iloc[ind]["boxscore_abbrev"])
        stats = pd.concat([stats, b.game_stats],ignore_index=True)
        stats.season = stats.season.fillna(b.season)
        stats.week = stats.week.fillna(b.week)
        stats.game_id = stats.game_id.fillna(b.game_id)
    return stats


def get_draft(season: int):
    raw_text = get_page("years/{}/draft.htm".format(season))
    draft_order = parse_table(raw_text, "drafts")
    return draft_order


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
    names.loc[names.name == "Logan Thomas", "position"] = "TE"
    names.loc[names.name == "Cordarrelle Patterson", "position"] = "RB"
    return names
