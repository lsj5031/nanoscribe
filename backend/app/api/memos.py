"""Memo API endpoints – upload, list, get, delete."""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.schemas.upload import FileError, JobResponse, MemoResponse, UploadResponse
from app.services.upload import SUPPORTED_EXTENSIONS, _is_supported_extension, create_memo_and_job

router = APIRouter(tags=["memos"])


def _parse_bool(value: str | None) -> bool:
    """Parse a form-field boolean value.

    Accepts 'true', '1', 'yes' (case-insensitive) as True.
    Accepts 'false', '0', 'no', None, '' as False.
    """
    if value is None or value.strip() == "":
        return False
    return value.strip().lower() in ("true", "1", "yes")


@router.post("/memos", response_model=UploadResponse, status_code=201)
async def upload_memos(
    files: list[UploadFile] = File(..., alias="files[]"),
    title: str | None = Form(None),
    source_kind: str = Form("upload"),
    language: str | None = Form(None),
    enable_diarization: str | None = Form(None),
    hotwords: str | None = Form(None),
) -> UploadResponse:
    """Upload one or more audio files.

    VAL-INTAKE-001: Creates memo and job for each file.
    VAL-INTAKE-004: Batch upload creates independent memos and jobs.
    VAL-INTAKE-006: Unsupported formats return per-file error.
    VAL-INTAKE-016: Empty upload returns 422.
    """
    if not files:
        raise HTTPException(status_code=422, detail="At least one file is required")

    diarization = _parse_bool(enable_diarization)

    memos: list[MemoResponse] = []
    jobs: list[JobResponse] = []
    errors: list[FileError] = []

    for upload_file in files:
        filename = upload_file.filename or "unknown"

        # Read file content
        content = await upload_file.read()

        # Validate format
        if not _is_supported_extension(filename):
            supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
            errors.append(
                FileError(
                    filename=filename,
                    error=f"Unsupported format. Supported formats: {supported}",
                )
            )
            continue

        # Create memo and job
        result = create_memo_and_job(
            filename=filename,
            file_content=content,
            title=title,
            source_kind=source_kind,
            language=language,
            enable_diarization=diarization,
            hotwords=hotwords,
        )

        memos.append(MemoResponse(**result["memo"]))
        jobs.append(JobResponse(**result["job"]))

    # If ALL files were rejected, return 422
    if not memos and errors:
        raise HTTPException(
            status_code=422,
            detail=f"All files rejected. Supported formats: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )

    return UploadResponse(memos=memos, jobs=jobs, errors=errors)
