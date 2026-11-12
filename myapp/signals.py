from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Account, UserProfile


@receiver(post_save, sender=User)
def create_profile_and_wallet(sender, instance, created, **kwargs):
    """Every user gets a profile and a wallet. Superusers default to the admin role."""
    if created:
        role = UserProfile.ROLE_ADMIN if instance.is_superuser else UserProfile.ROLE_CUSTOMER
        UserProfile.objects.get_or_create(user=instance, defaults={'role': role})
        Account.objects.get_or_create(user=instance)
