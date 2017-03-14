import random
from collections import OrderedDict
import logging
from datetime import datetime as dt
import os
import sys
import functools
from utils import get_alias_match
from threading import Thread
from itertools import zip_longest
from telegram import ReplyKeyboardMarkup, ParseMode, ReplyKeyboardRemove
from telegram.ext import Updater, CommandHandler, RegexHandler, MessageHandler, Filters, ConversationHandler
from telegram.contrib.botan import Botan
from config import ALLTESTS, BOTAN_TOKEN, LEGAL, ADMINS, OLEG
from pyexcel_xlsx import get_data, save_data
from model import save, Users, \
    UndefinedRequests, Company, Good, Service, Aliases, DoesNotExist, fn, \
    before_request_handler, after_request_handler, Passwords


start_msg = '''Вас приветствует автоматический помощник для персонала магазинов, позволяющий оперативно решать юридические вопросы.

Например, чтобы проверить, входит ли товар в тот или иной перечень (есть ли для товара специальные условия возврата или обмена), введите его название, например "утюг", "телевизор", "планшет" и т.п.

Помощник позволит получить информацию по общим вопросам ("срок ремонта", "проверка качества", "возврат товара" и т.п.), ознакомиться с установленными перечнями товаров ("перечень технически сложных товаров", "перечень товаров надлежащего качества, не подлежащих возврату или обмену"), получить последнюю редакцию закона о защите прав потребителей или правил торговли ("закон о защите прав потребителей", "правила торговли").

В случае проверки помощник проинформирует о порядке действий ("проверка", "ход проверки", "ответы проверяющим" и т.п.) и предоставит контакты уполномоченных лиц ("служба безопасности").

Если интересующей информации нет в базе, операторы получат Ваш запрос и внесут необходимые сведения.

Помощник может быть запущен в браузере на компьютере (https://web.telegram.org/) или через приложение для компьютера (https://desktop.telegram.org/).'''


ASK_PASS, APPROVE = range(2)
SECOND, THIRD, FORTH = range(3)

dbs = {'Компания': Company,
       'Услуга': Service,
       'Товар': Good,
       'Алиасы': Aliases}

SEARCH = 1
user_data = dict()

botan = Botan(BOTAN_TOKEN)

search_fckup_msg = '''Информация по Вашему запросу пока отсутствует в базе. Операторы добавят необходимые сведения в течение 24 часов.

Чтобы проверить, входит ли товар в тот или иной перечень (есть ли для товара специальные условия возврата или обмена), введите его название, например "утюг", "телевизор", "планшет" и т.п.

Помощник позволяет получить информацию по общим вопросам ("срок ремонта", "проверка качества", "возврат товара" и т.п.), ознакомиться с установленными перечнями товаров ("перечень технически сложных товаров", "перечень товаров надлежащего качества, не подлежащих возврату или обмену"), получить последнюю редакцию закона о защите прав потребителей или правил торговли ("закон о защите прав потребителей", "правила торговли").

В случае проверки помощник информирует о порядке действий ("проверка", "ход проверки", "ответы проверяющим" и т.п.) и предоставляет контакты уполномоченных лиц ("служба безопасности").'''


def generate_password():
    s = 'abcdefghijklmnopqrstuvwxyz01234567890ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    passlen = 8
    return ''.join(random.sample(s, passlen))


def unknown_req_add(tid, txt):
    before_request_handler()
    try:
        UndefinedRequests.get(fn.lower(UndefinedRequests.request) == txt.lower())
        UndefinedRequests.create(from_user=tid, request=txt)
    except DoesNotExist:
        UndefinedRequests.create(from_user=tid, request=txt)
        after_request_handler()
    return True


def get_reply_keyboard(uid):
    if uid in ADMINS:
        k_clients = [['Выгрузка'], ['Сгенерировать пароль'], ['Отправить всем']]
        return ReplyKeyboardMarkup(k_clients, resize_keyboard=True)
    return ReplyKeyboardRemove()



def check_password(func):
    @functools.wraps(func)
    def decorator(*args, **kwargs):
        bot, update = args
        uid = update.message.from_user.id
        message = update.message.text
        username = update.message.from_user.username
        name = update.message.from_user.first_name
        before_request_handler()
        active_pass = Passwords.get(Passwords.active == 1).password
        user, created = Users.get_or_create(telegram_id=uid, username=username, name=name)
        if created:
            bot.sendMessage(uid, 'Введите пароль')
        elif user.current_password == active_pass:
            result = func(*args, **kwargs)
            return result
        elif user.current_password != active_pass:
            try:
                Passwords.get(Passwords.password == message, Passwords.active == 1)
                user.current_password = message
                user.save()
                bot.sendMessage(uid, 'Пароль обновлен')
            except:
                bot.sendMessage(uid, 'Ваш пароль неправильный, введите новый')
        else:
            bot.sendMessage(uid, 'Пароль неправильный, попробуйте еще раз')

        after_request_handler()
    return decorator


