#!/usr/bin/env python
# -*-coding:utf-8 -*-
"""
@File    :   TennisElo.py
@Time    :   2023/02/13 09:48:18
@author  :   tefirman
@Desc    :   None
"""

import pandas as pd
import numpy as np
import os
import datetime
from bs4 import BeautifulSoup
from math import factorial
import optparse
import sys


def n_choose_k(n: int, k: int) -> float:
    """
    Generates the number of possible combinations for choosing k items from a unique list of n.

    Args:
        n (int): number of things to choose from.
        k (int): number of things to choose.

    Returns:
        float: number of possible combinations.
    """
    return factorial(n) / (factorial(n - k) * factorial(k))


def pull_elo_rankings() -> pd.DataFrame:
    """
    Pull the latest men's and women's elo rankings from "Tennis Abstract" and formats them into a dataframe.

    Returns:
        pd.DataFrame: dataframe containing details and rankings for each of the top ~800 players.
    """
    elo = pd.DataFrame()
    for tour in ["atp", "wta"]:
        os.system(
            "wget http://tennisabstract.com/reports/{}_elo_ratings.html".format(tour)
        )
        tempData = open("{}_elo_ratings.html".format(tour), "r")
        raw = tempData.read()
        tempData.close()
        soup = BeautifulSoup(raw, "html.parser")
        updated = soup.find_all("i")[-1].text.split("Last update: ")[-1]
        players = soup.find(id="reportable").find_all("tr")
        columns = [col.text for col in players.pop(0).find_all("th")] + [
            "Tour",
            "Updated",
        ]
        for player in players:
            values = [val.text for val in player.find_all("td")] + [
                tour.upper(),
                updated,
            ]
            elo = pd.concat(
                [
                    elo,
                    pd.DataFrame(
                        {columns[ind]: [values[ind]] for ind in range(len(columns))}
                    ),
                ],
                ignore_index=True,
            )
        os.remove("{}_elo_ratings.html".format(tour))
    for col in elo.columns:
        if elo[col].str.replace(".", "", regex=False).str.isnumeric().all():
            elo[col] = elo[col].astype(float)
    elo.Updated = pd.to_datetime(elo.Updated)
    elo.Player = elo.Player.str.replace('\xa0',' ')

    # Merge in ace and double fault rates???
    rates = pd.concat([pd.read_csv("https://github.com/JeffSackmann/tennis_atp/raw/master/atp_matches_2023.csv"),\
    pd.read_csv("https://github.com/JeffSackmann/tennis_wta/raw/master/wta_matches_2023.csv")],ignore_index=True,sort=False)
    service = pd.concat([rates[['winner_name','w_ace','w_df','w_svpt']]\
    .rename(columns={'winner_name':'Player','w_ace':'ace','w_df':'df','w_svpt':'svpt'}),\
    rates[['loser_name','l_ace','l_df','l_svpt']].rename(columns={'loser_name':'Player',\
    'l_ace':'ace','l_df':'df','l_svpt':'svpt'})],ignore_index=True,sort=False)
    service['num_matches'] = 1
    avg_ace = service.ace.sum()/service.svpt.sum()
    avg_df = service.df.sum()/service.svpt.sum()
    service = service.groupby('Player').sum().reset_index()
    service['ace_pct'] = service['ace']/service['svpt']
    service['df_pct'] = service['df']/service['svpt']
    service = service.loc[service.num_matches > 10].reset_index(drop=True)
    elo = pd.merge(left=elo,right=service,how='left',on='Player')
    elo.ace_pct = elo.ace_pct.fillna(avg_ace)
    elo.df_pct = elo.df_pct.fillna(avg_df)
    return elo


def load_elos(elo_loc: str = "TennisElo.csv") -> pd.DataFrame:
    """
    Loads the specified elo rankings csv, but if it doesn't exist or isn't recent,
    downloads the latest version from "Tennis Abstract".

    Args:
        elo_loc (str, optional): location of your preferred elo csv. Defaults to "TennisElo.csv".

    Returns:
        pd.DataFrame: dataframe containing the latest details and rankings for each of the top ~800 players.
    """
    if os.path.exists(elo_loc):
        elo = pd.read_csv(elo_loc)
        elo.Updated = pd.to_datetime(elo.Updated)
        if elo.Updated.max() < datetime.datetime.now() - datetime.timedelta(days=7):
            elo = pull_elo_rankings()
            elo.to_csv(elo_loc, index=False)
    else:
        elo = pull_elo_rankings()
        elo.to_csv(elo_loc, index=False)
    corrections = pd.read_csv(
        "https://raw.githubusercontent.com/tefirman/FantasySports/main/res/tennis/name_corrections.csv"
    )
    # corrections = pd.read_csv("res/tennis/name_corrections.csv")
    elo = pd.merge(left=elo, right=corrections, how="left", on="Player")
    elo.loc[~elo.NewPlayer.isnull(), "Player"] = elo.loc[
        ~elo.NewPlayer.isnull(), "NewPlayer"
    ]
    del elo["NewPlayer"]
    return elo


