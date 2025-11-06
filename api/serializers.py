from rest_framework import serializers
from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema_field
from .models import University, Organization, College
from authentication.serializers import UserSerializer


User = get_user_model()


class UniversitySerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    total_organizations = serializers.SerializerMethodField()
    total_colleges = serializers.SerializerMethodField()

    class Meta:
        model = University
        fields = ['id', 'university_id', 'name', 'address', 'logo',
                 'created_by', 'created_at', 'updated_at', 'is_active',
                 'total_organizations', 'total_colleges']
        read_only_fields = ['id', 'university_id', 'created_by', 'created_at', 'updated_at']

    @extend_schema_field(serializers.IntegerField())
    def get_total_organizations(self, obj):
        return obj.organizations.filter(is_active=True).count()

    @extend_schema_field(serializers.IntegerField())
    def get_total_colleges(self, obj):
        return College.objects.filter(organization__university=obj, is_active=True).count()



class OrganizationSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    university_name = serializers.CharField(source='university.name', read_only=True)
    total_colleges = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = ['id', 'organization_id', 'university', 'university_name',
                 'name', 'address', 'logo', 'created_by', 'created_at',
                 'updated_at', 'is_active', 'total_colleges']
        read_only_fields = ['id', 'organization_id', 'created_by', 'created_at', 'updated_at']

    @extend_schema_field(serializers.IntegerField())
    def get_total_colleges(self, obj):
        return obj.colleges.filter(is_active=True).count()



class CollegeSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    university_name = serializers.CharField(source='organization.university.name', read_only=True)
    available_seats = serializers.SerializerMethodField()
    is_registration_open = serializers.SerializerMethodField()
    logo = serializers.ImageField(required=False, allow_null=True, allow_empty_file=True)
    password = serializers.CharField(write_only=True, required=True, min_length=6, help_text="College login password")

    class Meta:
        model = College
        fields = ['id', 'college_id', 'organization', 'organization_name',
                 'university_name', 'name', 'email', 'password', 'address',
                 'phone_number', 'max_students', 'current_students',
                 'available_seats', 'is_registration_open', 'logo',
                 'description', 'created_by', 'created_at', 'updated_at', 'is_active']
        read_only_fields = ['id', 'college_id', 'created_by', 'created_at',
                          'updated_at', 'current_students']

    @extend_schema_field(serializers.IntegerField())
    def get_available_seats(self, obj):
        return obj.available_seats

    @extend_schema_field(serializers.BooleanField())
    def get_is_registration_open(self, obj):
        return obj.is_registration_open

    def to_internal_value(self, data):
        # Handle logo field - if it's a string "null" or "Null", treat it as None
        if 'logo' in data:
            if data['logo'] in ['null', 'Null', 'NULL', '', None]:
                data = data.copy()
                data.pop('logo', None)
        return super().to_internal_value(data)

    def create(self, validated_data):
        from django.contrib.auth.hashers import make_password

        password = validated_data.pop('password')

        # Create the college record
        college = College.objects.create(**validated_data)
        college.password = make_password(password)
        college.save()

        # Automatically create a User account for this college staff
        # Check if user already exists with this email
        user, created = User.objects.get_or_create(
            email=college.email,
            defaults={
                'username': college.email,
                'is_staff': True,  # Mark as staff so they can create companies
                'is_superuser': False,
                'college': college,
                'college_name': college.name,
                'is_active': True,
            }
        )

        # If user was created, set their password
        if created:
            user.set_password(password)
            user.save()
            print(f"✅ User account created for college: {college.name} (email: {college.email})")
        else:
            # Update existing user with college info
            user.is_staff = True
            user.college = college
            user.college_name = college.name
            user.set_password(password)
            user.save()
            print(f"✅ Existing user updated with college info: {college.name}")

        return college

    def update(self, instance, validated_data):
        from django.contrib.auth.hashers import make_password

        password = validated_data.pop('password', None)

        # Update college fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        # Update college password if provided
        if password:
            instance.password = make_password(password)

        instance.save()

        # Also update the associated User account
        try:
            user = User.objects.get(email=instance.email)
            user.college = instance
            user.college_name = instance.name
            if password:
                user.set_password(password)
            user.save()
            print(f"✅ User account updated for college: {instance.name}")
        except User.DoesNotExist:
            # If user doesn't exist, create one
            user = User.objects.create(
                email=instance.email,
                username=instance.email,
                is_staff=True,
                is_superuser=False,
                college=instance,
                college_name=instance.name,
                is_active=True,
            )
            if password:
                user.set_password(password)
            else:
                # Use the college's existing password
                user.password = instance.password
            user.save()
            print(f"✅ User account created (during update) for college: {instance.name}")

        return instance


class CollegeListSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    university_name = serializers.CharField(source='organization.university.name', read_only=True)
    available_seats = serializers.SerializerMethodField()
    is_registration_open = serializers.SerializerMethodField()

    class Meta:
        model = College
        fields = ['id', 'college_id', 'name', 'organization_name',
                 'university_name', 'email','address', 'phone_number', 'max_students',
                 'current_students', 'available_seats', 'is_registration_open',
                 'logo','description', 'created_by','created_at','updated_at', 'is_active']

    @extend_schema_field(serializers.IntegerField())
    def get_available_seats(self, obj):
        return obj.available_seats

    @extend_schema_field(serializers.BooleanField())
    def get_is_registration_open(self, obj):
        return obj.is_registration_open




