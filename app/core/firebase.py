import json
import os
from functools import lru_cache

import firebase_admin
from firebase_admin import credentials


def _load_credentials():
    credentials_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
    credentials_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
    if credentials_json:
        return credentials.Certificate(json.loads(credentials_json))
    if credentials_path:
        return credentials.Certificate(credentials_path)
    return credentials.ApplicationDefault()


@lru_cache
def get_firebase_app():
    if firebase_admin._apps:
        return firebase_admin.get_app()
    project_id = os.getenv("FIREBASE_PROJECT_ID")
    app_options = {"projectId": project_id} if project_id else None
    cred = _load_credentials()
    return firebase_admin.initialize_app(cred, app_options)
