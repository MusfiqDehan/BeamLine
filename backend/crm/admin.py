from django.contrib import admin
from crm.models import (
    ChecklistTemplate,
    ConstructionProject,
    Contact,
    EmailCommunicationLog,
    GuestServiceUpsell,
    MaterialOrder,
    Opportunity,
    ProjectCost,
    ProjectTask,
    PropertyProfile,
    PropertyWorkOrder,
    ReservationTurn,
    SalesActivity,
)

admin.site.register(Contact)
admin.site.register(Opportunity)
admin.site.register(SalesActivity)
admin.site.register(ConstructionProject)
admin.site.register(ProjectTask)
admin.site.register(MaterialOrder)
admin.site.register(ProjectCost)
admin.site.register(EmailCommunicationLog)
admin.site.register(PropertyProfile)
admin.site.register(ChecklistTemplate)
admin.site.register(ReservationTurn)
admin.site.register(PropertyWorkOrder)
admin.site.register(GuestServiceUpsell)