def make_search(message):
    res = []
    try:
        check_aliases = get_alias_match(message)
        alias = [c.key for c in check_aliases]
        if alias:
            message = alias[0]
    except DoesNotExist:
        pass

    for model in dbs.values():
        if model == Aliases:
            continue
        before_request_handler()
        try:
            search = model.get(fn.lower(model.name) == message.lower())
            res.append(search)
        except DoesNotExist:
            pass
        after_request_handler()
    return res


@check_password
def start(bot, update):
    print(update)
    uid = update.message.from_user.id
    bot.sendMessage(uid, start_msg, 
                    reply_markup=get_reply_keyboard(uid),
                    disable_web_page_preview=True)


@check_password
def search_wo_cat(bot, update):
    print(update)
    uid = update.message.from_user.id
    message = update.message.text.strip('"\'!?[]{},. ').lower()
    msg = ''
    res = make_search(message)
    if not res:
        unknown_req_add(uid, message.strip('"\'!?[]{},. '))
        bot.sendMessage(uid, search_fckup_msg,
                        disable_web_page_preview=True,
                        reply_markup=get_reply_keyboard(uid))
        bot.sendMessage(OLEG, 'Новый поиск!\n\n' + message)
        return
    for m in res:
        msg += '<b>{}</b>\n{}\n{}\n\n'.format(m.name, m.description, m.url)
    bot.sendMessage(uid, msg, parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                    reply_markup=get_reply_keyboard(uid))
    botan.track(update.message, event_name='search_wo_cat')


def process_file(bot, update):
    uid = update.message.from_user.id
    if uid in ADMINS:
        file_id = update.message.document.file_id
        fname = update.message.document.file_name
        newFile = bot.getFile(file_id)
        newFile.download(fname)
        sheets = get_data(fname)
        columns = ('name', 'description', 'url')
        for sheet in sheets:
            if sheet.lower() == 'алиасы':
                columns = ['key'] + ['alias' + str(i) for i in range(1, 101)]
            _data = []
            for row in sheets[sheet][1:]:
                if not row:
                    continue
                _data.append(dict(zip_longest(columns, [r.strip('"\'!?[]{},. \n') for r in row], fillvalue='')))
            if save(_data, dbs[sheet]):
                bot.sendMessage(uid, 'Данные на странице {} сохранил'.format(sheet), disable_notification=1)
            else:
                bot.sendMessage(uid, 'Что-то не так с данными')
        os.remove(fname)
        data = [u for u in UndefinedRequests.select(UndefinedRequests.id,
                                                    UndefinedRequests.from_user,
                                                    UndefinedRequests.request).where(UndefinedRequests.is_answered == 0).execute()]
        for d in data:
            _id = d.id
            tid = d.from_user.telegram_id
            request = d.request
            msg = ''
            res = make_search(request)
            if res:
                UndefinedRequests.update(is_answered=True).where(UndefinedRequests.id == _id).execute()
                for m in res:
                    msg += '<b>{}</b>\n{}\n{}\n\n'.format(m.name, m.description, m.url)
                bot.sendMessage(tid, msg, parse_mode=ParseMode.HTML,
                                disable_web_page_preview=True,
                                reply_markup=get_reply_keyboard(tid))
        bot.sendMessage(uid, 'Обновления пользователям отправил')


def output(bot, update):
    print(update)
    uid = update.message.from_user.id
    if uid not in ADMINS:
        return
    foud = OrderedDict()
    before_request_handler()
    res = UndefinedRequests.select(UndefinedRequests.request, fn.COUNT(UndefinedRequests.id).alias('count')).\
        group_by(UndefinedRequests.request).execute()
    after_request_handler()
    foud.update({'Отсутствия в базе': [(r.request, r.count) for r in res]})
    fname = str(dt.now()) + '.xlsx'
    save_data(fname, foud)
    bot.sendDocument(uid, document=open(fname, 'rb'))
    os.remove(fname)


