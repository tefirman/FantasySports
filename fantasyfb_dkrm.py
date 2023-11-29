
import pandas as pd
import datetime
import fantasyfb as fb
from util import sportsref_nfl as sr
import matplotlib.pyplot as plt
import numpy as np
import os
import sys
import optparse

class Collection:
    def __init__(self, date: str = None, rarity: str = None):
        if date is None:
            self.date = datetime.datetime.now()
        elif type(date) == str:
            try:
                self.date = pd.to_datetime(date)
            except:
                print("Can't recognize datetime format, exiting...")
                sys.exit(0)
        elif type(date) in [datetime.datetime,pd._libs.tslibs.timestamps.Timestamp]:
            self.date = date
        else:
            print("Date needs to be in string or datetime format, exiting...")
            sys.exit(0)
        self.load_raw_data()
        self.clean_data()
        self.load_cards(rarity=rarity)
        self.load_ff_league()
        self.add_proj_pts()
        self.add_proj_price()

    def load_raw_data(self):
        players_loc = "DKRM_{}.txt".format(self.date.strftime('%m%d%y'))
        if not os.path.exists(players_loc):
            print("Can't find RM player data at specified location... Try again...")
            sys.exit(0)
        tempData = open(players_loc,"r")
        raw_vals = tempData.read().split("""\nBUY NOW\n""")[-1].split("""\nTOTAL\n""")[-1]\
        .split("""\nDraftKings Inc.\n""")[0].replace("\nQ\n","\n").replace("\nIR\n","\n").replace("\nOUT\n","\n")\
        .replace("\nD\n","\n").replace("WR\n-\n","WR\n\n0.0\n").replace("RB\n-\n","RB\n\n0.0\n")\
        .replace("K\n-\n","K\n\n0.0\n").replace("TE\n-\n","TE\n\n0.0\n").replace("QB\n-\n","QB\n\n0.0\n").split("\n")
        tempData.close()
        names = raw_vals[::14]
        team_pos = raw_vals[2::14]
        ffpg = raw_vals[5::14]
        opponent = raw_vals[6::14]
        opp_rank = raw_vals[8::14]
        price = raw_vals[10::14]
        pts_per_dollar = raw_vals[11::14]
        owned = raw_vals[12::14]
        self.players = pd.DataFrame({"name":names,"team_pos":team_pos,"ffpg":ffpg,"opponent":opponent,\
        "opp_rank":opp_rank,"price":price,"pts_per_dollar":pts_per_dollar,"owned":owned})
    
    def clean_data(self):
        self.players = self.players.loc[~self.players.price.isin(['-'])].reset_index(drop=True)
        self.players = self.players.loc[~self.players.price.str.contains('K')].reset_index(drop=True) # Excluding super high listings, most likely mistakes...
        self.players["price"] = self.players["price"].str[1:].astype(float)
        self.players["opp_rank"] = self.players["opp_rank"].str.replace('th','').str.replace('st','').str.replace('rd','').str.replace('nd','').astype(float,errors="ignore")
        self.players["pts_per_dollar"] = self.players["pts_per_dollar"].str.replace('-','0.0').str.replace('<','').astype(float)
        self.players.loc[self.players.ffpg.isin(['-']),'ffpg'] = '0.0'
        self.players["ffpg"] = self.players["ffpg"].astype(float)
        self.players["home_game"] = self.players.opponent.str.startswith("@ ")
        self.players["opponent"] = self.players.opponent.str.replace("@ ","")
        for team in self.players.opponent.unique():
            self.players.loc[self.players.team_pos.str.startswith(team),'team'] = team
            self.players.loc[self.players.team_pos.str.startswith(team),'pos'] = \
            self.players.loc[self.players.team_pos.str.startswith(team),'team_pos'].str.replace(team,"")
        del self.players['team_pos']
    
    def load_cards(self, rarity: str = "Core", series: int = datetime.datetime.now().year):
        cards_loc = "{}_tefirman_mycards.csv".format(self.date.strftime('%Y-%m-%d'))
        if not os.path.exists(cards_loc):
            print("Can't find card data at specified location... Try again...")
            sys.exit(0)
        self.cards = pd.read_csv(cards_loc)
        self.cards = self.cards.loc[self.cards.Series == series].reset_index(drop=True)
        self.cards['name'] = self.cards['FirstName'].str[0] + '. ' + self.cards['LastName']
        self.cards['listable'] = ~self.cards.Set.isin(['Starter'])
        self.cards['my_card'] = True
        if str(rarity).title() in ["Core","Rare","Elite","Legendary","Reignmaker"]:
            self.cards = self.cards.loc[self.cards.Rarity == rarity.title()].reset_index(drop=True)
        self.players = pd.merge(left=self.players,right=self.cards[['name','Position','my_card','listable','Set']]\
        .rename(columns={'Position':'pos'}),how='left',on=['name','pos'])
        self.players.listable = self.players.listable.fillna(False)
        self.players.my_card = self.players.my_card.fillna(False)

    def load_ff_league(self, schedule_loc: str = "NFLSchedule.csv"):
        if os.path.exists(str(schedule_loc)):
            schedule = pd.read_csv(schedule_loc)
        else:
            s = sr.Schedule(2015,datetime.datetime.now().year,False,True,False)
            schedule = s.schedule.copy()
            schedule.to_csv(schedule_loc,index=False)
        try:
            schedule.game_date = pd.to_datetime(schedule.game_date, format="%Y-%m-%d")
        except:
            schedule.game_date = pd.to_datetime(schedule.game_date, format="%m/%d/%y") # Accounting for manual updates to schedule csv... Thanks Excel...
        season, week = schedule.loc[schedule.game_date >= self.date,['season','week']].values[0]
        self.league = fb.League("The GENIEs", season, week)
        self.league.players['name'] = self.league.players['name'].str.split(' ').str[0].str[:1] + \
        '. ' + self.league.players['name'].str.split(' ').str[1:].apply(' '.join)
        self.league.players.loc[self.league.players.player_id_sr.isin(['RobiAl02']),'name'] += ' II'
        self.league.players.loc[self.league.players.player_id_sr.isin(['WilsCe01','MimsMa00','HardMe00',\
        'CharDJ00','ParhDo00','JameRi00','WilsJe01','JoneMa02','EtieTr00','StroPi00','JoneTo04']),'name'] += ' Jr.'
        self.league.players.loc[self.league.players.player_id_sr.isin(['MetcJo00','McClRa00','AustCa00']),'name'] += ' III'
        self.league.players.loc[self.league.players.position == 'DEF','name'] = \
        self.league.players.loc[self.league.players.position == 'DEF','current_team']
        self.league.nfl_teams.yahoo = self.league.nfl_teams.yahoo.str.upper()
    
    def add_proj_pts(self):
        self.players = pd.merge(left=self.players,right=self.league.nfl_teams[["yahoo","real_abbrev"]]\
        .rename(columns={"yahoo":"team","real_abbrev":"current_team"}),how='inner',on=["team"])
        del self.players["team"]
        defense = ~self.players.pos.isin(['QB','RB','WR','TE','K'])
        self.idp_names = self.players.loc[defense,['name','current_team','price']]
        self.players.loc[defense,'pos'] = 'DEF'
        self.players.loc[defense,'name'] = self.players.loc[defense,'current_team'] # current_team isn't there...
        self.players = pd.concat([self.players.loc[~self.players.pos.isin(['DEF'])],\
        self.players.loc[self.players.pos.isin(['DEF'])].sort_values(by='my_card',ascending=False)\
        .drop_duplicates(subset=['name'])],ignore_index=True)
        self.players = pd.merge(left=self.players,right=self.league.players[["name","current_team",\
        "WAR","points_avg","pct_rostered","string","until"]],how='inner',on=["name","current_team"])
        # Excluding J. Williams from DEN for now, but need to fix this...
        self.players = self.players.loc[~self.players['name'].isin(['J. Williams']) \
        | ~self.players['current_team'].isin(['DEN'])].reset_index(drop=True)
        self.idp_names = pd.merge(left=self.idp_names,right=self.players.loc[self.players.pos.isin(['DEF']),["current_team","points_avg"]],how='inner',on='current_team')
    
    def add_proj_price(self, plot_proj=False):
        self.coeffs = {}
        for pos in ['QB','RB','WR','TE','K']:
            poi = self.players.pos.isin([pos]) & (self.players.pct_rostered >= 0.05) & (self.players.string < 2)
            self.coeffs[pos] = np.polyfit(self.players.loc[poi,'points_avg'].tolist(),self.players.loc[poi,'price'].tolist(),1)
            self.players.loc[self.players.pos.isin([pos]),'proj_price'] = self.players.loc[self.players.pos.isin([pos]),'points_avg']*self.coeffs[pos][0] + self.coeffs[pos][1]
            if plot_proj:
                plt.figure()
                plt.plot(self.players.points_avg,self.players.price,'.b')
                plt.plot(np.arange(5.0,25.01,0.1),np.arange(5.0,25.01,0.1)*self.coeffs[pos][0] + self.coeffs[pos][1],'r')
                plt.xlabel("Avg Points")
                plt.ylabel("Price ($)")
                plt.title(pos)
                plt.grid(True)
                plt.legend(["Actual","Linear Fit"])
                plt.savefig("DKRM_PointsVsPrice_{}.pdf".format(pos))
                plt.close()
        self.players['price_delta'] = self.players['proj_price'] - self.players['price']
    
    def print_values(self, limit=10):
        uninjured = self.players.until.isnull() | (self.players.until < 17)
        starters = self.players.string < 2
        cols = ["name","pos","current_team","points_avg","WAR","price","proj_price","price_delta"]
        print("\nBest Values")
        print(self.players.loc[uninjured & starters,cols].sort_values(by="price_delta",ascending=False).groupby('pos').head(limit).to_string(index=False))
        print("\nWorst Values")
        print(self.players.loc[uninjured & starters,cols].sort_values(by="price_delta",ascending=True).groupby('pos').head(limit).to_string(index=False))
        print("My Listable Cards")
        print(self.players.loc[self.players.my_card & self.players.listable].sort_values(by="price_delta").to_string(index=False))
    
    def best_lineups(self, stacks={}, superstars=[], limit=1000):
        self.players['dummy'] = 1
        if 'taken' not in self.players.columns:
            self.players["taken"] = False
        
        # INCORPORATE DIFFERENT CONTEST TYPES!!!
        positions = {"QB":1,"WR":2,"RB":2,"TE":1,"K":1,'DEF':1}
        # INCORPORATE DIFFERENT CONTEST TYPES!!!

        lineups = pd.DataFrame({'dummy':[1]})
        uninjured = self.players.until.isnull() | (self.players.until < self.league.current_week)
        for pos in positions:
            for ind in range(positions[pos]):
                lineups = pd.merge(left=lineups,right=self.players.loc[self.players.pos.isin([pos]) \
                & self.players.my_card & ~self.players.taken & uninjured,['name','points_avg','price','dummy']]\
                .rename(columns={col:"{}_{}{}".format(col,pos,ind + 1) for col in ["name","points_avg","price"]}),how='inner',on='dummy')
                lineups['points_avg'] = lineups[[col for col in lineups.columns if col.startswith('points_avg_')]].sum(axis=1)
                lineups['price'] = lineups[[col for col in lineups.columns if col.startswith('price_')]].sum(axis=1)
                name_cols = [col for col in lineups.columns if col.startswith('name_')]
                lineups['name'] = lineups[name_cols].apply(sorted,axis=1).apply(", ".join)
                lineups = lineups.drop_duplicates(subset=["name"],ignore_index=True)
                lineups = lineups.loc[lineups[name_cols].nunique(axis=1) == len(name_cols)].reset_index(drop=True)
                # ACCOUNT FOR STACKS A BIT MORE GENERICALLY!!!
                # ACCOUNT FOR STACKS A BIT MORE GENERICALLY!!!
                # ACCOUNT FOR STACKS A BIT MORE GENERICALLY!!!
            if pos in stacks:
                for qb in stacks[pos]:
                    if not lineups['name'].str.contains(qb).any():
                        continue
                    for stack in stacks[pos][qb]:
                        lineups = lineups.loc[~lineups['name'].str.contains(qb) | lineups['name'].str.contains(stack)]
                        lineups = lineups.loc[lineups['name'].str.contains(qb) | ~lineups['name'].str.contains(stack)]
            
            lineups['superstars'] = lineups['name'].apply(lambda x: len([val for val in x.split(', ') if val in superstars]))
            lineups = lineups.loc[lineups.superstars <= 1].reset_index(drop=True)

            lineups = lineups.sort_values(by='points_avg',ascending=False,ignore_index=True)
            # lineups = lineups.sort_values(by='price',ascending=False,ignore_index=True)
            lineups = lineups.groupby('name_QB1').head(limit).reset_index(drop=True) # Switch this to CPT for showdowns...
        lineups = pd.merge(left=lineups,right=self.players.loc[~self.players.pos.isin(['QB']) \
        & self.players.my_card & ~self.players.taken & uninjured,['name','points_avg','price','dummy']]\
        .rename(columns={col:"{}_{}{}".format(col,pos,ind + 1) for col in ["name","points_avg","price"]}),how='inner',on='dummy')
        lineups['points_avg'] = lineups[[col for col in lineups.columns if col.startswith('points_avg_')]].sum(axis=1)
        lineups['price'] = lineups[[col for col in lineups.columns if col.startswith('price_')]].sum(axis=1)
        name_cols = [col for col in lineups.columns if col.startswith('name_')]
        lineups['name'] = lineups[name_cols].apply(sorted,axis=1).apply(", ".join)
        lineups = lineups.drop_duplicates(subset=["name"],ignore_index=True)
        lineups = lineups.loc[lineups[name_cols].nunique(axis=1) == len(name_cols)].reset_index(drop=True)
        for pos in stacks:
            for qb in stacks[pos]:
                if not lineups['name'].str.contains(qb).any():
                    continue
                for stack in stacks[pos][qb]:
                    lineups = lineups.loc[~lineups['name'].str.contains(qb) | lineups['name'].str.contains(stack)]
                    lineups = lineups.loc[lineups['name'].str.contains(qb) | ~lineups['name'].str.contains(stack)]
        lineups['superstars'] = lineups['name'].apply(lambda x: len([val for val in x.split(', ') if val in superstars]))
        lineups = lineups.loc[lineups.superstars <= 1].reset_index(drop=True)
        lineups = lineups.sort_values(by='points_avg',ascending=False,ignore_index=True)
        # lineups = lineups.sort_values(by='price',ascending=False,ignore_index=True)
        lineups = lineups.groupby('name_QB1').head(limit).reset_index(drop=True)
        lineups['name'] = lineups[name_cols].apply(", ".join,axis=1)
        return lineups

