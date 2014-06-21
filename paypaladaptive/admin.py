from django.contrib import admin

from . import models


def update_adaptive_instance(modeladmin, request, queryset):
    for instance in queryset:
        instance.update(save=True)

update_adaptive_instance.short_description = u"Update"


class PaymentAdmin(admin.ModelAdmin):
    actions = [update_adaptive_instance]
    list_display = ('created_date', 'pay_key', 'status',)
    list_filter = ('status',)
    search_fields = ('=id', '=pay_key')


class PreapprovalAdmin(admin.ModelAdmin):
    list_display = ('preapproval_key', 'valid_until_date', 'status')
    actions = [update_adaptive_instance]


class RefundAdmin(admin.ModelAdmin):
    pass


class IPNLogAdmin(admin.ModelAdmin):
    list_display = (
        'created_date', 'verify_request_response',
        'return_status_code', 'duration',
        )


admin.site.register(models.Payment, PaymentAdmin)
admin.site.register(models.Preapproval, PreapprovalAdmin)
admin.site.register(models.Refund, RefundAdmin)
admin.site.register(models.IPNLog, IPNLogAdmin)
