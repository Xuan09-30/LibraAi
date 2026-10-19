import os
import sys
import argparse
import subprocess
import winreg

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STARTUP_DIR = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup")
SHORTCUT_PATH = os.path.join(STARTUP_DIR, "LibraAssistant.lnk")
ICON_PATH = os.path.join(PROJECT_ROOT, "assets", "icon.png")

PYTHONW_PATH = os.path.join(PROJECT_ROOT, "venv", "Scripts", "pythonw.exe")
if not os.path.exists(PYTHONW_PATH):
    PYTHONW_PATH = "pythonw.exe"

ARGUMENTS = "-m ui.gui --hidden"
REG_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_APP_NAME = "LibraAssistant"


def register_registry_run() -> bool:
    """Registers Libra directly into Windows Logon Run registry (HKCU\\...\\Run)."""
    cmd = f'"{PYTHONW_PATH}" {ARGUMENTS}'
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, REG_APP_NAME, 0, winreg.REG_SZ, cmd)
        print(f"[Success] Registered in Windows Run Registry:\n  HKCU\\{REG_RUN_KEY}\\{REG_APP_NAME} -> {cmd}")
        return True
    except Exception as e:
        print(f"[Warning] Failed to write to Windows Run registry: {e}")
        return False


def unregister_registry_run() -> bool:
    """Removes Libra from Windows Logon Run registry."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, REG_APP_NAME)
        print(f"[Success] Removed from Windows Run Registry: HKCU\\{REG_RUN_KEY}\\{REG_APP_NAME}")
        return True
    except FileNotFoundError:
        return True
    except Exception as e:
        print(f"[Warning] Failed to remove from Windows Run registry: {e}")
        return False


def is_registry_registered() -> bool:
    """Checks if Libra is registered in Windows Run registry."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_QUERY_VALUE) as key:
            val, _ = winreg.QueryValueEx(key, REG_APP_NAME)
            return bool(val)
    except FileNotFoundError:
        return False
    except Exception:
        return False


def create_startup_shortcut() -> bool:
    """Creates a Windows Startup shortcut pointing directly to pythonw.exe."""
    os.makedirs(STARTUP_DIR, exist_ok=True)

    # 1. Primary method: win32com WScript.Shell
    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(SHORTCUT_PATH)
        shortcut.TargetPath = PYTHONW_PATH
        shortcut.Arguments = ARGUMENTS
        shortcut.WorkingDirectory = PROJECT_ROOT
        shortcut.Description = "Project Libra // Cybernetic Neural Assistant"
        if os.path.exists(ICON_PATH):
            shortcut.IconLocation = ICON_PATH
        shortcut.save()
        print(f"[Success] Startup shortcut created at:\n  {SHORTCUT_PATH}")
        return True
    except Exception as e:
        print(f"[Info] win32com method failed ({e}), attempting PowerShell fallback...")

    # 2. Fallback method: PowerShell COM WScript.Shell
    try:
        escaped_shortcut = SHORTCUT_PATH.replace("'", "''")
        escaped_target = PYTHONW_PATH.replace("'", "''")
        escaped_root = PROJECT_ROOT.replace("'", "''")
        escaped_icon = ICON_PATH.replace("'", "''")

        icon_line = f"$s.IconLocation = '{escaped_icon}';" if os.path.exists(ICON_PATH) else ""
        ps_cmd = (
            f"$ws = New-Object -ComObject WScript.Shell; "
            f"$s = $ws.CreateShortcut('{escaped_shortcut}'); "
            f"$s.TargetPath = '{escaped_target}'; "
            f"$s.Arguments = '{ARGUMENTS}'; "
            f"$s.WorkingDirectory = '{escaped_root}'; "
            f"$s.Description = 'Project Libra // Cybernetic Neural Assistant'; "
            f"{icon_line} "
            f"$s.Save()"
        )
        res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True)
        if res.returncode == 0 and os.path.exists(SHORTCUT_PATH):
            print(f"[Success] Startup shortcut created via PowerShell at:\n  {SHORTCUT_PATH}")
            return True
        else:
            print(f"[Error] PowerShell shortcut creation failed: {res.stderr}")
            return False
    except Exception as ex:
        print(f"[Error] Failed to create shortcut: {ex}")
        return False


def remove_startup_shortcut() -> bool:
    """Removes the Windows Startup shortcut and registry key for Project Libra."""
    reg_ok = unregister_registry_run()
    sc_ok = True
    if os.path.exists(SHORTCUT_PATH):
        try:
            os.remove(SHORTCUT_PATH)
            print(f"[Success] Removed startup shortcut from:\n  {SHORTCUT_PATH}")
        except Exception as e:
            print(f"[Error] Failed to remove shortcut: {e}")
            sc_ok = False
    else:
        print(f"[Notice] Shortcut does not exist at: {SHORTCUT_PATH}")
    return reg_ok and sc_ok


def check_status() -> bool:
    """Checks if Project Libra is registered for Windows startup."""
    sc_exists = os.path.exists(SHORTCUT_PATH)
    reg_exists = is_registry_registered()

    status_str = "ENABLED" if (sc_exists or reg_exists) else "DISABLED"
    print(f"\n[Project Libra Startup Status]: {status_str}")
    print(f"  Windows Run Registry: {'ENABLED' if reg_exists else 'DISABLED'}")
    print(f"  Startup Folder .lnk:  {'ENABLED' if sc_exists else 'DISABLED'} ({SHORTCUT_PATH})")
    print(f"  Target Executable:    {PYTHONW_PATH}")
    print(f"  Arguments:            {ARGUMENTS}")
    print(f"  Working Directory:    {PROJECT_ROOT}\n")
    return sc_exists or reg_exists


def main():
    parser = argparse.ArgumentParser(description="Configure Project Libra Windows Startup Registration.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--enable", action="store_true", help="Register Libra to auto-boot silently on Windows startup.")
    group.add_argument("--disable", action="store_true", help="Remove Libra from Windows startup.")
    group.add_argument("--status", action="store_true", help="Check current Windows startup registration status.")

    args = parser.parse_args()

    if args.enable:
        reg_ok = register_registry_run()
        sc_ok = create_startup_shortcut()
        sys.exit(0 if (reg_ok or sc_ok) else 1)
    elif args.disable:
        success = remove_startup_shortcut()
        sys.exit(0 if success else 1)
    elif args.status:
        check_status()
        sys.exit(0)


if __name__ == "__main__":
    main()
