from dotenv import load_dotenv
import os

load_dotenv()

# Database
DB_SERVER = os.getenv("DB_SERVER")
DB_DRIVER = os.getenv("DB_DRIVER")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
 
# Paths
TEXT_FOLDER = os.getenv("TEXT_FOLDER")
TEXT_FOLDER = r"D:\cdpgpt_enhancement\data"
SAVE_PATH = r"D:\cdpgpt_enhancement\data"
MAX_FILE_SIZE = 25 * 1024  # 25 KB
BASE_FILE_NAME = "KB_update"