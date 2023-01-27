from django.conf.urls import url

from core.views.stats import StatsView


urlpatterns = [url(r'^stats/?$', StatsView.as_view()),
               ]
