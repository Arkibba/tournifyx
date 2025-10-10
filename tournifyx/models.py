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
        ('football', 'Football'),
        ('valorant', 'Valorant'),
        ('cricket', 'Cricket'),
        ('basketball', 'Basketball'),
        # Add more as needed
    ]
    MATCH_TYPE_CHOICES = [
        ('knockout', 'Knockout'),
        ('league', 'League'),
        # Add more as needed
    ]

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    num_participants = models.IntegerField(default=0)
    match_type = models.CharField(max_length=50, choices=MATCH_TYPE_CHOICES)
    created_by = models.ForeignKey('HostProfile', on_delete=models.CASCADE)
    code = models.CharField(max_length=6, unique=True)
    is_active = models.BooleanField(default=True)
    is_paid = models.BooleanField(default=False)
    price = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    is_public = models.BooleanField(default=False)  # Add this line
    registration_deadline = models.DateTimeField(null=True, blank=True)
    

    def __str__(self):
        return self.name


class TournamentParticipant(models.Model):
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE)
    user_profile = models.ForeignKey('UserProfile', on_delete=models.CASCADE)
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



# PointTable model to track points for each player/team in a tournament
class PointTable(models.Model):
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE)
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    matches_played = models.PositiveIntegerField(default=0)
    wins = models.PositiveIntegerField(default=0)
    losses = models.PositiveIntegerField(default=0)
    draws = models.PositiveIntegerField(default=0)
    points = models.IntegerField(default=0)

    class Meta:
        unique_together = ('tournament', 'player')

    def __str__(self):
        return f"{self.player.name} - {self.points} pts"


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
    player2 = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='match_player2', null=True, blank=True)
    stage = models.CharField(max_length=10, choices=STAGE_CHOICES)
    round_number = models.IntegerField(default=1)
    parent_match1 = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='children_as_parent1')
    parent_match2 = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='children_as_parent2')
    scheduled_time = models.DateTimeField(null=True, blank=True)
    winner = models.ForeignKey(Player, on_delete=models.SET_NULL, null=True, blank=True, related_name='match_winner')
    is_draw = models.BooleanField(default=False)

    def _str_(self):
        return f"{self.player1.name} vs {self.player2.name} ({self.stage})"
