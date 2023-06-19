from django.contrib.auth.models import User
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from core.models.facade import Profile
from core.models.facade import SmsHistory
from core.models.facade import SourceOfFunds
from core.models.facade import TwoFactorSecretTokens
from core.models.facade import UserKYC
from core.models.facade import UserRestrictions
from core.models.inouts.withdrawal import WithdrawalUserLimit


@receiver(post_save, sender=User)
def create_or_save_user(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(
            user=instance,
            user_type=Profile.USER_TYPE_STAFF if instance.is_staff else Profile.USER_TYPE_DEFAULT
        )
        SourceOfFunds.objects.create(user=instance)
        UserRestrictions.objects.create(user=instance)  # TODO get default data from settings
        WithdrawalUserLimit.get_limits(user=instance)
    else:
        instance.profile.save()
    TwoFactorSecretTokens.objects.get_or_create(user=instance)
    UserKYC.objects.get_or_create(user=instance)


@receiver(pre_save, sender=Profile)
def notify_sof_updated(sender, instance, *args, **kwargs):
    from core.tasks.facade import notify_sof_request_status_changed_user
    old_instance = Profile.objects.filter(id=instance.id).first()

    if old_instance is None:
        return

    if old_instance.is_sof_verified != instance.is_sof_verified:
        notify_sof_request_status_changed_user.apply_async([instance.user.id])

    if old_instance.phone != instance.phone or \
            old_instance.withdrawals_sms_confirmation != instance.withdrawals_sms_confirmation:

        SmsHistory.objects.create(
            user=instance.user,
            withdrawals_sms_confirmation=instance.withdrawals_sms_confirmation,
            phone=instance.phone
        )

    if old_instance.user_type != instance.user_type:
        User.objects.filter(id=instance.user.id).update(
            is_staff=bool(instance.user_type == Profile.USER_TYPE_STAFF)
        )
