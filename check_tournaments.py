from tournifyx.models import Tournament

# Print all tournaments with their public/active status
for t in Tournament.objects.all():
    print(f"ID: {t.id}, Name: {t.name}, Public: {t.is_public}, Active: {t.is_active}")

# Print only public and active tournaments
public_active = Tournament.objects.filter(is_public=True, is_active=True)
print("\nPublic & Active Tournaments:")
for t in public_active:
    print(f"ID: {t.id}, Name: {t.name}")
