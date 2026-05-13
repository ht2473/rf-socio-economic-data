# 🇷🇺 Социально-экономические показатели регионов России

[![CI: validate](https://github.com/ht2473/russia-regions-dataset/actions/workflows/validate.yml/badge.svg)](https://github.com/ht2473/russia-regions-dataset/actions/workflows/validate.yml)
[![License: CC BY](https://img.shields.io/badge/Data%20License-CC%20BY%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by/4.0/)
[![License: MIT](https://img.shields.io/badge/Code%20License-MIT-green.svg)](LICENSE)
[![Data source: Росстат](https://img.shields.io/badge/Источник-Росстат-blue)](https://rosstat.gov.ru/folder/210)
[![Dataset version](https://img.shields.io/badge/версия-3.0%20(2026--03--13)-orange)](CHANGELOG.md)

Готовый к анализу датасет из **19 сборников Росстата** о социально-экономическом развитии регионов России.  
Первичная обработка: [«Если быть точным»](https://tochno.st/datasets/regions_collection). Репозиторий добавляет воспроизводимый ETL-пайплайн, справочные таблицы и примеры анализа.

---

## 📊 Ключевые цифры

| | |
|---|---|
| **Строк** | 1 969 010 |
| **Показателей** | 1 294 |
| **Регионов** | 87 |
| **Разделов** | 117 |
| **Временной охват** | 2001–2025 |
| **Сборников Росстата** | 19 (38 изданий) |
| **Валидных значений** | 92.4 % |

**Тематика:** доходы, зарплаты, демография, промышленность, инвестиции, транспорт, здравоохранение, образование, жильё, экология и др.

---

## 🗂 Структура репозитория

```
russia-regions-dataset/
├── Makefile                          # make all / validate / search / clean
├── requirements.txt
├── CHANGELOG.md
├── CONTRIBUTING.md
│
├── scripts/
│   ├── 01_process.py    # ETL: raw → processed (CLI, zstd, streaming CSV)
│   ├── 02_validate.py   # Quality checks → docs/data_profile.md
│   └── 03_explore.py    # CLI: examples | search | info
│
├── notebooks/
│   └── explore.ipynb    # Jupyter notebook (GitHub-renderable)
│
├── data/
│   ├── raw/             # Source parquet — NOT in git (download separately)
│   ├── processed/
│   │   ├── regions_full.parquet    # Full cleaned dataset — NOT in git
│   │   ├── regions_full.csv.gz     # Same, gzip CSV — NOT in git
│   │   ├── catalogue.parquet/.csv  # Indicator reference  (1 294 rows) ✓ git
│   │   ├── objects.parquet/.csv    # Territory reference  (98 rows)    ✓ git
│   │   └── sections.parquet/.csv   # Section coverage     (117 rows)   ✓ git
│   └── samples/
│       └── regions_sample_1000.*   # Stratified sample    (1 000 rows) ✓ git
│
└── docs/
    ├── data_profile.md             # Auto-generated quality report      ✓ git
    └── description_*.pdf           # Official Rosstat documentation     ✓ git
```

---

## ⬇️ Получить полный датасет

`regions_full.parquet` не хранится в git (слишком большой). Два способа:

**Вариант 1 — скачать и обработать самостоятельно:**
```bash
# Скачайте parquet с https://tochno.st/datasets/regions_collection
# Положите в data/raw/ и запустите:
make all
```

**Вариант 2 — только скрипт, без make:**
```bash
python scripts/01_process.py --input data/raw/<filename>.parquet
```

Если полного файла нет — все скрипты автоматически падают на выборку `regions_sample_1000.parquet`, которая уже есть в репозитории.

---

## 🚀 Быстрый старт

### Установка

```bash
git clone https://github.com/ht2473/russia-regions-dataset.git
cd russia-regions-dataset
make install       # pip install -r requirements.txt
```

### Pipeline

```bash
make all           # ETL + валидация (нужен raw файл в data/raw/)
make validate      # только валидация  → docs/data_profile.md
make sample        # валидация по выборке (быстро, без raw)
```

### Поиск показателей

```bash
make search Q=зарплата
make search Q=здравоохранение
# или напрямую:
python scripts/03_explore.py search зарплата
python scripts/03_explore.py search --field section инвестиции
python scripts/03_explore.py info
```

### Примеры анализа

```bash
python scripts/03_explore.py examples
# или в Jupyter:
jupyter notebook notebooks/explore.ipynb
```

---

## 🐍 Python API

```python
import pandas as pd

# Загрузка
df = pd.read_parquet("data/processed/regions_full.parquet")

# Только валидные значения — всегда фильтруй сначала
clean = df[df["value_status"] == "ok"]

# Поиск нужного показателя
cat = pd.read_parquet("data/processed/catalogue.parquet")
cat[cat["indicator_name"].str.contains("зарплата", case=False)]

# ВРП регионов за последний год
grp = clean[
    clean["indicator_name"].str.contains("Валовой региональный продукт") &
    (clean["object_level"] == "Регион")
]
latest = grp[grp["year"] == grp["year"].max()]
print(latest.nlargest(10, "indicator_value")[["object_name", "indicator_value", "indicator_unit"]])

# Динамика зарплат по округам
wages = clean[
    clean["indicator_name"].str.contains("Среднемесячная.*заработная плата") &
    (clean["object_level"] == "Федеральный округ")
].groupby(["object_name", "year"])["indicator_value"].mean().unstack("year")
print(wages[[c for c in wages.columns if c >= 2015]].round(0))
```

---

## 📐 Структура данных

| Атрибут | Тип | Описание |
|---------|-----|----------|
| `section` | str | Тематический раздел (117 уникальных) |
| `indicator_code` | str | Уникальный код показателя |
| `indicator_name` | str | Название показателя |
| `subsection` | str | Разрез (пол, вид деятельности и т.п.); `CD` = нет разреза |
| `object_name` | str | Название территории |
| `object_level` | str | `Регион` / `Федеральный округ` / `Страна` |
| `object_oktmo` | str | Код ОКТМО |
| `object_okato` | str | Код ОКАТО |
| `year` | int | Год наблюдения |
| `indicator_value` | float | Значение (или sentinel — см. ниже) |
| `indicator_unit` | str | Единица измерения; `ND` = не определена |
| `comment` | str | Комментарии Росстата; `CD` = нет |
| `source` | str | Название и год сборника |
| `version_date` | str | Версия датасета |
| **`value_status`** ⭐ | str | **Добавлено:** `ok` / `no_data` / `hidden` |

### Пропущенные значения

| `value_status` | Sentinel в `indicator_value` | Смысл |
|---|---|---|
| `ok` | реальное число | Валидное наблюдение |
| `no_data` | `-99999999` | Нет в источнике / ошибочное |
| `hidden` | `-77777777` | Скрыто Росстатом (прочерк / многоточие) |

**Всегда фильтруй `df[df["value_status"] == "ok"]` перед анализом.**

### О дублях по первичному ключу

Ключ `(indicator_code, subsection, object_oktmo, year)` **не уникален** в источнике:
один и тот же показатель может поступать из нескольких сборников Росстата за один год.
Это **задокументированное поведение** (§4 «Полнота данных» в официальной документации),
не ошибка данных. Датасет сохраняет последнее ненулевое значение из более позднего сборника.

---

## 🔄 Опции pipeline

```bash
# Изменить размер выборки
python scripts/01_process.py --sample-n 5000

# Изменить сжатие (zstd по умолчанию; snappy — быстрее, больше файл)
python scripts/01_process.py --compression snappy

# Пропустить тяжёлый CSV-шаг
python scripts/01_process.py --no-csv-gz

# Все опции
python scripts/01_process.py --help
python scripts/02_validate.py --help
python scripts/03_explore.py --help
```

---

## 📖 Источник и цитирование

**Данные:** Росстат, [Статистические издания](https://rosstat.gov.ru/folder/210)  
**Первичная обработка:** [«Если быть точным»](https://tochno.st/datasets/regions_collection), 2026  
**Версия:** 3.0 (13.03.2026)

**Цитирование (рус.):**
> «Социально-экономические показатели регионов России» // Росстат; обработка: «Если быть точным», 2026. URL: https://tochno.st/datasets/regions_collection

**Citation (EN):**
> Socio-economic indicators of Russian regions // Rosstat (Russia); data-processing: «To Be Precise», 2026. URL: https://tochno.st/datasets/regions_collection

---

## 📄 Лицензия

- **Данные:** [Creative Commons BY 4.0](https://creativecommons.org/licenses/by/4.0/) — указывай источник
- **Код:** [MIT License](LICENSE)
