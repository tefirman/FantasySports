#!/usr/bin/env python
# -*-coding:utf-8 -*-
'''
@File    :   UltimateSurvivor.py
@Time    :   2023/10/11 15:14:43
@Author  :   Taylor Firman
@Version :   1.0
@Contact :   tefirman@gmail.com
@Desc    :   Simulation tools for an "Ultimate Survivor Pool" where every week,
each player picks a team to win and cannot pick them again for the rest of the season. 
However, unlike other survivor/elimination-style football pools, you aren't eliminated 
if you don't pick a winner, you just don't get a win for that week. The player with 
the most wins at the end of the season wins the pool. To increase the number of picks 
and therefore increase complexity, odd weeks get one pick, even weeks get two picks, 
and Thanksgiving day gets an extra pick.
'''

import pandas as pd
import os
import datetime
from util import sportsref_nfl as sr
import optparse
from pandas.tseries.holiday import USFederalHolidayCalendar
cal = USFederalHolidayCalendar()

def load_probs(schedule_loc: str = "NFLSchedule.csv", first: int = 1, last: int = 17) -> pd.DataFrame:
    """
    Loads win probabilities for every matchup in the current season.

    Args:
        schedule_loc (str, optional): location of schedule csv, defaults to "NFLSchedule.csv".
        first (int, optional): first week of interest, defaults to 1.
        last (int, optional): last week of interest, defaults to 17.

    Returns:
        pd.DataFrame: dataframe containing win probabilities for every matchup in the current season.
    """
    if os.path.exists(schedule_loc):
        schedule = pd.read_csv(schedule_loc)
    else:
        s = sr.Schedule(2015,datetime.datetime.now().year,False,True,False)
        schedule = s.schedule.copy()
        schedule.to_csv(schedule_loc,index=False)
    schedule = schedule.loc[schedule.season == datetime.datetime.now().year].reset_index(drop=True)
    schedule.loc[schedule.score1 > schedule.score2,'elo_prob1'] = 1.0
    schedule.loc[schedule.score1 > schedule.score2,'elo_prob2'] = 0.0
    schedule.loc[schedule.score1 < schedule.score2,'elo_prob1'] = 0.0
    schedule.loc[schedule.score1 < schedule.score2,'elo_prob2'] = 1.0
    schedule.loc[schedule.score1 == schedule.score2,'elo_prob1'] = 0.0
    schedule.loc[schedule.score1 == schedule.score2,'elo_prob2'] = 0.0
    probs = pd.concat([schedule[['week_num','game_date','team1_abbrev','elo_prob1']]\
    .rename(columns={'week_num':'week','team1_abbrev':'team','elo_prob1':'prob'}),\
    schedule[['week_num','game_date','team2_abbrev','elo_prob2']]\
    .rename(columns={'week_num':'week','team2_abbrev':'team','elo_prob2':'prob'})],ignore_index=True)
    probs = probs.loc[(probs.week >= first) & (probs.week <= last)].reset_index(drop=True)
    probs.game_date = pd.to_datetime(probs.game_date,infer_datetime_format=True)
    return probs

