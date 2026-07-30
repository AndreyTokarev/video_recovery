# Video Recovery

Пакетный исправитель видеофайлов курса: чинит **контейнер MP4** (HLS remux / non-interleaved fMP4), из‑за которого файл играет в Windows, но ломается в VLC.

По умолчанию — **lossless remux** (`-c copy` + `faststart`), без перекодирования.

## Что чинит

Типичные признаки проблемных файлов курса:

- encoder вроде `videojs-contrib-hls`
- fragmented MP4 (`moof` / `mvex`)
- аудио и видео в двух огромных неперемешанных фрагментах

Подробнее: [legacy/docs/PROBLEM_AND_SOLUTION.ru.md](legacy/docs/PROBLEM_AND_SOLUTION.ru.md).

## Требования

- Python **3.12+** и [uv](https://docs.astral.sh/uv/)
- **FFmpeg** (`ffmpeg` + `ffprobe` в PATH, либо в `bin/` рядом с проектом/бинарником)

## Установка (разработка)

```bash
uv sync
```

Скачать FFmpeg в `bin/` (Windows):

```powershell
powershell -ExecutionPolicy Bypass -File scripts/fetch_ffmpeg.ps1
```

## GUI

```bash
uv run video-recovery gui
# или
uv run video-recovery-gui
```

В интерфейсе:

1. Выберите папку курса
2. **Только анализ** — диагностика без записи
3. **Исправить файлы** — создать `*_fixed.mp4` (или заменить оригинал с `.bak`)

По умолчанию чинятся только файлы с findings `critical` / `high`.

## CLI

```bash
# Один файл
uv run video-recovery analyze "lesson.mp4"
uv run video-recovery fix "lesson.mp4"
uv run video-recovery fix "lesson.mp4" --mode remux

# Папка курса
uv run video-recovery batch "D:\courses\mechanics" --fix
uv run video-recovery batch "D:\courses\mechanics" --fix --force-all
```

## Сборка Windows-бинарника

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1
```

Результат: `dist/VideoRecovery/VideoRecovery.exe` (+ `ffmpeg.exe` / `ffprobe.exe` рядом, если были в `bin/`).

Архивируйте всю папку `dist/VideoRecovery` для раздачи.

## Структура

```text
src/video_recovery/   # пакет (analyze / fix / batch / gui)
legacy/               # исходные скрипты и документация проблемы
scripts/              # fetch FFmpeg, build Windows
```

## Лицензия

MIT
