import subprocess
import os
import uuid
import time
import shutil
import re
from celery import shared_task
from django.conf import settings
from .models import Submission

LANGUAGE_CONFIG = {
    'swift': {
        'image': 'swift:latest',
        'file_name': 'main.swift',
        'compile_cmd': 'swiftc /code/main.swift -o /code/main',
        'run_cmd': '/code/main'
    },
    'csharp': {
        'image': 'mcr.microsoft.com/dotnet/sdk:8.0-alpine',
        'file_name': 'Program.cs',
        'compile_cmd': 'dotnet new console -n app -o /code --force && dotnet build /code/app.csproj -o /code/build',
        'run_cmd': 'dotnet /code/build/app.dll'
    },
    'python': {
        'image': 'python:3.12-slim',
        'file_name': 'main.py',
        'run_cmd': 'python /code/main.py'
    },
    'javascript': {
        'image': 'node:20-alpine',
        'file_name': 'main.js',
        'run_cmd': 'node /code/main.js'
    },
    'bash': {
        'image': 'bash:5.2-alpine',
        'file_name': 'script.sh',
        'run_cmd': 'bash /code/script.sh'
    },
    'c': {
        'image': 'gcc:latest',
        'file_name': 'main.c',
        'compile_cmd': 'gcc /code/main.c -o /code/main',
        'run_cmd': '/code/main'
    },
    'cpp': {
        'image': 'gcc:latest',
        'file_name': 'main.cpp',
        'compile_cmd': 'g++ /code/main.cpp -o /code/main',
        'run_cmd': '/code/main'
    },
    'java': {
        'image': 'amazoncorretto:17-alpine',
        'file_name': 'Main.java',
        'compile_cmd': 'javac /code/{filename}',
        'run_cmd': 'java -cp /code {classname}'
    },
    'rust': {
        'image': 'rust:1.75-slim',
        'file_name': 'main.rs',
        'compile_cmd': 'rustc /code/main.rs -o /code/main',
        'run_cmd': '/code/main'
    },
    'go': {
        'image': 'golang:1.21-alpine',
        'file_name': 'main.go',
        'compile_cmd': 'go build -o /code/main /code/main.go',
        'run_cmd': '/code/main'
    },
    'typescript': {
        'image': 'oven/bun:1',
        'file_name': 'main.ts',
        'run_cmd': 'bun run /code/main.ts'
    },
    'ruby': {
        'image': 'ruby:3.2-alpine',
        'file_name': 'main.rb',
        'run_cmd': 'ruby /code/main.rb'
    }
}

def run_docker(image, command, host_dir, input_data=None, timeout=30):
    docker_cmd = [
        'docker', 'run', 
        '-i',
        '--rm',
        '--network', 'none',
        '--memory', '512m',
        '-v', f'{host_dir}:/code',
        image,
        '/bin/sh', '-c', command
    ]
    return subprocess.run(
        docker_cmd,
        input=input_data if input_data else "",
        capture_output=True,
        text=True,
        timeout=timeout
    )

@shared_task(soft_time_limit=65, time_limit=70)
def process_submission(submission_id):
    print(f"--> [Smart Runner] Processing {submission_id}")
    submission = Submission.objects.get(id=submission_id)
    lang = submission.language_id.lower()
    user_input = submission.custom_input or ""
    if lang not in LANGUAGE_CONFIG:
        submission.result = "System Error"
        submission.stderr = "Language not supported."
        submission.save()
        return

    config = LANGUAGE_CONFIG[lang].copy()

    unique_id = uuid.uuid4().hex[:8]
    host_dir = os.path.join(settings.BASE_DIR, 'temp_submissions', unique_id)
    os.makedirs(host_dir, exist_ok=True)

    user_class = "Main"
    if lang == 'java':
        match = re.search(r'public\s+class\s+(\w+)', submission.source_code)
        if match:
            user_class = match.group(1)
            config['file_name'] = f"{user_class}.java"
    
    file_path = os.path.join(host_dir, config['file_name'])
    with open(file_path, 'w') as f:
        f.write(submission.source_code)
        
    submission.memory_used = len(submission.source_code.encode('utf-8'))
    
    try:
        if 'compile_cmd' in config:
            compile_command = config['compile_cmd'].format(filename=config['file_name'])
            
            c_result = run_docker(config['image'], compile_command, host_dir, input_data=None, timeout=60)
            
            if c_result.returncode != 0:
                submission.result = "Compilation Error"
                submission.stderr = c_result.stderr
                submission.stdout = c_result.stdout
                submission.execution_time = 0
                submission.status = Submission.Status.COMPLETED
                submission.save()
                shutil.rmtree(host_dir)
                return 
        run_command = config['run_cmd'].format(classname=user_class)
        
        start_time = time.perf_counter()
        
        r_result = run_docker(config['image'], run_command, host_dir, input_data=user_input, timeout=60)
        
        end_time = time.perf_counter()
        
        total_time = end_time - start_time
        submission.execution_time = max(round(total_time - 1.5, 3), 0.01)

        if r_result.returncode == 0:
            submission.result = "Accepted"
            submission.stdout = r_result.stdout
            submission.stderr = ""
        else:
            submission.result = "Runtime Error"
            submission.stderr = r_result.stderr
            submission.stdout = r_result.stdout

    except subprocess.TimeoutExpired:
        submission.result = "Time Limit Exceeded"
        submission.stderr = "Code took too long to execute."

    except Exception as e:
        submission.result = "System Error"
        submission.stderr = str(e)

    finally:
        if os.path.exists(host_dir):
            shutil.rmtree(host_dir)

    submission.status = Submission.Status.COMPLETED
    submission.save()