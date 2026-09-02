"""PyInstaller entrypoint;kept separate from package console scripts."""
from multiprocessing import freeze_support

from vibegap.cli import main


if __name__ == "__main__":
    freeze_support()
    main()
