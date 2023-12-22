#!/usr/bin/env python
# -*-coding:utf-8 -*-
'''
@File    :   ConfidencePickEm.py
@Time    :   2023/10/11 13:19:41
@Author  :   Taylor Firman
@Version :   1.0
@Contact :   tefirman@gmail.com
@Desc    :   Simulation tools for a Confidence Pick'em league where every player picks
a winner for each game of the week and assigns a point value based on how confident 
they are in that winner (between 1 and the number of games). For each correct pick, 
the player receives the amount of points assigned to that game and the player with 
the most points that week wins.
'''

from util import sportsref_nfl as sr
import pandas as pd
import os
import datetime
import numpy as np
import optparse

def load_pick_probs(week: int) -> pd.DataFrame:
    """
    Parses pick probabilities from a direct copy of the "Pick Distribution" tab of Yahoo's Pick'em GUI.
    Literally just Ctrl+A, then copy paste into a plain text file. Sadly, the raw html doesn't contain the required data.

    Args:
        week (int): week of the NFL season to load pick probabilities for.

    Returns:
        pd.DataFrame: dataframe containing the percentage of players picking each team in every matchup for that week.
    """
    nfl_teams = pd.read_csv("https://raw.githubusercontent.com/tefirman/FantasySports/main/res/football/team_abbrevs.csv")
    tempData = open("PickEmDistribution_Week{}.txt".format(week),'r')
    raw_str = tempData.read()
    tempData.close()
    games = raw_str.split("Spread and Confidence\n")[-1].split('\n\n')[0].split('\tFavorite\t \n')
    fave = [game.split('\n')[7].split('\t')[0] for game in games]
    fave = [nfl_teams.loc[nfl_teams.yahoo.str.upper().isin([team]),'real_abbrev'].values[0] for team in fave]
    fave_pct = [float(game.split('\n')[3].replace('%',''))/100.0 for game in games]
    fave_pts = [float(game.split('\n')[8].split('\t')[0]) for game in games]
    underdog = [game.split('\n')[7].split('\t')[-1] for game in games]
    underdog = [nfl_teams.loc[nfl_teams.yahoo.str.upper().isin([team]),'real_abbrev'].values[0] for team in underdog]
    underdog_pct = [float(game.split('\n')[6].replace('%',''))/100.0 for game in games]
    underdog_pts = [float(game.split('\n')[8].split('\t')[-1]) for game in games]
    home_fave = ['@' in game.split('\n')[1] for game in games]
    pick_probs = pd.DataFrame({'fave_abbrev':fave,'underdog_abbrev':underdog,'fave_pick_prob':fave_pct,\
    'underdog_pick_prob':underdog_pct,'fave_pick_pts':fave_pts,'underdog_pick_pts':underdog_pts,'home_fave':home_fave})
    pick_probs.loc[pick_probs.home_fave,'team1_abbrev'] = pick_probs.loc[pick_probs.home_fave,'fave_abbrev']
    pick_probs.loc[pick_probs.home_fave,'pick_prob1'] = pick_probs.loc[pick_probs.home_fave,'fave_pick_prob']
    pick_probs.loc[pick_probs.home_fave,'pick_pts1'] = pick_probs.loc[pick_probs.home_fave,'fave_pick_pts']
    pick_probs.loc[pick_probs.home_fave,'team2_abbrev'] = pick_probs.loc[pick_probs.home_fave,'underdog_abbrev']
    pick_probs.loc[pick_probs.home_fave,'pick_prob2'] = pick_probs.loc[pick_probs.home_fave,'underdog_pick_prob']
    pick_probs.loc[pick_probs.home_fave,'pick_pts2'] = pick_probs.loc[pick_probs.home_fave,'underdog_pick_pts']
    pick_probs.loc[~pick_probs.home_fave,'team1_abbrev'] = pick_probs.loc[~pick_probs.home_fave,'underdog_abbrev']
    pick_probs.loc[~pick_probs.home_fave,'pick_prob1'] = pick_probs.loc[~pick_probs.home_fave,'underdog_pick_prob']
    pick_probs.loc[~pick_probs.home_fave,'pick_pts1'] = pick_probs.loc[~pick_probs.home_fave,'underdog_pick_pts']
    pick_probs.loc[~pick_probs.home_fave,'team2_abbrev'] = pick_probs.loc[~pick_probs.home_fave,'fave_abbrev']
    pick_probs.loc[~pick_probs.home_fave,'pick_prob2'] = pick_probs.loc[~pick_probs.home_fave,'fave_pick_prob']
    pick_probs.loc[~pick_probs.home_fave,'pick_pts2'] = pick_probs.loc[~pick_probs.home_fave,'fave_pick_pts']
    pick_probs.pick_pts1 = pick_probs.pick_pts1*1.131 - 0.259
    pick_probs.pick_pts2 = pick_probs.pick_pts2*1.131 - 0.259
    return pick_probs[['team1_abbrev','team2_abbrev','pick_prob1','pick_prob2','pick_pts1','pick_pts2']]

