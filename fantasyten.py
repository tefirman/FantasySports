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
    elo.Updated = pd.to_datetime(elo.Updated, infer_datetime_format=True)
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
        elo.Updated = pd.to_datetime(elo.Updated, infer_datetime_format=True)
        if elo.Updated.max() < datetime.datetime.now() - datetime.timedelta(days=7):
            elo = pull_elo_rankings()
            elo.to_csv(elo_loc, index=False)
    else:
        elo = pull_elo_rankings()
        elo.to_csv(elo_loc, index=False)
    corrections = pd.read_csv(
        "https://raw.githubusercontent.com/tefirman/FantasySports/main/res/tennis/name_corrections.csv"
    )
    elo = pd.merge(left=elo, right=corrections, how="left", on="Player")
    elo.loc[~elo.NewPlayer.isnull(), "Player"] = elo.loc[
        ~elo.NewPlayer.isnull(), "NewPlayer"
    ]
    del elo["NewPlayer"]
    return elo


def add_match_details(elo: pd.DataFrame, salary_loc: str = "DKSalaries.csv", court_type: str = "h") -> pd.DataFrame:
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
    missing = salaries.loc[~salaries.Name.isin(elo.Player.tolist()), "Name"].tolist()
    if len(missing) > 0:
        print("Missing some players: " + ", ".join(missing))
        print("Assuming elo rating of 1100...")
        elo = pd.concat(
            [
                elo,
                pd.DataFrame(
                    {
                        "Player": missing,
                        "gElo": [1100] * len(missing),
                        "hElo": [1100] * len(missing),
                        "cElo": [1100] * len(missing),
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
        right=elo[["Player", court_type + "Elo", "Tour"]].rename(
            columns={"Player": "Name", court_type + "Elo": "Elo"}
        ),
        how="inner",
        on="Name",
    )
    matchups = pd.merge(
        left=matchups,
        right=elo[["Player", court_type + "Elo"]].rename(
            columns={"Player": "OppName", court_type + "Elo": "OppElo"}
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


def set_probabilities(p, scoring):
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
                            n_choose_k(6 + lost, lost) * (p**6) * ((1 - p) ** lost)
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
                    "prob": [n_choose_k(10, 5) * (p**7) * ((1 - p) ** 5)],
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
                    "prob": [n_choose_k(10, 5) * (p**6) * ((1 - p) ** 6)],
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
                            n_choose_k(6 + won, won) * (p**won) * ((1 - p) ** 6)
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
                    "prob": [n_choose_k(10, 5) * (p**5) * ((1 - p) ** 7)],
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
                    "prob": [n_choose_k(10, 5) * (p**6) * ((1 - p) ** 6)],
                }
            ),
        ],
        ignore_index=True,
    )
    set_probs.prob = set_probs.prob / set_probs.prob.sum()
    set_probs["DKFP"] = (
        set_probs.games_won * scoring["game_won"]
        + set_probs.games_lost * scoring["game_lost"]
        + set_probs.sets_won * scoring["set_won"]
        + set_probs.sets_lost * scoring["set_lost"]
    )
    set_probs.loc[
        (set_probs.games_won == 6) & (set_probs.games_lost == 0), "DKFP"
    ] += scoring["clean_set"]
    return set_probs


def match_probabilities(p, scoring, major=False):
    wins = pd.DataFrame()
    losses = pd.DataFrame()
    set_probs = set_probabilities(p, scoring)
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
    match_combos["DKFP"] = match_combos["DKFP_1"] + match_combos["DKFP_2"]
    match_combos["prob"] = match_combos["prob_1"] * match_combos["prob_2"]
    if not major:
        match_combos["sets_won"] = match_combos[
            [col for col in match_combos.columns if col.startswith("sets_won_")]
        ].sum(axis=1)
        match_combos.loc[match_combos.sets_won == 2, "DKFP"] += (
            scoring["straight_sets"] + scoring["match_won"]
        )
        wins = pd.concat(
            [wins, match_combos.loc[match_combos.sets_won == 2]], ignore_index=True
        )
        losses = pd.concat(
            [losses, match_combos.loc[match_combos.sets_won == 0]], ignore_index=True
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
    match_combos["prob"] *= match_combos["prob_3"]
    match_combos["sets_won"] = match_combos[
        [col for col in match_combos.columns if col.startswith("sets_won_")]
    ].sum(axis=1)
    winner = 3 if major else 2
    match_combos.loc[match_combos.sets_won == winner, "DKFP"] += scoring[
        "match_won"
    ] + (scoring["straight_sets"] if major else 0)
    wins = pd.concat(
        [wins, match_combos.loc[match_combos.sets_won == winner]], ignore_index=True
    )
    losses = pd.concat(
        [losses, match_combos.loc[match_combos.sets_won == 3 - winner]],
        ignore_index=True,
    )
    match_combos = match_combos.loc[
        ~match_combos.sets_won.isin([winner, 3 - winner])
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
        match_combos["prob"] *= match_combos["prob_4"]
        match_combos["sets_won"] = match_combos[
            [col for col in match_combos.columns if col.startswith("sets_won_")]
        ].sum(axis=1)
        match_combos.loc[match_combos.sets_won == 3, "DKFP"] += scoring["match_won"]
        wins = pd.concat(
            [wins, match_combos.loc[match_combos.sets_won == 3]], ignore_index=True
        )
        losses = pd.concat(
            [losses, match_combos.loc[match_combos.sets_won == 1]], ignore_index=True
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
        match_combos["prob"] *= match_combos["prob_5"]
        match_combos["sets_won"] = match_combos[
            [col for col in match_combos.columns if col.startswith("sets_won_")]
        ].sum(axis=1)
        match_combos.loc[match_combos.sets_won == 3, "DKFP"] += scoring["match_won"]
    outcomes = pd.concat(
        [
            match_combos[["DKFP", "prob"]],
            wins[["DKFP", "prob"]],
            losses[["DKFP", "prob"]],
        ],
        ignore_index=True,
    )
    return outcomes


def project_points(matchups, major=False, verbose=False):
    scoring = (
        pd.read_csv(
            "https://raw.githubusercontent.com/tefirman/FantasySports/main/res/tennis/scoring.csv"
        )
        .set_index("stat")
        .to_dict()
    )
    for ind in range(matchups.shape[0]):
        if verbose:
            print(matchups.loc[ind, "Name"])
        p = matchups.loc[ind, "game_prob"]
        num_sets = (
            "three_set"
            if matchups.loc[ind, "Tour"] == "WTA" or not major
            else "five_set"
        )
        outcomes = match_probabilities(p, scoring[num_sets], major)
        matchups.loc[ind, "DKFP"] = (outcomes.prob * outcomes.DKFP).sum()
        if verbose:
            print((outcomes.prob * outcomes.DKFP).sum())
    players = matchups[["Name", "Salary", "DKFP", "OppName"]]
    return players


def compile_teams(
    salaries, salary_cap=50000, same_match=False, fixed=None, verbose=False
):
    salaries["dummy"] = 1
    teams = pd.DataFrame({"dummy": [1], "Name": [""], "DKFP": [0], "Salary": [0]})
    spots = 6
    for ind in range(spots):
        teams = pd.merge(
            left=teams,
            right=salaries[["dummy", "Name", "DKFP", "Salary", "OppName"]].rename(
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
            < salary_cap - (3500 * (spots - ind) if ind < spots - 2 else 0)
        ]
        teams.Name += "_" + teams["Name_" + str(ind + 1)]
        teams.DKFP += teams["DKFP_" + str(ind + 1)]
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
            .reset_index(drop=True)
        )
    del teams["dummy"]
    teams.Name = teams.Name.str[1:].str.replace("_", ", ")
    teams.DKFP = round(teams.DKFP, 2)
    teams = teams[["Name", "DKFP", "Salary"]]
    return teams


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


def write_to_spreadsheet(teams, output=""):
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
        default="hard",
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
    matchups = add_match_details(elo, options.salaries, options.court[0])
    players = project_points(matchups, options.major, options.verbose)
    teams = compile_teams(
        matchups, options.salarycap, options.samematch, options.fixed, options.verbose
    )
    write_to_spreadsheet(teams.iloc[:20000], options.output)


if __name__ == "__main__":
    main()
