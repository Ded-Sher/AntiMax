import discord
from discord.ext import commands
from datetime import datetime, timedelta
import asyncio
import logging
from typing import Optional

class VoiceModeration(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.manual_mutes = {}  # {user_id: mute_info}
        self.mute_tasks = {}    # {user_id: task}
        self.locks = {}         # {user_id: lock} для управления потоками
        print("🔹 Модуль модерации голосовых каналов инициализирован")

    async def get_lock(self, user_id: int) -> asyncio.Lock:
        # Получаем или создаем lock для пользователя
        if user_id not in self.locks:
            self.locks[user_id] = asyncio.Lock()
        return self.locks[user_id]

    @commands.command()
    @commands.has_role('Генсек')
    async def mute(self, ctx, member: discord.Member, duration: Optional[int] = None):
        # Замьютить пользователя в текущем канале
        if not member.voice or not member.voice.channel:
            await ctx.send("❌ Пользователь не в голосовом канале", delete_after=5)
            return

        async with await self.get_lock(member.id):
            success = await self.mute_user_in_channel(member, member.voice.channel, duration, ctx.author)
            if success:
                await ctx.send(f"✅ {member.mention} замьючен в этом канале")
            else:
                await ctx.send("❌ Не удалось замьютить пользователя (проверьте права бота)", delete_after=10)

    @commands.command()
    @commands.has_role('Генсек')
    async def unmute(self, ctx, member: discord.Member):
        # Размьютить пользователя
        async with await self.get_lock(member.id):
            # Проверяем, был ли пользователь замьючен через систему
            if member.id not in self.manual_mutes:
                # Проверяем, есть ли технический мут
                if member.voice and member.voice.mute:
                    try:
                        await member.edit(mute=False)
                        await ctx.send(f"✅ {member.mention} размьючен (технический мут)")
                        return
                    except discord.Forbidden:
                        await ctx.send("❌ Нет прав для размута", delete_after=5)
                        return
                else:
                    await ctx.send(f"❌ Пользователь {member.mention} не был замьючен", delete_after=5)
                    return

            # Отменяем задачу авторазмута если есть
            if member.id in self.mute_tasks:
                self.mute_tasks[member.id].cancel()
                try:
                    await self.mute_tasks[member.id]  # Дожидаемся отмены
                except asyncio.CancelledError:
                    pass
                del self.mute_tasks[member.id]

            # Полностью очищаем информацию о муте для избежания повторного мута
            if member.id in self.manual_mutes:
                del self.manual_mutes[member.id]

            # Пытаемся снять мут
            try:
                await member.edit(mute=False)
                await ctx.send(f"✅ {member.mention} размьючен")
                print(f"🔊 Размучен: {member.display_name} (полное снятие)")
            except discord.Forbidden:
                await ctx.send("❌ Нет прав для размута", delete_after=5)
            except Exception as e:
                await ctx.send(f"❌ Ошибка при размуте: {str(e)}", delete_after=10)
                print(f"❌ Ошибка размута {member.display_name}: {e}")

    async def mute_user_in_channel(self, member: discord.Member, channel: discord.VoiceChannel, 
                                 duration: Optional[int], moderator: Optional[discord.Member]) -> bool:
        # Логика мута в конкретном канале
        # Если уже замьючен - сначала размьючим
        if member.id in self.manual_mutes:
            await self.unmute_user_completely(member)

        self.manual_mutes[member.id] = {
            'channel_id': channel.id,
            'moderator_id': moderator.id if moderator else None,
            'muted_at': datetime.now(),
            'duration': duration
        }

        try:
            if member.voice and member.voice.channel.id == channel.id:
                await member.edit(mute=True)
                print(f"🔇 Мут: {member.display_name} в {channel.name}")

            if duration:
                # Создаем задачу на авторазмут
                task = asyncio.create_task(self.auto_unmute_user(member, duration))
                self.mute_tasks[member.id] = task
                task.add_done_callback(lambda t: self._cleanup_task(member.id, t))

            return True
        except discord.Forbidden:
            print(f"❌ Нет прав для мута {member.display_name}")
            return False
        except Exception as e:
            print(f"❌ Ошибка при муте {member.display_name}: {e}")
            return False

    async def unmute_user_completely(self, member: discord.Member, 
                                   moderator: Optional[discord.Member] = None) -> bool:
        # Полное снятие мута
        if member.id not in self.manual_mutes:
            return False

        try:
            await member.edit(mute=False)
            print(f"🔊 Размучен: {member.display_name}")
            
            # Удаляем из ручных мутов
            del self.manual_mutes[member.id]
            
            # Очищаем задачу, если есть
            if member.id in self.mute_tasks:
                self.mute_tasks[member.id].cancel()
                del self.mute_tasks[member.id]
                
            return True
        except discord.Forbidden:
            print(f"❌ Нет прав для размута {member.display_name}")
            return False
        except Exception as e:
            print(f"❌ Ошибка при размуте {member.display_name}: {e}")
            return False
        
    async def auto_unmute_user(self, member: discord.Member, duration: int):
        # Автоматическое снятие мута
        try:
            await asyncio.sleep(duration)
            async with await self.get_lock(member.id):
                if member.id in self.manual_mutes:
                    await self.unmute_user_completely(member)
        except asyncio.CancelledError:
            pass  # Задача была отменена - это нормально
        except Exception as e:
            print(f"❌ Ошибка в auto_unmute_user для {member.display_name}: {e}")

    def _cleanup_task(self, user_id: int, task: asyncio.Task):
        # Очистка завершенных задач
        if user_id in self.mute_tasks and self.mute_tasks[user_id] == task:
            del self.mute_tasks[user_id]

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, 
                                  before: discord.VoiceState, 
                                  after: discord.VoiceState):
        # Обработка изменений голосового состояния
        if member.bot:
            return

        async with await self.get_lock(member.id):
            if member.id not in self.manual_mutes:
                return
                
            mute_info = self.manual_mutes[member.id]
            current_time = datetime.now().strftime("%H:%M:%S")
            
            # Пользователь вышел из голосового канала
            if before.channel and not after.channel:
                try:
                    was_muted = before.mute
                    await member.edit(mute=False)
                    if was_muted:
                        print(f"{current_time} | 🔊 {member.display_name} вышел из канала (мут временно снят)")
                except discord.Forbidden:
                    pass
                return
                
            # Пользователь вошёл в голосовой канал
            if not before.channel and after.channel:
                if after.channel.id == mute_info['channel_id']:
                    try:
                        if not member.voice.mute:
                            await member.edit(mute=True)
                            print(f"{current_time} | 🔇 {member.display_name} подключился к каналу (мут применён)")
                    except discord.Forbidden:
                        pass
                return
                
            # Пользователь сменил канал
            if before.channel and after.channel:
                # Перешёл из замьюченного канала в другой
                if before.channel.id == mute_info['channel_id'] and after.channel.id != mute_info['channel_id']:
                    try:
                        if before.mute:
                            await member.edit(mute=False)
                            print(f"{current_time} | 🔊 {member.display_name} покинул замьюченный канал")
                    except discord.Forbidden:
                        pass
                
                # Вернулся в замьюченный канал из другого
                elif after.channel.id == mute_info['channel_id'] and before.channel.id != mute_info['channel_id']:
                    try:
                        if not member.voice.mute:
                            await member.edit(mute=True)
                            print(f"{current_time} | 🔇 {member.display_name} вернулся в замьюченный канал")
                    except discord.Forbidden:
                        pass

    async def cog_unload(self):
        # Очистка при выгрузке модуля
        for task in self.mute_tasks.values():
            task.cancel()
        await asyncio.gather(*self.mute_tasks.values(), return_exceptions=True)

async def setup(bot):
    await bot.add_cog(VoiceModeration(bot))