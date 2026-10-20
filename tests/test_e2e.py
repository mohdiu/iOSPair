"""End-to-end test against tests/fake_iphone.py: python tests/test_e2e.py [IOS_VERSION ...]

Pairs twice, checks every export, and reopens a TLS session with the exported file.
On Windows the fake listens where Apple's service would; elsewhere USBMUXD_SOCKET_ADDRESS points to it.
"""

import asyncio
import json
import os
import plistlib
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ.setdefault("USBMUXD_SOCKET_ADDRESS", "127.0.0.1:27015")

from pymobiledevice3.lockdown import create_using_usbmux  # noqa: E402

from iospair import core  # noqa: E402


async def check():
    devices = await core.list_devices()
    assert len(devices) == 1, f"expected one USB device, got {devices}"
    device = devices[0]
    out = Path(tempfile.mkdtemp())
    statuses = []
    first = await core.generate(device.udid, out, statuses.append)
    second = await core.generate(device.udid, out, statuses.append)
    assert statuses[:4] == ["connecting", "unlock", "trust", "saving"], statuses
    assert first.wifi_enabled and second.wifi_enabled
    assert first.folder != second.folder

    record = plistlib.loads(first.files[0][0].read_bytes())
    other = plistlib.loads(second.files[0][0].read_bytes())
    assert record["HostID"] != other["HostID"] and record["SystemBUID"] != other["SystemBUID"]
    assert record["UDID"] == device.udid
    assert len({path.read_bytes() for path, _ in first.files}) == 1
    for key in ("HostCertificate", "HostPrivateKey", "RootCertificate", "DeviceCertificate", "EscrowBag"):
        assert key in record, key

    client = await create_using_usbmux(device.udid, pair_record=record, autopair=False, connection_type="USB")
    try:
        assert client.paired, "exported pairing file was rejected"
    finally:
        await client.close()


def run(ios):
    fake = subprocess.Popen(
        [sys.executable, str(HERE / "fake_iphone.py"), ios], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
    )
    try:
        assert fake.stdout.readline().strip() == "ready"
        asyncio.run(check())
    finally:
        state = json.loads(fake.communicate("\n", timeout=30)[0].strip().splitlines()[-1])
    assert not state["saved_to_usbmux"], "touched the iTunes pair record"
    print(f"PASS iOS {ios}")


if __name__ == "__main__":
    for version in sys.argv[1:] or ["9.3.5", "12.5.7", "15.8.3", "16.7.10", "26.0"]:
        run(version)
