from django.http import HttpResponse, HttpResponseForbidden
from django.contrib.auth import login as auth_login, logout as auth_logout, authenticate
from django.contrib.auth.models import User
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.cache import cache
from django.db import models

import itertools
import random
import string
import secrets

from .models import *
from .forms import TournamentForm, JoinTournamentForm, PlayerForm, PublicTournamentJoinForm
from .utils import generate_knockout_fixtures, generate_league_fixtures, generate_next_knockout_round, propagate_result_change
from collections import defaultdict, OrderedDict
from django.http import JsonResponse
from django.contrib.auth.models import User


def build_knockout_stages(tournament):
    """Return OrderedDict mapping round label -> list of Match objects for knockout tournaments.
    Round labels are 'Round 1', 'Round 2', ..., and final round is labelled 'Final' when only one match in that round.
    """
    matches = Match.objects.filter(tournament=tournament).select_related('player1', 'player2', 'winner').order_by('round_number', 'id')
    if not matches.exists():
        return None

    rounds = defaultdict(list)
    for m in matches:
        rounds[m.round_number].append(m)

    ordered = OrderedDict()
    max_round = max(rounds.keys())
    for r in sorted(rounds.keys()):
        label = 'Final' if len(rounds[r]) == 1 and r == max_round else f'Round {r}'
        ordered[label] = rounds[r]
    return ordered




def tournament_knockout_json(request, tournament_id):
    """Return knockout stages as JSON for JS bracket rendering."""
    tournament = get_object_or_404(Tournament, id=tournament_id)
    if tournament.match_type != 'knockout':
        return JsonResponse({'error': 'Not a knockout tournament'}, status=400)

    stages = build_knockout_stages(tournament) or {}
    data = []
    for label, matches in stages.items():
        mlist = []
        for m in matches:
            mlist.append({
                'id': m.id,
                'round': m.round_number,
                'player1': m.player1.name,
                'player2': m.player2.name if m.player2 else None,
                'winner_id': m.winner.id if m.winner else None,
                'winner_name': m.winner.name if m.winner else None,
            })
        data.append({'label': label, 'matches': mlist})
    return JsonResponse({'stages': data})


def profile_view(request, username):
    # Basic profile lookup
    user = get_object_or_404(User, username=username)
    # Ensure a UserProfile exists
    try:
        user_profile = UserProfile.objects.get(user=user)
    except UserProfile.DoesNotExist:
        user_profile = None

    # Tournaments organized by this user (as Host)
    tournaments_organized_qs = Tournament.objects.filter(created_by__user=user)
    tournaments_organized = tournaments_organized_qs.count()

    # Tournaments participated
    tournaments_participated_qs = TournamentParticipant.objects.filter(user_profile__user=user)
    tournaments_participated = tournaments_participated_qs.count()

    # Matches played: matches belonging to tournaments the user participated in
    participated_tournaments = tournaments_participated_qs.values_list('tournament', flat=True)
    matches_played = Match.objects.filter(tournament__in=participated_tournaments).count()

    # Top finishes
    # For knockout: count FINAL matches where winner.name matches the user's username
    knockout_wins = Match.objects.filter(stage='FINAL', winner__isnull=False, winner__name__iexact=user.username).count()

    # For league: count tournaments where PointTable top player name matches user.username
    league_firsts = 0
    league_seconds = 0
    # For each league tournament the user participated in, check PointTable ordering
    for t in Tournament.objects.filter(id__in=participated_tournaments, match_type='league'):
        pts = PointTable.objects.filter(tournament=t).order_by('-points')
        if pts.exists():
            top = pts.first()
            if top.player.name.lower() == user.username.lower():
                league_firsts += 1
            if pts.count() > 1 and pts[1].player.name.lower() == user.username.lower():
                league_seconds += 1

    # For knockouts second place: count finals where winner is other and the runner-up matches user's name
    knockout_seconds = 0
    finals = Match.objects.filter(stage='FINAL', tournament__in=participated_tournaments).select_related('player1', 'player2', 'winner')
    for f in finals:
        # runner-up is the non-winner player
        if f.winner:
            runner = None
            if f.player1 and f.winner and f.player1.id != f.winner.id:
                runner = f.player1
            elif f.player2 and f.winner and f.player2.id != f.winner.id:
                runner = f.player2
            if runner and runner.name.lower() == user.username.lower():
                knockout_seconds += 1

    top_firsts = knockout_wins + league_firsts
    top_seconds = knockout_seconds + league_seconds

    # Handle avatar / cover uploads and bio update if owner posts
    if request.method == 'POST' and request.user.is_authenticated and request.user == user:
        # Ensure user_profile exists
        if not user_profile:
            user_profile = UserProfile.objects.create(user=user)
        avatar = request.FILES.get('avatar')
        cover = request.FILES.get('cover')
        bio_text = request.POST.get('bio')
        if avatar:
            user_profile.avatar = avatar
        if cover:
            user_profile.cover_photo = cover
        if bio_text is not None:
            user_profile.bio = bio_text.strip() or None
        user_profile.save()
        # If this is an AJAX request, return JSON so the client can update without reload
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'ok', 'bio': user_profile.bio})
        messages.success(request, 'Profile updated.')
        return redirect('profile_view', username=username)

    context = {
        'profile_user': user,
        'user_profile': user_profile,
        'tournaments_organized': tournaments_organized,
        'matches_played': matches_played,
        'tournaments_participated': tournaments_participated,
        'top_firsts': top_firsts,
        'top_seconds': top_seconds,
    }
    return render(request, 'profile.html', context)




