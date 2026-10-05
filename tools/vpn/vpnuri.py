#!/usr/bin/env python3
"""Generate an AmneziaVPN *client* vpn:// link (.vpnuri) from an AmneziaWG client .conf.
Format (matches AmneziaVPN import): vpn:// + base64url( uint32be(len(json)) + zlib(json) ).
"""
import sys, json, zlib, base64, struct

def parse_conf(text):
    iface, peer = {}, {}
    cur = None
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.lower() == "[interface]":
            cur = iface; continue
        if s.lower() == "[peer]":
            cur = peer; continue
        if "=" in s and cur is not None:
            k, v = s.split("=", 1)
            cur[k.strip()] = v.strip()
    return iface, peer

def je(s):
    return (s.replace("\\", "\\\\").replace('"', '\\"')
             .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t"))

def build(conf_text, server_name="Caravan VPN"):
    iface, peer = parse_conf(conf_text)
    ep = peer.get("Endpoint", "")            # ip:port
    host = ep.rsplit(":", 1)[0] if ep else ""
    port = int(peer.get("Endpoint", ":0").rsplit(":", 1)[1] or 0)
    addr = iface.get("Address", "10.8.1.0/32")
    client_ip = addr.split("/", 1)[0]
    allowed = [a.strip() for a in peer.get("AllowedIPs", "0.0.0.0/0").split(",")]

    inner = {}
    for k in ("H1", "H2", "H3", "H4", "Jc", "Jmin", "Jmax", "S1", "S2", "S3", "S4"):
        if k in iface:
            inner[k] = iface[k]
    for k in ("I1", "I2", "I3", "I4", "I5"):
        if iface.get(k):
            inner[k] = iface[k]
    if iface.get("HeaderProtectionKey"):
        inner["HeaderProtectionKey"] = iface["HeaderProtectionKey"]
    if iface.get("ContentPaddingAddition"):
        inner["ContentPaddingAddition"] = iface["ContentPaddingAddition"]
    inner["allowed_ips"] = allowed
    inner["client_ip"] = client_ip
    inner["client_ipv6"] = ""
    inner["client_priv_key"] = iface.get("PrivateKey", "")
    if peer.get("PresharedKey"):
        inner["psk_key"] = peer["PresharedKey"]
    inner["config"] = conf_text
    inner["hostName"] = host
    inner["mtu"] = iface.get("MTU", "1420")
    inner["persistent_keep_alive"] = str(peer.get("PersistentKeepalive", "25"))
    inner["port"] = port
    inner["server_pub_key"] = peer.get("PublicKey", "")

    outer = {
        "containers": [{
            "awg": {
                "isThirdPartyConfig": True,
                "last_config": json.dumps(inner),
                "port": str(port),
                "protocol_version": "3.1",
                "transport_proto": "udp",
            },
            "container": "amnezia-awg",
        }],
        "defaultContainer": "amnezia-awg",
        "description": server_name,
        "dns1": iface.get("DNS", "1.1.1.1").split(",")[0].strip(),
        "dns2": "1.0.0.1",
        "hostName": host,
    }
    oj = json.dumps(outer)
    payload = struct.pack(">I", len(oj.encode("utf-8"))) + zlib.compress(oj.encode("utf-8"))
    return "vpn://" + base64.urlsafe_b64encode(payload).decode().rstrip("=")

if __name__ == "__main__":
    text = open(sys.argv[1], encoding="utf-8").read()
    name = sys.argv[2] if len(sys.argv) > 2 else "Caravan VPN"
    print(build(text, name))
