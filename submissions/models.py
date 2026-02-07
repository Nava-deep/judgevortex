import uuid
from django.db import models
from django.contrib.auth.models import User

class Submission(models.Model):
    class Status(models.TextChoices):
        PENDING = 'P', 'Pending'
        PROCESSING = 'PR', 'Processing'
        COMPLETED = 'C', 'Completed'
        FAILED = 'F', 'Internal Error'
    class Result(models.TextChoices):
        ACCEPTED = 'Accepted', 'Accepted'
        RUNTIME_ERROR = 'Runtime Error', 'Runtime Error'
        COMPILATION_ERROR = 'Compilation Error', 'Compilation Error'
        TLE = 'Time Limit Exceeded', 'Time Limit Exceeded'
        SYSTEM_ERROR = 'System Error', 'System Error'
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='submissions')
    language_id = models.CharField(max_length=50, default='python')
    source_code = models.TextField()
    custom_input = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=2,choices=Status.choices,default=Status.PENDING)
    result = models.CharField(max_length=50,choices=Result.choices,blank=True,null=True) 
    execution_time = models.FloatField(null=True, blank=True)
    memory_used = models.IntegerField(null=True, blank=True)
    stdout = models.TextField(null=True, blank=True)
    stderr = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:ordering = ['-created_at']