@login_required
def join_public_tournament(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id, is_public=True)
    current_players = Player.objects.filter(tournament=tournament).count()
    capacity = tournament.num_participants
    if request.method == 'POST':
        form = PublicTournamentJoinForm(request.POST)
        if form.is_valid():
            if current_players >= capacity:
                messages.error(request, 'This tournament is full. No more players can join.')
            elif tournament.is_paid and tournament.price > 0:
                messages.error(request, 'Payment gateway is currently disabled. You cannot join paid tournaments.')
            else:
                Player.objects.create(
                    tournament=tournament,
                    name=form.cleaned_data['name'],
                    team_name=form.cleaned_data['ign'],
                    # added_by can be null for public join
                )
                # Add TournamentParticipant entry for the user
                if request.user.is_authenticated:
                    user_profile = UserProfile.objects.get(user=request.user)
                    TournamentParticipant.objects.get_or_create(
                        tournament=tournament,
                        user_profile=user_profile
                    )
                messages.success(request, 'You have successfully joined the tournament!')
                messages.info(request, "The organizer needs to regenerate fixtures to include you.")
                return redirect('tournament_dashboard', tournament_id=tournament.id)
    else:
        form = PublicTournamentJoinForm()
    return render(request, 'join_tournament.html', {'form': form, 'tournament': tournament})

def generate_knockout_fixtures(players):
    random.shuffle(players)
    fixtures = []
    while len(players) > 1:
        fixtures.append((players.pop(), players.pop()))
    return fixtures

def generate_league_fixtures(players):
    fixtures = list(itertools.combinations(players, 2))
    return fixtures


# Views
def home(request):
    # Top Players: aggregate across all tournaments
    top_players_qs = (
        PointTable.objects.select_related('player')
        .values('player__name', 'player__id')
        .annotate(
            total_points=models.Sum('points'),
            total_wins=models.Sum('wins'),
            total_tournaments=models.Count('tournament', distinct=True),
            total_matches=models.Sum('matches_played'),
        )
        .order_by('-total_points', '-total_wins')[:10]
    )

    # Prepare player leaderboard data
    top_players = []
    for p in top_players_qs:
        win_rate = 0
        if p['total_matches']:
            win_rate = round(100 * p['total_wins'] / p['total_matches'])
        top_players.append({
            'username': p['player__name'],
            'points': p['total_points'],
            'tournaments': p['total_tournaments'],
            'wins': p['total_wins'],
            'win_rate': win_rate,
            # Placeholder avatar (replace with real if available)
            'avatar_url': '/static/images/github.png',
        })

    # Top Teams: group by team_name, ignore blank/null
    top_teams_qs = (
        Player.objects.exclude(team_name__isnull=True).exclude(team_name='')
        .values('team_name')
        .annotate(
            team_points=models.Sum('pointtable__points'),
            team_wins=models.Sum('pointtable__wins'),
            team_tournaments=models.Count('tournament', distinct=True),
            team_matches=models.Sum('pointtable__matches_played'),
        )
        .order_by('-team_points', '-team_wins')[:10]
    )

    top_teams = []
    for t in top_teams_qs:
        win_rate = 0
        if t['team_matches']:
            win_rate = round(100 * t['team_wins'] / t['team_matches'])
        top_teams.append({
            'name': t['team_name'],
            'points': t['team_points'],
            'tournaments': t['team_tournaments'],
            'wins': t['team_wins'],
            'win_rate': win_rate,
            # Placeholder logo (replace with real if available)
            'logo_url': '/static/images/logo.png',
        })

    return render(request, 'home.html', {
        'top_players': top_players,
        'top_teams': top_teams,
    })


