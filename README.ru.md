# Shorts Studio kit

[English](README.md) · **Русский**

Переносимый набор для коротких вертикальных видео (YouTube Shorts, Reels, TikTok) из исходных кадров и закадрового голоса:
сценарий и озвучка, монтаж по `edl.json`, автоматические проверки, сведение звука, упаковка для загрузки. Набор **не привязан к
тематике**: всё, что относится к конкретному каналу (тема, языки, аудитория, правила контента, внешний вид, голос, расписание),
лежит в одном файле `CHANNEL.md` в папке проекта, а скиллы читают его первым.

Один и тот же репозиторий ставится и в **Claude Code**, и в **Codex**: оба читают `skills/*/SKILL.md` и манифест плагина.

## Что внутри

| Папка | Что это |
|---|---|
| `skills/shorts-script-voice` | тема, сценарий, озвучка локальным Kokoro, проверка whisper, заголовок |
| `skills/shorts-pipeline` | основной процесс: кадры, `edl.json`, рендер, `check.py`, звук, делегирование редактору-агенту; справочники в `references/` (разбор `edl.json`, уроки, шаблон задания, шаблон `edl-template.json`) |
| `skills/shorts-packaging` | папка `ready/`, нумерация, блок для описания загрузки, расписание, перенос в `published/` |
| `engine/_pipeline`, `engine/_fonts` | движок (Python + ffmpeg), темы оформления, проверки, звук (3 CC0-трека, синтезированные эффекты), шрифты под OFL |
| `tools/` | озвучка (`build_vo.py`), слова с таймингами (`words.py`), загрузка клипов (`grab.py`, `ytdl.sh`), карточка-цитата, тонмаппинг HDR |
| `engine/templates/` | пустой профиль канала `CHANNEL.md` и правила проекта `PROJECT-AGENTS.md` |
| `extras/gaming/` | необязательное: загрузка трейлеров и скриншотов из магазина Steam |
| `scripts/` | `install-system-deps.sh` (ffmpeg, Python, curl), `setup.sh` (пакеты, модели), `shorts-init.sh` (новая папка проекта), `doctor.sh` (проверка всех зависимостей), `install-codex.sh` |
| `DEPENDENCIES.md`, `Brewfile`, `engine/requirements*.txt`, `engine/models.sha256` | полный список зависимостей, точные версии пакетов, контрольные суммы моделей |
| `.claude-plugin/`, `.codex-plugin/` | манифесты плагина и маркетплейса |

## Установка (macOS; на Linux то же, кроме `brew`)

Все зависимости перечислены в `DEPENDENCIES.md` (системные программы, пакеты Python с точными версиями, модели, место на диске).

1. **Системные программы** (один раз): `scripts/install-system-deps.sh` (Homebrew или apt; перед установкой спрашивает) или
   `brew bundle --file Brewfile`. Нужны Python 3.10+, ffmpeg (с `libx264` и `aac`), curl.
2. **Набор**: `git clone https://github.com/ilyamelnichenkov/youtube-shorts ~/shorts-studio` или распакуйте архив туда же.
3. **Окружение, голос и расшифровка** (скачивается около 1 ГБ: пакеты, модели Kokoro с проверкой контрольной суммы и whisper `small`):
   ```bash
   cd ~/shorts-studio
   scripts/setup.sh
   echo 'export SHORTS_HOME="$HOME/.shorts-studio"' >> ~/.zshrc
   ```
   Всё ставится в `$SHORTS_HOME` (по умолчанию `~/.shorts-studio`: `venv/`, `kokoro/models/`, копия набора `kit/`); модель whisper
   кладётся в кэш Hugging Face (`~/.cache/huggingface` или `$HF_HOME`). Без моделей: `scripts/setup.sh --skip-models`.
4. **Claude Code**:
   ```bash
   claude plugin marketplace add ~/shorts-studio
   claude plugin install shorts-studio@shorts-studio-kit
   ```
