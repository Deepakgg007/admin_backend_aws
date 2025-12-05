from rest_framework import serializers
from .models import (
    Certification, 
    CertificationQuestion, 
    CertificationOption, 
    AttemptAnswer, 
    CertificationAttempt
)
from courses.models import Enrollment


class CertificationOptionSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = CertificationOption
        fields = ["id", "text", "is_correct"]


class CertificationQuestionSerializer(serializers.ModelSerializer):
    options = CertificationOptionSerializer(many=True)
    id = serializers.IntegerField(required=False)

    class Meta:
        model = CertificationQuestion
        fields = ["id", "text", "order", "weight", "is_multiple_correct", "is_active", "options"]

    def _validate_options_logic(self, question, options_data):
        """DRF-side validation instead of model method"""
        if len(options_data) < 2:
            raise serializers.ValidationError(
                f"Question '{question.text}' must have at least 2 options."
            )

        correct_count = sum(1 for opt in options_data if opt.get("is_correct"))
        if correct_count == 0:
            raise serializers.ValidationError(
                f"Question '{question.text}' must have at least 1 correct option."
            )
        if not question.is_multiple_correct and correct_count > 1:
            raise serializers.ValidationError(
                f"Question '{question.text}' allows only 1 correct option."
            )

    def create(self, validated_data):
        options_data = validated_data.pop("options")
        question = CertificationQuestion.objects.create(**validated_data)
        self._validate_options_logic(question, options_data)

        for opt_data in options_data:
            CertificationOption.objects.create(question=question, **opt_data)
        return question

    def update(self, instance, validated_data):
        options_data = validated_data.pop("options", [])

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        existing_ids = [opt["id"] for opt in options_data if "id" in opt]
        instance.options.exclude(id__in=existing_ids).delete()

        for opt_data in options_data:
            if "id" in opt_data:
                opt = CertificationOption.objects.get(id=opt_data["id"], question=instance)
                opt.text = opt_data.get("text", opt.text)
                opt.is_correct = opt_data.get("is_correct", opt.is_correct)
                opt.save()
            else:
                CertificationOption.objects.create(question=instance, **opt_data)

        self._validate_options_logic(instance, options_data)
        return instance



class CertificationQuestionPublicSerializer(serializers.ModelSerializer):
    """Serializer for students - hides correct answers"""
    options = serializers.SerializerMethodField()

    class Meta:
        model = CertificationQuestion
        fields = ["id", "text", "order", "weight", "is_multiple_correct", "options"]

    def get_options(self, obj):
        options = obj.options.all()
        return [{"id": opt.id, "text": opt.text} for opt in options]


class CertificationSerializer(serializers.ModelSerializer):
    questions = CertificationQuestionSerializer(many=True)
    total_questions = serializers.SerializerMethodField()
    course_title = serializers.CharField(source='course.title', read_only=True)
    course_id = serializers.IntegerField(source='course.id', read_only=True)

    class Meta:
        model = Certification
        fields = [
            "id", "course", "course_id", "course_title", "title", "description",
            "passing_score", "duration_minutes",
            "max_attempts", "is_active", "created_at",
            "total_questions", "questions"
        ]
        read_only_fields = ["created_at"]

    def get_total_questions(self, obj):
        return obj.questions.filter(is_active=True).count()

    def validate_questions(self, value):
        if len(value) < 1:
            raise serializers.ValidationError("Certification must have at least one question.")
        return value

    def create(self, validated_data):
        questions_data = validated_data.pop("questions")
        cert = Certification.objects.create(**validated_data)

        for q_data in questions_data:
            options_data = q_data.pop("options")
            question = CertificationQuestion.objects.create(certification=cert, **q_data)
            
            # ✅ Inline validation (no model method)
            if len(options_data) < 2:
                raise serializers.ValidationError(
                    f"Question '{question.text}' must have at least 2 options."
                )
            correct_count = sum(1 for opt in options_data if opt.get("is_correct"))
            if correct_count == 0:
                raise serializers.ValidationError(
                    f"Question '{question.text}' must have at least 1 correct option."
                )
            if not question.is_multiple_correct and correct_count > 1:
                raise serializers.ValidationError(
                    f"Question '{question.text}' allows only 1 correct option."
                )

            for opt_data in options_data:
                CertificationOption.objects.create(question=question, **opt_data)

        return cert

    def update(self, instance, validated_data):
        questions_data = validated_data.pop("questions", [])

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        existing_ids = [q["id"] for q in questions_data if "id" in q]
        instance.questions.exclude(id__in=existing_ids).delete()

        for q_data in questions_data:
            options_data = q_data.pop("options", [])

            if "id" in q_data:
                question = CertificationQuestion.objects.get(id=q_data["id"], certification=instance)
                for attr, value in q_data.items():
                    if attr != "id":
                        setattr(question, attr, value)
                question.save()

                existing_opt_ids = [opt["id"] for opt in options_data if "id" in opt]
                question.options.exclude(id__in=existing_opt_ids).delete()

                for opt_data in options_data:
                    if "id" in opt_data:
                        opt = CertificationOption.objects.get(id=opt_data["id"], question=question)
                        opt.text = opt_data.get("text", opt.text)
                        opt.is_correct = opt_data.get("is_correct", opt.is_correct)
                        opt.save()
                    else:
                        CertificationOption.objects.create(question=question, **opt_data)

                # ✅ Inline validation again
                if len(options_data) < 2:
                    raise serializers.ValidationError(
                        f"Question '{question.text}' must have at least 2 options."
                    )
                correct_count = sum(1 for opt in options_data if opt.get("is_correct"))
                if correct_count == 0:
                    raise serializers.ValidationError(
                        f"Question '{question.text}' must have at least 1 correct option."
                    )
                if not question.is_multiple_correct and correct_count > 1:
                    raise serializers.ValidationError(
                        f"Question '{question.text}' allows only 1 correct option."
                    )

            else:
                question = CertificationQuestion.objects.create(certification=instance, **q_data)
                for opt_data in options_data:
                    CertificationOption.objects.create(question=question, **opt_data)
                
                # Validation for new questions
                if len(options_data) < 2:
                    raise serializers.ValidationError(
                        f"Question '{question.text}' must have at least 2 options."
                    )

        return instance



