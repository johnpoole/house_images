import cv2

def list_available_cameras(max_range=10):
    """
    Probes camera indices 0 to max_range to see which return a valid frame.
    Returns a list of available indices.
    """
    available = []
    for i in range(max_range):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if cap.isOpened():
            # Try to read a frame to be sure
            ret, _ = cap.read()
            if ret:
                available.append(i)
            cap.release()
    return available
