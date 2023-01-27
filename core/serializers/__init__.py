from django.conf import settings
from rest_framework import serializers


class TranslateModelSerializer(serializers.ModelSerializer):

    def _translate(self, obj, value):
        request = self.context['request']
        locale = request.GET.get('locale')
        if locale and locale in dict(settings.LANGUAGES):
            return getattr(obj, value + '_' + locale)
        return getattr(obj, value)