def load_picks(week: int, schedule: pd.DataFrame) -> pd.DataFrame:
    """
    Parses actual picks made by each player from a direct copy of the "Group Picks" tab of Yahoo's Pick'em GUI.
    Literally just Ctrl+A, then copy paste into a plain text file. Sadly, the raw html doesn't contain the required data.

    Args:
        week (int): week of the NFL season to load actual picks.

    Returns:
        pd.DataFrame: dataframe containing the actual picks every player made for that week.
    """
    if os.path.exists("ActualConfidencePicks_Week{}.txt".format(week)):
        tempData = open("ActualConfidencePicks_Week{}.txt".format(week),'r')
        raw_str = tempData.read()
        matchup_vals = raw_str.split('Favored\t')[-1].split('\nTeam Name\tPoints')[0].split('\n')[::2]
        favorites = matchup_vals[0].split('\t')[:-1]
        underdogs = matchup_vals[1].split('\t')[1:-1]
        pick_vals = raw_str.split('Team Name\tPoints\n')[-1].split("\nYahoo! Sports")[0].replace('\n(','\r(').split('\n')
        tempData.close()
    else:
        favorites,underdogs,pick_vals = [],[],[]
    matchups = pd.DataFrame({"favorite":favorites,"underdog":underdogs})
    matchups['matchup_ind'] = matchups.index
    actual = pd.DataFrame(columns=["player","pick"])
    for vals in pick_vals:
        player = vals.split('\t')[0]
        picks = vals.split('\t')[1:-1]
        actual = pd.concat([actual,pd.DataFrame({'player':[player]*len(picks),'pick':picks})],ignore_index=True)
    actual['points_bid'] = actual.pick.str.split('\r').str[-1].str[1:-1]
    actual.loc[actual.points_bid == '','points_bid'] = '0'
    actual.points_bid = actual.points_bid.astype(int)
    actual['pick'] = actual.pick.str.split('\r').str[0]
    actual.loc[actual.pick.isin(['--',' ']),'pick'] = 'UNK'
    actual['matchup_ind'] = actual.index%matchups.shape[0]
    for player in actual.player.unique():
        val = 0
        while ((actual.player == player) & (actual.points_bid == 0)).any():
            while ((actual.player == player) & (actual.points_bid == val)).any():
                val += 1
            bad_inds = actual.loc[(actual.player == player) & (actual.points_bid == 0)].index
            actual.loc[bad_inds[0],'points_bid'] = val
    actual = pd.merge(left=actual,right=matchups,how='inner',on='matchup_ind')
    nfl_teams = pd.read_csv("https://raw.githubusercontent.com/tefirman/FantasySports/main/res/football/team_abbrevs.csv")
    for col in ['pick','favorite','underdog']:
        actual = pd.merge(left=actual,right=nfl_teams[['yahoo','real_abbrev']].rename(columns={"yahoo":col}),how='left',on=col)
        actual.loc[~actual.real_abbrev.isnull(),col] = actual.loc[~actual.real_abbrev.isnull(),'real_abbrev']
        del actual['real_abbrev']
    if actual.shape[0] > 0:
        actual['matchup_abbrev'] = actual.apply(lambda x: ''.join(sorted([x['favorite'],x['underdog']])),axis=1)
        schedule['matchup_abbrev'] = schedule.apply(lambda x: ''.join(sorted([x['team1_abbrev'],x['team2_abbrev']])),axis=1)
        actual = pd.merge(left=actual,right=schedule.loc[~schedule.still_to_play,['matchup_abbrev']],how='inner',on='matchup_abbrev')
        del schedule['matchup_abbrev'], actual['matchup_abbrev'], actual['matchup_ind']
    my_picks = actual.loc[actual.player == "Firman's Educated Guesses"].reset_index(drop=True)
    my_picks["entry"] = 0.0
    actual = actual.loc[actual.player != "Firman's Educated Guesses"].reset_index(drop=True)
    actual["entry"] = actual.player.rank(method='dense')
    actual = pd.concat([my_picks,actual])
    return actual

def load_schedule(sched_loc: str = "NFLSchedule.csv", week: int = None, vegas: bool = False):
    if os.path.exists(sched_loc):
        schedule = pd.read_csv(sched_loc)
    else:
        s = sr.Schedule(2015,datetime.datetime.now().year,False,True,False)
        schedule = s.schedule.copy()
        schedule.to_csv(sched_loc,index=False)
    schedule = schedule.loc[schedule.season == datetime.datetime.now().year].reset_index(drop=True)
    if week is None:
        week = schedule.loc[schedule.pts_win.isnull(),'week'].min()
    schedule = schedule.loc[schedule.week == week].reset_index(drop=True)
    schedule['still_to_play'] = schedule.score1.isnull() & schedule.score2.isnull() & schedule.pts_win.isnull() & schedule.pts_lose.isnull()
    if vegas:
        veg_probs = load_vegas("Week{}Spreads.txt".format(week))
        if veg_probs is not None:
            veg_probs = veg_probs.rename(columns={"home_abbrev":"team1_abbrev",\
            "away_abbrev":"team2_abbrev","home_prob":"elo_prob1","away_prob":"elo_prob2"})
            del schedule['elo_prob1'], schedule['elo_prob2']
            schedule = pd.merge(left=schedule,right=veg_probs,how='inner',on=["team1_abbrev","team2_abbrev"])
    return schedule

