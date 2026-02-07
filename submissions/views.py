from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from .models import Submission
from .forms import SubmissionForm
from .tasks import process_submission
from django.views.decorators.http import require_POST

@login_required
@require_POST
def delete(request, pk):
    sub = get_object_or_404(Submission, pk=pk, user=request.user)
    sub.delete()
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