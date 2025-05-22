import discord
from discord.ext import commands
from config import Config
from datetime import datetime, timedelta
import asyncio
import logging
import numpy as np
from utils.audio import AudioAnalyzer

class VoiceMod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voice_client = None
        self.user_data = {}  # Для анализа громкости
        self.mute_tasks = {}  # Для автоматического снятия мута
        self.last_mute_time = {}  # Время последнего мута
        self.last_print_time = {}
        self.CHECK_INTERVAL = 0.5
        self.MAX_DECIBEL = Config.MAX_DECIBEL
        self.MUTE_DURATION = Config.MUTE_DURATION
        self.DB_CALIBRATION = Config.DB_CALIBRATION
        
        # Удаляем стандартную команду !help
        if self.bot.help_command:
            self.bot.help_command = None
        
        # Словарь команд и их обработчиков
        self.commands = {
            "help": self.cmd_help,
            "status": self.cmd_status,
            "set_threshold": self.cmd_set_threshold,
            "set_duration": self.cmd_set_duration,
            "set_calibration": self.cmd_set_calibration,
            "join": self.cmd_join,
            "leave": self.cmd_leave,
        }
        
        print("🔹 Модуль голосовой модерации инициализирован")

    async def process_command(self, ctx, command, args):
        # Обработка команд через словарь
        if command not in self.commands:
            return False
            
        if not await self.bot.check_permissions(ctx.message):
            await ctx.send("❌ У вас нет прав для выполнения этой команды.", delete_after=5.0)
            return True
            
        await self.commands[command](ctx, args)
        return True

    async def cmd_help(self, ctx, args):
        # Показывает справку по командам
        help_text = """
        **Доступные команды (только для Генсеков):**
        `!help` – Показать эту справку
        `!status` – Текущие настройки бота
        `!join [ID_канала]` – Пригласить бота в голосовой канал
        `!leave` – Отключить бота от голосового канала
        `!set_threshold <значение>` – Установить порог громкости (dB)
        `!set_duration <секунды>` – Установить длительность мута
        `!set_calibration <значение>` – Установить калибровку микрофона (dB)
        `!mute <@пользователь>` – Замьютить пользователя в этом голосовом канале
        `!unmute <@пользователь>` – Размьютить пользователя в голосовых каналах
        """
        await ctx.send(help_text)

    async def cmd_status(self, ctx, args):
        # Показывает текущие настройки
        status_msg = (
            f"**Текущие настройки:**\n"
            f"• Порог громкости: {self.MAX_DECIBEL} dB\n"
            f"• Длительность мута: {self.MUTE_DURATION} сек\n"
            f"• Калибровка микрофона: {self.DB_CALIBRATION} dB\n"
            f"• Мониторинг канала: {self.voice_client.channel.name if self.voice_client else 'Не активен'}"
        )
        await ctx.send(status_msg)

    async def cmd_set_threshold(self, ctx, args):
        # Устанавливает порог громкости
        try:
            value = float(args[0])
            Config.MAX_DECIBEL = value
            
            # Применяем изменение в аудиоанализаторе
            if hasattr(self.bot, 'audio_analyzer'):
                self.bot.audio_analyzer.threshold = value
            
            await ctx.send(f"✅ Порог громкости установлен на {value} dB")
            print(f"🔹 Порог громкости изменён на {value} dB по команде от {ctx.author}")
        except (IndexError, ValueError):
            await ctx.send("❌ Использование: `!set_threshold <значение>`")

    async def cmd_set_duration(self, ctx, args):
        # Устанавливает длительность мута
        try:
            seconds = int(args[0])
            Config.MUTE_DURATION = seconds
            
            # Применяем в модуле голосовой модерации
            if hasattr(self.bot, 'voice_mod'):
                self.bot.voice_mod.MUTE_DURATION = seconds
            
            await ctx.send(f"✅ Длительность мута установлена на {seconds} сек")
            print(f"🔹 Длительность мута изменена на {seconds} сек по команде от {ctx.author}")
        except (IndexError, ValueError):
            await ctx.send("❌ Использование: `!set_duration <секунды>`")

    async def cmd_set_calibration(self, ctx, args):
        # Устанавливает калибровку микрофона
        try:
            value = float(args[0])
            Config.DB_CALIBRATION = value
            
            # Применяем в аудиоанализаторе
            if hasattr(self.bot, 'audio_analyzer'):
                self.bot.audio_analyzer.calibration = value
            
            await ctx.send(f"✅ Калибровка микрофона установлена на {value} dB")
            print(f"🔹 Калибровка изменена на {value} dB по команде от {ctx.author}")
        except (IndexError, ValueError):
            await ctx.send("❌ Использование: `!set_calibration <значение>`")

    async def cmd_join(self, ctx, args):
        # Подключает бота к голосовому каналу
        target_channel = None
        
        if args:
            try:
                channel_id = int(args[0])
                target_channel = self.bot.get_channel(channel_id)
                if not target_channel or not isinstance(target_channel, discord.VoiceChannel):
                    await ctx.send("❌ Неверный ID голосового канала")
                    return
            except ValueError:
                await ctx.send("❌ Неверный формат ID канала. Пример: `!join 123456789`")
                return
        else:
            if not ctx.author.voice or not ctx.author.voice.channel:
                await ctx.send("❌ Вы не в голосовом канале. Укажите ID канала или зайдите в канал")
                return
            target_channel = ctx.author.voice.channel
            
        if self.voice_client and self.voice_client.is_connected():
            if self.voice_client.channel == target_channel:
                await ctx.send("ℹ️ Бот уже в этом канале")
                return
            await self.voice_client.move_to(target_channel)
            await ctx.send(f"✅ Перемещён в {target_channel.name}")
            return
            
        self.voice_client = await target_channel.connect()
        await ctx.send(f"✅ Подключился к {target_channel.name}")
        self.bot.loop.create_task(self.monitor_voice_activity())
        print(f"🔹 Подключение к голосовому каналу {target_channel.name}")

    async def cmd_leave(self, ctx, args):
        # Отключает бота от голосового канала
        if not self.voice_client or not self.voice_client.is_connected():
            await ctx.send("ℹ️ Бот не подключён к голосовому каналу")
            return

        await self.voice_client.disconnect()
        self.voice_client = None
        await ctx.send("✅ Бот отключён от голосового канала")
        print("🔹 Отключение от голосового канала")

    @commands.Cog.listener()
    async def on_message(self, message):
        # Обработчик сообщений для команд
        if message.author.bot or not message.content.startswith('!'):
            return

        parts = message.content.split()
        command = parts[0][1:].lower()
        args = parts[1:] if len(parts) > 1 else []

        await self.process_command(await self.bot.get_context(message), command, args)
        