def add_match_details(elo: pd.DataFrame, salary_loc: str = "DKSalaries.csv", court_type: str = "h", base_elo: float = 1500) -> pd.DataFrame:
    """
    Merges in opponents and DFS salaries to elo rankings and extrapolates match & game win probabilities.

    Args:
        elo (pd.DataFrame): dataframe containing the latest details and rankings for each of the top ~800 players.
        salary_loc (str, optional): location of the current DFS salaries. Defaults to "DKSalaries.csv".
        court_type (str, optional): court surface type for the current contests ("h"ard, "c"lay, "g"rass). Defaults to "h".

    Returns:
        pd.DataFrame: updated dataframe containing matchup details for each player in the current slate.
    """
    salaries = pd.read_csv(salary_loc)
    # MAKE IT USE THE MATCHUP NAME RATHER THAN TEAMABBREV!!!
    team_abbrevs = salaries.groupby("TeamAbbrev").size().to_frame('freq').reset_index()
    duplicates = team_abbrevs.loc[team_abbrevs.freq > 1,'TeamAbbrev'].tolist()
    if len(duplicates) > 0:
        print("Duplicate team abbreviations for some players: " + ", ".join(duplicates))
    # MAKE IT USE THE MATCHUP NAME RATHER THAN TEAMABBREV!!!
    missing = salaries.loc[~salaries.Name.isin(elo.Player.tolist()), "Name"].tolist()
    if len(missing) > 0:
        print("Missing some players: " + ", ".join(missing))
        print("Assuming elo rating of {}...".format(base_elo))
        elo = pd.concat(
            [
                elo,
                pd.DataFrame(
                    {
                        "Player": missing,
                        "gElo": [base_elo] * len(missing),
                        "hElo": [base_elo] * len(missing),
                        "cElo": [base_elo] * len(missing),
                        "ace_pct": [0.0585] * len(missing),
                        "df_pct": [0.0428] * len(missing),
                    }
                ),
            ],
            ignore_index=True,
        )
    salaries["OppAbbrev"] = salaries.apply(
        lambda x: x["Game Info"]
        .split(" 0")[0]
        .split(" 1")[0]
        .replace("@", "")
        .replace(x["TeamAbbrev"], ""),
        axis=1,
    )
    matchups = pd.merge(
        left=salaries,
        right=salaries[["Name", "TeamAbbrev"]].rename(
            columns={"Name": "OppName", "TeamAbbrev": "OppAbbrev"}
        ),
        how="inner",
        on="OppAbbrev",
    )
    matchups = pd.merge(
        left=matchups,
        right=elo[["Player", court_type + "Elo", "ace_pct", "df_pct", "Tour"]].rename(
            columns={"Player": "Name", court_type + "Elo": "Elo", "ace_pct":"AcePct", "df_pct":"DfPct"}
        ),
        how="inner",
        on="Name",
    )
    matchups = pd.merge(
        left=matchups,
        right=elo[["Player", court_type + "Elo", "ace_pct", "df_pct"]].rename(
            columns={"Player": "OppName", court_type + "Elo": "OppElo", "ace_pct":"OppAcePct", "df_pct":"OppDfPct"}
        ),
        how="inner",
        on="OppName",
    )
    matchups["elo_diff"] = matchups["Elo"] - matchups["OppElo"]
    matchups["match3_prob"] = 1 - (1 / (1 + 10 ** (matchups["elo_diff"] / 400)))
    matchups["set_prob"] = matchups["match3_prob"].apply(
        lambda x: np.roots([-2, 3, 0, -1 * x])[1]
    )
    # matchups['game_prob'] = matchups['set_prob'].apply(lambda x: np.roots([-252+252, 
    # 1260-1512, 126-2520+3780, -56-504+2520-5040, 21+168+756-1260+3780, -6-42-168-504+252-1512, 
    # 1+6+21+56+126+252, 0, 0, 0, 0, 0, -1*x])[1])
    matchups["game_prob"] = matchups["set_prob"].apply(
        lambda x: np.roots(
            [-252, 1386, -3080, 3465, -1980, 462, 0, 0, 0, 0, 0, -1 * x]
        )[5].real
    )
    matchups["match5_prob"] = matchups["set_prob"].apply(
        lambda x: (x**3) * (4 - 3 * x + 6 * (1 - x) * (1 - x))
    )
    return matchups