def get_new_password(bot, update):
    uid = update.message.from_user.id
    r_keyboard = [['Да'], ['Нет']]
    if not user_data.get(uid):
        user_data[uid] = {}
    if uid in ADMINS:
        before_request_handler()
        while True:
            new_password = generate_password()
            user_data[uid]['current_pass'] = new_password
            password, create = Passwords.get_or_create(password=new_password)
            if create:
                bot.sendMessage(uid, 'Новый пароль: <b>{}</b>\nМеняем?'.format(new_password),
                                parse_mode=ParseMode.HTML,
                                reply_markup=ReplyKeyboardMarkup(r_keyboard, resize_keyboard=True))
                after_request_handler()
                return APPROVE


def approve(bot, update):
    uid = update.message.from_user.id
    message = update.message.text
    cur_pass = user_data[uid]['current_pass']
    if message == 'Да':
        query = Passwords.update(active=False).where(Passwords.password != cur_pass)
        query.execute()
        bot.sendMessage(uid, 'Пароль изменил')
    elif message == 'Нет':
        q = Passwords.delete().where(Passwords.password == cur_pass)
        q.execute()
        bot.sendMessage(uid, 'Пароль не менял')
    bot.sendMessage(uid, 'Ответь на вопрос :)')


def start_sendtoall(bot, update):
    uid = update.message.from_user.id
    if uid not in ADMINS:
        return ConversationHandler.END
    bot.sendMessage(uid, 'Что будем отправлять?', reply_markup=ReplyKeyboardRemove())
    return SECOND


def get_text_to_send(bot, update):
    uid = update.message.from_user.id
    message = update.message.text
    user_data[uid] = {'text_to_send': message}
    bot.sendMessage(uid, 'Отправляем?', reply_markup=ReplyKeyboardMarkup([['Да'], ['Нет']], one_time_keyboard=True))
    return THIRD


def mails(bot, text, reply_uid):
    uids = [t.telegram_id for t in Users.select().execute()]
    for uid in uids:
        try:
            bot.sendMessage(uid, text)
        except:
            pass
    bot.sendMessage(reply_uid, 'Всем отправил')


def start_send(bot, update):
    uid = update.message.from_user.id
    message = update.message.text
    text = user_data[uid].get('text_to_send')
    if message == 'Да':
        t = Thread(target=mails, args=(bot, text, uid), name='mails')
        t.start()
        bot.sendMessage(uid, 'Начал отправку',
                        reply_markup=get_reply_keyboard(uid))
    elif message == 'Нет':
        del user_data[uid]
        bot.sendMessage(uid, 'Ок, не будет ничего отправлять :)',
                        reply_markup=get_reply_keyboard(uid))
        return ConversationHandler.END
    else:
        return


def clear(bot, update):
    uid = update.message.from_user.id
    if uid not in ADMINS:
        return
    if UndefinedRequests.table_exists():
        UndefinedRequests.drop_table()
    UndefinedRequests.create_table()
    bot.send_message(uid, 'Таблицу очистил', reply_markup=get_reply_keyboard(uid))
 
if __name__ == '__main__':
    updater = None
    token = None
    if len(sys.argv) > 1:
        token = sys.argv[-1]
        if token.lower() == 'legal':
            updater = Updater(LEGAL)
            BASE_DIR = os.path.dirname(os.path.abspath(__file__))
            logging.basicConfig(filename=BASE_DIR + '/out.log',
                                filemode='a',
                                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                                level=logging.INFO)
    else:
        updater = Updater(ALLTESTS)
        logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG)

    dp = updater.dispatcher
    dp.add_handler(CommandHandler('unload', output))
    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(CommandHandler('clear', clear))
    dp.add_handler(RegexHandler('^Выгрузка$', output))
    pass_change = ConversationHandler(
        entry_points=[RegexHandler('^Сгенерировать пароль$', get_new_password)],
        states={APPROVE: [RegexHandler('^(Да)|(Нет)$', approve)]},
        fallbacks=[CommandHandler('start', start)]
    )

    mailing = ConversationHandler(
        entry_points=[RegexHandler('^Отправить всем$', start_sendtoall)],
        states={SECOND: [MessageHandler(Filters.text, get_text_to_send)],
                THIRD: [MessageHandler(Filters.text, start_send)]},
        fallbacks=[CommandHandler('start', start)]
    )

    dp.add_handler(mailing)
    dp.add_handler(pass_change)
    dp.add_handler(MessageHandler(Filters.text, search_wo_cat))
    dp.add_handler(MessageHandler(Filters.document, process_file))
    updater.start_polling()
    updater.idle()

