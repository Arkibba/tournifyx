import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Main.settings')
django.setup()

from tournifyx.models import Tournament, Player, Match
import itertools

# Find the tournament
tournament_code = '7K45RC'
t = Tournament.objects.get(code=tournament_code)

print(f"=== Fixing Tournament: {t.name} ===")
print(f"Match Type: {t.match_type}")
print(f"Capacity: {t.num_participants}")

# Get all players
players = Player.objects.filter(tournament=t)
print(f"Current Players: {players.count()}")
for p in players:
    print(f"  - {p.name}")

# Delete all existing matches
existing_matches = Match.objects.filter(tournament=t)
print(f"\nDeleting {existing_matches.count()} existing matches...")
existing_matches.delete()

# Check if tournament is full
if players.count() == t.num_participants:
    print(f"\nTournament is full ({players.count()}/{t.num_participants})! Generating new fixtures...")
    
    if t.match_type == 'league':
        # Generate all possible pairings
        player_list = list(players)
        fixture_pairs = list(itertools.combinations(player_list, 2))
        
        print(f"Creating {len(fixture_pairs)} league matches:")
        for p1, p2 in fixture_pairs:
            Match.objects.create(
                tournament=t,
                player1=p1,
                player2=p2,
                stage='GROUP',
                round_number=1,
                scheduled_time=None
            )
            print(f"  ✓ {p1.name} vs {p2.name}")
    
    elif t.match_type == 'knockout':
        count = players.count()
        if count >= 2 and (count & (count - 1)) == 0:  # Power of 2
            import random
            player_list = list(players)
            random.shuffle(player_list)
            
            fixture_pairs = []
            for i in range(0, len(player_list), 2):
                fixture_pairs.append((player_list[i], player_list[i+1]))
            
            print(f"Creating {len(fixture_pairs)} knockout matches:")
            for p1, p2 in fixture_pairs:
                Match.objects.create(
                    tournament=t,
                    player1=p1,
                    player2=p2,
                    stage='KNOCKOUT',
                    round_number=1,
                    scheduled_time=None
                )
                print(f"  ✓ {p1.name} vs {p2.name}")
        else:
            print(f"ERROR: Knockout requires power of 2 players, but have {count}")
    
    print(f"\n✅ Fixtures regenerated successfully!")
else:
    print(f"\n⚠️  Tournament is not full yet ({players.count()}/{t.num_participants})")
    print("Fixtures will be generated when all players have joined.")

# Verify
final_matches = Match.objects.filter(tournament=t)
print(f"\nFinal match count: {final_matches.count()}")
