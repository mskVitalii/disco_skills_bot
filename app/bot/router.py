from aiogram import Router

from app.bot.handlers import callbacks, commands, messages

main_router = Router(name="main")
main_router.include_router(commands.router)
main_router.include_router(callbacks.router)
main_router.include_router(messages.router)
