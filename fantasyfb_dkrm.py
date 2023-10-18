
import pandas as pd
import datetime
import fantasyfb as fb
import matplotlib.pyplot as plt
import numpy as np

class Collection:
    def __init__(self):
        self.load_raw_data()
        self.clean_data()
        self.load_cards()
        self.load_ff_league()
        self.add_proj_pts()
        self.add_proj_price()

    def load_raw_data(self):
        tempData = open("DKRM_{}.txt".format(datetime.datetime.now().strftime('%m%d%y')),"r")
        raw_vals = tempData.read().split("""NAME
BUY NOW
FPPG
OPP
OPRK
LAST
FLOOR
FPPG/$
OWNED
TOTAL
""")[-1].split("""
DraftKings Inc.
Boston, MA
COMPANY
About DraftKings""")[0].replace("\nQ\n","\n").replace("\nIR\n","\n")\
        .replace("\nOUT\n","\n").replace("\nD\n","\n").replace("WR\n-\n","WR\n0.0\n\n").split("\n")
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
        self.players = self.players.loc[self.players.pos.isin(['QB','RB','WR','TE','K'])].reset_index(drop=True)
    
    def load_cards(self):
        self.cards = pd.read_csv("{}_tefirman_mycards.csv".format(datetime.datetime.now().strftime('%Y-%m-%d')))
        self.cards = self.cards.loc[self.cards.Series == datetime.datetime.now().year].reset_index(drop=True)
        self.cards['name'] = self.cards['FirstName'].str[0] + '. ' + self.cards['LastName']
        self.cards['listable'] = ~self.cards.Set.isin(['Starter'])
        self.cards['my_card'] = True
        self.players = pd.merge(left=self.players,right=self.cards[['name','Position','my_card','listable','Set']]\
        .rename(columns={'Position':'pos'}),how='left',on=['name','pos'])
        self.players.listable = self.players.listable.fillna(False)
        self.players.my_card = self.players.my_card.fillna(False)
    
    def load_ff_league(self):
        self.league = fb.League("The GENIEs")
        self.league.players['name'] = self.league.players['name'].str.split(' ').str[0].str[:1] + \
        '. ' + self.league.players['name'].str.split(' ').str[-1]
        self.league.players.loc[self.league.players['name'].isin(['A. Robinson']),'name'] += ' II'
        self.league.players.loc[self.league.players.player_id_sr.isin(['WilsCe01']),'name'] = 'C. Wilson Jr.'
        self.league.nfl_teams.yahoo = self.league.nfl_teams.yahoo.str.upper()
    
    def add_proj_pts(self):
        self.players = pd.merge(left=self.players,right=self.league.nfl_teams[["yahoo","real_abbrev"]]\
        .rename(columns={"yahoo":"team","real_abbrev":"current_team"}),how='inner',on=["team"])
        del self.players["team"]
        self.players = pd.merge(left=self.players,right=self.league.players[["name","current_team",\
        "WAR","points_avg","pct_rostered","string","until"]],how='inner',on=["name","current_team"])
        # Excluding J. Williams from DEN for now, but need to fix this...
        self.players = self.players.loc[~self.players['name'].isin(['J. Williams']) \
        | ~self.players['current_team'].isin(['DEN'])].reset_index(drop=True)
    
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
    
    def print_values(self, limit=20):
        uninjured = self.players.until.isnull() | (self.players.until < 17)
        starters = self.players.string < 2
        cols = ["name","pos","current_team","points_avg","WAR","price","proj_price","price_delta"]
        print("\nBest Values")
        print(self.players.loc[uninjured & starters,cols].sort_values(by="price_delta",ascending=False).iloc[:limit].to_string(index=False))
        print("\nWorst Values")
        print(self.players.loc[uninjured & starters,cols].sort_values(by="price_delta",ascending=True).iloc[:limit].to_string(index=False))
        print("My Listable Cards")
        print(self.players.loc[self.players.my_card & self.players.listable].sort_values(by="price_delta").to_string(index=False))
    
    def best_lineups(self, stacks, limit=1000):
        self.players['dummy'] = 1
        if 'taken' not in self.players.columns:
            self.players["taken"] = False
        
        # INCORPORATE DIFFERENT CONTEST TYPES!!!
        positions = {"QB":1,"WR":2,"RB":2,"TE":1,"K":1}
        # INCORPORATE DIFFERENT CONTEST TYPES!!!

        lineups = pd.DataFrame({'dummy':[1]})
        uninjured = self.players.until.isnull() | (self.players.until < self.league.current_week)
        for pos in positions:
            for ind in range(positions[pos]):
                lineups = pd.merge(left=lineups,right=self.players.loc[self.players.pos.isin([pos]) \
                & self.players.my_card & ~self.players.taken & uninjured,['name','points_avg','dummy']]\
                .rename(columns={'name':'name_' + pos + str(ind + 1),'points_avg':'points_avg_' + pos + str(ind + 1)}),how='inner',on='dummy')
                lineups['points_avg'] = lineups[[col for col in lineups.columns if col.startswith('points_avg_')]].sum(axis=1)
                name_cols = [col for col in lineups.columns if col.startswith('name_')]
                lineups['name'] = lineups[name_cols].apply(sorted,axis=1).apply(", ".join)
                lineups = lineups.drop_duplicates(subset=["name"],ignore_index=True)
                lineups = lineups.loc[lineups[name_cols].nunique(axis=1) == len(name_cols)].reset_index(drop=True)

                # ACCOUNT FOR STACKS A BIT MORE GENERICALLY!!!
                # ACCOUNT FOR STACKS A BIT MORE GENERICALLY!!!
                # ACCOUNT FOR STACKS A BIT MORE GENERICALLY!!!

                if pos in stacks:
                    for qb in stacks[pos]:
                        for stack in stacks[pos][qb]:
                            lineups = lineups.loc[~lineups['name'].str.contains(qb) | lineups['name'].str.contains(stack)]
                            lineups = lineups.loc[lineups['name'].str.contains(qb) | ~lineups['name'].str.contains(stack)]
                lineups = lineups.sort_values(by='points_avg',ascending=False,ignore_index=True)
                lineups = lineups.groupby('name_QB1').head(limit).reset_index(drop=True) # Switch this to CPT for showdowns...
        lineups = pd.merge(left=lineups,right=self.players.loc[~self.players.pos.isin(['QB']) \
        & self.players.my_card & ~self.players.taken & uninjured,['name','points_avg','dummy']]\
        .rename(columns={'name':'name_FLEX','points_avg':'points_avg_FLEX'}),how='inner',on='dummy')
        lineups['points_avg'] = lineups[[col for col in lineups.columns if col.startswith('points_avg_')]].sum(axis=1)
        name_cols = [col for col in lineups.columns if col.startswith('name_')]
        lineups['name'] = lineups[name_cols].apply(sorted,axis=1).apply(", ".join)
        lineups = lineups.drop_duplicates(subset=["name"],ignore_index=True)
        lineups = lineups.loc[lineups[name_cols].nunique(axis=1) == len(name_cols)].reset_index(drop=True)
        for pos in stacks:
            for qb in stacks[pos]:
                for stack in stacks[pos][qb]:
                    lineups = lineups.loc[~lineups['name'].str.contains(qb) | lineups['name'].str.contains(stack)]
                    lineups = lineups.loc[lineups['name'].str.contains(qb) | ~lineups['name'].str.contains(stack)]
        lineups = lineups.sort_values(by='points_avg',ascending=False,ignore_index=True)
        lineups = lineups.groupby('name_QB1').head(limit).reset_index(drop=True)
        lineups['name'] = lineups[name_cols].apply(", ".join,axis=1)
        return lineups

