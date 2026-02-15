from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.views.decorators.http import require_POST
import os

# App Imports
from .models import Submission
from .forms import SubmissionForm
# Ensure this import path matches your project structure
from judge_vortex.kafka_producer import send_submission_event 

@login_required
@require_POST
def delete(request, pk):
    # 1. Get the submission
    submission = get_object_or_404(Submission, pk=pk)

    # 2. Try to delete the actual file (cleanup)
    try:
        if submission.code and os.path.isfile(submission.code.path):
            os.remove(submission.code.path)
    except Exception as e:
        print(f"Error deleting file: {e}")

    # 3. Delete DB record
    submission.delete()
    return redirect('list')

def landing(request):
    if request.user.is_authenticated:
        return redirect('list')
    return render(request, 'submissions/landing.html')

def register(request):
    if request.user.is_authenticated:
        return redirect('list')
    
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('list')
    else:
        form = UserCreationForm()
    return render(request, 'submissions/auth/register.html', {'form': form})

@login_required
def slist(request):
    # Using 'select_related' improves performance by fetching ForeignKeys in one query
    submissions = Submission.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'submissions/list.html', {'submissions': submissions})

@login_required
def create(request):
    submission_id = None
    form = SubmissionForm(request.POST or None)

    if request.method == 'POST':
        if form.is_valid():
            # 1. Save to Database
            sub = form.save(commit=False)
            sub.user = request.user
            sub.status = 'Pending' # Ensure default status
            sub.save()

            # 2. Trigger Kafka Producer
            # We convert language to string just in case it's a model object
            send_submission_event(
                submission_id=sub.id, 
                code=sub.source_code, 
                language=str(sub.language) 
            )

            # 3. Pass ID to context (This triggers the WebSocket in HTML)
            submission_id = sub.id
            
            # NOTE: We do NOT redirect here. We render the same page so the 
            # user can see the live console output.

    return render(request, 'submissions/create.html', {
        'form': form,
        'submission_id': submission_id
    })

@login_required
def detail(request, pk):
    sub = get_object_or_404(Submission, pk=pk, user=request.user)
    return render(request, 'submissions/detail.html', {'submission': sub})