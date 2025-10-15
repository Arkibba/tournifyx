from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Tournament, Player, UserProfile


class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    profile_picture = forms.ImageField(required=False, help_text="Optional profile picture (max 5MB)")
    
    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2", "profile_picture")
    
    def clean_password1(self):
        # Override to remove all password validation
        password1 = self.cleaned_data.get("password1")
        return password1
    
    def clean_password2(self):
        # Override to only check if passwords match, no other validation
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("The two password fields didn't match.")
        return password2
    
    def clean_profile_picture(self):
        profile_picture = self.cleaned_data.get('profile_picture')
        if profile_picture:
            if profile_picture.size > 5 * 1024 * 1024:  # 5MB limit
                raise forms.ValidationError("Image file too large ( > 5MB )")
        return profile_picture
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
            # Create or get UserProfile with profile picture
            profile_picture = self.cleaned_data.get('profile_picture')
            user_profile, created = UserProfile.objects.get_or_create(user=user)
            if profile_picture:
                user_profile.avatar = profile_picture
                user_profile.save()
        return user


class PublicTournamentJoinForm(forms.Form):
    name = forms.CharField(max_length=100, label='Name')
    ign = forms.CharField(max_length=100, label='In-Game Name')
    contact_number = forms.CharField(max_length=20, label='Contact Number')



class TournamentForm(forms.ModelForm):
    players = forms.CharField(
        widget=forms.Textarea(attrs={
            'placeholder': 'Enter initial player names, one per line (optional for public tournaments)\nRemaining slots will be available for public registration',
            'rows': 5,
            'class': 'w-full p-2 rounded bg-gray-800 text-white border border-gray-600 focus:ring-2 focus:ring-orange-500'
        }),
        required=False,
        label="Initial Players (Optional)"
    )
    def clean(self):
        cleaned_data = super().clean()
        # Allow creating tournaments with partial player lists for public tournaments
        if self.instance.pk is None:  # Only for new tournaments
            is_public = cleaned_data.get('is_public')
            players = cleaned_data.get('players')
            # For private tournaments, require at least some players
            if not is_public and not players:
                self.add_error('players', 'Players are required for private tournaments.')
        
        # Validate knockout participant count
        match_type = cleaned_data.get('match_type')
        num_participants = cleaned_data.get('num_participants')
        if match_type == 'knockout' and num_participants:
            try:
                n = int(num_participants)
                if n < 2 or (n & (n - 1)) != 0:
                    self.add_error('num_participants', 'Knockout tournament capacity must be a power of two (2, 4, 8, 16, ...).')
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
