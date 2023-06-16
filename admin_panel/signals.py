from django.contrib.auth import get_user_model
from django.db.models.signals import pre_save
from django.dispatch import receiver

from core.enums.profile import UserTypeEnum
from core.models import Profile


@receiver(pre_save, sender=Profile)
def on_change(sender: Profile, instance: Profile, **kwargs):
    if instance.id is None:
        if instance.user_type == UserTypeEnum.staff.value:
            get_user_model().objects.filter(id=instance.user.id).update(is_staff=True)
        else:
            get_user_model().objects.filter(id=instance.user.id).update(is_staff=False)
    else:
        previous = Profile.objects.get(id=instance.id)
        if previous.user_type != instance.user_type:
            if instance.user_type == UserTypeEnum.staff.value:
                get_user_model().objects.filter(id=instance.user.id).update(is_staff=True)
            else:
                get_user_model().objects.filter(id=instance.user.id).update(is_staff=False)
