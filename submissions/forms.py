from django import forms
from .models import Submission

LANGUAGE_CHOICES = [
    ('python', 'Python'),
    ('cpp', 'C++'),
    ('java', 'Java'),
    ('javascript', 'JavaScript'),
    ('typescript', 'TypeScript'),
    ('c', 'C'),
    ('csharp', 'C#'),
    ('go', 'Go'),
    ('rust', 'Rust'),
    ('php', 'PHP'),
    ('ruby', 'Ruby'),
    ('swift', 'Swift'),
    ('kotlin', 'Kotlin'),
    ('bash', 'Bash'),
    ('perl', 'Perl'),
    ('haskell', 'Haskell'),
    ('scala', 'Scala'),
    ('lua', 'Lua'),
]

class SubmissionForm(forms.ModelForm):
    language_id = forms.ChoiceField(choices=LANGUAGE_CHOICES)
    class Meta:
        model = Submission
        fields = ['language_id', 'source_code', 'custom_input']
        widgets = {
            'source_code': forms.Textarea(attrs={
                'class': 'form-control code-editor', 
                'rows': 12,
                'placeholder': '// Write your code here...'
            }),
            'custom_input': forms.Textarea(attrs={
                'class': 'form-control code-editor', 
                'rows': 3,
                'placeholder': 'Input data (optional)...'
            }),
        }