from pathlib import Path

from wps_table.runner import run


if __name__ == "__main__":
    run(str(Path(__file__).resolve().parent))
