from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from .models import Submission
from .forms import SubmissionForm
import os
from .tasks import process_submission
from django.views.decorators.http import require_POST
from django.views.generic.edit import CreateView
from django.http import JsonResponse
from judge_vortex.throttling import DistributedRateThrottle
from judge_vortex.kafka_producer import send_submission_event

@login_required
@require_POST
def delete(request, pk):
    # 1. Get the submission from the DB
    submission = get_object_or_404(Submission, pk=pk)

    # 2. Try to delete the actual file (if it exists)
    try:
        if submission.code and os.path.isfile(submission.code.path):
            os.remove(submission.code.path)
    except Exception as e:
        print(f"Error deleting file: {e}") # Prints error to logs but doesn't crash

    # 3. Delete the database record (This is the important part)
    submission.delete()

    return redirect('list')

def landing(request):
    if request.user.is_authenticated:return redirect('list')
    return render(request, 'submissions/landing.html')

def register(request):
    if request.user.is_authenticated:return redirect('list')
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('list')
    else:form = UserCreationForm()
    return render(request, 'submissions/auth/register.html', {'form': form})

@login_required
def slist(request):
    submissions = Submission.objects.filter(user=request.user)
    return render(request, 'submissions/list.html', {'submissions': submissions})

@login_required
def create(request):
    if request.method == 'POST':
        form = SubmissionForm(request.POST)
        if form.is_valid():
            sub = form.save(commit=False)
            sub.user = request.user
            sub.save()
            process_submission.delay(sub.id)
            return redirect('list')
    else:form = SubmissionForm()
    return render(request, 'submissions/create.html', {'form': form})

@login_required
def detail(request, pk):
    sub = get_object_or_404(Submission, pk=pk, user=request.user)
    return render(request, 'submissions/detail.html', {'submission': sub})


class SubmissionCreateView(CreateView):
    model = Submission
    form_class = SubmissionForm
    template_name = 'submissions/create.html'

    def post(self, request, *args, **kwargs):
        # 1. SCALE: Check Rate Limit
        throttler = DistributedRateThrottle()
        if not throttler.allow_request(request, self):
            return JsonResponse({'error': 'Thundering Herd Protection: Too many requests!'}, status=429)

        # 2. Standard Form Processing
        form = self.get_form()
        if form.is_valid():
            submission = form.save(commit=False)
            if request.user.is_authenticated:
                submission.user = request.user
            submission.save()
            
            # 3. MICROSERVICES: Send to Kafka (Instead of running immediately)
            send_submission_event(submission.id, submission.source_code, submission.language_id)
            
            return JsonResponse({'status': 'queued', 'id': submission.id})
        
        return JsonResponse({'error': 'Invalid form'}, status=400)