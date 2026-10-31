import uuid


def generate_idempotency_key() -> str:
    """A v4 UUID from the platform's CSPRNG: the key the SDK sends when a call names none."""
    return str(uuid.uuid4())


def idempotency_key_for_job(job_id: str | int, operation: str) -> str:
    """The key of a background job's call, job:{job_id}:{operation}, the same on every attempt of the job."""
    if isinstance(job_id, bool) or not isinstance(job_id, str | int) or not isinstance(operation, str):
        raise TypeError("Slen: the key of a job takes the id of the job (a string or an integer) and the operation.")

    if not str(job_id).strip() or not operation.strip():
        raise ValueError("Slen: the key of a job needs the id of the job and the operation.")

    return f"job:{job_id}:{operation}"
