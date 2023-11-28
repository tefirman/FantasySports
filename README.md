
# Taylor Firman's Fantasy Sports Repository

This repository contains fantasy sports simulators based in Python that were originally used as a training tool for myself, but have since grown into more of a pet project. All applications are meant for entertainment purposes only.

## Installation

Still working on uploading this package to PyPI, but in the meantime, you can create and activate an operational conda environment via the following commands:

```
git clone https://github.com/tefirman/FantasySports.git
cd FantasySports
conda create --name fantasy --file environment.yml
conda activate fantasy
```

## Usage

For details on each script's exact usage, execute the "help" option for each script:

```
python fantasyfb.py --help

Usage: fantasyfb.py [options]

Options:
  -h, --help            show this help message and exit
  --season=SEASON       season of interest
  --week=WEEK           week to project the season from
  --name=NAME           name of team to analyze in the case of multiple teams
                        in a single season
  --earliest=EARLIEST   earliest week of stats being considered, e.g. 201807
                        corresponds to week 7 of the 2018 season
  --games=GAMES         number of games to build each player's prior off of
  --basaloppstringtime=BASALOPPSTRINGTIME
                        scaling factors for basal/opponent/depthchart/time
                        factors, comma-separated string of values
  --sims=SIMS           number of season simulations
  --payouts=PAYOUTS     comma separated string containing integer payouts for
                        1st, 2nd, and 3rd
  --injurytries=INJURYTRIES
                        number of times to try pulling injury statuses before
                        rolling with it
  --bestball            whether to assess the league of interest in the
                        context of bestball (simulates bench contributions
                        better)
  --pickups=PICKUPS     assess possible free agent pickups for the players
                        specified ("all" will analyze all possible pickups)
  --adds                whether to assess possible free agent adds
  --drops               whether to assess possible drops
  --trades=TRADES       assess possible trades for the players specified
                        ("all" will analyze all possible trades)
  --given=GIVEN         given players to start with for multi-player trades
  --deltas              whether to assess deltas for each matchup of the
                        current week
  --output=OUTPUT       where to save the final projections spreadsheet
  --email=EMAIL         where to send the final projections spreadsheet
```

## Contact

Taylor Firman, @tefirman51, [taylorfirman.com](http://www.taylorfirman.com)


