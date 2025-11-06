"""
Management command to fix concept slugs
Run: python manage.py fix_concept_slugs
"""

from django.core.management.base import BaseCommand
from django.utils.text import slugify
from company.models import Concept, Company


class Command(BaseCommand):
    help = 'Generate slugs for concepts that don\'t have them'

    def handle(self, *args, **kwargs):
        self.stdout.write("=" * 70)
        self.stdout.write("CONCEPT SLUG FIX")
        self.stdout.write("=" * 70)

        # Check companies
        companies = Company.objects.filter(is_active=True)
        self.stdout.write(f"\nActive Companies: {companies.count()}")

        # Check all concepts
        all_concepts = Concept.objects.all()
        self.stdout.write(f"Total Concepts: {all_concepts.count()}\n")

        # List all concepts and their slugs
        for company in companies:
            concepts = company.concepts.all()
            if concepts.exists():
                self.stdout.write(f"\n🏢 {company.name}:")
                for concept in concepts:
                    slug_info = f"'{concept.slug}'" if concept.slug else "❌ NO SLUG"
                    self.stdout.write(f"   ID: {concept.id:3} | Slug: {slug_info:35} | Name: {concept.name}")

        # Find and fix concepts without slugs
        concepts_needing_fix = []
        for concept in all_concepts:
            if not concept.slug or concept.slug.strip() == '':
                concepts_needing_fix.append(concept)

        if concepts_needing_fix:
            self.stdout.write(self.style.WARNING(f"\n⚠️  Found {len(concepts_needing_fix)} concepts without slugs"))
            self.stdout.write("\n🔧 Generating slugs...")

            for concept in concepts_needing_fix:
                # Generate slug
                base_slug = slugify(f"{concept.company.name}-{concept.name}")
                slug = base_slug
                
                # Ensure uniqueness
                counter = 1
                while Concept.objects.filter(slug=slug).exists():
                    slug = f"{base_slug}-{counter}"
                    counter += 1
                
                concept.slug = slug
                concept.save()
                
                self.stdout.write(self.style.SUCCESS(f"  ✓ {concept.company.name} - {concept.name} → {slug}"))

            self.stdout.write(self.style.SUCCESS(f"\n✅ Fixed {len(concepts_needing_fix)} concepts!"))
        else:
            self.stdout.write(self.style.SUCCESS("\n✅ All concepts already have slugs!"))

        # Final verification
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write("FINAL STATUS")
        self.stdout.write("=" * 70)
        
        for company in companies:
            concepts = company.concepts.all()
            if concepts.exists():
                self.stdout.write(f"\n{company.name}:")
                for concept in concepts:
                    self.stdout.write(f"  ✓ {concept.slug:40} | {concept.name}")

        self.stdout.write(self.style.SUCCESS("\n✅ All done! Concepts are ready to use."))
