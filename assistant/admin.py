from django.contrib import admin
from .models import UserHealthProfile

# Register your models here.

@admin.register(UserHealthProfile)
class UserHealthProfileAdmin(admin.ModelAdmin):
    list_display = ['name', 'age', 'weight', 'gender', 'blood_category', 'eligibility_status', 'completed', 'created_at']
    list_filter = ['completed', 'eligibility_status', 'has_diabetes', 'had_corona', 'has_anemia', 'created_at']
    search_fields = ['name', 'session_id', 'blood_category', 'eligibility_status']
    readonly_fields = ['created_at', 'updated_at', 'eligibility_status', 'eligibility_reasons']
    fieldsets = (
        ('Personal Information', {
            'fields': ('name', 'age', 'weight', 'gender', 'blood_category', 'user', 'session_id')
        }),
        ('Health Information', {
            'fields': ('has_diabetes', 'has_anemia', 'hemoglobin_level', 'blood_pressure', 'had_corona',
                      'has_allergies', 'allergies_details', 'taking_medications', 'medications_details',
                      'has_chronic_diseases', 'chronic_diseases_details', 'has_infectious_disease', 
                      'infectious_disease_details')
        }),
        ('Donation History', {
            'fields': ('donated_before', 'last_donation_date')
        }),
        ('Other Factors', {
            'fields': ('has_tattoo_piercing', 'tattoo_piercing_date', 'is_pregnant', 'is_breastfeeding',
                      'has_surgery_recently', 'surgery_details')
        }),
        ('Eligibility Assessment', {
            'fields': ('eligibility_status', 'eligibility_reasons', 'completed')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )
