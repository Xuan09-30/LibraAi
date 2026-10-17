import psutil


def execute(args: dict, context: dict) -> dict:
    vm = psutil.virtual_memory()
    cpu = psutil.cpu_percent(interval=0.1)
    procs = []
    for p in psutil.process_iter(["name", "memory_info"]):
        try:
            mem_mb = p.info["memory_info"].rss / (1024 * 1024)
            name = p.info["name"]
            if name and mem_mb > 50:
                procs.append((name, mem_mb))
        except Exception:
            continue

    procs.sort(key=lambda x: x[1], reverse=True)
    top_3 = [f"{name.replace('.exe', '')} ({int(mb)} MB)" for name, mb in procs[:3]]
    top_str = ", ".join(top_3) if top_3 else "no heavy processes"
    used_gb = round(vm.used / (1024 ** 3), 1)
    total_gb = round(vm.total / (1024 ** 3), 1)

    voice = (
        f"CPU is at {cpu}% and RAM is at {used_gb} of {total_gb} gigabytes ({vm.percent}%). "
        f"Your top memory consumers are {top_str}."
    )
    return {
        "status": "success",
        "cpu_percent": cpu,
        "ram_percent": vm.percent,
        "top_processes": top_3,
        "voice_response": voice,
    }