def load_picks(picks_loc: str = str(datetime.datetime.now().year) + " USP Weekly Picks.xlsx") -> pd.DataFrame:
    """
    Parses actual picks made by each player from the weekly results spreadsheet.

    Args:
        picks_loc (str, optional): location of the weekly results spreadsheet, defaults to "{YEAR} USP Weekly Picks.xlsx".

    Returns:
        pd.DataFrame: dataframe containing the actual picks every player made for the season thus far.
    """
    if not os.path.exists(picks_loc):
        return pd.DataFrame() # Not sure what will happen here to be honest...
    picks = pd.read_excel(picks_loc, sheet_name="Season", skiprows=2)
    num_entries = picks.loc[picks.Player == "Total Picks"].index[0] - 1
    picks = picks.iloc[:num_entries].reset_index(drop=True)
    ind = 0
    while not picks[picks.columns[ind]].isnull().all():
        ind += 1
    picks = picks[picks.columns[:ind]]
    for col in picks.columns:
        if type(col) == int:
            picks = picks.rename(columns={col:"team_" + str(col) + "a"})
        elif str(col).endswith(".1"):
            picks = picks.rename(columns={col:"team_" + col[:-2] + "b"})
        elif col == "Giving":
            picks = picks.rename(columns={col:"team_" + str(col) + "c"})
    team_names = ['KAN', 'CLT', 'RAV', 'MIN', 'WAS', 'NOR', 'CLE', 'PIT', \
    'ATL', 'NWE', 'CHI', 'SEA', 'SDG', 'DEN', 'NYG', 'NYJ', 'PHI', 'OTI', \
    'JAX', 'DET', 'HTX', 'CIN', 'TAM', 'BUF', 'CRD', 'RAM', 'DAL', 'CAR', \
    'SFO', 'MIA', 'GNB', 'RAI']
    translation = {"BAL":"RAV","KC":"KAN","JAC":"JAX","NO":"NOR","SF":"SFO",\
    "TB":"TAM","IND":"CLT","LAC":"SDG","GB":"GNB","HOU":"HTX","TEN":"OTI",\
    "ARI":"CRD","LAR":"RAM","LV":"RAI"}
    for col in picks.columns:
        if col == "Player":
            continue
        for team_name in translation:
            picks[col] = picks[col].str.replace(team_name,translation[team_name])
        if (~picks[col].isin(team_names)).any():
            print(picks.loc[~picks[col].isin(team_names),col].unique())
    return picks

