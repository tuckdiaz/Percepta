import requests, json, hashlib

# Let's inspect the camera login directly!
url = "https://192.168.1.109/stok="
headers = {
    "Host": "192.168.1.109:443",
    "Referer": "https://192.168.1.109:443",
    "Accept": "application/json",
    "Content-Type": "application/json; charset=UTF-8"
}

# 1. Step 1: Login request
data1 = {
    "method": "login",
    "params": {
        "cnonce": "12345678",
        "encrypt_type": "3",
        "username": "homeadmin"
    }
}
r1 = requests.post("https://192.168.1.109", data=json.dumps(data1), headers=headers, verify=False)
print("Step 1 status:", r1.status_code)
print("Step 1 body:", r1.text)

# If Step 1 returns nonce, let's do Step 2:
resp1 = r1.json()
if "result" in resp1 and "data" in resp1["result"]:
    nonce = resp1["result"]["data"]["nonce"]
    device_confirm = resp1["result"]["data"].get("device_confirm")
    print("nonce:", nonce)
    print("device_confirm from camera:", device_confirm)

    pwd = "admin@123"
    hashedSha256 = hashlib.sha256(pwd.encode("utf8")).hexdigest().upper()
    hashedMd5 = hashlib.md5(pwd.encode("utf8")).hexdigest().upper()

    calcSha = hashlib.sha256(("12345678" + hashedSha256 + nonce).encode("utf8")).hexdigest().upper()
    calcMd5 = hashlib.sha256(("12345678" + hashedMd5 + nonce).encode("utf8")).hexdigest().upper()

    print("calcSha:", calcSha + nonce + "12345678")
    print("calcMd5:", calcMd5 + nonce + "12345678")
    print("Matches SHA256?", (calcSha + nonce + "12345678") == device_confirm)
    print("Matches MD5?", (calcMd5 + nonce + "12345678") == device_confirm)

    # Let's try sending digest_passwd
    digestPasswd = hashlib.sha256((hashedMd5 + "12345678" + nonce).encode("utf8")).hexdigest().upper()
    data2 = {
        "method": "login",
        "params": {
            "cnonce": "12345678",
            "encrypt_type": "3",
            "digest_passwd": digestPasswd + "12345678" + nonce,
            "username": "homeadmin"
        }
    }
    r2 = requests.post("https://192.168.1.109", data=json.dumps(data2), headers=headers, verify=False)
    print("\nStep 2 (MD5) response:", r2.text)

    # Try with SHA256
    digestPasswdSha = hashlib.sha256((hashedSha256 + "12345678" + nonce).encode("utf8")).hexdigest().upper()
    data2_sha = {
        "method": "login",
        "params": {
            "cnonce": "12345678",
            "encrypt_type": "3",
            "digest_passwd": digestPasswdSha + "12345678" + nonce,
            "username": "homeadmin"
        }
    }
    r2_sha = requests.post("https://192.168.1.109", data=json.dumps(data2_sha), headers=headers, verify=False)
    print("Step 2 (SHA) response:", r2_sha.text)
