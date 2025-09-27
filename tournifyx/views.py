from django.http import HttpResponse
from django.contrib.auth import login as auth_login, logout as auth_logout, authenticate
from django.contrib.auth.models import User
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import *
from django.contrib.auth.decorators import login_required
from .forms import TournamentForm, JoinTournamentForm, PlayerForm, PublicTournamentJoinForm
import secrets
import string
import random
from .utils import generate_knockout_fixtures, generate_league_fixtures
import itertools
from django.http import HttpResponseForbidden
from django.core.cache import cache

from .models import Match, Player, PointTable, Tournament
from django.views.decorators.http import require_POST
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
    messages.success(request, 'Match result updated and point table recalculated.')
    return redirect('tournament_dashboard', tournament_id=match.tournament.id)


# Helper function to update points for a match
def update_points_for_match(match, prev_result=None):
    # Recalculate the entire point table for the tournament
    tournament = match.tournament
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
            pt2, _ = PointTable.objects.get_or_create(tournament=tournament, player=m.player2)
            pt1.matches_played += 1
            pt2.matches_played += 1
            if m.is_draw:
                pt1.draws += 1
                pt2.draws += 1
                pt1.points += 1
                pt2.points += 1
            elif m.winner == m.player1:
                pt1.wins += 1
                pt2.losses += 1
                pt1.points += 3
            elif m.winner == m.player2:
                pt2.wins += 1
                pt1.losses += 1
                pt2.points += 3
            pt1.save()
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


            player_objs = []
            for name in player_names:
                if name.strip():  # Ignore empty lines
                    player_objs.append(Player.objects.create(
                        tournament=tournament,
                        name=name.strip(),
                        added_by=host_profile
                    ))

            # Create Match objects for all fixtures (league: all pairs, knockout: shuffled pairs)
            if tournament.match_type == 'knockout':
                fixture_pairs = generate_knockout_fixtures([p.name for p in player_objs])
            else:
                fixture_pairs = generate_league_fixtures([p.name for p in player_objs])

            # Map player names to Player objects
            name_to_player = {p.name: p for p in player_objs}
            from tournifyx.models import Match
            for p1, p2 in fixture_pairs:
                Match.objects.create(
                    tournament=tournament,
                    player1=name_to_player[p1],
                    player2=name_to_player[p2],
                    stage='GROUP',  # Default to group/league stage
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
        'is_host': is_host,
    })


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
    return render(request, 'public_tournaments.html', {'tournaments': tournaments})