def main():
    dkrm_tf = Collection()
    dkrm_tf.print_values()
    stacks = {"WR":{"J. Herbert":["J. Palmer"],"B. Purdy":["D. Samuel"],"T. Lawrence":["C. Ridley","C. Kirk"],\
                    "R. Tannehill":["T. Burks","N. Westbrook-Ikhine"],"K. Pickett":["A. Robinson II"],\
                    "M. Jones":["J. Smith-Schuster"],"T. Tagovailoa":["C. Wilson Jr."]},\
            "RB":{"K. Pickett":["N. Harris"]},\
            "TE":{"J. Herbert":["G. Everett"],"B. Purdy":["G. Kittle"],\
                    "R. Tannehill":["C. Okonkwo"],"T. Tagovailoa":["D. Smythe"]}}
    limit = 1000
    dkrm_tf.players['taken'] = dkrm_tf.players.name.isin(["S. Clifford","D. Mills","S. Barkley","G. Davis","G. Gano","D. Knox",\
    "J. Herbert","J. Palmer","G. Everett","B. Cooks","R. Tannehill","J. Hill", "N. Westbrook-Ikhine","C. Okonkwo",\
    "T. Tagovailoa","T. Allgeier","T. Hockenson"]) # TNF Entry, Exclusions
    best = pd.DataFrame()
    for lineup in range(3):
        lineups = dkrm_tf.best_lineups(stacks, limit)
        best = pd.concat([best,lineups.iloc[:1][['name','points_avg']]],ignore_index=True)
        taken_inds = dkrm_tf.players.loc[dkrm_tf.players.name.isin(lineups.iloc[0]['name'].split(', ')) & ~dkrm_tf.players.taken].drop_duplicates(subset=["name"],keep="first").index
        dkrm_tf.players.loc[taken_inds,'taken'] = True
    print(best.to_string(index=False))

if __name__ == "__main__":
    main()


