"""Fake Apple usbmuxd + iPhone lockdownd on 127.0.0.1:27015 (the Windows Apple Mobile Device port).

Behaves like a real device: passcode-locked first, then pending Trust dialog, then accepts the pair,
checks the generated certificates, and requires a TLS session (with the device key) for SetValue.
"""

import json
import os
import plistlib
import socketserver
import ssl
import struct
import sys
import tempfile
import threading
import time

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

UDID = sys.argv[2] if len(sys.argv) > 2 else "00008030-001A2B3C4D5E802E"
IOS = sys.argv[1] if len(sys.argv) > 1 else "16.7.10"
DEVICE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
DEVICE_PUB = DEVICE_KEY.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.PKCS1)
VALUES = {
    "DeviceName": "iPhone Test",
    "ProductVersion": IOS,
    "ProductType": "iPhone10,3",
    "UniqueDeviceID": UDID,
    "WiFiAddress": "aa:bb:cc:dd:ee:ff",
    "DevicePublicKey": DEVICE_PUB,
}
# paired_hosts: HostID -> DeviceCertificate the host issued for us (used as our TLS server cert).
STATE = {"pair_attempts": 0, "paired_hosts": {}, "wifi": False, "events": [], "saved_to_usbmux": False}
lock = threading.Lock()


def log(event):
    with lock:
        STATE["events"].append(event)


def recv_exact(sock, n):
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError
        data += chunk
    return data


def send_mux(sock, tag, payload):
    body = plistlib.dumps(payload)
    sock.sendall(struct.pack("<IIII", 16 + len(body), 1, 8, tag) + body)


def lockdown_recv(sock):
    (size,) = struct.unpack(">I", recv_exact(sock, 4))
    return plistlib.loads(recv_exact(sock, size))


def lockdown_send(sock, payload):
    body = plistlib.dumps(payload)
    sock.sendall(struct.pack(">I", len(body)) + body)


def verify_record(record):
    root = x509.load_pem_x509_certificate(record["RootCertificate"])
    device = x509.load_pem_x509_certificate(record["DeviceCertificate"])
    host = x509.load_pem_x509_certificate(record["HostCertificate"])
    for cert in (device, host):
        root.public_key().verify(cert.signature, cert.tbs_certificate_bytes, padding.PKCS1v15(), cert.signature_hash_algorithm)
    assert device.public_key().public_numbers() == DEVICE_KEY.public_key().public_numbers(), "device cert key mismatch"
    assert host.public_key() is not None


def lockdown(sock):
    session_host = None
    while True:
        try:
            req = lockdown_recv(sock)
        except (ConnectionError, ssl.SSLError, OSError):
            return
        name = req.get("Request")
        resp = {"Request": name}
        if name == "QueryType":
            resp["Type"] = "com.apple.mobile.lockdown"
        elif name == "GetValue":
            key, domain = req.get("Key"), req.get("Domain")
            if domain == "com.apple.mobile.wireless_lockdown":
                resp["Value"] = STATE["wifi"]
            elif key:
                resp["Value"] = VALUES[key]
            else:
                resp["Value"] = VALUES
        elif name == "Pair":
            STATE["pair_attempts"] += 1
            n = STATE["pair_attempts"]
            if n == 1:
                resp["Error"] = "PasswordProtected"
                log("pair:locked")
            elif n == 2:
                resp["Error"] = "PairingDialogResponsePending"
                log("pair:pending")
            else:
                record = req["PairRecord"]
                verify_record(record)
                host_id = record["HostID"]
                STATE["paired_hosts"][host_id] = record["DeviceCertificate"]
                resp["EscrowBag"] = b"fake-escrow"
                log("pair:ok " + host_id)
        elif name == "StartSession":
            host_id = req.get("HostID")
            if host_id not in STATE["paired_hosts"]:
                resp["Error"] = "InvalidHostID"
                lockdown_send(sock, resp)
                continue
            resp.update({"SessionID": "S1", "EnableSessionSSL": True})
            lockdown_send(sock, resp)
            dev_cert = tempfile.NamedTemporaryFile("wb", suffix=".pem", delete=False)
            dev_cert.write(STATE["paired_hosts"][host_id])
            dev_cert.write(DEVICE_KEY.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
            dev_cert.close()
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.set_ciphers("ALL:@SECLEVEL=0")
            ctx.load_cert_chain(dev_cert.name)
            sock = ctx.wrap_socket(sock, server_side=True)
            session_host = host_id
            log("session:ok " + host_id)
            continue
        elif name == "SetValue":
            if session_host is None:
                resp["Error"] = "SessionInactive"
            else:
                if req.get("Domain") == "com.apple.mobile.wireless_lockdown":
                    STATE["wifi"] = req["Value"]
                    log("wifi:on")
        elif name == "StopSession":
            pass
        else:
            resp["Error"] = "UnsupportedRequest"
        lockdown_send(sock, resp)


class Mux(socketserver.BaseRequestHandler):
    def handle(self):
        sock = self.request
        while True:
            try:
                length, _version, _msg, tag = struct.unpack("<IIII", recv_exact(sock, 16))
            except ConnectionError:
                return
            req = plistlib.loads(recv_exact(sock, length - 16))
            kind = req["MessageType"]
            if kind == "ReadBUID":
                send_mux(sock, tag, {"BUID": "ITUNES-BUID-0000"})
            elif kind == "ListDevices":
                send_mux(sock, tag, {"DeviceList": [
                    {"MessageType": "Attached", "DeviceID": 1, "Properties": {"SerialNumber": UDID, "ConnectionType": "USB"}},
                    {"MessageType": "Attached", "DeviceID": 2, "Properties": {"SerialNumber": UDID, "ConnectionType": "Network"}},
                ]})
            elif kind == "SavePairRecord":
                STATE["saved_to_usbmux"] = True
                send_mux(sock, tag, {"MessageType": "Result", "Number": 0})
            elif kind == "ReadPairRecord":
                send_mux(sock, tag, {"MessageType": "Result", "Number": 2})
            elif kind == "Connect":
                send_mux(sock, tag, {"MessageType": "Result", "Number": 0})
                lockdown(sock)
                return
            else:
                send_mux(sock, tag, {"MessageType": "Result", "Number": 1})


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    server = Server(("127.0.0.1", 27015), Mux)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print("ready", flush=True)
    if os.environ.get("FAKE_IPHONE_LIFETIME"):
        time.sleep(float(os.environ["FAKE_IPHONE_LIFETIME"]))
    else:
        sys.stdin.readline()  # stop on newline / EOF, then dump state
    print(json.dumps({k: v for k, v in STATE.items() if k in ("events", "wifi", "saved_to_usbmux", "pair_attempts")}))