def set_probabilities(matchup, scoring, pts_per_game=6.4):
    set_probs = pd.DataFrame(
        columns=["games_won", "games_lost", "sets_won", "sets_lost", "probability"]
    )
    for lost in range(5):
        set_probs = pd.concat(
            [
                set_probs,
                pd.DataFrame(
                    {
                        "games_won": [6],
                        "games_lost": [lost],
                        "sets_won": [1],
                        "sets_lost": [0],
                        "prob": [
                            n_choose_k(6 + lost, lost) * (matchup['game_prob']**6) * ((1 - matchup['game_prob']) ** lost)
                        ],
                    }
                ),
            ],
            ignore_index=True,
        )
    set_probs = pd.concat(
        [
            set_probs,
            pd.DataFrame(
                {
                    "games_won": [7],
                    "games_lost": [5],
                    "sets_won": [1],
                    "sets_lost": [0],
                    "prob": [n_choose_k(10, 5) * (matchup['game_prob']**7) * ((1 - matchup['game_prob']) ** 5)],
                }
            ),
        ],
        ignore_index=True,
    )
    set_probs = pd.concat(
        [
            set_probs,
            pd.DataFrame(
                {
                    "games_won": [6],
                    "games_lost": [6],
                    "sets_won": [1],
                    "sets_lost": [0],
                    "prob": [n_choose_k(10, 5) * (matchup['game_prob']**6) * ((1 - matchup['game_prob']) ** 6)],
                }
            ),
        ],
        ignore_index=True,
    )
    for won in range(5):
        set_probs = pd.concat(
            [
                set_probs,
                pd.DataFrame(
                    {
                        "games_won": [won],
                        "games_lost": [6],
                        "sets_won": [0],
                        "sets_lost": [1],
                        "prob": [
                            n_choose_k(6 + won, won) * (matchup['game_prob']**won) * ((1 - matchup['game_prob']) ** 6)
                        ],
                    }
                ),
            ],
            ignore_index=True,
        )
    set_probs = pd.concat(
        [
            set_probs,
            pd.DataFrame(
                {
                    "games_won": [5],
                    "games_lost": [7],
                    "sets_won": [0],
                    "sets_lost": [1],
                    "prob": [n_choose_k(10, 5) * (matchup['game_prob']**5) * ((1 - matchup['game_prob']) ** 7)],
                }
            ),
        ],
        ignore_index=True,
    )
    set_probs = pd.concat(
        [
            set_probs,
            pd.DataFrame(
                {
                    "games_won": [6],
                    "games_lost": [6],
                    "sets_won": [0],
                    "sets_lost": [1],
                    "prob": [n_choose_k(10, 5) * (matchup['game_prob']**6) * ((1 - matchup['game_prob']) ** 6)],
                }
            ),
        ],
        ignore_index=True,
    )
    set_probs.prob = set_probs.prob / set_probs.prob.sum()
    set_probs["DKFP"] = (
        set_probs.games_won * scoring["game_won"]
        + set_probs.games_lost * scoring["game_lost"]
        + (set_probs.games_lost < 6).astype(float)*set_probs.apply(lambda x: max(x["games_won"] - x["games_lost"],0.0)/2.0,axis=1)*scoring["break_point"]
        + (set_probs.games_won + set_probs.games_lost)/2.0*pts_per_game*(matchup["AcePct"]*scoring["ace"] + matchup["DfPct"]*scoring["double_fault"])
        + set_probs.sets_won * scoring["set_won"]
        + set_probs.sets_lost * scoring["set_lost"]
    )
    set_probs["DKFP_opp"] = (
        set_probs.games_lost * scoring["game_won"]
        + set_probs.games_won * scoring["game_lost"]
        + (set_probs.games_won < 6).astype(float)*set_probs.apply(lambda x: max(x["games_lost"] - x["games_won"],0.0)/2.0,axis=1)*scoring["break_point"]
        + (set_probs.games_won + set_probs.games_lost)/2.0*pts_per_game*(matchup["OppAcePct"]*scoring["ace"] + matchup["OppDfPct"]*scoring["double_fault"])
        + set_probs.sets_lost * scoring["set_won"]
        + set_probs.sets_won * scoring["set_lost"]
    )
    set_probs.loc[
        (set_probs.games_won == 6) & (set_probs.games_lost == 0), "DKFP"
    ] += scoring["clean_set"]
    set_probs.loc[
        (set_probs.games_won == 0) & (set_probs.games_lost == 6), "DKFP_opp"
    ] += scoring["clean_set"]
    return set_probs


