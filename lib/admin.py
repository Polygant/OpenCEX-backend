import base64
from decimal import Decimal
from gettext import ngettext

from django import forms
from django.conf import settings
from django.contrib import admin
from django.contrib import messages
from django.contrib.admin import helpers
from django.contrib.admin.options import ModelAdmin, csrf_protect_m, IncorrectLookupParameters
from django.contrib.admin.utils import (
    model_ngettext, )
from django.core.exceptions import (
    PermissionDenied, )
from django.http import HttpResponseRedirect
from django.template.response import SimpleTemplateResponse, TemplateResponse
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _, ngettext

IS_POPUP_VAR = '_popup'
TO_FIELD_VAR = '_to_field'


HORIZONTAL, VERTICAL = 1, 2


class NoTransactionAdmin(admin.ModelAdmin):
    exclude = ('transaction',)


class ReadOnlyMixin:
    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]


class NoDeleteMixIn(object):
    no_delete = True

    def has_add_permission(self, request):
        return False if self.no_delete else True

    def has_delete_permission(self, request, obj=None):
        return False if self.no_delete else True

    def get_actions(self, request):
        actions = super(NoDeleteMixIn, self).get_actions(request)
        if self.no_delete and 'delete_selected' in actions:
            del actions['delete_selected']
        return actions


class NoAddMixIn:
    no_add = True

    def has_add_permission(self, request):
        return False if self.no_add else True


class ImmutableMixIn(NoDeleteMixIn, NoAddMixIn):
    no_save = True

    def change_view(self, request, object_id, extra_context=None):
        extra_context = extra_context or {}
        if self.no_save:
            extra_context['show_save'] = False
            extra_context['show_save_and_continue'] = False
        return super(ImmutableMixIn, self).change_view(request, object_id, extra_context=extra_context)


class JsonListViewMixin(object):
    """
    Displays json field values in list view page
    Uses json_list_fields dict, where the key is JSONField name, the value is some key in json
    """
    json_list_fields = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        all_json_fields = [item for sublist in self.json_list_fields.values() for item in sublist]
        self.list_display += all_json_fields

        for json_field, fields in self.json_list_fields.items():
            for custom_field in fields:
                self._generate_json_field(json_field, custom_field)

    def get_handler_fn(self, json_field_name, fieldname):
        def handler(obj):
            res = getattr(obj, json_field_name).get(fieldname)
            # show res as 0.0000000 instead of 0E-8
            if res and res.replace('E-', '').isdigit():
                res = '{:f}'.format(Decimal(res))
            return res
        handler.__name__ = fieldname
        return handler

    def _generate_json_field(self, json_field_name, fieldname):
        handler = self.get_handler_fn(json_field_name, fieldname)
        setattr(self, fieldname, handler)


class JsonListApiViewMixin(JsonListViewMixin):
    def get_handler_fn(self, json_field_name, fieldname):
        def handler(view, obj):
            res = getattr(obj, json_field_name).get(fieldname)
            # show res as 0.0000000 instead of 0E-8
            if res and res.replace('E-', '').isdigit():
                res = '{:f}'.format(Decimal(res))
            return res
        handler.__name__ = fieldname
        return handler


