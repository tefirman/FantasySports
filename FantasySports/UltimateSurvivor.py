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
import sys
import datetime
import numpy as np
import sportsref_nfl as sr
import optparse
from pandas.tseries.holiday import USFederalHolidayCalendar
cal = USFederalHolidayCalendar()

class USP:
    def __init__(self, season: int = datetime.datetime.now().year, schedule_loc: str = None, picks_loc: str = None, limit: int = 1000, num_sims: int = 1000):
        self.season = season
        self.load_probs(schedule_loc)
        self.load_picks(picks_loc)
        self.week = int(self.picks.columns[-1].split('_')[-1][:-1]) + 1 if self.picks.shape[1] > 1 else 1
        self.best_combos(limit)
        self.season_sims(num_sims)

    def load_probs(self, schedule_loc: str = None, first: int = 1, last: int = 17) -> pd.DataFrame:
        """
        Loads win probabilities for every matchup in the current season.

        Args:
            schedule_loc (str, optional): location of schedule csv, defaults to "NFLSchedule.csv".
            first (int, optional): first week of interest, defaults to 1.
            last (int, optional): last week of interest, defaults to 17.
        """
        if schedule_loc is None:
            schedule_loc = "NFLSchedule.csv"
        if os.path.exists(schedule_loc):
            self.schedule = pd.read_csv(schedule_loc)
        else:
            self.schedule = pd.DataFrame(columns=["season"])
        if self.season not in self.schedule.season.unique():
            # Needs to update with new results...
            s = sr.Schedule(self.season - 8,self.season,False,True,False)
            self.schedule = s.schedule.copy()
            self.schedule.to_csv(schedule_loc,index=False)
        self.schedule = self.schedule.loc[self.schedule.season == datetime.datetime.now().year].reset_index(drop=True)
        self.schedule.loc[self.schedule.score1 > self.schedule.score2,'elo_prob1'] = 1.0
        self.schedule.loc[self.schedule.score1 > self.schedule.score2,'elo_prob2'] = 0.0
        self.schedule.loc[self.schedule.score1 < self.schedule.score2,'elo_prob1'] = 0.0
        self.schedule.loc[self.schedule.score1 < self.schedule.score2,'elo_prob2'] = 1.0
        self.schedule.loc[self.schedule.score1 == self.schedule.score2,'elo_prob1'] = 0.0
        self.schedule.loc[self.schedule.score1 == self.schedule.score2,'elo_prob2'] = 0.0
        self.probs = pd.concat([self.schedule[['week_num','game_date','team1_abbrev','elo_prob1']]\
        .rename(columns={'week_num':'week','team1_abbrev':'team','elo_prob1':'prob'}),\
        self.schedule[['week_num','game_date','team2_abbrev','elo_prob2']]\
        .rename(columns={'week_num':'week','team2_abbrev':'team','elo_prob2':'prob'})],ignore_index=True)
        self.probs = self.probs.loc[(self.probs.week >= first) & (self.probs.week <= last)].reset_index(drop=True)
        try:
            self.probs.game_date = pd.to_datetime(self.probs.game_date, format="%Y-%m-%d")
        except:
            self.probs.game_date = pd.to_datetime(self.probs.game_date, format="%m/%d/%y") # Accounting for manual updates to schedule csv... Thanks Excel...
        self.thanksgiving = cal.holidays(start=str(datetime.datetime.now().year) + '-11-15', end=str(datetime.datetime.now().year) + '-12-01').to_pydatetime()[0]
        self.tg_week = self.probs.loc[self.probs.game_date == self.thanksgiving,'week'].unique()[0]

    def load_picks(self, picks_loc: str = None) -> pd.DataFrame:
        """
        Parses actual picks made by each player from the weekly results spreadsheet.

        Args:
            picks_loc (str, optional): location of the weekly results spreadsheet, defaults to "{YEAR} USP Weekly Picks.xlsx".
        """
        if picks_loc is None:
            picks_loc = "{} USP Weekly Picks.xlsx".format(self.season)
        if not os.path.exists(picks_loc):
            print("Can't find Ultimate Surivor picks at specified location... Try again...")
            sys.exit(0)
        self.picks = pd.read_excel(picks_loc, sheet_name="Season", skiprows=2)
        num_entries = self.picks.loc[self.picks.Player == "Total Picks"].index[0] - 1
        self.picks = self.picks.iloc[:num_entries].reset_index(drop=True)
        ind = 0
        while not self.picks[self.picks.columns[ind]].isnull().all():
            ind += 1
        self.picks = self.picks[self.picks.columns[:ind]]
        for col in self.picks.columns:
            if type(col) == int:
                self.picks = self.picks.rename(columns={col:"team_" + str(col) + "a"})
            elif str(col).endswith(".1"):
                self.picks = self.picks.rename(columns={col:"team_" + col[:-2] + "b"})
            elif col == "Giving":
                self.picks = self.picks.rename(columns={col:"team_" + str(self.tg_week) + "c"})
        team_names = self.schedule.team1_abbrev.unique().tolist()
        translation = {"BAL":"RAV","KC":"KAN","JAC":"JAX","NO":"NOR","SF":"SFO",\
        "TB":"TAM","IND":"CLT","LAC":"SDG","GB":"GNB","HOU":"HTX","TEN":"OTI",\
        "ARI":"CRD","LAR":"RAM","LV":"RAI","NE":"NWE"}
        for col in self.picks.columns:
            if col == "Player":
                continue
            for team_name in translation:
                self.picks[col] = self.picks[col].str.replace(team_name,translation[team_name])
            if (~self.picks[col].isin(team_names) & ~self.picks[col].isnull()).any():
                print(self.picks.loc[~self.picks[col].isin(team_names) & ~self.picks[col].isnull(),col].unique())

    def best_combos(self, limit: int = 1000) -> pd.DataFrame:
        """
        Identifies the best combinations of picks for the rest of the season based on 538 win probabilities.

        Args:
            limit (int, optional): maximum number of pick combinations to retain between each iteration, defaults to 1000.
        """
        probs_tg = self.probs.loc[self.probs.game_date == self.thanksgiving].reset_index(drop=True)
        winners = self.probs.loc[self.probs.prob == 1].reset_index(drop=True)
        self.picks["points_so_far"] = 0.0
        for week in winners.week.unique():
            self.picks.loc[self.picks["team_{}a".format(week)].isin(winners.loc[winners.week == week,'team'].tolist()),'points_so_far'] += 1.0
            if week%2 == 0:
                self.picks.loc[self.picks["team_{}b".format(week)].isin(winners.loc[winners.week == week,'team'].tolist()),'points_so_far'] += 1.0
            if week == probs_tg.week.unique()[0]:
                self.picks.loc[self.picks["team_{}c".format(week)].isin(winners.loc[winners.week == week,'team'].tolist()),'points_so_far'] += 1.0
        self.probs = self.probs.loc[(self.probs.prob > 0) & (self.probs.prob < 1)].reset_index(drop=True)
        self.probs['dummy'] = 1
        if self.picks.shape[0] == 0:
            self.combos = pd.DataFrame({"dummy":[1],"Player":["Best"]})
        else:
            self.combos = self.picks.copy()
            self.combos['dummy'] = 1
        for week in range(self.probs.week.min(),self.probs.week.max() + 1):
            print("Week {}, {}".format(week,datetime.datetime.now()))
            self.combos = pd.merge(left=self.combos,right=self.probs.loc[(self.probs.week == week) & (self.probs.prob >= 0.5),['dummy','team','prob']]\
            .rename(columns={'team':f'team_{week}a','prob':f'prob_{week}a'}),how='inner',on='dummy')
            if week%2 == 0:
                self.combos = pd.merge(left=self.combos,right=self.probs.loc[(self.probs.week == week) & (self.probs.prob >= 0.5),['dummy','team','prob']]\
                .rename(columns={'team':f'team_{week}b','prob':f'prob_{week}b'}),how='inner',on='dummy')
                self.combos = self.combos.loc[self.combos[f'team_{week}a'] < self.combos[f'team_{week}b']].reset_index(drop=True)
            team_cols = [team for team in self.combos.columns if team.startswith('team_')]
            self.combos = self.combos.loc[self.combos[team_cols].nunique(axis=1) >= len(team_cols) - int(week >= 12)].reset_index(drop=True)
            self.combos['tot_prob'] = self.combos[[team for team in self.combos.columns if team.startswith('prob_')]].sum(axis=1)
            self.combos = self.combos.sort_values(by='tot_prob',ascending=False,ignore_index=True).groupby('Player').head(limit).reset_index(drop=True)
            if week == probs_tg.week.unique()[0]: # Thanksgiving
                self.combos = pd.merge(left=self.combos,right=self.probs.loc[(self.probs.week == week) & (self.probs.prob >= 0.5),['dummy','team','prob']]\
                .rename(columns={'team':f'team_{week}c','prob':f'prob_{week}c'}),how='inner',on='dummy')
                if week%2 == 1:
                    self.combos.rename(columns={f'team_{week}c':f'team_{week}b'},inplace=True)
                    self.combos = self.combos.loc[self.combos[f'team_{week}a'].isin(probs_tg.team.tolist()) \
                    | self.combos[f'team_{week}b'].isin(probs_tg.team.tolist())].reset_index(drop=True)
                else:
                    self.combos = self.combos.loc[self.combos[f'team_{week}b'] < self.combos[f'team_{week}c']].reset_index(drop=True)
                    self.combos = self.combos.loc[self.combos[f'team_{week}a'].isin(probs_tg.team.tolist()) \
                    | self.combos[f'team_{week}b'].isin(probs_tg.team.tolist()) \
                    | self.combos[f'team_{week}c'].isin(probs_tg.team.tolist())].reset_index(drop=True)
                team_cols = [team for team in self.combos.columns if team.startswith('team_')]
                self.combos = self.combos.loc[self.combos[team_cols].nunique(axis=1) >= len(team_cols) - int(week >= 12)].reset_index(drop=True)
                self.combos['tot_prob'] = self.combos[[team for team in self.combos.columns if team.startswith('prob_')]].sum(axis=1)
                self.combos = self.combos.sort_values(by='tot_prob',ascending=False,ignore_index=True).groupby('Player').head(limit).reset_index(drop=True)
        del self.probs['dummy'], self.combos['dummy']
        self.combos['projected_points'] = self.combos["tot_prob"] + self.combos["points_so_far"]
        self.combos = self.combos.sort_values(by="projected_points",ascending=False,ignore_index=True)
        self.best_combos = self.combos.drop_duplicates(subset=['Player'],keep='first')

    def season_sims(self, num_sims: int = 1000):
        best_picks = pd.DataFrame(columns=["week","Player","pick"])
        for col in self.best_combos.columns:
            if col.startswith('team_'):
                best_picks = pd.concat([best_picks,self.best_combos[['Player',col]].rename(columns={col:'pick'})],ignore_index=True)
                best_picks.week = best_picks.week.fillna(int(col.split('_')[-1][:-1]))
        sched_sims = pd.concat(num_sims*[self.schedule[['week','team1_abbrev','elo_prob1','team2_abbrev','elo_prob2']]],ignore_index=True)
        sched_sims['num_sim'] = sched_sims.index//self.schedule.shape[0]
        sched_sims['sim'] = np.random.rand(sched_sims.shape[0])
        home_winner = sched_sims.sim <= sched_sims.elo_prob1
        sched_sims.loc[home_winner,'pick'] = sched_sims.loc[home_winner,'team1_abbrev']
        sched_sims.loc[~home_winner,'pick'] = sched_sims.loc[~home_winner,'team2_abbrev']
        pick_sims = pd.merge(left=best_picks,right=sched_sims[['num_sim','week','pick']],how='inner',on=['week','pick'])
        standings = pick_sims.groupby(['num_sim','Player']).size().to_frame('points').reset_index()
        standings['tiebreaker'] = np.random.rand(standings.shape[0])
        standings = standings.sort_values(by=['num_sim','points','tiebreaker'],ascending=[True,False,False],ignore_index=True)
        standings['place'] = standings.index%self.best_combos.shape[0] + 1
        standings['playoffs'] = (standings.place <= 8).astype(float)
        standings['winner'] = (standings.place == 1).astype(float)
        standings['runner_up'] = (standings.place == 2).astype(float)
        standings['third'] = (standings.place == 3).astype(float)
        standings['earnings'] = 100.0*standings.winner + 75.0*standings.runner_up + 50.0*standings.third + (715.0/8.0)*standings.playoffs
        standings = standings.groupby('Player').mean().reset_index()
        self.best_combos = pd.merge(left=self.best_combos,right=standings[['Player','winner','runner_up','third','playoffs','earnings']],how='inner',on='Player')
        self.best_combos = self.best_combos.sort_values(by=['earnings','projected_points'],ascending=False,ignore_index=True)

    def write_to_spreadsheet(self, name: str, filename: str = "UltimateSurvivorCombos.xlsx"):
        """
        Writes final results to an excel spreadsheet in three tabs:
            - Standings: optimal pick combinations for each contestant ranked by projected points.
            - This Week: user's optimal picks for the current week.
            - Next 3 Weeks: user's optimal picks for the next three weeks.

        Args:
            name (str): name of the contestant of interest.
            filename (str, optional): where to save the results spreadsheet, defaults to "UltimateSurvivorCombos.xlsx".
        """
        writer = pd.ExcelWriter(filename,engine="xlsxwriter")
        writer.book.add_format({"align": "vcenter"})
        future_cols = [col.replace("prob_","team_") for col in self.combos.columns if col.startswith("prob_")]
        hidden_cols = [col for col in self.combos.columns if col.startswith("team_") and col not in future_cols]
        writer = excel_autofit(self.best_combos[["Player"] + [team for team in self.best_combos.columns if team.startswith('team_')] + \
        ["points_so_far","projected_points",'winner','runner_up','third','playoffs','earnings']], "Standings", writer, hidden_cols)
        writer.sheets["Standings"].freeze_panes(1, 1)
        current_week = future_cols[0][:-1]
        my_picks = self.combos.loc[self.combos.Player.isin([name])].reset_index(drop=True)
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

def main():
    # Initializing input arguments
    parser = optparse.OptionParser()
    parser.add_option(
        "--season",
        action="store",
        dest="season",
        default=datetime.datetime.now().year,
        help="season of interest for the Ultimate Surivor Pool",
    )
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
        "--num_sims",
        action="store",
        type="int",
        dest="num_sims",
        default=1000,
        help="number of simulations to run when assessing picks",
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
    usp = USP(options.season, options.schedule, options.picks, options.limit, options.num_sims)

    # Writing results to spreadsheet
    usp.write_to_spreadsheet(options.name, "{}UltimateSurvivorCombos_Week{}.xlsx".format(options.output,usp.week))


if __name__ == "__main__":
    main()


