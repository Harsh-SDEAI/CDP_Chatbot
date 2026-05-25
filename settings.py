from dotenv import load_dotenv
import os

load_dotenv()

# Database (chatbot DB — CDPChatHistory etc.)
DB_SERVER = os.getenv("DB_SERVER")
DB_DRIVER = os.getenv("DB_DRIVER")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

# CDP2000 DB (lives on a separate server — Roster, AllGamesCurrentYear, RegularCurrentStandings)
CDP_DB_SERVER = os.getenv("CDP_DB_SERVER")
CDP_DB_DRIVER = os.getenv("CDP_DB_DRIVER")
CDP_DB_NAME = os.getenv("CDP_DB_NAME")
CDP_DB_USER = os.getenv("CDP_DB_USER")
CDP_DB_PASSWORD = os.getenv("CDP_DB_PASSWORD")

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
 
# Paths
TEXT_FOLDER = os.getenv("TEXT_FOLDER")
USER_LIMIT = int(os.getenv('USER_LIMIT', 5))
SAVE_PATH = os.getenv("SAVE_PATH")
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", 25600))  
BASE_FILE_NAME = os.getenv("BASE_FILE_NAME", "KB_update")
API_KEYS = os.getenv("API_KEYS", "").split(",")