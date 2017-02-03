import random
from telegram import ReplyKeyboardMarkup, ParseMode
from telegram.ext import Updater, CommandHandler, RegexHandler, MessageHandler, Filters, ConversationHandler
from telegram.contrib.botan import Botan
from config import ALLTESTS, BOTAN_TOKEN, LEGAL, ADMINS
from pyexcel_xlsx import get_data, save_data
from itertools import zip_longest
from collections import OrderedDict
import logging
from datetime import datetime as dt
import os
import sys
import functools
from model import save, Users, \
    UndefinedRequests, Company, Good, Service, Aliases, DoesNotExist, fn, \
    before_request_handler, after_request_handler, Passwords


start_msg = 'Привет! Я буду защищать тебя от обмана в рекламе и помогу с безопасным выбором мест для покупки товаров и услуг. ' \
            'В моей базе - несколько сотен компаний и рекламных роликов и она постоянно пополняется. ' \
            'Для поиска просто введи название компании, рекламного ролика, товара или фразы из рекламы. ' \
            'Если информации не будет в базе, мы получим твой запрос и организуем проверку'

ASK_PASS, APPROVE = range(2)

dbs = {'Компания': Company,
       'Услуга': Service,
       'Товар': Good,
       'Алиасы': Aliases}

SEARCH = 1
user_search = dict()

aliases = [Aliases.alias1,
           Aliases.alias2,
           Aliases.alias3,
           Aliases.alias4,
           Aliases.alias5,
           Aliases.alias6,
           Aliases.alias7,
           Aliases.alias8,
           Aliases.alias9,
           Aliases.alias10]

botan = Botan(BOTAN_TOKEN)

search_fckup_msg = '''Мы не нашли совпадений, но приняли заявку на проверку!

Признаки недобросовестного Интернет-магазина:
- Отсутствие на сайте юридического или фактического адреса;
- Отсутствие на сайте официального названия продавца (например, ООО "Ромашка", ИП Иванов и т.п.);
- Администратор домена отличается от компании, указанной на сайте (можно проверить через https://www.reg.ru/whois/).

Признаки недобросовестной рекламы:
- Сноски, "звездочки" и оговорки мелким шрифтом;
- Утверждения "самый", "лучший", "первый";
- Негативная информация про конкурентов;
- Заявления об одобрении органами власти.

Будем рады выполнить другой запрос!'''


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
    after_request_handler()
    return False


def get_new_layout(uid):
    if uid in ADMINS:
        k_clients = [['Выгрузка'], ['Сгенерировать пароль']]
        return k_clients


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


@check_password
def start(bot, update):
    print(update)
    uid = update.message.from_user.id
    bot.sendMessage(uid, start_msg, reply_markup=ReplyKeyboardMarkup(get_new_layout(uid), resize_keyboard=True))


@check_password
def search_wo_cat(bot, update):
    print(update)
    uid = update.message.from_user.id
    message = update.message.text.strip('"\'!?[]{},. ').lower()
    res = []
    msg = ''
    try:
        check_aliases = (Aliases.select().where((fn.lower(Aliases.alias1) == message) |
                                                (fn.lower(Aliases.alias2) == message) |
                                                (fn.lower(Aliases.alias3) == message) |
                                                (fn.lower(Aliases.alias4) == message) |
                                                (fn.lower(Aliases.alias5) == message) |
                                                (fn.lower(Aliases.alias6) == message) |
                                                (fn.lower(Aliases.alias7) == message) |
                                                (fn.lower(Aliases.alias8) == message) |
                                                (fn.lower(Aliases.alias9) == message) |
                                                (fn.lower(Aliases.alias10) == message))).execute()
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
    if not res:
        if unknown_req_add(uid, message.strip('"\'!?[]{},. ')):
            bot.sendMessage(uid, search_fckup_msg,
                            disable_web_page_preview=True,
                            reply_markup=ReplyKeyboardMarkup(get_new_layout(uid), resize_keyboard=True))
        else:
            bot.sendMessage(uid, search_fckup_msg,
                            disable_web_page_preview=True,
                            reply_markup=ReplyKeyboardMarkup(get_new_layout(uid), resize_keyboard=True))
            return
    for m in res:
        msg += '<b>{}</b>\n{}\n{}\n\n'.format(m.name, m.description, m.url)
    bot.sendMessage(uid, msg, parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                    reply_markup=ReplyKeyboardMarkup(get_new_layout(uid), resize_keyboard=True))
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
                columns = ['key', 'alias1', 'alias2', 'alias3', 'alias4', 'alias5', 'alias6', 'alias7', 'alias8', 'alias9', 'alias10']
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
    if uid in ADMINS:
        before_request_handler()
        while True:
            new_password = generate_password()
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
    if message == 'Да':
        query = Passwords.update(active=0)
        query.execute()
        bot.sendMessage(uid, 'Пароль изменил')
    elif message == 'Нет':
        bot.sendMessage(uid, 'Пароль не менял')


if __name__ == '__main__':
    updater = None
    token = None
    if len(sys.argv) > 1:
        token = sys.argv[-1]
        if token.lower() == 'legal':
            updater = Updater(LEGAL)
            BASE_DIR = os.path.dirname(os.path.abspath(__file__))
            logging.basicConfig(filename=BASE_DIR + '/out.log', filemode='a', format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
    else:
        updater = Updater(ALLTESTS)
        logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG)

    dp = updater.dispatcher
    dp.add_handler(CommandHandler('unload', output))
    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(RegexHandler('^Выгрузка$', output))
    dp.add_handler(RegexHandler('^Сгенерировать пароль$', get_new_password))

    pass_change = ConversationHandler(
        entry_points=[RegexHandler('^Сгенерировать пароль$', get_new_password)],
        states={APPROVE: [RegexHandler('^(Да)|(Нет)$', approve)]},
        fallbacks=[CommandHandler('start', start)]
    )
    dp.add_handler(pass_change)
    dp.add_handler(MessageHandler(Filters.text, search_wo_cat))
    dp.add_handler(MessageHandler(Filters.document, process_file))
    updater.start_polling()
    updater.idle()