# Мониторинг громкости ===
    async def monitor_voice_activity(self):
        # Мониторинг громкости пользователей
        while self.voice_client and self.voice_client.is_connected():
            try:
                current_time = datetime.now()
                
                # Обрабатываем автоматический мут за громкость
                for member in self.voice_client.channel.members:
                    if member.bot or member.voice.deaf or member.voice.mute:
                        continue
                    
                    await self.process_member_volume(member, current_time)
                
                await self.cleanup_inactive_users()
                await asyncio.sleep(self.CHECK_INTERVAL)
                
            except Exception as e:
                print(f"❌ Ошибка мониторинга: {e}")
                await asyncio.sleep(5)

    async def process_member_volume(self, member, current_time):
        # Обрабатывает громкость пользователя
        if member.id not in self.user_data:
            self.user_data[member.id] = {
                'analyzer': AudioAnalyzer(),
                'member': member,
                'last_update': current_time,
                'is_muted': False
            }
            self.user_data[member.id]['analyzer'].start()
        
        user = self.user_data[member.id]
        user['last_update'] = current_time
        
        volume = await self._calculate_volume(user)
        await self._check_volume_threshold(user, volume, current_time)

    async def _calculate_volume(self, user_data):
        # Расчёт громкости
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self.bot.executor,
            user_data['analyzer'].calculate_volume
        )

    async def _check_volume_threshold(self, user_data, volume, current_time):
        # Проверка превышения порога громкости
        if (volume > Config.MAX_DECIBEL and 
            not user_data['is_muted'] and 
            (user_data['member'].id not in self.last_mute_time or 
             (current_time - self.last_mute_time[user_data['member'].id]).total_seconds() > Config.MUTE_DURATION)):
            
            await self.apply_mute(user_data, volume)

    async def apply_mute(self, user_data, volume):
        # Применение мута
        try:
            member = user_data['member']
            await member.edit(mute=True)
            user_data['is_muted'] = True
            self.last_mute_time[member.id] = datetime.now()
            
            msg = f"⚠️ МУТ: {member.display_name} ({volume:.1f} dB > {Config.MAX_DECIBEL} dB)"
            print(msg)
            logging.info(msg)
            
            channel = self.bot.get_channel(Config.LOG_CHANNEL_ID)
            if channel:
                embed = discord.Embed(
                    title="🔊 Превышение громкости",
                    description=f"{member.mention} был заглушен",
                    color=discord.Color.red()
                )
                embed.add_field(name="Средняя громкость", value=f"{volume:.1f} dB")
                embed.add_field(name="Порог", value=f"{Config.MAX_DECIBEL} dB")
                await channel.send(embed=embed)

            self.mute_tasks[member.id] = self.bot.loop.create_task(
                self.remove_mute_after_delay(user_data))
            
        except Exception as e:
            error_msg = f"❌ Ошибка мута {user_data['member'].display_name}: {e}"
            print(error_msg)
            logging.error(error_msg)

    async def remove_mute_after_delay(self, user_data):
        # Снятие мута после задержки
        await asyncio.sleep(Config.MUTE_DURATION)
        try:
            member = user_data['member']
            await member.edit(mute=False)
            user_data['is_muted'] = False
            user_data['analyzer'].reset_history()
            
            msg = f"🔇 Снятие мута: {member.display_name}"
            print(msg)
            logging.info(msg)
        except Exception as e:
            error_msg = f"❌ Ошибка снятия мута {user_data['member'].display_name}: {e}"
            print(error_msg)
            logging.error(error_msg)
        finally:
            if member.id in self.mute_tasks:
                del self.mute_tasks[member.id]

    async def cleanup_inactive_users(self):
        # Очистка неактивных пользователей
        current_time = datetime.now()
        inactive_users = [
            uid for uid, data in self.user_data.items()
            if (current_time - data['last_update']) > timedelta(seconds=10)
            and not data['is_muted']
        ]
        
        for uid in inactive_users:
            if uid in self.mute_tasks:
                self.mute_tasks[uid].cancel()
                del self.mute_tasks[uid]
            
            self.user_data[uid]['analyzer'].stop()
            del self.user_data[uid]

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        # Обрабатывает изменения голосового состояния
        if member.bot:
            return
        
        # Обработка автоматического мута
        if before.channel and not after.channel:
            if member.id in self.user_data:
                if member.id in self.mute_tasks:
                    self.mute_tasks[member.id].cancel()
                    del self.mute_tasks[member.id]
                self.user_data[member.id]['analyzer'].stop()
                del self.user_data[member.id]

async def setup(bot):
    await bot.add_cog(VoiceMod(bot))