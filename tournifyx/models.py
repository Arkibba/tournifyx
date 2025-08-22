from django.contrib.auth.models import User
from django.db import models

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    joined_tournaments = models.ManyToManyField('Tournament', through='TournamentParticipant')

    def _str_(self):
        return self.user.username

# Separate host profile
class HostProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    organization = models.CharField(max_length=100, blank=True)

    def _str_(self):
        return f"Host: {self.user.username}"


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    def _str_(self):
        return self.name

# models.py

class Tournament(models.Model):
    CATEGORY_CHOICES = [
        ('valorant', 'Valorant'),
        ('football', 'Football'),
        ('cricket', 'Cricket'),
        ('chess', 'Chess'),
    ]

    name = models.CharField(max_length=100)
    description = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='valorant')
    num_participants = models.PositiveIntegerField()
    match_type = models.CharField(max_length=10, choices=[('knockout', 'Knockout'), ('league', 'League')], default='knockout')
    created_by = models.ForeignKey(HostProfile, on_delete=models.CASCADE)
    code = models.CharField(max_length=6, unique=True)
    is_active = models.BooleanField(default=True)  # Add a default value

    def __str__(self):
        return self.name


class TournamentParticipant(models.Model):
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user_profile', 'tournament')

    def _str_(self):
        return f"{self.user_profile.user.username} in {self.tournament.name}"

# Player model managed by host inside a tournament
class Player(models.Model):
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    team_name = models.CharField(max_length=100, null=True, blank=True)  # Make this optional
    added_by = models.ForeignKey(HostProfile, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return f"{self.name} - {self.tournament.name}"


class Match(models.Model):
    STAGE_CHOICES = [
        ('GROUP', 'Group Stage'),
        ('KNOCKOUT', 'Knockout'),
        ('QUARTER', 'Quarterfinal'),
        ('SEMI', 'Semifinal'),
        ('FINAL', 'Final'),
    ]
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE)
    player1 = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='match_player1')
    player2 = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='match_player2')
    stage = models.CharField(max_length=10, choices=STAGE_CHOICES)
    scheduled_time = models.DateTimeField()
    winner = models.ForeignKey(Player, on_delete=models.SET_NULL, null=True, blank=True, related_name='match_winner')

    def _str_(self):
        return f"{self.player1.name} vs {self.player2.name} ({self.stage})"