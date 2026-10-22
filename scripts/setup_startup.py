import os
import sys
import argparse
import subprocess
import winreg

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tools.file_manager import FileManager

STARTUP_DIR = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup")
SHORTCUT_PATH = os.path.join(STARTUP_DIR, "LibraAssistant.lnk")
ICON_PATH = os.path.join(PROJECT_ROOT, "assets", "icon.png")

DESKTOP_DIR = FileManager.get_real_desktop_path()
DESKTOP_SHORTCUT_PATH = os.path.join(DESKTOP_DIR, "Project Libra.lnk")

PYTHONW_PATH = os.path.join(PROJECT_ROOT, "venv", "Scripts", "pythonw.exe")
if not os.path.exists(PYTHONW_PATH):
    PYTHONW_PATH = "pythonw.exe"

GUI_SCRIPT_PATH = os.path.join(PROJECT_ROOT, "ui", "gui.py")
ARGUMENTS = f'"{GUI_SCRIPT_PATH}"'
REG_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_APP_NAME = "LibraAssistant"


def register_registry_run(hidden: bool = False) -> bool:
    """Registers Libra directly into Windows Logon Run registry (HKCU\\...\\Run) with full script path."""
    arg_str = f'"{GUI_SCRIPT_PATH}" --hidden' if hidden else f'"{GUI_SCRIPT_PATH}"'
    cmd = f'"{PYTHONW_PATH}" {arg_str}'
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


def create_startup_shortcut(hidden: bool = False) -> bool:
    """Creates Windows Startup and Desktop shortcuts pointing directly to pythonw.exe with full script path."""
    os.makedirs(STARTUP_DIR, exist_ok=True)
    os.makedirs(DESKTOP_DIR, exist_ok=True)

    startup_args = f'"{GUI_SCRIPT_PATH}" --hidden' if hidden else f'"{GUI_SCRIPT_PATH}"'

    # 1. Primary method: win32com WScript.Shell
    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")

        # A) Auto-startup shortcut (opens and shows UI on boot by default)
        shortcut = shell.CreateShortCut(SHORTCUT_PATH)
        shortcut.TargetPath = PYTHONW_PATH
        shortcut.Arguments = startup_args
        shortcut.WorkingDirectory = PROJECT_ROOT
        shortcut.Description = "Project Libra // Cybernetic Neural Assistant (Auto-Startup)"
        if os.path.exists(ICON_PATH):
            shortcut.IconLocation = ICON_PATH
        shortcut.save()
        print(f"[Success] Startup shortcut created at:\n  {SHORTCUT_PATH}")

        # B) Desktop shortcut (opens / reveals UI on click)
        desktop_sc = shell.CreateShortCut(DESKTOP_SHORTCUT_PATH)
        desktop_sc.TargetPath = PYTHONW_PATH
        desktop_sc.Arguments = f'"{GUI_SCRIPT_PATH}"'
        desktop_sc.WorkingDirectory = PROJECT_ROOT
        desktop_sc.Description = "Project Libra // Cybernetic Neural Assistant"
        if os.path.exists(ICON_PATH):
            desktop_sc.IconLocation = ICON_PATH
        desktop_sc.save()
        print(f"[Success] Desktop shortcut created at:\n  {DESKTOP_SHORTCUT_PATH}")
        return True
    except Exception as e:
        print(f"[Info] win32com method failed ({e}), attempting PowerShell fallback...")

    # 2. Fallback method: PowerShell COM WScript.Shell
    try:
        escaped_startup = SHORTCUT_PATH.replace("'", "''")
        escaped_desktop = DESKTOP_SHORTCUT_PATH.replace("'", "''")
        escaped_target = PYTHONW_PATH.replace("'", "''")
        escaped_script = GUI_SCRIPT_PATH.replace("'", "''")
        escaped_root = PROJECT_ROOT.replace("'", "''")
        escaped_icon = ICON_PATH.replace("'", "''")
        escaped_startup_args = f'`\"{escaped_script}`\" --hidden' if hidden else f'`\"{escaped_script}`\"'

        icon_line = f"$s.IconLocation = '{escaped_icon}';" if os.path.exists(ICON_PATH) else ""
        desktop_icon_line = f"$ds.IconLocation = '{escaped_icon}';" if os.path.exists(ICON_PATH) else ""

        ps_cmd = (
            f"$ws = New-Object -ComObject WScript.Shell; "
            f"$s = $ws.CreateShortcut('{escaped_startup}'); "
            f"$s.TargetPath = '{escaped_target}'; "
            f"$s.Arguments = '{escaped_startup_args}'; "
            f"$s.WorkingDirectory = '{escaped_root}'; "
            f"$s.Description = 'Project Libra // Cybernetic Neural Assistant (Auto-Startup)'; "
            f"{icon_line} "
            f"$s.Save(); "
            f"$ds = $ws.CreateShortcut('{escaped_desktop}'); "
            f"$ds.TargetPath = '{escaped_target}'; "
            f"$ds.Arguments = '`\"{escaped_script}`\"'; "
            f"$ds.WorkingDirectory = '{escaped_root}'; "
            f"$ds.Description = 'Project Libra // Cybernetic Neural Assistant'; "
            f"{desktop_icon_line} "
            f"$ds.Save();"
        )
        res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True)
        if res.returncode == 0 and os.path.exists(SHORTCUT_PATH):
            print(f"[Success] Startup shortcut created via PowerShell at:\n  {SHORTCUT_PATH}")
            print(f"[Success] Desktop shortcut created via PowerShell at:\n  {DESKTOP_SHORTCUT_PATH}")
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
            print(f"[Error] Failed to remove startup shortcut: {e}")
            sc_ok = False
    else:
        print(f"[Notice] Startup shortcut does not exist at: {SHORTCUT_PATH}")

    if os.path.exists(DESKTOP_SHORTCUT_PATH):
        try:
            os.remove(DESKTOP_SHORTCUT_PATH)
            print(f"[Success] Removed desktop shortcut from:\n  {DESKTOP_SHORTCUT_PATH}")
        except Exception:
            pass

    return reg_ok and sc_ok