5. **Codex** (любой из двух способов):
   ```bash
   codex plugin marketplace add ~/shorts-studio
   codex plugin add shorts-studio@shorts-studio-kit
   # или без маркетплейса, копированием скиллов в ~/.codex/skills:
   scripts/install-codex.sh
   ```
   После установки перезапустите Codex. Правила проекта для Codex лежат в `AGENTS.md` папки проекта (его создаёт `shorts-init.sh`).
6. **Папка проекта**:
   ```bash
   scripts/shorts-init.sh ~/Shorts        # движок, инструменты, шрифты, пустой CHANNEL.md, AGENTS.md, BRIEF.md
   scripts/doctor.sh ~/Shorts             # проверяет ВСЕ зависимости; должно закончиться "All good."
   ```
   Затем откройте `~/Shorts` в Claude Code или Codex и попросите заполнить `CHANNEL.md` вместе с вами.

## Как этим пользоваться

- «Заполни профиль канала» (агент задаёт вопросы по разделам `CHANNEL.md`).
- «Придумай тему и напиши сценарий для видео про …» → скилл `shorts-script-voice`.
- «Сделай видео по этому сценарию» → `shorts-pipeline`: голос, клипы, `edl.json`, рендер, проверки, звук.
- «Упакуй для загрузки» → `shorts-packaging`.
- Для большой партии: агент-редактор получает `BRIEF.md`, а сценарий, голос, просмотр каждого кадра и звук остаются за основной сессией.

## Под свою тему

Скиллы про тему ничего не знают. Заполните `CHANNEL.md` (языки, аудитория, правила фактов и контента, источники кадров, подписи, голос,
расписание). Внешний вид выбирается темой движка (`case-file`, `panel-heist`, `vice-dusk`, `classic`); голос, скорость и язык задаются в
`vo/beats.json` (`voice`, `speed`, `lang`) или переменными `SHORTS_VOICE`, `SHORTS_SPEED`, `SHORTS_LANG`. Язык whisper берётся из `lang`.
Слитные подписи вида «ACME 6» включаются ключом `captions.join_prefix` в `edl.json`.

## Что не входит и почему

- **Кадры и готовые ролики**: набор их не содержит и не распространяет. Журнал источников ведёт `_footage/SOURCES.md` проекта.
- **Системные программы, пакеты Python и модели**: в репозиторий не входят (размер и лицензии), ставятся скриптами `install-system-deps.sh`
  и `setup.sh`; список и версии в `DEPENDENCIES.md`. Сведению звука хватает одного venv.
- **Длинные ролики 16:9**: код (`wide.py`, `longform.py`) в движке есть, но демо-проекта и проверки этого пути в наборе нет.

## Обновление

`scripts/shorts-init.sh <проект> --update` заменяет `_pipeline`, `_tools`, `_fonts` проекта копией из набора и ничего больше не трогает.

## Что проверено

Полный список с результатами: `TESTED.md`. Коротко:
- `claude plugin validate` проходит для плагина и маркетплейса.
- `setup.sh` с нуля, с настоящей загрузкой моделей и проверкой контрольных сумм, затем `doctor.sh` без замечаний (около 1,2 ГБ).
- `check.py` на готовом ролике даёт `ALL CHECKS PASS`; кадры и обложка совпадают с эталонным рендером без отличий.
- Сведение звука в чистом окружении: −14,10 LUFS, −1,30 dBTP и 0 ошибок слов, как у эталона. Озвучка и whisper на испанском и английском.
- **Не проверено**: установка плагина командами `claude plugin install` / `codex plugin add` и `install-codex.sh` (меняют настройки пользователя),
  `install-system-deps.sh` (ставит системные пакеты), Linux и Windows.

## Лицензии

Код и документация набора распространяются по лицензии MIT (файл `LICENSE`). Она не распространяется на сторонние материалы внутри
репозитория, у них свои условия: шрифты под SIL OFL (тексты рядом в `engine/_fonts/*/OFL.txt`) и три CC0-трека с Freesound (лицензии и
ссылки в `engine/_pipeline/sound/music/`). Эффекты синтезируются кодом. Сторонние программы и модели (ffmpeg, Kokoro, faster-whisper,
yt-dlp и пакеты из `requirements.lock.txt`) в репозиторий не входят и подчиняются своим лицензиям, подробнее в `NOTICE.md`.
