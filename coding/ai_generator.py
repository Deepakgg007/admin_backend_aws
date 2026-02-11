"""
AI-powered Coding Challenge Generator with Duplicate Detection
Integrates with existing AIProviderSettings for AI providers
"""
import json
import re
from typing import Dict, List, Optional, Tuple
from difflib import SequenceMatcher
from django.db import transaction
from django.utils.text import slugify
from django.utils import timezone
from django.core.exceptions import ValidationError
import requests

from .models import (
    Challenge, TestCase, StarterCode,
    PROGRAMMING_LANGUAGE_CHOICES, ALGORITHM_CATEGORIES
)
from course_cert.models import AIProviderSettings, AIGenerationLog


class DuplicateDetector:
    """Detects duplicate or similar coding challenges"""

    def __init__(self, similarity_threshold: float = 0.75):
        self.similarity_threshold = similarity_threshold

    def text_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two text strings"""
        if not text1 or not text2:
            return 0.0
        return SequenceMatcher(None, text1.lower().strip(), text2.lower().strip()).ratio()

    def normalize_text(self, text: str) -> str:
        """Normalize text for comparison"""
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        return text.lower().strip()

    def check_duplicate_title(self, title: str, exclude_id: Optional[int] = None) -> Optional[Challenge]:
        """Check if a challenge with similar title already exists"""
        queryset = Challenge.objects.all()
        if exclude_id:
            queryset = queryset.exclude(id=exclude_id)

        # Exact match check
        exact_match = queryset.filter(title__iexact=title).first()
        if exact_match:
            return exact_match

        # Similarity check
        for challenge in queryset:
            similarity = self.text_similarity(title, challenge.title)
            if similarity >= self.similarity_threshold:
                return challenge

        return None

    def check_duplicate_description(self, description: str, exclude_id: Optional[int] = None) -> List[Dict]:
        """Check for challenges with similar descriptions"""
        similar_challenges = []
        queryset = Challenge.objects.all()
        if exclude_id:
            queryset = queryset.exclude(id=exclude_id)

        normalized_desc = self.normalize_text(description)

        for challenge in queryset:
            if not challenge.description:
                continue
            normalized_challenge = self.normalize_text(challenge.description)
            similarity = SequenceMatcher(None, normalized_desc, normalized_challenge).ratio()
            if similarity >= self.similarity_threshold:
                similar_challenges.append({
                    'challenge': challenge,
                    'similarity': round(similarity * 100, 2)
                })

        return sorted(similar_challenges, key=lambda x: x['similarity'], reverse=True)

    def check_duplicate_test_cases(self, test_cases: List[Dict], exclude_id: Optional[int] = None) -> List[Dict]:
        """Check for challenges with similar test cases"""
        similar_challenges = []
        queryset = Challenge.objects.all()
        if exclude_id:
            queryset = queryset.exclude(id=exclude_id)

        for challenge in queryset:
            existing_test_cases = challenge.test_cases.all()
            if not existing_test_cases.exists() or not test_cases:
                continue

            # Compare test case patterns
            match_count = 0
            total_checks = min(len(test_cases), existing_test_cases.count())

            for tc_input in test_cases[:total_checks]:
                for existing_tc in existing_test_cases:
                    input_sim = self.text_similarity(
                        str(tc_input.get('input_data', '')),
                        str(existing_tc.input_data)
                    )
                    output_sim = self.text_similarity(
                        str(tc_input.get('expected_output', '')),
                        str(existing_tc.expected_output)
                    )
                    if input_sim > 0.8 and output_sim > 0.8:
                        match_count += 1
                        break

            if total_checks > 0 and match_count >= total_checks * 0.5:  # 50% match threshold
                similar_challenges.append({
                    'challenge': challenge,
                    'match_percentage': round((match_count / total_checks) * 100, 2)
                })

        return sorted(similar_challenges, key=lambda x: x['match_percentage'], reverse=True)

    def comprehensive_duplicate_check(self, title: str, description: str,
                                     test_cases: List[Dict], exclude_id: Optional[int] = None) -> Dict:
        """
        Perform comprehensive duplicate check and return detailed report
        """
        report = {
            'is_duplicate': False,
            'duplicates': [],
            'warnings': []
        }

        # Check title
        title_duplicate = self.check_duplicate_title(title, exclude_id)
        if title_duplicate:
            report['is_duplicate'] = True
            report['duplicates'].append({
                'type': 'title',
                'challenge': {
                    'id': title_duplicate.id,
                    'title': title_duplicate.title,
                    'slug': title_duplicate.slug,
                    'category': title_duplicate.category,
                    'difficulty': title_duplicate.difficulty
                },
                'reason': 'Similar or identical title found'
            })

        # Check description
        description_duplicates = self.check_duplicate_description(description, exclude_id)
        for dup in description_duplicates[:3]:  # Top 3 matches
            if dup['challenge'].id not in [d['challenge']['id'] for d in report['duplicates']]:
                report['duplicates'].append({
                    'type': 'description',
                    'challenge': {
                        'id': dup['challenge'].id,
                        'title': dup['challenge'].title,
                        'slug': dup['challenge'].slug,
                        'category': dup['challenge'].category,
                        'difficulty': dup['challenge'].difficulty
                    },
                    'similarity': dup['similarity'],
                    'reason': f'Similar description ({dup["similarity"]}% match)'
                })

        # Check test cases
        test_case_duplicates = self.check_duplicate_test_cases(test_cases, exclude_id)
        for dup in test_case_duplicates[:3]:  # Top 3 matches
            if dup['challenge'].id not in [d['challenge']['id'] for d in report['duplicates']]:
                report['duplicates'].append({
                    'type': 'test_cases',
                    'challenge': {
                        'id': dup['challenge'].id,
                        'title': dup['challenge'].title,
                        'slug': dup['challenge'].slug,
                        'category': dup['challenge'].category,
                        'difficulty': dup['challenge'].difficulty
                    },
                    'match_percentage': dup['match_percentage'],
                    'reason': f'Similar test cases ({dup["match_percentage"]}% match)'
                })

        # Add warning if duplicates found
        if report['duplicates']:
            report['warnings'].append('This question appears to be similar to existing challenges.')

        return report


class AICodingChallengeGenerator:
    """
    AI-powered coding challenge generator.
    Integrates with AIProviderSettings (OpenRouter, Gemini, Z.AI)
    """

    def __init__(self):
        self.duplicate_detector = DuplicateDetector()

    def get_ai_provider(self):
        """Get the active AI provider settings"""
        # First try to get the default active provider with API key
        provider_settings = AIProviderSettings.objects.filter(
            is_default=True,
            is_active=True
        ).exclude(api_key__isnull=True).exclude(api_key='').first()

        if not provider_settings:
            # If no default, try to get any active provider with API key
            provider_settings = AIProviderSettings.objects.filter(
                is_active=True
            ).exclude(api_key__isnull=True).exclude(api_key='').first()

        return provider_settings

    def build_generation_prompt(self, topic: str, category: str, difficulty: str,
                                num_questions: int = 1, additional_context: str = '') -> str:
        """Build the prompt for AI coding challenge generation"""

        difficulty_desc = {
            'EASY': 'beginner-friendly problems with simple logic, O(n) or better complexity',
            'MEDIUM': 'intermediate problems requiring common algorithms/data structures, O(n log n) complexity',
            'HARD': 'challenging problems with multiple techniques or advanced algorithms (DP, advanced graphs, etc.)'
        }

        category_hints = {
            'arrays': 'array manipulation, index-based operations, two pointers',
            'strings': 'string processing, pattern matching, character manipulation',
            'sorting': 'sorting algorithms, comparison-based sorting',
            'searching': 'binary search, linear search optimizations',
            'dynamic_programming': 'optimal substructure, overlapping subproblems, memoization',
            'greedy': 'greedy choice property, optimal substructure',
            'graphs': 'graph traversal (BFS/DFS), shortest paths, graph properties',
            'trees': 'binary trees, BST, tree traversals, tree properties',
            'linked_lists': 'linked list manipulation, pointer operations',
            'stacks_queues': 'stack and queue operations, monotonic stacks',
            'recursion': 'recursive approaches, backtracking, divide and conquer',
            'bit_manipulation': 'bit operations, XOR, bit masking',
            'maths': 'number theory, mathematical properties, GCD, LCM',
            'implementation': 'straightforward implementation, simulation',
            'hash_map': 'hash table usage, frequency counting',
            'matrix': '2D array operations, matrix properties',
            'sliding_window': 'sliding window technique, two pointers',
            'binary_search': 'binary search on answer space',
        }

        category_hint = category_hints.get(category, 'algorithmic problem solving')

        prompt = f"""Generate exactly {num_questions} complete coding challenge(s) about "{topic}".

