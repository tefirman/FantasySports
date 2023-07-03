
import pandas as pd
import optparse
import fantasyfb as fb
import numpy as np
from difflib import SequenceMatcher
import sys

def check_pick_value(league, pick):
    pick = str(pick)
    if not pick.strip().isnumeric():
        print("Invalid pick value, must be numeric.")
        return None
    elif int(pick.strip()) < 1 or int(pick.strip()) > len(league.teams):
        print("Invalid pick value, must be between 1 and {}.".format(len(league.teams)))
        return None
    else:
        return int(pick.strip())

def provide_pick_order(league,customize=False):
    my_pick = check_pick_value(league,input("Which pick are you? "))
    while my_pick is None:
        my_pick = check_pick_value(league,input("Which pick are you? "))
    my_team = [team for team in league.teams if team['name'] == league.name]
    other_teams = [team for team in league.teams if team['name'] != league.name]
    league.teams = other_teams[:my_pick - 1] + my_team + other_teams[my_pick - 1:]
    avg_team = pd.concat(3*[league.players.loc[league.players.player_id_sr.astype(str).str.startswith('avg_')]],ignore_index=True,sort=False)
    for pick in range(len(league.teams)):
        if pick + 1 == my_pick:
            pick_name = "My Team"
        elif customize:
            pick_name = input("Who has pick #{}? ".format(pick + 1))
        else:
            pick_name = "Team #" + str(pick + 1)
        league.schedule.loc[league.schedule.team_1 == league.teams[pick]['name'],'team_1'] = pick_name
        league.schedule.loc[league.schedule.team_2 == league.teams[pick]['name'],'team_2'] = pick_name
        league.teams[pick]['name'] = pick_name
        avg_team['fantasy_team'] = pick_name
        league.players = pd.concat([league.players,avg_team.copy()],ignore_index=True,sort=False)
    return league

def check_pick_name(league, pick_name, exceptions=[]):
    not_picked = league.players.fantasy_team.isnull()
    available = league.players.loc[not_picked].copy()
    taken = league.players.loc[~not_picked].copy()

    if pick_name in available.name.tolist() or pick_name.lower() in exceptions:
        return pick_name
    else:
        if pick_name in taken.name.tolist():
            team = taken.loc[taken.name == pick_name,'fantasy_team'].values[0]
            print("Player has already been taken by {}.".format(team))
        else:
            available['similarity'] = available.name.apply(lambda x: SequenceMatcher(None, x, pick_name).ratio())
            print("Can't find the player you provided. Closest options:")
            print(available.sort_values(by="similarity",ascending=False).iloc[:3][['name','position','current_team']].to_string(index=False))
        return None

