from copy import deepcopy

from admin_tools.dashboard.modules import DashboardModule
from admin_tools.menu.items import MenuItem
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


class MenuList(DashboardModule):
    """
    A module that displays a list of links.
    As well as the :class:`~admin_tools.dashboard.modules.DashboardModule`
    properties, the :class:`~admin_tools.dashboard.modules.LinkList` takes
    an extra keyword argument:

    ``layout``
        The layout of the list, possible values are ``stacked`` and ``inline``.
        The default value is ``stacked``.

    Link list modules children are simple python dictionaries that can have the
    following keys:

    ``title``
        The link title.

    ``url``
        The link URL.

    ``external``
        Boolean that indicates whether the link is an external one or not.

    ``description``
        A string describing the link, it will be the ``title`` attribute of
        the html ``a`` tag.

    ``attrs``
        Hash comprising attributes of the html ``a`` tag.

    Children can also be iterables (lists or tuples) of length 2, 3, 4 or 5.

    Here's a small example of building a link list module::

        from admin_tools.dashboard import modules, Dashboard

        class MyDashboard(Dashboard):
            def __init__(self, **kwargs):
                Dashboard.__init__(self, **kwargs)

                self.children.append(modules.LinkList(
                    layout='inline',
                    children=(
                        {
                            'title': 'Python website',
                            'url': 'http://www.python.org',
                            'external': True,
                            'description': 'Python language rocks !',
                            'attrs': {'target': '_blank'},
                        },
                        ['Django', 'http://www.djangoproject.com', True],
                        ['Some internal link', '/some/internal/link/'],
                    )
                ))

    The screenshot of what this code produces:

    .. image:: images/linklist_dashboard_module.png
    """

    title = _('Links')
    template = 'admin/dashboard/modules/menu/list.html'
    layout = 'stacked'

    def init_with_context(self, context):
        # if self._initialized:
        #     return
        # new_children = []
        # print(self.children)
        # for link in self.children:
        #     if isinstance(link, (tuple, list,)):
        #         link_dict = {'title': link[0], 'url': link[1]}
        #         if len(link) >= 3:
        #             link_dict['external'] = link[2]
        #         if len(link) >= 4:
        #             link_dict['description'] = link[3]
        #         if len(link) >= 5:
        #             link_dict['attrs'] = link[4]
        #         link = link_dict
        #     if 'attrs' not in link:
        #         link['attrs'] = {}
        #     link['attrs']['href'] = link['url']
        #     if link.get('description', ''):
        #         link['attrs']['title'] = link['description']
        #     if link.get('external', False):
        #         link['attrs']['class'] = ' '.join(
        #             ['external-link'] + link['attrs'].get('class', '').split()
        #         ).strip()
        #     # link['attrs'] = flatatt(link['attrs'])
        #     new_children.append(link)
        # self.children = new_children
        # self._initialized = True
        pass

    @staticmethod
    def update_menu_items_dashboard_template(menu_items: list):
        new_items = []
        for menu_item in menu_items:
            if isinstance(menu_item, MenuItem):
                new_item = deepcopy(menu_item)
                new_item.template = 'admin/dashboard/modules/menu/item.html'
                new_items.append(new_item)

        return new_items