Category: {category}
Difficulty: {difficulty} - {difficulty_desc.get(difficulty, 'intermediate')}
Focus area: {category_hint}

{f'Additional context: {additional_context}' if additional_context else ''}

For EACH challenge, provide:

1. **title**: Short descriptive title in PascalCase (e.g., "TwoSum", "LongestSubstring")
2. **description**: Detailed problem description with examples (can include HTML tags for formatting)
3. **input_format**: Clear specification of input format
4. **output_format**: Clear specification of output format
5. **constraints**: Constraints on input size, time complexity expectations
6. **explanation**: Brief explanation of the optimal approach
7. **sample_input**: Sample input exactly as provided to the program
8. **sample_output**: Expected output for the sample input
9. **time_complexity**: Expected time complexity (e.g., "O(n)", "O(n log n)")
10. **space_complexity**: Expected space complexity (e.g., "O(1)", "O(n)")
11. **tags**: Comma-separated relevant tags
12. **test_cases**: Array of 3-5 test cases with:
   - input_data: Test input
   - expected_output: Expected output
   - is_sample: true for first 1-2 cases, false for others
   - hidden: true for grading cases (at least 2)
   - score_weight: Points for this test case
13. **starter_codes**: Code templates for each language:
   - python: Python function template
   - java: Java class template
   - cpp: C++ class template
   - c: C function template
   - javascript: JavaScript function template