def main():
    # Initializing input arguments
    parser = optparse.OptionParser()
    parser.add_option(
        "--date",
        action="store",
        dest="date",
        default=datetime.datetime.now(),
        help="date of interest, defaults to today if not provided",
    )
    parser.add_option(
        "--rarity",
        action="store",
        dest="rarity",
        default="Core",
        help="rarity tier of interest, i.e. Core, Rare, Elite, Legendary, Reignmaker",
    )
    parser.add_option(
        "--limit",
        action="store",
        type="int",
        dest="limit",
        default=1000,
        help="number of top lineups to keep during each merge for memory purposes",
    )
    options = parser.parse_args()[0]

    dkrm_tf = Collection(options.date, options.rarity)
    dkrm_tf.print_values()
    stacks = {}
    # stacks = {"WR":{"K. Pickett":["D. Johnson"],\
    #                 "B. Purdy":["D. Samuel"],\
    #                 "T. Lawrence":["C. Ridley","C. Kirk"],\
    #                 "T. Tagovailoa":["J. Waddle"],\
    #                 "J. Allen":["G. Davis"]},\
    #           "TE":{"B. Purdy":["G. Kittle"]}}
    stacks = {"WR":{"B. Purdy":["D. Samuel"],\
                    "T. Tagovailoa":["J. Waddle"],\
                    "J. Allen":["G. Davis"]},\
              "RB":{"T. Tagovailoa":["B. Hall"]},\
              "TE":{"B. Purdy":["G. Kittle"]},\
              "DEF":{"B. Purdy":["SFO"]},\
              "K":{"B. Purdy":["J. Moody"]}}
    superstars = ["J. Herbert","P. Mahomes","S. Barkley","J. Allen","T. Hill","C. McCaffrey",\
    "J. Hurts","J. Jefferson","A. St. Brown","L. Jackson","J. Chase","R. Mostert","A. Thielen",\
    "T. Etienne Jr.","D. Moore","C. Kupp"]

    # TNF SCORING UPDATES
    # dkrm_tf.players.loc[dkrm_tf.players.name.isin(['B. Purdy']),'points_avg'] = 11.46
    # TNF SCORING UPDATES

    dkrm_tf.players['taken'] = dkrm_tf.players.name.isin(["DAL","Z. Jones","T. Lawrence","K. Pickett"]) # Showdown Entries, Exclusions
    # taken_inds = dkrm_tf.players.loc[dkrm_tf.players.name.isin(["A. Gibson",\
    # "D. Parker","J. Smith-Schuster"])].drop_duplicates(subset=["name"],keep="first").index
    # dkrm_tf.players.loc[taken_inds,'taken'] = True # When I'm only using one of two cards for a particular player

    best = pd.DataFrame()
    while True:
        try:
            lineups = dkrm_tf.best_lineups(stacks, superstars, options.limit)
        except:
            break
        best = pd.concat([best,lineups.iloc[:1][['name','points_avg','price']]],ignore_index=True)
        taken_inds = dkrm_tf.players.loc[dkrm_tf.players.name.isin(lineups.iloc[0]['name'].split(', ')) & ~dkrm_tf.players.taken].drop_duplicates(subset=["name"],keep="first").index
        dkrm_tf.players.loc[taken_inds,'taken'] = True
    print(best.to_string(index=False))
    remaining = dkrm_tf.players.loc[~dkrm_tf.players.taken & dkrm_tf.players.my_card]\
    .groupby('pos').size().sort_values().to_frame('num_cards').reset_index()
    print("Cards remaining by position:\n" + remaining.to_string(index=False))
    war_by_pos = dkrm_tf.players.loc[dkrm_tf.players.taken].groupby('pos').WAR.mean().sort_values().reset_index()
    print("Average starter WAR by position:\n" + war_by_pos.to_string(index=False))

if __name__ == "__main__":
    main()