def check_status() -> bool:
    """Checks if Project Libra is registered for Windows startup."""
    sc_exists = os.path.exists(SHORTCUT_PATH)
    reg_exists = is_registry_registered()

    status_str = "ENABLED" if (sc_exists or reg_exists) else "DISABLED"
    print(f"\n[Project Libra Startup Status]: {status_str}")
    print(f"  Windows Run Registry: {'ENABLED' if reg_exists else 'DISABLED'}")
    print(f"  Startup Folder .lnk:  {'ENABLED' if sc_exists else 'DISABLED'} ({SHORTCUT_PATH})")
    print(f"  Desktop Shortcut:     {'ENABLED' if os.path.exists(DESKTOP_SHORTCUT_PATH) else 'DISABLED'} ({DESKTOP_SHORTCUT_PATH})")
    print(f"  Target Executable:    {PYTHONW_PATH}")
    print(f"  Script Target:        {GUI_SCRIPT_PATH}")
    print(f"  Arguments:            {ARGUMENTS}")
    print(f"  Working Directory:    {PROJECT_ROOT}")

    if sc_exists and reg_exists:
        print("\n  [CRITICAL WARNING]: Both Windows Run Registry AND Startup Folder .lnk are active!")
        print("                      Windows will launch two instances simultaneously at logon.")
        print("                      Run 'python scripts/setup_startup.py --enable' to remove the duplicate registry key.")
    print()
    return sc_exists or reg_exists


def main():
    parser = argparse.ArgumentParser(description="Configure Project Libra Windows Startup Registration.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--enable", action="store_true", help="Register Libra to auto-boot and show UI on Windows startup.")
    group.add_argument("--disable", action="store_true", help="Remove Libra from Windows startup.")
    group.add_argument("--status", action="store_true", help="Check current Windows startup registration status.")
    parser.add_argument("--hidden", action="store_true", help="Start minimized/hidden instead of showing the UI.")

    args = parser.parse_args()

    if args.enable:
        is_hidden = bool(args.hidden)
        # Clean up any duplicate Windows Run registry key to prevent dual-launch race conditions
        unregister_registry_run()
        # Create standard Startup folder shortcut with working directory and icon
        sc_ok = create_startup_shortcut(hidden=is_hidden)
        sys.exit(0 if sc_ok else 1)
    elif args.disable:
        success = remove_startup_shortcut()
        sys.exit(0 if success else 1)
    elif args.status:
        check_status()
        sys.exit(0)


if __name__ == "__main__":
    main()