class BaseModelAdmin(NoDeleteMixIn, ModelAdmin):
    show_full_result_count = False

    class Media:
        js = [
            'admin/js/jquery.init.js',
            f'{settings.STATIC_URL}js/menu_filter_collapse.js',
        ]

    @csrf_protect_m
    def changelist_view(self, request, extra_context=None):
        """
        The 'change list' admin view for this model.
        """
        from django.contrib.admin.views.main import ERROR_FLAG
        opts = self.model._meta
        app_label = opts.app_label
        if not self.has_view_or_change_permission(request):
            raise PermissionDenied

        try:
            cl = self.get_changelist_instance(request)
        except IncorrectLookupParameters:
            # Wacky lookup parameters were given, so redirect to the main
            # changelist page, without parameters, and pass an 'invalid=1'
            # parameter via the query string. If wacky parameters were given
            # and the 'invalid=1' parameter was already in the query string,
            # something is screwed up with the database, so display an error
            # page.
            if ERROR_FLAG in request.GET:
                return SimpleTemplateResponse('admin/invalid_setup.html', {
                    'title': _('Database error'),
                })
            return HttpResponseRedirect(request.path + '?' + ERROR_FLAG + '=1')

        # If the request was POSTed, this might be a bulk action or a bulk
        # edit. Try to look up an action or confirmation first, but if this
        # isn't an action the POST will fall through to the bulk edit check,
        # below.
        action_failed = False
        selected = request.POST.getlist(helpers.ACTION_CHECKBOX_NAME)

        actions = self.get_actions(request)
        # Actions with no confirmation
        if (actions and request.method == 'POST' and
                'index' in request.POST and '_save' not in request.POST):
            if selected:
                response = self.response_action(request, queryset=cl.get_queryset(request))
                if response:
                    return response
                else:
                    action_failed = True
            else:
                msg = _("Items must be selected in order to perform "
                        "actions on them. No items have been changed.")
                self.message_user(request, msg, messages.WARNING)
                action_failed = True

        # Actions with confirmation
        if (actions and request.method == 'POST' and
                helpers.ACTION_CHECKBOX_NAME in request.POST and
                'index' not in request.POST and '_save' not in request.POST):
            if selected:
                response = self.response_action(request, queryset=cl.get_queryset(request))
                if response:
                    return response
                else:
                    action_failed = True

        if action_failed:
            # Redirect back to the changelist page to avoid resubmitting the
            # form if the user refreshes the browser or uses the "No, take
            # me back" button on the action confirmation page.
            return HttpResponseRedirect(request.get_full_path())

        # If we're allowing changelist editing, we need to construct a formset
        # for the changelist given all the fields to be edited. Then we'll
        # use the formset to validate/process POSTed data.
        formset = cl.formset = None

        # Handle POSTed bulk-edit data.
        if request.method == 'POST' and cl.list_editable and '_save' in request.POST:
            if not self.has_change_permission(request):
                raise PermissionDenied
            FormSet = self.get_changelist_formset(request)
            modified_objects = self._get_list_editable_queryset(request, FormSet.get_default_prefix())
            formset = cl.formset = FormSet(request.POST, request.FILES, queryset=modified_objects)
            if formset.is_valid():
                changecount = 0
                for form in formset.forms:
                    if form.has_changed():
                        obj = self.save_form(request, form, change=True)
                        self.save_model(request, obj, form, change=True)
                        self.save_related(request, form, formsets=[], change=True)
                        change_msg = self.construct_change_message(request, form, None)
                        self.log_change(request, obj, change_msg)
                        changecount += 1

                if changecount:
                    msg = ngettext(
                        "%(count)s %(name)s was changed successfully.",
                        "%(count)s %(name)s were changed successfully.",
                        changecount
                    ) % {
                              'count': changecount,
                              'name': model_ngettext(opts, changecount),
                          }
                    self.message_user(request, msg, messages.SUCCESS)

                return HttpResponseRedirect(request.get_full_path())

        # Handle GET -- construct a formset for display.
        elif cl.list_editable and self.has_change_permission(request):
            FormSet = self.get_changelist_formset(request)
            formset = cl.formset = FormSet(queryset=cl.result_list)

        # Build the list of media to be used by the formset.
        if formset:
            media = self.media + formset.media
        else:
            media = self.media

        # Build the action form and populate it with available actions.
        choices_with_extra = []
        if actions:
            action_form = self.action_form(auto_id=None)
            choices = self.get_action_choices(request)
            action_form.fields['action'].choices = choices
            media += action_form.media

            for action_name, description in choices:
                extra_fields = []
                if isinstance(self.actions, dict):
                    fields = self.actions.get(action_name) or []
                    for field in fields:
                        form_field = field.get('type') or forms.CharField()
                        html = form_field.widget.render(field['name'], field.get('default', ''))
                        label = field.get('label') or field['name'].capitalize().replace('_', ' ')
                        extra_fields.append((label, mark_safe(html)))

                if extra_fields:
                    choices_with_extra.append((action_name, extra_fields))

        else:
            action_form = None

        selection_note_all = ngettext(
            '%(total_count)s selected',
            'All %(total_count)s selected',
            cl.result_count
        )

        context = {
            **self.admin_site.each_context(request),
            'module_name': str(opts.verbose_name_plural),
            'selection_note': _('0 of %(cnt)s selected') % {'cnt': len(cl.result_list)},
            'selection_note_all': selection_note_all % {'total_count': cl.result_count},
            'title': cl.title,
            'subtitle': None,
            'is_popup': cl.is_popup,
            'to_field': cl.to_field,
            'cl': cl,
            'media': media,
            'has_add_permission': self.has_add_permission(request),
            'opts': cl.opts,
            'action_form': action_form,
            'extra_actions_fields': choices_with_extra,
            'actions_on_top': self.actions_on_top,
            'actions_on_bottom': self.actions_on_bottom,
            'actions_selection_counter': self.actions_selection_counter,
            'preserved_filters': self.get_preserved_filters(request),
            **(extra_context or {}),
        }

        request.current_app = self.admin_site.name

        return TemplateResponse(request, self.change_list_template or [
            'admin/%s/%s/change_list.html' % (app_label, opts.model_name),
            'admin/%s/change_list.html' % app_label,
            'admin/change_list.html'
        ], context)


class SuperUserMixIn(object):
    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def get_readonly_fields(self, request, obj=None):
        if request.user.is_superuser:
            fields = super(SuperUserMixIn, self).get_readonly_fields(request, obj)
        else:
            fields = [f.name for f in self.model._meta.fields]
        return fields

    def change_view(self, request, object_id, extra_context=None):
        if not request.user.is_superuser:
            extra_context = extra_context or {}
            extra_context['show_save'] = False
            extra_context['show_save_and_continue'] = False
        return super(SuperUserMixIn, self).change_view(request, object_id, extra_context=extra_context)


class MasterPassForm(forms.ModelForm):
    password = forms.CharField(required=True)

    def clean_password(self):
        password = self.cleaned_data['password']
        if password != settings.ADMIN_MASTERPASS:
            raise forms.ValidationError('Invalid password!')
        return password


def download_file_as_base64(filename, content, mimetype):
    return {
        'filename': filename,
        'content': base64.b64encode(content),
        'mimetype': mimetype
    }
