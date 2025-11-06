from django.apps import AppConfig


class StudentConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "student"
    
    def ready(self):
        """Import signals when app is ready"""
        import student.signals