def load_vegas(vegas_loc: str = None):
    # Checking that the spread data actually exists
    if os.path.exists(vegas_loc):
        tempData = open(vegas_loc,"r")
        raw_str = tempData.read().split('Upcoming\n')[-1].split('\nGame Info\nNFL odds guide')[0]
        tempData.close()
    else:
        print("Can't find Vegas spreads for this week... Skipping...")
        return None
    # Loading Vegas moneylines/spreads
    details = raw_str.split('\nGame Info\n')
    matchups = pd.DataFrame()
    for game in details:
        game_deets = game.split('\n')
        matchups = pd.concat([matchups,pd.DataFrame({"away_team":[game_deets[4].split('(')[0]],\
        "away_moneyline":[float(game_deets[6])],"away_spread":[float(game_deets[8])],\
        "home_team":[game_deets[13].split('(')[0]],"home_moneyline":[float(game_deets[15])],\
        "home_spread":[float(game_deets[17])]})],ignore_index=True)
    # Converting to probabilities
    home_fave = matchups.home_moneyline < 0
    matchups.loc[home_fave,'home_prob'] = abs(matchups.loc[home_fave,'home_moneyline'])/(100 + abs(matchups.loc[home_fave,'home_moneyline']))
    matchups.loc[~home_fave,'home_prob'] = 100/(100 + matchups.loc[~home_fave,'home_moneyline'])
    away_fave = matchups.away_moneyline < 0
    matchups.loc[away_fave,'away_prob'] = abs(matchups.loc[away_fave,'away_moneyline'])/(100 + abs(matchups.loc[away_fave,'away_moneyline']))
    matchups.loc[~away_fave,'away_prob'] = 100/(100 + matchups.loc[~away_fave,'away_moneyline'])
    matchups['norm_sum'] = matchups.home_prob + matchups.away_prob
    matchups.home_prob /= matchups.norm_sum
    matchups.away_prob /= matchups.norm_sum
    del matchups['norm_sum']
    # Converting team names to SportsRef abbreviations
    nfl_teams = pd.read_csv("https://raw.githubusercontent.com/tefirman/FantasySports/main/res/football/team_abbrevs.csv")
    for team in ['home','away']:
        matchups['name'] = matchups[team + '_team'].str.split(' ').str[:-1].apply(' '.join)
        matchups.loc[matchups.name.isin(['New York','Los Angeles']),'name'] = matchups.loc[matchups.name.isin(['New York','Los Angeles']),team + '_team']
        matchups = pd.merge(left=matchups,right=nfl_teams[["name","real_abbrev"]].rename(columns={"real_abbrev":team + "_abbrev"}),how='inner',on=['name'])
        del matchups['name']
    return matchups[['home_abbrev','home_prob','away_abbrev','away_prob']]

