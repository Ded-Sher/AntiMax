import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Основные настройки
    TOKEN = os.getenv('DISCORD_TOKEN')
    PREFIX = '!'
    GUILD_ID = int(os.getenv('GUILD_ID'))  # ID сервера Discord
    
    # Настройки ролей
    POST_ID = int(os.getenv('POST_ID'))
    ALLOWED_CHANNEL_ID = int(os.getenv('ALLOWED_CHANNEL_ID'))
    MAX_ROLES_PER_USER = int(os.getenv('MAX_ROLES_PER_USER', 5))
    ROLES = {
        os.getenv('EMOJI_1'): int(os.getenv('ROLE_ID_1')),
        os.getenv('EMOJI_2'): int(os.getenv('ROLE_ID_2')),
        os.getenv('EMOJI_3'): int(os.getenv('ROLE_ID_3'))
    }
    EXCROLES = {int(x) for x in os.getenv('EXCROLES', '').split(',') if x}
    
    # Настройки голоса
    VOICE_CHANNEL_ID = int(os.getenv('VOICE_CHANNEL_ID'))
    MAX_DECIBEL = float(os.getenv('MAX_DECIBEL', 30))
    MUTE_DURATION = int(os.getenv('MUTE_DURATION', 10))
    LOG_CHANNEL_ID = int(os.getenv('LOG_CHANNEL_ID'))
    DB_CALIBRATION = float(os.getenv('DB_CALIBRATION', 0))
    
    # Настройки безопасности
    SAMPLE_RATE = 48000
    BUFFER_SECONDS = 10
    MIN_AUDIO_LENGTH = 1
    MAX_BAN_WORDS = 3
    PHRASE_TIMEOUT = 3.0
    MODERATOR_ROLE = os.getenv('MODERATOR_ROLE', 'Генсек')