# View to update match result and update point table

@login_required
@require_POST
def update_match_result(request, match_id):
    match = get_object_or_404(Match, id=match_id)
    winner_id = request.POST.get('winner_id')
    draw = request.POST.get('draw', False)

    # Fetch previous result from DB (not from possibly already updated match object)
    match_db = Match.objects.get(id=match_id)
    prev = None
    if match_db.winner is None and not match_db.is_draw:
        prev = None
    elif match_db.is_draw:
        prev = 'draw'
    elif match_db.winner == match_db.player1:
        prev = 'player1'
    elif match_db.winner == match_db.player2:
        prev = 'player2'

    if not winner_id and not draw:
        messages.error(request, 'Please select a winner or mark as draw.')
        return redirect('tournament_dashboard', tournament_id=match.tournament.id)

    # Only the tournament host may update knockout match results
    if match.tournament.match_type == 'knockout':
        # Compare by user to avoid HostProfile instance mismatch
        try:
            if not match.tournament.created_by or match.tournament.created_by.user != request.user:
                return HttpResponseForbidden('Only the tournament host can update knockout match results.')
        except Exception:
            return HttpResponseForbidden('Only the tournament host can update knockout match results.')

    # Update match result
    if draw:
        match.winner = None
        match.is_draw = True
    else:
        match.winner = Player.objects.get(id=winner_id)
        match.is_draw = False
    match.save()

    # Update point table for both players
    update_points_for_match(match, prev)
    # If knockout, propagate this change to downstream matches and try to generate next round automatically
    if match.tournament.match_type == 'knockout':
        try:
            # Update child matches to reflect change (clear winners downstream)
            propagate_result_change(match)
        except Exception as e:
            print(f"Error propagating result change: {e}")
        try:
            generate_next_knockout_round(match.tournament)
        except Exception as e:
            print(f"Error generating next knockout round: {e}")

    messages.success(request, 'Match result updated and point table recalculated.')
    return redirect('tournament_dashboard', tournament_id=match.tournament.id)


# Helper function to update points for a match
def update_points_for_match(match, prev_result=None):
    # Recalculate the entire point table for the tournament
    tournament = match.tournament
    # Only maintain point tables for league tournaments
    if tournament.match_type == 'knockout':
        return
    players = Player.objects.filter(tournament=tournament)
    # Reset all point table entries
    for pt in PointTable.objects.filter(tournament=tournament):
        pt.matches_played = 0
        pt.wins = 0
        pt.draws = 0
        pt.losses = 0
        pt.points = 0
        pt.save()

    
    # Go through all matches and update stats
    for m in Match.objects.filter(tournament=tournament):
        # Only count as played if result is set (winner or draw)
        if m.winner is not None or m.is_draw:
            pt1, _ = PointTable.objects.get_or_create(tournament=tournament, player=m.player1)
            # Handle possible bye (player2 is None)
            if m.player2:
                pt2, _ = PointTable.objects.get_or_create(tournament=tournament, player=m.player2)
            else:
                pt2 = None

            pt1.matches_played += 1
            if pt2:
                pt2.matches_played += 1

            if m.is_draw:
                # Draw with missing player doesn't make sense; only handle if both present
                if pt2:
                    pt1.draws += 1
                    pt2.draws += 1
                    pt1.points += 1
                    pt2.points += 1
            elif m.winner == m.player1:
                pt1.wins += 1
                pt1.points += 3
                if pt2:
                    pt2.losses += 1
            elif m.player2 and m.winner == m.player2:
                pt2.wins += 1
                pt2.points += 3
                pt1.losses += 1

            pt1.save()
            if pt2:
                pt2.save()

