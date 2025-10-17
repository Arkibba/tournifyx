from django.contrib import admin
from .models import *

# Register your models here.
admin.site.register(UserProfile)
admin.site.register(HostProfile)
admin.site.register(Tournament)
admin.site.register(TournamentParticipant)
admin.site.register(Player)
admin.site.register(Match)
admin.site.register(LeaveRequest)


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'subject', 'created_at', 'is_read')
    list_filter = ('is_read', 'created_at')
    search_fields = ('name', 'email', 'subject', 'message')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)


admin.site.index_title = "TournifyX Admin"
admin.site.site_header = "TournifyX Admin Panel"
admin.site.site_title = "TournifyX Admin Panel"