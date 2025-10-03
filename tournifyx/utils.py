import os
import random
import itertools
import stripe
from dotenv import load_dotenv
from django.db import models

from .models import Match, Player, Tournament

# ==============================
# 🔸 1. Load environment & Stripe setup
# ==============================
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env'))
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')


# ==============================
# 🔸 2. League Fixture Generator
# ==============================
def generate_league_fixtures(players):
    """
    Generate league fixtures (round robin).
    Each player plays every other player exactly once.
    """
    print(f"[League] Generating fixtures for players: {players}")
    fixtures = list(itertools.combinations(players, 2))
    return fixtures


# ==============================
# 🔸 3. Knockout Fixture Generator
# ==============================
def generate_knockout_fixtures(players):
    """
    Generate knockout fixtures by shuffling and pairing players.
    Handles odd number of players by giving a bye (automatic advance).
    """
    print(f"[Knockout] Generating fixtures for players: {players}")
    random.shuffle(players)
    fixtures = []

    while len(players) > 1:
        p1 = players.pop()
        p2 = players.pop()
        fixtures.append((p1, p2))

    # Odd number of players — last one gets a bye
    if players:
        fixtures.append((players.pop(), None))

    return fixtures


# ==============================
# 🔸 4. Auto-create Fixtures in DB
# ==============================
def create_fixtures_for_tournament(tournament):
    """
    Automatically generates and saves fixtures in the database
    depending on tournament.match_type.
    """
    participants = list(tournament.participants.all())
    if len(participants) < 2:
        print("[Fixtures] Not enough participants to create fixtures.")
        return

    players = [p.name for p in participants]

    # Generate fixtures based on tournament type
    if tournament.match_type == 'league':
        fixture_pairs = generate_league_fixtures(players)
        for p1_name, p2_name in fixture_pairs:
            p1 = Participant.objects.get(tournament=tournament, name=p1_name)
            p2 = Participant.objects.get(tournament=tournament, name=p2_name)
            Match.objects.get_or_create(
                tournament=tournament,
                player1=p1,
                player2=p2,
                round_number=1
            )

    elif tournament.match_type == 'knockout':
        fixture_pairs = generate_knockout_fixtures(players)
        for p1_name, p2_name in fixture_pairs:
            p1 = Participant.objects.get(tournament=tournament, name=p1_name)
            p2 = Participant.objects.get(tournament=tournament, name=p2_name) if p2_name else None
            match = Match.objects.create(
                tournament=tournament,
                player1=p1,
                player2=p2,
                round_number=1
            )
            if p2 is None:
                # Auto-advance bye player
                match.winner = p1
                match.save()


# ==============================
# 🔸 5. Knockout Next-Round Progression
# ==============================
def generate_next_knockout_round(tournament):
    """
    Creates the next knockout round once the current round is complete.
    """
    max_round = Match.objects.filter(tournament=tournament).aggregate(models.Max('round_number'))['round_number__max']
    if not max_round:
        print("[Knockout] No existing rounds found.")
        return

    current_round_matches = Match.objects.filter(tournament=tournament, round_number=max_round)

    # Wait until all matches in current round have winners
    if current_round_matches.filter(winner__isnull=True).exists():
        print("[Knockout] Current round is not finished yet.")
        return

    winners = [m.winner for m in current_round_matches if m.winner]
    if len(winners) <= 1:
        # Tournament has a winner
        if winners:
            print(f"[Knockout] Tournament Winner: {winners[0].name}")
        return

    random.shuffle(winners)
    next_round = max_round + 1

    # Pair winners for next round
    for i in range(0, len(winners), 2):
        p1 = winners[i]
        if i + 1 < len(winners):
            p2 = winners[i + 1]
            Match.objects.create(
                tournament=tournament,
                player1=p1,
                player2=p2,
                round_number=next_round
            )
        else:
            # Bye case
            Match.objects.create(
                tournament=tournament,
                player1=p1,
                player2=None,
                winner=p1,
                round_number=next_round
            )
            print(f"[Knockout] {p1.name} gets a bye to next round.")
