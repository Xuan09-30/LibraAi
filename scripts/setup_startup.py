import os
import sys
import argparse
import subprocess

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STARTUP_DIR = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup")
SHORTCUT_PATH = os.path.join(STARTUP_DIR, "LibraAssistant.lnk")
VBS_PATH = os.path.join(PROJECT_ROOT, "scripts", "Launch_Libra_Background.vbs")
ICON_PATH = os.path.join(PROJECT_ROOT, "assets", "icon.png")


def create_startup_shortcut() -> bool:
    """Creates a Windows Startup shortcut pointing to Launch_Libra_Background.vbs."""
    if not os.path.exists(VBS_PATH):
        print(f"[Error] Launcher VBS not found at: {VBS_PATH}")
        return False

    os.makedirs(STARTUP_DIR, exist_ok=True)

    # 1. Primary method: win32com WScript.Shell
    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(SHORTCUT_PATH)
        shortcut.TargetPath = VBS_PATH
        shortcut.WorkingDirectory = PROJECT_ROOT
        shortcut.Description = "Project Libra // Cybernetic Neural Assistant"
        if os.path.exists(ICON_PATH):
            shortcut.IconLocation = ICON_PATH
        shortcut.save()
        print(f"[Success] Startup shortcut created via win32com at:\n  {SHORTCUT_PATH}")
        return True
    except Exception as e:
        print(f"[Info] win32com method failed ({e}), attempting PowerShell fallback...")

    # 2. Fallback method: PowerShell COM WScript.Shell
    try:
        escaped_shortcut = SHORTCUT_PATH.replace("'", "''")
        escaped_vbs = VBS_PATH.replace("'", "''")
        escaped_root = PROJECT_ROOT.replace("'", "''")
        escaped_icon = ICON_PATH.replace("'", "''")

        icon_line = f"$s.IconLocation = '{escaped_icon}';" if os.path.exists(ICON_PATH) else ""
        ps_cmd = (
            f"$ws = New-Object -ComObject WScript.Shell; "
            f"$s = $ws.CreateShortcut('{escaped_shortcut}'); "
            f"$s.TargetPath = '{escaped_vbs}'; "
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
    """Removes the Windows Startup shortcut for Project Libra."""
    if os.path.exists(SHORTCUT_PATH):
        try:
            os.remove(SHORTCUT_PATH)
            print(f"[Success] Removed startup shortcut from:\n  {SHORTCUT_PATH}")
            return True
        except Exception as e:
            print(f"[Error] Failed to remove shortcut: {e}")
            return False
    else:
        print(f"[Notice] Shortcut does not exist at: {SHORTCUT_PATH}")
        return True


def check_status() -> bool:
    """Checks if Project Libra is registered for Windows startup."""
    exists = os.path.exists(SHORTCUT_PATH)
    status_str = "ENABLED" if exists else "DISABLED"
    print(f"\n[Project Libra Startup Status]: {status_str}")
    print(f"  Shortcut Path: {SHORTCUT_PATH}")
    print(f"  Target VBS:    {VBS_PATH}")
    print(f"  Target Exists: {os.path.exists(VBS_PATH)}\n")
    return exists


def main():
    parser = argparse.ArgumentParser(description="Configure Project Libra Windows Startup Registration.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--enable", action="store_true", help="Register Libra to auto-boot silently on Windows startup.")
    group.add_argument("--disable", action="store_true", help="Remove Libra from Windows startup.")
    group.add_argument("--status", action="store_true", help="Check current Windows startup registration status.")

    args = parser.parse_args()

    if args.enable:
        success = create_startup_shortcut()
        sys.exit(0 if success else 1)
    elif args.disable:
        success = remove_startup_shortcut()
        sys.exit(0 if success else 1)
    elif args.status:
        check_status()
        sys.exit(0)


if __name__ == "__main__":
    main()
