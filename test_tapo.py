from pytapo import Tapo
import traceback

def test(user, pwd, cloud_pwd=""):
    print(f"\n--- Testing user='{user}', pwd='{pwd}', cloud_pwd='{cloud_pwd}' ---")
    try:
        t = Tapo("192.168.1.109", user, pwd, cloudPassword=cloud_pwd, printDebugInformation=True)
        info = t.getBasicInfo()
        print("SUCCESS! Basic Info:")
        print(info)
        print("\nTesting getRecordings for today:")
        from datetime import date
        today_str = date.today().strftime("%Y%m%d")
        recs = t.getRecordings(today_str)
        print("Recordings found for today:", recs)
        return True
    except Exception as e:
        print("FAILED with error:", e)
        traceback.print_exc()
        return False

# Test combinations
if not test("homeadmin", "admin@123", ""):
    if not test("homeadmin", "admin@123", "admin@123"):
        if not test("admin", "admin@123", ""):
            test("admin", "admin@123", "admin@123")