def simulate_picks(games: pd.DataFrame, picks: pd.DataFrame, num_sims: int = 1000, num_entries: int = 50) -> pd.DataFrame:
    """
    Simulates contestant picks for an entire Confidence Pick'em contest based on the parameters provided.

    Args:
        games (pd.DataFrame): dataframe containing details on each NFL matchup during the week of interest.
        picks (pd.DataFrame): dataframe containing details about picks that have already been made.
        num_sims (int, optional): number of simulations to perform, defaults to 1000.
        num_entries (int, optional): number of contestants in the group, defaults to 50.

    Returns:
        pd.DataFrame: dataframe containing simulated picks for each matchup and each contestant in each simulation.
    """
    sims = pd.concat(num_sims*num_entries*[games.loc[games.still_to_play]],ignore_index=True)
    sims['entry'] = sims.index%(games.still_to_play.sum()*num_entries)//games.still_to_play.sum()
    sims['num_sim'] = sims.index//(games.still_to_play.sum()*num_entries)
    sims = pd.merge(left=sims,right=picks,how='left',left_on=["entry","team1_abbrev"],right_on=["entry","pick"])
    sims = pd.merge(left=sims,right=picks,how='left',left_on=["entry","team2_abbrev"],right_on=["entry","pick"],suffixes=("","_2"))
    sims.loc[~sims['pick_2'].isnull(),"pick"] = sims.loc[~sims['pick_2'].isnull(),'pick_2']
    sims.loc[~sims['points_bid_2'].isnull(),"points_bid"] = sims.loc[~sims['points_bid_2'].isnull(),'points_bid_2']
    del sims['pick_2'], sims['points_bid_2'], sims['player'], sims['player_2'], sims['points_won'], sims['points_won_2']
    already_picked = sims.loc[~sims.pick.isnull()].reset_index(drop=True)
    sims = sims.loc[sims.pick.isnull()].reset_index(drop=True)
    sims['pick_sim'] = np.random.rand(sims.shape[0])
    home_pick = sims.pick_sim < sims.pick_prob1
    sims.loc[home_pick,'pick'] = sims.loc[home_pick,'team1_abbrev']
    sims.loc[~home_pick,'pick'] = sims.loc[~home_pick,'team2_abbrev']
    # sims.loc[home_pick,'pts_avg'] = 1.131*sims.loc[home_pick,'pick_pts1'] - 0.259
    # sims.loc[~home_pick,'pts_avg'] = 1.131*sims.loc[~home_pick,'pick_pts2'] - 0.259
    sims.loc[home_pick,'pts_avg'] = sims.loc[home_pick,'pick_pts1']
    sims.loc[~home_pick,'pts_avg'] = sims.loc[~home_pick,'pick_pts2']
    sims['rel_pts'] = sims['pts_avg']/games.shape[0]
    # sims['pts_stdev_true'] = (-0.441*sims['rel_pts']**2.0 + 0.446*sims['rel_pts'] + 0.097)*games.shape[0]
    sims['pts_stdev_true'] = (-0.5*sims['rel_pts']**2.0 + 0.519*sims['rel_pts'] + 0.08)*games.shape[0]
    sims['pts_stdev'] = sims['pts_stdev_true']*1.09 # Simulation fudge factor
    all_picks = pd.DataFrame({"entry":[val//games.shape[0] for val in range(games.shape[0]*num_entries)],\
    "points_bid":[val%games.shape[0] + 1 for val in range(games.shape[0]*num_entries)]})
    all_picks = pd.merge(left=all_picks,right=picks,how='left',on=['entry','points_bid'])
    all_picks = all_picks.loc[all_picks.pick.isnull()]
    # print(all_picks.groupby('entry').size().sort_values())
    # print(picks.loc[picks.entry.isin([15,18,25,31,35,46,53,29]),['player','entry']].drop_duplicates())
    if all_picks.entry.nunique() == num_entries:
        sims['points_bid_sim'] = sims.apply(lambda x: np.random.normal(x['pts_avg'],x['pts_stdev']),axis=1)
        sims = sims.sort_values(by=['num_sim','entry','points_bid_sim'],ascending=True)
        sims['points_bid'] = all_picks.points_bid.tolist()*num_sims
    # comparison = pd.merge(left=sims.groupby('pick').points_bid.mean().reset_index().rename(columns={"points_bid":"actual_avg"}),\
    # right=sims.groupby('pick').points_bid.std().reset_index().rename(columns={"points_bid":"actual_stdev"}),how='inner',on='pick')
    # comparison = pd.merge(left=comparison,right=sims.groupby('pick')[['pts_avg','pts_stdev','pts_stdev_true']].mean().reset_index(),how='inner',on='pick')
    # print(comparison)
    # print(comparison[['actual_avg','pts_avg','actual_stdev','pts_stdev','pts_stdev_true']].corr())
    # print("St. Dev. Mean Squared Error: " + str(sum((comparison.actual_stdev - comparison.pts_stdev_true)**2.0)))
    sims = pd.concat([sims,already_picked],ignore_index=True).sort_values(by=['num_sim','entry'],ascending=True)
    return sims

def add_my_picks(sims: pd.DataFrame, fixed: list = [], pick_pref: str = "best", point_pref: str = "best", prioritize: list = []) -> pd.DataFrame:
    """
    Updates the user's entries in the provided simulations based on the specified strategies.

    Args:
        sims (pd.DataFrame): dataframe containing simulated picks for each matchup and each contestant in each simulation.
        fixed (list, optional): list of teams to automatically pick regardless of strategy, defaults to [].
        pick_pref (str, optional): strategy to use during pick selection. Acceptable values: "best", "worst", "popular", "random"; defaults to "best".
        point_pref (str, optional): strategy to use during points selection. Acceptable values: "best", "worst", "popular", "random"; defaults to "best".

    Returns:
        pd.DataFrame: same simulation dataframe, but with the user's picks strategically updated.
    """
    num_sims = int(sims.num_sim.max() + 1)
    my_entries = sims.loc[sims.entry == 0].reset_index(drop=True)
    my_points = sorted(my_entries.points_bid.unique().tolist())[::-1]
    sims = sims.loc[sims.entry != 0].reset_index(drop=True)
    home_fixed = my_entries.team1_abbrev.isin(fixed)
    away_fixed = my_entries.team2_abbrev.isin(fixed)
    home_fav = my_entries.elo_prob1 >= my_entries.elo_prob2
    if str(pick_pref).lower() not in ["best","popular","worst","random"]:
        print('Invalid preference value ("best", "popular", "worst", "random"), using "best" by default...')
        pick_pref = "best"
    if pick_pref.lower() == "best":
        home_fav = my_entries.elo_prob1 >= my_entries.elo_prob2
    elif pick_pref.lower() == "worst":
        home_fav = my_entries.elo_prob1 < my_entries.elo_prob2
    elif pick_pref.lower() == "popular":
        home_fav = my_entries.pick_prob1 >= my_entries.pick_prob2
    elif pick_pref.lower() == "random":
        picks = my_entries.loc[my_entries.num_sim == 0].reset_index(drop=True)
        picks['random_pick'] = np.random.rand(picks.shape[0])
        random = picks.loc[picks.random_pick > 0.5,'team1_abbrev'].tolist() + picks.loc[picks.random_pick <= 0.5,'team2_abbrev'].tolist()
        home_fav = my_entries.team1_abbrev.isin(random)
    my_entries.loc[home_fav & ~home_fixed & ~away_fixed,'pick'] = my_entries.loc[home_fav & ~home_fixed & ~away_fixed,'team1_abbrev']
    my_entries.loc[home_fav & ~home_fixed & ~away_fixed,'win_prob'] = my_entries.loc[home_fav & ~home_fixed & ~away_fixed,'elo_prob1']
    my_entries.loc[home_fav & ~home_fixed & ~away_fixed,'pick_pts'] = my_entries.loc[home_fav & ~home_fixed & ~away_fixed,'pick_pts1']
    my_entries.loc[~home_fav & ~home_fixed & ~away_fixed,'pick'] = my_entries.loc[~home_fav & ~home_fixed & ~away_fixed,'team2_abbrev']
    my_entries.loc[~home_fav & ~home_fixed & ~away_fixed,'win_prob'] = my_entries.loc[~home_fav & ~home_fixed & ~away_fixed,'elo_prob2']
    my_entries.loc[~home_fav & ~home_fixed & ~away_fixed,'pick_pts'] = my_entries.loc[~home_fav & ~home_fixed & ~away_fixed,'pick_pts2']
    my_entries.loc[home_fixed,'pick'] = my_entries.loc[home_fixed,'team1_abbrev']
    my_entries.loc[home_fixed,'win_prob'] = my_entries.loc[home_fixed,'elo_prob1']
    my_entries.loc[home_fixed,'pick_pts'] = my_entries.loc[home_fixed,'pick_pts1']
    my_entries.loc[away_fixed,'pick'] = my_entries.loc[away_fixed,'team2_abbrev']
    my_entries.loc[away_fixed,'win_prob'] = my_entries.loc[away_fixed,'elo_prob2']
    my_entries.loc[away_fixed,'pick_pts'] = my_entries.loc[away_fixed,'pick_pts2']
    my_entries.loc[my_entries.team1_abbrev.isin(prioritize) \
    | my_entries.team2_abbrev.isin(prioritize),'win_prob'] += 1
    my_entries = my_entries.sort_values(by=['num_sim','win_prob'],ascending=False,ignore_index=True)
    if str(point_pref).lower() not in ["best","popular","worst","random"]:
        print('Invalid preference value ("best", "popular", "worst", "random"), using "best" by default...')
        point_pref = "best"
    if point_pref.lower() == "worst":
        my_points = my_points[::-1]
    elif point_pref.lower() == "popular":
        my_entries = my_entries.sort_values(by=['num_sim','pick_pts'],ascending=False,ignore_index=True)
    elif point_pref.lower() == "random":
        np.random.shuffle(my_points)
    my_entries['points_bid'] = my_points*num_sims
    my_entries.loc[my_entries.team1_abbrev.isin(prioritize) \
    | my_entries.team2_abbrev.isin(prioritize),'win_prob'] -= 1
    sims = pd.concat([sims,my_entries],ignore_index=True)
    sims = sims.sort_values(by=["num_sim","entry"],ascending=True,ignore_index=True)
    if "points_won" in sims.columns:
        sims.loc[sims.winner == sims.pick,'points_won'] = sims.loc[sims.winner == sims.pick,'points_bid']
        sims.loc[sims.winner != sims.pick,'points_won'] = 0.0
    return sims

def simulate_games(sims: pd.DataFrame, fixed: list = []) -> pd.DataFrame:
    """
    Simulates NFL games for the simulated picks provided.

    Args:
        sims (pd.DataFrame): dataframe containing simulated picks for each matchup and each contestant in each simulation.
        fixed (list, optional): list of teams to automatically win regardless of simulation, defaults to [].

    Returns:
        pd.DataFrame: same simulation dataframe, but with game/point outcomes updated.
    """
    matchups = sims[['num_sim','team1_abbrev','team2_abbrev']].drop_duplicates(ignore_index=True)
    matchups['game_sim'] = np.random.rand(matchups.shape[0])
    if "game_sim" in sims.columns:
        del sims['game_sim']
    sims = pd.merge(left=sims,right=matchups,how='inner',on=["num_sim","team1_abbrev","team2_abbrev"])
    home_win = sims.game_sim < sims.elo_prob1
    sims.loc[home_win,'winner'] = sims.loc[home_win,'team1_abbrev']
    sims.loc[~home_win,'winner'] = sims.loc[~home_win,'team2_abbrev']
    sims.loc[sims.team1_abbrev.isin(fixed),"winner"] = sims.loc[sims.team1_abbrev.isin(fixed),"team1_abbrev"]
    sims.loc[sims.team2_abbrev.isin(fixed),"winner"] = sims.loc[sims.team2_abbrev.isin(fixed),"team2_abbrev"]
    sims.loc[sims.winner == sims.pick,'points_won'] = sims.loc[sims.winner == sims.pick,'points_bid']
    sims.loc[sims.winner != sims.pick,'points_won'] = 0.0
    return sims

def assess_sims(sims: pd.DataFrame, picks: pd.DataFrame(), pot_size: float = 500.0) -> pd.DataFrame:
    """
    Assesses the overall results for each contestant in the simulations provided.

    Args:
        sims (pd.DataFrame): dataframe containing simulated picks and game results.
        picks (pd.DataFrame): dataframe containing details about picks that have already been made.
        pot_size (float, optional): amount of money that goes to the winner, defaults to 500.0.

    Returns:
        pd.DataFrame: dataframe containing results summaries for each contestant.
    """
    num_sims = sims.num_sim.max() + 1
    standings = sims.groupby(['entry','num_sim']).points_won.sum().reset_index()
    standings = pd.merge(left=standings,right=picks.groupby('entry').points_won.sum().reset_index(),how='left',on=['entry'],suffixes=("","_already"))
    standings.points_won_already = standings.points_won_already.fillna(0.0)
    standings.points_won += standings.points_won_already
    del standings['points_won_already']
    standings = standings.sort_values(by=['num_sim','points_won'],ascending=[True,False])
    winners = standings.drop_duplicates(subset=['num_sim'],keep='first')
    results = pd.merge(left=standings.groupby('entry').points_won.mean().reset_index().rename(columns={'points_won':'points_avg'}),\
    right=standings.groupby('entry').points_won.std().reset_index().rename(columns={'points_won':'points_std'}),how='inner',on='entry')
    results = pd.merge(left=results,right=winners.groupby('entry').size().to_frame('win_pct').reset_index(),how='left',on='entry')
    results.win_pct = results.win_pct.fillna(0.0)/num_sims
    results['earnings'] = results.win_pct*pot_size
    return results

def optimize_picks(games: pd.DataFrame, picks: pd.DataFrame, num_sims: int = 1000, num_entries: int = 50, \
fixed: list = [], initial_picks: str = "best", initial_pts: str = "best", prioritize: list = []) -> pd.DataFrame:
    """
    Gradually changes each pick one by one and keeps any that improve expected earnings.
    Once picks have been settled, gradually swaps point values and keeps any that improve expected earnings.

    Args:
        games (pd.DataFrame): dataframe containing details on each NFL matchup during the week of interest.
        picks (pd.DataFrame): dataframe containing details about picks that have already been made.
        num_sims (int, optional): number of simulations to perform, defaults to 1000.
        num_entries (int, optional): number of contestants in the group, defaults to 50.
        fixed (list, optional): list of strings containing teams guaranteed to be picked.
        initial_picks (str, optional): strategy to use during initial pick selection. Acceptable values: "best", "worst", "popular", "random"; defaults to "best".
        initial_pts (str, optional): strategy to use during initial points selection. Acceptable values: "best", "worst", "popular", "random"; defaults to "best".

    Returns:
        pd.DataFrame: dataframe containing simulated picks and game results with optimal picks made for the user.
    """
    sims = simulate_picks(games, picks, num_sims, num_entries)
    sims = add_my_picks(sims, fixed, pick_pref=initial_picks, prioritize=prioritize)
    sims = simulate_games(sims)
    results = assess_sims(sims, picks)
    baseline = results.loc[results.entry == 0].iloc[0]
    # Pick changes
    update = True
    while update:
        my_picks = sims.loc[(sims.entry == 0) & (sims.num_sim == 0),['team1_abbrev','team2_abbrev','pick','win_prob','points_bid']].reset_index(drop=True)
        deltas = pd.DataFrame()
        for ind in range(my_picks.shape[0]):
            pick = my_picks.iloc[ind]['pick']
            oppo = my_picks.iloc[ind]['team1_abbrev'] if pick == my_picks.iloc[ind]['team2_abbrev'] else my_picks.iloc[ind]['team2_abbrev']
            if pick in fixed:
                continue
            sims = add_my_picks(sims, [team for team in my_picks.pick if team != pick] + [oppo], prioritize=prioritize)
            results = assess_sims(sims, picks)
            switch = results.loc[results.entry == 0].iloc[0]
            print('{} --> {}: ${:.2f} --> ${:.2f}'.format(pick,oppo,baseline['earnings'],switch['earnings']))
            deltas = pd.concat([deltas,pd.DataFrame({'orig_pick':[pick],'orig_earnings':[baseline['earnings']],\
            'new_pick':[oppo],'new_earnings':[switch['earnings']]})],ignore_index=True)
        deltas['change'] = deltas.new_earnings - deltas.orig_earnings
        deltas = deltas.sort_values(by='change',ascending=False,ignore_index=True)
        print(deltas)
        update = (deltas.change > 0).any() or ((deltas.change == 0).any() and np.random.rand() > 0.5)
        if update:
            sims = add_my_picks(sims, [team for team in my_picks.pick if team != deltas.iloc[0]['orig_pick']] + [deltas.iloc[0]['new_pick']], prioritize=prioritize)
            results = assess_sims(sims, picks)
            baseline = results.loc[results.entry == 0].iloc[0]
    # Point changes
    final_picks = sims.loc[(sims.entry == 0) & (sims.num_sim == 0),'pick'].tolist()
    sims = add_my_picks(sims, final_picks, point_pref=initial_pts, prioritize=prioritize)
    results = assess_sims(sims, picks)
    baseline = results.loc[results.entry == 0].iloc[0]
    for change in range(4,0,-1):
        update = True
        while update:
            deltas = pd.DataFrame()
            for switch_from in range(1,games.shape[0] - change + 1):
                up = (sims.entry == 0) & (sims.points_bid == switch_from)
                down = (sims.entry == 0) & (sims.points_bid == switch_from + change)
                if up.sum() == 0 or down.sum() == 0 \
                or sims.loc[up,'pick'].values[0] in prioritize \
                or sims.loc[down,'pick'].values[0] in prioritize:
                    continue # One of the point values have already been used...
                sims.loc[up,'points_bid'] = switch_from + change
                sims.loc[down,'points_bid'] = switch_from
                sims.loc[sims.winner == sims.pick,'points_won'] = sims.loc[sims.winner == sims.pick,'points_bid']
                sims.loc[sims.winner != sims.pick,'points_won'] = 0.0
                results = assess_sims(sims, picks)
                switch = results.loc[results.entry == 0].iloc[0]
                pick = sims.loc[up,'pick'].values[0]
                oppo = sims.loc[down,'pick'].values[0]
                deltas = pd.concat([deltas,pd.DataFrame({'from_pick':[pick],'from_pts':[switch_from],\
                'to_pick':[oppo],'to_pts':[switch_from + change],'orig_earnings':[baseline['earnings']],\
                'new_earnings':[switch['earnings']]})],ignore_index=True)
                sims.loc[up,'points_bid'] = switch_from
                sims.loc[down,'points_bid'] = switch_from + change
                sims.loc[sims.winner == sims.pick,'points_won'] = sims.loc[sims.winner == sims.pick,'points_bid']
                sims.loc[sims.winner != sims.pick,'points_won'] = 0.0
            deltas['change'] = deltas.new_earnings - deltas.orig_earnings
            deltas = deltas.sort_values(by='change',ascending=False,ignore_index=True)
            print(deltas)
            update = (deltas.change > 0).any() or ((deltas.change == 0).any() and np.random.rand() > 0.5)
            if update:
                up = (sims.entry == 0) & (sims.points_bid == deltas.iloc[0]['from_pts'])
                down = (sims.entry == 0) & (sims.points_bid == deltas.iloc[0]['to_pts'])
                sims.loc[up,'points_bid'] = deltas.iloc[0]['to_pts']
                sims.loc[down,'points_bid'] = deltas.iloc[0]['from_pts']
                sims.loc[sims.winner == sims.pick,'points_won'] = sims.loc[sims.winner == sims.pick,'points_bid']
                sims.loc[sims.winner != sims.pick,'points_won'] = 0.0
                results = assess_sims(sims, picks)
                baseline = results.loc[results.entry == 0].iloc[0]
    return sims

def pick_deltas(sims: pd.DataFrame, picks: pd.DataFrame) -> pd.DataFrame:
    """
    Measures the relative importance of each game by calculating the 
    change in expected earnings between correct and incorrect picks.

    Args:
        sims (pd.DataFrame): dataframe containing simulated picks and game results.
        picks (pd.DataFrame): dataframe containing details about picks that have already been made.

    Returns:
        pd.DataFrame: dataframe containing the user's picks and their relative earnings impact.
    """
    my_picks = sims.loc[(sims.entry == 0) & (sims.num_sim == 0),\
    ['team1_abbrev','team2_abbrev','pick','points_bid']]\
    .sort_values(by='points_bid',ascending=False,ignore_index=True)
    for ind in range(my_picks.shape[0]):
        pick = my_picks.iloc[ind]
        correct = pick['team1_abbrev'] if pick['team1_abbrev'] == pick['pick'] else pick['team2_abbrev']
        sims = simulate_games(sims, [correct])
        results = assess_sims(sims, picks)
        winner = results.loc[results.entry == 0].iloc[0]
        incorrect = pick['team2_abbrev'] if pick['team1_abbrev'] == pick['pick'] else pick['team1_abbrev']
        sims = simulate_games(sims, [incorrect])
        results = assess_sims(sims, picks)
        loser = results.loc[results.entry == 0].iloc[0]
        my_picks.loc[ind,'win'] = winner["earnings"]
        my_picks.loc[ind,'loss'] = loser["earnings"]
        my_picks.loc[ind,'delta'] = winner["earnings"] - loser["earnings"]
    print("\nRemaining Games:")
    print(my_picks.to_string(index=False))
    return my_picks

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
        "--week",
        action="store",
        type="int",
        dest="week",
        help="week of the NFL season to simulate and assess",
    )
    parser.add_option(
        "--vegas",
        action="store_true",
        dest="vegas",
        help="whether to use Vegas odds instead of the 538 methodology",
    )
    parser.add_option(
        "--num_entries",
        action="store",
        type="int",
        dest="num_entries",
        default=58,
        help="number of entries in the pick em league in question",
    )
    parser.add_option(
        "--num_sims",
        action="store",
        type="int",
        dest="num_sims",
        default=10000,
        help="number of simulations to run when assessing picks",
    )
    parser.add_option(
        "--fixed",
        action="store",
        dest="fixed",
        help="comma-separated list of teams to automatically pick regardless of odds",
    )
    parser.add_option(
        "--prioritize",
        action="store",
        dest="prioritize",
        help="comma-separated list of teams to automatically give the highest points possible",
    )
    parser.add_option(
        "--optimize",
        action="store",
        dest="optimize",
        help="which starting point to use during pick optimization (best, worst, popular, random)",
    )
    options, args = parser.parse_args()
    options.fixed = options.fixed.split(',') if options.fixed else []
    options.prioritize = options.prioritize.split(',') if options.prioritize else []
    if len(options.prioritize) > 0:
        options.optimize = "best"

    # Loading the current week's schedule
    schedule = load_schedule(options.schedule, options.week, options.vegas)
    options.week = schedule.week.unique()[0]

    # Loading pick probabilities for the current week
    pick_probs = load_pick_probs(options.week)
    picks = load_picks(options.week,schedule)
    winners = schedule.loc[~schedule.still_to_play,'winner_abbrev']
    picks.loc[picks.pick.isin(winners),'points_won'] = picks.loc[picks.pick.isin(winners),'points_bid']
    picks.points_bid = picks.points_bid.fillna(1.0)
    picks.points_won = picks.points_won.fillna(0.0)
    if picks.shape[0] > 0:
        options.num_entries = picks.entry.nunique()
    games = pd.merge(left=schedule[['team1_abbrev','team2_abbrev','elo_prob1','elo_prob2','still_to_play']],\
    right=pick_probs,how='inner',on=['team1_abbrev','team2_abbrev'])

    # Simulating a full Confidence Pick'em contest
    sims = simulate_picks(games, picks, options.num_sims, options.num_entries)
    if schedule.still_to_play.sum() < 10:
        sims = add_my_picks(sims, options.fixed, prioritize=options.prioritize)
    sims = simulate_games(sims)
    results = assess_sims(sims,picks)
    if picks.shape[0] > 0:
        results = pd.merge(left=results,right=picks[["entry","player"]].drop_duplicates(),how='inner',on=["entry"])
    else:
        results["player"] = "Player #" + (results["entry"] + 1).astype(str)
    baseline = results.loc[results.entry == 0].iloc[0]
    del results["entry"], baseline["entry"]

    # Printing simulation results
    print("\nFull Standings:")
    print(results[["player","points_avg","points_std","win_pct","earnings"]]\
    .sort_values(by=['earnings','points_avg'],ascending=False).to_string(index=False))
    print("\nYour Projections:")
    print(baseline.to_string())

    if options.optimize:
        # Identifying optimal picks for the current week
        sims = optimize_picks(games, picks, options.num_sims, options.num_entries, \
        options.fixed, options.optimize, options.optimize, options.prioritize)
    
    # Identifying the relative impact of each pick
    my_picks = pick_deltas(sims, picks)
    my_picks.to_excel("ConfidencePickEm_Week{}.xlsx".format(options.week),index=False)


if __name__ == "__main__":
    main()