def register(request):
    if request.method == 'POST':
        username = request.POST['username']
        password1 = request.POST['password1']
        password2 = request.POST['password2']
        email = request.POST['email']

        if password1 != password2:
            messages.error(request, 'Passwords do not match!')
            return render(request, 'auth/register.html')


        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already taken!')
            return render(request, 'auth/register.html')

        if User.objects.filter(email=email).exists():
            messages.error(request, 'Email already in use!')
            return render(request, 'auth/register.html')

        user = User.objects.create_user(username=username, password=password1, email=email)
        user.save()



        # Optional: Also create a HostProfile now, or later when they choose to host
        HostProfile.objects.create(user=user)

        messages.success(request, 'Registration successful! Please log in.')
        return redirect('login')

    return render(request, 'auth/register.html')


def login(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)

        if user is not None:
            auth_login(request, user)
            # Ensure UserProfile exists for this user
            from .models import UserProfile
            try:
                user.userprofile
            except UserProfile.DoesNotExist:
                UserProfile.objects.create(user=user)
            messages.success(request, '')
            return redirect('home')
        else:
            messages.error(request, 'Invalid username or password!')
            return render(request, 'auth/login.html')

    return render(request, 'auth/login.html')


@login_required(login_url='login')
def logout(request):
    auth_logout(request)
    messages.success(request, 'You have been logged out!')
    return redirect('home')


@login_required(login_url='login')
def host_tournament(request):
    try:
        host_profile = HostProfile.objects.get(user=request.user)
    except HostProfile.DoesNotExist:
        host_profile = HostProfile.objects.create(user=request.user)

    tournaments = Tournament.objects.filter(created_by=host_profile)
    tournament_code = None
    tournament = None  # Initialize the tournament variable

    if request.method == 'POST':
        form = TournamentForm(request.POST)

        if form.is_valid():
            tournament = form.save(commit=False)
            tournament.created_by = host_profile
            # Explicitly set is_public and is_active from form.cleaned_data
            tournament.is_public = form.cleaned_data.get('is_public', False)
            tournament.is_active = form.cleaned_data.get('is_active', True)
            # Generate a unique tournament code
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            while Tournament.objects.filter(code=code).exists():
                code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            tournament.code = code
            tournament.save()

            # Add players to the tournament
            player_names = form.cleaned_data['players'].splitlines()
            if len(player_names) > tournament.num_participants:
                messages.error(request, f"Player limit exceeded! Maximum allowed: {tournament.num_participants}.")
                tournament.delete()  # Rollback tournament creation
                return redirect('host_tournament')

            
            # If knockout, ensure participants are exactly a power of two (2,4,8,16...)
            if tournament.match_type == 'knockout':
                count = len([n for n in player_names if n.strip()])
                if count < 2 or (count & (count - 1)) != 0:
                    messages.error(request, 'Knockout tournaments must have 2^n participants (e.g., 2,4,8,16...).')
                    tournament.delete()
                    return redirect('host_tournament')


            player_objs = []
            for name in player_names:
                if name.strip():  # Ignore empty lines
                    player_objs.append(Player.objects.create(
                        tournament=tournament,
                        name=name.strip(),
                        added_by=host_profile
                    ))

            # Create Match objects for all fixtures
            from tournifyx.models import Match
            if tournament.match_type == 'knockout':
                # generate_knockout_fixtures accepts Player instances and returns pairs (p1, p2)
                fixture_pairs = generate_knockout_fixtures(player_objs[:])
                # Create knockout matches in round 1
                for p1, p2 in fixture_pairs:
                    Match.objects.create(
                        tournament=tournament,
                        player1=p1,
                        player2=p2,
                        stage='KNOCKOUT',
                        round_number=1,
                        scheduled_time=None
                    )
                    
            else:
                fixture_pairs = generate_league_fixtures([p.name for p in player_objs])
                # Map names back to Player objects
                name_to_player = {p.name: p for p in player_objs}
                for p1_name, p2_name in fixture_pairs:
                    Match.objects.create(
                        tournament=tournament,
                        player1=name_to_player[p1_name],
                        player2=name_to_player[p2_name],
                        stage='GROUP',
                        round_number=1,
                        scheduled_time=None
                    )

            tournament_code = tournament.code
            messages.success(
                request,
                f"Tournament '{tournament.name}' created successfully with {len(player_names)} players!"
            )
        return render(request, 'host_tournament.html', {
            'form': form,
            'tournaments': tournaments,
            'tournament_code': tournament_code,
            'tournament': tournament,  # Pass the tournament object to the template
        })

    else:
        form = TournamentForm()

    return render(request, 'host_tournament.html', {
        'form': form,
        'tournaments': tournaments,
        'tournament_code': tournament_code,
        'tournament': tournament,  # Pass the tournament object to the template
    })


