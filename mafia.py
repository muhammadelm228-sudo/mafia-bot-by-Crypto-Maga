import os
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
import asyncio
import random

bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()

games = {}


class Game:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.players = []
        self.roles = {}
        self.dead_players = []
        self.phase = "waiting"
        self.votes = {}
        self.mafia_votes = {}
        self.doctor_save = None
        self.commissar_check = None
        self.creator_id = None

    def alive_players(self):
        return [p for p in self.players if p['id'] not in self.dead_players]

    def add_player(self, user_id, username):
        if user_id not in [p['id'] for p in self.players]:
            self.players.append({'id': user_id, 'username': username})
            return True
        return False

    def assign_roles(self):
        random.shuffle(self.players)

        mafia_count = max(1, len(self.players) // 4)

        roles_list = (
            ["Мафия"] * mafia_count +
            ["Доктор"] +
            ["Комиссар"] +
            ["Мирный"] * (len(self.players) - mafia_count - 2)
        )

        random.shuffle(roles_list)

        for player, role in zip(self.players, roles_list):
            self.roles[player['id']] = role

    def check_win(self):
        mafia = 0
        civilians = 0

        for player in self.alive_players():
            if self.roles[player['id']] == "Мафия":
                mafia += 1
            else:
                civilians += 1

        if mafia == 0:
            return "🏆 Мирные победили!"
        if mafia >= civilians:
            return "🏆 Мафия победила!"
        return None

@dp.message(Command("help"))
async def help_command(message: Message):
    text = (
        "🎮 Команды бота:\n\n"
        "/create — создать игру\n"
        "/join — присоединиться\n"
        "/startgame — начать игру\n"
        "/players — список игроков\n"
        "/alive — живые игроки\n"
        "/stop — остановить игру\n"
        "/rules — правила игры"
    )
    await message.answer(text)

@dp.message(Command("rules"))
async def rules_command(message: Message):
    text = (
        "📜 Правила Мафии:\n\n"
        "🎭 Есть роли:\n"
        "🔪 Мафия — убивает ночью\n"
        "💉 Доктор — спасает игрока\n"
        "🕵 Комиссар — проверяет роль\n"
        "👤 Мирные — ищут мафию\n\n"
        "🌙 Ночью действуют роли\n"
        "☀️ Днём голосование\n"
        "🏆 Побеждает команда, которая устранит противников"
    )
    await message.answer(text)


@dp.message(Command("players"))
async def players_list(message: Message):
    chat_id = message.chat.id

    if chat_id not in games:
        await message.answer("Нет активной игры.")
        return

    game = games[chat_id]

    text = "👥 Игроки:\n\n"
    for p in game.players:
        status = "💀" if p['id'] in game.dead_players else "🟢"
        text += f"{status} {p['username']}\n"

    await message.answer(text)

@dp.message(Command("alive"))
async def alive_list(message: Message):
    chat_id = message.chat.id

    if chat_id not in games:
        await message.answer("Нет активной игры.")
        return

    game = games[chat_id]
    alive = game.alive_players()

    text = "🟢 Живые игроки:\n\n"
    for p in alive:
        text += f"{p['username']}\n"

    await message.answer(text)



@dp.message(Command("create"))
async def create_game(message: Message):
    chat_id = message.chat.id

    if chat_id in games:
        await message.answer("Игра уже создана.")
        return

    game = Game(chat_id)
    game.creator_id = message.from_user.id
    games[chat_id] = game

    await message.answer("Игра создана! Напишите /join чтобы присоединиться.")



@dp.message(Command("join"))
async def join_game(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name

    if chat_id not in games:
        await message.answer("Сначала создайте игру.")
        return

    game = games[chat_id]

    if game.add_player(user_id, username):
        await message.answer(f"{username} присоединился к игре!")
    else:
        await message.answer("Вы уже в игре.")


@dp.message(Command("stop"))
async def stop_game(message: Message):
    chat_id = message.chat.id

    if chat_id not in games:
        await message.answer("Нет активной игры.")
        return

    game = games[chat_id]

    if message.from_user.id != game.creator_id:
        await message.answer("Только создатель может остановить игру.")
        return

    del games[chat_id]
    await message.answer("🛑 Игра остановлена.")

@dp.message(Command("startgame"))
async def start_game(message: Message):
    chat_id = message.chat.id

    if chat_id not in games:
        return

    game = games[chat_id]

    if message.from_user.id != game.creator_id:
        await message.answer("Только создатель может начать игру.")
        return

    if len(game.players) < 4:
        await message.answer("Минимум 4 игрока.")
        return

    game.assign_roles()

    await message.answer("Игра началась! 🌙 Наступает ночь...")

    for player in game.players:
        try:
            await bot.send_message(
                player['id'],
                f"Ваша роль: {game.roles[player['id']]}"
            )
        except:
            pass

    await start_night(game)


async def start_night(game):
    game.phase = "night"
    game.mafia_votes = {}
    game.doctor_save = None
    game.commissar_check = None

    alive = game.alive_players()

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=p['username'],
                callback_data=f"night_{p['id']}"
            )]
            for p in alive
        ]
    )

    for player in alive:
        role = game.roles[player['id']]

        if role == "Мафия":
            await bot.send_message(player['id'], "🔪 Выберите жертву:", reply_markup=keyboard)

        elif role == "Доктор":
            await bot.send_message(player['id'], "💉 Кого спасти?", reply_markup=keyboard)

        elif role == "Комиссар":
            await bot.send_message(player['id'], "🕵️ Кого проверить?", reply_markup=keyboard)