def best_combos(probs: pd.DataFrame, picks: pd.DataFrame = pd.DataFrame(), limit: int = 1000) -> pd.DataFrame:
    """
    Identifies the best combinations of picks for the rest of the season based on 538 win probabilities.

    Args:
        probs (pd.DataFrame): win probabilities for every matchup remaining in the season.
        picks (pd.DataFrame, optional): dataframe containing details about picks that have already been made, defaults to pd.DataFrame().
        limit (int, optional): maximum number of pick combinations to retain between each iteration, defaults to 1000.

    Returns:
        pd.DataFrame: dataframe containing the best pick combinations for the rest of season.
    """
    thanksgiving = cal.holidays(start=str(datetime.datetime.now().year) + '-11-15', end=str(datetime.datetime.now().year) + '-12-01').to_pydatetime()[0]
    probs_tg = probs.loc[probs.game_date == thanksgiving].reset_index(drop=True)
    winners = probs.loc[probs.prob == 1].reset_index(drop=True)
    picks["points_so_far"] = 0.0
    for week in winners.week.unique():
        picks.loc[picks["team_{}a".format(week)].isin(winners.loc[winners.week == week,'team'].tolist()),'points_so_far'] += 1.0
        if week%2 == 0:
            picks.loc[picks["team_{}b".format(week)].isin(winners.loc[winners.week == week,'team'].tolist()),'points_so_far'] += 1.0
        if week == probs_tg.week.unique()[0]:
            picks.loc[picks["team_{}c".format(week)].isin(winners.loc[winners.week == week,'team'].tolist()),'points_so_far'] += 1.0
    probs = probs.loc[(probs.prob > 0) & (probs.prob < 1)].reset_index(drop=True)
    probs['dummy'] = 1
    if picks.shape[0] == 0:
        combos = pd.DataFrame({"dummy":[1],"Player":["Best"]})
    else:
        combos = picks.copy()
        combos['dummy'] = 1
    for week in range(probs.week.min(),probs.week.max() + 1):
        print("Week {}, {}".format(week,datetime.datetime.now()))
        combos = pd.merge(left=combos,right=probs.loc[(probs.week == week) & (probs.prob >= 0.5),['dummy','team','prob']]\
        .rename(columns={'team':f'team_{week}a','prob':f'prob_{week}a'}),how='inner',on='dummy')
        if week%2 == 0:
            combos = pd.merge(left=combos,right=probs.loc[(probs.week == week) & (probs.prob >= 0.5),['dummy','team','prob']]\
            .rename(columns={'team':f'team_{week}b','prob':f'prob_{week}b'}),how='inner',on='dummy')
            combos = combos.loc[combos[f'team_{week}a'] < combos[f'team_{week}b']].reset_index(drop=True)
        team_cols = [team for team in combos.columns if team.startswith('team_')]
        combos = combos.loc[combos[team_cols].nunique(axis=1) >= len(team_cols) - int(week >= 12)].reset_index(drop=True)
        combos['tot_prob'] = combos[[team for team in combos.columns if team.startswith('prob_')]].sum(axis=1)
        combos = combos.sort_values(by='tot_prob',ascending=False,ignore_index=True).groupby('Player').head(limit).reset_index(drop=True)
        if week == probs_tg.week.unique()[0]: # Thanksgiving
            combos = pd.merge(left=combos,right=probs.loc[(probs.week == week) & (probs.prob >= 0.5),['dummy','team','prob']]\
            .rename(columns={'team':f'team_{week}c','prob':f'prob_{week}c'}),how='inner',on='dummy')
            combos = combos.loc[combos[f'team_{week}b'] < combos[f'team_{week}c']].reset_index(drop=True)
            combos = combos.loc[combos[f'team_{week}a'].isin(probs_tg.team.tolist()) \
            | combos[f'team_{week}b'].isin(probs_tg.team.tolist()) \
            | combos[f'team_{week}c'].isin(probs_tg.team.tolist())].reset_index(drop=True)
            team_cols = [team for team in combos.columns if team.startswith('team_')]
            combos = combos.loc[combos[team_cols].nunique(axis=1) >= len(team_cols) - int(week >= 12)].reset_index(drop=True)
            combos['tot_prob'] = combos[[team for team in combos.columns if team.startswith('prob_')]].sum(axis=1)
            combos = combos.sort_values(by='tot_prob',ascending=False,ignore_index=True).groupby('Player').head(limit).reset_index(drop=True)
    del probs['dummy'], combos['dummy']
    combos['projected_points'] = combos["tot_prob"] + combos["points_so_far"]
    return combos