@login_required
def join_tournament(request):
    public_tournaments = Tournament.objects.filter(is_public=True, is_active=True)
    initial_code = request.GET.get('code', '')
    if request.method == 'POST':
        form = JoinTournamentForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data['code']
            try:
                tournament = Tournament.objects.get(code=code)
                user_profile = UserProfile.objects.get(user=request.user)
                already_joined = TournamentParticipant.objects.filter(
                    tournament=tournament,
                    user_profile=user_profile
                ).exists()
                if already_joined:
                    messages.error(request, 'You have already joined this tournament.')
                    return render(request, 'join_tournament.html', {
                        'form': form,
                        'public_tournaments': public_tournaments
                    })

                if tournament.is_paid and tournament.price > 0:
                    messages.error(request, 'Payment gateway is currently disabled. You cannot join paid tournaments.')
                else:
                    TournamentParticipant.objects.create(
                        tournament=tournament,
                        user_profile=user_profile
                    )
                    
                    return redirect('tournament_dashboard', tournament_id=tournament.id)
            except Tournament.DoesNotExist:
                messages.error(request, 'Invalid tournament code!')
    else:
        form = JoinTournamentForm(initial={'code': initial_code})
    return render(request, 'join_tournament.html', {
        'form': form,
        'public_tournaments': public_tournaments
    })




