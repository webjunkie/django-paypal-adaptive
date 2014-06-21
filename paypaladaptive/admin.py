from django.contrib import admin

from . import models


def update_adaptive_instance(modeladmin, request, queryset):
    for instance in queryset:
        instance.update(save=True)

update_adaptive_instance.short_description = u"Update"


class PaymentAdmin(admin.ModelAdmin):
    actions = [update_adaptive_instance]


class PreapprovalAdmin(admin.ModelAdmin):
    list_display = ('preapproval_key', 'valid_until_date', 'status')
    actions = [update_adaptive_instance]


class RefundAdmin(admin.ModelAdmin):
    pass


admin.site.register(models.Payment, PaymentAdmin)
admin.site.register(models.Preapproval, PreapprovalAdmin)
admin.site.register(models.Refund, RefundAdmin)
