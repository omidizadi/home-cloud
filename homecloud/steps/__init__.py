"""Steps package — one module per install phase."""

from .base import Step, StepResult
from .docker import DockerStep
from .hardening import HardeningStep
from .immich import ImmichStep
from .restic_s3 import ResticS3Step
from .ssd import SsdStep
from .tailscale import TailscaleStep
from .telegram_bot import TelegramBotStep
from .wifi import WifiStep

ALL_STEPS = [
    SsdStep,
    DockerStep,
    TailscaleStep,
    ImmichStep,
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
    "ImmichStep",
    "TailscaleStep",
    "WifiStep",
    "ResticS3Step",
    "TelegramBotStep",
    "HardeningStep",
]
