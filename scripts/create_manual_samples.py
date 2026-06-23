import base64
from pathlib import Path

PNG_1X1 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC"


def main() -> None:
    samples = Path("samples")
    samples.mkdir(exist_ok=True)
    data = base64.b64decode(PNG_1X1)
    for name in [
        "purchase.png",
        "nohit.png",
        "low.png",
        "very-long-contract-file-name-for-responsive-wrapping-check-abcdefghijklmnopqrstuvwxyz-0123456789.png",
    ]:
        (samples / name).write_bytes(data)


if __name__ == "__main__":
    main()
