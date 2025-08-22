import itertools
import random

def generate_knockout_fixtures(players):
    print(f"Generating knockout fixtures for players: {players}")
    random.shuffle(players)
    fixtures = []
    while len(players) > 1:
        fixtures.append((players.pop(), players.pop()))
    return fixtures

def generate_league_fixtures(players):
    print(f"Generating league fixtures for players: {players}")
    fixtures = list(itertools.combinations(players, 2))
    return fixtures