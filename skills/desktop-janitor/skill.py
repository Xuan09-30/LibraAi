import os


def execute(args: dict, context: dict) -> dict:
    downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
    if not os.path.isdir(downloads_dir):
        return {
            "status": "success",
            "voice_response": "Your Downloads folder could not be found.",
        }

    categories = {
        "installers": (".exe", ".msi"),
        "archives": (".zip", ".rar", ".7z", ".tar", ".gz"),
        "images": (".png", ".jpg", ".jpeg", ".webp", ".gif"),
        "documents": (".pdf", ".docx", ".xlsx", ".pptx", ".txt", ".csv"),
    }
    counts = {k: 0 for k in categories}
    total_bytes = 0
    total_files = 0

    for item in os.listdir(downloads_dir):
        full_p = os.path.join(downloads_dir, item)
        if os.path.isfile(full_p):
            total_files += 1
            try:
                total_bytes += os.path.getsize(full_p)
            except Exception:
                pass
            ext = os.path.splitext(item)[1].lower()
            for cat, exts in categories.items():
                if ext in exts:
                    counts[cat] += 1

    size_mb = round(total_bytes / (1024 * 1024), 1)
    voice = (
        f"Your Downloads folder holds {total_files} files totaling {size_mb} megabytes, "
        f"including {counts['installers']} installers, {counts['archives']} archives, "
        f"and {counts['documents']} documents."
    )
    return {
        "status": "success",
        "total_files": total_files,
        "size_mb": size_mb,
        "breakdown": counts,
        "voice_response": voice,
    }