IMPORTANT:
- Sample test cases must match the sample_input/output
- Generate 3-5 test cases per challenge
- At least 2 test cases should be hidden (for grading)
- Starter codes should include function signatures only
- Return ONLY valid JSON, no markdown, no extra text

Return format:
{{
  "challenges": [
    {{
      "title": "ChallengeTitle",
      "description": "Problem description...",
      "input_format": "Input specification...",
      "output_format": "Output specification...",
      "constraints": "Constraints...",
      "explanation": "Approach explanation...",
      "sample_input": "Sample input",
      "sample_output": "Sample output",
      "time_complexity": "O(n)",
      "space_complexity": "O(n)",
      "tags": "tag1,tag2,tag3",
      "test_cases": [
        {{"input_data": "...", "expected_output": "...", "is_sample": true, "hidden": false, "score_weight": 10}},
        {{"input_data": "...", "expected_output": "...", "is_sample": false, "hidden": true, "score_weight": 15}}
      ],
      "starter_codes": {{
        "python": "def solve():\\n    # Your code here\\n    pass",
        "java": "public class Solution {{\\n    public static void solve() {{\\n        // Your code here\\n    }}\\n}}",
        "cpp": "class Solution {{\\npublic:\\n    void solve() {{\\n        // Your code here\\n    }}\\n}};",
        "c": "void solve() {{\\n    // Your code here\\n}}",
        "javascript": "function solve() {{\\n    // Your code here\\n}}"
      }}
    }}
  ]
}}"""
        return prompt

    def call_ai_provider(self, prompt: str, provider_settings: AIProviderSettings) -> str:
        """Call the AI provider API"""

        if provider_settings.provider == 'OPENROUTER':
            endpoint = provider_settings.api_endpoint or 'https://openrouter.ai/api/v1/chat/completions'
            response = requests.post(
                endpoint,
                headers={
                    'Authorization': f'Bearer {provider_settings.api_key}',
                    'Content-Type': 'application/json',
                    'HTTP-Referer': 'https://z1-platform.com',
                    'X-Title': 'Z1 Educational Platform'
                },
                json={
                    'model': provider_settings.default_model or 'openai/gpt-4o',
                    'messages': [
                        {
                            'role': 'system',
                            'content': 'You are an expert coding challenge creator. Generate complete, well-structured coding problems in valid JSON format only. Do not include any text outside the JSON.'
                        },
                        {
                            'role': 'user',
                            'content': prompt
                        }
                    ],
                    'temperature': provider_settings.temperature,
                    'max_tokens': provider_settings.max_tokens
                },
                timeout=300
            )
            response.raise_for_status()
            result = response.json()
            return result['choices'][0]['message']['content']

        elif provider_settings.provider == 'GEMINI':
            model = provider_settings.default_model or 'gemini-2.5-pro'
            endpoint = provider_settings.api_endpoint or f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
            response = requests.post(
                f'{endpoint}?key={provider_settings.api_key}',
                headers={'Content-Type': 'application/json'},
                json={
                    'contents': [{
                        'parts': [{
                            'text': f'You are an expert coding challenge creator. Generate complete, well-structured coding problems in valid JSON format only. Do not include any text outside the JSON.\n\n{prompt}'
                        }]
                    }],
                    'generationConfig': {
                        'temperature': provider_settings.temperature,
                        'maxOutputTokens': provider_settings.max_tokens
                    }
                },
                timeout=300
            )
            response.raise_for_status()
            result = response.json()
            return result['candidates'][0]['content']['parts'][0]['text']

        elif provider_settings.provider == 'ZAI':
            endpoint = provider_settings.api_endpoint or 'https://open.bigmodel.cn/api/paas/v4/chat/completions'
            if not endpoint.endswith('/chat/completions'):
                endpoint = endpoint.rstrip('/') + '/chat/completions'

            response = requests.post(
                endpoint,
                headers={
                    'Authorization': f'Bearer {provider_settings.api_key}',
                    'Content-Type': 'application/json',
                },
                json={
                    'model': provider_settings.default_model or 'glm-4.7',
                    'messages': [
                        {
                            'role': 'system',
                            'content': 'You are an expert coding challenge creator. Generate complete, well-structured coding problems in valid JSON format only. Do not include any text outside the JSON.'
                        },
                        {
                            'role': 'user',
                            'content': prompt
                        }
                    ],
                    'temperature': provider_settings.temperature,
                    'max_tokens': provider_settings.max_tokens
                },
                timeout=300
            )
            response.raise_for_status()
            result = response.json()
            return result['choices'][0]['message']['content']

        else:
            raise ValueError(f'Unsupported AI provider: {provider_settings.provider}')

    def parse_ai_response(self, content: str) -> List[Dict]:
        """Parse the AI response and extract challenges"""
        content = content.strip()

        # Save original for error logging
        original_content = content[:500]  # First 500 chars

        # Remove markdown code blocks if present - handle various formats
        # 1. ```json ... ```
        if '```json' in content:
            parts = content.split('```json')
            if len(parts) > 1:
                content = parts[1].split('```')[0] if '```' in parts[1] else parts[1]
        # 2. ``` ... ```
        elif content.startswith('```'):
            content = content.split('```')[1] if '```' in content[3:] else content[3:]
            if '```' in content:
                content = content.split('```')[0]

        content = content.strip()

        # Try to find JSON array first [...]
        array_match = re.search(r'\[\s*\{[\s\S]*\}\s*\]', content)
        if array_match:
            try:
                challenges = json.loads(array_match.group())
                if isinstance(challenges, list) and len(challenges) > 0:
                    validated = self._validate_challenges(challenges)
                    if validated:
                        return validated
            except json.JSONDecodeError:
                pass

        # Try to find JSON object with "challenges" key
        challenges_match = re.search(r'"challenges"\s*:\s*\[[\s\S]*\]', content)
        if challenges_match:
            try:
                challenges_json = '{"challenges":' + challenges_match.group() + '}'
                data = json.loads(challenges_json)
                if 'challenges' in data and isinstance(data['challenges'], list):
                    validated = self._validate_challenges(data['challenges'])
                    if validated:
                        return validated
            except json.JSONDecodeError:
                pass

        # Try parsing the whole content as JSON
        try:
            data = json.loads(content)
            challenges = []

            if isinstance(data, list):
                challenges = data
            elif 'challenges' in data and isinstance(data['challenges'], list):
                challenges = data['challenges']
            elif 'data' in data and isinstance(data['data'], list):
                challenges = data['data']
            elif isinstance(data, dict) and 'title' in data:
                challenges = [data]

            validated = self._validate_challenges(challenges)
            if validated:
                return validated
        except json.JSONDecodeError:
            pass

        # Try to find individual challenge objects
        object_match = re.search(r'\{[^{}]*"title"[^{}]*\}', content)
        if object_match:
            try:
                challenge = json.loads(object_match.group())
                if 'title' in challenge and 'description' in challenge:
                    return [challenge]
            except json.JSONDecodeError:
                pass

        # If nothing worked, raise error with context
        raise ValueError(f'Could not parse AI response as JSON. Response preview: {original_content}...')

    def _validate_challenges(self, challenges: List) -> List[Dict]:
        """Validate and return challenges that have required fields"""
        validated_challenges = []
        for challenge in challenges:
            if not isinstance(challenge, dict):
                continue
            if 'title' in challenge and 'description' in challenge:
                validated_challenges.append(challenge)
        return validated_challenges

    def validate_and_clean_challenge_data(self, data: Dict, category: str, difficulty: str) -> Dict:
        """Validate and clean the challenge data"""
        required_fields = ['title', 'description']
        missing_fields = [f for f in required_fields if not data.get(f)]

        if missing_fields:
            raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

        # Set defaults for optional fields
        data.setdefault('input_format', '')
        data.setdefault('output_format', '')
        data.setdefault('constraints', '')
        data.setdefault('explanation', '')
        data.setdefault('sample_input', '')
        data.setdefault('sample_output', '')
        data.setdefault('time_complexity', '')
        data.setdefault('space_complexity', '')
        data.setdefault('difficulty', difficulty)
        data.setdefault('category', category)
        data.setdefault('tags', '')
        data.setdefault('time_limit_seconds', 10)
        data.setdefault('memory_limit_mb', 256)
        data.setdefault('max_score', 100)
        data.setdefault('test_cases', [])
        data.setdefault('starter_codes', {})

        # Generate slug from title
        if 'title' in data and not data.get('slug'):
            data['slug'] = slugify(data['title'])

        return data

    def check_for_duplicates(self, challenge_data: Dict, exclude_id: Optional[int] = None) -> Dict:
        """Check if the generated challenge is a duplicate of existing challenges"""
        title = challenge_data.get('title', '')
        description = challenge_data.get('description', '')
        test_cases = challenge_data.get('test_cases', [])

        return self.duplicate_detector.comprehensive_duplicate_check(
            title, description, test_cases, exclude_id
        )

    @transaction.atomic
    def save_challenge(self, challenge_data: Dict, created_by, force_save: bool = False) -> Tuple[bool, Dict]:
        """Save the generated challenge to the database"""
        # Check for duplicates first
        duplicate_report = self.check_for_duplicates(challenge_data)

        if duplicate_report['is_duplicate'] and not force_save:
            return False, {
                'status': 'duplicate',
                'message': 'Similar challenge already exists',
                'duplicates': duplicate_report['duplicates']
            }

        # Extract basic fields
        title = challenge_data['title']
        slug = challenge_data.get('slug', slugify(title))

        # Ensure slug is unique
        base_slug = slug
        counter = 1
        while Challenge.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1

        # Create the challenge
        challenge = Challenge.objects.create(
            title=title,
            slug=slug,
            description=challenge_data.get('description', ''),
            input_format=challenge_data.get('input_format', ''),
            output_format=challenge_data.get('output_format', ''),
            constraints=challenge_data.get('constraints', ''),
            explanation=challenge_data.get('explanation', ''),
            sample_input=challenge_data.get('sample_input', ''),
            sample_output=challenge_data.get('sample_output', ''),
            time_complexity=challenge_data.get('time_complexity', ''),
            space_complexity=challenge_data.get('space_complexity', ''),
            difficulty=challenge_data.get('difficulty', 'MEDIUM'),
            category=challenge_data.get('category', 'implementation'),
            tags=challenge_data.get('tags', ''),
            time_limit_seconds=challenge_data.get('time_limit_seconds', 10),
            memory_limit_mb=challenge_data.get('memory_limit_mb', 256),
            max_score=challenge_data.get('max_score', 100)
        )

        # Create test cases
        created_test_cases = []
        for tc_data in challenge_data.get('test_cases', []):
            test_case = TestCase.objects.create(
                challenge=challenge,
                input_data=tc_data.get('input_data', ''),
                expected_output=tc_data.get('expected_output', ''),
                is_sample=tc_data.get('is_sample', False),
                hidden=tc_data.get('hidden', False),
                score_weight=tc_data.get('score_weight', 1)
            )
            created_test_cases.append({
                'id': test_case.id,
                'input_data': test_case.input_data[:50] + '...' if len(test_case.input_data) > 50 else test_case.input_data,
                'is_sample': test_case.is_sample,
                'hidden': test_case.hidden
            })

        # Create starter codes
        created_starter_codes = []
        starter_codes = challenge_data.get('starter_codes', {})
        for lang, code in starter_codes.items():
            # Normalize language name
            if lang in ['python', 'java', 'c_cpp', 'c', 'javascript']:
                lang_key = lang
            elif lang == 'cpp':
                lang_key = 'c_cpp'
            else:
                continue

            starter_code = StarterCode.objects.create(
                challenge=challenge,
                language=lang_key,
                code=code
            )
            created_starter_codes.append({
                'language': lang,
                'code_preview': starter_code.code[:100] + '...' if len(starter_code.code) > 100 else starter_code.code
            })

        return True, {
            'status': 'success',
            'challenge': {
                'id': challenge.id,
                'title': challenge.title,
                'slug': challenge.slug,
                'difficulty': challenge.difficulty,
                'category': challenge.category
            },
            'test_cases': created_test_cases,
            'starter_codes': created_starter_codes
        }

    def generate_challenges(self, topic: str, category: str = 'implementation',
                           difficulty: str = 'MEDIUM', num_challenges: int = 1,
                           additional_context: str = '', created_by=None,
                           force_save: bool = False, check_duplicates: bool = True) -> Dict:
        """
        Complete workflow: generate, check duplicates, and save.

        Args:
            topic: Topic for the coding challenge
            category: Algorithm category
            difficulty: EASY, MEDIUM, or HARD
            num_challenges: Number of challenges to generate (max 5)
            additional_context: Additional context for generation
            created_by: User creating the challenge
            force_save: Save even if duplicates are found
            check_duplicates: Whether to check for duplicates

        Returns:
            Dictionary with generation results
        """
        # Validate number of challenges
        if num_challenges > 5:
            return {
                'status': 'error',
                'error': 'Maximum 5 challenges per generation to prevent timeouts.',
                'max_allowed': 5,
                'requested': num_challenges
            }

        # Get AI provider
        provider_settings = self.get_ai_provider()
        if not provider_settings or not provider_settings.api_key:
            return {
                'status': 'error',
                'error': 'No AI provider configured. Please configure an AI provider in AI Settings.'
            }

        # Build prompt
        prompt = self.build_generation_prompt(topic, category, difficulty, num_challenges, additional_context)

        # Create generation log
        log = AIGenerationLog.objects.create(
            prompt=prompt,
            topic=topic,
            difficulty=difficulty,
            num_questions=num_challenges,
            model_used=provider_settings.default_model or 'unknown',
            provider=provider_settings.provider,
            status='PENDING',
            created_by=created_by
        )

        try:
            # Call AI
            ai_content = self.call_ai_provider(prompt, provider_settings)
            log.response_raw = ai_content[:5000] if ai_content else ''  # Store first 5000 chars

            # Parse response
            try:
                challenges_data = self.parse_ai_response(ai_content)
            except ValueError as parse_error:
                log.status = 'FAILED'
                log.error_message = f'Parse error: {str(parse_error)}\n\nAI Response (first 1000 chars): {ai_content[:1000]}'
                log.completed_at = timezone.now()
                log.save()

                return {
                    'status': 'error',
                    'error': str(parse_error),
                    'ai_response_preview': ai_content[:500] if ai_content else 'No response'
                }

            if not challenges_data:
                log.status = 'FAILED'
                log.error_message = f'No valid challenges found in AI response.\n\nResponse (first 1000 chars): {ai_content[:1000]}'
                log.completed_at = timezone.now()
                log.save()

                raise ValueError('No valid challenges found in AI response')

            # Process each challenge
            results = []
            created_challenges = []
            skipped_challenges = []
            duplicate_challenges = []

            for idx, challenge_data in enumerate(challenges_data):
                # Validate and clean
                try:
                    challenge_data = self.validate_and_clean_challenge_data(
                        challenge_data, category, difficulty
                    )
                except ValueError as e:
                    skipped_challenges.append({
                        'index': idx,
                        'reason': str(e)
                    })
                    continue

                # Check for duplicates if enabled
                if check_duplicates:
                    duplicate_report = self.check_for_duplicates(challenge_data)
                    if duplicate_report['is_duplicate'] and not force_save:
                        duplicate_challenges.append({
                            'index': idx,
                            'title': challenge_data['title'],
                            'duplicates': duplicate_report['duplicates']
                        })
                        continue

                # Save challenge
                success, result = self.save_challenge(challenge_data, created_by, force_save)

                if success:
                    created_challenges.append(result['challenge'])
                    results.append({
                        'status': 'created',
                        'title': challenge_data['title'],
                        'challenge_id': result['challenge']['id'],
                        'slug': result['challenge']['slug']
                    })
                else:
                    if result.get('status') == 'duplicate':
                        duplicate_challenges.append({
                            'index': idx,
                            'title': challenge_data['title'],
                            'duplicates': result['duplicates']
                        })
                    else:
                        skipped_challenges.append({
                            'index': idx,
                            'reason': result.get('message', 'Unknown error')
                        })

            # Update log
            log.status = 'SUCCESS' if created_challenges else 'PARTIAL'
            log.questions_created = len(created_challenges)
            log.completed_at = timezone.now()
            log.save()

            return {
                'status': 'success',
                'total_requested': num_challenges,
                'created': len(created_challenges),
                'skipped': len(skipped_challenges),
                'duplicates_found': len(duplicate_challenges),
                'challenges': results,
                'created_challenges': created_challenges,
                'skipped_challenges': skipped_challenges,
                'duplicate_challenges': duplicate_challenges,
                'log_id': log.id
            }

        except requests.exceptions.RequestException as e:
            log.status = 'FAILED'
            log.error_message = f'API request failed: {str(e)}'
            log.completed_at = timezone.now()
            log.save()

            return {
                'status': 'error',
                'error': f'Failed to connect to AI service: {str(e)}'
            }
        except (json.JSONDecodeError, ValueError) as e:
            log.status = 'FAILED'
            log.error_message = f'Failed to parse AI response: {str(e)}'
            log.completed_at = timezone.now()
            log.save()

            return {
                'status': 'error',
                'error': f'Failed to parse AI response: {str(e)}'
            }
        except Exception as e:
            log.status = 'FAILED'
            log.error_message = f'Unexpected error: {str(e)}'
            log.completed_at = timezone.now()
            log.save()

            return {
                'status': 'error',
                'error': f'Unexpected error: {str(e)}'
            }
