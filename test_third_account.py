import pytapo
from pytapo import Tapo
from datetime import date
import inspect, textwrap

src = textwrap.dedent(inspect.getsource(Tapo.refreshStok))
patched_src = src.replace('responseData["result"]["user_group"] != "root"', 'False')

namespace = pytapo.__dict__.copy()
namespace["Tapo"] = Tapo
exec(patched_src, namespace)
Tapo.refreshStok = namespace["refreshStok"]

print("Attempting Tapo login with third_account (homeadmin)...")
try:
    t = Tapo("192.168.1.109", "homeadmin", "admin@123", printDebugInformation=False)
    print("SUCCESS! Logged in with stok:", t.stok)
    print("\nBasic Info:")
    info = t.getBasicInfo()
    print(info)

    today = date.today().strftime("%Y%m%d")
    print(f"\nFetching recordings for {today}...")
    recs = t.getRecordings(today)
    print("Recordings:", recs)
except Exception as e:
    print("Error:", e)
    import traceback
    traceback.print_exc()
