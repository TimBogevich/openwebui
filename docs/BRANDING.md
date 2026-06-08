# Брендирование интерфейса

Интерфейс Open WebUI кастомизирован под корпоративный стиль ОАО «РЖД» через статические файлы в `static/`.

---

## Компоненты брендирования

### `custom.css` — тёмная тема РЖД

Тёмно-графитовая боковая панель (`#3a3a3e`), акценты красным РЖД (`#E21A1A`). Основные изменения:

- **Боковая панель:** заменены цвета, скрыты элементы Workspace, Auth, Suggestions, имена моделей
- **Заголовок:** удалён «Open WebUI», заменён на «РЖД Интер» через `loader.js`
- **Логотип:** RZD logo в хедере, аватаре и фавиконе
- **Footer:** кастомный профиль с зелёным индикатором «в сети»
- **White-flash fix:** принудительная замена светлых Tailwind-классов (`from-white`, `via-white`, `bg-gradient-to-b`) на прозрачные/тёмные внутри `#sidebar`
- **Пункт меню «Загрузить доклад»:** красная иконка файла, ссылка на `:8810`

Всего ~32 секции стилей.

### `loader.js` — runtime DOM-инъекция

JavaScript, выполняемый при загрузке страницы:

- Удаление «(Open WebUI)» из `<title>` → «РЖД Интер»
- Создание `#rzd-brand` хедера с RZD-логотипом (46px, переиспользует фавикон OWI)
- Принудительное открытие боковой панели
- Footer profile: аватар + зелёный `#rzd-live` badge, имя → «Оператор»
- Пункт меню «Загрузить доклад» (клон строки Настройки → «Загрузить доклад», ссылка на `:8810`)

### Статические ресурсы

| Файл | Назначение |
|---|---|
| `rzd_logo.png` | Фавикон, аватар модели, логотип на сплеш-скрине |
| `rzd_logo.svg` | Векторный фавикон |
| `rzd_logo_dark.png` | Светло-серый логотип для тёмной боковой панели |
| `rzd_splash.png` | Заставка загрузки |
| `rzd_user.png` | Аватар пользователя в футере |

---

## Монтирование в Docker

Файлы монтируются как bind-тома в контейнер Open WebUI. Важно: статика обслуживается из `/app/build/static/`, но некоторые серверные ссылки идут через `/app/backend/open_webui/static/` — монтируются **оба пути**:

```yaml
volumes:
  - ./static/custom.css:/app/build/static/custom.css
  - ./static/custom.css:/app/backend/open_webui/static/custom.css
  - ./static/loader.js:/app/build/static/loader.js
  - ./static/loader.js:/app/backend/open_webui/static/loader.js
  # ... фавиконы, логотипы аналогично
```

Сборка не требуется — изменения в `static/` применяются после перезапуска контейнера.

---

## Настройки Open WebUI для брендирования

```python
# Название
httpx.post(f"{BASE}/api/v1/configs/update", headers=H, json={
    "WEBUI_NAME": "РЖД Интер",
})

# Русские подсказки
httpx.post(f"{BASE}/api/v1/configs/update", headers=H, json={
    "ui": {
        "prompt_suggestions": [
            {"title": ["Показатели за сегодня", "Красная зона"], "content": "..."},
            # ...
        ]
    }
})

# Локаль
httpx.post(f"{BASE}/api/v1/configs/update", headers=H, json={
    "DEFAULT_LOCALE": "ru-RU",
})

# Имя пользователя → «Оператор»
# db/set_brand.py
```
