from django.core.management.base import BaseCommand
from django.db import transaction
from courses.models import Course
from course_cert.models import Certification, CertificationQuestion, CertificationOption
from api.models import College


class Command(BaseCommand):
    help = "Seeds multiple sample certifications with questions and options (global or college-specific)."

    @transaction.atomic
    def handle(self, *args, **kwargs):
        course = Course.objects.first()
        if not course:
            self.stdout.write(self.style.ERROR("❌ No courses found — create at least one course first."))
            return

        college = College.objects.filter(id=1).first()
        if not college:
            self.stdout.write(self.style.WARNING("⚠️ No college with id=1 found — seeding as global certifications."))

        self.stdout.write(self.style.WARNING(f"Seeding certifications for course: {course.title}"))

        certifications = [
            {
                "title": "Python Fundamentals Certification",
                "description": "Validate core Python knowledge",
                "passing_score": 60,
                "duration_minutes": 45,
                "max_attempts": 2,
                "college_specific": False,
                "questions": [
                    {
                        "text": "Which data type is immutable?",
                        "is_multiple_correct": False,
                        "weight": 2,
                        "options": [
                            ("List", False),
                            ("Tuple", True),
                            ("Dictionary", False),
                        ],
                    },
                    {
                        "text": "Select valid list methods",
                        "is_multiple_correct": True,
                        "weight": 3,
                        "options": [
                            ("append()", True),
                            ("pop()", True),
                            ("size()", False),
                        ],
                    },
                ],
            },
            {
                "title": "Advanced Python Certification",
                "description": "Covers decorators, generators, and OOP.",
                "passing_score": 70,
                "duration_minutes": 60,
                "max_attempts": 3,
                "college_specific": False,
                "questions": [
                    {
                        "text": "What is a decorator in Python?",
                        "is_multiple_correct": False,
                        "weight": 3,
                        "options": [
                            ("A function that modifies another function", True),
                            ("A class method", False),
                            ("A special variable", False),
                        ],
                    },
                    {
                        "text": "Which of these are valid ways to create a generator?",
                        "is_multiple_correct": True,
                        "weight": 4,
                        "options": [
                            ("Using 'yield' in a function", True),
                            ("Using list comprehension", False),
                            ("Using (x for x in range(10)) syntax", True),
                        ],
                    },
                ],
            },
            {
                "title": "Django Basics Certification",
                "description": "Tests knowledge of Django MVT, ORM, and views.",
                "passing_score": 65,
                "duration_minutes": 50,
                "max_attempts": 2,
                "college_specific": True,  # ✅ this one will be assigned to college id=1
                "questions": [
                    {
                        "text": "Which of these is part of Django’s MVT architecture?",
                        "is_multiple_correct": True,
                        "weight": 3,
                        "options": [
                            ("Model", True),
                            ("Template", True),
                            ("Variable", False),
                        ],
                    },
                    {
                        "text": "What command is used to create database migrations?",
                        "is_multiple_correct": False,
                        "weight": 2,
                        "options": [
                            ("makemigrations", True),
                            ("migrate", False),
                            ("createsuperuser", False),
                        ],
                    },
                ],
            },
        ]

        for cert_data in certifications:
            cert, created = Certification.objects.get_or_create(
                course=course,
                title=cert_data["title"],
                defaults={
                    "description": cert_data["description"],
                    "passing_score": cert_data["passing_score"],
                    "duration_minutes": cert_data["duration_minutes"],
                    "max_attempts": cert_data["max_attempts"],
                    "college": college if cert_data["college_specific"] else None,
                },
            )

            if not created:
                self.stdout.write(self.style.WARNING(f"⚠️  {cert.title} already exists, skipping."))
                continue

            for order, q_data in enumerate(cert_data["questions"], start=1):
                question = CertificationQuestion.objects.create(
                    certification=cert,
                    text=q_data["text"],
                    is_multiple_correct=q_data["is_multiple_correct"],
                    weight=q_data["weight"],
                    order=order,
                )

                CertificationOption.objects.bulk_create([
                    CertificationOption(
                        question=question,
                        text=opt_text,
                        is_correct=is_correct,
                    )
                    for opt_text, is_correct in q_data["options"]
                ])

            cert.save(update_fields=["college"])  # ✅ only field that exists
            self.stdout.write(self.style.SUCCESS(f"✅ {cert.title} created successfully."))

        self.stdout.write(self.style.SUCCESS("🎯 All certifications seeded successfully!"))
