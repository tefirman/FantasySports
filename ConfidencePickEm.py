
from util import sportsref_nfl as sr
import pandas as pd
import os
import datetime
import numpy as np
import optparse

def load_pick_probs(week: int):
    nfl_teams = pd.read_csv("https://raw.githubusercontent.com/tefirman/FantasySports/main/res/football/team_abbrevs.csv")
    tempData = open("PickEmDistribution_Week{}.txt".format(week),'r')
    raw_str = tempData.read()
    tempData.close()
    games = raw_str.split("Spread and Confidence\n")[-1].split('\n\n')[0].split('pts\tFavorite\t \n')
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
    return pick_probs[['team1_abbrev','team2_abbrev','pick_prob1','pick_prob2','pick_pts1','pick_pts2']]

def load_picks(week: int):
    if os.path.exists("ActualConfidencePicks_Week{}.txt".format(week)):
        tempData = open("ActualConfidencePicks_Week{}.txt".format(week),'r')
        raw_data = tempData.read().split('Team Name\tPoints\n')[-1]\
        .split("\nYahoo! Sports - NBC Sports Network.")[0].replace('\n(','\r(').split('\n')
        tempData.close()
    else:
        raw_data = []
    actual = pd.DataFrame(columns=["player","pick","points_bid"])
    for vals in raw_data:
        player = vals.split('\t')[0]
        picks = vals.split('\t')[1:-1]
        actual = pd.concat([actual,pd.DataFrame({'player':[player]*len(picks),'pick':picks})],ignore_index=True)
    actual = actual.loc[~actual.pick.isin(['--',' '])].reset_index(drop=True)
    actual['points_bid'] = actual.pick.str.split('\r').str[-1].str[1:-1].astype(int)
    actual['pick'] = actual.pick.str.split('\r').str[0]
    nfl_teams = pd.read_csv("https://raw.githubusercontent.com/tefirman/FantasySports/main/res/football/team_abbrevs.csv")
    actual = pd.merge(left=actual,right=nfl_teams[['yahoo','real_abbrev']].rename(columns={"yahoo":"pick"}),how='left',on='pick')
    actual.loc[~actual.real_abbrev.isnull(),'pick'] = actual.loc[~actual.real_abbrev.isnull(),'real_abbrev']
    del actual['real_abbrev']
    my_picks = actual.loc[actual.player == "Firman's Educated Guesses"].reset_index(drop=True)
    my_picks["entry"] = 0.0
    actual = actual.loc[actual.player != "Firman's Educated Guesses"].reset_index(drop=True)
    actual["entry"] = actual.player.rank(method='dense')
    actual = pd.concat([my_picks,actual])
    num_picks = actual.groupby('pick').size().to_frame('freq').reset_index()
    # This isn't quite right, but fine for now...
    already = num_picks.loc[num_picks.freq > 1,'pick'].unique().tolist()
    actual = actual.loc[actual.pick.isin(already)].reset_index(drop=True)
    # This isn't quite right, but fine for now...
    return actual