@dp.callback_query(F.data.startswith("night_"))
async def night_action(callback: CallbackQuery):
    target_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id

    for game in games.values():
        if user_id in game.roles and game.phase == "night":
            role = game.roles[user_id]

            if role == "Мафия":
                game.mafia_votes[user_id] = target_id

            elif role == "Доктор":
                game.doctor_save = target_id

            elif role == "Комиссар":
                game.commissar_check = target_id
                role_checked = game.roles[target_id]
                await bot.send_message(
                    user_id,
                    f"Роль игрока: {role_checked}"
                )

            await callback.answer("Действие принято")
            await check_night_end(game)
            break


async def check_night_end(game):
    mafia_alive = [
        p for p in game.alive_players()
        if game.roles[p['id']] == "Мафия"
    ]

    doctor_alive = any(
        game.roles[p['id']] == "Доктор"
        for p in game.alive_players()
    )

    commissar_alive = any(
        game.roles[p['id']] == "Комиссар"
        for p in game.alive_players()
    )

    mafia_done = len(game.mafia_votes) == len(mafia_alive)
    doctor_done = (not doctor_alive) or game.doctor_save is not None
    commissar_done = (not commissar_alive) or game.commissar_check is not None

    if mafia_done and doctor_done and commissar_done:

        votes = list(game.mafia_votes.values())
        victim = max(set(votes), key=votes.count)

        if victim != game.doctor_save:
            game.dead_players.append(victim)
            await bot.send_message(game.chat_id, "🌙 Ночью игрок был убит.")
        else:
            await bot.send_message(game.chat_id, "💉 Доктор спас игрока!")

        winner = game.check_win()
        if winner:
            await bot.send_message(game.chat_id, winner)
            del games[game.chat_id]
        else:
            await start_day(game)



async def start_day(game):
    game.phase = "day"
    game.votes = {}

    alive = game.alive_players()

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=p['username'],
                callback_data=f"vote_{p['id']}"
            )]
            for p in alive
        ]
    )

    await bot.send_message(
        game.chat_id,
        "☀️ День. Голосование:",
        reply_markup=keyboard
    )


@dp.callback_query(F.data.startswith("vote_"))
async def vote(callback: CallbackQuery):
    target_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id

    for game in games.values():
        if game.phase == "day":
            if user_id in [p['id'] for p in game.alive_players()]:
                game.votes[user_id] = target_id
                await callback.answer("Вы проголосовали")

                if len(game.votes) == len(game.alive_players()):
                    votes = list(game.votes.values())
                    victim = max(set(votes), key=votes.count)

                    game.dead_players.append(victim)

                    await bot.send_message(
                        game.chat_id,
                        "🗳 Игрок изгнан."
                    )

                    winner = game.check_win()
                    if winner:
                        await bot.send_message(game.chat_id, winner)
                        del games[game.chat_id]
                    else:
                        await start_night(game)
                break


async def main():
    print("Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
