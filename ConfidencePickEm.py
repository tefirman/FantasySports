
from util import sportsref_nfl as sr
import pandas as pd
import os
import datetime
import numpy as np
import optparse

def load_picks(week: int):
    nfl_teams = pd.read_csv("https://raw.githubusercontent.com/tefirman/FantasySports/main/res/football/team_abbrevs.csv")
    tempData = open("PickEmDistribution_Week1.txt",'r')
    raw_str = tempData.read()
    tempData.close()
    games = raw_str.split("Spread and Confidence\n")[-1].split('\n\n')[0].split('pts\tFavorite\t \n')
    home = [game.split('\n')[7].split('\t')[0] for game in games]
    home = [nfl_teams.loc[nfl_teams.yahoo.str.upper().isin([team]),'real_abbrev'].values[0] for team in home]
    home_pct = [float(game.split('\n')[3].replace('%',''))/100.0 for game in games]
    away = [game.split('\n')[7].split('\t')[-1] for game in games]
    away = [nfl_teams.loc[nfl_teams.yahoo.str.upper().isin([team]),'real_abbrev'].values[0] for team in away]
    away_pct = [float(game.split('\n')[6].replace('%',''))/100.0 for game in games]
    pick_probs = pd.DataFrame({'team1_abbrev':home,'team2_abbrev':away,'pick_prob1':home_pct,'pick_prob2':away_pct})
    return pick_probs

def simulate_picks(games: pd.DataFrame, num_sims: int = 1000, num_entries: int = 50, pts_stdev: float = 3.0):
    sims = pd.concat(num_sims*num_entries*[games],ignore_index=True)
    sims['entry'] = sims.index%(games.shape[0]*num_entries)//games.shape[0]
    sims['num_sim'] = sims.index//(games.shape[0]*num_entries)
    sims['pick_sim'] = np.random.rand(sims.shape[0])
    home_pick = sims.pick_sim < sims.pick_prob1
    sims.loc[home_pick,'pick'] = sims.loc[home_pick,'team1_abbrev']
    sims.loc[~home_pick,'pick'] = sims.loc[~home_pick,'team2_abbrev']
    sims.loc[home_pick,'points_bid_sim'] = np.random.normal(0,pts_stdev,home_pick.sum()) + sims.loc[home_pick,'elo_prob1']*games.shape[0]
    sims.loc[~home_pick,'points_bid_sim'] = np.random.normal(0,pts_stdev,(~home_pick).sum()) + sims.loc[~home_pick,'elo_prob2']*games.shape[0]
    sims['points_bid'] = sims.groupby(['entry','num_sim']).points_bid_sim.rank()
    return sims

def add_chalk_picks(sims: pd.DataFrame, fixed: list = []):
    num_sims = sims.num_sim.max() + 1
    my_entries = sims.loc[sims.entry == 0].reset_index(drop=True)
    sims = sims.loc[sims.entry != 0].reset_index(drop=True)
    home_fixed = my_entries.team1_abbrev.isin(fixed)
    away_fixed = my_entries.team2_abbrev.isin(fixed)
    home_fav = my_entries.elo_prob1 >= my_entries.elo_prob2
    my_entries.loc[home_fav & ~home_fixed & ~away_fixed,'pick'] = my_entries.loc[home_fav & ~home_fixed & ~away_fixed,'team1_abbrev']
    my_entries.loc[home_fav & ~home_fixed & ~away_fixed,'win_prob'] = my_entries.loc[home_fav & ~home_fixed & ~away_fixed,'elo_prob1']
    my_entries.loc[~home_fav & ~home_fixed & ~away_fixed,'pick'] = my_entries.loc[~home_fav & ~home_fixed & ~away_fixed,'team2_abbrev']
    my_entries.loc[~home_fav & ~home_fixed & ~away_fixed,'win_prob'] = my_entries.loc[~home_fav & ~home_fixed & ~away_fixed,'elo_prob2']
    my_entries.loc[home_fixed,'pick'] = my_entries.loc[home_fixed,'team1_abbrev']
    my_entries.loc[home_fixed,'win_prob'] = my_entries.loc[home_fixed,'elo_prob1']
    my_entries.loc[away_fixed,'pick'] = my_entries.loc[away_fixed,'team2_abbrev']
    my_entries.loc[away_fixed,'win_prob'] = my_entries.loc[away_fixed,'elo_prob2']
    my_entries = my_entries.sort_values(by=['num_sim','win_prob'],ascending=False,ignore_index=True)
    my_entries['points_bid'] = list(range(16,0,-1))*num_sims
    sims = pd.concat([sims,my_entries],ignore_index=True)
    sims = sims.sort_values(by=["num_sim","entry"],ascending=True,ignore_index=True)
    return sims

def simulate_games(sims: pd.DataFrame):
    sims['game_sim'] = np.random.rand(sims.shape[0])
    home_win = sims.game_sim < sims.elo_prob1
    sims.loc[home_win,'winner'] = sims.loc[home_win,'team1_abbrev']
    sims.loc[~home_win,'winner'] = sims.loc[~home_win,'team2_abbrev']
    sims.loc[sims.winner == sims.pick,'points_won'] = sims.loc[sims.winner == sims.pick,'points_bid']
    sims.loc[sims.winner != sims.pick,'points_won'] = 0.0
    return sims

def assess_sims(sims: pd.DataFrame, pot_size: float = 500.0):
    num_sims = sims.num_sim.max() + 1
    standings = sims.groupby(['entry','num_sim']).points_won.sum().reset_index()\
    .sort_values(by=['num_sim','points_won'],ascending=[True,False])
    winners = standings.drop_duplicates(subset=['num_sim'],keep='first')
    results = pd.merge(left=standings.groupby('entry').points_won.mean().reset_index().rename(columns={'points_won':'points_avg'}),\
    right=standings.groupby('entry').points_won.std().reset_index().rename(columns={'points_won':'points_std'}),how='inner',on='entry')
    results = pd.merge(left=results,right=winners.groupby('entry').size().to_frame('win_pct').reset_index(),how='left',on='entry')
    results.win_pct = results.win_pct.fillna(0.0)/num_sims
    results['earnings'] = results.win_pct*pot_size
    return results

def main():
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
        "--num_entries",
        action="store",
        type="int",
        dest="num_entries",
        default=40,
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
    options, args = parser.parse_args()

    if os.path.exists(options.schedule):
        schedule = pd.read_csv(options.schedule)
    else:
        s = sr.Schedule(2015,datetime.datetime.now().year,False,True,False)
        schedule = s.schedule.copy()
        schedule.to_csv(options.schedule,index=False)
    schedule = schedule.loc[(schedule.season == datetime.datetime.now().year) & (schedule.week == options.week)].reset_index(drop=True)

    pick_probs = load_picks(options.week)

    games = pd.merge(left=schedule[['team1_abbrev','team2_abbrev','elo_prob1','elo_prob2']],\
    right=pick_probs,how='inner',on=['team1_abbrev','team2_abbrev'])

    sims = simulate_picks(games, options.num_sims, options.num_entries)

    sims = add_chalk_picks(sims)
    sims = simulate_games(sims)

    results = assess_sims(sims)
    print(results)


if __name__ == "__main__":
    main()