def match_probabilities(matchup, scoring, major=False):
    wins = pd.DataFrame()
    losses = pd.DataFrame()
    set_probs = set_probabilities(matchup, scoring)
    set_probs["dummy"] = 1
    match_combos = pd.merge(
        left=set_probs.rename(
            columns={col: col + "_1" for col in set_probs.columns if col != "dummy"}
        ),
        right=set_probs.rename(
            columns={col: col + "_2" for col in set_probs.columns if col != "dummy"}
        ),
        how="inner",
        on="dummy",
    )
    match_combos["DKFP"] = scoring["match_played"] + match_combos["DKFP_1"] + match_combos["DKFP_2"]
    match_combos["DKFP_opp"] = scoring["match_played"] + match_combos["DKFP_opp_1"] + match_combos["DKFP_opp_2"]
    match_combos["prob"] = match_combos["prob_1"] * match_combos["prob_2"]
    if not major:
        match_combos["sets_won"] = match_combos[
            [col for col in match_combos.columns if col.startswith("sets_won_")]
        ].sum(axis=1)
        match_combos["sets_lost"] = match_combos[
            [col for col in match_combos.columns if col.startswith("sets_lost_")]
        ].sum(axis=1)
        match_combos.loc[match_combos.sets_won == 2, "DKFP"] += (
            scoring["straight_sets"] + scoring["match_won"]
        )
        match_combos.loc[match_combos.sets_lost == 2, "DKFP_opp"] += (
            scoring["straight_sets"] + scoring["match_won"]
        )
        wins = pd.concat(
            [wins, match_combos.loc[match_combos.sets_won == 2]], ignore_index=True
        )
        losses = pd.concat(
            [losses, match_combos.loc[match_combos.sets_lost == 2]], ignore_index=True
        )
        match_combos = match_combos.loc[match_combos.sets_won == 1].reset_index(
            drop=True
        )
    match_combos = pd.merge(
        left=match_combos,
        right=set_probs.rename(
            columns={col: col + "_3" for col in set_probs.columns if col != "dummy"}
        ),
        how="inner",
        on="dummy",
    )
    match_combos["DKFP"] += match_combos["DKFP_3"]
    match_combos["DKFP_opp"] += match_combos["DKFP_opp_3"]
    match_combos["prob"] *= match_combos["prob_3"]
    match_combos["sets_won"] = match_combos[
        [col for col in match_combos.columns if col.startswith("sets_won_")]
    ].sum(axis=1)
    match_combos["sets_lost"] = match_combos[
        [col for col in match_combos.columns if col.startswith("sets_lost_")]
    ].sum(axis=1)
    winner = 3 if major else 2
    match_combos.loc[match_combos.sets_won == winner, "DKFP"] += scoring[
        "match_won"
    ] + (scoring["straight_sets"] if major else 0)
    match_combos.loc[match_combos.sets_lost == winner, "DKFP_opp"] += scoring[
        "match_won"
    ] + (scoring["straight_sets"] if major else 0)
    wins = pd.concat(
        [wins, match_combos.loc[match_combos.sets_won == winner]], ignore_index=True
    )
    losses = pd.concat(
        [losses, match_combos.loc[match_combos.sets_lost == winner]],
        ignore_index=True,
    )
    match_combos = match_combos.loc[
        ~match_combos.sets_won.isin([winner]) & ~match_combos.sets_lost.isin([winner])
    ].reset_index(drop=True)
    if major:
        match_combos = pd.merge(
            left=match_combos.loc[match_combos.sets_won.isin([1, 2])],
            right=set_probs.rename(
                columns={col: col + "_4" for col in set_probs.columns if col != "dummy"}
            ),
            how="inner",
            on="dummy",
        )
        match_combos["DKFP"] += match_combos["DKFP_4"]
        match_combos["DKFP_opp"] += match_combos["DKFP_opp_4"]
        match_combos["prob"] *= match_combos["prob_4"]
        match_combos["sets_won"] = match_combos[
            [col for col in match_combos.columns if col.startswith("sets_won_")]
        ].sum(axis=1)
        match_combos["sets_lost"] = match_combos[
            [col for col in match_combos.columns if col.startswith("sets_lost_")]
        ].sum(axis=1)
        match_combos.loc[match_combos.sets_won == 3, "DKFP"] += scoring["match_won"]
        match_combos.loc[match_combos.sets_lost == 3, "DKFP_opp"] += scoring["match_won"]
        wins = pd.concat(
            [wins, match_combos.loc[match_combos.sets_won == 3]], ignore_index=True
        )
        losses = pd.concat(
            [losses, match_combos.loc[match_combos.sets_lost == 3]], ignore_index=True
        )
        match_combos = pd.merge(
            left=match_combos.loc[match_combos.sets_won == 2],
            right=set_probs.rename(
                columns={col: col + "_5" for col in set_probs.columns if col != "dummy"}
            ),
            how="inner",
            on="dummy",
        )
        match_combos["DKFP"] += match_combos["DKFP_5"]
        match_combos["DKFP_opp"] += match_combos["DKFP_opp_5"]
        match_combos["prob"] *= match_combos["prob_5"]
        match_combos["sets_won"] = match_combos[
            [col for col in match_combos.columns if col.startswith("sets_won_")]
        ].sum(axis=1)
        match_combos["sets_lost"] = match_combos[
            [col for col in match_combos.columns if col.startswith("sets_lost_")]
        ].sum(axis=1)
        match_combos.loc[match_combos.sets_won == 3, "DKFP"] += scoring["match_won"]
        match_combos.loc[match_combos.sets_lost == 3, "DKFP_opp"] += scoring["match_won"]
    outcomes = pd.concat(
        [
            match_combos[["DKFP", "DKFP_opp", "prob"]],
            wins[["DKFP", "DKFP_opp", "prob"]],
            losses[["DKFP", "DKFP_opp", "prob"]],
        ],
        ignore_index=True,
    )
    return outcomes


