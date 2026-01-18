import json
import os

from google.cloud import tasks_v2


class TaskConfigError(Exception):
    pass


def _get_tasks_config() -> tuple[str, str, str, str]:
    project = os.getenv("GCP_PROJECT_ID")
    location = os.getenv("CLOUD_TASKS_LOCATION")
    queue = os.getenv("CLOUD_TASKS_QUEUE")
    worker_url = os.getenv("CLOUD_TASKS_WORKER_URL")
    if not (project and location and queue and worker_url):
        raise TaskConfigError("Cloud Tasks nao configurado.")
    return project, location, queue, worker_url.rstrip("/")


def enqueue_http_task(path: str, payload: dict) -> bool:
    try:
        project, location, queue, worker_url = _get_tasks_config()
    except TaskConfigError:
        return False

    client = tasks_v2.CloudTasksClient()
    parent = client.queue_path(project, location, queue)
    url = f"{worker_url}{path}"
    secret = os.getenv("BULK_TASKS_SECRET", "")
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["X-Tasks-Secret"] = secret

    task = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": url,
            "headers": headers,
            "body": json.dumps(payload).encode(),
        }
    }
    client.create_task(request={"parent": parent, "task": task})
    return True
