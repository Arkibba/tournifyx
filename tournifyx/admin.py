from django.contrib import admin
from .models import *

# Register your models here.
admin.site.register(UserProfile)
admin.site.register(HostProfile)
admin.site.register(Tournament)
admin.site.register(TournamentParticipant)
admin.site.register(Player)
admin.site.register(Match)


admin.site.index_title = "TournifyX Admin"
admin.site.site_header = "TournifyX Admin Panel"
admin.site.site_title = "TournifyX Admin Panel"