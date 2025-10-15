from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.contrib.auth import login as auth_login, logout as auth_logout, authenticate
from django.contrib.auth.models import User
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.db import models
from collections import defaultdict, OrderedDict

import itertools
import random
import string
import secrets

from .models import *
from .forms import TournamentForm, JoinTournamentForm, PlayerForm, PublicTournamentJoinForm, CustomUserCreationForm
from .utils import generate_knockout_fixtures, generate_league_fixtures, generate_next_knockout_round, propagate_result_change


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
            # Check if user is authenticated and has profile
            if request.user.is_authenticated:
                try:
                    user_profile = UserProfile.objects.get(user=request.user)
                    
                    # Check if user is the host (hosts can't join their own tournaments)
                    try:
                        host_profile = HostProfile.objects.get(user=request.user)
                        if tournament.created_by == host_profile:
                            messages.error(request, 'You cannot join a tournament that you created.')
                            return render(request, 'join_tournament.html', {'form': form, 'tournament': tournament})
                    except HostProfile.DoesNotExist:
                        pass  # User is not a host, they can join
                    
                    # Check if user already joined
                    already_joined = TournamentParticipant.objects.filter(
                        tournament=tournament,
                        user_profile=user_profile
                    ).exists()
                    if already_joined:
                        messages.error(request, 'You have already joined this tournament.')
                        return render(request, 'join_tournament.html', {'form': form, 'tournament': tournament})
                        
                except UserProfile.DoesNotExist:
                    # Create profile if it doesn't exist
                    user_profile = UserProfile.objects.create(user=request.user)
            
            if current_players >= capacity:
                messages.error(request, 'This tournament is full. No more players can join.')
                # Return with tournament_full flag
                return render(request, 'join_tournament.html', {
                    'form': form,
                    'tournament': tournament,
                    'tournament_full': True  # Flag to show modal
                })
            elif tournament.is_paid and tournament.price > 0:
                messages.error(request, 'Payment gateway is currently disabled. You cannot join paid tournaments.')
            else:
                # Create the player
                new_player = Player.objects.create(
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
                    # Link player to user profile
                    new_player.user_profile = user_profile
                    new_player.save()
                
                # Check if tournament is now FULL and needs fixtures generated
                current_players = Player.objects.filter(tournament=tournament)
                count = current_players.count()
                
                print(f"[PUBLIC JOIN DEBUG] Tournament: {tournament.name}")
                print(f"[PUBLIC JOIN DEBUG] Current player count: {count}")
                print(f"[PUBLIC JOIN DEBUG] Required participants: {tournament.num_participants}")
                print(f"[PUBLIC JOIN DEBUG] Match type: {tournament.match_type}")
                
                # Only generate fixtures if tournament is now full and no fixtures exist yet
                if count == tournament.num_participants:
                    existing_matches = Match.objects.filter(tournament=tournament)
                    print(f"[PUBLIC JOIN DEBUG] Tournament is full! Existing matches: {existing_matches.count()}")
                    
                    if not existing_matches.exists():
                        print(f"[PUBLIC JOIN DEBUG] No existing matches, generating fixtures...")
                        if tournament.match_type == 'knockout':
                            if count >= 2 and (count & (count - 1)) == 0:  # Power of 2
                                print(f"[PUBLIC JOIN DEBUG] Generating knockout fixtures for {count} players")
                                fixture_pairs = generate_knockout_fixtures(list(current_players))
                                for p1, p2 in fixture_pairs:
                                    Match.objects.create(
                                        tournament=tournament,
                                        player1=p1,
                                        player2=p2,
                                        stage='KNOCKOUT',
                                        round_number=1,
                                        scheduled_time=None
                                    )
                                print(f"[PUBLIC JOIN DEBUG] Created {len(fixture_pairs)} knockout matches")
                                messages.success(request, f'Successfully joined "{tournament.name}"! Tournament is now full and fixtures have been generated.')
                            else:
                                print(f"[PUBLIC JOIN DEBUG] Player count {count} is not a power of 2")
                                messages.success(request, 'You have successfully joined the tournament!')
                        elif tournament.match_type == 'league' and count >= 2:
                            print(f"[PUBLIC JOIN DEBUG] Generating league fixtures for {count} players")
                            fixture_pairs = generate_league_fixtures([p.name for p in current_players])
                            name_to_player = {p.name: p for p in current_players}
                            for p1_name, p2_name in fixture_pairs:
                                Match.objects.create(
                                    tournament=tournament,
                                    player1=name_to_player[p1_name],
                                    player2=name_to_player[p2_name],
                                    stage='GROUP',
                                    round_number=1,
                                    scheduled_time=None
                                )
                            print(f"[PUBLIC JOIN DEBUG] Created {len(fixture_pairs)} league matches")
                            messages.success(request, f'Successfully joined "{tournament.name}"! Tournament is now full and fixtures have been generated.')
                    else:
                        print(f"[PUBLIC JOIN DEBUG] Fixtures already exist, skipping generation")
                        messages.success(request, 'You have successfully joined the tournament!')
                else:
                    print(f"[PUBLIC JOIN DEBUG] Tournament not full yet ({count}/{tournament.num_participants})")
                    messages.success(request, 'You have successfully joined the tournament!')
                
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
        form = CustomUserCreationForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            # Create HostProfile
            HostProfile.objects.create(user=user)
            messages.success(request, 'Registration successful! Please log in.')
            return redirect('login')
        else:
            # Pass form errors to template
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = CustomUserCreationForm()
    
    return render(request, 'auth/register.html', {'form': form})


def login(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)

        if user is not None:
            auth_login(request, user)
            # Ensure UserProfile exists for this user
            try:
                user.userprofile
            except UserProfile.DoesNotExist:
                UserProfile.objects.create(user=user)
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
            player_names = [name.strip() for name in player_names if name.strip()]  # Clean and filter empty lines
            
            if len(player_names) > tournament.num_participants:
                messages.error(request, f"Player limit exceeded! Maximum allowed: {tournament.num_participants}.")
                tournament.delete()  # Rollback tournament creation
                return redirect('host_tournament')

            # For knockout tournaments, only validate if we're creating matches now (i.e., tournament is not public)
            # If it's public, people can join later to reach the required power-of-2
            if tournament.match_type == 'knockout' and not tournament.is_public:
                count = len(player_names)
                if count < 2 or (count & (count - 1)) != 0:
                    messages.error(request, 'Private knockout tournaments must have exactly 2^n participants (e.g., 2,4,8,16...) at creation.')
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

            # Create Match objects ONLY if tournament is FULL
            # Fixtures should only be generated when the tournament reaches full capacity
            count = len(player_objs)
            print(f"[HOST DEBUG] Tournament: {tournament.name}")
            print(f"[HOST DEBUG] Initial player count: {count}")
            print(f"[HOST DEBUG] Required participants: {tournament.num_participants}")
            print(f"[HOST DEBUG] Match type: {tournament.match_type}")
            
            if count == tournament.num_participants:
                print(f"[HOST DEBUG] Tournament is full at creation! Generating fixtures...")
                if tournament.match_type == 'knockout':
                    if count >= 2 and (count & (count - 1)) == 0:  # Power of 2 check
                        print(f"[HOST DEBUG] Generating knockout fixtures for {count} players")
                        fixture_pairs = generate_knockout_fixtures(player_objs[:])
                        for p1, p2 in fixture_pairs:
                            Match.objects.create(
                                tournament=tournament,
                                player1=p1,
                                player2=p2,
                                stage='KNOCKOUT',
                                round_number=1,
                                scheduled_time=None
                            )
                        print(f"[HOST DEBUG] Created {len(fixture_pairs)} knockout matches")
                    else:
                        print(f"[HOST DEBUG] Player count {count} is not a power of 2")
                        
                elif tournament.match_type == 'league' and count >= 2:
                    print(f"[HOST DEBUG] Generating league fixtures for {count} players")
                    fixture_pairs = generate_league_fixtures([p.name for p in player_objs])
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
                    print(f"[HOST DEBUG] Created {len(fixture_pairs)} league matches")
            else:
                print(f"[HOST DEBUG] Tournament not full yet ({count}/{tournament.num_participants}), fixtures will be generated later")

            tournament_code = tournament.code
            player_count = len(player_objs)
            remaining_slots = tournament.num_participants - player_count
            
            if remaining_slots > 0:
                messages.success(
                    request,
                    f"Tournament '{tournament.name}' created successfully with {player_count} players! "
                    f"{remaining_slots} slots remaining for public registration."
                )
            else:
                messages.success(
                    request,
                    f"Tournament '{tournament.name}' created successfully with {player_count} players!"
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
    # Clear any existing messages to prevent irrelevant messages from other pages
    from django.contrib.messages import get_messages
    storage = get_messages(request)
    for message in storage:
        pass  # This consumes all existing messages
    
    public_tournaments = Tournament.objects.filter(is_public=True, is_active=True)
    initial_code = request.GET.get('code', '')
    tournament = None
    form = JoinTournamentForm(initial={'code': initial_code})  # Initialize form at the start
    
    if request.method == 'POST':
        if 'find_tournament' in request.POST:
            # Handle tournament finding
            form = JoinTournamentForm(request.POST)
            if form.is_valid():
                code = form.cleaned_data['code']
                try:
                    tournament = Tournament.objects.get(code=code)
                    # Check if user already joined
                    user_profile = UserProfile.objects.get(user=request.user)
                    already_joined = TournamentParticipant.objects.filter(
                        tournament=tournament,
                        user_profile=user_profile
                    ).exists()
                    if already_joined:
                        messages.error(request, 'You have already joined this tournament.')
                        tournament = None
                    else:
                        # Show join form with player details
                        join_form = PublicTournamentJoinForm()
                        return render(request, 'join_tournament.html', {
                            'form': form,
                            'join_form': join_form,
                            'tournament': tournament,
                            'public_tournaments': public_tournaments
                        })
                except Tournament.DoesNotExist:
                    messages.error(request, 'Invalid tournament code!')
        elif 'join_tournament' in request.POST or ('name' in request.POST and 'ign' in request.POST):
            # Handle actual joining with player details
            join_form = PublicTournamentJoinForm(request.POST)
            tournament_code = request.POST.get('tournament_code')
            
            if join_form.is_valid() and tournament_code:
                try:
                    tournament = Tournament.objects.get(code=tournament_code)
                    user_profile = UserProfile.objects.get(user=request.user)
                    
                    # Check if user already joined
                    already_joined = TournamentParticipant.objects.filter(
                        tournament=tournament,
                        user_profile=user_profile
                    ).exists()
                    if already_joined:
                        messages.error(request, 'You have already joined this tournament.')
                    else:
                        # Check if user is the host (hosts can't join their own tournaments)
                        try:
                            host_profile = HostProfile.objects.get(user=request.user)
                            if tournament.created_by == host_profile:
                                messages.error(request, 'You cannot join a tournament that you created.')
                                return render(request, 'join_tournament.html', {
                                    'form': form,
                                    'join_form': join_form,
                                    'tournament': tournament,
                                    'public_tournaments': public_tournaments
                                })
                        except HostProfile.DoesNotExist:
                            pass  # User is not a host, they can join
                        
                        # Check if tournament is full
                        current_players = Player.objects.filter(tournament=tournament).count()
                        if current_players >= tournament.num_participants:
                            messages.error(request, 'This tournament is full. No more players can join.')
                            # Return with tournament_full flag
                            return render(request, 'join_tournament.html', {
                                'form': form,
                                'join_form': join_form,
                                'tournament': tournament,
                                'public_tournaments': public_tournaments,
                                'tournament_full': True  # Flag to show modal
                            })
                        elif tournament.is_paid and tournament.price > 0:
                            messages.error(request, 'Payment gateway is currently disabled. You cannot join paid tournaments.')
                        else:
                            # Create TournamentParticipant
                            TournamentParticipant.objects.create(
                                tournament=tournament,
                                user_profile=user_profile
                            )
                            
                            # Create Player entry with user details
                            Player.objects.create(
                                tournament=tournament,
                                name=join_form.cleaned_data['name'],
                                ign=join_form.cleaned_data['ign'],
                                contact_number=join_form.cleaned_data['contact_number'],
                                added_by=None,  # Player added themselves
                                user_profile=user_profile  # Link to user profile
                            )
                            
                            # Check if tournament is now FULL and needs fixtures generated
                            current_players = Player.objects.filter(tournament=tournament)
                            count = current_players.count()
                            
                            print(f"[JOIN DEBUG] Tournament: {tournament.name}")
                            print(f"[JOIN DEBUG] Current player count: {count}")
                            print(f"[JOIN DEBUG] Required participants: {tournament.num_participants}")
                            print(f"[JOIN DEBUG] Match type: {tournament.match_type}")
                            
                            # Only generate fixtures if tournament is now full and no fixtures exist yet
                            if count == tournament.num_participants:
                                existing_matches = Match.objects.filter(tournament=tournament)
                                print(f"[JOIN DEBUG] Tournament is full! Existing matches: {existing_matches.count()}")
                                
                                if not existing_matches.exists():
                                    print(f"[JOIN DEBUG] No existing matches, generating fixtures...")
                                    if tournament.match_type == 'knockout':
                                        if count >= 2 and (count & (count - 1)) == 0:  # Power of 2
                                            print(f"[JOIN DEBUG] Generating knockout fixtures for {count} players")
                                            fixture_pairs = generate_knockout_fixtures(list(current_players))
                                            for p1, p2 in fixture_pairs:
                                                Match.objects.create(
                                                    tournament=tournament,
                                                    player1=p1,
                                                    player2=p2,
                                                    stage='KNOCKOUT',
                                                    round_number=1,
                                                    scheduled_time=None
                                                )
                                            print(f"[JOIN DEBUG] Created {len(fixture_pairs)} knockout matches")
                                            messages.success(request, f'Successfully joined "{tournament.name}"! Tournament is now full and fixtures have been generated.')
                                        else:
                                            print(f"[JOIN DEBUG] Player count {count} is not a power of 2")
                                    elif tournament.match_type == 'league' and count >= 2:
                                        print(f"[JOIN DEBUG] Generating league fixtures for {count} players")
                                        fixture_pairs = generate_league_fixtures([p.name for p in current_players])
                                        name_to_player = {p.name: p for p in current_players}
                                        for p1_name, p2_name in fixture_pairs:
                                            Match.objects.create(
                                                tournament=tournament,
                                                player1=name_to_player[p1_name],
                                                player2=name_to_player[p2_name],
                                                stage='GROUP',
                                                round_number=1,
                                                scheduled_time=None
                                            )
                                        print(f"[JOIN DEBUG] Created {len(fixture_pairs)} league matches")
                                        messages.success(request, f'Successfully joined "{tournament.name}"! Tournament is now full and fixtures have been generated.')
                                else:
                                    print(f"[JOIN DEBUG] Fixtures already exist, skipping generation")
                            
                            if count < tournament.num_participants:
                                messages.success(request, f'Successfully joined "{tournament.name}"!')
                            return redirect('tournament_dashboard', tournament_id=tournament.id)
                            
                except Tournament.DoesNotExist:
                    messages.error(request, 'Tournament not found!')
        
    return render(request, 'join_tournament.html', {
        'form': form,
        'tournament': tournament,
        'public_tournaments': public_tournaments
    })




@login_required
def tournament_dashboard(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    participants = Player.objects.filter(tournament=tournament)
    
    # Check if fixtures need to be generated for filled tournaments
    current_player_count = participants.count()
    matches = list(Match.objects.filter(tournament=tournament).select_related('player1', 'player2', 'winner'))
    
    # Auto-generate fixtures if tournament is filled and no fixtures exist
    if (current_player_count == tournament.num_participants and 
        not matches and 
        current_player_count >= 2):
        
        if tournament.match_type == 'knockout':
            # Check if player count is power of 2
            if current_player_count & (current_player_count - 1) == 0:
                fixture_pairs = generate_knockout_fixtures(list(participants))
                for p1, p2 in fixture_pairs:
                    Match.objects.create(
                        tournament=tournament,
                        player1=p1,
                        player2=p2,
                        stage='KNOCKOUT',
                        round_number=1,
                        scheduled_time=None
                    )
                messages.success(request, f"Tournament is now full! Fixtures have been generated automatically.")
                
        elif tournament.match_type == 'league':
            fixture_pairs = generate_league_fixtures([p.name for p in participants])
            name_to_player = {p.name: p for p in participants}
            for p1_name, p2_name in fixture_pairs:
                Match.objects.create(
                    tournament=tournament,
                    player1=name_to_player[p1_name],
                    player2=name_to_player[p2_name],
                    stage='GROUP',
                    round_number=1,
                    scheduled_time=None
                )
            messages.success(request, f"Tournament is now full! Fixtures have been generated automatically.")
        
        # Refresh matches after generation
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
            
    # Check tournament status
    is_tournament_full = (current_player_count == tournament.num_participants)
    remaining_slots = tournament.num_participants - current_player_count
    
    # Check tournament status - now use manual host control
    tournament_ended = tournament.is_finished
    
    # Check if current user can leave (is a participant - now allowed any time)
    # Hosts cannot leave their own tournaments
    can_leave = False
    if request.user.is_authenticated:
        try:
            user_profile = UserProfile.objects.get(user=request.user)
        except UserProfile.DoesNotExist:
            # Create UserProfile if it doesn't exist
            user_profile = UserProfile.objects.create(user=request.user)
        
        # Check if user is the host - hosts cannot leave their own tournaments
        is_host = False
        try:
            host_profile = HostProfile.objects.get(user=request.user)
            if tournament.created_by == host_profile:
                is_host = True
        except HostProfile.DoesNotExist:
            pass
        
        # Only allow leave if user is NOT the host
        if not is_host:
            # Check both TournamentParticipant and Player records
            participant_exists = TournamentParticipant.objects.filter(
                tournament=tournament,
                user_profile=user_profile
            ).exists()
            
            # Also check if user is a player by user_profile or by matching username
            player_by_profile = Player.objects.filter(
                tournament=tournament,
                user_profile=user_profile
            ).exists()
            
            player_by_name = Player.objects.filter(
                tournament=tournament,
                name__iexact=request.user.username
            ).exists()
            
            can_leave = participant_exists or player_by_profile or player_by_name
    
    # Get pending leave requests for this tournament
    pending_leave_requests = LeaveRequest.objects.filter(
        tournament=tournament,
        status='pending'
    ).select_related('player', 'user_profile')
    
    # Check if current user has a pending leave request
    user_has_pending_request = False
    if request.user.is_authenticated:
        try:
            user_profile = UserProfile.objects.get(user=request.user)
            user_has_pending_request = LeaveRequest.objects.filter(
                tournament=tournament,
                user_profile=user_profile,
                status='pending'
            ).exists()
        except UserProfile.DoesNotExist:
            pass
    
    return render(request, 'tournament_dashboard.html', {
        'tournament': tournament,
        'participants': participants,
        'matches': matches,
        'point_table': point_table,
        # Knockout stages grouped by round_number (labelled)
        'knockout_stages': build_knockout_stages(tournament) if tournament.match_type == 'knockout' else None,
        'is_host': is_host,
        'is_tournament_full': is_tournament_full,
        'remaining_slots': remaining_slots,
        'current_player_count': current_player_count,
        'tournament_ended': tournament_ended,
        'can_leave': can_leave,
        'pending_leave_requests': pending_leave_requests,
        'user_has_pending_request': user_has_pending_request,
    })

@login_required
def regenerate_fixtures(request, tournament_id):
    """Regenerate all fixtures for the tournament from scratch"""
    tournament = get_object_or_404(Tournament, id=tournament_id)

    try:
        host_profile = HostProfile.objects.get(user=request.user)
        if tournament.created_by != host_profile:
            messages.error(request, "You are not authorized to regenerate fixtures for this tournament.")
            return redirect('tournament_dashboard', tournament_id=tournament.id)
    except HostProfile.DoesNotExist:
        messages.error(request, "You are not authorized to regenerate fixtures for this tournament.")
        return redirect('tournament_dashboard', tournament_id=tournament.id)

    if request.method == 'POST':
        # Get all players
        players = list(Player.objects.filter(tournament=tournament))
        player_count = len(players)
        
        print(f"[REGENERATE DEBUG] Tournament: {tournament.name}")
        print(f"[REGENERATE DEBUG] Player count: {player_count}")
        print(f"[REGENERATE DEBUG] Required participants: {tournament.num_participants}")
        print(f"[REGENERATE DEBUG] Match type: {tournament.match_type}")
        
        # Check if we have enough players
        if player_count < 2:
            messages.error(request, "Need at least 2 players to generate fixtures.")
            return redirect('tournament_dashboard', tournament_id=tournament.id)
        
        # Delete all existing matches (will regenerate from scratch)
        existing_count = Match.objects.filter(tournament=tournament).count()
        Match.objects.filter(tournament=tournament).delete()
        print(f"[REGENERATE DEBUG] Deleted {existing_count} existing matches")
        
        # Generate new fixtures based on tournament type
        try:
            if tournament.match_type == 'knockout':
                # Check if player count is power of 2
                if player_count & (player_count - 1) != 0:
                    messages.error(request, f"Knockout tournaments require a power of 2 players (2, 4, 8, 16...). You have {player_count} players.")
                    return redirect('tournament_dashboard', tournament_id=tournament.id)
                
                print(f"[REGENERATE DEBUG] Generating knockout fixtures")
                fixture_pairs = generate_knockout_fixtures(players[:])
                for p1, p2 in fixture_pairs:
                    Match.objects.create(
                        tournament=tournament,
                        player1=p1,
                        player2=p2,
                        stage='KNOCKOUT',
                        round_number=1,
                        scheduled_time=None
                    )
                print(f"[REGENERATE DEBUG] Created {len(fixture_pairs)} knockout matches")
                messages.success(request, f"Successfully generated {len(fixture_pairs)} knockout fixtures for {player_count} players!")
                
            elif tournament.match_type == 'league':
                print(f"[REGENERATE DEBUG] Generating league fixtures")
                player_names = [p.name for p in players]
                fixture_pairs = generate_league_fixtures(player_names)
                name_to_player = {p.name: p for p in players}
                
                for p1_name, p2_name in fixture_pairs:
                    Match.objects.create(
                        tournament=tournament,
                        player1=name_to_player[p1_name],
                        player2=name_to_player[p2_name],
                        stage='GROUP',
                        round_number=1,
                        scheduled_time=None
                    )
                print(f"[REGENERATE DEBUG] Created {len(fixture_pairs)} league matches")
                messages.success(request, f"Successfully generated {len(fixture_pairs)} league fixtures for {player_count} players!")
            
        except Exception as e:
            messages.error(request, f"Error generating fixtures: {str(e)}")
            print(f"[REGENERATE DEBUG] Error: {e}")
    
    return redirect('tournament_dashboard', tournament_id=tournament.id)


@login_required
def toggle_tournament_status(request, tournament_id):
    """Allow host to toggle tournament finished status"""
    tournament = get_object_or_404(Tournament, id=tournament_id)
    
    # Check if user is the host
    try:
        host_profile = HostProfile.objects.get(user=request.user)
        if tournament.created_by != host_profile:
            messages.error(request, "You are not authorized to change tournament status.")
            return redirect('tournament_dashboard', tournament_id=tournament.id)
    except HostProfile.DoesNotExist:
        messages.error(request, "You are not authorized to change tournament status.")
        return redirect('tournament_dashboard', tournament_id=tournament.id)
    
    if request.method == 'POST':
        # Toggle the finished status
        tournament.is_finished = not tournament.is_finished
        tournament.save()
        
        status_text = "finished" if tournament.is_finished else "active"
        messages.success(request, f'Tournament "{tournament.name}" has been marked as {status_text}.')
    
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


@login_required
def leave_tournament(request, tournament_id):
    """Allow a player to request to leave a tournament - requires host approval if tournament hasn't ended"""
    tournament = get_object_or_404(Tournament, id=tournament_id)
    
    # Check if user is authenticated and has a profile
    try:
        user_profile = UserProfile.objects.get(user=request.user)
    except UserProfile.DoesNotExist:
        messages.error(request, 'User profile not found.')
        return redirect('tournament_dashboard', tournament_id=tournament.id)
    
    # Check if the user is actually in this tournament
    participant = None
    player = None
    
    # Try to find TournamentParticipant
    try:
        participant = TournamentParticipant.objects.get(
            tournament=tournament,
            user_profile=user_profile
        )
    except TournamentParticipant.DoesNotExist:
        pass
    
    # Try to find Player by user_profile
    try:
        player = Player.objects.get(
            tournament=tournament,
            user_profile=user_profile
        )
    except Player.DoesNotExist:
        # Try to find Player by username match
        try:
            player = Player.objects.get(
                tournament=tournament,
                name__iexact=request.user.username
            )
        except Player.DoesNotExist:
            pass
    
    # Check if user is in the tournament at all
    if not participant and not player:
        messages.error(request, 'You are not a participant in this tournament.')
        return redirect('tournament_dashboard', tournament_id=tournament.id)
    
    if request.method == 'POST':
        # If tournament has ended, allow immediate leave
        if tournament.is_finished:
            # Remove from point table first if exists
            if player:
                PointTable.objects.filter(
                    tournament=tournament,
                    player=player
                ).delete()
                
                # Remove the player from the tournament
                player.delete()
            
            # Remove participant record if it exists
            if participant:
                participant.delete()
            
            messages.success(request, f'You have successfully left "{tournament.name}".')
            return redirect('user_tournaments')
        else:
            # Tournament is ongoing - create a leave request
            if not player:
                messages.error(request, 'Player record not found.')
                return redirect('tournament_dashboard', tournament_id=tournament.id)
            
            # Check if there's already a pending request
            existing_request = LeaveRequest.objects.filter(
                tournament=tournament,
                player=player,
                status='pending'
            ).first()
            
            if existing_request:
                messages.warning(request, 'You already have a pending leave request for this tournament.')
                return redirect('tournament_dashboard', tournament_id=tournament.id)
            
            # Create the leave request
            reason = request.POST.get('reason', '')
            LeaveRequest.objects.create(
                tournament=tournament,
                player=player,
                user_profile=user_profile,
                reason=reason,
                status='pending'
            )
            
            messages.success(request, f'Your leave request has been submitted. The host will review it shortly.')
            return redirect('tournament_dashboard', tournament_id=tournament.id)
    
    return redirect('tournament_dashboard', tournament_id=tournament.id)


@login_required
def approve_leave_request(request, request_id):
    """Host approves a leave request"""
    leave_request = get_object_or_404(LeaveRequest, id=request_id)
    tournament = leave_request.tournament
    
    # Check if user is the host
    try:
        host_profile = HostProfile.objects.get(user=request.user)
        if tournament.created_by != host_profile:
            messages.error(request, 'You are not authorized to approve leave requests for this tournament.')
            return redirect('tournament_dashboard', tournament_id=tournament.id)
    except HostProfile.DoesNotExist:
        messages.error(request, 'You must be a host to approve leave requests.')
        return redirect('tournament_dashboard', tournament_id=tournament.id)
    
    if request.method == 'POST':
        # Update the request status
        from django.utils import timezone
        leave_request.status = 'approved'
        leave_request.reviewed_at = timezone.now()
        leave_request.reviewed_by = host_profile
        leave_request.save()
        
        # Remove the player from the tournament
        player = leave_request.player
        
        # Remove from point table first if exists
        PointTable.objects.filter(
            tournament=tournament,
            player=player
        ).delete()
        
        # Remove participant record if exists
        if player.user_profile:
            TournamentParticipant.objects.filter(
                tournament=tournament,
                user_profile=player.user_profile
            ).delete()
        
        # Remove the player
        player.delete()
        
        messages.success(request, f'{player.name} has been removed from the tournament.')
        return redirect('tournament_dashboard', tournament_id=tournament.id)
    
    return redirect('tournament_dashboard', tournament_id=tournament.id)


@login_required
def reject_leave_request(request, request_id):
    """Host rejects a leave request"""
    leave_request = get_object_or_404(LeaveRequest, id=request_id)
    tournament = leave_request.tournament
    
    # Check if user is the host
    try:
        host_profile = HostProfile.objects.get(user=request.user)
        if tournament.created_by != host_profile:
            messages.error(request, 'You are not authorized to reject leave requests for this tournament.')
            return redirect('tournament_dashboard', tournament_id=tournament.id)
    except HostProfile.DoesNotExist:
        messages.error(request, 'You must be a host to reject leave requests.')
        return redirect('tournament_dashboard', tournament_id=tournament.id)
    
    if request.method == 'POST':
        # Update the request status
        from django.utils import timezone
        leave_request.status = 'rejected'
        leave_request.reviewed_at = timezone.now()
        leave_request.reviewed_by = host_profile
        leave_request.save()
        
        messages.success(request, f'Leave request from {leave_request.player.name} has been rejected.')
        return redirect('tournament_dashboard', tournament_id=tournament.id)
    
    return redirect('tournament_dashboard', tournament_id=tournament.id)
