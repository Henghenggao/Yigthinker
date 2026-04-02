from __future__ import annotations


def record_until_keypress() -> bytes:
    """
    Record audio until the user presses Enter.
    Returns raw PCM bytes.
    Uses sounddevice if available, otherwise raises ImportError with help message.
    """
    try:
        import sounddevice as sd
        import numpy as np
    except ImportError:
        raise ImportError(
            "Voice input requires sounddevice: pip install sounddevice"
        )

    sample_rate = 16000
    chunks = []
    print("Recording... (press Enter to stop)")

    with sd.InputStream(samplerate=sample_rate, channels=1, dtype="int16") as stream:
        import threading
        stop_event = threading.Event()

        def wait_for_enter():
            input()
            stop_event.set()

        t = threading.Thread(target=wait_for_enter, daemon=True)
        t.start()

        while not stop_event.is_set():
            chunk, _ = stream.read(sample_rate // 10)  # 100ms chunks
            chunks.append(chunk)

    audio = np.concatenate(chunks, axis=0)
    return audio.tobytes()