def simulate_picks(games: pd.DataFrame, picks: pd.DataFrame, num_sims: int = 1000, num_entries: int = 50, pts_stdev: float = 4.0):
    # games includes all games from this week, picks only contains games already played...
    sims = pd.concat(num_sims*num_entries*[games.loc[games.still_to_play]],ignore_index=True)
    sims['entry'] = sims.index%(games.still_to_play.sum()*num_entries)//games.still_to_play.sum()
    sims['num_sim'] = sims.index//(games.still_to_play.sum()*num_entries)
    sims['pick_sim'] = np.random.rand(sims.shape[0])
    home_pick = sims.pick_sim < sims.pick_prob1
    sims.loc[home_pick,'pick'] = sims.loc[home_pick,'team1_abbrev']
    sims.loc[~home_pick,'pick'] = sims.loc[~home_pick,'team2_abbrev']
    all_picks = pd.DataFrame({"entry":[val//games.shape[0] for val in range(games.shape[0]*num_entries)],\
    "points_bid":[val%games.shape[0] + 1 for val in range(games.shape[0]*num_entries)]})
    all_picks = pd.merge(left=all_picks,right=picks,how='left',on=['entry','points_bid'])
    all_picks = all_picks.loc[all_picks.pick.isnull()]
    sims.loc[home_pick,'points_bid_sim'] = np.random.normal(0,pts_stdev,home_pick.sum()) + sims.loc[home_pick,'pick_pts1']
    sims.loc[~home_pick,'points_bid_sim'] = np.random.normal(0,pts_stdev,(~home_pick).sum()) + sims.loc[~home_pick,'pick_pts2']
    sims = sims.sort_values(by=['num_sim','entry','points_bid_sim'],ascending=True)
    sims['points_bid'] = all_picks.points_bid.tolist()*num_sims
    return sims

def add_my_picks(sims: pd.DataFrame, fixed: list = [], pick_pref: str = "best", point_pref: str = "best"):
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
    sims = pd.concat([sims,my_entries],ignore_index=True)
    sims = sims.sort_values(by=["num_sim","entry"],ascending=True,ignore_index=True)
    if "points_won" in sims.columns:
        sims.loc[sims.winner == sims.pick,'points_won'] = sims.loc[sims.winner == sims.pick,'points_bid']
        sims.loc[sims.winner != sims.pick,'points_won'] = 0.0
    return sims

def simulate_games(sims: pd.DataFrame, fixed: list = []):
    sims['game_sim'] = np.random.rand(sims.shape[0])
    home_win = sims.game_sim < sims.elo_prob1
    sims.loc[home_win,'winner'] = sims.loc[home_win,'team1_abbrev']
    sims.loc[~home_win,'winner'] = sims.loc[~home_win,'team2_abbrev']
    sims.loc[sims.team1_abbrev.isin(fixed),"winner"] = sims.loc[sims.team1_abbrev.isin(fixed),"team1_abbrev"]
    sims.loc[sims.team2_abbrev.isin(fixed),"winner"] = sims.loc[sims.team2_abbrev.isin(fixed),"team2_abbrev"]
    sims.loc[sims.winner == sims.pick,'points_won'] = sims.loc[sims.winner == sims.pick,'points_bid']
    sims.loc[sims.winner != sims.pick,'points_won'] = 0.0
    return sims

def assess_sims(sims: pd.DataFrame, picks: pd.DataFrame(), pot_size: float = 500.0):
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
fixed: list = [], initial_picks: str = "best", initial_pts: str = "best"):
    sims = simulate_picks(games, picks, num_sims, num_entries)
    sims = add_my_picks(sims, fixed, pick_pref=initial_picks)
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
            sims = add_my_picks(sims, [team for team in my_picks.pick if team != pick] + [oppo])
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
            sims = add_my_picks(sims, [team for team in my_picks.pick if team != deltas.iloc[0]['orig_pick']] + [deltas.iloc[0]['new_pick']])
            results = assess_sims(sims, picks)
            baseline = results.loc[results.entry == 0].iloc[0]
    # Point changes
    final_picks = sims.loc[(sims.entry == 0) & (sims.num_sim == 0),'pick'].tolist()
    sims = add_my_picks(sims, final_picks, point_pref=initial_pts)
    results = assess_sims(sims, picks)
    baseline = results.loc[results.entry == 0].iloc[0]
    for change in range(4,0,-1):
        update = True
        while update:
            deltas = pd.DataFrame()
            for switch_from in range(1,games.shape[0] - change + 1):
                up = (sims.entry == 0) & (sims.points_bid == switch_from)
                down = (sims.entry == 0) & (sims.points_bid == switch_from + change)
                if up.sum() == 0 or down.sum() == 0:
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
    my_picks = sims.loc[(sims.entry == 0) & (sims.num_sim == 0),\
    ['team1_abbrev','team2_abbrev','pick','win_prob','points_bid']]\
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
        my_picks.loc[ind,'delta'] = winner["earnings"] - loser["earnings"]
    print(my_picks)
    return my_picks

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
        "--optimize",
        action="store",
        dest="optimize",
        help="which starting point to use during pick optimization (best, worst, popular, random)",
    )
    options, args = parser.parse_args()
    options.fixed = options.fixed.split(',') if options.fixed else []

    if os.path.exists(options.schedule):
        schedule = pd.read_csv(options.schedule)
    else:
        s = sr.Schedule(2015,datetime.datetime.now().year,False,True,False)
        schedule = s.schedule.copy()
        schedule.to_csv(options.schedule,index=False)
    schedule = schedule.loc[schedule.season == datetime.datetime.now().year].reset_index(drop=True)
    if not options.week:
        options.week = schedule.loc[schedule.pts_win.isnull(),'week'].min()
    schedule = schedule.loc[schedule.week == options.week].reset_index(drop=True)
    schedule['still_to_play'] = pd.to_datetime(schedule.game_date + ', ' + \
    schedule.gametime,infer_datetime_format=True) > datetime.datetime.now() + datetime.timedelta(hours=2)
    winners = schedule.loc[~schedule.still_to_play,'winner_abbrev']

    pick_probs = load_pick_probs(options.week)
    picks = load_picks(options.week)
    picks.loc[picks.pick.isin(winners),'points_won'] = picks.loc[picks.pick.isin(winners),'points_bid']
    picks.points_won = picks.points_won.fillna(0.0)
    if picks.shape[0] > 0:
        options.num_entries = picks.entry.nunique()

    games = pd.merge(left=schedule[['team1_abbrev','team2_abbrev','elo_prob1','elo_prob2','still_to_play']],\
    right=pick_probs,how='inner',on=['team1_abbrev','team2_abbrev'])

    sims = simulate_picks(games, picks, options.num_sims, options.num_entries)
    sims = add_my_picks(sims, options.fixed)
    sims = simulate_games(sims)

    results = assess_sims(sims,picks)
    if picks.shape[0] > 0:
        results = pd.merge(left=results,right=picks[["entry","player"]].drop_duplicates(),how='inner',on=["entry"])
    else:
        results["player"] = "Player #" + (results["entry"] + 1).astype(str)
    baseline = results.loc[results.entry == 0].iloc[0]
    del results["entry"], baseline["entry"]
    print(results[["player","points_avg","points_std","win_pct","earnings"]]\
    .sort_values(by='earnings',ascending=False).to_string(index=False))
    print(baseline)

    if options.optimize:
        my_picks = optimize_picks(games, picks, options.num_sims, options.num_entries, options.fixed, options.optimize, options.optimize)
        my_picks.to_excel("ConfidencePickEm_Week{}.xlsx".format(options.week),index=False)


if __name__ == "__main__":
    main()

