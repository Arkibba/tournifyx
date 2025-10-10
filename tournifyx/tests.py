from django.test import TestCase
from django.contrib.auth.models import User
from .models import HostProfile, Tournament, Player, Match
from .utils import generate_next_knockout_round
from django.urls import reverse
from .models import PointTable


class KnockoutProgressionTests(TestCase):
	def setUp(self):
		# Create host user and profile
		self.user = User.objects.create_user(username='host1', password='pass')
		self.host = HostProfile.objects.create(user=self.user)

	def test_knockout_round_generation(self):
		# Create a knockout tournament with 8 players (2^3)
		t = Tournament.objects.create(
			name='KO Test',
			description='Test',
			category='valorant',
			num_participants=8,
			match_type='knockout',
			created_by=self.host,
			code='TEST01',
			is_active=True
		)

		# Add 8 players
		players = []
		for i in range(8):
			p = Player.objects.create(tournament=t, name=f'P{i+1}', added_by=self.host)
			players.append(p)

		# Create initial fixtures using utils.create_fixtures_for_tournament
		# call the helper in utils by importing via models
		from .utils import create_fixtures_for_tournament
		create_fixtures_for_tournament(t)

		# There should be 4 matches in round 1
		round1_matches = Match.objects.filter(tournament=t, round_number=1)
		self.assertEqual(round1_matches.count(), 4)

		# Set winners for all round 1 matches
		winners = []
		for m in round1_matches:
			# choose player1 as winner for determinism
			m.winner = m.player1
			m.save()
			winners.append(m.winner)

		# Generate next round
		generate_next_knockout_round(t)

		# Verify round 2 has 2 matches
		round2 = Match.objects.filter(tournament=t, round_number=2)
		self.assertEqual(round2.count(), 2)

		
		# Set winners for round 2
		for m in round2:
			m.winner = m.player1
			m.save()

		
		# Generate final
		generate_next_knockout_round(t)
		round3 = Match.objects.filter(tournament=t, round_number=3)
		self.assertEqual(round3.count(), 1)

		
		# Set final winner and generate next (should detect tournament winner)
		final = round3.first()
		final.winner = final.player1
		final.save()
		generate_next_knockout_round(t)

		
		# After final, no further matches should be created and winner exists
		all_winners = Match.objects.filter(tournament=t, winner__isnull=False).values_list('winner__name', flat=True)
		self.assertIn(final.winner.name, list(all_winners))

	def test_non_power_of_two_rejected(self):
		# Create tournament with 3 players but declared num_participants 3 -> should not create fixtures
		t = Tournament.objects.create(
			name='Bad KO',
			description='Bad',
			category='valorant',
			num_participants=3,
			match_type='knockout',
			created_by=self.host,
			code='BAD01',
			is_active=True
		)
		
		# Add 3 players
		for i in range(3):
			Player.objects.create(tournament=t, name=f'B{i+1}', added_by=self.host)

		from .utils import create_fixtures_for_tournament
		create_fixtures_for_tournament(t)
		# No matches should be created
		self.assertEqual(Match.objects.filter(tournament=t).count(), 0)

	
	def test_host_permission_enforced(self):
		# Create a knockout tournament and a match, then attempt to update as non-host
		t = Tournament.objects.create(
			name='KO Perm',
			description='Perm',
			category='valorant',
			num_participants=2,
			match_type='knockout',
			created_by=self.host,
			code='PERM01',
			is_active=True
		)
		
		p1 = Player.objects.create(tournament=t, name='A', added_by=self.host)
		p2 = Player.objects.create(tournament=t, name='B', added_by=self.host)
		m = Match.objects.create(tournament=t, player1=p1, player2=p2, round_number=1)

		# Create a non-host user
		other = User.objects.create_user(username='other', password='p')
		self.client.login(username='other', password='p')
		url = reverse('update_match_result', args=[m.id])
		resp = self.client.post(url, {'winner_id': p1.id})
		# Should be forbidden
		self.assertEqual(resp.status_code, 403)

	def test_point_table_absent_for_knockout(self):
		t = Tournament.objects.create(
			name='KO No Points',
			description='NOP',
			category='valorant',
			num_participants=2,
			match_type='knockout',
			created_by=self.host,
			code='NOP01',
			is_active=True
		)
		
		p1 = Player.objects.create(tournament=t, name='A', added_by=self.host)
		p2 = Player.objects.create(tournament=t, name='B', added_by=self.host)
		m = Match.objects.create(tournament=t, player1=p1, player2=p2, round_number=1)
		# Update result as host
		self.client.login(username='host1', password='pass')
		url = reverse('update_match_result', args=[m.id])
		resp = self.client.post(url, {'winner_id': p1.id})
		# There should be no PointTable entries for knockout tournament
		self.assertEqual(PointTable.objects.filter(tournament=t).count(), 0)

	
	def test_host_can_update_final(self):
		# Create tournament, create fixtures, progress to final, then host updates final via view
		t = Tournament.objects.create(
			name='Final Update',
			description='Final',
			category='valorant',
			num_participants=4,
			match_type='knockout',
			created_by=self.host,
			code='FIN01',
			is_active=True
		)
		
		p = [Player.objects.create(tournament=t, name=f'P{i+1}', added_by=self.host) for i in range(4)]
		from .utils import create_fixtures_for_tournament, generate_next_knockout_round
		create_fixtures_for_tournament(t)
		# set winners for round1
		r1 = Match.objects.filter(tournament=t, round_number=1)
		for m in r1:
			m.winner = m.player1
			m.save()
			
		generate_next_knockout_round(t)
		# set winners for semi (round 2)
		r2 = Match.objects.filter(tournament=t, round_number=2)
		for m in r2:
			m.winner = m.player1
			m.save()
			
		generate_next_knockout_round(t)
		final = Match.objects.filter(tournament=t).order_by('-round_number').first()
		# Host posts to update final
		self.client.login(username='host1', password='pass')
		url = reverse('update_match_result', args=[final.id])
		resp = self.client.post(url, {'winner_id': final.player1.id})
		self.assertEqual(resp.status_code, 302)  # redirect on success
		final.refresh_from_db()
		self.assertIsNotNone(final.winner)