def main():
    parser = optparse.OptionParser()
    parser.add_option(
        "--teamname", action="store", dest="teamname", help="name of the Yahoo team you're drafting"
    )
    parser.add_option(
        "--payouts",
        action="store",
        dest="payouts",
        help="comma separated string containing integer payouts for 1st, 2nd, and 3rd",
    )
    parser.add_option(
        "--sfb",
        action="store_true",
        dest="sfb",
        help="whether to use SFB scoring/settings throughout the draft",
    )
    options, args = parser.parse_args()
    league = fb.League(options.teamname,num_sims=10000,sfb=options.sfb)
    num_spots = sum([pos["roster_position"]["count"] for pos in league.settings["roster_positions"] if pos["roster_position"]["position"] != "IR"])
    num_teams = len(league.teams)
    if options.sfb and num_teams != 12:
        print("SFB13 uses 12 team divisions!!! Pick a different league!!!")
        sys.exit(0)

    # Validating payouts input
    if options.payouts:
        options.payouts = options.payouts.split(",")
        if all([val.isnumeric() for val in options.payouts]):
            options.payouts = [float(val) for val in options.payouts]
        else:
            print("Weird values provided for payouts... Assuming standard payouts...")
            options.payouts = [
                100 * len(league.teams) * 0.6,
                100 * len(league.teams) * 0.3,
                100 * len(league.teams) * 0.1,
            ]
        if len(options.payouts) > 3:
            print("Too many values provided for payouts... Only using top three...")
            options.payouts = options.payouts[:3]
    elif league.name == "The Algorithm":
        options.payouts = [720, 360, 120]
    elif league.name == "Toothless Wonders":
        options.payouts = [350, 100, 50]
    elif league.name == "The GENIEs":
        options.payouts = [100, 0, 0]
    elif league.name == "The Great Gadsby's":
        options.payouts = [50, 35, 15]
    else:
        options.payouts = [
            100 * len(league.teams) * 0.6,
            100 * len(league.teams) * 0.3,
            100 * len(league.teams) * 0.1,
        ]

    # SFB13 ADP Source: https://goingfor2.com/the-best-only-scott-fish-bowl-sfb13-sleeper-adp/
    adp = pd.read_csv("SFB13_ADP.csv")
    adp['name'] = adp['LAST NAME'] + ' ' + adp['FIRST NAME']
    missing = ~adp.name.isin(league.players.name.tolist())
    if missing.any():
        print("Name mismatches in ADP:")
        print(adp.loc[missing,['name','POSITION','TEAM']].to_string(index=False))
    adp = adp.rename(columns={'ADP':'avg_pick','POSITION':'position'})
    adp['avg_round'] = round(1.0 + adp.avg_pick/num_teams,1)
    adp['avg_pick'] = round(adp.avg_pick,1)
    league.players = pd.merge(left=league.players,right=adp[['name','position','avg_pick','avg_round']],how='left',on=['name','position'])
    display_cols = ['player_to_add','position','current_team','wins_avg','points_avg','playoffs','winner','earnings','avg_pick','avg_round']
    # SFB13 ADP Source: https://goingfor2.com/the-best-only-scott-fish-bowl-sfb13-sleeper-adp/

    tot_picks = num_teams*num_spots
    custom_order = input("Would you like to provide a custom draft order? ")
    league = provide_pick_order(league,custom_order.lower() in ["yes","y"])
    exclude = []
    pick_num = 0
    progress = pd.DataFrame()
    while pick_num < tot_picks:
        round_num = pick_num//num_teams + 1
        rel_pick = pick_num%num_teams
        if options.sfb and ((round_num > 2 and round_num%2 == 1) or round_num == 2): # 3rd round reversal
            rel_pick = num_teams - rel_pick - 1
        elif round_num%2 == 0 and not options.sfb:
            rel_pick = num_teams - rel_pick - 1
        
        pick_deets = 'Round #{}, Pick #{}, {}: '.format(round_num,pick_num + 1,league.teams[rel_pick]['name'])
        pick_name = check_pick_name(league,input(pick_deets),["best","nearest","next","lookup","exclude","go back","sim","roster"])
        while pick_name is None:
            pick_name = check_pick_name(league,input(pick_deets),["best","nearest","next","lookup","exclude","go back","sim","roster"])
        
        if pick_name in league.players.name.tolist():
            # What about players with the same name???
            league.players.loc[league.players.name == pick_name,'fantasy_team'] = league.teams[rel_pick]['name']
            progress = pd.concat([progress,league.players.loc[league.players.name == pick_name]],ignore_index=True,sort=False)
            progress.to_csv("DraftProgress.csv",index=False)
            pick_num += 1
        elif pick_name.lower() == "best":
            best = league.possible_adds([pick_name],exclude,limit_per=5,team_name="My Team",verbose=False,payouts=options.payouts)
            best = pd.merge(left=best,right=adp[['name','position','avg_pick','avg_round']]\
            .rename(columns={'name':'player_to_add'}),how='inner',on=['player_to_add','position'])
            print("Best players according to the Algorithm:")
            print(best[display_cols].to_string(index=False))
        elif pick_name.lower() == "nearest":
            nearby = league.players.loc[league.players.avg_pick <= pick_num + 2*num_teams,'name'].tolist()
            nearest = league.possible_adds(nearby,exclude,limit_per=5,team_name="My Team",verbose=False,payouts=options.payouts)
            nearest = pd.merge(left=nearest,right=adp[['name','position','avg_pick','avg_round']]\
            .rename(columns={'name':'player_to_add'}),how='inner',on=['player_to_add','position'])
            print("Best players in terms of ADP:")
            print(nearest[display_cols].to_string(index=False))
        elif pick_name.lower() == "lookup":
            focus = check_pick_name(league,input("Which player would you like to check? "),["nevermind"])
            while focus is None:
                focus = check_pick_name(league,input("Which player would you like to check? "),["nevermind"])
            if focus != "nevermind":
                lookup = league.possible_adds([pick_name],exclude,team_name="My Team",verbose=False,payouts=options.payouts)
                lookup = pd.merge(left=lookup,right=adp[['name','position','avg_pick','avg_round']]\
                .rename(columns={'name':'player_to_add'}),how='inner',on=['player_to_add','position'])
                print("Player of interest:")
                print(lookup[display_cols].to_string(index=False))
        elif pick_name.lower() == "exclude":
            ignore = check_pick_name(league,input("Which player would you like to exclude from consideration? "),["nevermind"])
            while ignore is None:
                ignore = check_pick_name(league,input("Which player would you like to exclude from consideration? "),["nevermind"])
            if ignore != "nevermind":
                exclude.append(ignore)
        elif pick_name.lower() == "go back":
            league.players.loc[league.players.name == progress.iloc[-1].name,'fantasy_team'] = None
            progress = progress.iloc[:-1].reset_index(drop=True)
            progress.to_csv("DraftProgress.csv",index=False)
            pick_num -= 1
        elif pick_name.lower() == "sim":
            standings_sim = league.season_sims(payouts=options.payouts)[1]
            print(standings_sim[['team','points_avg','wins_avg','playoffs','winner','earnings']].to_string(index=False))
        elif pick_name.lower() == "roster":
            print(league.players.loc[league.players.fantasy_team == "My Team",\
            ['name','position','current_team','points_avg','points_stdev','WAR']].to_string(index=False))


if __name__ == "__main__":
    main()
