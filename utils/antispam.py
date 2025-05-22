from datetime import datetime, timedelta
import logging

class AntiFlood:
    def __init__(self, cooldown=2):
        self.last_actions = {}
        self.cooldown = cooldown
        print(f"🔹 Антифлуд система инициализирована (задержка {cooldown} сек)")
    
    async def check_flood(self, user_id):
        now = datetime.now()
        if user_id in self.last_actions:
            if (now - self.last_actions[user_id]).total_seconds() < self.cooldown:
                logging.warning(f'Обнаружен флуд от пользователя {user_id}')
                return True
        self.last_actions[user_id] = now
        return False