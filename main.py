import os
import asyncio
import discord
from discord.ext import commands
from config import Config
import logging
import cProfile
import pstats
import concurrent.futures

# Настройка многопоточности для numpy
os.environ["OMP_NUM_THREADS"] = "4"
os.environ["MKL_NUM_THREADS"] = "4"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

intents = discord.Intents.default()
intents.members = True      # Для работы с участниками
intents.message_content = True  # Для чтения сообщений
intents.voice_states = True  # Для голосовых каналов

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=Config.PREFIX,
            intents=intents,
            activity=discord.Game(name="Модерация сервера")
        )
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        self.allowed_channel_id = Config.ALLOWED_CHANNEL_ID
        self.required_role = "Генсек"

    async def setup_hook(self):
        await self.load_extension('cogs.roles')
        await self.load_extension('cogs.voice')
        await self.load_extension('cogs.security')
        await self.load_extension('cogs.moderation')
        print("✅ Все модули загружены")

    async def check_permissions(self, message):
        # Проверка канала
        if message.channel.id != self.allowed_channel_id:
            return False  # Сообщение не в разрешённом канале
        
        # Проверка роли (только для участников сервера)
        if isinstance(message.author, discord.Member):
            return any(role.name.lower() == self.required_role.lower() 
                     for role in message.author.roles)
        return False  # Не участник сервера или нет роли

async def main():
    bot = MyBot()  # Создаем экземпляр бота
    try:
        print("🔹 Бот запускается...")
        await bot.start(Config.TOKEN)
    except Exception as e:
        logging.critical(f"Критическая ошибка: {e}")
        print(f"🔴 Критическая ошибка: {e}")
    finally:
        if not bot.is_closed():
            await bot.close()

def run_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    finally:
        loop.close()

if __name__ == '__main__':
    print("🔹 Начало работы бота")
    try:
        with cProfile.Profile() as pr:  # Профилирование
            run_bot()  # Запуск бота
    except KeyboardInterrupt:
        print("\n🔹 Бот остановлен пользователем")
    except Exception as e:
        logging.critical(f"Критическая ошибка: {e}")
        print(f"🔴 Критическая ошибка: {e}")
    finally:
        # Анализ и вывод результатов профилирования
        stats = pstats.Stats(pr)
        stats.sort_stats(pstats.SortKey.TIME)
        print("\n🔹 Профилирование производительности:")
        stats.print_stats(20)
        print("🔹 Бот завершил работу")