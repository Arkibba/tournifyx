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
    Expects `players` to be a list of Player model instances.
    Requires number of players to be a power of two (2^n). Returns list of (p1, p2) tuples.
    """
    print(f"[Knockout] Generating fixtures for players: {[p.name for p in players]}")
    # Filter valid players
    players = [p for p in players if p]
    count = len(players)
    if count < 2 or (count & (count - 1)) != 0:
        raise ValueError("Knockout fixtures require 2^n players (2,4,8,...)")

    random.shuffle(players)
    fixtures = []
    # Pair sequentially into fixtures
    for i in range(0, len(players), 2):
        fixtures.append((players[i], players[i+1]))
    return fixtures


# ==============================
# 🔸 4. Auto-create Fixtures in DB
# ==============================
def create_fixtures_for_tournament(tournament):
    """
    Automatically generates and saves fixtures in the database
    depending on tournament.match_type.
    """
    # Fetch players from Player model
    players = list(Player.objects.filter(tournament=tournament))
    if len(players) < 2:
        print("[Fixtures] Not enough participants to create fixtures.")
        return

    # Generate fixtures based on tournament type
    if tournament.match_type == 'league':
        player_names = [p.name for p in players]
        fixture_pairs = generate_league_fixtures(player_names)
        for p1_name, p2_name in fixture_pairs:
            p1 = Player.objects.get(tournament=tournament, name=p1_name)
            p2 = Player.objects.get(tournament=tournament, name=p2_name)
            Match.objects.get_or_create(
                tournament=tournament,
                player1=p1,
                player2=p2,
                round_number=1
            )

    elif tournament.match_type == 'knockout':
        # Require power-of-two players
        count = len(players)
        if count < 2 or (count & (count - 1)) != 0:
            print("[Knockout] Tournament must have 2^n participants. Skipping fixture creation.")
            return

        fixture_pairs = generate_knockout_fixtures(players[:])
        for p1, p2 in fixture_pairs:
            match = Match.objects.create(
                tournament=tournament,
                player1=p1,
                player2=p2,
                round_number=1
            )
            # No bye handling needed since we require 2^n players
            


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

    # Preserve parent match order to pair correctly
    parent_winners = [(m, m.winner) for m in current_round_matches.order_by('id') if m.winner]
    winners = [pw[1] for pw in parent_winners]
    if len(winners) <= 1:
        # Tournament has a winner
        if winners:
            print(f"[Knockout] Tournament Winner: {winners[0].name}")
        return

    random.shuffle(winners)
    next_round = max_round + 1

    # Determine stage for next round based on number of matches
    num_next_matches = len(winners) // 2
    if num_next_matches == 1:
        stage = 'FINAL'
    elif num_next_matches == 2:
        stage = 'SEMI'
    elif num_next_matches == 4:
        stage = 'QUARTER'
    else:
        stage = 'KNOCKOUT'
    
    # Pair winners for next round
    for i in range(0, len(parent_winners), 2):
        p1_parent, p1 = parent_winners[i]
        if i + 1 < len(parent_winners):
            p2_parent, p2 = parent_winners[i + 1]
            # Create match and attach parent links
            m = Match.objects.create(
                tournament=tournament,
                player1=p1,
                player2=p2,
                stage=stage,
                round_number=next_round,
                parent_match1=p1_parent,
                parent_match2=p2_parent
            )
            print(f"[Knockout] Created {stage} match: {p1.name} vs {p2.name}")
            
        else:
            # Bye case (shouldn't occur with 2^n) - attach parent
            Match.objects.create(
                tournament=tournament,
                player1=p1,
                player2=None,
                winner=p1,
                stage=stage,
                round_number=next_round,
                parent_match1=p1_parent
            )
            print(f"[Knockout] {p1.name} gets a bye to {stage}.")


def propagate_result_change(changed_match):
    """When a match result changes, update immediate child matches to reflect new participant,
    clear their winners (so hosts must re-confirm), and recurse downstream.
    Behavior:
      - For each child where parent_match1 == changed_match or parent_match2 == changed_match,
        update the corresponding player slot (player1/player2) to changed_match.winner (or None),
        clear child.winner and child.is_draw, then recursively clear their descendants.
    """
    
    # find direct children
    children = Match.objects.filter(models.Q(parent_match1=changed_match) | models.Q(parent_match2=changed_match))
    for child in children:
        # Determine which slot to update
        updated = False
        
        if child.parent_match1_id == changed_match.id:
            child.player1 = changed_match.winner if changed_match.winner else None
            updated = True
            
        if child.parent_match2_id == changed_match.id:
            child.player2 = changed_match.winner if changed_match.winner else None
            updated = True

        if updated:
            # clear result so host must re-enter
            child.winner = None
            child.is_draw = False
            child.save()
            # recurse
            propagate_result_change(child)