def project_points(matchups, major=False, underdog=False, verbose=False):
    scoring = (
        pd.read_csv(
            "https://raw.githubusercontent.com/tefirman/FantasySports/main/res/tennis/scoring.csv"
        )
        .set_index("stat")
        .to_dict()
    )
    # scoring = pd.read_csv("res/tennis/scoring.csv").set_index("stat").to_dict()
    for ind in range(matchups.shape[0]):
        if verbose:
            print(matchups.loc[ind, "Name"])
        num_sets = "underdog" if underdog else (
            "three_set"
            if matchups.loc[ind, "Tour"] == "WTA" or not major
            else "five_set"
        )
        outcomes = match_probabilities(matchups.iloc[ind], scoring[num_sets], major)
        avg = (outcomes.prob * outcomes.DKFP).sum()
        sq_avg = (outcomes.prob * (outcomes.DKFP**2.0)).sum()
        stdev = (sq_avg - avg**2.0)**0.5
        matchups.loc[ind, "DKFP"] = avg
        if verbose:
            print("{} +/- {}".format(round(avg,2),round(stdev,2)))
    players = matchups[["Name", "Salary", "DKFP", "OppName"]]
    return players


def simulate_points(matchups, num_sims=1000, major=False, verbose=False):
    scoring = (
        pd.read_csv(
            "https://raw.githubusercontent.com/tefirman/FantasySports/main/res/tennis/scoring.csv"
        )
        .set_index("stat")
        .to_dict()
    )
    # scoring = pd.read_csv("res/tennis/scoring.csv").set_index("stat").to_dict()
    sim_matches = pd.DataFrame(columns=['Name','OppName'])
    for ind in range(matchups.shape[0]):
        if matchups.iloc[ind]["Name"] in matchups.iloc[:ind]["OppName"].unique():
            continue
        if verbose:
            print(matchups.iloc[ind]["Name"] + ' vs. ' + matchups.iloc[ind]["OppName"])
        num_sets = (
            "three_set"
            if matchups.iloc[ind]["Tour"] == "WTA" or not major
            else "five_set"
        )
        outcomes = match_probabilities(matchups.iloc[ind], scoring[num_sets], major)
        outcomes['Name'] = matchups.iloc[ind]['Name']
        outcomes['OppName'] = matchups.iloc[ind]['OppName']
        sim_matches = pd.concat([sim_matches,outcomes.sample(n=num_sims,weights='prob',replace=True)],ignore_index=True,sort=False)
    sim_matches = pd.concat([sim_matches[['Name','DKFP']],sim_matches[['OppName','DKFP_opp']]\
    .rename(columns={'OppName':'Name','DKFP_opp':'DKFP'})],ignore_index=True)
    sim_matches = sim_matches.rename(columns={'DKFP':'DKFP_sim'})
    sim_matches['num_sim'] = sim_matches.index%num_sims
    return sim_matches


