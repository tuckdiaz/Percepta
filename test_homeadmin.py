from pytapo import Tapo

t = Tapo("192.168.1.109", "homeadmin", "admin@123", printDebugInformation=True, redactConfidentialInformation=False)
try:
    print(t.getBasicInfo())
except Exception as e:
    print("Caught error:", e)
