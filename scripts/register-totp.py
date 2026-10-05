#!/usr/bin/env python3
"""Register a TOTP device for an Authelia user (used by install.sh).

Logs in, completes identity verification using the one-time code Authelia writes
to its notifier file, registers a TOTP configuration, validates it, and prints
the ``otpauth://`` URL so the admin can add it to an authenticator app. This
removes the fragile browser elevation dance from onboarding.

    python3 register-totp.py --base https://auth.example.com --user admin \
        --password PW --notify /opt/caravan/authelia/notification.txt
"""
import argparse
import base64
import hashlib
import hmac
import http.cookiejar
import json
import re
import ssl
import struct
import sys
import time
import urllib.request

CODE_RE = re.compile(r"^[A-Z0-9]{8}$", re.M)


def build_opener():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ctx),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
    )


def totp_code(secret, at=None):
    key = base64.b32decode(secret + "=" * ((8 - len(secret) % 8) % 8))
    counter = struct.pack(">Q", int((at or time.time()) // 30))
    digest = hmac.new(key, counter, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return "%06d" % (value % 1000000)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="Authelia base URL")
    ap.add_argument("--user", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--notify", required=True, help="Authelia notifier file")
    ap.add_argument("--target", default="", help="targetURL for the login")
    args = ap.parse_args()

    opener = build_opener()

    def call(path, body=None, method="POST"):
        data = json.dumps(body if body is not None else {}).encode()
        req = urllib.request.Request(
            args.base + path, data=data, method=method,
            headers={"Content-Type": "application/json"})
        with opener.open(req, timeout=20) as resp:
            raw = resp.read().decode() or "{}"
        return json.loads(raw)

    call("/api/firstfactor", {"username": args.user, "password": args.password,
                              "targetURL": args.target, "keepMeLoggedIn": True})
    call("/api/user/session/elevation", {}, "POST")

    code = ""
    for _ in range(20):
        try:
            with open(args.notify, encoding="utf-8") as fh:
                found = CODE_RE.findall(fh.read())
            code = found[-1] if found else ""
        except OSError:
            code = ""
        if code:
            break
        time.sleep(0.5)
    if not code:
        sys.exit("could not read the one-time code from " + args.notify)

    call("/api/user/session/elevation", {"otc": code}, "PUT")

    reg = call("/api/secondfactor/totp/register",
               {"algorithm": "SHA1", "length": 6, "period": 30}, "PUT")
    secret = reg["data"]["base32_secret"]
    otpauth = reg["data"]["otpauth_url"]

    call("/api/secondfactor/totp/register", {"token": totp_code(secret)}, "POST")
    print(otpauth)


if __name__ == "__main__":
    main()