class CertificationPublicSerializer(serializers.ModelSerializer):
    """Serializer for students listing certifications"""
    total_questions = serializers.SerializerMethodField()
    user_attempts = serializers.SerializerMethodField()
    user_passed = serializers.SerializerMethodField()
    college = serializers.SerializerMethodField()

    class Meta:
        model = Certification
        fields = [
            "id", "title", "description", "passing_score",
            "duration_minutes", "max_attempts",
            "total_questions", "user_attempts", "user_passed", "college"
        ]

    def get_total_questions(self, obj):
        return obj.questions.filter(is_active=True).count()

    def get_user_attempts(self, obj):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return CertificationAttempt.objects.filter(
                user=request.user,
                certification=obj
            ).count()
        return 0

    def get_user_passed(self, obj):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return CertificationAttempt.objects.filter(
                user=request.user,
                certification=obj,
                passed=True
            ).exists()
        return False

    def get_college(self, obj):
        """Get college information from the course or user's college as fallback"""
        # Try to get college from course first
        college = obj.course.college
        
        # If course doesn't have college, try to get from the user's college (who took the certification)
        if not college:
            request = self.context.get("request")
            if request and request.user.is_authenticated:
                college = request.user.college
        
        if college:
            serializer = CollegeSerializer(college, context=self.context)
            return serializer.data
        return None


class AttemptAnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttemptAnswer
        fields = ["question", "selected_options"]

    def validate(self, attrs):
        question = attrs["question"]
        selected = attrs["selected_options"]

        if not isinstance(selected, list):
            raise serializers.ValidationError("selected_options must be a list")

        if not selected:
            raise serializers.ValidationError("At least one option must be selected")

        valid_ids = list(question.options.values_list("id", flat=True))

        for opt in selected:
            if opt not in valid_ids:
                raise serializers.ValidationError(
                    f"Invalid option {opt} for question {question.id}"
                )

        # Check if multiple answers for single-answer question
        if not question.is_multiple_correct and len(selected) > 1:
            raise serializers.ValidationError(
                "This question allows only one answer"
            )

        return attrs