@login_required
def tournament_dashboard(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    participants = Player.objects.filter(tournament=tournament)
    matches = list(Match.objects.filter(tournament=tournament).select_related('player1', 'player2', 'winner'))
    for match in matches:
        match.has_result = bool(match.winner) or match.is_draw
    
    # Get point table sorted in descending order by points
    point_table = None
    if tournament.match_type != 'knockout':
        point_table = PointTable.objects.filter(tournament=tournament).select_related('player').order_by('-points')
    
    # Determine if the current user is the host
    is_host = False
    if request.user.is_authenticated:
        try:
            host_profile = HostProfile.objects.get(user=request.user)
            is_host = (tournament.created_by == host_profile)
        except HostProfile.DoesNotExist:
            is_host = False
    return render(request, 'tournament_dashboard.html', {
        'tournament': tournament,
        'participants': participants,
        'matches': matches,
        'point_table': point_table,
        # Knockout stages grouped by round_number (labelled)
        'knockout_stages': build_knockout_stages(tournament) if tournament.match_type == 'knockout' else None,
        'is_host': is_host,
    })

@login_required
def regenerate_fixtures(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)

    try:
        host_profile = HostProfile.objects.get(user=request.user)
        if tournament.created_by != host_profile:
            messages.error(request, "You are not authorized to regenerate fixtures.")
            return redirect('tournament_dashboard', tournament_id=tournament.id)
    except HostProfile.DoesNotExist:
        messages.error(request, "You are not authorized to regenerate fixtures.")
        return redirect('tournament_dashboard', tournament_id=tournament.id)

    # ✅ Only allow regeneration for league-type tournaments
    if tournament.match_type != 'league':
        messages.warning(request, "Fixture regeneration is only available for league tournaments.")
        return redirect('tournament_dashboard', tournament_id=tournament.id)

    # Delete old matches before regenerating
    Match.objects.filter(tournament=tournament).delete()

    # ✅ Delete old point table entries
    PointTable.objects.filter(tournament=tournament).delete()

    # ✅ Fetch players and generate new fixtures
    players = list(Player.objects.filter(tournament=tournament))
    fixture_pairs = generate_league_fixtures(players)

    # ✅ Create new Match entries
    for p1, p2 in fixture_pairs:
        Match.objects.create(
            tournament=tournament,
            player1=p1,
            player2=p2,
            stage='GROUP',
            round_number=1,
            scheduled_time=None
        )

    # ✅ Create default PointTable entries for all players
    for player in players:
        PointTable.objects.create(
            tournament=tournament,
            player=player,
            matches_played=0,
            wins=0,
            draws=0,
            losses=0,
            points=0
        )

    messages.success(request, "League fixtures regenerated and point table initialized successfully!")
    return redirect('tournament_dashboard', tournament_id=tournament.id)


@login_required(login_url='login')
def user_tournaments(request):
    user_profile = UserProfile.objects.get(user=request.user)
    host_profile = HostProfile.objects.filter(user=request.user).first()
    # Only show one tournament per unique name (latest by id)
    hosted_tournaments = []
    if host_profile:
        seen_names = set()
        
        for t in Tournament.objects.filter(created_by=host_profile).order_by('-id'):
            if t.name not in seen_names:
                hosted_tournaments.append(t)
                seen_names.add(t.name)
    joined_tournaments = Tournament.objects.filter(
        tournamentparticipant__user_profile=user_profile
    ).exclude(created_by=host_profile).distinct()

    
    if request.method == 'POST':
        tournament_id = request.POST.get('tournament_id')
        action = request.POST.get('action')
        if action == 'delete':
            Tournament.objects.filter(id=tournament_id, created_by=host_profile).delete()
        elif action == 'update':
            return redirect('update_tournament', tournament_id=tournament_id)

    return render(request, 'user_tournaments.html', {
        'hosted_tournaments': hosted_tournaments,
        'joined_tournaments': joined_tournaments,
    })


@login_required(login_url='login')
def update_tournament(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    players = Player.objects.filter(tournament=tournament)
    player_names = [p.name for p in players]
    if tournament.match_type == 'knockout':
        fixtures = generate_knockout_fixtures(player_names)
    else:
        fixtures = generate_league_fixtures(player_names)
    if request.method == 'POST':
        form = TournamentForm(request.POST, instance=tournament)
        if form.is_valid():
            updated_tournament = form.save(commit=False)
            # Always set is_public and is_active from the form value if present
            updated_tournament.is_public = form.cleaned_data.get('is_public', False)
            updated_tournament.is_active = form.cleaned_data.get('is_active', tournament.is_active)
            updated_tournament.save()
            # Update player names in the database
            new_player_names = [name.strip() for name in form.cleaned_data.get('players', '').splitlines() if name.strip()]
            existing_players = list(players)
            # Update existing player names
            for i, player in enumerate(existing_players):
                if i < len(new_player_names):
                    player.name = new_player_names[i]
                    player.save()
                else:
                    player.delete()  # Remove extra players
            # Add new players if needed
            for i in range(len(existing_players), len(new_player_names)):
                Player.objects.create(tournament=tournament, name=new_player_names[i])
            return redirect('user_tournaments')
    else:
        initial = {'players': '\n'.join([p.name for p in players])}
        # Set is_public checked by default if tournament is public
        if tournament.is_public:
            initial['is_public'] = True
        form = TournamentForm(instance=tournament, initial=initial)
    return render(request, 'update_tournament.html', {
        'form': form,
        'tournament': tournament,
        'players': players,
        'fixtures': fixtures,
    })



def about(request):
    """Render the About page."""
    return render(request, 'about.html', {
        'creators': [
            'Md. Zubaer Islam',
            'MD. Arkive',
            'Shoshi Khan'
            
        ]
    })




@login_required(login_url='login')
def public_tournaments(request):
    tournaments = Tournament.objects.filter(is_public=True, is_active=True)

    # Sort: soonest registration deadline, then most participants, then most recent
    tournaments = tournaments.order_by(
        'registration_deadline',
        '-num_participants',
        '-id'
    )

    # Search by name or description
    q = request.GET.get('q', '').strip()
    if q:
        tournaments = tournaments.filter(
            models.Q(name__icontains=q) | models.Q(description__icontains=q)
        )

    # Filter by category
    category = request.GET.get('category', '').strip().lower()
    if category:
        tournaments = tournaments.filter(category__iexact=category)

    # Filter by match_type
    match_type = request.GET.get('match_type', '').strip().lower()
    if match_type:
        tournaments = tournaments.filter(match_type__iexact=match_type)

    # Filter by free_only
    free_only = request.GET.get('free_only')
    if free_only:
        tournaments = tournaments.filter(is_paid=False)

    # Featured tournaments: top 2 by most recent or by participants
    featured_tournaments = tournaments.order_by('-id')[:2]

    return render(request, 'public_tournaments.html', {
        'tournaments': tournaments,
        'featured_tournaments': featured_tournaments,
    })
