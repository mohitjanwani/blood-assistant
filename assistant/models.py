from django.db import models
from django.contrib.auth.models import User

# Create your models here.

class UserHealthProfile(models.Model):
    """Stores user responses to health questions for blood donation eligibility"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    session_id = models.CharField(max_length=255, unique=True)  # For anonymous users
    name = models.CharField(max_length=100, blank=True)
    age = models.IntegerField(null=True, blank=True)
    weight = models.FloatField(null=True, blank=True)  # in kg
    gender = models.CharField(max_length=20, blank=True)
    has_diabetes = models.BooleanField(null=True, blank=True)
    had_corona = models.BooleanField(null=True, blank=True)
    blood_pressure = models.CharField(max_length=50, blank=True)
    blood_category = models.CharField(max_length=10, blank=True)  # A+, B+, O+, etc.
    has_allergies = models.BooleanField(null=True, blank=True)
    allergies_details = models.TextField(blank=True)
    taking_medications = models.BooleanField(null=True, blank=True)
    medications_details = models.TextField(blank=True)
    donated_before = models.BooleanField(null=True, blank=True)
    last_donation_date = models.CharField(max_length=50, blank=True)
    has_chronic_diseases = models.BooleanField(null=True, blank=True)
    chronic_diseases_details = models.TextField(blank=True)
    has_anemia = models.BooleanField(null=True, blank=True)
    hemoglobin_level = models.CharField(max_length=20, blank=True)
    has_infectious_disease = models.BooleanField(null=True, blank=True)
    infectious_disease_details = models.TextField(blank=True)
    has_tattoo_piercing = models.BooleanField(null=True, blank=True)
    tattoo_piercing_date = models.CharField(max_length=50, blank=True)
    is_pregnant = models.BooleanField(null=True, blank=True)
    is_breastfeeding = models.BooleanField(null=True, blank=True)
    has_surgery_recently = models.BooleanField(null=True, blank=True)
    surgery_details = models.TextField(blank=True)
    eligibility_status = models.CharField(max_length=50, blank=True)  # Eligible, Not Eligible, etc.
    eligibility_reasons = models.TextField(blank=True)
    # Legacy fields (kept for migration compatibility)
    question_7 = models.TextField(blank=True)
    question_8 = models.TextField(blank=True)
    question_9 = models.TextField(blank=True)
    question_10 = models.TextField(blank=True)
    completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
