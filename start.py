import subprocess
import sys

"""Данный файл py нужен для старта двух файлов одновременно"""

'''Запускаем Бота для приема оплаты и настройки, а также ботов для ИИ-Ассистентов'''
process1 = subprocess.Popen([sys.executable, "main.py"]) #Прием оплат и настройка
process2 = subprocess.Popen([sys.executable, "openrouter.py"]) #ИИ-Ассистенты

"""Дожидаемся завершения всех ботов"""
try:
    process1.wait()
    process2.wait()
except KeyboardInterrupt: #Если происходит завершение вручную на сервере
    print("Process interrupted by user")
    process1.terminate()  # или process1.kill() для более жесткого завершения
    process2.terminate()  # или process2.kill()

    """На всякий случай ждем"""
    process1.wait()
    process2.wait()