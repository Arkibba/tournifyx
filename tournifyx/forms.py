from django import forms
from .models import Tournament, Player


class PublicTournamentJoinForm(forms.Form):
    name = forms.CharField(max_length=100, label='Name')
    ign = forms.CharField(max_length=100, label='In-Game Name')
    contact_number = forms.CharField(max_length=20, label='Contact Number')



class TournamentForm(forms.ModelForm):
    players = forms.CharField(
        widget=forms.Textarea(attrs={
            'placeholder': 'Enter player names, one per line',
            'rows': 5,
            'class': 'w-full p-2 rounded bg-gray-800 text-white border border-gray-600 focus:ring-2 focus:ring-orange-500'
        }),
        required=False,
        label="Players"
    )
    def clean(self):
        cleaned_data = super().clean()
        # Only require players when creating, not updating
        if self.instance.pk is None:
            is_public = cleaned_data.get('is_public')
            players = cleaned_data.get('players')
            if not is_public and not players:
                self.add_error('players', 'Players are required for non-public tournaments.')
        # Enforce power-of-two participant count for knockout tournaments
        match_type = cleaned_data.get('match_type')
        num_participants = cleaned_data.get('num_participants')
        if match_type == 'knockout' and num_participants:
            try:
                n = int(num_participants)
                if n < 2 or (n & (n - 1)) != 0:
                    self.add_error('num_participants', 'Invalid participant number — knockout tournaments must use a power of two (2, 4, 8, 16, ...).')
            except Exception:
                self.add_error('num_participants', 'Invalid participant number.')
        return cleaned_data
    is_paid = forms.BooleanField(required=False, label="Paid Tournament")
    price = forms.DecimalField(required=False, min_value=0, label="Price to Join", initial=0.00)
    is_public = forms.BooleanField(required=False, label="Public Tournament")
    is_active = forms.BooleanField(required=False, label="Active Tournament")

    class Meta:
        model = Tournament
        fields = ['name', 'description', 'category', 'num_participants', 'match_type', 'is_paid', 'price', 'is_public', 'is_active', 'registration_deadline']
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'Enter tournament name',
                'class': 'w-full p-3 pl-3 rounded-xl bg-white/20 text-white focus:outline-none focus:ring-2 focus:ring-orange-500 shadow focus:bg-white/30 transition placeholder-gray-300'
            }),
            'description': forms.Textarea(attrs={
                'placeholder': 'Add description of your tournament',
                'rows': 3,
                'class': 'w-full p-3 pl-3 rounded-xl bg-white/20 text-white focus:outline-none focus:ring-2 focus:ring-orange-500 shadow focus:bg-white/30 transition placeholder-gray-300'
            }),
            'category': forms.Select(attrs={
                'class': 'w-full p-3 pl-3 rounded-xl bg-white/20 text-white focus:outline-none focus:ring-2 focus:ring-orange-500 shadow focus:bg-white/30 transition placeholder-gray-300 appearance-none pr-10'
            }),
            'match_type': forms.Select(attrs={
                'class': 'w-full p-3 pl-3 rounded-xl bg-white/20 text-white focus:outline-none focus:ring-2 focus:ring-orange-500 shadow focus:bg-white/30 transition placeholder-gray-300 appearance-none pr-10'
            }),
            'registration_deadline': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'w-full p-3 pl-3 rounded-xl bg-white/20 text-white focus:outline-none focus:ring-2 focus:ring-orange-500 shadow focus:bg-white/30 transition placeholder-gray-300'
            }),
        }









class JoinTournamentForm(forms.Form):
   code = forms.CharField(max_length=20, label="Tournament Code", widget=forms.TextInput(attrs={'class': 'form-control'}))







class PlayerForm(forms.ModelForm):
   class Meta:
       model = Player
       fields = ['name', 'team_name']  # Include team_name
