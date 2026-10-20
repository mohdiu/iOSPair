"""Pairing-file generation for iPhone/iPad over USB.

Every run creates a brand-new pairing (new HostID + SystemBUID), so it never
collides with iTunes' own record or with pairing files made earlier.
Nothing is written to the computer's lockdown store; the record only lives
in the exported files.
"""

import asyncio
import datetime
import plistlib
import re
import socket
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from pymobiledevice3 import usbmux
from pymobiledevice3.ca import generate_pairing_cert_chain
from pymobiledevice3.exceptions import (
    ConnectionFailedToUsbmuxdError,
    PairingDialogResponsePendingError,
    PasswordRequiredError,
    PasscodeRequiredError,
    UserDeniedPairingError,
)
from pymobiledevice3.lockdown import UsbmuxLockdownClient
from pymobiledevice3.service_connection import ServiceConnection

LOCKDOWN_PORT = 62078
LABEL = "iOSPair"
TRUST_TIMEOUT = 180  # seconds to wait for the user to tap "Trust"

# Same record, saved under the names each popular app expects.
OUTPUT_NAMES = (
    ("{udid}.mobiledevicepairing", "SideStore / AltStore"),
    ("ALTPairingFile.mobiledevicepairing", "SideStore / AltStore"),
    ("{udid}.plist", "StikDebug / Jitterbug / LiveContainer"),
    ("pairingFile.plist", "Feather / StikDebug"),
)


class AppleServiceMissing(Exception):
    """Apple Mobile Device Service (iTunes / Apple Devices) is not running."""


class UserDenied(Exception):
    pass


class TrustTimeout(Exception):
    pass


@dataclass
class Device:
    udid: str
    name: str = ""
    ios: str = ""
    model: str = ""

    @property
    def title(self) -> str:
        name = self.name or self.model or "iPhone"
        return f"{name}  (iOS {self.ios})" if self.ios else name


@dataclass
class PairResult:
    device: Device
    folder: Path
    files: list = field(default_factory=list)
    wifi_enabled: bool = False


class _ExportOnlyClient(UsbmuxLockdownClient):
    """Lockdown client that never reads or writes the system pair-record store."""

    async def fetch_pair_record(self) -> None:
        return None

    async def save_pair_record(self) -> None:
        return None


async def _open_client(udid: str) -> _ExportOnlyClient:
    service = await ServiceConnection.create_using_usbmux(udid, LOCKDOWN_PORT, connection_type="USB")
    client = _ExportOnlyClient(
        service,
        host_id=str(uuid.uuid4()).upper(),
        identifier=udid,
        label=LABEL,
        system_buid=str(uuid.uuid4()).upper(),
    )
    try:
        await client._initialize()
    except Exception:
        await service.close()
        raise
    return client


async def list_devices() -> list:
    try:
        mux_devices = await usbmux.list_devices()
    except ConnectionFailedToUsbmuxdError as e:
        raise AppleServiceMissing() from e

    devices = []
    seen = set()
    for mux_device in mux_devices:
        if not mux_device.is_usb or mux_device.serial in seen:
            continue
        seen.add(mux_device.serial)
        device = Device(udid=mux_device.serial)
        try:
            service = await ServiceConnection.create_using_usbmux(device.udid, LOCKDOWN_PORT, connection_type="USB")
            try:
                # Unpaired hosts may still read these basic values.
                client = _ExportOnlyClient(service, host_id="", identifier=device.udid, label=LABEL)
                values = await client.get_value()
                device.name = values.get("DeviceName", "")
                device.ios = values.get("ProductVersion", "")
                device.model = values.get("ProductType", "")
            finally:
                await service.close()
        except Exception:
            pass
        devices.append(device)
    return devices


def _safe_name(text: str) -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", text).strip(" .")
    return text or "iPhone"


def write_pairing_files(record: dict, device: Device, out_root: Path) -> PairResult:
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    folder = out_root / f"{_safe_name(device.name)}_{stamp}"
    folder.mkdir(parents=True, exist_ok=True)
    data = plistlib.dumps(record, fmt=plistlib.FMT_XML)
    result = PairResult(device=device, folder=folder)
    for pattern, app in OUTPUT_NAMES:
        path = folder / pattern.format(udid=device.udid)
        path.write_bytes(data)
        result.files.append((path, app))
    return result


async def generate(udid: str, out_root: Path, status: Callable[[str], None], enable_wifi: bool = True) -> PairResult:
    """Pair with the device and export the record. `status` receives a key from STATUS_TEXT."""
    status("connecting")
    client = await _open_client(udid)
    try:
        device = Device(
            udid=client.udid or udid,
            name=client.all_values.get("DeviceName", ""),
            ios=client.product_version,
            model=client.all_values.get("ProductType", ""),
        )

        device_public_key = await client.get_value("", "DevicePublicKey")
        host_cert, host_key, device_cert, root_cert, root_key = generate_pairing_cert_chain(
            device_public_key, device_version=device.ios or None
        )
        record = {
            "DeviceCertificate": device_cert,
            "HostCertificate": host_cert,
            "HostID": client.host_id,
            "RootCertificate": root_cert,
            "RootPrivateKey": root_key,
            "SystemBUID": client.system_buid,
        }
        if client.wifi_mac_address:
            record["WiFiMACAddress"] = client.wifi_mac_address
        pair_options = {
            "HostName": socket.gethostname(),
            "PairRecord": record,
            "ProtocolVersion": "2",
            "PairingOptions": {"ExtendedPairingErrors": True},
        }

        loop = asyncio.get_running_loop()
        deadline = loop.time() + TRUST_TIMEOUT
        while True:
            try:
                response = await client._request("Pair", pair_options)
                break
            except (PasswordRequiredError, PasscodeRequiredError):
                status("unlock")
            except PairingDialogResponsePendingError:
                status("trust")
            except UserDeniedPairingError as e:
                raise UserDenied() from e
            if loop.time() > deadline:
                raise TrustTimeout()
            await asyncio.sleep(1)

        status("saving")
        record["HostPrivateKey"] = host_key
        if response.get("EscrowBag") is not None:
            record["EscrowBag"] = response["EscrowBag"]
        record["UDID"] = device.udid

        wifi_enabled = False
        if enable_wifi:
            try:
                client.pair_record = dict(record)
                if await client.validate_pairing():
                    await client.set_enable_wifi_connections(True)
                    wifi_enabled = True
            except Exception:
                pass

        result = write_pairing_files(record, device, out_root)
        result.wifi_enabled = wifi_enabled
        return result
    finally:
        await client.close()


def _desktop() -> Path:
    if sys.platform == "win32":
        # Real Desktop location, also when it is redirected to OneDrive.
        import ctypes

        buf = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buf) == 0 and buf.value:
            return Path(buf.value)
    desktop = Path.home() / "Desktop"
    return desktop if desktop.is_dir() else Path.home()


def default_output_dir() -> Path:
    return _desktop() / "iOSPair"