def compile_teams(salaries, salary_cap=50000, same_match=False, fixed=None, \
verbose=False, shortslate=False, salary_rate=-0.003125):
    salaries["dummy"] = 1
    teams = pd.DataFrame({"dummy": [1], "Name": [""], "DKFP": [0], "Salary": [0]})
    spots = 3 if shortslate else 6
    for ind in range(spots):
        pos = ['CPT','A-CPT','P'][ind] if shortslate else 'P'
        multiplier = [1.5,1.25,1.0][ind] if shortslate else 1.0
        teams = pd.merge(
            left=teams,
            right=salaries.loc[salaries['Roster Position'] == pos,\
            ["dummy", "Name", "DKFP", "Salary", "OppName"]].rename(
                columns={
                    "Name": "Name_" + str(ind + 1),
                    "DKFP": "DKFP_" + str(ind + 1),
                    "Salary": "Salary_" + str(ind + 1),
                }
            ),
            how="inner",
            on="dummy",
        )
        teams = teams.loc[
            teams.apply(lambda x: x["Name_" + str(ind + 1)] not in x["Name"], axis=1)
        ]
        teams = teams.loc[
            teams["Salary"] + teams["Salary_" + str(ind + 1)]
            < salary_cap - salaries.Salary.min() * (spots - ind - 1)
        ]
        teams.Name += "_" + teams["Name_" + str(ind + 1)] + '-' + pos
        teams.DKFP += teams["DKFP_" + str(ind + 1)]*multiplier
        teams.Salary += teams["Salary_" + str(ind + 1)]
        teams.Name = teams.Name.apply(lambda x: "_".join(sorted(x.split("_"))))
        """ Eliminating lineups with match opponents """
        if not same_match:
            teams = teams.loc[
                teams.apply(lambda x: x["OppName"] not in x["Name"], axis=1)
            ]
        del (
            teams["Name_" + str(ind + 1)],
            teams["DKFP_" + str(ind + 1)],
            teams["Salary_" + str(ind + 1)],
            teams["OppName"],
        )
        """ Forcing lineup spots """
        if fixed:
            teams["valid"] = True
            for fixed in fixed.split(","):
                teams.valid = teams.valid & teams.Name.str.contains(fixed)
            if teams.valid.any():
                teams = teams.loc[teams.valid]
        if verbose:
            print(teams.shape)
        teams = (
            teams.drop_duplicates(subset=["Name"])
            .sort_values(by="DKFP", ascending=False)
            .reset_index(drop=True)#.iloc[:100000]
        )
    del teams["dummy"]
    teams.Name = teams.Name.str[1:].str.replace("_", ", ")
    teams.DKFP = round(teams.DKFP, 2)
    teams = teams[["Name", "DKFP", "Salary"]]
    q = sum(np.exp(salary_rate*(50000 - np.arange(0,50001,100))))
    for salary in range(10000,50001,100):
        sal_teams = teams.Salary == salary
        if sal_teams.any():
            teams.loc[sal_teams,'Probability'] = np.exp(salary_rate*(50000 - salary))/(q*sal_teams.sum())
    if shortslate:
        teams['captain'] = teams.Name.str.replace('-A-CPT','-ACPT').str.split('-CPT').str[0].str.split(', ').str[-1]
    else:
        teams['captain'] = teams['Name']
        teams.captain = teams.captain.str[:-2].str.split('-P, ')
        teams = teams.explode('captain',ignore_index=True)
        teams = pd.merge(left=teams,right=salaries[['Name','Salary']].rename(columns={'Name':'captain','Salary':'cpt_salary'}),how='inner',on='captain')
        teams = teams.sort_values(by=['DKFP','cpt_salary'],ascending=False).drop_duplicates(subset=['Name'],keep='first',ignore_index=True)
    return teams


def simulate_contest(teams, matchups, contest_type, num_sims=1000, major=False, verbose=False):
    if contest_type == 'QuarterJukebox50':
        num_entries = 237
        max_entries = 7
        entry_fee = 0.25
        payouts = [5,4,3,2,2,1.5,1.5,1.5] + 6*[1.0] + 12*[0.75] + 29*[0.5]
    elif contest_type == 'QuarterJukebox200':
        num_entries = 951
        max_entries = 20
        entry_fee = 0.25
        payouts = [20,10,7.5,5,4,3,3,2,2,2,2,2] + 10*[1.5] + 20*[1.0] + 50*[0.75] + 130*[0.5]
    elif contest_type == 'QuarterJukebox400':
        num_entries = 1902
        max_entries = 20
        entry_fee = 0.25
        payouts = [40,20,15,10,8,6,5,4,3,3] + 5*[2.0] + 15*[1.5] + 40*[1.0] + 110*[0.75] + 262*[0.5]
    elif contest_type == 'DoubleUp':
        num_entries = 23
        max_entries = 1
        entry_fee = 1.0
        payouts = [2.0]*10
    elif contest_type == 'Satellite':
        num_entries = 250
        max_entries = 7
        entry_fee = 0.25
        payouts = [20]
    else:
        print("Don't recognize the contest type provided, assuming Quarter Jukebox...")
        num_entries = 1400
        max_entries = 20
        payouts = [25,10,5,4,3,2,1]
    payouts = payouts + [0]*(num_entries - len(payouts))
    if 'my_entries' not in teams.columns:
        teams['my_entries'] = 0.0
    sims = teams.sample(n=int((num_entries - teams.my_entries.sum())*num_sims),replace=True,weights="Probability",ignore_index=True)
    my_entries = teams.loc[teams.my_entries > 0].reset_index(drop=True)
    if my_entries.my_entries.sum() > max_entries:
        print("Too many entries for this contest!!! Only using the first {}...".format(max_entries))
        while my_entries.my_entries.sum() > max_entries:
            my_entries.loc[my_entries.shape[0] - 1,'my_entries'] -= 1
            my_entries = my_entries.loc[my_entries.my_entries > 0].reset_index(drop=True)
    for ind in range(my_entries.shape[0]):
        this_entry = pd.concat(int(my_entries.iloc[ind]['my_entries']*num_sims)*[my_entries.iloc[ind:ind + 1]],ignore_index=True)
        sims = pd.concat([sims,this_entry],ignore_index=True)
    sims['num_sim'] = sims.index%num_sims
    sims['num_entry'] = sims.index//num_sims
    sims.Name = sims.Name.str.replace('-A-CPT','-P').str.replace('-CPT','-P')
    sims.Name = sims.Name.str[:-2].str.split('-P, ')
    sims = sims.explode('Name',ignore_index=True)
    sim_matches = simulate_points(matchups, num_sims, major, verbose)
    sims = pd.merge(left=sims,right=sim_matches[['num_sim','Name','DKFP_sim']],how='inner',on=['num_sim','Name'])
    sims = sims.groupby(['num_sim','num_entry']).DKFP_sim.sum().reset_index()
    sims = sims.sort_values(by=['num_sim','DKFP_sim'],ascending=[True,False],ignore_index=True)
    sims['ranking'] = sims.groupby(['num_sim']).DKFP_sim.rank(ascending=False,method='min')
    sims['projected_payout'] = payouts*num_sims
    payouts = sims.groupby(['num_sim','DKFP_sim']).projected_payout.mean()\
    .reset_index().rename(columns={'projected_payout':'actual_payout'})
    sims = pd.merge(left=sims,right=payouts,how='inner',on=['num_sim','DKFP_sim'])
    sims['my_entry'] = sims.num_entry >= num_entries - teams.my_entries.sum()
    sims['entry_fee'] = entry_fee
    return sims


