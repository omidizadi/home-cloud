"""Steps package — one module per install phase."""

from .base import Step, StepResult
from .coturn import CoturnStep
from .docker import DockerStep
from .duckdns import DuckDnsStep
from .hardening import HardeningStep
from .nextcloud_aio import NextcloudAioStep
from .restic_s3 import ResticS3Step
from .samba import SambaStep
from .ssd import SsdStep
from .tailscale import TailscaleStep
from .telegram_bot import TelegramBotStep
from .wifi import WifiStep

ALL_STEPS = [
    SsdStep,
    DockerStep,
    TailscaleStep,
    NextcloudAioStep,
    DuckDnsStep,
    CoturnStep,
    SambaStep,
    WifiStep,
    ResticS3Step,
    TelegramBotStep,
    HardeningStep,
]

__all__ = [
    "Step",
    "StepResult",
    "ALL_STEPS",
    "SsdStep",
    "DockerStep",
    "NextcloudAioStep",
    "DuckDnsStep",
    "TailscaleStep",
    "CoturnStep",
    "SambaStep",
    "WifiStep",
    "ResticS3Step",
    "TelegramBotStep",
    "HardeningStep",
]
