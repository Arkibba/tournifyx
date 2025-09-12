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
    return render(request, 'home.html')

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

        user = User.objects.create_user(username=username, password=password1, email=email)
        user.save()

        # Automatically create UserProfile
        UserProfile.objects.create(user=user)

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
    return redirect('login')


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

            for name in player_names:
                if name.strip():  # Ignore empty lines
                    Player.objects.create(
                        tournament=tournament,
                        name=name.strip(),
                        added_by=host_profile
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
    participant_names = [p.name for p in participants]

    if tournament.match_type == 'knockout':
        fixtures = generate_knockout_fixtures(participant_names)
    else:  # League
        fixtures = generate_league_fixtures(participant_names)

    return render(request, 'tournament_dashboard.html', {
        'tournament': tournament,
        'participants': participants,
        'fixtures': fixtures,
    })


@login_required(login_url='login')
def user_tournaments(request):
    user_profile = UserProfile.objects.get(user=request.user)
    host_profile = HostProfile.objects.filter(user=request.user).first()
    hosted_tournaments = Tournament.objects.filter(created_by=host_profile) if host_profile else Tournament.objects.none()
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