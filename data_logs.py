import logging
import os

log_path = os.path.join(os.getcwd(), "test_log.txt")

logger = logging.getLogger()
logger.setLevel(logging.INFO)

if logger.hasHandlers():
    logger.handlers.clear()

try:
    file_handler = logging.FileHandler(log_path, mode='w')
    logger.addHandler(file_handler)
    print("✅ FileHandler created at:", log_path)
except Exception as e:
    print("❌ Error:", e)

logger.info("TEST LOG ENTRY")

print("DONE")