def excel_autofit(df: pd.DataFrame, name: str, writer: pd.ExcelWriter, hidden: list = []) -> pd.ExcelWriter:
    """
    Writes the provided dataframe to a new tab in an excel spreadsheet 
    with the columns autofitted and autoformatted.

    Args:
        df (pd.DataFrame): dataframe to print to the excel spreadsheet.
        name (str): name of the new tab to be added.
        writer (pd.ExcelWriter): ExcelWriter object representing the excel spreadsheet.
        hidden (list): list of column names that should be hidden in the excel spreadsheet.

    Returns:
        pd.ExcelWriter: same excel spreadsheet provided originally with the new tab added.
    """
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
        if col == "Earnings":
            writer.sheets[name].set_column(idx, idx, max_len, m, {"hidden": col in hidden})
        else:
            writer.sheets[name].set_column(idx, idx, max_len, f, {"hidden": col in hidden})
    writer.sheets[name].autofilter(
        "A1:"
        + (
            chr(64 + (df.shape[1] - 1) // 26) + chr(65 + (df.shape[1] - 1) % 26)
        ).replace("@", "")
        + str(df.shape[0] + 1)
    )
    return writer

def write_to_spreadsheet(combos: pd.DataFrame, name: str, filename: str = "UltimateSurvivorCombos.xlsx"):
    """
    Writes final results to an excel spreadsheet in three tabs:
        - Standings: optimal pick combinations for each contestant ranked by projected points.
        - This Week: user's optimal picks for the current week.
        - Next 3 Weeks: user's optimal picks for the next three weeks.

    Args:
        combos (pd.DataFrame): optimal pick combinations for each contestant ranked by projected points.
        name (str): name of the contestant of interest.
        filename (str, optional): where to save the results spreadsheet, defaults to "UltimateSurvivorCombos.xlsx".
    """
    writer = pd.ExcelWriter(filename,engine="xlsxwriter")
    writer.book.add_format({"align": "vcenter"})
    future_cols = [col.replace("prob_","team_") for col in combos.columns if col.startswith("prob_")]
    hidden_cols = [col for col in combos.columns if col.startswith("team_") and col not in future_cols]
    writer = excel_autofit(combos[["Player"] + [team for team in combos.columns if team.startswith('team_')] + \
    ["points_so_far","projected_points"]].sort_values(by="projected_points",ascending=False)\
    .drop_duplicates(subset=['Player'],keep='first'), "Standings", writer, hidden_cols)
    writer.sheets["Standings"].freeze_panes(1, 1)
    current_week = future_cols[0][:-1]
    my_picks = combos.loc[combos.Player.isin([name])].reset_index(drop=True)
    teams = [team for team in my_picks.columns if team in [current_week + 'a',current_week + 'b',current_week + 'c']]
    this_week_pts = my_picks.groupby(teams).projected_points.mean().reset_index()
    this_week_freq = my_picks.groupby(teams).size().to_frame('freq').reset_index()
    this_week_freq.freq /= my_picks.shape[0]
    this_week = pd.merge(left=this_week_pts,right=this_week_freq,how='inner',on=teams).sort_values(by='freq',ascending=False)
    writer = excel_autofit(this_week, "This Week", writer)
    start_week = int(current_week.split('_')[-1])
    for week in range(min(start_week + 1,18),min(start_week + 3,18)):
        current_week = 'team_' + str(week)
        teams += [team for team in my_picks.columns if team in [current_week + 'a',current_week + 'b',current_week + 'c']]
    three_week_pts = my_picks.groupby(teams).projected_points.mean().reset_index()
    three_week_freq = my_picks.groupby(teams).size().to_frame('freq').reset_index()
    three_week_freq.freq /= my_picks.shape[0]
    three_week = pd.merge(left=three_week_pts,right=three_week_freq,how='inner',on=teams).sort_values(by='freq',ascending=False)
    writer = excel_autofit(three_week, "Next 3 Weeks", writer)
    writer.close()

def main():
    # Initializing input arguments
    parser = optparse.OptionParser()
    parser.add_option(
        "--schedule",
        action="store",
        dest="schedule",
        default="NFLSchedule.csv",
        help="location of schedule projections csv based on 538 strategies",
    )
    parser.add_option(
        "--picks",
        action="store",
        dest="picks",
        default=str(datetime.datetime.now().year) + " USP Weekly Picks.xlsx",
        help="location of spreadsheet containing picks already made",
    )
    parser.add_option(
        "--name",
        action="store",
        dest="name",
        default="Taylor",
        help="name of the contestant to focus on",
    )
    parser.add_option(
        "--limit",
        action="store",
        type="int",
        dest="limit",
        default=1000,
        help="number of top lineups to keep during each merge for memory purposes",
    )
    parser.add_option(
        "--output",
        action="store",
        dest="output",
        default="",
        help="where to save the final projections spreadsheet",
    )
    options = parser.parse_args()[0]

    # Simulating Ultimate Survivor Pool contest
    picks = load_picks(options.picks)
    probs = load_probs(options.schedule)
    combos = best_combos(probs, picks, options.limit)

    # Writing results to spreadsheet
    write_to_spreadsheet(combos, options.name, "{}UltimateSurvivorCombos_Week{}.xlsx".format(options.output,int(picks.columns[-2].split('_')[-1][:-1]) + 1))


if __name__ == "__main__":
    main()


