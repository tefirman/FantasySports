
import pandas as pd
import os
import datetime
from util import sportsref_nfl as sr
import optparse
from pandas.tseries.holiday import USFederalHolidayCalendar
cal = USFederalHolidayCalendar()

def load_picks(schedule_loc: str = "NFLSchedule.csv", first: int = 1, last: int = 17):
    if os.path.exists(schedule_loc):
        schedule = pd.read_csv(schedule_loc)
    else:
        s = sr.Schedule(2015,datetime.datetime.now().year,False,True,False)
        schedule = s.schedule.copy()
        schedule.to_csv(schedule_loc,index=False)
    schedule = schedule.loc[schedule.season == datetime.datetime.now().year].reset_index(drop=True)
    picks = pd.concat([schedule[['week_num','game_date','team1_abbrev','elo_prob1']]\
    .rename(columns={'week_num':'week','team1_abbrev':'team','elo_prob1':'prob'}),\
    schedule[['week_num','game_date','team2_abbrev','elo_prob2']]\
    .rename(columns={'week_num':'week','team2_abbrev':'team','elo_prob2':'prob'})],ignore_index=True)
    picks = picks.loc[(picks.week >= first) & (picks.week <= last)].reset_index(drop=True)
    return picks

def best_combos(picks, limit: int = 10000):
    thanksgiving = cal.holidays(start='2023-11-15', end='2023-12-01').to_pydatetime()[0]
    picks_tg = picks.loc[picks.game_date == thanksgiving.strftime('%Y-%m-%d')].reset_index(drop=True)
    picks['dummy'] = 1
    combos = pd.DataFrame({'dummy':[1]})
    for week in range(picks.week.min(),picks.week.max() + 1):
        combos = pd.merge(left=combos,right=picks.loc[(picks.week == week) & (picks.prob >= 0.5),['dummy','team','prob']]\
        .rename(columns={'team':f'team_{week}a','prob':f'prob_{week}a'}),how='inner',on='dummy')
        if week%2 == 0:
            combos = pd.merge(left=combos,right=picks.loc[(picks.week == week) & (picks.prob >= 0.5),['dummy','team','prob']]\
            .rename(columns={'team':f'team_{week}b','prob':f'prob_{week}b'}),how='inner',on='dummy')
            combos = combos.loc[combos[f'team_{week}a'] < combos[f'team_{week}b']].reset_index(drop=True)
        if week == picks_tg.week.unique()[0]: # Thanksgiving
            combos = pd.merge(left=combos,right=picks.loc[(picks.week == week) & (picks.prob >= 0.5),['dummy','team','prob']]\
            .rename(columns={'team':f'team_{week}c','prob':f'prob_{week}c'}),how='inner',on='dummy')
            combos = combos.loc[combos[f'team_{week}b'] < combos[f'team_{week}c']].reset_index(drop=True)
            combos = combos.loc[combos[f'team_{week}a'].isin(picks_tg.team.tolist()) \
            | combos[f'team_{week}b'].isin(picks_tg.team.tolist()) \
            | combos[f'team_{week}c'].isin(picks_tg.team.tolist())].reset_index(drop=True)
        team_cols = [team for team in combos.columns if team.startswith('team_')]
        combos = combos.loc[combos[team_cols].nunique(axis=1) >= len(team_cols) - int(week >= 12)].reset_index(drop=True)
        combos['tot_prob'] = combos[[team for team in combos.columns if team.startswith('prob_')]].sum(axis=1)
        combos = combos.sort_values(by='tot_prob',ascending=False,ignore_index=True).iloc[:limit]
    del picks['dummy'], combos['dummy']
    return combos

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
        "--limit",
        action="store",
        type="int",
        dest="limit",
        default=10000,
        help="number of top lineups to keep during each merge for memory purposes",
    )
    parser.add_option(
        "--output",
        action="store",
        dest="output",
        default="",
        help="where to save the final projections spreadsheet",
    )
    options, args = parser.parse_args()
    picks = load_picks(options.schedule)
    combos = best_combos(picks,options.limit)

    writer = pd.ExcelWriter(options.output + "UltimateSurvivorCombos.xlsx",engine="xlsxwriter")
    writer.book.add_format({"align": "vcenter"})
    writer = excel_autofit(combos[[team for team in combos.columns if team.startswith('team_')] + ["tot_prob"]], "Season", writer)
    current_week = 'team_' + str(picks.week.min())
    teams = [team for team in combos.columns if team in [current_week + 'a',current_week + 'b',current_week + 'c']]
    this_week_pts = combos.groupby(teams).tot_prob.mean().reset_index()
    this_week_freq = combos.groupby(teams).size().to_frame('freq').reset_index()
    this_week_freq.freq /= options.limit
    this_week = pd.merge(left=this_week_pts,right=this_week_freq,how='inner',on=teams).sort_values(by='freq',ascending=False)
    writer = excel_autofit(this_week, "This Week", writer)
    for week in range(min(picks.week.min() + 1,18),min(picks.week.min() + 3,18)):
        current_week = 'team_' + str(week)
        teams += [team for team in combos.columns if team in [current_week + 'a',current_week + 'b',current_week + 'c']]
    three_week_pts = combos.groupby(teams).tot_prob.mean().reset_index()
    three_week_freq = combos.groupby(teams).size().to_frame('freq').reset_index()
    three_week_freq.freq /= options.limit
    three_week = pd.merge(left=three_week_pts,right=three_week_freq,how='inner',on=teams).sort_values(by='freq',ascending=False)
    writer = excel_autofit(three_week, "Next 3 Weeks", writer)
    writer.close()


if __name__ == "__main__":
    main()


