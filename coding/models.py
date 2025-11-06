
from django.db import models
from django.core.validators import MinValueValidator
from django.forms import ValidationError
from django.utils.text import slugify

# Define the choices for languages in a central place for reuse
PROGRAMMING_LANGUAGE_CHOICES = [
    ('python', 'Python'),
    ('java', 'Java'),
    ('c_cpp', 'C++'),
    ('c', 'C'),
    ('javascript', 'JavaScript'),
]

ALGORITHM_CATEGORIES = [
    ('arrays', 'Arrays'),
    ('strings', 'Strings'),
    ('sorting', 'Sorting'),
    ('searching', 'Searching'),
    ('dynamic_programming', 'Dynamic Programming'),
    ('greedy', 'Greedy'),
    ('graphs', 'Graph Theory'),
    ('trees', 'Trees'),
    ('linked_lists', 'Linked Lists'),
    ('stacks_queues', 'Stacks and Queues'),
    ('recursion', 'Recursion'),
    ('bit_manipulation', 'Bit Manipulation'),
    ('maths', 'Mathematics'),
    ('implementation', 'Implementation'),
    ('data_structures', 'Data Structures'),
    ('number_theory', 'Number Theory'),
    ('hash_map', 'Hash Map'),
    ('matrix', 'Matrix'),
    ('stack', 'Stack'),
    ('queue', 'Queue'),
    ('heap', 'Heap'),
    ('binary_search', 'Binary Search'),
    ('sliding_window', 'Sliding Window'),
    ('basic', 'Basic'),
]


class Challenge(models.Model):
    DIFFICULTY_CHOICES = [
        ('EASY', 'Easy'),
        ('MEDIUM', 'Medium'),
        ('HARD', 'Hard'),
    ]
    title = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True, help_text='Challenge description (supports HTML)')
    input_format = models.TextField(blank=True)
    output_format = models.TextField(blank=True)
    constraints = models.TextField(blank=True)
    explanation = models.TextField(blank=True)
    sample_input = models.TextField(blank=True, null=True)
    sample_output = models.TextField(blank=True, null=True)
    time_complexity = models.CharField(max_length=100, blank=True, null=True)
    space_complexity = models.CharField(max_length=100, blank=True, null=True)
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES, default='MEDIUM')
    max_score = models.PositiveIntegerField(default=100)
    
    # New HackerRank-like fields
    category = models.CharField(max_length=50, choices=ALGORITHM_CATEGORIES, default='implementation')
    tags = models.CharField(max_length=500, blank=True, help_text='Comma-separated tags')
    time_limit_seconds = models.IntegerField(default=10, help_text='Time limit in seconds')
    memory_limit_mb = models.IntegerField(default=256, help_text='Memory limit in MB')
    success_rate = models.FloatField(default=0.0, help_text='Percentage of successful submissions')
    total_submissions = models.PositiveIntegerField(default=0)
    accepted_submissions = models.PositiveIntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'coding_api_challenge'
        verbose_name = "Coding Challenge"
        verbose_name_plural = "Coding Challenges"
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title
        
    def get_tags_list(self):
        """Returns tags as a list"""
        return [tag.strip() for tag in self.tags.split(',') if tag.strip()]
        
    def update_success_rate(self):
        """Update success rate based on submissions"""
        if self.total_submissions > 0:
            self.success_rate = (self.accepted_submissions / self.total_submissions) * 100
        else:
            self.success_rate = 0.0
        self.save(update_fields=['success_rate'])
        
    def get_difficulty_score(self):
        """Returns numeric score based on difficulty"""
        difficulty_scores = {'EASY': 10, 'MEDIUM': 20, 'HARD': 30}
        return difficulty_scores.get(self.difficulty, 20)

class StarterCode(models.Model):
    """
    Stores starter code for a specific challenge and programming language.
    """
    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE, related_name='starter_codes')
    language = models.CharField(max_length=50,choices=PROGRAMMING_LANGUAGE_CHOICES,help_text="Programming language for this starter code")
    code = models.TextField(blank=True,help_text="The initial code snippet provided to the user, e.g., function signature, imports.")

    class Meta:
        db_table = 'coding_api_startercode'
        verbose_name = "Starter Code"
        verbose_name_plural = "Starter Codes"
        unique_together = ('challenge', 'language')
        ordering = ['language']

    def __str__(self):
        return f"Starter Code for {self.challenge.title} ({self.get_language_display()})"




class TestCase(models.Model):
    """
    Represents a single test case for a coding challenge.
    """
    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE, related_name='test_cases')
    input_data = models.TextField()
    expected_output = models.TextField()
    is_sample = models.BooleanField(default=False)
    hidden = models.BooleanField(default=False, help_text="If checked, this test case is hidden from users and used only for grading.") 
    score_weight = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])

    class Meta:
        db_table = 'coding_api_testcase'
        verbose_name = "Test Case"
        verbose_name_plural = "Test Cases"
        ordering = ['-is_sample', '-hidden', 'pk']

    def clean(self):
        # Ensure a test case can't be both sample and hidden
        if self.is_sample and self.hidden:
            raise ValidationError("A test case cannot be both sample and hidden.")
        
        # Ensure sample test cases match the challenge's sample input/output if they exist
        if self.is_sample and self.challenge.sample_input and self.challenge.sample_output:
            if (self.input_data.strip() != self.challenge.sample_input.strip() or 
                self.expected_output.strip() != self.challenge.sample_output.strip()):
                raise ValidationError("Sample test case must match the challenge's sample input/output.")

    def __str__(self):
        return f"Test Case for '{self.challenge.title}' (Sample: {self.is_sample}, Hidden: {self.hidden})"



