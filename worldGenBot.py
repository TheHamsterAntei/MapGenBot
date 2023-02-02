import asyncio
import numpy as np
import os
from scipy.ndimage import gaussian_filter
import telegram
import time
from PIL import Image, ImageDraw


user_dict = {}

greeting_keyboard = telegram.ReplyKeyboardMarkup([
    [telegram.KeyboardButton("Конечно, присылайте!")],
    [telegram.KeyboardButton("Не нужно новостей")]
], resize_keyboard=True)

main_keyboard = telegram.ReplyKeyboardMarkup([
    [telegram.KeyboardButton("Создать карту!")],
    [telegram.KeyboardButton("Помощь"),
     telegram.KeyboardButton("Настройки")]
], resize_keyboard=True)


#test_img = Image.open("Maps/Output.png").convert('RGB')


class User:
    def __init__(self, userid, worlds=0, balance=5, notifications=True, stage=0):
        self.id = userid
        self.worlds = worlds
        self.balance = balance
        self.notifications = notifications
        self.stage = stage
        self.last_time = [time.time() for i in range(0, 5)]

        self.map = None


class Event:
    def __init__(self, message, action=lambda x: x):
        self.message = message
        self.action = action

    async def do(self, *args):
        return await self.action(*args)


class World:
    def __init__(self, userid, width=800, height=600):
        self.id = userid
        self.width = width
        self.height = height

        self.type = "Undefined"
        self.smoothing = 5
        self.sharpness = "Moderate"

        self.ready = False

    async def generate(self):
        detail_arrays = dict()
        h = 0.06
        detail_arrays[1] = np.random.rand(self.width, self.height) * 0.3
        detail_arrays[7] = np.random.rand(
            int(np.ceil(self.width / 7)),
            int(np.ceil(self.height / 7))
        ) * 0.3
        detail_arrays[23] = np.random.rand(
            int(np.ceil(self.width / 23)),
            int(np.ceil(self.height / 23))
        ) * 0.15
        detail_arrays[100] = np.random.rand(
            int(np.ceil(self.width / 100)),
            int(np.ceil(self.height / 100))
        ) * 0.15
        vals = {
            1: 0.8,
            7: 1.2,
            23: 4.0,
            100: 6.0
        }

        #Первичное сглаживание
        for key in detail_arrays.keys():
            detail_arrays[key] = gaussian_filter(detail_arrays[key], sigma=(vals[key]), mode="constant")

        result_array = np.full((self.width, self.height), 0.0)
        for y in range(0, self.height):
            for x in range(0, self.width):
                result_array[x][y] = (detail_arrays[1][x][y] +
                                      detail_arrays[7][x // 7][y // 7] +
                                      detail_arrays[23][x // 23][y // 23] +
                                      detail_arrays[100][x // 100][y // 100] + h)
                result_array[x][y] = self.calculate_sharpness(
                    value=result_array[x][y],
                    level=0.45,
                    power=5.0
                )

        #Сглаживание
        result_array = gaussian_filter(result_array, sigma=1.2, mode="constant")

        #Раскрашивание
        result_array *= 255

        result_image = Image.new('RGB', (self.width, self.height), (0, 0, 0))
        for y in range(0, self.height):
            for x in range(0, self.width):
                h = result_array[x][y]
                red = 0
                green = 0
                blue = 0
                bright = 0
                if h <= 140.0:
                    red = 30
                    green = 50
                    blue = 230
                    bright = 0.4 + 0.6 * (h / 140)
                if 140.0 < h <= 180.0:
                    red = 50
                    green = 240
                    blue = 20
                    bright = 0.6 + 0.4 * ((h - 140.0) / 40.0)
                if 180.0 < h <= 220.0:
                    red = 160
                    green = 90
                    blue = 10
                    bright = 0.7 + 0.3 * ((h - 180.0) / 40.0)
                if 220.0 < h:
                    red = 240
                    green = 240
                    blue = 240
                    bright = 1.0
                result_image.putpixel((x, y), (int(red * bright), int(green * bright), int(blue * bright)))
        result_image.save("Maps/" + str(self.id) + '.png', 'PNG')
        self.ready = True

    def calculate_sharpness(self, value, level, power):
        mod = 1.0
        if value < level:
            mod = -1.0
        val = min(0.5, abs(value - 0.5) ** (1 / (1 + 0.2 * power))) * mod + 0.5
        return val

    def distance(self, x1, y1, x2, y2):
        return np.sqrt((x2 - x1)**2 + (y2 - y1)**2)


class Bot:
    def __init__(self, token):
        self.token = token
        self.bot = telegram.Bot(token=self.token)

        self.updates = None
        self.triggers = {}

    async def check_for_updates(self):
        num = 0
        save_timer = time.time()
        while True:
            try:
                self.updates = await self.bot.get_updates(offset=num, allowed_updates=["message"], read_timeout=1)
            except telegram.error.TimedOut:
                self.updates = list()
            if time.time() - save_timer > 300:
                asyncio.create_task(save_data())
                save_timer = time.time()
            if len(self.updates) > 0:
                num = self.updates[len(self.updates) - 1].update_id + 1
                for i in self.updates:
                    if i.message:
                        text = i.message.text
                        user = i.message.from_user.id

                        if user not in user_dict.keys():
                            user_dict[user] = User(user)

                        if text in self.triggers.keys():
                            asyncio.create_task(self.triggers[text].do(self.bot, user))

                        if len(text) > 7:
                            if text[1:6] == 'send ' and user == 352422311:
                                asyncio.create_task(self.mass_sending(text[6:]))

            else:
                await asyncio.sleep(1)

    async def push_event(self, event: Event):
        self.triggers[event.message] = event

    async def mass_sending(self, message):
        for i in user_dict.keys():
            if user_dict[i].notifications:
                await self.bot.sendMessage(i, message)


async def save_data():
    temp = open('Data/Temp.save', 'w')
    for i in user_dict.keys():
        temp.write(
            str(i) + '\t' +
            str(user_dict[i].worlds) + '\t' +
            str(user_dict[i].balance) + '\t' +
            str(1 if user_dict[i].notifications else 0) + '\t' +
            str(user_dict[i].stage) + '\n'
        )
    temp.close()
    os.remove("Data/Users.save")
    os.rename("Data/Temp.save", "Data/Users.save")


async def bot_incorrect(bot: telegram.Bot, user):
    await bot.sendMessage(user, "Выглядит так, будто вы пытаетесь использовать стороннюю команду во время задания" +
                          " настроек мира. Пожалуйста, попробуйте ввести команду /reset, чтобы вернуться в меню")


async def bot_reset(bot: telegram.Bot, user):
    if user_dict[user].stage != 0:
        user_dict[user].stage = 1
        await bot.sendMessage(user, "Вы успешно вернулись в меню!", reply_markup=main_keyboard)
    else:
        await bot.sendMessage(user, "Мы разве знакомы, чтобы что-то сбрасывать?", reply_markup=greeting_keyboard)


async def bot_greeting(bot: telegram.Bot, user):
    if user_dict[user].stage != 0:
        await bot.sendMessage(user, "Разве мы ещё не знакомы? Если Вы вдруг удалили бота, а теперь вернулись — всё " +
                              "хорошо! Я никого не забыл, все настройки сохранены!\n\n" +
                              "P.s. в случае каких-то багов и иных затруднений, воспользуйтесь командой /reset для " +
                              "вызова главного меню")
        return
    await bot.sendMessage(user, "Добро пожаловать!\n" +
                          "Хотите ли Вы видеть новости об обновлениях данного бота (их можно будет отключить позднее" +
                          " в настройках)?",
                          reply_markup=greeting_keyboard)


async def bot_notification_enabled(bot: telegram.Bot, user):
    if user_dict[user].stage == 0:
        user_dict[user].stage = 1
        user_dict[user].notifications = True
    else:
        if user_dict[user].stage != 1:
            await bot_incorrect(bot, user)
            return
        await bot.sendMessage(user, "Я-то включу уведомления, но лучше и быстрее было бы воспользоваться кнопкой в " +
                              "настройках!",
                              reply_markup=main_keyboard)
        user_dict[user].notifications = True
        return
    await bot.sendMessage(user, "Что ж, я рад, что Вам хочется узнавать о новостях!\n" +
                          "А теперь к тому, для чего предназначен бот: генерация карт. На данный момент это ну очень " +
                          "ранняя альфа, но его функционал можно оценить по генерации островов. В дальнейшем настроек" +
                          " и возможностей станет больше: континенты, влажность, температура, плоские и шарообразные" +
                          " миры." +
                          " Есть даже мысли, как настроить генерацию городов и государств. В общем, дерзайте. В сыром" +
                          " виде карты использовать, скорее всего, не выйдет. Но как фундамент для более красивой " +
                          "карты очень даже сгодятся, ибо по своему опыту знаю, что выдумывать приятные глазу и " +
                          "разноообразные береговые линии сложновато. Удачи!",
                          reply_markup=main_keyboard)


async def bot_notification_disabled(bot: telegram.Bot, user):
    if user_dict[user].stage == 0:
        user_dict[user].stage = 1
        user_dict[user].notifications = False
    else:
        if user_dict[user].stage != 1:
            await bot_incorrect(bot, user)
            return
        await bot.sendMessage(user, "Я-то выключу уведомления, но лучше и быстрее было бы воспользоваться кнопкой в " +
                              "настройках!",
                              reply_markup=main_keyboard)
        user_dict[user].notifications = False
        return
    await bot.sendMessage(user, "Заставить не могу. В случае чего, всегда можно подключить новости в настройках!\n" +
                          "А теперь к тому, для чего предназначен бот: генерация карт. На данный момент это ну очень " +
                          "ранняя альфа, но его функционал можно оценить по генерации островов. В дальнейшем настроек" +
                          " и возможностей станет больше: континенты, влажность, температура, плоские и шарообразные" +
                          " миры." +
                          " Есть даже мысли, как настроить генерацию городов и государств. В общем, дерзайте. В сыром" +
                          " виде карты использовать, скорее всего, не выйдет. Но как фундамент для более красивой " +
                          "карты очень даже сгодятся, ибо по своему опыту знаю, что выдумывать приятные глазу и " +
                          "разноообразные береговые линии сложновато. Удачи!",
                          reply_markup=main_keyboard)


async def bot_help(bot: telegram.Bot, user):
    await bot.sendMessage(user, "Текущая версия: 1-Альфа\n\n" +
                          "Команды:\n" +
                          "/reset — вернуться в основное меню\n" +
                          "/help — получить информацию о командах\n" +
                          "/settings — войти в меню настроек (работает только из основного меню)")


async def bot_settings(bot: telegram.Bot, user):
    if user_dict[user].stage == 1 or user_dict[user].stage == 99:
        user_dict[user].stage = 99
        if user_dict[user].notifications:
            notification_button = "Выключить уведомления"
        else:
            notification_button = "Включить уведомления"
        settings_keyboard = telegram.ReplyKeyboardMarkup([
            [telegram.KeyboardButton(notification_button)],
            [telegram.KeyboardButton("Назад")]
        ], resize_keyboard=True)
        await bot.sendMessage(user, "Настройки...", reply_markup=settings_keyboard)
    else:
        await bot_incorrect(bot, user)


async def bot_settings_notifications(bot: telegram.Bot, user):
    if user_dict[user].stage == 99:
        if user_dict[user].notifications:
            notification_button = "Включить уведомления"
        else:
            notification_button = "Выключить уведомления"
        settings_keyboard = telegram.ReplyKeyboardMarkup([
            [telegram.KeyboardButton(notification_button)],
            [telegram.KeyboardButton("Назад")]
        ], resize_keyboard=True)
        if user_dict[user].notifications:
            user_dict[user].notifications = False
            await bot.sendMessage(user, "Уведомления выключены!", reply_markup=settings_keyboard)
        else:
            user_dict[user].notifications = True
            await bot.sendMessage(user, "Уведомления включены!", reply_markup=settings_keyboard)
    else:
        await bot_incorrect(bot, user)


async def bot_back(bot: telegram.Bot, user):
    if user_dict[user].stage == 99:
        user_dict[user].stage = 1
        await bot.sendMessage(user, "Возврат в меню...", reply_markup=main_keyboard)
        return
    await bot_incorrect(bot, user)


async def bot_create_map(bot: telegram.Bot, user):
    if user_dict[user].stage == 1:
        #Проверка баланса
        if user_dict[user].balance < user_dict[user].worlds + 5:
            user_dict[user].last_time.sort()
            for i in range(0, len(user_dict[user].last_time)):
                if time.time() - user_dict[user].last_time[i] > 3600:
                    user_dict[user].balance += 1
                else:
                    break
                if user_dict[user].balance >= user_dict[user].worlds + 5:
                    break
        if user_dict[user].balance <= user_dict[user].worlds:
            await bot.sendMessage(user, "Невозможно создать карту! Баланс меньше нуля!")
            return
        #Создание карты
        user_dict[user].stage = 2
        gen_map = World(user)
        user_dict[user].map = gen_map
        await bot.sendMessage(user, "Создание карты...")
        asyncio.create_task(gen_map.generate())
        while not gen_map.ready:
            await asyncio.sleep(1)
        img_send = open("Maps/" + str(user) + ".png", 'rb')
        await bot.sendPhoto(user, img_send)
        img_send.close()
        user_dict[user].stage = 1
        user_dict[user].worlds += 1
        user_dict[user].last_time.sort()
        user_dict[user].last_time[0] = time.time()
        await bot.sendMessage(user, "Создано карт: " + str(user_dict[user].worlds) + '\n' +
                              "Баланс: " + str(user_dict[user].balance - user_dict[user].worlds) + ' карт\n' +
                              "Баланс восполняется в течение часа!")
        return
    await bot_incorrect(bot, user)


async def main():
    bot = Bot("TOKEN")
    asyncio.create_task(bot.push_event(
        Event(
            message="/start",
            action=bot_greeting
        )
    ))
    asyncio.create_task(bot.push_event(
        Event(
            message="Конечно, присылайте!",
            action=bot_notification_enabled
        )
    ))
    asyncio.create_task(bot.push_event(
        Event(
            message="Не нужно новостей",
            action=bot_notification_disabled
        )
    ))
    asyncio.create_task(bot.push_event(
        Event(
            message="/reset",
            action=bot_reset
        )
    ))
    asyncio.create_task(bot.push_event(
        Event(
            message="/help",
            action=bot_help
        )
    ))
    asyncio.create_task(bot.push_event(
        Event(
            message="/settings",
            action=bot_settings
        )
    ))
    asyncio.create_task(bot.push_event(
        Event(
            message="Помощь",
            action=bot_help
        )
    ))
    asyncio.create_task(bot.push_event(
        Event(
            message="Настройки",
            action=bot_settings
        )
    ))
    asyncio.create_task(bot.push_event(
        Event(
            message="Включить уведомления",
            action=bot_settings_notifications
        )
    ))
    asyncio.create_task(bot.push_event(
        Event(
            message="Выключить уведомления",
            action=bot_settings_notifications
        )
    ))
    asyncio.create_task(bot.push_event(
        Event(
            message="Назад",
            action=bot_back
        )
    ))

    #Создание карты
    asyncio.create_task(bot.push_event(
        Event(
            message="Создать карту!",
            action=bot_create_map
        )
    ))
    await bot.check_for_updates()


if __name__ == "__main__":
    if not os.path.exists('Data/'):
        os.mkdir('Data')
    if not os.path.exists('Maps/'):
        os.mkdir('Maps')
    if not os.path.exists('Data/Users.save'):
        save = open('Data/Users.save', 'w')
        save.close()
    else:
        save = open('Data/Users.save', 'r')
        for line in save:
            data = line.split('\t')
            if len(data) < 5:
                continue
            else:
                user_dict[int(data[0])] = User(int(data[0]),
                                               worlds=int(data[1]),
                                               balance=int(data[2]),
                                               notifications=bool(int(data[3])),
                                               stage=int(data[4]))
        save.close()
    asyncio.run(main())
