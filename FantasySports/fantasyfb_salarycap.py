#!/usr/bin/env python
# -*-coding:utf-8 -*-
'''
@File    :   fantasyfb_salarycap.py
@Time    :   2023/08/20 16:32:11
@Author  :   Taylor Firman
@Version :   1.0
@Contact :   tefirman@gmail.com
@Desc    :   Salary cap specific application of the Firman Fantasy Football Algorithm.
'''

import os
import pandas as pd
import numpy as np
import optparse
import fantasyfb as fb
from difflib import SequenceMatcher

def best_combos(positions, budget, league, limit=500, fixed="", exclude=[]):
    teams = pd.DataFrame({'dummy':[1]})
    tot = 0
    for pos in positions: # Sorting by relevancy...
        for num in range(positions[pos]):
            # print(pos + str(num + 1))
            if pos == "W/T":
                teams = pd.merge(left=teams,right=league.players.loc[league.players.position.isin(["WR","TE"]) & league.players.fantasy_team.isnull(),\
                ['dummy','name','WAR','avg_salary']].rename(columns={'name':'Name_' + pos + str(num + 1),\
                'WAR':'WAR_' + pos + str(num + 1),'avg_salary':'Salary_' + pos + str(num + 1)}),how='inner',on='dummy')
            elif pos == "W/R/T":
                teams = pd.merge(left=teams,right=league.players.loc[league.players.position.isin(["WR","RB","TE"]) & league.players.fantasy_team.isnull(),\
                ['dummy','name','WAR','avg_salary']].rename(columns={'name':'Name_' + pos + str(num + 1),\
                'WAR':'WAR_' + pos + str(num + 1),'avg_salary':'Salary_' + pos + str(num + 1)}),how='inner',on='dummy')
            elif pos == "Q/W/R/T":
                teams = pd.merge(left=teams,right=league.players.loc[league.players.position.isin(["WR","RB","TE","QB"]) & league.players.fantasy_team.isnull(),\
                ['dummy','name','WAR','avg_salary']].rename(columns={'name':'Name_' + pos + str(num + 1),\
                'WAR':'WAR_' + pos + str(num + 1),'avg_salary':'Salary_' + pos + str(num + 1)}),how='inner',on='dummy')
            else:
                teams = pd.merge(left=teams,right=league.players.loc[league.players.position.apply(lambda x: x in pos) & league.players.fantasy_team.isnull(),\
                ['dummy','name','WAR','avg_salary']].rename(columns={'name':'Name_' + pos + str(num + 1),\
                'WAR':'WAR_' + pos + str(num + 1),'avg_salary':'Salary_' + pos + str(num + 1)}),how='inner',on='dummy')
            teams['Total_Names'] = teams[[col for col in teams.columns if col.startswith('Name_')]].apply("_".join,axis=1)
            # Feels like this could be sped up...
            teams['Total_Names'] = teams['Total_Names'].str.split('_').apply(lambda x: '_'.join(sorted(np.unique(x))))
            # Feels like this could be sped up...
            teams = teams.loc[teams.Total_Names.str.count('_') == tot].drop_duplicates(subset=['Total_Names'])
            if fixed in league.players.name.tolist() and teams.Total_Names.str.contains(fixed).any():
                teams = teams.loc[teams.Total_Names.apply(lambda x: fixed in x.split('_'))].reset_index(drop=True)
            for player in exclude:
                if player in league.players.name.tolist():
                    teams = teams.loc[teams.Total_Names.apply(lambda x: player not in x.split('_'))].reset_index(drop=True)
            teams['Total_Salary'] = teams[[col for col in teams.columns if col.startswith('Salary_')]].sum(axis=1)
            teams = teams.loc[teams.Total_Salary <= budget]
            teams['Total_WAR'] = teams[[col for col in teams.columns if col.startswith('WAR_')]].sum(axis=1)
            teams = teams.sort_values(by='Total_WAR',ascending=False).iloc[:limit]
            tot += 1
    # Expanding salaries to fit budget
    for pos in positions:
        for num in range(positions[pos]):
            teams['Salary_' + pos + str(num + 1)] *= budget/teams['Total_Salary']
    return teams

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
        "--budget",
        action="store",
        type="int",
        dest="budget",
        default=200,
        help="amount of money each team is allocated during the auction",
    )
    parser.add_option(
        "--starterpct",
        action="store",
        type="float",
        dest="starterpct",
        default=0.875,
        help="percentage of your budget to allocate to starters",
    )
    parser.add_option(
        "--limit",
        action="store",
        type="int",
        dest="limit",
        default=500,
        help="maximum number of top lineups to consider each draft pick",
    )
    parser.add_option(
        "--keepers",
        action="store",
        dest="keepers",
        help="location of keeper details in the form of a csv",
    )
    parser.add_option(
        "--exclude",
        action="store",
        dest="exclude",
        help="comma separated string containing players to exclude from consideration",
    )
    parser.add_option(
        "--inprogress",
        action="store",
        dest="inprogress",
        help="location of the csv containing details about a draft already in progress",
    )
    parser.add_option(
        "--output",
        action="store",
        dest="output",
        help="where to save the draft progress csv",
    )
    options, args = parser.parse_args()

    league = fb.League(options.teamname)

    # # Redraft Prices Source: https://football.fantasysports.yahoo.com/f1/53063/draftanalysis?type=salcap
    # adp = pd.read_csv("Yahoo_2023_Overall_SalaryCap_Rankings_Redraft.csv")
    # Redraft Prices Source: https://football.fantasysports.yahoo.com/f1/draftanalysis?type=salcap
    adp = pd.read_csv("Yahoo_2024_Overall_SalaryCap_Rankings_Redraft.csv")
    corrections = pd.read_csv("https://raw.githubusercontent.com/tefirman/FantasySports/main/res/football/name_corrections.csv")
    adp = pd.merge(left=adp, right=corrections, how="left", on="name")
    to_fix = ~adp.new_name.isnull()
    adp.loc[to_fix, "name"] = adp.loc[to_fix, "new_name"]
    del adp['new_name']
    missing = ~adp.name.isin(league.players.name.tolist()) & ~adp.position.isin(['DEF']) & ~adp.name.isnull()
    if missing.any():
        print("Name mismatches in ADP:")
        print(adp.loc[missing,['name','position','yahoo_team']].to_string(index=False))
    league.players = pd.merge(left=league.players,right=adp[['name','position','avg_salary','proj_salary']],how='left',on=['name','position'])
    league.players['dummy'] = 1

    budget = options.budget*options.starterpct # ~90% of total draft salary cap, autodraft after that...
    positions = league.roster_spots.loc[~league.roster_spots.position.isin(["DEF", "K", "BN", "IR"])].set_index('position').to_dict()['count']
    bench_spots = league.roster_spots.loc[league.roster_spots.position.isin(["DEF", "K", "BN"]),'count'].sum()
    excluded = [val.strip() for val in options.exclude.split(',')] if options.exclude else []

    # Asking for keepers
    if os.path.exists(str(options.keepers) and options.keepers.endswith('.csv')):
        keepers = pd.read_csv(options.keepers).rename(columns={'fantasy_team':'keeper_team','salary':'actual_salary'})
        missing = ~keepers.name.isin(league.players.name.tolist())
        if missing.any():
            print("Player misspellings in keepers csv: " + ', '.join(keepers.loc[missing,'name'].tolist()))
        bad_teams = ~keepers.keeper_team.isin([team['name'] for team in league.teams])
        if bad_teams.any():
            print("Team misspellings in keepers csv: " + ', '.join(keepers.loc[bad_teams,'keeper_team'].tolist()))
        league.players = pd.merge(left=league.players,right=keepers,how='left',on='name')
        kept = ~league.players.keeper_team.isnull()
        league.players.loc[kept,'fantasy_team'] = league.players.loc[kept,'keeper_team']
        del league.players['keeper_team']
    else:
        keepers = input("Would you like to provide any keepers? (y/n) ")
        while keepers.lower() in ["yes","y"]:
            pick_name = check_pick_name(league,input("Player Being Kept: "))
            while pick_name is None:
                pick_name = check_pick_name(league,input("Player Being Kept: "))
            team_name = input("Team Keeping Them: ")
            while team_name not in [team['name'] for team in league.teams] + [team['manager'] for team in league.teams]:
                print("Name provided not in the list of accepted values: " + \
                ", ".join([team['name'] for team in league.teams] + [team['manager'] for team in league.teams]))
                team_name = input("Team Keeping Them: ")
            if team_name in [team['manager'] for team in league.teams]:
                team_name = [team['name'] for team in league.teams if team['manager'] == team_name][0]
            league.players.loc[league.players.name == pick_name,'fantasy_team'] = team_name
            salary_val = input("Salary of Player: ")
            while not salary_val.isnumeric():
                print("Salary must be an integer, try again...")
                salary_val = input("Salary of Player: ")
            league.players.loc[league.players.name == pick_name,'actual_salary'] = int(salary_val)
            if team_name == league.name:
                pos = league.players.loc[league.players.name == draft_pick,'position'].values[0]
                if positions[pos] > 0: # DEFENSES DUMMY!!!
                    positions[pos] -= 1
                elif positions['W/T'] > 0 and pos in ['WR','TE']:
                    positions['W/T'] -= 1
                elif positions['W/R/T'] > 0 and pos in ['WR','RB','TE']:
                    positions['W/R/T'] -= 1
                elif positions['Q/W/R/T'] > 0 and pos in ['QB','WR','RB','TE']:
                    positions['Q/W/R/T'] -= 1
                if pos not in ["DEF", "K"]:
                    budget -= int(salary_val)
            keepers = input("Would you like to provide any more keepers? (y/n) ")

    # BUDGET WASN'T MOVING CORRECTLY!!!
    # BUDGET WASN'T MOVING CORRECTLY!!!
    # BUDGET WASN'T MOVING CORRECTLY!!!

    avg_team = pd.concat(3*[league.players.loc[league.players.player_id_sr.astype(str).str.startswith('avg_')]],ignore_index=True,sort=False)
    if league.name == "Toothless Wonders":
        avg_team = avg_team.loc[~avg_team.player_id_sr.isin(['avg_QB'])].reset_index(drop=True)
    for team in league.teams:
        avg_team['fantasy_team'] = team["name"]
        league.players = pd.concat([league.players,avg_team.copy()],ignore_index=True,sort=False)

    # Calculating leagues spending trends
    league.players['delta'] = league.players['actual_salary'] - league.players['avg_salary']
    league_pace = league.players.loc[~league.players.fantasy_team.isnull() & ~league.players.fantasy_team.isin([league.name]),'delta'].mean()
    my_pace = league.players.loc[league.players.fantasy_team.isin([league.name]),'delta'].mean()

    remerge = True
    while all([sum(positions.values()) > 0,league.players.shape[0] > 0,budget > 0]):
        if remerge:
            teams = best_combos(positions, budget, league, limit=options.limit, exclude=excluded)
            remerge = False

        # Identifying nominated player
        print("")
        draft_pick = check_pick_name(league,input("Player Up For Grabs: "),["best","lookup","sim","roster"])
        while draft_pick is None:
            draft_pick = check_pick_name(league,input("Player Up For Grabs: "),["best","lookup","sim","roster"])
        if draft_pick == "best":
            best = pd.DataFrame({'Player':'_'.join(teams.Total_Names.tolist()).split('_')})
            best = best.groupby('Player').size().sort_values(ascending=False).to_frame('% of Teams').iloc[:20].reset_index()
            best['% of Teams'] = 100*best['% of Teams']/options.limit
            for ind in range(best.shape[0]):
                salaries = []
                for pos in positions:
                    for num in range(positions[pos]):
                        salaries += teams.loc[teams['Name_' + pos + str(num + 1)] == best.loc[ind,'Player'],'Salary_' + pos + str(num + 1)].tolist()
                best.loc[ind,'Avg Salary'] = '$' + "{:.2f}".format(np.average(salaries)) + ' ± ' + "{:.2f}".format(np.std(salaries))
                best.loc[ind,'Max Salary'] = '$' + "{:.2f}".format(max(salaries))
                best.loc[ind,'WAR'] = league.players.loc[league.players.name == best.loc[ind,'Player'],'WAR'].values[0]
            if (teams.Total_Names.str.count('_') <= 1).all(): # Sort by WAR if only one player left...
                best = best.sort_values(by='WAR',ascending=False).reset_index(drop=True)
            print(best)
            print('Best Possible Team: ' + teams.iloc[0].Total_Names.replace('_',', '))
            print('Best Possible WAR: ' + str(round(teams.iloc[0].Total_WAR,2)))
        elif draft_pick.lower() == "lookup":
            focus = check_pick_name(league,input("Which player would you like to check? "),["nevermind"])
            while focus is None:
                focus = check_pick_name(league,input("Which player would you like to check? "),["nevermind"])
            if focus != "nevermind":
                print('Player WAR: ' + str(round(league.players.loc[league.players.name == focus,'WAR'].values[0],2)))
                print('Avg Yahoo Salary: $' + "{:.2f}".format(league.players.loc[league.players.name == focus,'avg_salary'].values[0]))
                print('Proj Yahoo Salary: $' + "{:.2f}".format(league.players.loc[league.players.name == focus,'proj_salary'].values[0]))
                lookup_teams = best_combos(positions, budget, league, limit=options.limit, fixed=focus, exclude=excluded)
                print("Avg Team WAR = {}".format(round(lookup_teams.Total_WAR.mean(),3)))
                print("Current Best WAR = {}".format(round(teams.Total_WAR.mean(),3)))
                print("Delta WAR = {}".format(round(teams.Total_WAR.mean() - lookup_teams.Total_WAR.mean(),3)))
        elif draft_pick.lower() == "sim":
            standings_sim = league.season_sims()[1]
            print(standings_sim[['team','points_avg','wins_avg','playoffs','winner','earnings']].to_string(index=False))
        elif draft_pick.lower() == "roster":
            print(league.players.loc[league.players.fantasy_team == league.name,\
            ['name','position','current_team','points_avg','points_stdev','WAR']].to_string(index=False))
        elif draft_pick in league.players.name.tolist():
            print('Player WAR: ' + str(round(league.players.loc[league.players.name == draft_pick,'WAR'].values[0],2)))
            print('Avg Yahoo Salary: $' + "{:.2f}".format(league.players.loc[league.players.name == draft_pick,'avg_salary'].values[0]))
            print('Proj Yahoo Salary: $' + "{:.2f}".format(league.players.loc[league.players.name == draft_pick,'proj_salary'].values[0]))
            pick_teams = best_combos(positions, budget, league, limit=options.limit, fixed=draft_pick, exclude=excluded)
            print("Avg Team WAR = {}".format(round(pick_teams.Total_WAR.mean(),3)))
            print("Current Best WAR = {}".format(round(teams.Total_WAR.mean(),3)))
            print("Delta WAR = {}".format(round(teams.Total_WAR.mean() - pick_teams.Total_WAR.mean(),3)))

            # For player in question, find max spending in top teams
            salaries = []
            present = 0
            for pos in positions:
                for num in range(positions[pos]):
                    salaries += teams.loc[teams['Name_' + pos + str(num + 1)] == draft_pick,'Salary_' + pos + str(num + 1)].tolist()
                    present += teams.loc[teams['Name_' + pos + str(num + 1)] == draft_pick].shape[0]
            if len(salaries) == 0:
                print('Not present in top ' + str(options.limit) + ' teams...')
            else:
                print('Present in ' + "{:.1f}".format(100*present/options.limit) + '% of top ' + str(options.limit) + ' teams')
                print('Avg Salary in Best Teams: $' + "{:.2f}".format(np.average(salaries)) + ' +/- ' + "{:.2f}".format(np.std(salaries)))
                print('Max Salary in Best Teams: $' + "{:.2f}".format(max(salaries)))
                remerge = True
            
            print("League Spending Pace: " + str(round(league_pace,2)))
            print("My Spending Pace: " + str(round(my_pace,2)))

            team_name = input("Who picked them? ")
            while team_name not in [team['name'] for team in league.teams] + [team['manager'] for team in league.teams]:
                print("Name provided not in the list of accepted values: " + \
                ", ".join([team['name'] for team in league.teams] + [team['manager'] for team in league.teams]))
                team_name = input("Who picked them? ")
            if team_name in [team['manager'] for team in league.teams]:
                team_name = [team['name'] for team in league.teams if team['manager'] == team_name][0]
            league.players.loc[league.players.name == draft_pick,'fantasy_team'] = team_name
            salary_val = input("How much did they pay? ")
            while not salary_val.isnumeric():
                print("Salary must be an integer, try again...")
                salary_val = input("How much did they pay? ")
            league.players.loc[league.players.name == draft_pick,'actual_salary'] = int(salary_val)
            league.players.loc[~league.players.fantasy_team.isnull() & ~league.players.name.str.startswith('Average_'),\
            ['name','fantasy_team','actual_salary']].rename(columns={"actual_salary":"salary"}).to_csv("DraftProgressSalaryCap.csv",index=False)
            league.players['delta'] = league.players['actual_salary'] - league.players['avg_salary']
            league_pace = league.players.loc[~league.players.fantasy_team.isnull() & ~league.players.fantasy_team.isin([league.name]),'delta'].mean()
            my_pace = league.players.loc[league.players.fantasy_team.isin([league.name]),'delta'].mean()
            if team_name == league.name:
                pos = league.players.loc[league.players.name == draft_pick,'position'].values[0]
                if positions[pos] > 0: # DEFENSES DUMMY!!!
                    positions[pos] -= 1
                elif positions['W/T'] > 0 and pos in ['WR','TE']:
                    positions['W/T'] -= 1
                elif positions['W/R/T'] > 0 and pos in ['WR','RB','TE']:
                    positions['W/R/T'] -= 1
                elif positions['Q/W/R/T'] > 0 and pos in ['QB','WR','RB','TE']:
                    positions['Q/W/R/T'] -= 1
                budget -= int(salary_val)
                remerge = True

    # Using possible_adds and assuming you'll be spending $1 or $2 from here out...
    league.num_sims = 1000
    display_cols = ['player_to_add','position','current_team','WAR','wins_avg','points_avg','playoffs','winner','earnings','avg_pick','avg_round']
    while bench_spots > 0:
        draft_pick = check_pick_name(league,input("Player Up For Grabs: "),["best","lookup","sim","roster"])
        while draft_pick is None:
            draft_pick = check_pick_name(league,input("Player Up For Grabs: "),["best","lookup","sim","roster"])
        if draft_pick == "best":
            best = league.possible_adds([],excluded,limit_per=5,team_name=league.name,\
            verbose=False,payouts=options.payouts,bestball=True)
            print("Best players according to the Algorithm:")
            print(best[display_cols].to_string(index=False))
        elif pick_name.lower() == "lookup":
            focus = check_pick_name(league,input("Which player would you like to check? "),["nevermind"])
            while focus is None:
                focus = check_pick_name(league,input("Which player would you like to check? "),["nevermind"])
            if focus != "nevermind":
                lookup = league.possible_adds([focus],excluded,team_name=league.name,\
                verbose=False,payouts=options.payouts,bestball=options.bestball)
                print("Player of interest:")
                print(lookup[display_cols].to_string(index=False))
        elif draft_pick.lower() == "sim":
            standings_sim = league.season_sims()[1]
            print(standings_sim[['team','points_avg','wins_avg','playoffs','winner','earnings']].to_string(index=False))
        elif draft_pick.lower() == "roster":
            print(league.players.loc[league.players.fantasy_team == league.name,\
            ['name','position','current_team','points_avg','points_stdev','WAR']].to_string(index=False))
        elif draft_pick in league.players.name.tolist():
            team_name = input("Who picked them? ")
            while team_name not in [team['name'] for team in league.teams] + [team['manager'] for team in league.teams]:
                print("Name provided not in the list of accepted values: " + \
                ", ".join([team['name'] for team in league.teams] + [team['manager'] for team in league.teams]))
                team_name = input("Who picked them? ")
            if team_name in [team['manager'] for team in league.teams]:
                team_name = [team['name'] for team in league.teams if team['manager'] == team_name][0]
            league.players.loc[league.players.name == draft_pick,'fantasy_team'] = team_name
            salary_val = input("How much did they pay? ")
            while not salary_val.isnumeric():
                print("Salary must be an integer, try again...")
                salary_val = input("How much did they pay? ")
            if team_name == league.name:
                bench_spots -= 1
    
    # Simulating season as a general assessment
    league.num_sims = 10000
    standings_sim = league.season_sims(payouts=options.payouts)[1]
    print(standings_sim[['team','points_avg','wins_avg','playoffs','winner','earnings']].to_string(index=False))
    standings_sim.to_csv('DraftResults.csv',index=False)
    my_results = standings_sim.reset_index(drop=True).loc[standings_sim.team == league.name]
    if my_results.index[0] < standings_sim.shape[0]/4:
        print("You crushed it!!! Way to go!!!")
    elif my_results.index[0] >= standings_sim.shape[0]/4 \
    and my_results.index[0] < standings_sim.shape[0]/2:
        print("Pretty darn good, but we'll see... Good luck!!!")
    elif my_results.index[0] >= standings_sim.shape[0]/2 \
    and my_results.index[0] < 3*standings_sim.shape[0]/4:
        print("Not great, but you can recover... Hit the waiver wire hard!!!")
    else:
        print("Less than ideal... but you have so many other redeeming qualities!!!")


if __name__ == "__main__":
    main()


