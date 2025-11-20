#!/usr/bin/env python3
"""
Скрипт для коммита и пуша изменений в GitHub
Обходит проблему с Xcode лицензией, используя прямой вызов git
"""
import subprocess
import sys
import os

def run_git_command(cmd, check=True):
    """Выполняет git команду"""
    try:
        # Используем полный путь к git, чтобы обойти проблему с Xcode
        git_path = "/usr/bin/git"
        if not os.path.exists(git_path):
            git_path = "git"
        
        result = subprocess.run(
            [git_path] + cmd.split(),
            capture_output=True,
            text=True,
            check=check
        )
        return result.stdout.strip(), result.returncode
    except subprocess.CalledProcessError as e:
        return e.stdout + e.stderr, e.returncode
    except Exception as e:
        return str(e), 1

def main():
    print("🔄 Добавление изменений в git...")
    stdout, code = run_git_command("add main.py README.md requirements.txt deploy.sh COMMIT_AND_PUSH.sh git_push.py", check=False)
    if code != 0:
        print(f"⚠️  Предупреждение при добавлении файлов: {stdout}")
    
    print("📝 Создание коммита...")
    stdout, code = run_git_command('commit -m "Обновление бота: исправлена логика таймера, добавлена загрузка токена из .env, обновлена документация"', check=False)
    if code != 0:
        if "nothing to commit" in stdout.lower():
            print("ℹ️  Нет изменений для коммита")
        else:
            print(f"⚠️  Ошибка при коммите: {stdout}")
            return
    
    print("🔍 Проверка удаленного репозитория...")
    stdout, code = run_git_command("remote -v", check=False)
    
    if "origin" not in stdout:
        print("➕ Добавление remote для https://github.com/gukaylo/cnnctd_wyr...")
        run_git_command("remote add origin https://github.com/gukaylo/cnnctd_wyr.git", check=False)
        run_git_command("remote set-url origin https://github.com/gukaylo/cnnctd_wyr.git", check=False)
    
    print("📤 Отправка изменений в GitHub...")
    # Определяем текущую ветку
    branch_stdout, _ = run_git_command("branch --show-current", check=False)
    current_branch = branch_stdout.strip() or "main"
    
    # Пробуем push
    stdout, code = run_git_command(f"push -u origin {current_branch}", check=False)
    if code == 0:
        print("✅ Изменения успешно отправлены в GitHub!")
    else:
        # Пробуем main или master
        for branch in ["main", "master"]:
            stdout, code = run_git_command(f"push -u origin {branch}", check=False)
            if code == 0:
                print(f"✅ Изменения успешно отправлены в GitHub (ветка {branch})!")
                return
        print(f"❌ Ошибка при отправке: {stdout}")
        print("💡 Попробуйте выполнить вручную: git push -u origin <branch>")

if __name__ == "__main__":
    main()

