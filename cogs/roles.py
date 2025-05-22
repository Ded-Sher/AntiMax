import discord
from discord.ext import commands
from config import Config
from datetime import datetime, timedelta
import logging
from utils.antispam import AntiFlood
from functools import lru_cache

class Roles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.antiflood = AntiFlood()
        print("🔹 Модуль ролей инициализирован")
        
    @lru_cache(maxsize=100)
    def get_role(self, guild, role_id):
        return guild.get_role(role_id)
        
    async def validate_request(self, payload):
        if payload.message_id != Config.POST_ID:
            return False
        if payload.channel_id != Config.ALLOWED_CHANNEL_ID:
            return False
        if await self.antiflood.check_flood(payload.user_id):
            return False
        return True
    
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        await self.process_role_change(payload, add_role=True)
    
    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        await self.process_role_change(payload, add_role=False)
    
    async def process_role_change(self, payload, add_role=True):
        if not await self.validate_request(payload):
            return
        
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            print("❌ Сервер не найден")
            return
            
        member = guild.get_member(payload.user_id)
        if not member:
            print("❌ Участник не найден")
            return
        if member.bot:
            print("⚠️ Реакция от бота - игнорируем")
            return
            
        emoji = str(payload.emoji)
        if emoji not in Config.ROLES:
            print("❌ Эмодзи не привязан к роли")
            return
            
        role = self.get_role(guild, Config.ROLES[emoji])
        if not role:
            print(f"❌ Роль для эмодзи {emoji} не найдена")
            return
            
        try:
            current_roles = {r.id for r in member.roles if r.id not in Config.EXCROLES}
            
            if add_role:
                if len(current_roles) >= Config.MAX_ROLES_PER_USER:
                    msg = f"⚠️ Лимит ролей ({Config.MAX_ROLES_PER_USER}) достигнут"
                    print(msg)
                    await member.send(msg)
                    return
                if role.id not in current_roles:
                    await member.add_roles(role)
                    log_msg = f"✅ Выдана роль {role.name} пользователю {member.display_name}"
                    print(log_msg)
                    logging.info(log_msg)
            else:
                if role.id in current_roles:
                    await member.remove_roles(role)
                    log_msg = f"❌ Удалена роль {role.name} у {member.display_name}"
                    print(log_msg)
                    logging.info(log_msg)
                    
        except discord.Forbidden:
            error_msg = "❌ Недостаточно прав для управления ролями"
            print(error_msg)
            logging.error(error_msg)
            await guild.owner.send('⚠️ Боту не хватает прав для управления ролями!')
        except discord.HTTPException as e:
            error_msg = f"❌ Ошибка обновления ролей: {e}"
            print(error_msg)
            logging.error(error_msg)

async def setup(bot):
    await bot.add_cog(Roles(bot))