class CollegeSerializer(serializers.Serializer):
    """Serializer for college information in certificates"""
    id = serializers.IntegerField()
    name = serializers.CharField()
    logo = serializers.SerializerMethodField()
    signature_display = serializers.SerializerMethodField()

    def get_logo(self, obj):
        """Get absolute URL for college logo"""
        try:
            if hasattr(obj, 'logo') and obj.logo:
                # Always try to use request first
                request = self.context.get('request')
                if request:
                    return request.build_absolute_uri(obj.logo.url)

                # Fallback: construct absolute URL manually
                logo_path = obj.logo.url
                if logo_path.startswith('http'):
                    return logo_path
                return f"https://krishik-abiuasd.in{logo_path}"
            return None
        except Exception as e:
            print(f"[CollegeSerializer.get_logo] Error for college {obj.id}: {e}")
            import traceback
            traceback.print_exc()
            return None

    def get_signature_display(self, obj):
        """Get absolute URL for college signature image"""
        try:
            # College model uses 'signature' field
            if hasattr(obj, 'signature') and obj.signature:
                # Always try to use request first
                request = self.context.get('request')
                if request:
                    return request.build_absolute_uri(obj.signature.url)

                # Fallback: construct absolute URL manually
                signature_path = obj.signature.url
                if signature_path.startswith('http'):
                    return signature_path
                return f"https://krishik-abiuasd.in{signature_path}"
            return None
        except Exception as e:
            print(f"[CollegeSerializer.get_signature_display] Error for college {obj.id}: {e}")
            import traceback
            traceback.print_exc()
            return None


class CertificationAttemptSerializer(serializers.ModelSerializer):
    answers = AttemptAnswerSerializer(many=True, read_only=True)
    certification_title = serializers.CharField(source="certification.title", read_only=True)
    college = serializers.SerializerMethodField()
    student_name = serializers.SerializerMethodField()
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = CertificationAttempt
        fields = [
            "id", "certification", "certification_title",
            "score", "passed", "attempt_number",
            "started_at", "completed_at",
            "is_expired", "certificate_issued",
            "student_name", "college",
            "answers"
        ]
        read_only_fields = [
            "score", "passed", "attempt_number",
            "started_at", "completed_at", "certificate_issued"
        ]

    def get_student_name(self, obj):
        """Get student full name from user"""
        user = obj.user
        if user.first_name and user.last_name:
            return f"{user.first_name} {user.last_name}"
        elif user.first_name:
            return user.first_name
        return user.email

    def get_college(self, obj):
        """Get college information from the course or user's college as fallback"""
        try:
            # Try to get college from course first
            college = obj.certification.course.college
            
            # If course doesn't have college, try to get from the user's college (who took the certification)
            if not college and obj.user and obj.user.college:
                college = obj.user.college
            
            if college:
                # Create serializer with request context to build absolute URLs
                serializer = CollegeSerializer(
                    college,
                    context={"request": self.context.get("request")}
                )
                data = serializer.data

                # Debug logging
                print(f"\n[CertificationAttemptSerializer.get_college] Processing attempt {obj.id}")
                print(f"[get_college] College: {college.name} (ID: {college.id})")
                print(f"[get_college] College has logo field: {hasattr(college, 'logo')}")
                print(f"[get_college] College logo value: {college.logo}")
                print(f"[get_college] College logo bool: {bool(college.logo)}")
                if college.logo:
                    print(f"[get_college] College logo URL: {college.logo.url}")
                print(f"[get_college] Serialized college data: {data}")
                print(f"[get_college] Serialized logo field: {data.get('logo')}")
                print(f"[get_college] Serialized signature field: {data.get('signature_display')}\n")

                return data
            return None
        except Exception as e:
            print(f"[CertificationAttemptSerializer.get_college] ERROR: {e}")
            import traceback
            traceback.print_exc()
            return None

    def create(self, validated_data):
        user = self.context["request"].user
        certification = validated_data["certification"]

        # Check enrollment
        if not Enrollment.objects.filter(
            student=user, 
            course=certification.course
        ).exists():
            raise serializers.ValidationError(
                "You must be enrolled in this course to attempt certification."
            )

        # Check if certification is active
        if not certification.is_active:
            raise serializers.ValidationError(
                "This certification is not currently available."
            )

        # Check previous attempts
        previous_attempts = CertificationAttempt.objects.filter(
            user=user, 
            certification=certification
        )
        
        attempts_count = previous_attempts.count()
        
        if attempts_count >= certification.max_attempts:
            raise serializers.ValidationError(
                f"Maximum attempts ({certification.max_attempts}) reached for this certification."
            )

        # Check for incomplete attempts
        incomplete = previous_attempts.filter(completed_at__isnull=True).first()
        if incomplete:
            raise serializers.ValidationError(
                "You have an incomplete attempt. Please complete or abandon it first."
            )

        # Create new attempt
        attempt = CertificationAttempt.objects.create(
            user=user,
            certification=certification,
            attempt_number=attempts_count + 1
        )

        return attempt
