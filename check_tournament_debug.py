import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Main.settings')
django.setup()

from tournifyx.models import Tournament, Player, Match

# Find tournament
t = Tournament.objects.get(code='7K45RC')
print(f"Tournament: {t.name}")
print(f"Match Type: {t.match_type}")
print(f"Num Participants: {t.num_participants}")
print(f"Is Public: {t.is_public}")

# Check players
players = Player.objects.filter(tournament=t)
print(f"\nCurrent Players ({players.count()}):")
for p in players:
    print(f"  - {p.name} (ID: {p.id}, added_by: {p.added_by}, user_profile: {p.user_profile})")

# Check matches
matches = Match.objects.filter(tournament=t)
print(f"\nMatches ({matches.count()}):")
for m in matches:
    p2_name = m.player2.name if m.player2 else "BYE"
    print(f"  - {m.player1.name} vs {p2_name} (Stage: {m.stage}, Round: {m.round_number})")

print(f"\nExpected matches for {players.count()} players in {t.match_type}:")
if t.match_type == 'league':
    import itertools
    expected = list(itertools.combinations(players, 2))
    print(f"Should have {len(expected)} matches:")
    for p1, p2 in expected:
        print(f"  - {p1.name} vs {p2.name}")
elif t.match_type == 'knockout':
    count = players.count()
    if count & (count - 1) == 0:  # Power of 2
        print(f"Should have {count // 2} matches in round 1")
    else:
        print(f"ERROR: {count} is not a power of 2 for knockout!")
