import discord
from discord.ext import commands
from config import Config
from datetime import datetime
import asyncio
import speech_recognition as sr
import logging
import io
import re
from utils.audio import AudioAnalyzer

class VoiceSecurity(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.recognizer = sr.Recognizer()
        self.audio_analyzer = AudioAnalyzer()
        self.user_violations = {}
        self.user_phrases = {}
        self.last_phrase_time = {}
        self.processing_active = True
        self.word_pattern = re.compile(r'\w+', re.UNICODE)
        print("🔹 Модуль голосовой безопасности инициализирован")
        
    async def cog_load(self):
        self.audio_analyzer.start()
        self.bot.loop.create_task(self.continuous_audio_processing())
        print("🔹 Аудиоанализатор запущен")
        
    async def continuous_audio_processing(self):
        print("🔹 Начато непрерывное аудионаблюдение")
        while self.processing_active:
            try:
                audio_data = await self._get_audio_data()
                if audio_data:
                    await self._process_audio(audio_data)
                await asyncio.sleep(0.2)
            except Exception as e:
                error_msg = f"❌ Ошибка обработки аудио: {e}"
                print(error_msg)
                logging.error(error_msg)
                await asyncio.sleep(1)

    async def _get_audio_data(self):
        # Получение аудиоданных
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self.bot.executor,
            self.audio_analyzer.get_audio_data,
            2.0
        )

    async def _process_audio(self, audio_data):
        # Обработка аудиофрагмента
        try:
            loop = asyncio.get_running_loop()
            text = await loop.run_in_executor(
                self.bot.executor,
                self._recognize_speech,
                audio_data
            )
            
            if text:
                await self._process_text(text)
                
        except sr.UnknownValueError:
            pass  # Не распознана речь - нормальная ситуация
        except sr.RequestError as e:
            error_msg = f"❌ Ошибка сервиса распознавания: {e}"
            print(error_msg)
            logging.error(error_msg)
        except Exception as e:
            error_msg = f"❌ Ошибка распознавания речи: {e}"
            print(error_msg)
            logging.error(error_msg)

    def _recognize_speech(self, audio_data):
        # Распознавание речи
        with io.BytesIO(audio_data) as audio_file:
            with sr.AudioFile(audio_file) as source:
                audio = self.recognizer.record(source)
                return self.recognizer.recognize_google(audio, language="ru-RU").lower()

    async def _process_text(self, text):
        # Обработка распознанного текста
        if not self.bot.voice_clients:
            return
            
        voice_channel = self.bot.voice_clients[0].channel
        active_user = self._get_most_active_user(voice_channel)
        if not active_user:
            return
        
        current_time = datetime.now().timestamp()
        
        # Проверка на новую фразу
        if current_time - self.last_phrase_time.get(active_user.id, 0) > Config.PHRASE_TIMEOUT:
            self.user_phrases[active_user.id] = []
        
        self.user_phrases[active_user.id].append(text)
        self.last_phrase_time[active_user.id] = current_time
        
        full_phrase = " ".join(self.user_phrases[active_user.id])
        spoken_words = self.word_pattern.findall(full_phrase)
        found_banned_words = set(spoken_words) & set(BAN_WORDS)
        
        if found_banned_words:
            await self._handle_violation(active_user, next(iter(found_banned_words)))

    def _get_most_active_user(self, voice_channel):
        # Определение самого активного пользователя
        active_members = [m for m in voice_channel.members 
                         if not m.bot and m.voice and not m.voice.self_mute and not m.voice.self_deaf]
        
        if not active_members:
            return None
            
        active_members.sort(
            key=lambda m: self.last_phrase_time.get(m.id, 0),
            reverse=True
        )
        return active_members[0]

    async def _handle_violation(self, user, banned_word):
        # Обработка нарушения
        self.user_violations[user.id] = self.user_violations.get(user.id, 0) + 1
        violations = self.user_violations[user.id]
        
        log_msg = f'⚠️ Пользователь {user.name} произнёс запрещённое слово "{banned_word}" (нарушение {violations}/{Config.MAX_BAN_WORDS})'
        print(log_msg)
        logging.info(log_msg)
        
        self.user_phrases[user.id] = []
        
        if violations >= Config.MAX_BAN_WORDS:
            await self._punish_user(user, banned_word)
        else:
            channel = self.bot.get_channel(Config.ALLOWED_CHANNEL_ID)
            if channel:
                try:
                    await channel.send(f"⚠ {user.mention}, не используйте запрещенные слова! Нарушение {violations}/{Config.MAX_BAN_WORDS}")
                except discord.Forbidden:
                    error_msg = f"❌ Нет прав отправлять сообщения в канал {Config.ALLOWED_CHANNEL_ID}"
                    print(error_msg)
                    logging.error(error_msg)

    async def _punish_user(self, user, banned_word):
        # Наказание пользователя
        try:
            if not user.guild.me.guild_permissions.ban_members:
                error_msg = "❌ У бота нет прав на бан пользователей!"
                print(error_msg)
                logging.error(error_msg)
                channel = self.bot.get_channel(Config.ALLOWED_CHANNEL_ID)
                if channel:
                    await channel.send(f"❌ У меня нет прав забанить {user.mention} за нарушение правил!")
                return
                
            await user.ban(reason=f"Автоматический бан за повторные нарушения: {banned_word}", delete_message_days=0)
            self.user_violations.pop(user.id, None)
            
            log_msg = f"⛔ Пользователь {user.name} забанен за использование запрещенных слов"
            print(log_msg)
            logging.info(log_msg)
            
            channel = self.bot.get_channel(Config.ALLOWED_CHANNEL_ID)
            if channel:
                await channel.send(f"⛔ {user.mention} получил бан за использование запрещенных слов.")
            
            await asyncio.sleep(300)
            try:
                await user.guild.unban(user)
                log_msg = f"✅ Пользователь {user.name} автоматически разбанен"
                print(log_msg)
                logging.info(log_msg)
                if channel:
                    await channel.send(f"✅ {user.name} был автоматически разбанен.")
            except discord.Forbidden:
                error_msg = f"❌ Нет прав на разбан пользователя {user.name}"
                print(error_msg)
                logging.error(error_msg)
                if channel:
                    await channel.send(f"❌ Не удалось разбанить {user.name} - нет прав!")
            
        except discord.Forbidden:
            error_msg = f"❌ Нет прав забанить пользователя {user.name}"
            print(error_msg)
            logging.error(error_msg)
            channel = self.bot.get_channel(Config.ALLOWED_CHANNEL_ID)
            if channel:
                await channel.send(f"❌ Не удалось забанить {user.mention} - нет прав!")
        except Exception as e:
            error_msg = f"❌ Ошибка при бане пользователя {user.name}: {e}"
            print(error_msg)
            logging.error(error_msg)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        # Обновление статуса голосового подключения
        if member.bot:
            return
            
        if after.channel and (not after.self_mute and not after.self_deaf):
            self.last_phrase_time[member.id] = datetime.now().timestamp()

    async def cog_unload(self):
        # Выгрузка модуля
        self.processing_active = False
        self.audio_analyzer.stop()
        print("🔹 Модуль голосовой безопасности выгружен")

# Загрузка запрещенных слов
try:
    with open('ban_words.txt', 'r', encoding='utf-8') as f:
        BAN_WORDS = {word.strip().lower() for word in f.readlines() if word.strip()}
    print(f"🔹 Загружено {len(BAN_WORDS)} запрещенных слов")
    logging.info(f"Загружено {len(BAN_WORDS)} запрещенных слов")
except FileNotFoundError:
    error_msg = "❌ Файл ban_words.txt не найден! Создайте файл со списком запрещенных слов."
    print(error_msg)
    logging.error(error_msg)
    BAN_WORDS = set()

async def setup(bot):
    await bot.add_cog(VoiceSecurity(bot))