def best_lineups(teams, matchups, contest_type, limit=5, num_sims=1000, major=False, verbose=False, shortslate=False):
    if 'my_entries' not in teams.columns:
        teams['my_entries'] = 0.0
    teams[['profit','profit_stdev','profit_fano','gain_prob','push_prob','loss_prob','zero_prob','win_prob']] = None
    cpt_inds = teams.groupby('captain').head(limit).index.tolist()[:50]
    for ind in cpt_inds:
        teams.loc[ind,'my_entries'] += 1.0
        contest_sims = simulate_contest(teams, matchups, contest_type, num_sims=num_sims, major=False)
        payouts = contest_sims.loc[contest_sims.my_entry].groupby('num_sim')[['actual_payout','entry_fee']].sum().reset_index()
        payouts['profit'] = payouts['actual_payout'] - payouts['entry_fee']
        teams.loc[ind,'profit'] = payouts.profit.mean()
        teams.loc[ind,'profit_stdev'] = payouts.profit.std()
        teams.loc[ind,'profit_fano'] = payouts.profit.std()/payouts.profit.mean()
        teams.loc[ind,'gain_prob'] = payouts.loc[payouts.profit > 0.0].shape[0]/num_sims
        teams.loc[ind,'push_prob'] = payouts.loc[payouts.profit == 0.0].shape[0]/num_sims
        teams.loc[ind,'loss_prob'] = payouts.loc[payouts.profit < 0.0].shape[0]/num_sims
        teams.loc[ind,'zero_prob'] = payouts.loc[payouts.actual_payout == 0].shape[0]/num_sims
        teams.loc[ind,'win_prob'] = contest_sims.loc[(contest_sims.ranking == 1) & contest_sims.my_entry,'num_sim'].nunique()/num_sims
        teams.loc[ind,'my_entries'] -= 1.0
        if verbose:
            print("{} out of {}, {}".format((~teams.win_prob.isnull()).sum(),len(cpt_inds),datetime.datetime.now()))
    return teams


def best_combos(teams, matchups, contest_type, limit=5, num_sims=1000, major=False, verbose=False):
    best = pd.DataFrame()
    for num_entry in range(limit):
        print('Simulating {} entr'.format(num_entry + 1) + ('ies' if num_entry > 0 else 'y'))
        teams = best_lineups(teams, matchups, contest_type, num_sims=num_sims, major=major, verbose=verbose)
        teams = teams.sort_values(by='profit',ascending=False).reset_index(drop=True)
        if verbose:
            print(teams.iloc[0].Name)
            print(teams.iloc[0])
        best = pd.concat([best,teams.iloc[:1]],ignore_index=True,sort=False)
        teams.loc[0,'my_entries'] += 1
    return best


