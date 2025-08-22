from django.contrib.auth import login as auth_login, logout as auth_logout, authenticate
from django.contrib.auth.models import User
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import *
from django.contrib.auth.decorators import login_required
from .forms import TournamentForm, JoinTournamentForm, PlayerForm
import secrets
import string
import random
from .utils import generate_knockout_fixtures, generate_league_fixtures
import itertools
from django.http import HttpResponseForbidden
from django.core.cache import cache

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


def join_tournament(request):
    if request.method == 'POST':
        form = JoinTournamentForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data['code']
            try:
                # Fetch the tournament using the code
                tournament = Tournament.objects.get(code=code)  # Ensure this fetches the latest data
                return redirect('tournament_dashboard', tournament_id=tournament.id)
            except Tournament.DoesNotExist:
                # If the tournament code is invalid
                messages.error(request, 'Invalid tournament code!')
                return render(request, 'join_tournament.html', {'form': form})
    else:
        form = JoinTournamentForm()
    return render(request, 'join_tournament.html', {'form': form})


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
    try:
        host_profile = HostProfile.objects.get(user=request.user)
    except HostProfile.DoesNotExist:
        return HttpResponseForbidden("You are not authorized to view this page.")

    tournaments = Tournament.objects.filter(created_by=host_profile)

    if request.method == 'POST':
        tournament_id = request.POST.get('tournament_id')
        action = request.POST.get('action')

        if action == 'delete':
            Tournament.objects.filter(id=tournament_id, created_by=host_profile).delete()
        elif action == 'update':
            # Redirect to a tournament update page (to be implemented)
            return redirect('update_tournament', tournament_id=tournament_id)

    return render(request, 'user_tournaments.html', {'tournaments': tournaments})


@login_required(login_url='login')
def update_tournament(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id, created_by__user=request.user)

    if request.method == 'POST':
        form = TournamentForm(request.POST, instance=tournament)
        if form.is_valid():
            # Save the tournament details
            form.save()

            # Update participants
            player_names = form.cleaned_data['players'].splitlines()
            existing_players = Player.objects.filter(tournament=tournament)

            # Remove players not in the updated list
            existing_player_names = [player.name for player in existing_players]
            for player in existing_players:
                if player.name not in player_names:
                    player.delete()

            # Add new players
            for name in player_names:
                if name.strip() and name not in existing_player_names:
                    Player.objects.create(
                        tournament=tournament,
                        name=name.strip(),
                        added_by=tournament.created_by
                    )
            messages.success(request, f"Tournament '{tournament.name}' updated successfully!")
            return redirect('user_tournaments')
    else:
        # Prepopulate the players field with existing participant names
        existing_players = Player.objects.filter(tournament=tournament)
        player_names = "\n".join([player.name for player in existing_players])
        form = TournamentForm(instance=tournament, initial={'players': player_names})

    return render(request, 'update_tournament.html', {'form': form, 'tournament': tournament})



def about(request):
    """Render the About page."""
    return render(request, 'about.html', {
        'creators': [
            'Md. Zubaer Islam',
            'MD. Arkive',
            'Shoshi Khan'
        ]
    })