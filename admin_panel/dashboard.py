"""
This file was generated with the customdashboard management command, it
contains the two classes for the main dashboard and app index dashboard.
You can customize these classes as you want.

To activate your index dashboard add the following to your settings.py::
    ADMIN_TOOLS_INDEX_DASHBOARD = 'oc-backend.dashboard.CustomIndexDashboard'

And to activate the app index dashboard::
    ADMIN_TOOLS_APP_INDEX_DASHBOARD = 'oc-backend.dashboard.CustomAppIndexDashboard'
"""
from admin_panel.menu import MENU_ITEMS
from admin_panel.modules import MenuList

try:
    # we use django.urls import as version detection as it will fail on django 1.11 and thus we are safe to use
    # gettext_lazy instead of ugettext_lazy instead
    from django.urls import reverse
    from django.utils.translation import gettext_lazy as _
except ImportError:
    from django.core.urlresolvers import reverse
    from django.utils.translation import ugettext_lazy as _
from admin_tools.dashboard import modules, Dashboard, AppIndexDashboard
from admin_tools.utils import get_admin_site_name


class CustomIndexDashboard(Dashboard):
    DASHBOARD_MENU_ITEMS = MenuList.update_menu_items_dashboard_template(MENU_ITEMS)

    """
    Custom index dashboard for oc-backend.
    """
    def init_with_context(self, context):

        self.children.append(MenuList(
            _('Applications'),
            draggable=False,
            deletable=False,
            collapsible=False,
            children=self.DASHBOARD_MENU_ITEMS,
        ))

        # append a recent actions module
        self.children.append(modules.RecentActions(_('Recent Actions'), 5))


class CustomAppIndexDashboard(AppIndexDashboard):
    """
    Custom app index dashboard for oc-backend.
    """

    # we disable title because its redundant with the model list module
    title = ''

    def __init__(self, *args, **kwargs):
        AppIndexDashboard.__init__(self, *args, **kwargs)

        # append a model list module and a recent actions module
        self.children += [
            modules.ModelList(self.app_title, self.models),
            modules.RecentActions(
                _('Recent Actions'),
                include_list=self.get_app_content_types(),
                limit=5
            )
        ]

    def init_with_context(self, context):
        """
        Use this method if you need to access the request context.
        """
        return super(CustomAppIndexDashboard, self).init_with_context(context)
