# Subprocess Conventions

## Pattern for External Tool Invocation

When calling external tools (ffmpeg, etc.) from backend services:

- Use `subprocess.run()` with `shell=False` and command as a list
- Always set `capture_output=True` and `check=False`
- Set a reasonable `timeout` (300s for ffmpeg operations)
- Handle three error cases: `FileNotFoundError` (tool not installed), `subprocess.TimeoutExpired`, and non-zero `returncode`
- Include the command, stdout, and stderr in error messages for debugging
- Example: `backend/app/services/normalization.py`

## Rationale

External tools like ffmpeg are essential for audio processing. Using `shell=False` prevents injection. Timeouts prevent hung processes. Capturing output enables meaningful error messages.
