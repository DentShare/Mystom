# Протокол работы с Git и GitHub

Краткая инструкция по обновлению файлов проекта в GitHub.

---

## 1. Проверить статус

```bash
git status
```

Показывает изменённые (modified), новые (untracked) и удалённые файлы.

---

## 2. Добавить файлы в индекс

**Всё разом:**
```bash
git add .
```

**Выборочно:**
```bash
git add app/services/reminder_service.py
git add app/services/timezone.py
```

---

## 3. Создать коммит

```bash
git commit -m "Краткое описание изменений"
```

Примеры сообщений:
- `Учёт часового пояса врача в напоминаниях`
- `Добавлен local_to_utc в timezone.py`
- `Исправлена авторизация в веб-админке`

---

## 4. Отправить в GitHub

Если ветка уже привязана к `origin`:

```bash
git push origin main
```

(или `master` — смотрите текущую ветку: `git branch`)

**Настроить remote (один раз):**
```bash
git remote -v
git remote set-url origin https://github.com/ВАШ_ЛОГИН/MiniStom.git
git push -u origin main
```

---

## Полная цепочка

```bash
git status
git add .
git commit -m "Описание изменений"
git push origin main
```

---

## Полезные команды

| Действие | Команда |
|----------|--------|
| Отменить добавление файла из индекса | `git restore --staged путь/к/файлу` |
| Посмотреть изменения до коммита | `git diff` (не в индексе), `git diff --staged` (в индексе) |
| Отменить последний коммит, оставив изменения | `git reset --soft HEAD~1` |
| Подтянуть изменения с GitHub | `git pull origin main` |
| Список веток | `git branch` |
| Список удалённых репозиториев | `git remote -v` |

---

## Важно

1. Сначала всегда `git add` и `git commit`, затем `git push`.
2. Перед первым push в новый репозиторий настройте `origin` и при необходимости `git push -u origin main`.
3. Если на GitHub появились новые коммиты, сначала выполните `git pull origin main`, затем делайте свои изменения и push.