def excel_autofit(df, name, writer):
    f = writer.book.add_format({"num_format": "0.00"})
    f.set_align("center")
    f.set_align("vcenter")
    m = writer.book.add_format({"num_format": "$0"})
    m.set_align("center")
    m.set_align("vcenter")
    df.to_excel(writer, sheet_name=name, index=False)
    for idx, col in enumerate(df):
        series = df[col]
        max_len = min(
            max((series.astype(str).map(len).max(), len(str(series.name)))) + 5, 100
        )
        if col == "Salary":
            writer.sheets[name].set_column(idx, idx, max_len, m)
        else:
            writer.sheets[name].set_column(idx, idx, max_len, f)
    writer.sheets[name].autofilter(
        "A1:"
        + (
            chr(64 + (df.shape[1] - 1) // 26) + chr(65 + (df.shape[1] - 1) % 26)
        ).replace("@", "")
        + str(df.shape[0] + 1)
    )
    return writer


def write_to_spreadsheet(teams, combos, output=""):
    writer = pd.ExcelWriter(
        output + "DFS_Tennis_{}.xlsx".format(datetime.datetime.now().strftime("%m%d%y")),
        engine="xlsxwriter",
    )
    writer.book.add_format({"align": "vcenter"})
    writer = excel_autofit(teams, "Teams", writer)
    writer.sheets["Teams"].conditional_format(
        "B2:B" + str(teams.shape[0] + 1),
        {
            "type": "3_color_scale",
            "min_color": "#FF6347",
            "mid_color": "#FFD700",
            "max_color": "#3CB371",
        },
    )
    writer = excel_autofit(combos, "Combos", writer)
    writer.sheets["Combos"].conditional_format(
        "B2:B" + str(teams.shape[0] + 1),
        {
            "type": "3_color_scale",
            "min_color": "#FF6347",
            "mid_color": "#FFD700",
            "max_color": "#3CB371",
        },
    )
    writer.close()


def main():
    parser = optparse.OptionParser()
    parser.add_option(
        "--elos",
        action="store",
        dest="elos",
        default="TennisElo.csv",
        help="location of elo ratings, automatically pulled if none supplied",
    )
    parser.add_option(
        "--salaries",
        action="store",
        dest="salaries",
        default="DKSalaries.csv",
        help="location of DK salaries/opponents",
    )
    parser.add_option(
        "--court",
        action="store",
        dest="court",
        help="type of court being played on (hard, clay, or grass)",
    )
    parser.add_option(
        "--major",
        action="store_true",
        dest="major",
        help="whether the current event is a major tournament",
    )
    parser.add_option(
        "--samematch",
        action="store_true",
        dest="samematch",
        help="whether to allow players from the same match in your lineups (not recommended)",
    )
    parser.add_option(
        "--baseelo",
        action="store",
        dest="baseelo",
        type="int",
        default=1500,
        help="default elo ranking if none exists",
    )
    parser.add_option(
        "--salarycap",
        action="store",
        dest="salarycap",
        type="int",
        default=50000,
        help="team-building salary cap",
    )
    parser.add_option(
        "--fixed",
        action="store",
        dest="fixed",
        help="comma separated list of players to force into every lineup",
    )
    parser.add_option(
        "--shortstack",
        action="store_true",
        dest="shortstack",
        help="assembles teams based on short-stack rules",
    )
    parser.add_option(
        "--underdog",
        action="store_true",
        dest="underdog",
        help="whether to use Underdog scoring settings",
    )
    parser.add_option(
        "--verbose",
        action="store_true",
        dest="verbose",
        help="whether to print out status updates as the code progresses",
    )
    parser.add_option(
        "--output",
        action="store",
        dest="output",
        default=os.path.expanduser("~/Documents/"),
        help="where to save the final projections spreadsheet",
    )
    options, args = parser.parse_args()
    if not options.output.endswith('/'):
        options.output += '/'
    if not os.path.exists(options.output + 'DFS'):
        os.mkdir(options.output + 'DFS')
    if not os.path.exists(options.output + 'DFS/Tennis'):
        os.mkdir(options.output + 'DFS/Tennis')
    options.output += 'DFS/Tennis/'

    elo = load_elos(options.elos)
    matchups = add_match_details(elo, options.salaries, options.court[0] if options.court else "", base_elo=options.baseelo)
    players = project_points(matchups, options.major, options.underdog, options.verbose) # Alters matchups somehow... Object-based coding...
    # print(matchups[['Name','Elo']])
    # print(matchups.Elo.mean())
    # print(matchups.Elo.std())
    if not options.underdog:
        teams = compile_teams(matchups, options.salarycap, options.samematch, options.fixed, options.verbose, options.shortstack)
        teams = best_lineups(teams, matchups, "DoubleUp", limit=5, num_sims=5000, major=options.major, verbose=options.verbose)
        print('Double Up')
        print(teams.sort_values(by='profit',ascending=False).iloc[0].Name)
        print(teams.sort_values(by='profit',ascending=False).iloc[0])
        print('Quarter Jukebox')
        combos = best_combos(teams.copy(), matchups, "QuarterJukebox200", limit=20, num_sims=500, major=options.major, verbose=options.verbose)
        write_to_spreadsheet(teams.iloc[:20000], combos, options.output)


if __name__ == "__main__":
    main()
