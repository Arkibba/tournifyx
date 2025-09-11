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
        is_public = cleaned_data.get('is_public')
        players = cleaned_data.get('players')
        if not is_public and not players:
            self.add_error('players', 'Players are required for non-public tournaments.')
        return cleaned_data
    is_paid = forms.BooleanField(required=False, label="Paid Tournament")
    price = forms.DecimalField(required=False, min_value=0, label="Price to Join", initial=0.00)
    is_public = forms.BooleanField(required=False, label="Public Tournament")

    class Meta:
        model = Tournament
        fields = ['name', 'description', 'category', 'num_participants', 'match_type', 'is_paid', 'price', 'is_public']
        widgets = {
            'category': forms.Select(attrs={
                'class': 'w-full p-2 rounded bg-gray-800 text-white border border-gray-600 focus:ring-2 focus:ring-orange-500'
            }),
            'match_type': forms.Select(attrs={
                'class': 'w-full p-2 rounded bg-gray-800 text-white border border-gray-600 focus:ring-2 focus:ring-orange-500'
            }),
        }


class JoinTournamentForm(forms.Form):
   code = forms.CharField(max_length=20, label="Tournament Code", widget=forms.TextInput(attrs={'class': 'form-control'}))


class PlayerForm(forms.ModelForm):
   class Meta:
       model = Player
       fields = ['name', 'team_name']  # Include team_name
