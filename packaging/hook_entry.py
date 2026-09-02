"""Small console-capable PyInstaller entrypoint for Agent hooks."""
from vibegap.adapters.hook import hook_main


if __name__ == "__main__":
    hook_main()
