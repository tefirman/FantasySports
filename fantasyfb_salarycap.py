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

import pandas as pd
import numpy as np
import optparse
import fantasyfb as fb
from difflib import SequenceMatcher

def best_combos(positions, budget, league, limit=1000):
    teams = pd.DataFrame({'dummy':[1]})
    tot = 0
    for pos in positions: # Sorting by relevancy...
        for num in range(positions[pos]):
            # print(pos + str(num + 1))
            if pos == "W/T":
                teams = pd.merge(left=teams,right=league.players.loc[league.players.position.isin(["WR","TE"]),\
                ['dummy','name','WAR','avg_salary']].rename(columns={'name':'Name_' + pos + str(num + 1),\
                'WAR':'WAR_' + pos + str(num + 1),'avg_salary':'Salary_' + pos + str(num + 1)}),how='inner',on='dummy')
            elif pos == "W/R/T":
                teams = pd.merge(left=teams,right=league.players.loc[league.players.position.isin(["WR","RB","TE"]),\
                ['dummy','name','WAR','avg_salary']].rename(columns={'name':'Name_' + pos + str(num + 1),\
                'WAR':'WAR_' + pos + str(num + 1),'avg_salary':'Salary_' + pos + str(num + 1)}),how='inner',on='dummy')
            elif pos == "Q/W/R/T":
                teams = pd.merge(left=teams,right=league.players.loc[league.players.position.isin(["WR","RB","TE","QB"]),\
                ['dummy','name','WAR','avg_salary']].rename(columns={'name':'Name_' + pos + str(num + 1),\
                'WAR':'WAR_' + pos + str(num + 1),'avg_salary':'Salary_' + pos + str(num + 1)}),how='inner',on='dummy')
            else:
                teams = pd.merge(left=teams,right=league.players.loc[league.players.position.apply(lambda x: x in pos),\
                ['dummy','name','WAR','avg_salary']].rename(columns={'name':'Name_' + pos + str(num + 1),\
                'WAR':'WAR_' + pos + str(num + 1),'avg_salary':'Salary_' + pos + str(num + 1)}),how='inner',on='dummy')
            teams['Total_Names'] = teams[[col for col in teams.columns if col.startswith('Name_')]].apply("_".join,axis=1)
            """ Feels like this could be sped up... """
            teams['Total_Names'] = teams['Total_Names'].str.split('_').apply(lambda x: '_'.join(sorted(np.unique(x))))
            """ Feels like this could be sped up... """
            teams = teams.loc[teams.Total_Names.str.count('_') == tot].drop_duplicates(subset=['Total_Names'])
            teams['Total_Salary'] = teams[[col for col in teams.columns if col.startswith('Salary_')]].sum(axis=1)
            teams = teams.loc[teams.Total_Salary <= budget]
            teams['Total_WAR'] = teams[[col for col in teams.columns if col.startswith('WAR_')]].sum(axis=1)
            teams = teams.sort_values(by='Total_WAR',ascending=False).iloc[:limit]
            tot += 1
    """ Expanding salaries to fit budget """
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
        default=0.9,
        help="percentage of your budget to allocate to starters",
    )
    parser.add_option(
        "--limit",
        action="store",
        type="int",
        dest="limit",
        default=10000,
        help="maximum number of top lineups to consider each draft pick",
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

    # Redraft Prices Source: https://football.fantasysports.yahoo.com/f1/53063/draftanalysis?type=salcap
    adp = pd.read_csv("Yahoo_2023_Overall_SalaryCap_Rankings_Redraft.csv")
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
    positions = league.roster_spots.loc[~league.roster_spots.position.isin(["BN", "IR"])].set_index('position').to_dict()['count']

    # ASK FOR KEEPERS HERE!!!
    keepers = input("Would you like to provide any keepers? (y/n) ")
    while keepers.lower() in ["yes","y"]:
        pick_name = check_pick_name(league,input("Player Being Kept: "))
        while pick_name is None:
            pick_name = check_pick_name(league,input("Player Being Kept: "))
        team_name = input("Team Keeping Them: ")
        while team_name not in [team['name'] for team in league.teams]:
            print("Name provided not in the list of accepted values: " + ", ".join([team['name'] for team in league.teams]))
            team_name = input("Team Keeping Them: ")
        league.players.loc[league.players.name == pick_name,'fantasy_team'] = team_name
        salary_val = check_pick_name(league,input("Salary of Player: "))
        while not salary_val.isnumeric():
            print("Salary must be an integer, try again...")
            salary_val = check_pick_name(league,input("Salary of Player: "))
        league.players.loc[league.players.name == pick_name,'actual_salary'] = int(salary_val)
        if team_name == league.name:
            pos = league.players.loc[league.players.name == draft_pick,'position'].values[0]
            if positions[pos] > 0:
                positions[pos] -= 1
            elif positions['W/T'] > 0 and pos in ['WR','TE']:
                positions['W/T'] -= 1
            elif positions['W/R/T'] > 0 and pos in ['WR','RB','TE']:
                positions['W/R/T'] -= 1
            elif positions['Q/W/R/T'] > 0 and pos in ['QB','WR','RB','TE']:
                positions['Q/W/R/T'] -= 1
            budget -= int(salary_val)
        keepers = input("Would you like to provide any more keepers? (y/n) ")
    # ASK FOR KEEPERS HERE!!!

    # CALCULATE LEAGUE SPENDING TRENDS AS WELL AS YOUR OWN!!!
    # CALCULATE LEAGUE SPENDING TRENDS AS WELL AS YOUR OWN!!!
    # CALCULATE LEAGUE SPENDING TRENDS AS WELL AS YOUR OWN!!!

    remerge = True
    while all([sum(positions.values()) > 0,league.players.shape[0] > 0,budget > 0]):
        if remerge:
            teams = best_combos(positions, budget, league)

        """ Identifying nominated player """
        draft_pick = input("Player Up For Grabs: ")
        while draft_pick not in league.players.name.tolist():
            if draft_pick == 'best':
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
            else:
                league.players['similarity'] = league.players.name.apply(lambda x: SequenceMatcher(None, x, draft_pick).ratio())
                print("Couldn't find an exact match for " + '"' + draft_pick + '"... Closest matches:')
                print(league.players.sort_values(by='similarity',ascending=False).iloc[:3][['name','position','current_team']].to_string(index=False))
            draft_pick = input("Player Up For Grabs: ")
        
        """ For player in question, find max spending in top teams """
        salaries = []
        present = 0
        for pos in positions:
            for num in range(positions[pos]):
                salaries += teams.loc[teams['Name_' + pos + str(num + 1)] == draft_pick,'Salary_' + pos + str(num + 1)].tolist()
                present += teams.loc[teams['Name_' + pos + str(num + 1)] == draft_pick].shape[0]
        if len(salaries) == 0:
            print('Not present in top ' + str(options.limit) + ' teams...')
            print('WAR: ' + str(league.players.loc[league.players.name == draft_pick,'WAR'].values[0]))
            print('Avg Yahoo Salary: $' + "{:.2f}".format(league.players.loc[league.players.name == draft_pick,'avg_salary'].values[0]))
            print('Proj Yahoo Salary: $' + "{:.2f}".format(league.players.loc[league.players.name == draft_pick,'proj_salary'].values[0]))
            remerge = False
        else:
            print('Present in ' + "{:.1f}".format(100*present/options.limit) + '% of top ' + str(options.limit) + ' teams')
            print('WAR: ' + str(league.players.loc[league.players.name == draft_pick,'WAR'].values[0]))
            print('Avg Salary: $' + "{:.2f}".format(np.average(salaries)) + ' +/- ' + "{:.2f}".format(np.std(salaries)))
            print('Max Salary: $' + "{:.2f}".format(max(salaries)))
            remerge = True
        
        ans = ''
        while ans.lower() not in ['yes','no','y','n']:
            ans = input('Did you draft them? ')
        if ans.lower() in ['yes','y']:
            pos = league.players.loc[league.players.name == draft_pick,'position'].values[0]
            if positions[pos] > 0:
                positions[pos] -= 1
            elif positions['W/T'] > 0 and pos in ['WR','TE']:
                positions['W/T'] -= 1
            elif positions['W/R/T'] > 0 and pos in ['WR','RB','TE']:
                positions['W/R/T'] -= 1
            elif positions['Q/W/R/T'] > 0 and pos in ['QB','WR','RB','TE']:
                positions['Q/W/R/T'] -= 1
            cost = ''
            while not cost.isnumeric():
                cost = input('How much did you pay? ')
            budget -= int(cost)
            remerge = True
        
        league.players = league.players.loc[league.players.name != draft_pick]

    print("You've got your starters!!! Here are the best remaining players for your bench:")
    print(league.players.iloc[:20])
    league.players.to_excel('RemainingPlayers.xlsx',index=False)


if __name__ == "__main__":
    main()


