import docker
import tempfile
import os
import time
import shutil
import tarfile
import io
import platform

# Lazy initialization of Docker client
docker_client = None

def get_docker_client():
    global docker_client
    if docker_client is None:
        try:
            # On Windows, set DOCKER_HOST environment variable for Docker Desktop
            if platform.system() == 'Windows':
                os.environ['DOCKER_HOST'] = 'npipe:////./pipe/docker_engine'
            docker_client = docker.from_env(timeout=60)
        except docker.errors.DockerException as e:
            raise Exception(f"Docker is not running. Please start Docker Desktop: {str(e)}")
    return docker_client

LANGUAGE_CONFIG = {
    "python": {
        "extension": "py",
        "image": "python:3.10-slim",
        "command": ["python", "/code/script.py"],
        "compile_command": None
    },
    "java": {
        "extension": "java",
        "image": "openjdk:11-slim",
        "command": ["java", "-cp", "/code", "Solution"],
        "compile_command": ["javac", "/code/Solution.java"]
    },
    "cpp": {
        "extension": "cpp",
        "image": "gcc:latest",
        "command": ["/code/a.out"],
        "compile_command": ["g++", "-o", "/code/a.out", "/code/script.cpp"]
    },
    "c_cpp": {
        "extension": "cpp",
        "image": "gcc:latest",
        "command": ["/code/a.out"],
        "compile_command": ["g++", "-o", "/code/a.out", "/code/script.cpp"]
    },
    "c": {
        "extension": "c",
        "image": "gcc:latest",
        "command": ["/code/a.out"],
        "compile_command": ["gcc", "-o", "/code/a.out", "/code/script.c"]
    },
    "javascript": {
        "extension": "js",
        "image": "node:16-slim",
        "command": ["node", "/code/script.js"],
        "compile_command": None
    }
}


def _make_tar_bytes(src_dir):
    """Create tarball bytes of src_dir for put_archive"""
    tar_stream = io.BytesIO()
    with tarfile.open(fileobj=tar_stream, mode="w") as tar:
        for filename in os.listdir(src_dir):
            file_path = os.path.join(src_dir, filename)
            tar.add(file_path, arcname=filename)
    tar_stream.seek(0)
    return tar_stream.getvalue()


def _run_code_in_sandbox(code, input_data, language, challenge=None):
    config = LANGUAGE_CONFIG.get(language)
    if not config:
        return {
            "output": "",
            "error": f"Unsupported language: {language}",
            "runtime": 0,
            "memory": 0,
            "status": "ERROR"
        }

    temp_dir = tempfile.mkdtemp()
    code_filename = "Solution.java" if language == "java" else f"script.{config['extension']}"
    code_path = os.path.join(temp_dir, code_filename)

    try:
        # Save code
        with open(code_path, "w", encoding="utf-8") as f:
            f.write(code)

        # Save input - preserve all newlines for multi-line input
        input_file_path = os.path.join(temp_dir, "input.txt")
        with open(input_file_path, "w", encoding="utf-8") as f:
            if input_data:
                # Don't strip - preserve exact input format including newlines
                f.write(input_data)
                # Only add newline if input doesn't end with one
                if not input_data.endswith('\n'):
                    f.write('\n')
            else:
                f.write('')

        # Debug: Print what was written
        with open(input_file_path, "r", encoding="utf-8") as f:
            debug_content = f.read()
            print(f"DEBUG: Input file content ({len(debug_content)} chars, {len(debug_content.splitlines())} lines):")
            print(f"DEBUG: {repr(debug_content[:200])}")

        # Use existing code executor container
        client = get_docker_client()
        try:
            container = client.containers.get("z1_code_executor")
            # Check if container is running, if not start it
            if container.status != 'running':
                container.start()
                time.sleep(1)  # Give it a moment to start
                container.reload()  # Refresh container status
        except docker.errors.NotFound:
            return {
                "output": "",
                "error": "Code executor container not found. Please ensure Docker containers are running.",
                "runtime": 0,
                "memory": 0,
                "status": "SYSTEM_ERROR"
            }

        # Ensure /code exists and clean in one command
        container.exec_run("mkdir -p /code && rm -rf /code/*")

        # Copy code + input into /code
        tar_bytes = _make_tar_bytes(temp_dir)
        container.put_archive("/code", tar_bytes)

        # Compile if needed
        if config["compile_command"]:
            compile_exec = container.exec_run(config["compile_command"], demux=True)
            if compile_exec.exit_code != 0:
                stdout = (compile_exec.output[0] or b"").decode(errors="ignore")
                stderr = (compile_exec.output[1] or b"").decode(errors="ignore")
                # Clean up the /code directory
                container.exec_run(f"rm -rf /code/*")
                return {
                    "output": stdout,
                    "error": f"Compilation Error:\n{stderr}",
                    "runtime": 0,
                    "memory": 0,
                    "status": "COMPILATION_ERROR"
                }

        # Verify input.txt was created successfully
        verify_exec = container.exec_run("cat /code/input.txt", demux=True)
        if verify_exec.exit_code != 0:
            return {
                "output": "",
                "error": "Input file was not created in container",
                "runtime": 0,
                "memory": 0,
                "status": "SYSTEM_ERROR"
            }

        input_in_container = (verify_exec.output[0] or b"").decode(errors="ignore")
        print(f"DEBUG: Input in container ({len(input_in_container)} chars, {len(input_in_container.splitlines())} lines):")
        print(f"DEBUG: {repr(input_in_container[:200])}")

        # Run command using pipe for reliable stdin handling
        run_command_with_redirect = ["sh", "-c", f"cat /code/input.txt | {' '.join(config['command'])}"]

        # Get initial memory stats
        start_time = time.time()

        # Execute the code
        exec_result = container.exec_run(run_command_with_redirect, demux=True)
        runtime_ms = (time.time() - start_time) * 1000

        stdout = (exec_result.output[0] or b"").decode(errors="ignore").strip()
        stderr = (exec_result.output[1] or b"").decode(errors="ignore").strip()

        # Quick memory estimation based on language (skip slow /proc checks)
        code_lines = len(code.split('\n'))
        code_size_kb = len(code) / 1024

        base_memory = {
            'python': 8000 + (code_lines * 50),
            'java': 15000 + (code_lines * 100),
            'cpp': 1000 + (code_lines * 20),
            'c_cpp': 1000 + (code_lines * 20),
            'c': 800 + (code_lines * 15),
            'javascript': 12000 + (code_lines * 60)
        }
        memory_kb = base_memory.get(language, 5000) + (code_size_kb * 100)

        # Clean up the /code directory (non-blocking)
        try:
            container.exec_run("rm -rf /code/*", detach=True)
        except:
            pass  # Cleanup failure shouldn't block response

        # Determine status
        if exec_result.exit_code == 0 and not stderr:
            status = "OK"
        elif exec_result.exit_code == 124:  # timeout
            status = "TIME_LIMIT_EXCEEDED"
        elif stderr and "compilation" in stderr.lower():
            status = "COMPILATION_ERROR"
        else:
            status = "RUNTIME_ERROR"

        return {
            "output": stdout if stdout else "No output",
            "error": stderr,
            "runtime": runtime_ms,
            "memory": round(memory_kb, 2),
            "status": status
        }

    except Exception as e:
        return {
            "output": "",
            "error": f"Unexpected Error: {str(e)}",
            "runtime": 0,
            "memory": 0,
            "status": "SYSTEM_ERROR"
        }
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
