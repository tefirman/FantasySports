#!/usr/bin/env python
# -*-coding:utf-8 -*-
"""
@File    :   sportsref_mlb.py
@Time    :   2023/04/12 21:49:12
@Author  :   Taylor Firman
@Version :   1.0
@Contact :   tefirman@gmail.com
@Desc    :   Collection of functions to easily pull down statistics from baseball-reference.com
"""

import requests
from bs4 import BeautifulSoup
import time
import pandas as pd

base_url = "https://www.baseball-reference.com/"


def get_page(endpoint: str):
    """
    Pulls down the raw html for the specified endpoint of Baseball Reference
    and adds an additional four second delay to avoid triggering the 1hr jailtime
    for exceeding 20 requests per minute.

    Args:
        endpoint (str): relative location of the page to pull down.

    Returns:
        str: raw html of the specified endpoint.
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
            if col == "boxscore_word":
                entry[col] = entry[col].find("a").attrs["href"]
                entry[col] = entry[col].split("/")[-1].split(".")[0]
            else:
                if col == "player" and "data-append-csv" in entry[col].attrs:
                    entry["player_id"] = entry[col].attrs["data-append-csv"]
                entry[col] = entry[col].text
        stats = pd.concat([stats, pd.DataFrame(entry, index=[stats.shape[0]])])
    stats = stats.replace("", None).reset_index(drop=True)
    for col in stats.columns:
        if col.endswith("_pct") or col in ["wpa_bat_neg","cwpa_bat"]:
            stats[col] = stats[col].str.replace("%", "")
        stats[col] = stats[col].astype(float, errors="ignore")
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
    raw_text = get_page("leagues/majors/{}-schedule.shtml".format(season))
    season_id = (
        raw_text.find(attrs={"data-label": "MLB Schedule"}).attrs["id"].split("_")[0]
    )
    games = raw_text.find(id="div_" + season_id).find_all("p", attrs={"class": "game"})
    schedule = pd.DataFrame()
    for game in games:
        links = game.find_all("a")
        entry = {
            "away_team": links[0].text,
            "away_abbrev": links[0].attrs["href"].split("/")[2],
            "home_team": links[1].text,
            "home_abbrev": links[1].attrs["href"].split("/")[2],
            "boxscore_word": links[2].attrs["href"].split("/")[-1].split(".")[0],
        }
        if " (" in game.text:
            entry["away_score"] = int(game.text.split(" (")[1].split(")")[0])
            entry["home_score"] = int(game.text.split(" (")[2].split(")")[0])
        schedule = pd.concat([schedule, pd.DataFrame(entry, index=[schedule.shape[0]])])
    if playoffs:
        season_id = (
            raw_text.find(attrs={"data-label": "Postseason Schedule"})
            .attrs["id"]
            .split("_")[0]
        )
        games = raw_text.find(id="div_" + season_id).find_all(
            "p", attrs={"class": "game"}
        )
        for game in games:
            links = game.find_all("a")
            entry = {
                "away_team": links[0].text,
                "away_abbrev": links[0].attrs["href"].split("/")[2],
                "home_team": links[1].text,
                "home_abbrev": links[1].attrs["href"].split("/")[2],
                "boxscore_word": links[2].attrs["href"].split("/")[-1].split(".")[0],
            }
            if " (" in game.text:
                entry["away_score"] = int(game.text.split(" (")[1].split(")")[0])
                entry["home_score"] = int(game.text.split(" (")[2].split(")")[0])
            schedule = pd.concat(
                [schedule, pd.DataFrame(entry, index=[schedule.shape[0]])]
            )
    schedule["date"] = pd.to_datetime(schedule.boxscore_word.str[3:-1], format="%Y%m%d")
    return schedule


def get_boxscore(game_id: str):
    """
    Pulls down the per-player statistics from the boxscore of the specified game.

    Args:
        game_id (str): SportsReference identifier string for the game in question (e.g. SEA199510080).

    Returns:
        pd.DataFrame: dataframe containing the per-player batting stats from the specified game.
        pd.DataFrame: dataframe containing the per-player pitching stats from the specified game.

    """
    raw_text = get_page("boxes/{}/{}.shtml".format(game_id[:3], game_id))
    description = raw_text.find("meta", attrs={"property": "og:title"}).attrs["content"]
    if " Box Score: " not in description:
        print("Unclear if game actually exists... Returning empty dataframe...")
        return pd.DataFrame(), pd.DataFrame()
    away = description.split(" vs ")[0]
    home = description.split(" vs ")[-1].split(" Box Score: ")[0]
    date = pd.to_datetime(
        description.split(" Box Score: ")[-1].split(" | ")[0],
        infer_datetime_format=True,
    )
    batting = pd.concat(
        [
            parse_table(raw_text, away.replace(" ", "").replace(".", "") + "batting"),
            parse_table(raw_text, home.replace(" ", "").replace(".", "") + "batting"),
        ]
    )
    batting = batting.loc[
        ~batting.player.str.endswith(" P") & ~batting.player.isin(["Team Totals"])
    ]
    batting.details = batting.details.fillna("")
    deets = batting.loc[~batting.details.isnull(), ["player_id", "details"]].copy()
    deets.details = deets.details.str.split(",")
    deets = deets.explode("details")
    for stat in ["2B", "3B", "HR", "HBP", "SB"]:
        deets[stat] = float("NaN")
        deets.loc[deets.details.isin([stat]), stat] = 1
        for num in range(2, 10):
            deets.loc[deets.details.isin([str(num) + "-" + stat]), stat] = num
    deets = deets.fillna(0.0).groupby("player_id").sum(numeric_only=True).reset_index()
    batting = pd.merge(left=batting, right=deets, how="left", on="player_id")
    batting = batting.fillna(0.0)
    batting.player = batting.player.str.split(" ").str[:-1].apply(" ".join).str.strip()
    batting["date"] = date
    batting["game_id"] = game_id
    pitching = pd.concat(
        [
            parse_table(raw_text, away.replace(" ", "").replace(".", "") + "pitching"),
            parse_table(raw_text, home.replace(" ", "").replace(".", "") + "pitching"),
        ]
    )
    pitching = pitching.loc[~pitching.player.isin(["Team Totals"])]
    pitching.loc[
        pitching.player.str.contains(pat=", W \(\d{1,2}-\d{1,2}\)", regex=True), "W"
    ] = 1.0
    pitching.loc[
        pitching.player.str.contains(pat=", L \(\d{1,2}-\d{1,2}\)", regex=True), "L"
    ] = 1.0
    pitching.loc[
        pitching.player.str.contains(pat=", H \(\d{1,2}\)", regex=True), "HD"
    ] = 1.0
    pitching.loc[
        pitching.player.str.contains(pat=", S \(\d{1,2}\)", regex=True), "SV"
    ] = 1.0
    for stat in ["W", "L", "HD", "SV"]:
        if stat not in pitching.columns:
            pitching[stat] = float("NaN")
    pitching = pitching.fillna(0.0)
    pitching.player = pitching.player.str.split(", ").str[0]
    pitching["date"] = date
    pitching["game_id"] = game_id
    return batting, pitching


def get_games(start: str, finish: str):
    """
    Pulls individual player statistics for each game in the specified timeframe from Pro Football Reference.

    Args:
        start (str): date of the first game of interest (e.g. "April 1, 2020").
        finish (str): date of the last game of interest (e.g. "August 1, 2022").

    Returns:
        pd.DataFrame: dataframe containing player batting statistics for games during the timespan of interest.
        pd.DataFrame: dataframe containing player pitching statistics for games during the timespan of interest.
    """
    start = pd.to_datetime(start, infer_datetime_format=True)
    finish = pd.to_datetime(finish, infer_datetime_format=True)
    batting_stats = pd.DataFrame()
    pitching_stats = pd.DataFrame()
    for season in range(start.year, finish.year + 1):
        print(season)
        season_sched = get_schedule(season)
        if season == start.year:
            season_sched = season_sched.loc[season_sched.date >= start].reset_index(
                drop=True
            )
        if season == finish.year:
            season_sched = season_sched.loc[season_sched.date <= finish].reset_index(
                drop=True
            )
        for ind in range(season_sched.shape[0]):
            print(season_sched.loc[ind, "boxscore_word"])
            batting, pitching = get_boxscore(season_sched.loc[ind, "boxscore_word"])
            batting_stats = pd.concat([batting_stats, batting])
            pitching_stats = pd.concat([pitching_stats, pitching])
    return batting_stats, pitching_stats


def get_names():
    """
    Pulls the player id and name for every player on Baseball Reference for conversion purposes.

    Returns:
        pd.DataFrame: dataframe containing name, player id,
        and timespan of every player in the database.
    """
    names = pd.DataFrame()
    for letter in range(97, 123):
        raw_text = get_page("players/" + chr(letter))
        players = raw_text.find(id="div_players_").find_all("p")
        for player in players:
            entry = {
                "name": player.find("a").text,
                "player_id": player.find("a")
                .attrs["href"]
                .split("/")[-1]
                .split(".")[0],
                "years_active": player.text.split("(")[-1].split(")")[0],
            }
            names = pd.concat([names, pd.DataFrame(entry, index=[names.shape[0]])])
    return names
