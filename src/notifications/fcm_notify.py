"""Firebase Cloud Messaging — push notifications to the user's Android phone."""

import asyncio
from pathlib import Path

from loguru import logger

from src.shared.config import get_settings

_fcm_initialized = False
_fcm_init_attempted = False


def _get_fcm_service_account_path() -> Path:
    """Resolve Firebase service account path from config."""
    return Path(get_settings().aether_data_path) / "firebase-service-account.json"


def _init_firebase():
    global _fcm_initialized, _fcm_init_attempted
    if _fcm_initialized:
        return True
    if _fcm_init_attempted:
        return False  # Don't retry after failure — firebase_admin.initialize_app() crashes on second call
    _fcm_init_attempted = True
    FCM_SERVICE_ACCOUNT_PATH = _get_fcm_service_account_path()
    if not FCM_SERVICE_ACCOUNT_PATH.exists():
        logger.warning(
            f"FCM: Service account key not found at {FCM_SERVICE_ACCOUNT_PATH}. "
            "Android push notifications disabled. "
            "Download from Firebase Console -> Project Settings -> Service Accounts -> Generate new private key"
        )
        return False
    try:
        import firebase_admin
        from firebase_admin import credentials

        cred = credentials.Certificate(str(FCM_SERVICE_ACCOUNT_PATH))
        firebase_admin.initialize_app(cred)
        _fcm_initialized = True
        logger.info("FCM: Firebase initialized")
        return True
    except Exception as e:
        logger.error(f"FCM: Firebase init failed: {e}")
        return False


async def send_push_notification(
    title: str,
    body: str,
    device_token: str | None = None,
) -> bool:
    """Send a push notification to the user's Android phone. Returns True if sent."""
    if not _init_firebase():
        return False

    settings = get_settings()
    token = device_token or getattr(settings, "android_device_token", None)
    if not token:
        logger.warning("FCM: No Android device token configured -- push disabled")
        return False

    try:
        from firebase_admin import messaging

        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            token=token,
            android=messaging.AndroidConfig(priority="high"),
        )
        response = await asyncio.to_thread(messaging.send, message)
        logger.info(f"FCM: Notification sent ({response})")
        return True
    except Exception as e:
        logger.error(f"FCM: Send failed: {e}")
        return False
