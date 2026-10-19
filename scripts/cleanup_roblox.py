import winreg
import psutil

# 1. Remove RobloxPlayerBeta from HKCU Run
REG_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
try:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.DeleteValue(key, "RobloxPlayerBeta")
        print("[Success] Removed RobloxPlayerBeta from HKCU Run registry.")
except FileNotFoundError:
    print("[Info] RobloxPlayerBeta was not in HKCU Run registry.")
except Exception as e:
    print(f"[Warning] Failed to remove RobloxPlayerBeta from registry: {e}")

# 2. Terminate orphaned Roblox processes
killed = 0
for proc in psutil.process_iter(['name', 'pid']):
    try:
        pname = (proc.info.get('name') or '').lower()
        if 'roblox' in pname:
            proc.kill()
            killed += 1
            print(f"Killed orphan Roblox process: {proc.info['name']} (PID: {proc.info['pid']})")
    except Exception:
        pass
print(f"Total Roblox processes terminated: {killed}")
